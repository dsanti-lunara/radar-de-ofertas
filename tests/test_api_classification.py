from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine

from radar.api.app import create_app
from radar.domain.taxonomy import (
    APPROVED_TAXONOMY,
    HARD_RULE_OUT_OF_SCOPE_CATEGORY,
    WARNING_BRAND_FIT_CALIBRATION_REQUIRED,
    WARNING_CATEGORY_MAPPING_NOT_DEFINED,
    WARNING_CATEGORY_NOT_PROVIDED,
)
from radar.infrastructure.database import create_database_engine
from radar.infrastructure.settings import Settings

pytestmark = pytest.mark.contract


def _client(database_url: str) -> TestClient:
    settings = Settings(database_url=database_url)
    engine = create_database_engine(database_url)
    return TestClient(create_app(settings=settings, engine=engine, taxonomy=APPROVED_TAXONOMY))


def _payload(**overrides: Any) -> dict[str, Any]:
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
        "offer": {
            "current_price": "79.90",
            "original_price": "109.90",
            "sales_count": 2300,
            "seller": {"name": "Loja"},
        },
        "captured_at": "2026-10-05T12:00:00+00:00",
    }
    payload.update(overrides)
    return payload


def _capture(client: TestClient, **overrides: Any) -> dict[str, Any]:
    response = client.post("/captures/manual", json=_payload(**overrides))
    assert response.status_code == 201, response.text
    return response.json()


def _classify(client: TestClient, candidate_id: str, brand: str, **params: str) -> dict[str, Any]:
    response = client.get(
        f"/candidates/{candidate_id}/classification/{brand}",
        params=params,
        headers={"X-Correlation-ID": "cid-classify"},
    )
    return {"status_code": response.status_code, "headers": response.headers, **response.json()}


@pytest.mark.parametrize(
    ("category", "canonical", "priority", "brand_fit"),
    [
        ("Perfumes", "perfume", 1, 100),
        ("Body Splash", "body_splash", 1, 100),
        ("Cabelo", "hair", 2, 85),
        ("Skincare", "skincare", 2, 85),
        ("Maquiagem", "makeup", 3, 65),
        ("Acessórios", "accessories", 3, 60),
    ],
)
def test_radar_beauty_brand_fit_uses_approved_values(
    migrated_database_url: str,
    category: str,
    canonical: str,
    priority: int,
    brand_fit: int,
) -> None:
    client = _client(migrated_database_url)
    captured = _capture(client, product={**_payload()["product"], "category": category})
    body = _classify(client, captured["candidate_id"], "RADAR_BEAUTY")

    assert body["status_code"] == 200
    assert body["schema_version"] == "1.0"
    assert body["status"] == "CLASSIFIED"
    assert body["correlation_id"] == "cid-classify"
    assert body["brand"] == "RADAR_BEAUTY"
    assert body["category"] == canonical
    assert body["priority"] == priority
    assert body["brand_fit"] == brand_fit
    assert body["calibrated"] is True
    assert body["calibration_required"] is False
    assert body["warnings"] == []
    assert body["hard_rules"] == []
    assert body["taxonomy_version"] == APPROVED_TAXONOMY.taxonomy_version
    assert body["taxonomy_hash"] == APPROVED_TAXONOMY.content_hash


def test_casa_em_ordem_priorities_respect_scope_and_report_calibration_gap(
    migrated_database_url: str,
) -> None:
    client = _client(migrated_database_url)
    captured = _capture(client, product={**_payload()["product"], "category": "Cozinha"})
    body = _classify(client, captured["candidate_id"], "CASA_EM_ORDEM")

    assert body["status_code"] == 200
    assert body["category"] == "kitchen"
    assert body["priority"] == 1
    assert body["brand_fit"] is None
    assert body["calibrated"] is False
    assert body["calibration_required"] is True
    assert body["hard_rules"] == []
    assert [warning["code"] for warning in body["warnings"]] == [
        WARNING_BRAND_FIT_CALIBRATION_REQUIRED
    ]


