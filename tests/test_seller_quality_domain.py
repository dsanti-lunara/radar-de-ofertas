from __future__ import annotations

from decimal import Decimal

import pytest

from radar.domain.seller_quality import (
    APPROVED_SELLER_QUALITY_NORMALIZATION,
    REASON_INVALID_DATA,
    REASON_MISSING_DATA,
    REASON_NORMALIZATION_NOT_DEFINED,
    SELLER_QUALITY_NORMALIZATION_INVALID,
    WARNING_CONTRADICTION,
    WARNING_INVALID_DATA,
    WARNING_MISSING_DATA,
    WARNING_NORMALIZATION_NOT_DEFINED,
    WEIGHT_MARKETPLACE_REPUTATION,
    WEIGHT_RATING,
    WEIGHT_SALES_HISTORY,
    WEIGHT_TRUSTED_STATUS,
    SellerFacts,
    SellerQualityComponentName,
    SellerQualityNormalizationInvalidError,
    SellerSignal,
    build_seller_quality_normalization,
    compute_seller_quality,
)

pytestmark = pytest.mark.unit

_COMPONENTS = {
    SellerQualityComponentName.MARKETPLACE_REPUTATION,
    SellerQualityComponentName.RATING,
    SellerQualityComponentName.SALES_HISTORY,
    SellerQualityComponentName.TRUSTED_STATUS,
}


def _normalization():
    return build_seller_quality_normalization(
        {
            "schema_version": "1.0",
            "normalization_version": "seller-quality-normalization-test",
            "marketplace_reputation": {"gold": 100, "green": 80},
            "rating": [
                {"min": "4.5", "max": "5.0", "score": 100},
                {"min": "0", "max": "4.4999", "score": 50},
            ],
            "sales_history": [
                {"min": 1000, "max": None, "score": 100},
                {"min": 0, "max": 999, "score": 50},
            ],
            "trusted_status": {"true": 100, "false": 0},
        }
    )


def _result(
    *,
    seller_id: str | None = "seller_1",
    seller_name: str | None = "Loja",
    reputation: str | None = None,
    rating: str | None = None,
    sales_count: int | None = None,
    trusted: bool | None = None,
    normalization=None,
):
    return compute_seller_quality(
        candidate_id="cand_1",
        facts=SellerFacts(
            seller_id=seller_id,
            seller_name=seller_name,
            reputation=(
                None if reputation is None else SellerSignal(value=reputation, source="test")
            ),
            rating=(None if rating is None else SellerSignal(value=Decimal(rating), source="test")),
            sales_count=(
                None if sales_count is None else SellerSignal(value=sales_count, source="test")
            ),
            trusted=(None if trusted is None else SellerSignal(value=trusted, source="test")),
        ),
        normalization=normalization or _normalization(),
    )


def _score(result, name: SellerQualityComponentName) -> int | None:
    return result.component(name).score


def _codes(result) -> list[str]:
    return [warning.code for warning in result.warnings]


# --- Weights (acceptance criterion 1) --------------------------------------


def test_component_weights_follow_sdd() -> None:
    result = _result()
    weights = {component.name: component.weight for component in result.components}
    assert weights == {
        SellerQualityComponentName.MARKETPLACE_REPUTATION: 40,
        SellerQualityComponentName.RATING: 25,
        SellerQualityComponentName.SALES_HISTORY: 20,
        SellerQualityComponentName.TRUSTED_STATUS: 15,
    }
    assert WEIGHT_MARKETPLACE_REPUTATION == 40
    assert WEIGHT_RATING == 25
    assert WEIGHT_SALES_HISTORY == 20
    assert WEIGHT_TRUSTED_STATUS == 15
    assert set(weights) == _COMPONENTS


def test_composition_uses_approved_weights() -> None:
    result = _result(reputation="gold", rating="4.6", sales_count=500, trusted=False)
    # 100*40 + 100*25 + 50*20 + 0*15 = 7500 / 100 = 75
    assert _score(result, SellerQualityComponentName.MARKETPLACE_REPUTATION) == 100
    assert _score(result, SellerQualityComponentName.RATING) == 100
    assert _score(result, SellerQualityComponentName.SALES_HISTORY) == 50
    assert _score(result, SellerQualityComponentName.TRUSTED_STATUS) == 0
    assert result.seller_quality == 75
    assert result.weight_covered == 100
    assert result.fully_calibrated is True


