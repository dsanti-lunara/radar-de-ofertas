from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from radar.api.app import create_app
from radar.domain.operations import (
    OPERATIONS_INPUT_INVALID,
    AutomationMode,
    AutomationPolicy,
    ChannelCompliancePolicy,
    build_automation_policy,
    build_compliance_policy,
)
from radar.domain.taxonomy import APPROVED_TAXONOMY
from radar.infrastructure.database import create_database_engine
from radar.infrastructure.settings import Settings

pytestmark = pytest.mark.contract


def _automation(mode: AutomationMode) -> AutomationPolicy:
    return build_automation_policy(
        {"schema_version": "1.0", "policy_version": "a1", "default_mode": mode.value}
    )


def _compliance(status: str) -> ChannelCompliancePolicy:
    return build_compliance_policy(
        {"schema_version": "1.0", "policy_version": "c1", "status": status}
    )


def _client(
    database_url: str,
    *,
    mode: AutomationMode = AutomationMode.AUTO,
    compliance_status: str = "ACTIVE",
) -> TestClient:
    settings = Settings(database_url=database_url)
    engine = create_database_engine(database_url)
    return TestClient(
        create_app(
            settings=settings,
            engine=engine,
            taxonomy=APPROVED_TAXONOMY,
            automation_policy=_automation(mode),
            compliance_policy=_compliance(compliance_status),
        )
    )


