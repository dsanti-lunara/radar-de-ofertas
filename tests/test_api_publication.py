from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from radar.api.app import create_app
from radar.domain.operations import (
    AutomationPolicy,
    ChannelCompliancePolicy,
    build_automation_policy,
    build_compliance_policy,
)
from radar.domain.publication import (
    PUBLICATION_SCHEMA_VERSION,
    PublicationPolicy,
    build_publication_policy,
)
from radar.domain.taxonomy import APPROVED_TAXONOMY
from radar.domain.tracking import build_tracking_label_mapping
from radar.infrastructure.database import create_database_engine
from radar.infrastructure.settings import Settings

pytestmark = pytest.mark.contract

ASSISTED_POLICY: AutomationPolicy = build_automation_policy(
    {"schema_version": "1.0", "policy_version": "assisted", "default_mode": "ASSISTED"}
)
ACTIVE_COMPLIANCE: ChannelCompliancePolicy = build_compliance_policy(
    {"schema_version": "1.0", "policy_version": "active", "status": "ACTIVE"}
)


class _CountingPublisher:
    name = "counting"

    def __init__(self) -> None:
        self.calls = 0

    def send(self, request: Any) -> dict[str, Any]:
        self.calls += 1
        return {"external_message_id": f"stub-{request.publication_id}"}


class _FailingPublisher:
    name = "failing"

    def send(self, request: Any) -> dict[str, Any]:
        raise RuntimeError("publisher exploded")


def _mapping() -> Any:
    return build_tracking_label_mapping(
        {
            "schema_version": "1.0",
            "mapping_version": "tracking-labels-test",
            "entries": [
                {
                    "internal_reference": "RADAR_BEAUTY:MERCADO_LIVRE",
                    "marketplace": "MERCADO_LIVRE",
                    "label": "rbtgoffer",
                }
            ],
        }
    )


def _client(
    database_url: str,
    *,
    automation_policy: AutomationPolicy | None = None,
    compliance_policy: ChannelCompliancePolicy | None = None,
    publication_policy: PublicationPolicy | None = None,
    publisher: Any | None = None,
) -> TestClient:
    settings = Settings(database_url=database_url)
    engine = create_database_engine(database_url)
    return TestClient(
        create_app(
            settings=settings,
            engine=engine,
            taxonomy=APPROVED_TAXONOMY,
            tracking_labels=_mapping(),
            automation_policy=automation_policy,
            compliance_policy=compliance_policy,
            publication_policy=publication_policy,
            publisher=publisher,
        )
    )


def _capture(
    client: TestClient,
    *,
    price: str = "80.00",
    captured_at: str = "2026-10-06T12:00:00+00:00",
) -> str:
    payload = {
        "schema_version": "1.0",
        "marketplace": "MERCADO_LIVRE",
        "source": "BROWSER_EXTENSION",
        "product": {
            "external_id": "MLB-PUB",
            "title": "Perfume",
            "url": "https://www.mercadolivre.com.br/p/MLB-PUB",
            "category": "Perfumes",
        },
        "offer": {"current_price": price, "sales_count": 2300, "seller": {"name": "Loja"}},
        "captured_at": captured_at,
    }
    response = client.post("/captures/manual", json=payload)
    assert response.status_code == 201, response.text
    return response.json()["candidate_id"]


def _evaluate(client: TestClient, candidate_id: str, *, score: int = 100) -> None:
    response = client.post(
        f"/candidates/{candidate_id}/evaluations",
        json={
            "schema_version": "1.0",
            "brand": "RADAR_BEAUTY",
            "deal": {"price_opportunity": score, "seller_quality": score, "demand": score},
            "confidence": {
                "source_reliability": score,
                "freshness": score,
                "completeness": score,
                "price_history_depth": score,
                "cross_validation": score,
            },
        },
        headers={"X-Correlation-ID": "cid-eval"},
    )
    assert response.status_code == 201, response.text


def _transition(client: TestClient, opportunity_id: str, target: str) -> None:
    response = client.post(
        f"/opportunities/{opportunity_id}/transitions",
        json={"schema_version": "1.0", "target_state": target},
        headers={"X-Correlation-ID": "cid-transition"},
    )
    assert response.status_code == 200, response.text


