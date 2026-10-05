from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from radar.domain.capture import (
    CAPTURE_SCHEMA_VERSION,
    CaptureIntake,
    CaptureSource,
    CaptureValidationError,
    Marketplace,
    compute_discount_percent,
    find_sensitive_fields,
    normalize_intake,
    parse_money,
    sanitize_single_line,
    validate_source_url,
)

pytestmark = pytest.mark.unit


def _intake(**overrides: object) -> CaptureIntake:
    data: dict[str, object] = {
        "marketplace": Marketplace.MERCADO_LIVRE,
        "source": CaptureSource.BROWSER_EXTENSION,
        "external_id": "MLB123",
        "current_price": "79.90",
        "original_price": "109.90",
        "title": "Produto",
        "url": "https://www.mercadolivre.com.br/p/MLB123",
    }
    data.update(overrides)
    return CaptureIntake(**data)  # type: ignore[arg-type]


def test_sanitize_single_line_removes_controls_and_collapses_whitespace() -> None:
    assert sanitize_single_line("Cafeteira\n\n  12L\x00 ") == "Cafeteira 12L"


def test_find_sensitive_fields_detects_nested_paths() -> None:
    payload = {
        "product": {"external_id": "X"},
        "offer": {"seller": {"name": "Loja", "token": "abc"}},
        "password": "hunter2",
    }
    hits = find_sensitive_fields(payload)
    assert set(hits) == {"offer.seller.token", "password"}


def test_parse_money_rejects_binary_float() -> None:
    with pytest.raises(CaptureValidationError):
        parse_money(79.9, field_name="current_price")


def test_parse_money_rejects_bool_and_negative() -> None:
    with pytest.raises(CaptureValidationError):
        parse_money(True, field_name="current_price")
    with pytest.raises(CaptureValidationError):
        parse_money("-1", field_name="current_price")


def test_parse_money_accepts_decimal_string() -> None:
    parsed = parse_money("79.90", field_name="current_price")
    assert parsed == Decimal("79.90")
    assert isinstance(parsed, Decimal)


def test_validate_source_url_rejects_dangerous_schemes() -> None:
    for url in ("javascript:alert(1)", "data:text/html,x", "file:///etc/passwd", "not-a-url"):
        with pytest.raises(CaptureValidationError):
            validate_source_url(url)


def test_validate_source_url_rejects_sensitive_query_params() -> None:
    with pytest.raises(CaptureValidationError) as excinfo:
        validate_source_url("https://shopee.com.br/p/1?access_token=abc")
    assert excinfo.value.error.code == "RAD-CAP-002"


def test_normalize_intake_rejects_unsupported_schema_version() -> None:
    with pytest.raises(CaptureValidationError) as excinfo:
        normalize_intake(_intake(schema_version="2.0"))
    assert excinfo.value.error.code == "RAD-CAP-001"


def test_normalize_intake_sanitizes_and_parses_money() -> None:
    normalized = normalize_intake(_intake(title="  Produto\n grande \x00 ", current_price="79.90"))
    assert normalized.schema_version == CAPTURE_SCHEMA_VERSION
    assert normalized.title == "Produto grande"
    assert normalized.current_price == Decimal("79.90")
    assert normalized.original_price == Decimal("109.90")


def test_normalize_intake_requires_positive_current_price() -> None:
    with pytest.raises(CaptureValidationError):
        normalize_intake(_intake(current_price="0"))


def test_compute_discount_percent_is_deterministic_and_not_invented() -> None:
    assert compute_discount_percent(Decimal("79.90"), Decimal("109.90")) == Decimal("27.30")
    assert compute_discount_percent(Decimal("79.90"), None) is None
    assert compute_discount_percent(Decimal("109.90"), Decimal("79.90")) is None


def test_capture_intake_defaults_schema_version() -> None:
    intake = _intake(captured_at=datetime(2026, 10, 5, tzinfo=UTC))
    assert intake.schema_version == CAPTURE_SCHEMA_VERSION
