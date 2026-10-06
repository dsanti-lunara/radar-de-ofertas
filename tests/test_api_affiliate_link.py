from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from radar.api.app import create_app
from radar.domain.taxonomy import APPROVED_TAXONOMY
from radar.domain.tracking import (
    APPROVED_TRACKING_LABEL_MAPPING,
    TrackingLabelMapping,
    build_tracking_label_mapping,
)
from radar.infrastructure.database import create_database_engine
from radar.infrastructure.settings import Settings

pytestmark = pytest.mark.contract


class _CannedProvider:
    name = "stub"

    def __init__(self, response: dict[str, Any]) -> None:
        self._response = response

    def generate(self, request: Any) -> dict[str, Any]:
        return self._response


def _mapping(label: str = "rbtgoffer") -> TrackingLabelMapping:
    return build_tracking_label_mapping(
        {
            "schema_version": "1.0",
            "mapping_version": "tracking-labels-test",
            "entries": [
                {
                    "internal_reference": "RADAR_BEAUTY:MERCADO_LIVRE",
                    "marketplace": "MERCADO_LIVRE",
                    "label": label,
                }
            ],
        }
    )


def _client(
    database_url: str,
    *,
    tracking_labels: TrackingLabelMapping | None = None,
    provider: Any | None = None,
) -> TestClient:
    settings = Settings(database_url=database_url)
    engine = create_database_engine(database_url)
    return TestClient(
        create_app(
            settings=settings,
            engine=engine,
            taxonomy=APPROVED_TAXONOMY,
            tracking_labels=tracking_labels if tracking_labels is not None else _mapping(),
            affiliate_link_provider=provider,
        )
    )


def _capture_payload() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "marketplace": "MERCADO_LIVRE",
        "source": "BROWSER_EXTENSION",
        "product": {
            "external_id": "MLB-LINK",
            "title": "Perfume",
            "url": "https://www.mercadolivre.com.br/p/MLB-LINK",
            "category": "Perfumes",
        },
        "offer": {"current_price": "80.00", "sales_count": 2300, "seller": {"name": "Loja"}},
        "captured_at": "2026-10-06T12:00:00+00:00",
    }


def _capture(client: TestClient) -> str:
    response = client.post("/captures/manual", json=_capture_payload())
    assert response.status_code == 201, response.text
    return response.json()["candidate_id"]


def _evaluate(client: TestClient, candidate_id: str, *, score: int) -> dict[str, Any]:
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
    return response.json()


