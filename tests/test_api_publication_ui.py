"""Publication Inbox/detail, approval and audited actions (TKT-27, RDR-061/062).

Covers the publication read models and the audited lifecycle actions through the
public boundary with a real temporary SQLite database and a Fake publisher:
the Inbox/detail expose link, tracking, revision, external ID and the last
validation; approval is explicit and separate from the Candidate review; an
unknown result stays suspended and routed to a HumanAction; a preview never sends
and the real action depends on the operational gate and revalidation; and
revalidate/expire/cancel operate only through the audited contract.
"""

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
from radar.domain.taxonomy import APPROVED_TAXONOMY
from radar.domain.tracking import build_tracking_label_mapping
from radar.infrastructure.database import create_database_engine
from radar.infrastructure.publication_publisher import FakePublisher
from radar.infrastructure.settings import Settings

pytestmark = pytest.mark.contract

ASSISTED_POLICY: AutomationPolicy = build_automation_policy(
    {"schema_version": "1.0", "policy_version": "assisted", "default_mode": "ASSISTED"}
)
ACTIVE_COMPLIANCE: ChannelCompliancePolicy = build_compliance_policy(
    {"schema_version": "1.0", "policy_version": "active", "status": "ACTIVE"}
)


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
    publisher: Any | None = None,
) -> TestClient:
    engine = create_database_engine(database_url)
    return TestClient(
        create_app(
            settings=Settings(database_url=database_url),
            engine=engine,
            taxonomy=APPROVED_TAXONOMY,
            tracking_labels=_mapping(),
            automation_policy=automation_policy,
            compliance_policy=ACTIVE_COMPLIANCE,
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
            "external_id": "MLB-UI",
            "title": "Perfume",
            "url": "https://www.mercadolivre.com.br/p/MLB-UI",
            "category": "Perfumes",
        },
        "offer": {"current_price": price, "sales_count": 2300, "seller": {"name": "Loja"}},
        "captured_at": captured_at,
    }
    response = client.post("/captures/manual", json=payload)
    assert response.status_code == 201, response.text
    return response.json()["candidate_id"]


