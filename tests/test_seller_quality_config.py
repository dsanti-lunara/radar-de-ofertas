from __future__ import annotations

import json
from pathlib import Path

import pytest

from radar.domain.seller_quality import (
    APPROVED_SELLER_QUALITY_NORMALIZATION,
    SELLER_QUALITY_NORMALIZATION_INVALID,
    SellerQualityNormalizationInvalidError,
)
from radar.infrastructure.seller_quality import (
    ENV_SELLER_QUALITY_FILE,
    SellerQualityLoader,
)

pytestmark = pytest.mark.unit

_VALID_DOCUMENT = {
    "schema_version": "1.0",
    "normalization_version": "seller-quality-normalization-operator",
    "marketplace_reputation": {"gold": 100},
    "rating": [{"min": "4.5", "max": "5.0", "score": 100}],
    "sales_history": [{"min": 1000, "max": None, "score": 100}],
    "trusted_status": {"true": 100, "false": 0},
}


def test_loader_without_file_returns_approved_baseline(tmp_path: Path) -> None:
    normalization = SellerQualityLoader.from_env(env={}, cwd=tmp_path).load()
    assert normalization == APPROVED_SELLER_QUALITY_NORMALIZATION
    assert normalization.reputation_scores == {}
    assert normalization.rating_bands == ()


def test_loader_reads_versioned_file(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "seller-quality.json").write_text(json.dumps(_VALID_DOCUMENT), encoding="utf-8")

    normalization = SellerQualityLoader.from_env(env={}, cwd=tmp_path).load()
    assert normalization.normalization_version == "seller-quality-normalization-operator"
    assert normalization.score_reputation("Gold") == 100
    assert normalization.score_trusted(True) == 100


def test_loader_explicit_missing_file_fails_closed(tmp_path: Path) -> None:
    loader = SellerQualityLoader.from_env(
        env={ENV_SELLER_QUALITY_FILE: str(tmp_path / "missing.json")}, cwd=tmp_path
    )
    with pytest.raises(SellerQualityNormalizationInvalidError) as excinfo:
        loader.load()
    assert excinfo.value.error.code == SELLER_QUALITY_NORMALIZATION_INVALID


def test_loader_invalid_json_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "seller-quality.json"
    path.write_text("{not-json", encoding="utf-8")
    with pytest.raises(SellerQualityNormalizationInvalidError):
        SellerQualityLoader.from_env(env={}, cwd=tmp_path, normalization_path=path).load()


def test_loader_invalid_document_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "seller-quality.json"
    path.write_text(json.dumps({"schema_version": "1.0"}), encoding="utf-8")
    with pytest.raises(SellerQualityNormalizationInvalidError) as excinfo:
        SellerQualityLoader.from_env(env={}, cwd=tmp_path, normalization_path=path).load()
    assert excinfo.value.error.code == SELLER_QUALITY_NORMALIZATION_INVALID