def _authorize(
    client: TestClient,
    action: str,
    **overrides: Any,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"schema_version": "1.0", "action": action}
    payload.update(overrides)
    response = client.post(
        "/operations/authorize", json=payload, headers={"X-Correlation-ID": "cid-auth"}
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_operations_state_is_observable_and_audited(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)

    initial = client.get("/operations")
    assert initial.status_code == 200
    assert initial.json()["state"]["global_mode"] == "RUNNING"
    assert initial.json()["state"]["stop_external_actions"] is False
    assert initial.json()["automation_policy"]["policy_version"] == "a1"
    assert initial.json()["compliance_policy"]["status"] == "ACTIVE"

    changed = client.post(
        "/operations/mode",
        json={"schema_version": "1.0", "mode": "DRAINING", "reason": "upgrade"},
        headers={"X-Correlation-ID": "cid-mode"},
    )
    assert changed.status_code == 200
    assert changed.json()["state"]["global_mode"] == "DRAINING"
    assert changed.json()["correlation_id"] == "cid-mode"

    assert client.get("/operations").json()["state"]["global_mode"] == "DRAINING"


def test_shadow_blocks_publish_even_with_publication_approval(
    migrated_database_url: str,
) -> None:
    client = _client(migrated_database_url, mode=AutomationMode.SHADOW)
    decision = _authorize(client, "PUBLISH", publication_approved=True)
    assert decision["allowed"] is False
    assert decision["reason_code"] == "SHADOW_NO_COMMERCIAL_SEND"


def test_assisted_requires_explicit_publication_approval(
    migrated_database_url: str,
) -> None:
    client = _client(migrated_database_url, mode=AutomationMode.ASSISTED)

    blocked = _authorize(client, "PUBLISH")
    assert blocked["allowed"] is False
    assert blocked["reason_code"] == "PUBLICATION_APPROVAL_REQUIRED"

    allowed = _authorize(client, "PUBLISH", publication_approved=True)
    assert allowed["allowed"] is True
    assert allowed["reason_code"] == "ALLOWED"


def test_stop_external_actions_blocks_side_effects_and_keeps_safe_actions(
    migrated_database_url: str,
) -> None:
    client = _client(migrated_database_url)
    stopped = client.post(
        "/operations/stop-external-actions",
        json={"schema_version": "1.0", "reason": "incident"},
        headers={"X-Correlation-ID": "cid-stop"},
    )
    assert stopped.status_code == 200
    assert stopped.json()["state"]["stop_external_actions"] is True

    for action in ("PUBLISH", "BROWSER", "AUTHENTICATED_LINK"):
        decision = _authorize(client, action, publication_approved=True)
        assert decision["allowed"] is False, action
        assert decision["reason_code"] == "STOP_EXTERNAL_ACTIONS", action

    for action in ("READ", "DIAGNOSTIC", "RECOVERY"):
        decision = _authorize(client, action)
        assert decision["allowed"] is True, action
        assert decision["external"] is False, action

    released = client.request(
        "DELETE",
        "/operations/stop-external-actions",
        json={"schema_version": "1.0", "reason": "resolved"},
        headers={"X-Correlation-ID": "cid-release"},
    )
    assert released.status_code == 200
    assert released.json()["state"]["stop_external_actions"] is False
    assert _authorize(client, "PUBLISH", publication_approved=True)["allowed"] is True


def test_compliance_unknown_blocks_even_with_human_approval(
    migrated_database_url: str,
) -> None:
    client = _client(migrated_database_url, compliance_status="UNKNOWN")
    decision = _authorize(client, "PUBLISH", publication_approved=True)
    assert decision["allowed"] is False
    assert decision["reason_code"] == "POLICY_UNKNOWN"
    assert decision["compliance_status"] == "UNKNOWN"


def test_integration_health_endpoint_isolates_scope(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)

    assert (
        client.put(
            "/integrations/telegram",
            json={"schema_version": "1.0", "state": "OFFLINE", "summary": "down"},
            headers={"X-Correlation-ID": "cid-tg"},
        ).status_code
        == 200
    )
    assert (
        client.put(
            "/integrations/whatsapp",
            json={"schema_version": "1.0", "state": "ONLINE", "summary": "up"},
        ).status_code
        == 200
    )

    listed = client.get("/integrations").json()
    assert listed["count"] == 2
    assert {item["name"] for item in listed["integrations"]} == {"telegram", "whatsapp"}

    telegram = _authorize(client, "PUBLISH", integration="telegram", publication_approved=True)
    assert telegram["allowed"] is False
    assert telegram["reason_code"] == "INTEGRATION_UNAVAILABLE"

    whatsapp = _authorize(client, "PUBLISH", integration="whatsapp", publication_approved=True)
    assert whatsapp["allowed"] is True


def test_invalid_mode_and_action_return_structured_operations_error(
    migrated_database_url: str,
) -> None:
    client = _client(migrated_database_url)

    bad_mode = client.post(
        "/operations/mode",
        json={"schema_version": "1.0", "mode": "TURBO"},
        headers={"X-Correlation-ID": "cid-bad"},
    )
    assert bad_mode.status_code == 422
    assert bad_mode.json()["error"]["code"] == OPERATIONS_INPUT_INVALID

    bad_action = client.post(
        "/operations/authorize",
        json={"schema_version": "1.0", "action": "TURBO"},
        headers={"X-Correlation-ID": "cid-bad"},
    )
    assert bad_action.status_code == 422
    assert bad_action.json()["error"]["code"] == OPERATIONS_INPUT_INVALID


def _capture(client: TestClient) -> str:
    response = client.post(
        "/captures/manual",
        json={
            "schema_version": "1.0",
            "marketplace": "MERCADO_LIVRE",
            "source": "BROWSER_EXTENSION",
            "product": {
                "external_id": "MLB123",
                "title": "Produto",
                "url": "https://www.mercadolivre.com.br/p/MLB123",
                "category": "Perfumes",
            },
            "offer": {"current_price": "100.00", "sales_count": 2300, "seller": {"name": "Loja"}},
            "captured_at": "2026-10-05T12:00:00+00:00",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["candidate_id"]


def test_approved_candidate_pipeline_does_not_authorize_publication(
    migrated_database_url: str,
) -> None:
    """An approved Candidate/Opportunity is not a publication approval (GRILL-001)."""

    client = _client(migrated_database_url, mode=AutomationMode.ASSISTED)
    candidate_id = _capture(client)

    evaluated = client.post(
        f"/candidates/{candidate_id}/evaluations",
        json={
            "schema_version": "1.0",
            "brand": "RADAR_BEAUTY",
            "deal": {"price_opportunity": 100, "seller_quality": 100, "demand": 100},
            "confidence": {
                "source_reliability": 100,
                "freshness": 100,
                "completeness": 100,
                "price_history_depth": 100,
                "cross_validation": 100,
            },
        },
    )
    assert evaluated.status_code == 201, evaluated.text
    assert evaluated.json()["decision"] == "APPROVE"

    advanced = client.post(
        f"/candidates/{candidate_id}/opportunities",
        json={"schema_version": "1.0", "priority": 5},
    )
    assert advanced.status_code == 201, advanced.text
    assert advanced.json()["status"] == "OPPORTUNITY_CREATED"

    # Candidate/Opportunity approval does not authorize a commercial send.
    blocked = _authorize(client, "PUBLISH")
    assert blocked["allowed"] is False
    assert blocked["reason_code"] == "PUBLICATION_APPROVAL_REQUIRED"

    # Only an explicit publication approval unlocks it in ASSISTED.
    allowed = _authorize(client, "PUBLISH", publication_approved=True)
    assert allowed["allowed"] is True
