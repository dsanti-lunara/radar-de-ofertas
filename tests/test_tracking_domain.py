from __future__ import annotations

import pytest

from radar.domain.capture import Marketplace
from radar.domain.taxonomy import Brand
from radar.domain.tracking import (
    APPROVED_TRACKING_LABEL_MAPPING,
    TRACKING_LABEL_INVALID,
    TRACKING_LABELS_INVALID,
    TRACKING_MAPPING_NOT_CONFIGURED,
    TrackingError,
    build_tracking_context,
    build_tracking_label_mapping,
    validate_tracking_label,
)

pytestmark = pytest.mark.unit


def _mapping(*entries: dict[str, str]) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "mapping_version": "tracking-labels-test",
        "entries": list(entries),
    }


def _entry(reference: str, label: str, marketplace: str = "MERCADO_LIVRE") -> dict[str, str]:
    return {"internal_reference": reference, "marketplace": marketplace, "label": label}


def test_tracking_label_accepts_only_lowercase_alnum_up_to_30() -> None:
    assert validate_tracking_label("rbtgoffer") == "rbtgoffer"
    assert validate_tracking_label("a") == "a"
    assert validate_tracking_label("a" * 30) == "a" * 30
    assert validate_tracking_label("abc123") == "abc123"


def test_invalid_labels_fail_closed_without_silent_normalization() -> None:
    for invalid in ("RB_TG_OFFER", "rb-tg", "RB TG", "rb.tg", "", "a" * 31, "ábc", "RB"):
        with pytest.raises(TrackingError) as excinfo:
            validate_tracking_label(invalid)
        assert excinfo.value.error.code == TRACKING_LABEL_INVALID
        # The value is never lowercased, separator-stripped or truncated.
        assert excinfo.value.error.context.get("pattern") == "^[a-z0-9]{1,30}$"
    assert validate_tracking_label("a" * 30) != "a" * 31


def test_mapping_rejects_duplicate_reference_and_duplicate_label() -> None:
    with pytest.raises(TrackingError) as duplicate_reference:
        build_tracking_label_mapping(
            _mapping(_entry("A:ML", "labelone"), _entry("A:ML", "labeltwo"))
        )
    assert duplicate_reference.value.error.code == TRACKING_LABELS_INVALID

    with pytest.raises(TrackingError) as duplicate_label:
        build_tracking_label_mapping(_mapping(_entry("A:ML", "shared"), _entry("B:ML", "shared")))
    assert duplicate_label.value.error.code == TRACKING_LABELS_INVALID

    # The same label may be reused across different marketplaces.
    mapping = build_tracking_label_mapping(
        _mapping(_entry("A:ML", "shared"), _entry("A:SP", "shared", "SHOPEE"))
    )
    assert len(mapping.entries) == 2


def test_mapping_rejects_invalid_label_and_unknown_fields() -> None:
    with pytest.raises(TrackingError) as invalid_label:
        build_tracking_label_mapping(_mapping(_entry("A:ML", "NOT_lower")))
    assert invalid_label.value.error.code == TRACKING_LABEL_INVALID

    with pytest.raises(TrackingError) as unknown:
        build_tracking_label_mapping(
            {
                "schema_version": "1.0",
                "mapping_version": "v1",
                "entries": [],
                "extra": "no",
            }
        )
    assert unknown.value.error.code == TRACKING_LABELS_INVALID


def test_mapping_resolves_association_and_hashes_itself() -> None:
    mapping = build_tracking_label_mapping(
        _mapping(_entry("RADAR_BEAUTY:MERCADO_LIVRE", "rbtgoffer"))
    )
    entry = mapping.resolve("RADAR_BEAUTY:MERCADO_LIVRE", Marketplace.MERCADO_LIVRE)

    assert entry is not None
    assert entry.label == "rbtgoffer"
    assert mapping.content_hash
    assert mapping.mapping_version == "tracking-labels-test"
    # A reference from another marketplace does not resolve.
    assert mapping.resolve("RADAR_BEAUTY:MERCADO_LIVRE", Marketplace.SHOPEE) is None
    assert mapping.resolve("UNKNOWN", Marketplace.MERCADO_LIVRE) is None


def test_baseline_mapping_is_empty_and_context_is_an_explicit_gap() -> None:
    assert APPROVED_TRACKING_LABEL_MAPPING.entries == {}

    context = build_tracking_context(
        opportunity_id="opp_1",
        marketplace=Marketplace.MERCADO_LIVRE,
        brand=Brand.RADAR_BEAUTY,
        internal_reference="RADAR_BEAUTY:MERCADO_LIVRE",
        mapping=APPROVED_TRACKING_LABEL_MAPPING,
    )

    assert context.configured is False
    assert context.external_label is None
    assert context.warning_code == "TRACKING_MAPPING_NOT_CONFIGURED"


def test_tracking_context_points_to_the_internal_reference() -> None:
    mapping = build_tracking_label_mapping(
        _mapping(_entry("RADAR_BEAUTY:MERCADO_LIVRE", "rbtgoffer"))
    )
    context = build_tracking_context(
        opportunity_id="opp_1",
        marketplace=Marketplace.MERCADO_LIVRE,
        brand=Brand.RADAR_BEAUTY,
        internal_reference="RADAR_BEAUTY:MERCADO_LIVRE",
        mapping=mapping,
    )

    contract = context.to_contract()
    assert context.configured is True
    assert context.external_label == "rbtgoffer"
    assert contract["tracking_context_id"]
    assert contract["internal_reference"] == "RADAR_BEAUTY:MERCADO_LIVRE"
    assert contract["mapping_version"] == "tracking-labels-test"
    assert contract["mapping_hash"] == mapping.content_hash
    assert context.warning_code is None


def test_mapping_not_configured_error_is_structured() -> None:
    from radar.domain.tracking import tracking_mapping_not_configured_error

    error = tracking_mapping_not_configured_error(
        internal_reference="RADAR_BEAUTY:MERCADO_LIVRE", marketplace=Marketplace.MERCADO_LIVRE
    )
    assert error.error.code == TRACKING_MAPPING_NOT_CONFIGURED
    assert error.error.retryable is False
    assert error.error.context["internal_reference"] == "RADAR_BEAUTY:MERCADO_LIVRE"
