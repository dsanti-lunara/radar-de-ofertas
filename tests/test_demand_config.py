from __future__ import annotations

import json
from pathlib import Path

import pytest

from radar.domain.demand import (
    APPROVED_DEMAND_NORMALIZATION,
    DEMAND_NORMALIZATION_INVALID,
    DemandNormalizationInvalidError,
    DemandSignalName,
)
from radar.infrastructure.demand import (
    ENV_DEMAND_FILE,
    DemandLoader,
)

pytestmark = pytest.mark.unit

_VALID_DOCUMENT = {
    "schema_version": "1.0",
    "normalization_version": "demand-normalization-operator",
    "categories": {
        "perfume": {
            "weights": {"sales_count": 100},
            "sales_count": [{"min": 1000, "max": None, "score": 100}],
        }
    },
}


def test_loader_without_file_returns_approved_baseline(tmp_path: Path) -> None:
    normalization = DemandLoader.from_env(env={}, cwd=tmp_path).load()
    assert normalization == APPROVED_DEMAND_NORMALIZATION
    assert normalization.categories == {}


def test_loader_reads_versioned_file(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "demand.json").write_text(json.dumps(_VALID_DOCUMENT), encoding="utf-8")

    normalization = DemandLoader.from_env(env={}, cwd=tmp_path).load()
    assert normalization.normalization_version == "demand-normalization-operator"
    category = normalization.for_category("perfume")
    assert category is not None
    assert category.weight_for(DemandSignalName.SALES_COUNT) == 100


def test_loader_explicit_missing_file_fails_closed(tmp_path: Path) -> None:
    loader = DemandLoader.from_env(
        env={ENV_DEMAND_FILE: str(tmp_path / "missing.json")}, cwd=tmp_path
    )
    with pytest.raises(DemandNormalizationInvalidError) as excinfo:
        loader.load()
    assert excinfo.value.error.code == DEMAND_NORMALIZATION_INVALID


def test_loader_invalid_json_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "demand.json"
    path.write_text("{not-json", encoding="utf-8")
    with pytest.raises(DemandNormalizationInvalidError):
        DemandLoader.from_env(env={}, cwd=tmp_path, normalization_path=path).load()


def test_loader_invalid_document_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "demand.json"
    path.write_text(json.dumps({"schema_version": "1.0"}), encoding="utf-8")
    with pytest.raises(DemandNormalizationInvalidError) as excinfo:
        DemandLoader.from_env(env={}, cwd=tmp_path, normalization_path=path).load()
    assert excinfo.value.error.code == DEMAND_NORMALIZATION_INVALID
