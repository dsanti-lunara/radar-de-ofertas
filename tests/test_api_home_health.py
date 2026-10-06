from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from radar.api import __main__ as api_main
from radar.api.app import create_app
from radar.domain.home_health import HOME_HEALTH_CAPABILITIES
from radar.infrastructure.database import create_database_engine
from radar.infrastructure.settings import Settings

pytestmark = pytest.mark.contract


def _client(database_url: str, *, control_center_dist: Path | str | None = None) -> TestClient:
    settings = Settings(database_url=database_url)
    engine = create_database_engine(database_url)
    return TestClient(
        create_app(
            settings=settings,
            engine=engine,
            control_center_dist=control_center_dist,
        )
    )


def _item(body: dict[str, Any], capability: str) -> dict[str, Any]:
    items = body["items"]
    assert isinstance(items, list)
    return next(item for item in items if item["capability"] == capability)


def test_overview_reports_core_and_database_and_never_invents_capabilities(
    migrated_database_url: str,
) -> None:
    response = _client(migrated_database_url).get(
        "/health/overview", headers={"X-Correlation-ID": "cid-home"}
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["schema_version"] == "1.0"
    assert body["correlation_id"] == "cid-home"
    assert response.headers["x-correlation-id"] == "cid-home"
    assert response.headers["cache-control"] == "no-store"
    assert [item["capability"] for item in body["items"]] == list(HOME_HEALTH_CAPABILITIES)

    assert _item(body, "core")["state"] == "HEALTHY"
    assert _item(body, "database")["state"] == "HEALTHY"

    # Every dependency without a registered integration is UNKNOWN, never healthy.
    for capability in HOME_HEALTH_CAPABILITIES:
        if capability in {"core", "database"}:
            continue
        unproven = _item(body, capability)
        assert unproven["state"] == "UNKNOWN", capability
        assert unproven["reason_code"] == "INTEGRATION_NOT_REGISTERED"

    # Unknown dependencies degrade the aggregate state instead of advertising health.
    assert body["status"] == "DEGRADED"

    # REST is served same-origin from localhost; no CORS/public surface is opened.
    assert "access-control-allow-origin" not in response.headers


def test_registered_integrations_drive_the_strip_without_inventing(
    migrated_database_url: str,
) -> None:
    client = _client(migrated_database_url)
    for name, state in (
        ("telegram", "ONLINE"),
        ("whatsapp", "OFFLINE"),
        ("ai", "DEGRADED"),
        ("mercado_livre", "AUTH_REQUIRED"),
    ):
        assert (
            client.put(
                f"/integrations/{name}",
                json={"schema_version": "1.0", "state": state, "summary": f"{name} {state}"},
            ).status_code
            == 200
        )

    body = client.get("/health/overview").json()
    assert _item(body, "telegram")["state"] == "HEALTHY"
    assert _item(body, "ai")["state"] == "DEGRADED"
    assert _item(body, "whatsapp")["state"] == "UNHEALTHY"
    assert _item(body, "mercado_livre")["state"] == "UNHEALTHY"
    # A capability that was never registered stays UNKNOWN.
    assert _item(body, "shopee")["state"] == "UNKNOWN"


def test_unavailable_database_error_is_actionable_and_does_not_leak_configuration(
    unavailable_database_url: str,
) -> None:
    response = _client(unavailable_database_url).get("/health/overview")
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["status"] == "UNHEALTHY"
    assert _item(body, "core")["state"] == "HEALTHY"

    database = _item(body, "database")
    assert database["state"] == "UNHEALTHY"
    error = database["error"]
    assert error["code"] == "RAD-DB-003"
    assert error["retryable"] is True
    assert error["action"]

    # The integration store is also unreachable; the strip says so instead of
    # pretending the integrations are simply unregistered.
    assert _item(body, "shopee")["state"] == "UNKNOWN"
    assert _item(body, "shopee")["reason_code"] == "INTEGRATION_HEALTH_UNAVAILABLE"

    # The configuration (path/URL) is not echoed back to the caller.
    assert unavailable_database_url not in response.text
    assert "not-a-database" not in response.text


def test_overview_honors_caller_correlation_id_and_local_binding(
    migrated_database_url: str,
) -> None:
    response = _client(migrated_database_url).get(
        "/health/overview", headers={"X-Correlation-ID": "caller-correlation"}
    )
    assert response.json()["correlation_id"] == "caller-correlation"
    assert response.headers["x-correlation-id"] == "caller-correlation"

    # The API is only exposed on the loopback interface (AUT-402).
    assert api_main.LOCAL_HOST == "127.0.0.1"


def test_control_center_assets_are_served_locally_when_built(
    migrated_database_url: str, tmp_path: Path
) -> None:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(
        "<!doctype html><html><body><div id='root'>RADAR_CC_MARKER</div>"
        "<script type='module' src='/assets/app.js'></script></body></html>",
        encoding="utf-8",
    )
    (dist / "assets" / "app.js").write_text("console.log('radar-cc-asset');", encoding="utf-8")

    client = _client(migrated_database_url, control_center_dist=dist)

    index = client.get("/")
    assert index.status_code == 200
    assert "text/html" in index.headers["content-type"]
    assert "RADAR_CC_MARKER" in index.text

    asset = client.get("/assets/app.js")
    assert asset.status_code == 200
    assert "radar-cc-asset" in asset.text

    # API routes keep precedence over the static mount.
    health = client.get("/health")
    assert health.status_code == 200
    assert health.headers["content-type"].startswith("application/json")


def test_core_operates_without_a_control_center_build(
    migrated_database_url: str, tmp_path: Path
) -> None:
    missing = tmp_path / "no-control-center"

    client = _client(migrated_database_url, control_center_dist=missing)

    assert client.get("/health").status_code == 200
    assert client.get("/health/overview").status_code == 200
    assert client.get("/version").status_code == 200
    assert client.get("/config").status_code == 200
    # The UI is absent, so the root is not served.
    assert client.get("/").status_code == 404
