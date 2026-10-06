"""Effective Settings read model and AUTO eligibility boundary (RDR-067)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from radar.api.app import create_app
from radar.domain.errors import RadarException
from radar.domain.operations import (
    AutomationMode,
    build_automation_policy,
    build_compliance_policy,
)
from radar.domain.publication import build_publication_policy
from radar.domain.taxonomy import APPROVED_TAXONOMY
from radar.infrastructure.database import create_database_engine
from radar.infrastructure.settings import Settings

pytestmark = pytest.mark.contract


def _client(database_url: str, *, compliance_status: str = "ACTIVE") -> TestClient:
    settings = Settings(database_url=database_url)
    engine = create_database_engine(database_url)
    return TestClient(
        create_app(
            settings=settings,
            engine=engine,
            taxonomy=APPROVED_TAXONOMY,
            automation_policy=build_automation_policy(
                {
                    "schema_version": "1.0",
                    "policy_version": "a1",
                    "default_mode": AutomationMode.SHADOW.value,
                }
            ),
            compliance_policy=build_compliance_policy(
                {"schema_version": "1.0", "policy_version": "c1", "status": compliance_status}
            ),
            publication_policy=build_publication_policy(
                {"schema_version": "1.0", "policy_version": "p1"}
            ),
        )
    )


def test_settings_expose_versioned_policies_and_never_promote_auto(
    migrated_database_url: str,
) -> None:
    client = _client(migrated_database_url)

    response = client.get("/settings", headers={"X-Correlation-ID": "cid-set"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["schema_version"] == "1.0"
    assert body["status"] == "OK"
    assert body["correlation_id"] == "cid-set"
    assert response.headers["cache-control"] == "no-store"

    # Modes/caps/compliance are the already versioned/hashed policies.
    assert body["automation_policy"]["policy_version"] == "a1"
    assert body["automation_policy"]["policy_hash"]
    assert body["compliance_policy"]["policy_version"] == "c1"
    assert body["compliance_policy"]["status"] == "ACTIVE"
    assert body["publication_policy"]["policy_version"] == "p1"
    assert body["publication_policy"]["policy_hash"]
    assert body["publication_policy"]["default_limits"]["hard_cap_per_day"] == 12

    assert body["operations"]["global_mode"] == "RUNNING"
    assert body["operations"]["stop_external_actions"] is False
    assert body["integrations"] == []

    eligibility = body["auto_eligibility"]
    assert eligibility["eligible"] is False
    assert eligibility["promotes_automatically"] is False
    assert eligibility["requires_human_decision"] is True
    by_id = {item["criterion"]: item["state"] for item in eligibility["criteria"]}
    assert by_id["compliance_policy"] == "MET"
    assert by_id["integration_health"] == "NOT_MET"
    assert by_id["open_human_actions"] == "MET"
    # Unproven criteria are honest and keep the aggregate fail-closed.
    assert by_id["shadow_samples"] == "UNAVAILABLE"
    assert by_id["human_agreement"] == "UNAVAILABLE"
    assert by_id["p0_p1_open"] == "UNAVAILABLE"
    assert by_id["validation_failures"] == "UNAVAILABLE"


def test_unknown_compliance_blocks_and_never_reports_eligible(
    migrated_database_url: str,
) -> None:
    client = _client(migrated_database_url, compliance_status="UNKNOWN")
    body = client.get("/settings").json()
    by_id = {item["criterion"]: item["state"] for item in body["auto_eligibility"]["criteria"]}
    assert by_id["compliance_policy"] == "NOT_MET"
    assert body["auto_eligibility"]["eligible"] is False


def test_registered_integration_drives_the_health_criterion(
    migrated_database_url: str,
) -> None:
    client = _client(migrated_database_url)
    updated = client.put(
        "/integrations/telegram",
        json={"schema_version": "1.0", "state": "ONLINE", "summary": "up"},
    )
    assert updated.status_code == 200, updated.text

    body = client.get("/settings").json()
    assert [item["name"] for item in body["integrations"]] == ["telegram"]
    by_id = {item["criterion"]: item["state"] for item in body["auto_eligibility"]["criteria"]}
    assert by_id["integration_health"] == "MET"
    # Still not eligible: unproven criteria remain and promotion stays human.
    assert body["auto_eligibility"]["eligible"] is False
    assert body["auto_eligibility"]["promotes_automatically"] is False


def test_invalid_policy_is_rejected_without_inventing_a_threshold() -> None:
    """An invalid threshold fails closed with RAD-CFG-016 (acceptance #3)."""

    with pytest.raises(RadarException) as caught:
        build_publication_policy(
            {"schema_version": "1.0", "policy_version": "p1", "hard_cap_per_day": 0}
        )
    assert caught.value.error.code == "RAD-CFG-016"
