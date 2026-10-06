from __future__ import annotations

from datetime import UTC, datetime

import pytest

from radar.domain.human_review import (
    HUMAN_REVIEW_INPUT_INVALID,
    HUMAN_REVIEW_NOT_FOUND,
    HUMAN_REVIEW_SCHEMA_VERSION,
    REVIEW_CANDIDATE_NOT_FOUND,
    HumanDecision,
    HumanReviewError,
    build_edited_content,
    build_human_review,
    human_review_not_found_error,
    review_candidate_not_found_error,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)


def _review(**overrides: object):
    values: dict[str, object] = {
        "candidate_id": "cand_1",
        "human_decision": "APPROVE",
        "reason": "Preço e evidência conferem",
        "correlation_id": "cid-1",
        "now": NOW,
        "ai_review_id": "air_1",
        "ai_decision": "REVIEW",
        "id_factory": _ids("hr_1", "aud_1"),
    }
    values.update(overrides)
    return build_human_review(**values)  # type: ignore[arg-type]


def _ids(*values: str):
    iterator = iter(values)
    return lambda prefix: next(iterator)


def test_approve_preserves_the_ai_and_human_decisions_and_reason() -> None:
    review = _review(human_decision="APPROVE")

    contract = review.to_contract()
    assert review.human_decision is HumanDecision.APPROVE
    assert contract["schema_version"] == HUMAN_REVIEW_SCHEMA_VERSION
    assert contract["ai_review_id"] == "air_1"
    assert contract["ai_decision"] == "REVIEW"
    assert contract["human_decision"] == "APPROVE"
    assert contract["reason"] == "Preço e evidência conferem"
    assert contract["decision_matches_ai"] is False
    assert contract["publication_authorized"] is False
    assert contract["reviewed_at"] == "2026-10-06T12:00:00+00:00"
    assert review.is_candidate_approval is True


def test_reject_preserves_the_ai_decision_and_never_authorizes_publication() -> None:
    review = _review(human_decision="REJECT", ai_decision="APPROVE")

    contract = review.to_contract()
    assert contract["human_decision"] == "REJECT"
    assert contract["ai_decision"] == "APPROVE"
    assert contract["decision_matches_ai"] is False
    # Even an override of an approving AI never authorizes a commercial send.
    assert contract["publication_authorized"] is False
    assert review.is_candidate_approval is False


def test_edit_content_requires_and_sanitizes_the_edited_copy() -> None:
    review = _review(
        human_decision="EDIT_CONTENT",
        edited_content={
            "headline": "Oferta  <b>real</b>\n",
            "body": "  Corpo   com   espaços ",
            "cta": "Comprar\x07 agora",
        },
    )

    assert review.edited_content is not None
    assert review.edited_content.headline == "Oferta real"
    assert review.edited_content.body == "Corpo com espaços"
    assert review.edited_content.cta == "Comprar agora"
    assert review.to_contract()["edited_content"] == {
        "headline": "Oferta real",
        "body": "Corpo com espaços",
        "cta": "Comprar agora",
    }


def test_edit_content_without_payload_fails_closed() -> None:
    with pytest.raises(HumanReviewError) as excinfo:
        _review(human_decision="EDIT_CONTENT")

    assert excinfo.value.error.code == HUMAN_REVIEW_INPUT_INVALID
    assert excinfo.value.error.context["field"] == "edited_content"


def test_approve_rejects_an_edited_content_payload() -> None:
    with pytest.raises(HumanReviewError) as excinfo:
        _review(
            human_decision="APPROVE",
            edited_content={"headline": "h", "body": "b", "cta": "c"},
        )

    assert excinfo.value.error.code == HUMAN_REVIEW_INPUT_INVALID
    assert excinfo.value.error.context["field"] == "edited_content"


def test_unknown_decision_fails_closed_with_the_allowed_values() -> None:
    with pytest.raises(HumanReviewError) as excinfo:
        _review(human_decision="PUBLISH")

    error = excinfo.value.error
    assert error.code == HUMAN_REVIEW_INPUT_INVALID
    assert "APPROVE" in error.context["allowed"]
    assert "EDIT_CONTENT" in error.context["allowed"]


def test_unsupported_schema_version_is_rejected() -> None:
    with pytest.raises(HumanReviewError) as excinfo:
        _review(schema_version="2.0")

    assert excinfo.value.error.code == HUMAN_REVIEW_INPUT_INVALID
    assert excinfo.value.error.context["field"] == "schema_version"


def test_blank_reason_and_correlation_id_are_rejected() -> None:
    with pytest.raises(HumanReviewError):
        _review(reason="   ")
    with pytest.raises(HumanReviewError) as excinfo:
        _review(correlation_id="  ")

    assert excinfo.value.error.context["field"] == "correlation_id"


def test_edited_content_requires_all_three_fields() -> None:
    with pytest.raises(HumanReviewError) as excinfo:
        build_edited_content({"headline": "h", "body": "b"})

    assert excinfo.value.error.context["field"] == "edited_content.cta"


def test_error_codes_are_structured_and_actionable() -> None:
    not_found = human_review_not_found_error("hr_missing").error
    assert not_found.code == HUMAN_REVIEW_NOT_FOUND
    assert not_found.retryable is False
    assert not_found.action

    candidate = review_candidate_not_found_error("cand_missing").error
    assert candidate.code == REVIEW_CANDIDATE_NOT_FOUND
    assert candidate.retryable is False
    assert candidate.context["candidate_id"] == "cand_missing"
