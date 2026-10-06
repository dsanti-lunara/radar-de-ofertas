from __future__ import annotations

from datetime import UTC, datetime

import pytest

from radar.domain.opportunity import (
    ALLOWED_OPPORTUNITY_TRANSITIONS,
    OPPORTUNITY_INPUT_INVALID,
    OPPORTUNITY_TRANSITION_INVALID,
    OpportunityError,
    OpportunityState,
    coerce_opportunity_state,
    create_opportunity,
    transition_opportunity,
)
from radar.domain.taxonomy import Brand

pytestmark = pytest.mark.unit

FIXED_NOW = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)


def _opportunity():
    return create_opportunity(
        candidate_id="cand_1",
        evaluation_id="eval_1",
        brand=Brand.RADAR_BEAUTY,
        correlation_id="cid-1",
        now=FIXED_NOW,
        audit_event_id="aud_1",
    )


def test_opportunity_is_created_ready_with_traceable_fields() -> None:
    opportunity = _opportunity()

    assert opportunity.state is OpportunityState.READY
    assert opportunity.opportunity_id.startswith("opp_")
    assert opportunity.candidate_id == "cand_1"
    assert opportunity.evaluation_id == "eval_1"
    assert opportunity.brand is Brand.RADAR_BEAUTY
    assert opportunity.priority == 0
    assert opportunity.correlation_id == "cid-1"
    assert opportunity.audit_event_id == "aud_1"
    contract = opportunity.to_contract()
    assert contract["state"] == "READY"
    assert contract["schema_version"] == "1.0"
    assert contract["allowed_transitions"] == ["CANCELLED", "EXPIRED", "LINK_PENDING"]


def test_create_opportunity_rejects_unsupported_schema_and_unknown_brand() -> None:
    with pytest.raises(OpportunityError) as schema:
        create_opportunity(
            candidate_id="cand_1",
            evaluation_id="eval_1",
            brand=Brand.RADAR_BEAUTY,
            correlation_id="cid-1",
            now=FIXED_NOW,
            audit_event_id="aud_1",
            schema_version="2.0",
        )
    assert schema.value.error.code == OPPORTUNITY_INPUT_INVALID

    with pytest.raises(OpportunityError) as brand:
        create_opportunity(
            candidate_id="cand_1",
            evaluation_id="eval_1",
            brand="NOT_A_BRAND",  # type: ignore[arg-type]
            correlation_id="cid-1",
            now=FIXED_NOW,
            audit_event_id="aud_1",
        )
    assert brand.value.error.code == OPPORTUNITY_INPUT_INVALID


def test_allowed_transition_follows_the_state_machine() -> None:
    opportunity = _opportunity()

    linked = transition_opportunity(
        opportunity, target=OpportunityState.LINK_PENDING, now=FIXED_NOW
    )
    assert linked.state is OpportunityState.LINK_PENDING

    ready = transition_opportunity(linked, target="LINK_READY", now=FIXED_NOW)
    assert ready.state is OpportunityState.LINK_READY


def test_invalid_transition_is_rejected_with_allowed_targets() -> None:
    opportunity = _opportunity()

    with pytest.raises(OpportunityError) as excinfo:
        transition_opportunity(opportunity, target=OpportunityState.PUBLISHED, now=FIXED_NOW)

    error = excinfo.value.error
    assert error.code == OPPORTUNITY_TRANSITION_INVALID
    assert error.context["current_state"] == "READY"
    assert error.context["target_state"] == "PUBLISHED"
    assert error.context["allowed_states"] == ["CANCELLED", "EXPIRED", "LINK_PENDING"]


def test_noop_transition_is_rejected() -> None:
    opportunity = _opportunity()

    with pytest.raises(OpportunityError) as excinfo:
        transition_opportunity(opportunity, target=OpportunityState.READY, now=FIXED_NOW)

    assert excinfo.value.error.code == OPPORTUNITY_TRANSITION_INVALID


def test_terminal_states_have_no_transitions() -> None:
    opportunity = _opportunity()
    expired = transition_opportunity(opportunity, target=OpportunityState.EXPIRED, now=FIXED_NOW)

    assert ALLOWED_OPPORTUNITY_TRANSITIONS[OpportunityState.EXPIRED] == frozenset()
    with pytest.raises(OpportunityError) as excinfo:
        transition_opportunity(expired, target=OpportunityState.LINK_PENDING, now=FIXED_NOW)
    assert excinfo.value.error.code == OPPORTUNITY_TRANSITION_INVALID


def test_published_offer_may_still_expire() -> None:
    opportunity = _opportunity()
    link_pending = transition_opportunity(
        opportunity, target=OpportunityState.LINK_PENDING, now=FIXED_NOW
    )
    link_ready = transition_opportunity(
        link_pending, target=OpportunityState.LINK_READY, now=FIXED_NOW
    )
    content = transition_opportunity(
        link_ready, target=OpportunityState.CONTENT_PENDING, now=FIXED_NOW
    )
    ready = transition_opportunity(content, target=OpportunityState.READY_TO_PUBLISH, now=FIXED_NOW)
    published = transition_opportunity(ready, target=OpportunityState.PUBLISHED, now=FIXED_NOW)

    assert published.state is OpportunityState.PUBLISHED
    assert (
        transition_opportunity(published, target=OpportunityState.EXPIRED, now=FIXED_NOW).state
        is OpportunityState.EXPIRED
    )


def test_unknown_target_state_fails_closed_as_input_error() -> None:
    with pytest.raises(OpportunityError) as excinfo:
        coerce_opportunity_state("NOT_A_STATE")

    assert excinfo.value.error.code == OPPORTUNITY_INPUT_INVALID
