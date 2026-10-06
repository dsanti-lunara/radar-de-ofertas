from __future__ import annotations

import json
from pathlib import Path

import pytest

from radar.domain.tracking import (
    APPROVED_TRACKING_LABEL_MAPPING,
    TRACKING_LABELS_INVALID,
    TrackingError,
)
from radar.infrastructure.tracking_labels import (
    ENV_TRACKING_LABELS_FILE,
    TrackingLabelMappingLoader,
)

pytestmark = pytest.mark.unit

_VALID_DOCUMENT = {
    "schema_version": "1.0",
    "mapping_version": "tracking-labels-operator",
    "entries": [
        {
            "internal_reference": "RADAR_BEAUTY:MERCADO_LIVRE",
            "marketplace": "MERCADO_LIVRE",
            "label": "rbtgoffer",
        }
    ],
}


def test_loader_without_file_returns_empty_baseline(tmp_path: Path) -> None:
    mapping = TrackingLabelMappingLoader.from_env(env={}, cwd=tmp_path).load()

    assert mapping == APPROVED_TRACKING_LABEL_MAPPING
    assert mapping.entries == {}


def test_loader_reads_versioned_file(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "tracking-labels.json").write_text(json.dumps(_VALID_DOCUMENT), encoding="utf-8")

    mapping = TrackingLabelMappingLoader.from_env(env={}, cwd=tmp_path).load()

    assert mapping.mapping_version == "tracking-labels-operator"
    assert mapping.entries["RADAR_BEAUTY:MERCADO_LIVRE"].label == "rbtgoffer"
    assert mapping.content_hash


def test_loader_explicit_missing_file_fails_closed(tmp_path: Path) -> None:
    loader = TrackingLabelMappingLoader.from_env(
        env={ENV_TRACKING_LABELS_FILE: str(tmp_path / "missing.json")}, cwd=tmp_path
    )

    with pytest.raises(TrackingError) as excinfo:
        loader.load()
    assert excinfo.value.error.code == TRACKING_LABELS_INVALID


def test_loader_invalid_json_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "tracking-labels.json"
    path.write_text("{not-json", encoding="utf-8")

    with pytest.raises(TrackingError):
        TrackingLabelMappingLoader.from_env(env={}, cwd=tmp_path, labels_path=path).load()


def test_loader_invalid_label_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "tracking-labels.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "mapping_version": "v1",
                "entries": [
                    {
                        "internal_reference": "RADAR_BEAUTY:MERCADO_LIVRE",
                        "marketplace": "MERCADO_LIVRE",
                        "label": "NOT_lower",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(TrackingError) as excinfo:
        TrackingLabelMappingLoader.from_env(env={}, cwd=tmp_path, labels_path=path).load()
    assert excinfo.value.error.code == "RAD-LINK-004"