def _ready_content(client: TestClient) -> tuple[str, str]:
    """Build the full pipeline up to a READY_TO_PUBLISH Opportunity + preview."""

    candidate_id = _capture(client)
    _evaluate(client, candidate_id)
    advanced = client.post(
        f"/candidates/{candidate_id}/opportunities",
        json={"schema_version": "1.0", "priority": 5},
        headers={"X-Correlation-ID": "cid-adv"},
    )
    assert advanced.status_code == 201, advanced.text
    opportunity_id = advanced.json()["opportunity"]["opportunity_id"]
    link = client.post(
        f"/candidates/{candidate_id}/affiliate-link",
        json={"schema_version": "1.0"},
        headers={"X-Correlation-ID": "cid-link"},
    )
    assert link.status_code == 201, link.text
    generated = client.post(
        f"/opportunities/{opportunity_id}/content-generations",
        json={"schema_version": "1.0", "channel": "TELEGRAM"},
        headers={"X-Correlation-ID": "cid-ctg"},
    )
    assert generated.status_code == 201, generated.text
    content_generation_id = generated.json()["content_generation_id"]
    _transition(client, opportunity_id, "LINK_READY")
    _transition(client, opportunity_id, "CONTENT_PENDING")
    _transition(client, opportunity_id, "READY_TO_PUBLISH")
    return opportunity_id, content_generation_id


def _publish(
    client: TestClient,
    opportunity_id: str,
    content_generation_id: str,
    *,
    idempotency_key: str = "publish:radar_beauty:telegram:opp:1",
    destination_id: str = "dest-tg-sandbox",
    approved: bool = True,
) -> dict[str, Any]:
    response = client.post(
        f"/opportunities/{opportunity_id}/publications",
        json={
            "schema_version": "1.0",
            "content_generation_id": content_generation_id,
            "destination_id": destination_id,
            "idempotency_key": idempotency_key,
            "publication_approved": approved,
        },
        headers={"X-Correlation-ID": "cid-pub"},
    )
    return {"status_code": response.status_code, "headers": response.headers, **response.json()}


def test_pipeline_persists_publication_and_correlation_without_real_send(
    migrated_database_url: str,
) -> None:
    client = _client(
        migrated_database_url,
        automation_policy=ASSISTED_POLICY,
        compliance_policy=ACTIVE_COMPLIANCE,
    )
    opportunity_id, content_generation_id = _ready_content(client)

    body = _publish(client, opportunity_id, content_generation_id)

    assert body["status_code"] == 201, body
    assert body["schema_version"] == PUBLICATION_SCHEMA_VERSION
    assert body["status"] == "PUBLISHED"
    assert body["idempotent_replay"] is False
    assert body["correlation_id"] == "cid-pub"
    assert body["headers"]["x-correlation-id"] == "cid-pub"
    assert body["headers"]["cache-control"] == "no-store"
    assert body["publication_id"]
    assert body["external_message_id"]
    assert body["published_price"] == "80.00"
    assert body["destination_id"] == "dest-tg-sandbox"
    assert [event["event_type"] for event in body["events"]] == ["CREATED", "PUBLISHED"]

    listing = client.get(f"/opportunities/{opportunity_id}/publications")
    assert listing.status_code == 200
    assert listing.json()["count"] == 1

    detail = client.get(f"/publications/{body['publication_id']}")
    assert detail.status_code == 200
    assert detail.json()["publication"]["external_message_id"] == body["external_message_id"]


def test_publication_is_distinct_from_content_generation_and_opportunity(
    migrated_database_url: str,
) -> None:
    client = _client(
        migrated_database_url,
        automation_policy=ASSISTED_POLICY,
        compliance_policy=ACTIVE_COMPLIANCE,
    )
    opportunity_id, content_generation_id = _ready_content(client)

    body = _publish(client, opportunity_id, content_generation_id)

    assert body["publication_id"] != content_generation_id
    assert body["publication_id"] != opportunity_id
    assert body["content_generation_id"] == content_generation_id
    assert body["opportunity_id"] == opportunity_id
    # The referenced entities remain independently queryable.
    assert client.get(f"/opportunities/{opportunity_id}").status_code == 200
    assert client.get(f"/content-generations/{content_generation_id}").status_code == 200


