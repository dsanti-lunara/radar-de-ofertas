from __future__ import annotations

import pytest

from radar.domain.taxonomy import (
    APPROVED_TAXONOMY,
    HARD_RULE_OUT_OF_SCOPE_CATEGORY,
    WARNING_BRAND_FIT_CALIBRATION_REQUIRED,
    WARNING_CATEGORY_MAPPING_NOT_DEFINED,
    WARNING_CATEGORY_NOT_PROVIDED,
    Brand,
    TaxonomyInvalidError,
    build_taxonomy,
    classify_category,
    normalize_category,
)

pytestmark = pytest.mark.unit


def test_approved_taxonomy_carries_radar_beauty_values() -> None:
    expected = {
        "perfume": (1, 100),
        "body_splash": (1, 100),
        "hair": (2, 85),
        "skincare": (2, 85),
        "makeup": (3, 65),
        "accessories": (3, 60),
    }
    for category, (priority, brand_fit) in expected.items():
        rule = APPROVED_TAXONOMY.rule_for(Brand.RADAR_BEAUTY, category)
        assert rule is not None, category
        assert rule.priority == priority
        assert rule.brand_fit == brand_fit
        assert rule.calibrated is True


def test_approved_taxonomy_does_not_invent_casa_em_ordem_brand_fit() -> None:
    for category in ("organization", "kitchen", "utilities", "cleaning", "laundry", "bathroom"):
        rule = APPROVED_TAXONOMY.rule_for(Brand.CASA_EM_ORDEM, category)
        assert rule is not None, category
        assert rule.brand_fit is None
        assert rule.calibrated is False


def test_approved_taxonomy_is_versioned_and_hashed() -> None:
    assert APPROVED_TAXONOMY.taxonomy_version == "brand-taxonomy-1.0"
    assert len(APPROVED_TAXONOMY.content_hash) == 64


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Body Splash", "body splash"),
        ("body_splash", "body splash"),
        ("  PERFUMES  ", "perfumes"),
        ("", None),
        (None, None),
    ],
)
def test_normalize_category_handles_case_and_separators(
    raw: str | None, expected: str | None
) -> None:
    assert normalize_category(raw) == expected


def test_radar_beauty_brand_fit_is_explainable() -> None:
    result = classify_category(
        candidate_id="cand_1",
        brand=Brand.RADAR_BEAUTY,
        raw_category="Perfumes",
        taxonomy=APPROVED_TAXONOMY,
    )
    assert result.category == "perfume"
    assert result.priority == 1
    assert result.brand_fit == 100
    assert result.calibrated is True
    assert result.calibration_required is False
    assert result.warnings == ()
    assert result.hard_rules == ()
    contract = result.to_contract()
    assert contract["brand"] == "RADAR_BEAUTY"
    assert contract["taxonomy_version"] == "brand-taxonomy-1.0"
    assert contract["taxonomy_hash"] == APPROVED_TAXONOMY.content_hash


def test_out_of_scope_category_emits_hard_rule() -> None:
    result = classify_category(
        candidate_id="cand_1",
        brand=Brand.CASA_EM_ORDEM,
        raw_category="Perfumes",
        taxonomy=APPROVED_TAXONOMY,
    )
    assert result.category == "perfume"
    assert result.brand_fit is None
    assert result.calibrated is False
    assert len(result.hard_rules) == 1
    assert result.hard_rules[0].rule == HARD_RULE_OUT_OF_SCOPE_CATEGORY
    assert result.hard_rules[0].to_contract()["context"]["category"] == "perfume"


def test_undefined_mapping_is_explicit_gap_without_invented_value() -> None:
    result = classify_category(
        candidate_id="cand_1",
        brand=Brand.RADAR_BEAUTY,
        raw_category="Categoria Estranha",
        taxonomy=APPROVED_TAXONOMY,
    )
    assert result.category is None
    assert result.priority is None
    assert result.brand_fit is None
    assert result.calibrated is False
    assert result.hard_rules == ()
    assert [warning.code for warning in result.warnings] == [WARNING_CATEGORY_MAPPING_NOT_DEFINED]


def test_missing_category_is_explicit_gap() -> None:
    result = classify_category(
        candidate_id="cand_1",
        brand=Brand.RADAR_BEAUTY,
        raw_category=None,
        taxonomy=APPROVED_TAXONOMY,
    )
    assert result.category is None
    assert result.calibrated is False
    assert [warning.code for warning in result.warnings] == [WARNING_CATEGORY_NOT_PROVIDED]


def test_casa_em_ordem_calibration_gap_is_explicit() -> None:
    result = classify_category(
        candidate_id="cand_1",
        brand=Brand.CASA_EM_ORDEM,
        raw_category="Cozinha",
        taxonomy=APPROVED_TAXONOMY,
    )
    assert result.category == "kitchen"
    assert result.priority == 1
    assert result.brand_fit is None
    assert result.calibrated is False
    assert result.hard_rules == ()
    assert [warning.code for warning in result.warnings] == [WARNING_BRAND_FIT_CALIBRATION_REQUIRED]


def test_classification_is_deterministic() -> None:
    first = classify_category(
        candidate_id="cand_1",
        brand=Brand.RADAR_BEAUTY,
        raw_category="Cabelo",
        taxonomy=APPROVED_TAXONOMY,
    )
    second = classify_category(
        candidate_id="cand_1",
        brand=Brand.RADAR_BEAUTY,
        raw_category="Cabelo",
        taxonomy=APPROVED_TAXONOMY,
    )
    assert first.to_contract() == second.to_contract()


def _document(**overrides: object) -> dict[str, object]:
    document: dict[str, object] = {
        "schema_version": "1.0",
        "taxonomy_version": "brand-taxonomy-test",
        "brands": {"RADAR_BEAUTY": {"categories": {"perfume": {"priority": 1, "brand_fit": 100}}}},
        "aliases": {"perfume": "perfume"},
    }
    document.update(overrides)
    return document


def test_build_taxonomy_rejects_missing_version() -> None:
    document = _document()
    del document["taxonomy_version"]
    with pytest.raises(TaxonomyInvalidError):
        build_taxonomy(document)


def test_build_taxonomy_rejects_unknown_brand() -> None:
    with pytest.raises(TaxonomyInvalidError):
        build_taxonomy(_document(brands={"ACME": {"categories": {"perfume": {"priority": 1}}}}))


def test_build_taxonomy_rejects_unknown_category() -> None:
    with pytest.raises(TaxonomyInvalidError):
        build_taxonomy(
            _document(brands={"RADAR_BEAUTY": {"categories": {"unknown": {"priority": 1}}}})
        )


def test_build_taxonomy_rejects_out_of_range_brand_fit() -> None:
    with pytest.raises(TaxonomyInvalidError):
        build_taxonomy(
            _document(
                brands={
                    "RADAR_BEAUTY": {"categories": {"perfume": {"priority": 1, "brand_fit": 101}}}
                }
            )
        )


def test_build_taxonomy_rejects_alias_to_unknown_category() -> None:
    with pytest.raises(TaxonomyInvalidError):
        build_taxonomy(_document(aliases={"perfume": "nope"}))


def test_content_hash_changes_with_content_and_is_stable() -> None:
    first = build_taxonomy(_document())
    second = build_taxonomy(_document())
    changed = build_taxonomy(
        _document(
            brands={"RADAR_BEAUTY": {"categories": {"perfume": {"priority": 1, "brand_fit": 90}}}}
        )
    )
    assert first.content_hash == second.content_hash
    assert first.content_hash != changed.content_hash
