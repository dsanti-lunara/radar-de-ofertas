"""Unknown send-result suspension and evidence-gated resolution (TKT-24, RDR-128).

Covers ``adr/0001-unknown-publication-result.md`` and GRILL-002 through the public
boundary: a crash after remote acceptance without local confirmation suspends the
publication and opens a HumanAction, never a confirmed failure or an automatic
resend; the suspension survives a restart; a human resolution without sufficient
evidence neither proves failure nor releases a new attempt; and a sustained
resolution still passes through revalidation/guardrails.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from radar.api.app import create_app
from radar.domain.errors import RadarException
from radar.domain.knowledge import Channel
from radar.domain.operations import (
    AutomationPolicy,
    ChannelCompliancePolicy,
    build_automation_policy,
    build_compliance_policy,
)
from radar.domain.publication import (
    PUBLICATION_INPUT_INVALID,
    PUBLICATION_RESOLUTION_BLOCKED,
    PUBLICATION_RESULT_UNKNOWN,
    PublicationStatus,
    build_suspended_publication,
)
from radar.domain.publication_recovery import (
    UnknownResultDecision,
    UnknownResultEvidence,
    UnknownResultEvidenceType,
    build_unknown_result_evidence,
    decide_unknown_result,
    is_evidence_sufficient,
)
from radar.domain.taxonomy import APPROVED_TAXONOMY, Brand
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


def _client(database_url: str, publisher: FakePublisher) -> TestClient:
    engine = create_database_engine(database_url)
    return TestClient(
        create_app(
            settings=Settings(database_url=database_url),
            engine=engine,
            taxonomy=APPROVED_TAXONOMY,
            tracking_labels=_mapping(),
            automation_policy=ASSISTED_POLICY,
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
            "external_id": "MLB-UNKNOWN",
            "title": "Perfume",
            "url": "https://www.mercadolivre.com.br/p/MLB-UNKNOWN",
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
    for target in ("LINK_READY", "CONTENT_PENDING", "READY_TO_PUBLISH"):
        transition = client.post(
            f"/opportunities/{opportunity_id}/transitions",
            json={"schema_version": "1.0", "target_state": target},
        )
        assert transition.status_code == 200, transition.text
    return opportunity_id, generated.json()["content_generation_id"]


def _publish(
    client: TestClient,
    opportunity_id: str,
    content_generation_id: str,
    *,
    idempotency_key: str = "publish:unknown:1",
) -> dict[str, Any]:
    response = client.post(
        f"/opportunities/{opportunity_id}/publications",
        json={
            "schema_version": "1.0",
            "content_generation_id": content_generation_id,
            "destination_id": "dest-tg-sandbox",
            "idempotency_key": idempotency_key,
            "publication_approved": True,
        },
        headers={"X-Correlation-ID": "cid-unknown"},
    )
    return {"status_code": response.status_code, **response.json()}


def _crash(client: TestClient) -> dict[str, Any]:
    opportunity_id, content_generation_id = _ready_content(client)
    return _publish(client, opportunity_id, content_generation_id)


def _audit_event_types(database_url: str, entity_id: str) -> list[str]:
    engine = create_database_engine(database_url)
    try:
        with engine.connect() as connection:
            rows = (
                connection.execute(
                    text(
                        "SELECT event_type FROM audit_event WHERE entity_id = :entity_id "
                        "ORDER BY recorded_at, id"
                    ),
                    {"entity_id": entity_id},
                )
                .scalars()
                .all()
            )
        return [str(row) for row in rows]
    finally:
        engine.dispose()


def test_fake_crash_after_accept_suspends_and_never_resends_after_restart(
    migrated_database_url: str,
) -> None:
    publisher = FakePublisher(crash_after_accept=True)
    client = _client(migrated_database_url, publisher)

    crashed = _crash(client)

    assert crashed["status_code"] == 409
    assert crashed["error"]["code"] == PUBLICATION_RESULT_UNKNOWN
    assert crashed["error"]["retryable"] is False
    assert crashed["error"]["context"]["human_action_id"]
    publication_id = crashed["error"]["context"]["publication_id"]
    assert publisher.accepted_count() == 1

    detail = client.get(f"/publications/{publication_id}")
    assert detail.status_code == 200
    publication = detail.json()["publication"]
    assert publication["status"] == PublicationStatus.UNKNOWN.value
    assert publication["external_message_id"] is None
    assert [event["event_type"] for event in publication["events"]] == [
        "CREATED",
        "RESULT_UNKNOWN",
    ]

    # Restart: a fresh app over the same database must not resend the same key.
    restarted = _client(migrated_database_url, publisher)
    replay = _publish(
        restarted,
        publication["opportunity_id"],
        publication["content_generation_id"],
        idempotency_key=publication["idempotency_key"],
    )

    assert replay["status_code"] == 409
    assert replay["error"]["code"] == PUBLICATION_RESULT_UNKNOWN
    assert publisher.accepted_count() == 1
    assert (
        restarted.get(f"/opportunities/{publication['opportunity_id']}/publications").json()[
            "count"
        ]
        == 1
    )


def test_unknown_result_and_suspension_survive_reboot(migrated_database_url: str) -> None:
    publisher = FakePublisher(crash_after_accept=True)
    client = _client(migrated_database_url, publisher)
    crashed = _crash(client)
    publication_id = crashed["error"]["context"]["publication_id"]
    human_action_id = crashed["error"]["context"]["human_action_id"]

    # A new app instance (reboot) reads the persisted suspension and HumanAction.
    restarted = _client(migrated_database_url, publisher)

    publication = restarted.get(f"/publications/{publication_id}").json()["publication"]
    assert publication["status"] == PublicationStatus.UNKNOWN.value

    action = restarted.get(f"/human-actions/{human_action_id}").json()
    assert action["status"] == "OPEN"
    assert action["action_type"] == "REVIEW_PUBLICATION"
    assert action["reason"] == "SEND_RESULT_UNKNOWN"
    assert action["error_code"] == PUBLICATION_RESULT_UNKNOWN

    open_actions = restarted.get("/human-actions", params={"status": "OPEN"}).json()[
        "human_actions"
    ]
    assert [item["human_action_id"] for item in open_actions] == [human_action_id]


def test_human_action_records_impact_and_required_evidence(
    migrated_database_url: str,
) -> None:
    publisher = FakePublisher(crash_after_accept=True)
    client = _client(migrated_database_url, publisher)
    crashed = _crash(client)
    publication_id = crashed["error"]["context"]["publication_id"]
    human_action_id = crashed["error"]["context"]["human_action_id"]

    action = client.get(f"/human-actions/{human_action_id}").json()
    assert "suspensa" in action["impact"]
    assert "reenvio automático" in action["impact"]
    assert "evidência" in action["next_steps"]

    entity_audits = _audit_event_types(migrated_database_url, publication_id)
    assert "PUBLICATION_RESULT_UNKNOWN" in entity_audits
    action_audits = _audit_event_types(migrated_database_url, human_action_id)
    assert "HUMAN_ACTION_CREATED" in action_audits


def test_resolution_without_evidence_does_not_release_a_new_attempt(
    migrated_database_url: str,
) -> None:
    publisher = FakePublisher(crash_after_accept=True)
    client = _client(migrated_database_url, publisher)
    crashed = _crash(client)
    publication_id = crashed["error"]["context"]["publication_id"]
    opportunity_id = client.get(f"/publications/{publication_id}").json()["publication"][
        "opportunity_id"
    ]

    # Human authorization alone (a note) is not sufficient evidence (ADR 0001).
    blocked = client.post(
        f"/publications/{publication_id}/resolve",
        json={
            "schema_version": "1.0",
            "decision": "CONFIRM_NOT_SENT",
            "evidence": [{"evidence_type": "OPERATOR_NOTE", "reference": "Achei que não foi"}],
        },
    )
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == PUBLICATION_RESOLUTION_BLOCKED
    assert "required_evidence_types" in blocked.json()["error"]["context"]

    still_suspended = client.get(f"/publications/{publication_id}").json()["publication"]
    assert still_suspended["status"] == PublicationStatus.UNKNOWN.value

    # A different idempotency key does not bypass the open suspension.
    new_attempt = client.post(
        f"/opportunities/{opportunity_id}/publications",
        json={
            "schema_version": "1.0",
            "content_generation_id": still_suspended["content_generation_id"],
            "destination_id": "dest-tg-sandbox",
            "idempotency_key": "publish:unknown:new-key",
            "publication_approved": True,
        },
    )
    assert new_attempt.status_code == 409
    assert new_attempt.json()["error"]["code"] == PUBLICATION_RESULT_UNKNOWN
    assert publisher.accepted_count() == 1


def test_sustained_resolution_keeps_revalidation_and_guardrails(
    migrated_database_url: str,
) -> None:
    publisher = FakePublisher(crash_after_accept=True)
    client = _client(migrated_database_url, publisher)
    crashed = _crash(client)
    publication_id = crashed["error"]["context"]["publication_id"]
    publication = client.get(f"/publications/{publication_id}").json()["publication"]
    opportunity_id = publication["opportunity_id"]
    content_generation_id = publication["content_generation_id"]

    resolved = client.post(
        f"/publications/{publication_id}/resolve",
        json={
            "schema_version": "1.0",
            "decision": "CONFIRM_NOT_SENT",
            "evidence": [
                {
                    "evidence_type": "DESTINATION_AUDIT",
                    "reference": "dest-tg-sandbox:sem-mensagem",
                    "source": "operator",
                }
            ],
        },
    )
    assert resolved.status_code == 200, resolved.text
    body = resolved.json()
    assert body["status"] == "RESOLVED"
    assert body["resolution"]["decision"] == "CONFIRM_NOT_SENT"
    assert body["resolution"]["automatic_resend"] is False
    assert body["resolution"]["evidence"][0]["evidence_type"] == "DESTINATION_AUDIT"

    after_resolution = client.get(f"/publications/{publication_id}").json()["publication"]
    assert after_resolution["status"] == PublicationStatus.FAILED.value

    # The offer may expire during review: a new attempt still revalidates content.
    _capture(client, price="99.00", captured_at="2026-10-06T18:00:00+00:00")
    retried = client.post(
        f"/opportunities/{opportunity_id}/publications",
        json={
            "schema_version": "1.0",
            "content_generation_id": content_generation_id,
            "destination_id": "dest-tg-sandbox",
            "idempotency_key": "publish:unknown:retry",
            "publication_approved": True,
        },
    )
    assert retried.status_code == 409
    assert retried.json()["error"]["code"] == "RAD-PUB-003"
    assert retried.json()["error"]["context"]["reason_code"] == "REVALIDATION_REQUIRED"
    assert publisher.accepted_count() == 1


def test_confirm_sent_resolution_records_receipt_and_audit(
    migrated_database_url: str,
) -> None:
    publisher = FakePublisher(crash_after_accept=True)
    client = _client(migrated_database_url, publisher)
    crashed = _crash(client)
    publication_id = crashed["error"]["context"]["publication_id"]

    resolved = client.post(
        f"/publications/{publication_id}/resolve",
        json={
            "schema_version": "1.0",
            "decision": "CONFIRM_SENT",
            "evidence": [
                {
                    "evidence_type": "MESSAGE_MARKER",
                    "reference": "wa-marker-123",
                    "source": "destination",
                }
            ],
        },
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["resolution"]["status"] == PublicationStatus.PUBLISHED.value
    assert resolved.json()["resolution"]["external_message_id"] == "wa-marker-123"

    publication = client.get(f"/publications/{publication_id}").json()["publication"]
    assert publication["status"] == PublicationStatus.PUBLISHED.value
    assert publication["external_message_id"] == "wa-marker-123"
    assert [event["event_type"] for event in publication["events"]][-1] == "RESOLVED"
    assert "PUBLICATION_RESOLVED" in _audit_event_types(migrated_database_url, publication_id)


def test_resolving_a_confirmed_publication_is_blocked(migrated_database_url: str) -> None:
    publisher = FakePublisher()
    client = _client(migrated_database_url, publisher)
    opportunity_id, content_generation_id = _ready_content(client)
    published = _publish(client, opportunity_id, content_generation_id, idempotency_key="ok-1")
    assert published["status_code"] == 201

    response = client.post(
        f"/publications/{published['publication_id']}/resolve",
        json={
            "schema_version": "1.0",
            "decision": "CONFIRM_SENT",
            "evidence": [{"evidence_type": "MESSAGE_MARKER", "reference": "marker-1"}],
        },
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == PUBLICATION_RESOLUTION_BLOCKED


@pytest.mark.unit
def test_evidence_sufficiency_rejects_a_bare_authorization() -> None:
    note = build_unknown_result_evidence(
        evidence_type=UnknownResultEvidenceType.OPERATOR_NOTE,
        reference="não vi a mensagem",
    )
    assert is_evidence_sufficient((note,)) is False

    marker = build_unknown_result_evidence(
        evidence_type=UnknownResultEvidenceType.MESSAGE_MARKER,
        reference="marker-1",
    )
    assert is_evidence_sufficient((note, marker)) is True

    receipt = build_unknown_result_evidence(
        evidence_type=UnknownResultEvidenceType.PROVIDER_RECEIPT,
        reference="receipt-1",
    )
    assert is_evidence_sufficient((receipt,)) is True


@pytest.mark.unit
def test_evidence_rejects_empty_reference_and_unknown_type() -> None:
    with pytest.raises(RadarException) as excinfo:
        build_unknown_result_evidence(
            evidence_type=UnknownResultEvidenceType.DESTINATION_AUDIT, reference="  "
        )
    assert excinfo.value.error.code == PUBLICATION_INPUT_INVALID

    with pytest.raises(RadarException):
        build_unknown_result_evidence(evidence_type="NOT_A_TYPE", reference="x")


@pytest.mark.unit
def test_resolution_evidence_contract_roundtrip() -> None:
    from radar.api.contracts import PublicationResolveContract

    contract = PublicationResolveContract.model_validate(
        {
            "decision": "CONFIRM_NOT_SENT",
            "evidence": [
                {
                    "evidence_type": "DESTINATION_AUDIT",
                    "reference": "dest-1",
                    "source": "operator",
                    "observed_at": datetime(2026, 10, 6, 12, 0, tzinfo=UTC),
                }
            ],
        }
    )
    records = contract.to_evidence()
    assert isinstance(records[0], UnknownResultEvidence)
    assert records[0].evidence_type is UnknownResultEvidenceType.DESTINATION_AUDIT
    assert records[0].reference == "dest-1"

    # The domain decision fails closed without sufficient evidence.
    publication = build_suspended_publication(
        opportunity_id="opp-1",
        content_generation_id="ctg-1",
        affiliate_link_id="lnk-1",
        brand=Brand.RADAR_BEAUTY,
        channel=Channel.TELEGRAM,
        destination_id="dest-1",
        idempotency_key="k",
        published_price="80.00",
        content_hash="hash",
        correlation_id="cid",
        audit_event_id="aud",
        created_at=datetime(2026, 10, 6, 12, 0, tzinfo=UTC),
        publication_id="pub-1",
    )
    with pytest.raises(RadarException):
        decide_unknown_result(
            publication,
            decision=UnknownResultDecision.CONFIRM_NOT_SENT,
            evidence=[
                build_unknown_result_evidence(
                    evidence_type=UnknownResultEvidenceType.OPERATOR_NOTE,
                    reference="note",
                )
            ],
            correlation_id="cid",
            now=datetime(2026, 10, 6, 12, 0, tzinfo=UTC),
        )
