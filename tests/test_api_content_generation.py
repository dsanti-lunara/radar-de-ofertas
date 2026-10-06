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


class _CannedContentProvider:
    name = "stub"

    def __init__(self, response: dict[str, Any]) -> None:
        self._response = response

    def generate_content(self, request: Any) -> dict[str, Any]:
        return self._response


class _CountingContentProvider:
    name = "counting"

    def __init__(self, response: dict[str, Any]) -> None:
        self._response = response
        self.calls = 0

    def generate_content(self, request: Any) -> dict[str, Any]:
        self.calls += 1
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
            content_provider=provider,
        )
    )


def _capture_payload(*, captured_at: str = "2026-10-06T12:00:00+00:00") -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "marketplace": "MERCADO_LIVRE",
        "source": "BROWSER_EXTENSION",
        "product": {
            "external_id": "MLB-CT",
            "title": "Perfume",
            "url": "https://www.mercadolivre.com.br/p/MLB-CT",
            "category": "Perfumes",
        },
        "offer": {"current_price": "80.00", "sales_count": 2300, "seller": {"name": "Loja"}},
        "captured_at": captured_at,
    }


def _capture(client: TestClient, *, price: str = "80.00", captured_at: str | None = None) -> str:
    payload = _capture_payload(captured_at=captured_at or "2026-10-06T12:00:00+00:00")
    payload["offer"]["current_price"] = price
    response = client.post("/captures/manual", json=payload)
    assert response.status_code == 201, response.text
    return response.json()["candidate_id"]


def _evaluate(client: TestClient, candidate_id: str, *, score: int) -> None:
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


def _ready_opportunity(client: TestClient) -> str:
    candidate_id = _capture(client)
    _evaluate(client, candidate_id, score=100)
    advanced = client.post(
        f"/candidates/{candidate_id}/opportunities",
        json={"schema_version": "1.0", "priority": 5},
        headers={"X-Correlation-ID": "cid-adv"},
    )
    assert advanced.status_code == 201, advanced.text
    link = client.post(
        f"/candidates/{candidate_id}/affiliate-link",
        json={"schema_version": "1.0"},
        headers={"X-Correlation-ID": "cid-link"},
    )
    assert link.status_code == 201, link.text
    return advanced.json()["opportunity"]["opportunity_id"]


def _generate(client: TestClient, opportunity_id: str, **body: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"schema_version": "1.0", "channel": "TELEGRAM"}
    payload.update(body)
    response = client.post(
        f"/opportunities/{opportunity_id}/content-generations",
        json=payload,
        headers={"X-Correlation-ID": "cid-ctg"},
    )
    return {"status_code": response.status_code, "headers": response.headers, **response.json()}


def test_validated_preview_is_queryable_via_the_public_boundary(
    migrated_database_url: str,
) -> None:
    client = _client(migrated_database_url)
    opportunity_id = _ready_opportunity(client)

    body = _generate(client, opportunity_id)

    assert body["status_code"] == 201
    assert body["schema_version"] == "1.0"
    assert body["status"] == "VALIDATED"
    assert body["publishable"] is True
    assert body["stale"] is False
    assert body["generated_content"]["headline"]
    assert body["generated_content"]["body"] != body["final_content"]["text"]
    assert body["final_content"]["price"] == "80.00"
    assert body["final_content"]["affiliate_url"].endswith("matt_word=rbtgoffer")
    assert body["final_content"]["disclosure"] in body["final_content"]["text"]
    assert body["renderer_version"] == "renderer-1.0"
    assert body["correlation_id"] == "cid-ctg"
    assert body["headers"]["x-correlation-id"] == "cid-ctg"
    assert body["headers"]["cache-control"] == "no-store"

    listing = client.get(f"/opportunities/{opportunity_id}/content-generations")
    assert listing.status_code == 200
    assert listing.json()["count"] == 1
    assert (
        listing.json()["content_generations"][0]["content_generation_id"]
        == body["content_generation_id"]
    )

    detail = client.get(f"/content-generations/{body['content_generation_id']}")
    assert detail.status_code == 200
    assert detail.json()["content_generation"]["status"] == "VALIDATED"


def test_unsupported_number_blocks_publishable_preview(migrated_database_url: str) -> None:
    provider = _CannedContentProvider(
        {
            "headline": "Oferta",
            "body": "Preço especial de R$ 999,00!",
            "cta": "Compre",
            "warnings": [],
        }
    )
    client = _client(migrated_database_url, provider=provider)
    opportunity_id = _ready_opportunity(client)

    body = _generate(client, opportunity_id)

    assert body["status_code"] == 422
    assert body["error"]["code"] == "RAD-AI-005"
    assert client.get(f"/opportunities/{opportunity_id}/content-generations").json()["count"] == 0


def test_unsupported_claim_blocks_publishable_preview(migrated_database_url: str) -> None:
    provider = _CannedContentProvider(
        {
            "headline": "Melhor preço da internet",
            "body": "Aproveite agora.",
            "cta": "Compre",
            "warnings": [],
        }
    )
    client = _client(migrated_database_url, provider=provider)
    opportunity_id = _ready_opportunity(client)

    body = _generate(client, opportunity_id)

    assert body["status_code"] == 422
    assert body["error"]["code"] == "RAD-AI-006"
    assert client.get(f"/opportunities/{opportunity_id}/content-generations").json()["count"] == 0


def test_ai_invented_url_is_rejected(migrated_database_url: str) -> None:
    provider = _CannedContentProvider(
        {
            "headline": "Oferta",
            "body": "Compre em https://evil.example.com/MLB-CT",
            "cta": "Compre",
            "warnings": [],
        }
    )
    client = _client(migrated_database_url, provider=provider)
    opportunity_id = _ready_opportunity(client)

    body = _generate(client, opportunity_id)

    assert body["status_code"] == 422
    assert body["error"]["code"] == "RAD-AI-013"


