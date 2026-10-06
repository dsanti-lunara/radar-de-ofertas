from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from radar.api.app import create_app
from radar.domain.purchase_source import (
    PURCHASE_SOURCE_SCHEMA_VERSION,
    MaterialDifferenceAction,
    build_purchase_source_policy,
)
from radar.domain.taxonomy import APPROVED_TAXONOMY
from radar.infrastructure.database import create_database_engine
from radar.infrastructure.settings import Settings

pytestmark = pytest.mark.contract


def _client(
    database_url: str,
    *,
    action: MaterialDifferenceAction = MaterialDifferenceAction.REVIEW,
) -> TestClient:
    settings = Settings(database_url=database_url)
    engine = create_database_engine(database_url)
    policy = build_purchase_source_policy(
        {
            "schema_version": "1.0",
            "policy_version": "purchase-source-policy-test",
            "reference_difference_percent": "8",
            "on_material_difference": action.value,
        }
    )
    return TestClient(
        create_app(
            settings=settings,
            engine=engine,
            taxonomy=APPROVED_TAXONOMY,
            purchase_source_policy=policy,
        )
    )


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


def _alternative(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "source_id": "shopee:1",
        "marketplace": "SHOPEE",
        "price": "90",
        "shipping_cost": "0",
        "product_equivalence_id": "product-1",
    }
    data.update(overrides)
    return data


def _decide(
    client: TestClient,
    candidate_id: str,
    *,
    alternatives: list[dict[str, Any]],
    **overrides: Any,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "schema_version": PURCHASE_SOURCE_SCHEMA_VERSION,
        "product_equivalence_id": "product-1",
        "shipping_cost": "0",
        "alternatives": alternatives,
    }
    body.update(overrides)
    response = client.post(
        f"/candidates/{candidate_id}/purchase-source",
        json=body,
        headers={"X-Correlation-ID": "cid-ps"},
    )
    return {"status_code": response.status_code, "headers": response.headers, **response.json()}


def test_material_difference_reviews_and_is_queryable(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    candidate_id = _capture(client)["candidate_id"]

    body = _decide(client, candidate_id, alternatives=[_alternative(price="90")])

    assert body["status_code"] == 201
    assert body["schema_version"] == PURCHASE_SOURCE_SCHEMA_VERSION
    assert body["status"] == "DECIDED"
    assert body["correlation_id"] == "cid-ps"
    assert body["headers"]["x-correlation-id"] == "cid-ps"
    assert body["headers"]["cache-control"] == "no-store"
    # 100 vs 90 is 11.11% > 8%, so the guardrail forces REVIEW.
    assert body["decision"] == "REVIEW"
    assert body["material"] is True
    assert body["chosen_effective_price"] == "100.00"
    assert body["alternative_effective_price"] == "90"
    assert body["best_alternative_source_id"] == "shopee:1"
    assert body["substituted_source_id"] is None
    assert body["commission_considered"] is False
    assert body["reference_difference_percent"] == "8"
    assert body["evidence"]
    assert any(
        warning["code"] == "PURCHASE_SOURCE_MATERIAL_DIFFERENCE" for warning in body["warnings"]
    )

    listing = client.get(f"/candidates/{candidate_id}/purchase-source")
    assert listing.status_code == 200
    listing_body = listing.json()
    assert listing_body["status"] == "OK"
    assert listing_body["count"] == 1
    assert listing_body["decisions"][0]["decision_id"] == body["decision_id"]
    assert listing_body["decisions"][0]["decision"] == "REVIEW"


def test_substitute_policy_replaces_the_source(migrated_database_url: str) -> None:
    client = _client(migrated_database_url, action=MaterialDifferenceAction.SUBSTITUTE)
    candidate_id = _capture(client)["candidate_id"]

    body = _decide(client, candidate_id, alternatives=[_alternative(price="90")])

    assert body["decision"] == "SUBSTITUTE"
    assert body["substituted_source_id"] == "shopee:1"


def test_non_equivalent_product_is_not_a_valid_comparison(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    candidate_id = _capture(client)["candidate_id"]

    body = _decide(
        client,
        candidate_id,
        alternatives=[_alternative(price="10", product_equivalence_id="other-product")],
    )

    assert body["decision"] == "KEEP"
    assert body["difference_percent"] is None
    assert any(warning["code"] == "PURCHASE_SOURCE_NOT_EQUIVALENT" for warning in body["warnings"])


def test_unconfirmed_coupon_is_not_applied(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    candidate_id = _capture(client)["candidate_id"]

    body = _decide(
        client,
        candidate_id,
        alternatives=[_alternative(price="85")],
        coupon_state="LIKELY",
        coupon_amount="50",
    )

    assert body["chosen_effective_price"] == "100.00"
    assert body["decision"] == "REVIEW"


def test_confirmed_coupon_is_applied(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    candidate_id = _capture(client)["candidate_id"]

    body = _decide(
        client,
        candidate_id,
        alternatives=[_alternative(price="90")],
        coupon_state="CONFIRMED",
        coupon_amount="10",
    )

    assert body["chosen_effective_price"] == "90.00"
    assert body["difference_percent"] == "0.0000"
    assert body["decision"] == "KEEP"


def test_unknown_shipping_has_no_reliable_comparison(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    candidate_id = _capture(client)["candidate_id"]

    body = _decide(
        client,
        candidate_id,
        alternatives=[_alternative(price="10")],
        shipping_cost=None,
    )

    assert body["decision"] == "KEEP"
    assert any(
        warning["code"] == "PURCHASE_SOURCE_NO_RELIABLE_COMPARISON" for warning in body["warnings"]
    )


def test_high_commission_never_bypasses_the_guardrail(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    candidate_id = _capture(client)["candidate_id"]

    body = _decide(
        client,
        candidate_id,
        alternatives=[_alternative(price="90")],
        affiliate_commission="100000",
    )

    assert body["decision"] == "REVIEW"
    assert body["commission_considered"] is False
    assert any(
        warning["code"] == "PURCHASE_SOURCE_COMMISSION_IGNORED" for warning in body["warnings"]
    )


def test_candidate_not_found_returns_structured_404(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)

    body = _decide(client, "cand_missing", alternatives=[])
    assert body["status_code"] == 404
    assert body["error"]["code"] == "RAD-CAP-004"

    listing = client.get("/candidates/cand_missing/purchase-source")
    assert listing.status_code == 404
    assert listing.json()["error"]["code"] == "RAD-CAP-004"


def test_invalid_money_returns_structured_422(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    candidate_id = _capture(client)["candidate_id"]

    body = _decide(
        client,
        candidate_id,
        alternatives=[_alternative(price="not-a-number")],
    )

    assert body["status_code"] == 422
    assert body["error"]["code"] == "RAD-CAP-012"
    assert body["error"]["retryable"] is False


def test_sensitive_field_is_rejected(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    candidate_id = _capture(client)["candidate_id"]

    body = _decide(
        client,
        candidate_id,
        alternatives=[_alternative(price="90")],
        access_token="should-never-persist",
    )

    assert body["status_code"] == 422
    assert body["error"]["code"] == "RAD-CAP-002"


def test_correlation_id_is_generated_when_absent(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    candidate_id = _capture(client)["candidate_id"]

    response = client.post(
        f"/candidates/{candidate_id}/purchase-source",
        json={
            "schema_version": PURCHASE_SOURCE_SCHEMA_VERSION,
            "product_equivalence_id": "product-1",
            "shipping_cost": "0",
            "alternatives": [],
        },
    )
    body = response.json()
    assert body["correlation_id"]
    assert response.headers["x-correlation-id"] == body["correlation_id"]