def test_composition_is_deterministic() -> None:
    first = _result(reputation="gold", rating="4.6", sales_count=500, trusted=True)
    second = _result(reputation="gold", rating="4.6", sales_count=500, trusted=True)
    assert first.to_contract() == second.to_contract()


def test_reputation_label_is_case_and_separator_insensitive() -> None:
    for label in ("Gold", " gold ", "GOLD"):
        result = _result(reputation=label)
        assert _score(result, SellerQualityComponentName.MARKETPLACE_REPUTATION) == 100


# --- Missing data never becomes zero (criterion 2) --------------------------


def test_missing_signals_are_none_and_never_zero() -> None:
    result = _result()
    for component in result.components:
        assert component.score is None
        assert component.score != 0
        assert component.calibrated is False
        assert component.reason == REASON_MISSING_DATA
    assert result.seller_quality is None
    assert result.seller_quality != 0
    assert result.weight_covered == 0
    assert result.fully_calibrated is False
    assert _codes(result) == [WARNING_MISSING_DATA] * 4


def test_partial_aggregate_uses_only_calibrated_components() -> None:
    result = _result(trusted=True)
    assert _score(result, SellerQualityComponentName.TRUSTED_STATUS) == 100
    assert result.seller_quality == 100
    assert result.weight_covered == 15
    assert result.fully_calibrated is False
    assert _score(result, SellerQualityComponentName.RATING) is None
    assert WARNING_MISSING_DATA in _codes(result)


# --- Configured normalization: versioned, deterministic, gaps explicit ------


def test_normalization_is_versioned_and_hashed() -> None:
    normalization = _normalization()
    assert normalization.normalization_version == "seller-quality-normalization-test"
    assert len(normalization.content_hash) == 64
    result = _result(normalization=normalization)
    assert result.normalization_version == normalization.normalization_version
    assert result.normalization_hash == normalization.content_hash


def test_hash_is_stable_and_changes_with_content() -> None:
    first = _normalization()
    second = _normalization()
    assert first.content_hash == second.content_hash
    changed = build_seller_quality_normalization(
        {
            "schema_version": "1.0",
            "normalization_version": "seller-quality-normalization-test",
            "marketplace_reputation": {"gold": 90},
        }
    )
    assert changed.content_hash != first.content_hash


def test_unconfigured_value_is_explicit_gap_without_invented_constant() -> None:
    result = _result(reputation="platinum", rating="9.0")
    reputation = result.component(SellerQualityComponentName.MARKETPLACE_REPUTATION)
    rating = result.component(SellerQualityComponentName.RATING)
    assert reputation.score is None
    assert reputation.calibrated is False
    assert reputation.reason == REASON_NORMALIZATION_NOT_DEFINED
    assert rating.score is None
    assert rating.reason == REASON_NORMALIZATION_NOT_DEFINED
    assert _codes(result).count(WARNING_NORMALIZATION_NOT_DEFINED) == 2
    assert result.seller_quality is None


def test_approved_baseline_does_not_invent_normalization() -> None:
    result = _result(
        reputation="gold",
        rating="4.6",
        sales_count=2000,
        trusted=True,
        normalization=APPROVED_SELLER_QUALITY_NORMALIZATION,
    )
    assert result.seller_quality is None
    assert result.weight_covered == 0
    assert _codes(result) == [WARNING_NORMALIZATION_NOT_DEFINED] * 4


def test_bands_are_evaluated_deterministically_regardless_of_input_order() -> None:
    normalization = build_seller_quality_normalization(
        {
            "schema_version": "1.0",
            "normalization_version": "seller-quality-normalization-order",
            "rating": [
                {"min": "4.5", "max": "5.0", "score": 100},
                {"min": "0", "max": "4.4999", "score": 10},
            ],
        }
    )
    assert normalization.score_rating(Decimal("4.9")) == 100
    assert normalization.score_rating(Decimal("2.0")) == 10
    assert normalization.score_rating(Decimal("5.5")) is None


# --- Invalid and contradictory data (criterion 4) ---------------------------


def test_negative_rating_is_invalid_and_warns() -> None:
    result = _result(rating="-1.0")
    rating = result.component(SellerQualityComponentName.RATING)
    assert rating.score is None
    assert rating.reason == REASON_INVALID_DATA
    assert WARNING_INVALID_DATA in _codes(result)


