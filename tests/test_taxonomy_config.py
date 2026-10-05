from __future__ import annotations

import json
from pathlib import Path

import pytest

from radar.domain.taxonomy import (
    APPROVED_TAXONOMY,
    TAXONOMY_INVALID,
    Brand,
    TaxonomyInvalidError,
)
from radar.infrastructure.taxonomy import ENV_TAXONOMY_FILE, TaxonomyLoader

pytestmark = pytest.mark.unit

_VALID_DOCUMENT = {
    "schema_version": "1.0",
    "taxonomy_version": "brand-taxonomy-operator",
    "brands": {
        "RADAR_BEAUTY": {
            "categories": {"perfume": {"priority": 1, "brand_fit": 100}},
        }
    },
    "aliases": {"perfume": "perfume"},
}


def test_loader_without_file_returns_approved_taxonomy(tmp_path: Path) -> None:
    taxonomy = TaxonomyLoader.from_env(env={}, cwd=tmp_path).load()
    assert taxonomy == APPROVED_TAXONOMY


def test_loader_reads_versioned_file(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "brand-taxonomy.json").write_text(json.dumps(_VALID_DOCUMENT), encoding="utf-8")

    taxonomy = TaxonomyLoader.from_env(env={}, cwd=tmp_path).load()
    assert taxonomy.taxonomy_version == "brand-taxonomy-operator"
    assert taxonomy.rule_for(Brand.RADAR_BEAUTY, "perfume") is not None
    assert taxonomy.resolve("Perfume") == "perfume"


def test_loader_explicit_missing_file_fails_closed(tmp_path: Path) -> None:
    loader = TaxonomyLoader.from_env(
        env={ENV_TAXONOMY_FILE: str(tmp_path / "missing.json")}, cwd=tmp_path
    )
    with pytest.raises(TaxonomyInvalidError) as excinfo:
        loader.load()
    assert excinfo.value.error.code == TAXONOMY_INVALID


def test_loader_invalid_json_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "taxonomy.json"
    path.write_text("{not-json", encoding="utf-8")
    with pytest.raises(TaxonomyInvalidError):
        TaxonomyLoader.from_env(env={}, cwd=tmp_path, taxonomy_path=path).load()


def test_loader_invalid_document_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "taxonomy.json"
    path.write_text(json.dumps({"schema_version": "1.0"}), encoding="utf-8")
    with pytest.raises(TaxonomyInvalidError) as excinfo:
        TaxonomyLoader.from_env(env={}, cwd=tmp_path, taxonomy_path=path).load()
    assert excinfo.value.error.code == TAXONOMY_INVALID
