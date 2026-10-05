from __future__ import annotations

import pytest

from radar.domain.demand import (
    APPROVED_DEMAND_NORMALIZATION,
    DEMAND_NORMALIZATION_INVALID,
    REASON_INVALID_DATA,
    REASON_MISSING_DATA,
    REASON_NORMALIZATION_NOT_DEFINED,
    WARNING_CATEGORY_NOT_DEFINED,
    WARNING_INVALID_DATA,
    WARNING_MISSING_DATA,
    WARNING_NORMALIZATION_NOT_DEFINED,
    DemandFacts,
    DemandNormalizationInvalidError,
    DemandSignal,
    DemandSignalName,
    build_demand_normalization,
    compute_demand,
)

pytestmark = pytest.mark.unit

_COMPONENTS = {
    DemandSignalName.SALES_COUNT,
    DemandSignalName.RATING_COUNT,
    DemandSignalName.TREND,
    DemandSignalName.AFFILIATE_PORTAL,
    DemandSignalName.BADGES,
}


def _normalization():
    return build_demand_normalization(
        {
            "schema_version": "1.0",
            "normalization_version": "demand-normalization-test",
            "categories": {
                "perfume": {
                    "weights": {
                        "sales_count": 40,
                        "rating_count": 20,
                        "trend": 20,
                        "affiliate_portal": 10,
                        "badges": 10,
                    },
                    "sales_count": [
                        {"min": 1000, "max": None, "score": 100},
                        {"min": 100, "max": 999, "score": 70},
                        {"min": 0, "max": 99, "score": 40},
                    ],
                    "rating_count": [
                        {"min": 500, "max": None, "score": 100},
                        {"min": 0, "max": 499, "score": 50},
                    ],
                    "trend": {"rising": 100, "stable": 60, "falling": 20},
                    "affiliate_portal": {"featured": 100, "listed": 60},
                    "badges": {"best seller": 100, "free shipping": 70},
                }
            },
        }
    )


def _result(
    *,
    category: str | None = "perfume",
    raw_category: str | None = "Perfumes",
    sales_count: int | None = None,
    rating_count: int | None = None,
    trend: str | None = None,
    affiliate_portal: str | None = None,
    badges: tuple[str, ...] | None = None,
    normalization=None,
):
    return compute_demand(
        candidate_id="cand_1",
        facts=DemandFacts(
            raw_category=raw_category,
            category=category,
            sales_count=(
                None
                if sales_count is None
                else DemandSignal(value=sales_count, source="persisted_offer")
            ),
            rating_count=(
                None
                if rating_count is None
                else DemandSignal(value=rating_count, source="evaluation_input")
            ),
            trend=(None if trend is None else DemandSignal(value=trend, source="evaluation_input")),
            affiliate_portal=(
                None
                if affiliate_portal is None
                else DemandSignal(value=affiliate_portal, source="evaluation_input")
            ),
            badges=(
                None if badges is None else DemandSignal(value=badges, source="evaluation_input")
            ),
        ),
        normalization=normalization or _normalization(),
    )


def _score(result, name: DemandSignalName) -> int | None:
    return result.component(name).score


def _codes(result) -> list[str]:
    return [warning.code for warning in result.warnings]


# --- Breakdown and provenance (acceptance criterion 1) ----------------------


def test_breakdown_covers_all_approved_signals() -> None:
    result = _result()
    assert {component.name for component in result.components} == _COMPONENTS
    assert len(result.components) == 5


def test_composition_uses_configured_category_weights() -> None:
    result = _result(
        sales_count=2000,
        rating_count=600,
        trend="rising",
        affiliate_portal="featured",
        badges=("best seller",),
    )
    # Every signal scores 100 -> weighted 100 over covered weight 100.
    assert _score(result, DemandSignalName.SALES_COUNT) == 100
    assert _score(result, DemandSignalName.RATING_COUNT) == 100
    assert _score(result, DemandSignalName.TREND) == 100
    assert _score(result, DemandSignalName.AFFILIATE_PORTAL) == 100
    assert _score(result, DemandSignalName.BADGES) == 100
    assert result.demand == 100
    assert result.weight_covered == 100
    assert result.fully_calibrated is True


def test_composition_is_deterministic_and_category_weighted() -> None:
    first = _result(sales_count=500, trend="stable")
    second = _result(sales_count=500, trend="stable")
    assert first.to_contract() == second.to_contract()
    # sales_count 500 -> 70*40; trend stable -> 60*20 => 4000/60 = 66.67 -> 67
    assert first.demand == 67
    assert first.weight_covered == 60