def _advance(client: TestClient, candidate_id: str) -> dict[str, Any]:
    response = client.post(
        f"/candidates/{candidate_id}/opportunities",
        json={"schema_version": "1.0", "priority": 5},
        headers={"X-Correlation-ID": "cid-adv"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _approved_candidate_with_opportunity(client: TestClient) -> str:
    candidate_id = _capture(client)
    _evaluate(client, candidate_id, score=100)
    _advance(client, candidate_id)
    return candidate_id


def _generate(client: TestClient, candidate_id: str, **body: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"schema_version": "1.0"}
    payload.update(body)
    response = client.post(
        f"/candidates/{candidate_id}/affiliate-link",
        json=payload,
        headers={"X-Correlation-ID": "cid-link"},
    )
    return {"status_code": response.status_code, "headers": response.headers, **response.json()}


def test_fake_link_is_generated_and_queryable_via_public_boundary(
    migrated_database_url: str,
) -> None:
    client = _client(migrated_database_url)
    candidate_id = _approved_candidate_with_opportunity(client)

    body = _generate(client, candidate_id)

    assert body["status_code"] == 201
    assert body["schema_version"] == "1.0"
    assert body["status"] == "VALIDATED"
    assert body["generation_method"] == "FAKE"
    assert body["productive"] is False
    assert body["original_url"] == "https://www.mercadolivre.com.br/p/MLB-LINK"
    assert "MLB-LINK" in body["affiliate_url"]
    assert body["tracking"]["external_label"] == "rbtgoffer"
    assert body["tracking"]["internal_reference"] == "RADAR_BEAUTY:MERCADO_LIVRE"
    assert body["tracking"]["tracking_context_id"]
    assert body["tracking"]["configured"] is True
    assert body["correlation_id"] == "cid-link"
    assert body["headers"]["x-correlation-id"] == "cid-link"
    assert body["headers"]["cache-control"] == "no-store"

    listing = client.get(f"/candidates/{candidate_id}/affiliate-links")
    assert listing.status_code == 200
    assert listing.json()["count"] == 1
    assert listing.json()["affiliate_links"][0]["affiliate_link_id"] == body["affiliate_link_id"]

    detail = client.get(f"/affiliate-links/{body['affiliate_link_id']}")
    assert detail.status_code == 200
    assert detail.json()["affiliate_link"]["productive"] is False


def test_candidate_not_approved_does_not_generate_a_link(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    candidate_id = _capture(client)
    _evaluate(client, candidate_id, score=0)

    body = _generate(client, candidate_id)

    assert body["status_code"] == 409
    assert body["error"]["code"] == "RAD-LINK-007"
    assert client.get(f"/candidates/{candidate_id}/affiliate-links").json()["count"] == 0


def test_wrong_product_and_invalid_host_are_rejected(migrated_database_url: str) -> None:
    wrong_product = _CannedProvider(
        {
            "affiliate_url": "https://www.mercadolivre.com.br/social/x?matt_word=rbtgoffer",
            "source": "ML_LINK_GENERATOR",
            "product_reference": "MLB-OTHER",
        }
    )
    client = _client(migrated_database_url, provider=wrong_product)
    candidate_id = _approved_candidate_with_opportunity(client)

    body = _generate(client, candidate_id)

    assert body["status_code"] == 422
    assert body["error"]["code"] == "RAD-LINK-003"
    assert client.get(f"/candidates/{candidate_id}/affiliate-links").json()["count"] == 0

    invalid_host = _CannedProvider(
        {
            "affiliate_url": "https://evil.example.com/x/MLB-LINK?matt_word=rbtgoffer",
            "source": "ML_LINK_GENERATOR",
            "product_reference": "MLB-LINK",
        }
    )
    client = _client(migrated_database_url, provider=invalid_host)
    candidate_id = _approved_candidate_with_opportunity(client)

    body = _generate(client, candidate_id)

    assert body["status_code"] == 422
    assert body["error"]["code"] == "RAD-LINK-003"


def test_unmapped_label_blocks_without_writing(migrated_database_url: str) -> None:
    client = _client(migrated_database_url, tracking_labels=APPROVED_TRACKING_LABEL_MAPPING)
    candidate_id = _approved_candidate_with_opportunity(client)

    body = _generate(client, candidate_id)

    assert body["status_code"] == 409
    assert body["error"]["code"] == "RAD-LINK-005"
    assert client.get(f"/candidates/{candidate_id}/affiliate-links").json()["count"] == 0


def test_generation_is_idempotent_via_the_public_boundary(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    candidate_id = _approved_candidate_with_opportunity(client)

    first = _generate(client, candidate_id)
    second = _generate(client, candidate_id)

    assert first["affiliate_link_id"] == second["affiliate_link_id"]
    assert client.get(f"/candidates/{candidate_id}/affiliate-links").json()["count"] == 1


def test_candidate_not_found_and_without_evaluation_fail_closed(
    migrated_database_url: str,
) -> None:
    client = _client(migrated_database_url)

    missing = _generate(client, "cand_missing")
    assert missing["status_code"] == 404
    assert missing["error"]["code"] == "RAD-CAP-004"

    candidate_id = _capture(client)
    no_evaluation = _generate(client, candidate_id)
    assert no_evaluation["status_code"] == 404
    assert no_evaluation["error"]["code"] == "RAD-CAP-013"


def test_invalid_schema_version_and_sensitive_field_return_422(
    migrated_database_url: str,
) -> None:
    client = _client(migrated_database_url)
    candidate_id = _approved_candidate_with_opportunity(client)

    invalid_schema = _generate(client, candidate_id, schema_version="2.0")
    assert invalid_schema["status_code"] == 422
    assert invalid_schema["error"]["code"] == "RAD-LINK-001"

    sensitive = _generate(client, candidate_id, token="abc")
    assert sensitive["status_code"] == 422
    assert sensitive["error"]["code"] == "RAD-LINK-001"


def test_missing_link_returns_structured_404(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)

    response = client.get("/affiliate-links/lnk_missing")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RAD-LINK-002"


def test_correlation_id_is_generated_when_absent(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    candidate_id = _approved_candidate_with_opportunity(client)

    response = client.post(
        f"/candidates/{candidate_id}/affiliate-link",
        json={"schema_version": "1.0"},
    )
    body = response.json()

    assert body["correlation_id"]
    assert response.headers["x-correlation-id"] == body["correlation_id"]
    assert response.headers["cache-control"] == "no-store"
