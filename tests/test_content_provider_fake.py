from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

from radar.domain.ai_review import AIReviewEvaluationFacts, AIReviewOfferFacts, AIReviewProductFacts
from radar.domain.allowed_claims import ClaimOfferFacts, compute_allowed_claims
from radar.domain.content import build_content_generation_input, parse_generate_content_response
from radar.domain.knowledge import APPROVED_KNOWLEDGE_PACK, Channel, select_knowledge_context
from radar.domain.taxonomy import Brand
from radar.infrastructure.ai_provider import (
    FAKE_CONTENT_MODEL,
    FakeAIProvider,
)

pytestmark = pytest.mark.unit

FIXED_NOW = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)


def _claims() -> Any:
    return compute_allowed_claims(
        candidate_id="cand_1",
        evaluation_id="eval_1",
        evaluation_decision="APPROVE",
        offer=ClaimOfferFacts(
            offer_id="off_1",
            current_price=Decimal("80.00"),
            observed_at=FIXED_NOW,
            source="BROWSER_EXTENSION",
            correlation_id="cid-1",
            raw_capture_id="raw_1",
        ),
    )


def _request() -> Any:
    knowledge = select_knowledge_context(
        APPROVED_KNOWLEDGE_PACK,
        brand=Brand.RADAR_BEAUTY,
        channel=Channel.TELEGRAM,
        task="GENERATE_CONTENT",
    )
    return build_content_generation_input(
        candidate_id="cand_1",
        opportunity_id="opp_1",
        marketplace="MERCADO_LIVRE",
        product=AIReviewProductFacts(external_id="MLB-1", title="Perfume"),
        offer=AIReviewOfferFacts(current_price="80.00"),
        evaluation=AIReviewEvaluationFacts(evaluation_id="eval_1", decision="APPROVE"),
        knowledge=knowledge,
        allowed_claims=_claims().to_contract()["claims"],
    )


def test_fake_content_is_deterministic_and_evidence_backed() -> None:
    provider = FakeAIProvider()
    first = provider.generate_content(_request())
    second = provider.generate_content(_request())

    assert first == second
    assert first["headline"].startswith("Radar Beauty")
    assert "80.00" in first["body"]
    assert first["warnings"] == []
    assert FAKE_CONTENT_MODEL


def test_fake_content_never_carries_a_url() -> None:
    response = FakeAIProvider().generate_content(_request())
    generated = parse_generate_content_response(response, provider="fake")

    assert "http" not in generated.headline
    assert "http" not in generated.body
    assert "http" not in generated.cta
