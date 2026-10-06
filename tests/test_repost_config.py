from __future__ import annotations

import json
from pathlib import Path

import pytest

from radar.domain.repost import (
    APPROVED_REPOST_POLICY,
    REPOST_POLICY_INVALID,
    RepostPolicyInvalidError,
)
from radar.infrastructure.repost import ENV_REPOST_FILE, RepostPolicyLoader

pytestmark = pytest.mark.unit

_VALID_DOCUMENT = {
    "schema_version": "1.0",
    "policy_version": "repost-policy-operator",
    "cooldown_hours": 48,
    "price_drop_percent": "12",
    "strong_deal_threshold": "85",
}


def test_loader_without_file_returns_approved_baseline(tmp_path: Path) -> None:
    policy = RepostPolicyLoader.from_env(env={}, cwd=tmp_path).load()

    assert policy == APPROVED_REPOST_POLICY
    assert policy.cooldown_hours == 72
    assert str(policy.price_drop_percent) == "10"


def test_loader_reads_versioned_file(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "repost.json").write_text(json.dumps(_VALID_DOCUMENT), encoding="utf-8")

    policy = RepostPolicyLoader.from_env(env={}, cwd=tmp_path).load()

    assert policy.policy_version == "repost-policy-operator"
    assert policy.cooldown_hours == 48
    assert str(policy.price_drop_percent) == "12"
    assert str(policy.strong_deal_threshold) == "85"


def test_loader_explicit_missing_file_fails_closed(tmp_path: Path) -> None:
    loader = RepostPolicyLoader.from_env(
        env={ENV_REPOST_FILE: str(tmp_path / "missing.json")}, cwd=tmp_path
    )

    with pytest.raises(RepostPolicyInvalidError) as excinfo:
        loader.load()
    assert excinfo.value.error.code == REPOST_POLICY_INVALID


def test_loader_invalid_json_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "repost.json"
    path.write_text("{not-json", encoding="utf-8")

    with pytest.raises(RepostPolicyInvalidError):
        RepostPolicyLoader.from_env(env={}, cwd=tmp_path, policy_path=path).load()


def test_loader_invalid_document_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "repost.json"
    path.write_text(json.dumps({"schema_version": "1.0"}), encoding="utf-8")

    with pytest.raises(RepostPolicyInvalidError) as excinfo:
        RepostPolicyLoader.from_env(env={}, cwd=tmp_path, policy_path=path).load()
    assert excinfo.value.error.code == REPOST_POLICY_INVALID