def _ready_content(client: TestClient) -> tuple[str, str]:
    candidate_id = _capture(client)
    evaluation = client.post(
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
    assert evaluation.status_code == 201, evaluation.text
    advanced = client.post(
        f"/candidates/{candidate_id}/opportunities", json={"schema_version": "1.0"}
    )
    assert advanced.status_code == 201, advanced.text
    opportunity_id = advanced.json()["opportunity"]["opportunity_id"]
    link = client.post(f"/candidates/{candidate_id}/affiliate-link", json={"schema_version": "1.0"})
    assert link.status_code == 201, link.text
    generated = client.post(
        f"/opportunities/{opportunity_id}/content-generations",
        json={"schema_version": "1.0", "channel": "TELEGRAM"},
    )
    assert generated.status_code == 201, generated.text
    content_generation_id = generated.json()["content_generation_id"]
    for target in ("LINK_READY", "CONTENT_PENDING", "READY_TO_PUBLISH"):
        response = client.post(
            f"/opportunities/{opportunity_id}/transitions",
            json={"schema_version": "1.0", "target_state": target},
        )
        assert response.status_code == 200, response.text
    return opportunity_id, content_generation_id


def _publish(
    client: TestClient,
    opportunity_id: str,
    content_generation_id: str,
    *,
    idempotency_key: str = "ui-1",
    destination_id: str = "dest-tg-sandbox",
    approved: bool = True,
) -> Any:
    return client.post(
        f"/opportunities/{opportunity_id}/publications",
        json={
            "schema_version": "1.0",
            "content_generation_id": content_generation_id,
            "destination_id": destination_id,
            "idempotency_key": idempotency_key,
            "publication_approved": approved,
        },
        headers={"X-Correlation-ID": "cid-pub-ui"},
    )


def test_inbox_and_detail_expose_link_tracking_revision_external_id_and_validation(
    migrated_database_url: str,
) -> None:
    client = _client(migrated_database_url, automation_policy=ASSISTED_POLICY)
    opportunity_id, content_generation_id = _ready_content(client)
    published = _publish(client, opportunity_id, content_generation_id)
    assert published.status_code == 201, published.text
    publication_id = published.json()["publication_id"]

    inbox = client.get("/publications")
    assert inbox.status_code == 200, inbox.text
    body = inbox.json()
    assert body["count"] == 1
    item = body["items"][0]
    assert item["kind"] == "PUBLICATION"
    assert item["publication_id"] == publication_id
    assert item["revision"] == 1
    assert item["external_message_id"] == published.json()["external_message_id"]
    assert item["status"] == "PUBLISHED"
    assert item["product"]["external_id"] == "MLB-UI"
    assert item["product"]["current_price"] == "80.00"
    assert item["last_validation"]["source"] == "CREATION"

    detail = client.get(f"/publications/{publication_id}")
    assert detail.status_code == 200, detail.text
    view = detail.json()["detail"]
    assert view["revision"] == 1
    assert view["external_message_id"] == published.json()["external_message_id"]
    assert view["link"]["affiliate_url"]
    assert view["link"]["tracking_label"] == "rbtgoffer"
    assert view["link"]["tracking_context_id"]
    assert view["link"]["tracking_internal_reference"] == "RADAR_BEAUTY:MERCADO_LIVRE"
    assert view["preview"]["text"]
    assert view["preview"]["affiliate_url"] == view["link"]["affiliate_url"]
    assert view["last_validation"]["source"] == "CREATION"
    assert [
        entry["event_type"] for entry in view["timeline"] if entry["source"] == "publication_event"
    ] == [
        "CREATED",
        "PUBLISHED",
    ]


def test_approval_is_explicit_and_distinct_from_the_candidate_review(
    migrated_database_url: str,
) -> None:
    client = _client(migrated_database_url, automation_policy=ASSISTED_POLICY)
    opportunity_id, content_generation_id = _ready_content(client)
    candidate_id = client.get("/review/inbox").json()["items"][0]["candidate_id"]

    review = client.post(
        f"/candidates/{candidate_id}/human-reviews",
        json={
            "schema_version": "1.0",
            "human_decision": "APPROVE",
            "reason": "boa oferta",
        },
    )
    assert review.status_code == 201, review.text
    assert review.json()["publication_authorized"] is False

    blocked = _publish(client, opportunity_id, content_generation_id, approved=False)
    assert blocked.status_code == 409
    assert blocked.json()["error"]["context"]["reason_code"] == "PUBLICATION_APPROVAL_REQUIRED"
    assert [item["kind"] for item in client.get("/publications").json()["items"]] == ["PREVIEW"]

    approved = _publish(client, opportunity_id, content_generation_id, approved=True)
    assert approved.status_code == 201
    assert [item["kind"] for item in client.get("/publications").json()["items"]] == ["PUBLICATION"]


def test_unknown_result_is_suspended_and_routed_to_a_human_action(
    migrated_database_url: str,
) -> None:
    publisher = FakePublisher(crash_after_accept=True)
    client = _client(migrated_database_url, automation_policy=ASSISTED_POLICY, publisher=publisher)
    opportunity_id, content_generation_id = _ready_content(client)

    response = _publish(client, opportunity_id, content_generation_id)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "RAD-PUB-006"

    item = client.get("/publications").json()["items"][0]
    assert item["status"] == "UNKNOWN"
    detail = client.get(f"/publications/{item['publication_id']}").json()["detail"]
    assert [
        entry["event_type"]
        for entry in detail["timeline"]
        if entry["source"] == "publication_event"
    ] == [
        "CREATED",
        "RESULT_UNKNOWN",
    ]
    assert len(detail["human_actions"]) == 1
    action = detail["human_actions"][0]
    assert action["action_type"] == "REVIEW_PUBLICATION"
    assert action["reason"] == "SEND_RESULT_UNKNOWN"
    assert action["impact"]

    # A second attempt with another key stays blocked by the open suspension.
    retry = _publish(client, opportunity_id, content_generation_id, idempotency_key="ui-2")
    assert retry.status_code == 409
    assert retry.json()["error"]["code"] == "RAD-PUB-006"
    assert publisher.accepted_count() == 1


def test_preview_never_sends_and_the_real_action_respects_the_gate(
    migrated_database_url: str,
) -> None:
    publisher = FakePublisher()
    client = _client(migrated_database_url, automation_policy=ASSISTED_POLICY, publisher=publisher)
    opportunity_id, _content_generation_id = _ready_content(client)

    inbox = client.get("/publications")
    assert inbox.status_code == 200
    items = inbox.json()["items"]
    assert len(items) == 1
    assert items[0]["kind"] == "PREVIEW"
    assert items[0]["publication_id"] is None
    assert items[0]["status"] == "READY"
    assert publisher.accepted_count() == 0

    preview = client.get(f"/publications/preview/{opportunity_id}")
    assert preview.status_code == 200, preview.text
    detail = preview.json()["detail"]
    assert detail["kind"] == "PREVIEW"
    assert detail["publication"] is None
    assert detail["preview"]["text"]
    assert detail["link"]["affiliate_url"]
    assert publisher.accepted_count() == 0

    # The preview disappears once an open publication exists for the Opportunity.
    published = _publish(client, opportunity_id, _content_generation_id)
    assert published.status_code == 201
    remaining = client.get("/publications").json()["items"]
    assert [item["kind"] for item in remaining] == ["PUBLICATION"]


def test_shadow_never_sends_even_for_an_approved_publication(
    migrated_database_url: str,
) -> None:
    publisher = FakePublisher()
    client = _client(migrated_database_url, publisher=publisher)  # default SHADOW
    opportunity_id, content_generation_id = _ready_content(client)

    response = _publish(client, opportunity_id, content_generation_id, approved=True)
    assert response.status_code == 409
    assert response.json()["error"]["context"]["reason_code"] == "SHADOW_NO_COMMERCIAL_SEND"
    assert publisher.accepted_count() == 0
    assert client.get("/publications").json()["count"] == 1  # the preview remains


def test_revalidate_reports_stale_content_and_is_audited(
    migrated_database_url: str,
) -> None:
    client = _client(migrated_database_url, automation_policy=ASSISTED_POLICY)
    opportunity_id, content_generation_id = _ready_content(client)
    published = _publish(client, opportunity_id, content_generation_id)
    publication_id = published.json()["publication_id"]

    allowed = client.post(
        f"/publications/{publication_id}/revalidate", json={"schema_version": "1.0"}
    )
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["revalidation"]["allowed"] is True
    assert allowed.json()["revalidation"]["reason_code"] == "ALLOWED"

    # A new price observation makes the prepared content STALE.
    _capture(client, price="90.00", captured_at="2026-10-06T18:00:00+00:00")

    stale = client.post(
        f"/publications/{publication_id}/revalidate", json={"schema_version": "1.0"}
    )
    assert stale.status_code == 200, stale.text
    assert stale.json()["revalidation"]["allowed"] is False
    assert stale.json()["revalidation"]["reason_code"] == "REVALIDATION_REQUIRED"

    detail = client.get(f"/publications/{publication_id}").json()["detail"]
    assert detail["last_validation"]["source"] == "REVALIDATION"
    assert detail["last_validation"]["allowed"] is False


def test_expire_is_audited_and_idempotent(migrated_database_url: str) -> None:
    client = _client(migrated_database_url, automation_policy=ASSISTED_POLICY)
    opportunity_id, content_generation_id = _ready_content(client)
    publication_id = _publish(client, opportunity_id, content_generation_id).json()[
        "publication_id"
    ]

    first = client.post(f"/publications/{publication_id}/expire", json={"schema_version": "1.0"})
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "EXPIRED"
    events = [event["event_type"] for event in first.json()["publication"]["events"]]
    assert events == ["CREATED", "PUBLISHED", "EXPIRED"]

    replay = client.post(f"/publications/{publication_id}/expire", json={"schema_version": "1.0"})
    assert replay.status_code == 200
    assert [event["event_type"] for event in replay.json()["publication"]["events"]] == events

    timeline = client.get(f"/publications/{publication_id}").json()["detail"]["timeline"]
    assert "PUBLICATION_EXPIRED" in [entry["event_type"] for entry in timeline]


def test_cancel_is_a_soft_audited_action_and_published_is_not_cancelable(
    migrated_database_url: str,
) -> None:
    client = _client(migrated_database_url, automation_policy=ASSISTED_POLICY)
    opportunity_id, content_generation_id = _ready_content(client)
    publication_id = _publish(client, opportunity_id, content_generation_id).json()[
        "publication_id"
    ]

    blocked = client.post(f"/publications/{publication_id}/cancel", json={"schema_version": "1.0"})
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "RAD-PUB-003"
    assert blocked.json()["error"]["context"]["reason_code"] == "ACTION_NOT_APPLICABLE"

    client.post(f"/publications/{publication_id}/expire", json={"schema_version": "1.0"})
    cancelled = client.post(
        f"/publications/{publication_id}/cancel", json={"schema_version": "1.0"}
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "DELETED"
    assert cancelled.json()["publication"]["events"][-1]["event_type"] == "CANCELLED"


def test_expire_and_cancel_never_clear_an_open_unknown_suspension(
    migrated_database_url: str,
) -> None:
    publisher = FakePublisher(crash_after_accept=True)
    client = _client(migrated_database_url, automation_policy=ASSISTED_POLICY, publisher=publisher)
    opportunity_id, content_generation_id = _ready_content(client)
    assert _publish(client, opportunity_id, content_generation_id).status_code == 409
    publication_id = client.get("/publications").json()["items"][0]["publication_id"]

    for action in ("expire", "cancel"):
        response = client.post(
            f"/publications/{publication_id}/{action}", json={"schema_version": "1.0"}
        )
        assert response.status_code == 409, response.text
        assert response.json()["error"]["context"]["reason_code"] == "RESULT_UNKNOWN_OPEN"

    # The suspension is intact and still blocks a new attempt.
    assert (
        client.get(f"/publications/{publication_id}").json()["publication"]["status"] == "UNKNOWN"
    )


def test_action_input_validation_and_missing_publication_errors(
    migrated_database_url: str,
) -> None:
    client = _client(migrated_database_url, automation_policy=ASSISTED_POLICY)

    missing = client.post("/publications/pub_missing/expire", json={"schema_version": "1.0"})
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "RAD-PUB-002"

    invalid = client.post("/publications/pub_missing/expire", json={"schema_version": "2.0"})
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "RAD-PUB-001"
