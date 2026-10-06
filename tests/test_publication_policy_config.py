from __future__ import annotations

import json
from pathlib import Path

import pytest

from radar.domain.publication import (
    APPROVED_PUBLICATION_POLICY,
    PUBLICATION_POLICY_INVALID,
    PublicationError,
)
from radar.infrastructure.publication_policy import (
    ENV_PUBLICATION_POLICY_FILE,
    PublicationPolicyLoader,
)

pytestmark = pytest.mark.unit

_VALID_DOCUMENT = {
    "schema_version": "1.0",
    "policy_version": "publication-policy-operator",
    "timezone": "America/Maceio",
    "hard_cap_per_day": 10,
    "burst_limit": 1,
    "burst_window_minutes": 30,
    "cooldown_minutes": 45,
    "quiet_windows": [{"start": "22:00", "end": "07:00"}],
    "channels": {"WHATSAPP": {"hard_cap_per_day": 8}},
}


def test_loader_without_file_returns_approved_baseline(tmp_path: Path) -> None:
    policy = PublicationPolicyLoader.from_env(env={}, cwd=tmp_path).load()

    assert policy == APPROVED_PUBLICATION_POLICY
    assert policy.default_limits.hard_cap_per_day == 12


def test_loader_reads_versioned_file(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "publication-policy.json").write_text(
        json.dumps(_VALID_DOCUMENT), encoding="utf-8"
    )

    policy = PublicationPolicyLoader.from_env(env={}, cwd=tmp_path).load()

    assert policy.policy_version == "publication-policy-operator"
    assert policy.default_limits.hard_cap_per_day == 10
    assert policy.default_limits.cooldown_minutes == 45
    assert policy.quiet_windows[0].start == "22:00"
    assert policy.channel_limits["WHATSAPP"].hard_cap_per_day == 8


def test_loader_explicit_missing_file_fails_closed(tmp_path: Path) -> None:
    loader = PublicationPolicyLoader.from_env(
        env={ENV_PUBLICATION_POLICY_FILE: str(tmp_path / "missing.json")}, cwd=tmp_path
    )

    with pytest.raises(PublicationError) as excinfo:
        loader.load()
    assert excinfo.value.error.code == PUBLICATION_POLICY_INVALID


def test_loader_invalid_json_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "publication-policy.json"
    path.write_text("{not-json", encoding="utf-8")

    with pytest.raises(PublicationError):
        PublicationPolicyLoader.from_env(env={}, cwd=tmp_path, policy_path=path).load()


def test_loader_invalid_document_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "publication-policy.json"
    path.write_text(json.dumps({"schema_version": "1.0"}), encoding="utf-8")

    with pytest.raises(PublicationError) as excinfo:
        PublicationPolicyLoader.from_env(env={}, cwd=tmp_path, policy_path=path).load()
    assert excinfo.value.error.code == PUBLICATION_POLICY_INVALID