def test_labels_are_case_and_separator_insensitive() -> None:
    for label in ("Rising", " rising ", "RISING"):
        result = _result(trend=label)
        assert _score(result, DemandSignalName.TREND) == 100


def test_badges_use_the_strongest_recognized_badge() -> None:
    result = _result(badges=("free shipping", "best seller"))
    assert _score(result, DemandSignalName.BADGES) == 100
    assert result.component(DemandSignalName.BADGES).calibrated is True


def test_component_contract_reports_signal_origin_and_raw() -> None:
    result = _result(sales_count=2000, trend="rising", badges=("best seller",))
    sales = result.component(DemandSignalName.SALES_COUNT)
    trend = result.component(DemandSignalName.TREND)
    badges = result.component(DemandSignalName.BADGES)
    assert sales.source == "persisted_offer"
    assert sales.raw == 2000
    assert trend.source == "evaluation_input"
    assert trend.raw == "rising"
    assert badges.source == "evaluation_input"
    assert badges.raw == ("best seller",)
    contract = result.to_contract()
    serialized = next(item for item in contract["components"] if item["name"] == "badges")
    assert serialized["raw"] == ["best seller"]


# --- Missing data never becomes zero (acceptance criterion 3) ----------------


def test_missing_signals_are_none_and_never_zero() -> None:
    result = _result()
    for component in result.components:
        assert component.score is None
        assert component.score != 0
        assert component.calibrated is False
        assert component.reason == REASON_MISSING_DATA
    assert result.demand is None
    assert result.demand != 0
    assert result.weight_covered == 0
    assert result.fully_calibrated is False
    assert _codes(result) == [WARNING_MISSING_DATA] * 5


def test_empty_badges_do_not_become_zero() -> None:
    result = _result(badges=())
    badges = result.component(DemandSignalName.BADGES)
    assert badges.score is None
    assert badges.reason == REASON_MISSING_DATA
    assert WARNING_MISSING_DATA in _codes(result)


def test_partial_aggregate_uses_only_calibrated_components() -> None:
    result = _result(trend="stable")
    assert _score(result, DemandSignalName.TREND) == 60
    assert result.demand == 60
    assert result.weight_covered == 20
    assert result.fully_calibrated is False
    assert _score(result, DemandSignalName.SALES_COUNT) is None
    assert WARNING_MISSING_DATA in _codes(result)


# --- Versioned category normalization (acceptance criterion 2) --------------


def test_normalization_is_versioned_and_hashed() -> None:
    normalization = _normalization()
    assert normalization.normalization_version == "demand-normalization-test"
    assert len(normalization.content_hash) == 64
    result = _result(normalization=normalization)
    assert result.normalization_version == normalization.normalization_version
    assert result.normalization_hash == normalization.content_hash


def test_hash_is_stable_and_changes_with_content() -> None:
    first = _normalization()
    second = _normalization()
    assert first.content_hash == second.content_hash
    changed = build_demand_normalization(
        {
            "schema_version": "1.0",
            "normalization_version": "demand-normalization-test",
            "categories": {"perfume": {"weights": {"trend": 100}, "trend": {"rising": 100}}},
        }
    )
    assert changed.content_hash != first.content_hash


def test_unconfigured_value_is_explicit_gap_without_invented_constant() -> None:
    mapped = _result(sales_count=2000)
    assert mapped.component(DemandSignalName.SALES_COUNT).score == 100
    # A category with a weight but no mapping for a present signal is a gap.
    partial = build_demand_normalization(
        {
            "schema_version": "1.0",
            "normalization_version": "partial",
            "categories": {"perfume": {"weights": {"sales_count": 100}}},
        }
    )
    partial_result = _result(sales_count=2000, normalization=partial)
    assert partial_result.component(DemandSignalName.SALES_COUNT).reason == (
        REASON_NORMALIZATION_NOT_DEFINED
    )
    assert WARNING_NORMALIZATION_NOT_DEFINED in _codes(partial_result)
    assert partial_result.demand is None


def test_approved_baseline_does_not_invent_normalization() -> None:
    result = _result(
        sales_count=2000,
        rating_count=600,
        trend="rising",
        affiliate_portal="featured",
        badges=("best seller",),
        normalization=APPROVED_DEMAND_NORMALIZATION,
    )
    assert result.demand is None
    assert result.weight_covered == 0
    assert result.fully_calibrated is False
    assert WARNING_NORMALIZATION_NOT_DEFINED in _codes(result)