def test_negative_sales_count_is_invalid_and_warns() -> None:
    result = _result(sales_count=-5)
    sales = result.component(SellerQualityComponentName.SALES_HISTORY)
    assert sales.score is None
    assert sales.reason == REASON_INVALID_DATA
    assert WARNING_INVALID_DATA in _codes(result)


def test_signals_without_seller_identity_are_contradictory() -> None:
    result = _result(seller_id=None, seller_name=None, trusted=True)
    assert WARNING_CONTRADICTION in _codes(result)
    contradiction = next(
        warning for warning in result.warnings if warning.code == WARNING_CONTRADICTION
    )
    assert contradiction.context["components"] == ["trusted_status"]


def test_consistent_identity_does_not_emit_contradiction() -> None:
    result = _result(trusted=True)
    assert WARNING_CONTRADICTION not in _codes(result)


# --- Contract / provenance --------------------------------------------------


def test_component_contract_reports_signal_origin() -> None:
    facts = SellerFacts(
        seller_id="seller_1",
        seller_name="Loja",
        reputation=SellerSignal(value="gold", source="evaluation_input"),
        sales_count=SellerSignal(value=500, source="persisted_offer"),
    )
    result = compute_seller_quality(
        candidate_id="cand_1", facts=facts, normalization=_normalization()
    )
    contract = result.to_contract()
    components = {item["name"]: item for item in contract["components"]}
    assert components["marketplace_reputation"]["source"] == "evaluation_input"
    assert components["marketplace_reputation"]["raw"] == "gold"
    assert components["sales_history"]["source"] == "persisted_offer"
    assert components["sales_history"]["raw"] == 500
    assert components["rating"]["source"] is None


def test_contract_serializes_versioned_result() -> None:
    result = _result(reputation="gold", rating="4.6", sales_count=500, trusted=True)
    contract = result.to_contract()
    assert contract["schema_version"] == "1.0"
    assert contract["status"] == "EVALUATED"
    assert contract["candidate_id"] == "cand_1"
    assert contract["seller"] == {"id": "seller_1", "name": "Loja"}
    assert contract["scoring_version"] == "seller-quality-1.0"
    assert contract["normalization_version"] == "seller-quality-normalization-test"
    assert contract["seller_quality"] == 90
    assert len(contract["components"]) == 4


# --- Normalization builder validation --------------------------------------


def test_build_rejects_missing_version() -> None:
    with pytest.raises(SellerQualityNormalizationInvalidError) as excinfo:
        build_seller_quality_normalization({"schema_version": "1.0"})
    assert excinfo.value.error.code == SELLER_QUALITY_NORMALIZATION_INVALID


def test_build_rejects_unknown_schema_version() -> None:
    with pytest.raises(SellerQualityNormalizationInvalidError):
        build_seller_quality_normalization({"schema_version": "9.9", "normalization_version": "v"})


@pytest.mark.parametrize("score", [-1, 101, "many", True])
def test_build_rejects_out_of_range_score(score: object) -> None:
    with pytest.raises(SellerQualityNormalizationInvalidError):
        build_seller_quality_normalization(
            {
                "schema_version": "1.0",
                "normalization_version": "v",
                "trusted_status": {"true": score},
            }
        )


def test_build_rejects_overlapping_bands() -> None:
    with pytest.raises(SellerQualityNormalizationInvalidError):
        build_seller_quality_normalization(
            {
                "schema_version": "1.0",
                "normalization_version": "v",
                "rating": [
                    {"min": "0", "max": "4", "score": 50},
                    {"min": "3", "max": "5", "score": 100},
                ],
            }
        )


def test_build_rejects_unknown_trusted_key() -> None:
    with pytest.raises(SellerQualityNormalizationInvalidError):
        build_seller_quality_normalization(
            {
                "schema_version": "1.0",
                "normalization_version": "v",
                "trusted_status": {"maybe": 50},
            }
        )


def test_build_rejects_float_band_limit() -> None:
    with pytest.raises(SellerQualityNormalizationInvalidError):
        build_seller_quality_normalization(
            {
                "schema_version": "1.0",
                "normalization_version": "v",
                "rating": [{"min": 0.5, "max": 5.0, "score": 100}],
            }
        )


def test_build_rejects_max_below_min() -> None:
    with pytest.raises(SellerQualityNormalizationInvalidError):
        build_seller_quality_normalization(
            {
                "schema_version": "1.0",
                "normalization_version": "v",
                "rating": [{"min": "4", "max": "3", "score": 50}],
            }
        )
