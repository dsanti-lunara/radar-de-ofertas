from __future__ import annotations

import json
from pathlib import Path

import pytest

from radar.domain.purchase_source import (
    APPROVED_PURCHASE_SOURCE_POLICY,
    PURCHASE_SOURCE_POLICY_INVALID,
    MaterialDifferenceAction,
    PurchaseSourcePolicyInvalidError,
)
from radar.infrastructure.purchase_source import (
    ENV_PURCHASE_SOURCE_FILE,
    PurchaseSourcePolicyLoader,
)

pytestmark = pytest.mark.unit

_VALID_DOCUMENT = {
    "schema_version": "1.0",
    "policy_version": "purchase-source-policy-operator",
    "reference_difference_percent": "5",
    "on_material_difference": "SUBSTITUTE",
}


def test_loader_without_file_returns_approved_baseline(tmp_path: Path) -> None:
    policy = PurchaseSourcePolicyLoader.from_env(env={}, cwd=tmp_path).load()

    assert policy == APPROVED_PURCHASE_SOURCE_POLICY
    assert policy.reference_difference_percent == 8


def test_loader_reads_versioned_file(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "purchase-source.json").write_text(json.dumps(_VALID_DOCUMENT), encoding="utf-8")

    policy = PurchaseSourcePolicyLoader.from_env(env={}, cwd=tmp_path).load()

    assert policy.policy_version == "purchase-source-policy-operator"
    assert str(policy.reference_difference_percent) == "5"
    assert policy.on_material_difference is MaterialDifferenceAction.SUBSTITUTE


def test_loader_explicit_missing_file_fails_closed(tmp_path: Path) -> None:
    loader = PurchaseSourcePolicyLoader.from_env(
        env={ENV_PURCHASE_SOURCE_FILE: str(tmp_path / "missing.json")}, cwd=tmp_path
    )

    with pytest.raises(PurchaseSourcePolicyInvalidError) as excinfo:
        loader.load()
    assert excinfo.value.error.code == PURCHASE_SOURCE_POLICY_INVALID


def test_loader_invalid_json_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "purchase-source.json"
    path.write_text("{not-json", encoding="utf-8")

    with pytest.raises(PurchaseSourcePolicyInvalidError):
        PurchaseSourcePolicyLoader.from_env(env={}, cwd=tmp_path, policy_path=path).load()


def test_loader_invalid_document_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "purchase-source.json"
    path.write_text(json.dumps({"schema_version": "1.0"}), encoding="utf-8")

    with pytest.raises(PurchaseSourcePolicyInvalidError) as excinfo:
        PurchaseSourcePolicyLoader.from_env(env={}, cwd=tmp_path, policy_path=path).load()
    assert excinfo.value.error.code == PURCHASE_SOURCE_POLICY_INVALID