def test_repeating_idempotency_key_does_not_duplicate_a_confirmed_send(
    migrated_database_url: str,
) -> None:
    publisher = _CountingPublisher()
    client = _client(
        migrated_database_url,
        automation_policy=ASSISTED_POLICY,
        compliance_policy=ACTIVE_COMPLIANCE,
        publisher=publisher,
    )
    opportunity_id, content_generation_id = _ready_content(client)

    first = _publish(client, opportunity_id, content_generation_id, idempotency_key="key-1")
    second = _publish(client, opportunity_id, content_generation_id, idempotency_key="key-1")

    assert first["status_code"] == 201
    assert second["status_code"] == 200
    assert second["idempotent_replay"] is True
    assert second["publication_id"] == first["publication_id"]
    assert second["external_message_id"] == first["external_message_id"]
    assert publisher.calls == 1
    assert client.get(f"/opportunities/{opportunity_id}/publications").json()["count"] == 1


def test_shadow_is_zero_commercial_send_even_with_approval(migrated_database_url: str) -> None:
    publisher = _CountingPublisher()
    # Default automation policy is SHADOW; the compliance policy is ACTIVE so the
    # block is unambiguously the automation mode.
    client = _client(
        migrated_database_url,
        compliance_policy=ACTIVE_COMPLIANCE,
        publisher=publisher,
    )
    opportunity_id, content_generation_id = _ready_content(client)

    body = _publish(client, opportunity_id, content_generation_id, approved=True)

    assert body["status_code"] == 409
    assert body["error"]["code"] == "RAD-PUB-003"
    assert body["error"]["context"]["reason_code"] == "SHADOW_NO_COMMERCIAL_SEND"
    assert publisher.calls == 0
    assert client.get(f"/opportunities/{opportunity_id}/publications").json()["count"] == 0


def test_assisted_requires_explicit_approval_and_then_exercises_fake(
    migrated_database_url: str,
) -> None:
    publisher = _CountingPublisher()
    client = _client(
        migrated_database_url,
        automation_policy=ASSISTED_POLICY,
        compliance_policy=ACTIVE_COMPLIANCE,
        publisher=publisher,
    )
    opportunity_id, content_generation_id = _ready_content(client)

    blocked = _publish(client, opportunity_id, content_generation_id, approved=False)

    assert blocked["status_code"] == 409
    assert blocked["error"]["context"]["reason_code"] == "PUBLICATION_APPROVAL_REQUIRED"
    assert publisher.calls == 0

    allowed = _publish(client, opportunity_id, content_generation_id, approved=True)

    assert allowed["status_code"] == 201
    assert allowed["status"] == "PUBLISHED"
    assert publisher.calls == 1


def test_stale_content_requires_revalidation_before_the_publisher(
    migrated_database_url: str,
) -> None:
    publisher = _CountingPublisher()
    client = _client(
        migrated_database_url,
        automation_policy=ASSISTED_POLICY,
        compliance_policy=ACTIVE_COMPLIANCE,
        publisher=publisher,
    )
    opportunity_id, content_generation_id = _ready_content(client)

    # A new price observation makes the prepared content STALE.
    _capture(client, price="90.00", captured_at="2026-10-06T18:00:00+00:00")

    body = _publish(client, opportunity_id, content_generation_id)

    assert body["status_code"] == 409
    assert body["error"]["context"]["reason_code"] == "REVALIDATION_REQUIRED"
    assert publisher.calls == 0
    assert client.get(f"/opportunities/{opportunity_id}/publications").json()["count"] == 0


def test_burst_blocks_before_the_publisher(migrated_database_url: str) -> None:
    publisher = _CountingPublisher()
    client = _client(
        migrated_database_url,
        automation_policy=ASSISTED_POLICY,
        compliance_policy=ACTIVE_COMPLIANCE,
        publication_policy=build_publication_policy(
            {"policy_version": "burst-1", "burst_limit": 1}
        ),
        publisher=publisher,
    )
    opportunity_id, content_generation_id = _ready_content(client)

    first = _publish(client, opportunity_id, content_generation_id, idempotency_key="b1")
    second = _publish(client, opportunity_id, content_generation_id, idempotency_key="b2")

    assert first["status_code"] == 201
    assert second["status_code"] == 409
    assert second["error"]["context"]["reason_code"] == "BURST_LIMIT"
    assert publisher.calls == 1
    assert client.get(f"/opportunities/{opportunity_id}/publications").json()["count"] == 1