def test_content_becomes_stale_when_a_relevant_fact_changes(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    opportunity_id = _ready_opportunity(client)
    generated = _generate(client, opportunity_id)
    assert generated["status"] == "VALIDATED"

    _capture(client, price="90.00", captured_at="2026-10-06T18:00:00+00:00")

    detail = client.get(f"/content-generations/{generated['content_generation_id']}")
    assert detail.status_code == 200
    contract = detail.json()["content_generation"]
    assert contract["status"] == "STALE"
    assert contract["publishable"] is False
    assert contract["stale"] is True


def test_unmapped_tracking_label_blocks_content_generation(
    migrated_database_url: str,
) -> None:
    client = _client(migrated_database_url, tracking_labels=APPROVED_TRACKING_LABEL_MAPPING)
    candidate_id = _capture(client)
    _evaluate(client, candidate_id, score=100)
    advanced = client.post(
        f"/candidates/{candidate_id}/opportunities",
        json={"schema_version": "1.0"},
        headers={"X-Correlation-ID": "cid-adv"},
    )
    opportunity_id = advanced.json()["opportunity"]["opportunity_id"]
    link = client.post(
        f"/candidates/{candidate_id}/affiliate-link",
        json={"schema_version": "1.0"},
    )
    assert link.status_code == 409

    body = _generate(client, opportunity_id)

    assert body["status_code"] == 422
    assert body["error"]["code"] == "RAD-AI-012"


def test_invalid_channel_schema_and_sensitive_field_return_422(
    migrated_database_url: str,
) -> None:
    client = _client(migrated_database_url)
    opportunity_id = _ready_opportunity(client)

    invalid_channel = _generate(client, opportunity_id, channel="INVALID")
    assert invalid_channel["status_code"] == 422
    assert invalid_channel["error"]["code"] == "RAD-AI-012"

    invalid_schema = _generate(client, opportunity_id, schema_version="2.0")
    assert invalid_schema["status_code"] == 422
    assert invalid_schema["error"]["code"] == "RAD-AI-012"

    sensitive = _generate(client, opportunity_id, token="abc")
    assert sensitive["status_code"] == 422
    assert sensitive["error"]["code"] == "RAD-AI-012"


def test_missing_content_returns_structured_404(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)

    response = client.get("/content-generations/ctg_missing")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RAD-AI-011"


def test_correlation_id_is_generated_when_absent(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    opportunity_id = _ready_opportunity(client)

    response = client.post(
        f"/opportunities/{opportunity_id}/content-generations",
        json={"schema_version": "1.0", "channel": "TELEGRAM"},
    )
    body = response.json()

    assert body["correlation_id"]
    assert response.headers["x-correlation-id"] == body["correlation_id"]
    assert response.headers["cache-control"] == "no-store"


def test_equivalent_request_reuses_generation_without_calling_provider_again(
    migrated_database_url: str,
) -> None:
    provider = _CountingContentProvider(
        {"headline": "Oferta", "body": "Oferta selecionada.", "cta": "Compre", "warnings": []}
    )
    client = _client(migrated_database_url, provider=provider)
    opportunity_id = _ready_opportunity(client)

    first = _generate(client, opportunity_id)
    second = _generate(client, opportunity_id)

    assert first["status_code"] == 201
    assert first["cache_hit"] is False
    assert first["status"] == "VALIDATED"
    assert first["publishable"] is True
    assert first["ai_input_hash"]
    assert second["status_code"] == 201
    assert second["cache_hit"] is True
    assert second["content_generation_id"] == first["content_generation_id"]
    assert second["ai_input_hash"] == first["ai_input_hash"]
    assert second["publishable"] is True

    # The provider is called once: the second request reused the persisted result.
    assert provider.calls == 1
    listing = client.get(f"/opportunities/{opportunity_id}/content-generations")
    assert listing.json()["count"] == 1


def test_price_change_regenerates_via_the_public_boundary(migrated_database_url: str) -> None:
    provider = _CountingContentProvider(
        {"headline": "Oferta", "body": "Oferta selecionada.", "cta": "Compre", "warnings": []}
    )
    client = _client(migrated_database_url, provider=provider)
    opportunity_id = _ready_opportunity(client)

    first = _generate(client, opportunity_id)
    _capture(client, price="90.00", captured_at="2026-10-06T18:00:00+00:00")
    second = _generate(client, opportunity_id)

    assert first["cache_hit"] is False
    assert second["cache_hit"] is False
    assert second["content_generation_id"] != first["content_generation_id"]
    # The new price observation makes the first generation stale, so the request
    # cannot reuse it and the provider is called again.
    detail = client.get(f"/content-generations/{first['content_generation_id']}")
    assert detail.json()["content_generation"]["status"] == "STALE"
    assert provider.calls == 2
    assert client.get(f"/opportunities/{opportunity_id}/content-generations").json()["count"] == 2


def test_invalid_provider_output_is_never_cached_via_the_public_boundary(
    migrated_database_url: str,
) -> None:
    provider = _CountingContentProvider(
        {
            "headline": "Oferta",
            "body": "Preço especial de R$ 999,00!",
            "cta": "Compre",
            "warnings": [],
        }
    )
    client = _client(migrated_database_url, provider=provider)
    opportunity_id = _ready_opportunity(client)

    for _ in range(2):
        body = _generate(client, opportunity_id)
        assert body["status_code"] == 422
        assert body["error"]["code"] == "RAD-AI-005"

    assert provider.calls == 2
    assert client.get(f"/opportunities/{opportunity_id}/content-generations").json()["count"] == 0
