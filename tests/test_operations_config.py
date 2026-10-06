from __future__ import annotations

import json
from pathlib import Path

import pytest

from radar.domain.operations import (
    APPROVED_AUTOMATION_POLICY,
    APPROVED_COMPLIANCE_POLICY,
    AUTOMATION_POLICY_INVALID,
    COMPLIANCE_POLICY_INVALID,
    AutomationMode,
    ComplianceStatus,
    OperationsError,
)
from radar.infrastructure.automation_policy import (
    ENV_AUTOMATION_POLICY_FILE,
    AutomationPolicyLoader,
)
from radar.infrastructure.compliance_policy import (
    ENV_COMPLIANCE_POLICY_FILE,
    CompliancePolicyLoader,
)

pytestmark = pytest.mark.unit


def test_automation_loader_without_file_returns_approved_baseline(tmp_path: Path) -> None:
    policy = AutomationPolicyLoader.from_env(env={}, cwd=tmp_path).load()
    assert policy == APPROVED_AUTOMATION_POLICY
    assert policy.default_mode is AutomationMode.SHADOW


def test_automation_loader_reads_versioned_file(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "automation-policy.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "policy_version": "automation-policy-operator",
                "default_mode": "SHADOW",
                "rules": [{"mode": "ASSISTED", "channel": "TELEGRAM"}],
            }
        ),
        encoding="utf-8",
    )

    policy = AutomationPolicyLoader.from_env(env={}, cwd=tmp_path).load()
    assert policy.policy_version == "automation-policy-operator"
    assert policy.mode_for(channel="TELEGRAM") is AutomationMode.ASSISTED
    assert policy.mode_for(channel="WHATSAPP") is AutomationMode.SHADOW


def test_automation_loader_explicit_missing_file_fails_closed(tmp_path: Path) -> None:
    loader = AutomationPolicyLoader.from_env(
        env={ENV_AUTOMATION_POLICY_FILE: str(tmp_path / "missing.json")}, cwd=tmp_path
    )
    with pytest.raises(OperationsError) as excinfo:
        loader.load()
    assert excinfo.value.error.code == AUTOMATION_POLICY_INVALID


def test_automation_loader_invalid_json_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "automation-policy.json"
    path.write_text("{not-json", encoding="utf-8")
    with pytest.raises(OperationsError) as excinfo:
        AutomationPolicyLoader.from_env(env={}, cwd=tmp_path, policy_path=path).load()
    assert excinfo.value.error.code == AUTOMATION_POLICY_INVALID


def test_automation_loader_invalid_document_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "automation-policy.json"
    path.write_text(json.dumps({"schema_version": "9.9", "policy_version": "a"}), encoding="utf-8")
    with pytest.raises(OperationsError) as excinfo:
        AutomationPolicyLoader.from_env(env={}, cwd=tmp_path, policy_path=path).load()
    assert excinfo.value.error.code == AUTOMATION_POLICY_INVALID


def test_compliance_loader_without_file_returns_blocking_baseline(tmp_path: Path) -> None:
    policy = CompliancePolicyLoader.from_env(env={}, cwd=tmp_path).load()
    assert policy == APPROVED_COMPLIANCE_POLICY
    assert policy.status is ComplianceStatus.UNKNOWN


def test_compliance_loader_reads_versioned_file(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "channel-compliance.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "policy_version": "compliance-policy-operator",
                "status": "ACTIVE",
                "review_due_at": "2026-12-31T23:59:59+00:00",
                "source_reference": "docs/12_SECURITY_AND_COMPLIANCE.md",
            }
        ),
        encoding="utf-8",
    )

    policy = CompliancePolicyLoader.from_env(env={}, cwd=tmp_path).load()
    assert policy.policy_version == "compliance-policy-operator"
    assert policy.status is ComplianceStatus.ACTIVE
    assert policy.source_reference == "docs/12_SECURITY_AND_COMPLIANCE.md"


def test_compliance_loader_explicit_missing_file_fails_closed(tmp_path: Path) -> None:
    loader = CompliancePolicyLoader.from_env(
        env={ENV_COMPLIANCE_POLICY_FILE: str(tmp_path / "missing.json")}, cwd=tmp_path
    )
    with pytest.raises(OperationsError) as excinfo:
        loader.load()
    assert excinfo.value.error.code == COMPLIANCE_POLICY_INVALID


def test_compliance_loader_invalid_json_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "channel-compliance.json"
    path.write_text("{not-json", encoding="utf-8")
    with pytest.raises(OperationsError) as excinfo:
        CompliancePolicyLoader.from_env(env={}, cwd=tmp_path, policy_path=path).load()
    assert excinfo.value.error.code == COMPLIANCE_POLICY_INVALID


def test_compliance_loader_invalid_document_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "channel-compliance.json"
    path.write_text(json.dumps({"schema_version": "1.0"}), encoding="utf-8")
    with pytest.raises(OperationsError) as excinfo:
        CompliancePolicyLoader.from_env(env={}, cwd=tmp_path, policy_path=path).load()
    assert excinfo.value.error.code == COMPLIANCE_POLICY_INVALID