def test_out_of_scope_category_emits_hard_rule(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    captured = _capture(client, product={**_payload()["product"], "category": "Perfumes"})
    body = _classify(client, captured["candidate_id"], "CASA_EM_ORDEM")

    assert body["status_code"] == 200
    assert body["category"] == "perfume"
    assert body["brand_fit"] is None
    assert [rule["rule"] for rule in body["hard_rules"]] == [HARD_RULE_OUT_OF_SCOPE_CATEGORY]
    assert body["hard_rules"][0]["context"] == {"brand": "CASA_EM_ORDEM", "category": "perfume"}


def test_undefined_mapping_is_explicit_gap(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    captured = _capture(client, product={**_payload()["product"], "category": "Categoria Estranha"})
    body = _classify(client, captured["candidate_id"], "RADAR_BEAUTY")

    assert body["status_code"] == 200
    assert body["category"] is None
    assert body["priority"] is None
    assert body["brand_fit"] is None
    assert body["calibrated"] is False
    assert body["hard_rules"] == []
    assert [warning["code"] for warning in body["warnings"]] == [
        WARNING_CATEGORY_MAPPING_NOT_DEFINED
    ]


def test_missing_category_is_explicit_gap(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    product = dict(_payload()["product"])
    product.pop("category")
    captured = _capture(client, product=product)
    body = _classify(client, captured["candidate_id"], "RADAR_BEAUTY")

    assert body["status_code"] == 200
    assert body["raw_category"] is None
    assert body["category"] is None
    assert [warning["code"] for warning in body["warnings"]] == [WARNING_CATEGORY_NOT_PROVIDED]


def test_capture_persists_raw_category(migrated_database_url: str, migrated_engine: Engine) -> None:
    client = _client(migrated_database_url)
    _capture(client, product={**_payload()["product"], "category": "Perfumes"})

    with migrated_engine.connect() as connection:
        stored = connection.exec_driver_sql("SELECT raw_category FROM marketplace_product").scalar()
    assert stored == "Perfumes"


def test_repeated_capture_updates_raw_category_without_duplicating_identity(
    migrated_database_url: str, migrated_engine: Engine
) -> None:
    client = _client(migrated_database_url)
    first = _capture(client, product={**_payload()["product"], "category": "Perfumes"})
    second = _capture(client, product={**_payload()["product"], "category": "Cabelo"})

    assert second["marketplace_product_id"] == first["marketplace_product_id"]
    with migrated_engine.connect() as connection:
        stored = connection.exec_driver_sql("SELECT raw_category FROM marketplace_product").scalar()
    assert stored == "Cabelo"
    body = _classify(client, second["candidate_id"], "RADAR_BEAUTY")
    assert body["category"] == "hair"


def test_unknown_brand_returns_structured_error(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    captured = _capture(client)
    body = _classify(client, captured["candidate_id"], "ACME")

    assert body["status_code"] == 422
    assert body["error"]["code"] == "RAD-CAP-006"
    assert body["error"]["retryable"] is False


def test_taxonomy_version_mismatch_returns_structured_error(
    migrated_database_url: str,
) -> None:
    client = _client(migrated_database_url)
    captured = _capture(client)
    body = _classify(
        client,
        captured["candidate_id"],
        "RADAR_BEAUTY",
        taxonomy_version="brand-taxonomy-0.0",
    )

    assert body["status_code"] == 422
    assert body["error"]["code"] == "RAD-CAP-007"
    assert body["error"]["context"]["requested"] == "brand-taxonomy-0.0"
    assert body["error"]["context"]["active"] == APPROVED_TAXONOMY.taxonomy_version


def test_candidate_not_found_returns_structured_404(migrated_database_url: str) -> None:
    client = _client(migrated_database_url)
    body = _classify(client, "cand_missing", "RADAR_BEAUTY")

    assert body["status_code"] == 404
    assert body["error"]["code"] == "RAD-CAP-004"
    assert body["headers"]["x-correlation-id"] == body["correlation_id"]


def test_classification_correlation_id_is_generated_when_absent(
    migrated_database_url: str,
) -> None:
    client = _client(migrated_database_url)
    captured = _capture(client)
    response = client.get(f"/candidates/{captured['candidate_id']}/classification/RADAR_BEAUTY")
    body = response.json()
    assert body["correlation_id"]
    assert response.headers["x-correlation-id"] == body["correlation_id"]
    assert response.headers["cache-control"] == "no-store"