def test_missing_category_is_explicit_gap() -> None:
    result = _result(category=None, raw_category=None, sales_count=2000)
    assert result.category is None
    assert WARNING_CATEGORY_NOT_DEFINED in _codes(result)
    assert result.component(DemandSignalName.SALES_COUNT).reason == (
        REASON_NORMALIZATION_NOT_DEFINED
    )
    assert result.demand is None


# --- Invalid data -----------------------------------------------------------


def test_negative_sales_count_is_invalid_and_warns() -> None:
    result = _result(sales_count=-5)
    sales = result.component(DemandSignalName.SALES_COUNT)
    assert sales.score is None
    assert sales.reason == REASON_INVALID_DATA
    assert WARNING_INVALID_DATA in _codes(result)


def test_blank_trend_is_invalid_and_warns() -> None:
    result = _result(trend="   ")
    trend = result.component(DemandSignalName.TREND)
    assert trend.score is None
    assert trend.reason == REASON_INVALID_DATA
    assert WARNING_INVALID_DATA in _codes(result)


def test_unmapped_badge_is_explicit_gap() -> None:
    result = _result(badges=("best seller", "mystery"))
    badges = result.component(DemandSignalName.BADGES)
    assert badges.score is None
    assert badges.reason == REASON_NORMALIZATION_NOT_DEFINED
    warning = next(w for w in result.warnings if w.code == WARNING_NORMALIZATION_NOT_DEFINED)
    assert warning.context["unmapped"] == ["mystery"]


# --- Contract ---------------------------------------------------------------


def test_contract_serializes_versioned_result() -> None:
    result = _result(sales_count=2000, trend="rising")
    contract = result.to_contract()
    assert contract["schema_version"] == "1.0"
    assert contract["status"] == "EVALUATED"
    assert contract["candidate_id"] == "cand_1"
    assert contract["raw_category"] == "Perfumes"
    assert contract["category"] == "perfume"
    assert contract["scoring_version"] == "demand-1.0"
    assert contract["normalization_version"] == "demand-normalization-test"
    assert contract["fully_calibrated"] is False
    assert len(contract["components"]) == 5


# --- Normalization builder validation ---------------------------------------


def test_build_rejects_missing_version() -> None:
    with pytest.raises(DemandNormalizationInvalidError) as excinfo:
        build_demand_normalization({"schema_version": "1.0"})
    assert excinfo.value.error.code == DEMAND_NORMALIZATION_INVALID


def test_build_rejects_unknown_schema_version() -> None:
    with pytest.raises(DemandNormalizationInvalidError):
        build_demand_normalization({"schema_version": "9.9", "normalization_version": "v"})


def test_build_rejects_unknown_category() -> None:
    with pytest.raises(DemandNormalizationInvalidError):
        build_demand_normalization(
            {
                "schema_version": "1.0",
                "normalization_version": "v",
                "categories": {"not-a-category": {"weights": {"trend": 100}}},
            }
        )


def test_build_rejects_unknown_signal_in_weights() -> None:
    with pytest.raises(DemandNormalizationInvalidError):
        build_demand_normalization(
            {
                "schema_version": "1.0",
                "normalization_version": "v",
                "categories": {"perfume": {"weights": {"mystery": 100}}},
            }
        )


@pytest.mark.parametrize("weight", [-1, 101, "many", True])
def test_build_rejects_out_of_range_weight(weight: object) -> None:
    with pytest.raises(DemandNormalizationInvalidError):
        build_demand_normalization(
            {
                "schema_version": "1.0",
                "normalization_version": "v",
                "categories": {"perfume": {"weights": {"trend": weight}}},
            }
        )


def test_build_rejects_overlapping_bands() -> None:
    with pytest.raises(DemandNormalizationInvalidError):
        build_demand_normalization(
            {
                "schema_version": "1.0",
                "normalization_version": "v",
                "categories": {
                    "perfume": {
                        "sales_count": [
                            {"min": 0, "max": 500, "score": 50},
                            {"min": 400, "max": 1000, "score": 100},
                        ]
                    }
                },
            }
        )


def test_build_rejects_float_band_limit() -> None:
    with pytest.raises(DemandNormalizationInvalidError):
        build_demand_normalization(
            {
                "schema_version": "1.0",
                "normalization_version": "v",
                "categories": {
                    "perfume": {"sales_count": [{"min": 0.5, "max": 5.0, "score": 100}]}
                },
            }
        )


def test_build_rejects_max_below_min() -> None:
    with pytest.raises(DemandNormalizationInvalidError):
        build_demand_normalization(
            {
                "schema_version": "1.0",
                "normalization_version": "v",
                "categories": {"perfume": {"sales_count": [{"min": 100, "max": 10, "score": 50}]}},
            }
        )
