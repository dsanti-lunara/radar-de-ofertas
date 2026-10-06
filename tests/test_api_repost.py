from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from radar.api.app import create_app
from radar.domain.repost import REPOST_SCHEMA_VERSION
from radar.domain.taxonomy import APPROVED_TAXONOMY
from radar.infrastructure.database import create_database_engine
from radar.infrastructure.settings import Settings

pytestmark = pytest.mark.contract


def _client(database_url: str) -> TestClient:
    settings = Settings(database_url=database_url)
    engine = create_database_engine(database_url)
    return TestClient(create_app(settings=settings, engine=engine, taxonomy=APPROVED_TAXONOMY))


def _capture(client: TestClient, **overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
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
    }
    payload.update(overrides)
    response = client.post("/captures/manual", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _components(score: int) -> dict[str, int]:
    return {"price_opportunity": score, "seller_quality": score, "demand": score}


def _evaluate(client: TestClient, candidate_id: str, *, score: int) -> None:
    response = client.post(
        f"/candidates/{candidate_id}/evaluations",
        json={
            "schema_version": "1.0",
            "brand": "RADAR_BEAUTY",
            "deal": _components(score),
        },
    )
    assert response.status_code == 201, response.text


def _published(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "publication_id": "pub-1",
        "published_at": (datetime.now(UTC) - timedelta(hours=10)).isoformat(),
        "price": "100.00",
        "coupon_state": "NOT_APPLICABLE",
    }
    data.update(overrides)
    return data


def _repost(client: TestClient, candidate_id: str, **overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "schema_version": REPOST_SCHEMA_VERSION,
        "publications": [_published()],
    }
    body.update(overrides)
    response = client.post(
        f"/candidates/{candidate_id}/repost",
        json=body,
        headers={"X-Correlation-ID": "cid-repost"},
    )
    return {"status_code": response.status_code, "headers": response.headers, **response.json()}


def test_first_publication_is_allowed_and_queryable(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    candidate_id = _capture(client)["candidate_id"]

    body = _repost(client, candidate_id, publications=[])

    assert body["status_code"] == 201
    assert body["schema_version"] == REPOST_SCHEMA_VERSION
    assert body["status"] == "DECIDED"
    assert body["correlation_id"] == "cid-repost"
    assert body["headers"]["x-correlation-id"] == "cid-repost"
    assert body["headers"]["cache-control"] == "no-store"
    assert body["decision"] == "ALLOWED"
    assert body["reason"] == "FIRST_PUBLICATION"
    assert body["allowed"] is True
    assert body["evidence"]

    listing = client.get(f"/candidates/{candidate_id}/repost")
    assert listing.status_code == 200
    listing_body = listing.json()
    assert listing_body["count"] == 1
    assert listing_body["decisions"][0]["decision_id"] == body["decision_id"]


def test_irrelevant_change_with_active_cooldown_blocks_repost(
    migrated_database_url: str,
) -> None:
    client = _client(migrated_database_url)
    candidate_id = _capture(client)["candidate_id"]
    _evaluate(client, candidate_id, score=100)

    body = _repost(client, candidate_id, publications=[_published(price="100.00")])

    assert body["decision"] == "BLOCKED"
    assert body["reason"] == "DUPLICATE_WITHOUT_SIGNIFICANT_CHANGE"
    assert body["cooldown_expired"] is False
    assert any(
        warning["code"] == "DUPLICATE_WITHOUT_SIGNIFICANT_CHANGE" for warning in body["warnings"]
    )


def test_price_drop_at_ten_percent_releases_repost(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    candidate_id = _capture(client, offer={"current_price": "90.00", "seller": {"name": "Loja"}})[
        "candidate_id"
    ]
    _evaluate(client, candidate_id, score=50)

    body = _repost(client, candidate_id, publications=[_published(price="100.00")])

    assert body["decision"] == "ALLOWED"
    assert body["reason"] == "MATERIAL_PRICE_DROP"
    assert body["observed_price_drop_percent"] == "10.00"
    assert body["cooldown_hours"] == 72


def test_expired_cooldown_requires_strong_deal(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    expired = _published(
        published_at=(datetime.now(UTC) - timedelta(hours=80)).isoformat(), price="100.00"
    )

    weak_candidate = _capture(client)["candidate_id"]
    _evaluate(client, weak_candidate, score=70)
    weak = _repost(client, weak_candidate, publications=[expired])
    assert weak["decision"] == "BLOCKED"
    assert weak["reason"] == "DEAL_NOT_STRONG"

    strong_candidate = _capture(
        client,
        product={
            "external_id": "MLB999",
            "title": "Produto 2",
            "url": "https://www.mercadolivre.com.br/p/MLB999",
            "category": "Perfumes",
        },
    )["candidate_id"]
    _evaluate(client, strong_candidate, score=100)
    strong = _repost(client, strong_candidate, publications=[expired])
    assert strong["decision"] == "ALLOWED"
    assert strong["reason"] == "COOLDOWN_EXPIRED_STRONG_DEAL"


def test_material_coupon_requires_evidence(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    candidate_id = _capture(client)["candidate_id"]
    _evaluate(client, candidate_id, score=50)

    without = _repost(
        client,
        candidate_id,
        publications=[_published(price="100.00", coupon_state="NOT_APPLICABLE")],
        coupon_state="CONFIRMED",
        coupon_amount="10",
        coupon_code="SAVE10",
    )
    assert without["decision"] == "BLOCKED"
    assert any(
        warning["code"] == "REPOST_COUPON_WITHOUT_EVIDENCE" for warning in without["warnings"]
    )

    with_evidence = _repost(
        client,
        candidate_id,
        publications=[_published(price="100.00", coupon_state="NOT_APPLICABLE")],
        coupon_state="CONFIRMED",
        coupon_amount="10",
        coupon_code="SAVE10",
        evidence=[
            {
                "evidence_type": "COUPON",
                "reference_id": "rc-1",
                "field": "coupon",
                "value": "SAVE10",
            }
        ],
    )
    assert with_evidence["decision"] == "ALLOWED"
    assert with_evidence["reason"] == "MATERIAL_COUPON"


def test_candidate_not_found_returns_structured_404(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)

    body = _repost(client, "cand_missing")
    assert body["status_code"] == 404
    assert body["error"]["code"] == "RAD-CAP-004"

    listing = client.get("/candidates/cand_missing/repost")
    assert listing.status_code == 404
    assert listing.json()["error"]["code"] == "RAD-CAP-004"


def test_invalid_money_returns_structured_422(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    candidate_id = _capture(client)["candidate_id"]

    body = _repost(client, candidate_id, publications=[_published(price="not-a-number")])

    assert body["status_code"] == 422
    assert body["error"]["code"] == "RAD-CAP-015"
    assert body["error"]["retryable"] is False


def test_sensitive_field_is_rejected(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    candidate_id = _capture(client)["candidate_id"]

    body = _repost(client, candidate_id, access_token="should-never-persist")

    assert body["status_code"] == 422
    assert body["error"]["code"] == "RAD-CAP-002"


def test_correlation_id_is_generated_when_absent(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    candidate_id = _capture(client)["candidate_id"]

    response = client.post(
        f"/candidates/{candidate_id}/repost",
        json={"schema_version": REPOST_SCHEMA_VERSION, "publications": []},
    )
    body = response.json()
    assert body["correlation_id"]
    assert response.headers["x-correlation-id"] == body["correlation_id"]