def test_hard_cap_blocks_before_the_publisher(migrated_database_url: str) -> None:
    publisher = _CountingPublisher()
    client = _client(
        migrated_database_url,
        automation_policy=ASSISTED_POLICY,
        compliance_policy=ACTIVE_COMPLIANCE,
        publication_policy=build_publication_policy(
            {"policy_version": "cap-1", "hard_cap_per_day": 1, "burst_limit": 5}
        ),
        publisher=publisher,
    )
    opportunity_id, content_generation_id = _ready_content(client)

    first = _publish(client, opportunity_id, content_generation_id, idempotency_key="c1")
    capped = _publish(client, opportunity_id, content_generation_id, idempotency_key="c2")

    assert first["status_code"] == 201
    assert capped["status_code"] == 409
    assert capped["error"]["context"]["reason_code"] == "HARD_CAP_REACHED"
    assert publisher.calls == 1


def test_cooldown_blocks_before_the_publisher(migrated_database_url: str) -> None:
    publisher = _CountingPublisher()
    client = _client(
        migrated_database_url,
        automation_policy=ASSISTED_POLICY,
        compliance_policy=ACTIVE_COMPLIANCE,
        publication_policy=build_publication_policy(
            {"policy_version": "cooldown-1", "burst_limit": 5, "cooldown_minutes": 60}
        ),
        publisher=publisher,
    )
    opportunity_id, content_generation_id = _ready_content(client)

    first = _publish(client, opportunity_id, content_generation_id, idempotency_key="d1")
    second = _publish(client, opportunity_id, content_generation_id, idempotency_key="d2")

    assert first["status_code"] == 201
    assert second["status_code"] == 409
    assert second["error"]["context"]["reason_code"] == "COOLDOWN_ACTIVE"
    assert publisher.calls == 1


def test_publisher_failure_fails_closed_without_persisting(migrated_database_url: str) -> None:
    client = _client(
        migrated_database_url,
        automation_policy=ASSISTED_POLICY,
        compliance_policy=ACTIVE_COMPLIANCE,
        publisher=_FailingPublisher(),
    )
    opportunity_id, content_generation_id = _ready_content(client)

    body = _publish(client, opportunity_id, content_generation_id)

    assert body["status_code"] == 503
    assert body["error"]["code"] == "RAD-PUB-004"
    assert body["error"]["retryable"] is True
    assert client.get(f"/opportunities/{opportunity_id}/publications").json()["count"] == 0


def test_missing_publication_returns_structured_404(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)

    response = client.get("/publications/pub_missing")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RAD-PUB-002"


def test_invalid_publication_input_returns_structured_422(migrated_database_url: str) -> None:
    client = _client(
        migrated_database_url,
        automation_policy=ASSISTED_POLICY,
        compliance_policy=ACTIVE_COMPLIANCE,
    )
    opportunity_id, content_generation_id = _ready_content(client)

    invalid_schema = _publish(client, opportunity_id, content_generation_id)
    assert invalid_schema["status_code"] == 201

    response = client.post(
        f"/opportunities/{opportunity_id}/publications",
        json={
            "schema_version": "2.0",
            "content_generation_id": content_generation_id,
            "destination_id": "dest",
            "idempotency_key": "k",
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "RAD-PUB-001"


def test_correlation_id_is_generated_when_absent(migrated_database_url: str) -> None:
    client = _client(
        migrated_database_url,
        automation_policy=ASSISTED_POLICY,
        compliance_policy=ACTIVE_COMPLIANCE,
    )
    opportunity_id, content_generation_id = _ready_content(client)

    response = client.post(
        f"/opportunities/{opportunity_id}/publications",
        json={
            "schema_version": "1.0",
            "content_generation_id": content_generation_id,
            "destination_id": "dest-tg-sandbox",
            "idempotency_key": "corr-1",
            "publication_approved": True,
        },
    )
    body = response.json()

    assert response.status_code == 201
    assert body["correlation_id"]
    assert response.headers["x-correlation-id"] == body["correlation_id"]
    assert response.headers["cache-control"] == "no-store"
