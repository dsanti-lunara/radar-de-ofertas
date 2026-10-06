from __future__ import annotations

import json
from pathlib import Path

import pytest

from radar.domain.retry import (
    APPROVED_RETRY_POLICY,
    RETRY_POLICY_INVALID,
    RetryError,
)
from radar.infrastructure.retry import ENV_RETRY_FILE, RetryPolicyLoader

pytestmark = pytest.mark.unit

_VALID_DOCUMENT = {
    "schema_version": "1.0",
    "policy_version": "retry-policy-operator",
    "backoff_seconds": [10, 40, 90],
}


def test_loader_without_file_returns_approved_baseline(tmp_path: Path) -> None:
    policy = RetryPolicyLoader.from_env(env={}, cwd=tmp_path).load()

    assert policy == APPROVED_RETRY_POLICY
    assert policy.backoff_seconds == (30, 120, 600, 1800)


def test_loader_reads_versioned_file(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "retry-policy.json").write_text(json.dumps(_VALID_DOCUMENT), encoding="utf-8")

    policy = RetryPolicyLoader.from_env(env={}, cwd=tmp_path).load()

    assert policy.policy_version == "retry-policy-operator"
    assert policy.backoff_seconds == (10, 40, 90)


def test_loader_explicit_missing_file_fails_closed(tmp_path: Path) -> None:
    loader = RetryPolicyLoader.from_env(
        env={ENV_RETRY_FILE: str(tmp_path / "missing.json")}, cwd=tmp_path
    )

    with pytest.raises(RetryError) as excinfo:
        loader.load()
    assert excinfo.value.error.code == RETRY_POLICY_INVALID


def test_loader_invalid_json_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "retry-policy.json"
    path.write_text("{not-json", encoding="utf-8")

    with pytest.raises(RetryError):
        RetryPolicyLoader.from_env(env={}, cwd=tmp_path, policy_path=path).load()


def test_loader_invalid_document_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "retry-policy.json"
    path.write_text(json.dumps({"schema_version": "1.0"}), encoding="utf-8")

    with pytest.raises(RetryError) as excinfo:
        RetryPolicyLoader.from_env(env={}, cwd=tmp_path, policy_path=path).load()
    assert excinfo.value.error.code == RETRY_POLICY_INVALID
