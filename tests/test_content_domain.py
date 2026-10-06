from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

from radar.domain.ai_review import AIReviewEvaluationFacts, AIReviewOfferFacts, AIReviewProductFacts
from radar.domain.allowed_claims import (
    ClaimOfferFacts,
    compute_allowed_claims,
)
from radar.domain.content import (
    CONTENT_GENERATION_ENGINE_VERSION,
    CONTENT_SCHEMA_VERSION,
    DISCLOSURE_TEXT,
    UNSUPPORTED_CLAIM,
    UNSUPPORTED_NUMERIC_CLAIM,
    ContentGenerationError,
    ContentGenerationInput,
    ContentGenerationStatus,
    ContentValidation,
    GeneratedContent,
    build_content_generation,
    build_content_generation_input,
    channel_guard,
    claim_guard,
    is_stale,
    numeric_guard,
    parse_generate_content_response,
    render_content,
    validate_generated_content,
)
from radar.domain.knowledge import APPROVED_KNOWLEDGE_PACK, Channel, select_knowledge_context
from radar.domain.operations import (
    APPROVED_COMPLIANCE_POLICY,
    ComplianceStatus,
    build_compliance_policy,
)
from radar.domain.price_opportunity import Coupon, CouponState
from radar.domain.taxonomy import Brand

pytestmark = pytest.mark.unit

FIXED_NOW = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)


def _claims(*, current_price: str = "80.00", coupon: Coupon | None = None) -> Any:
    offer = ClaimOfferFacts(
        offer_id="off_1",
        current_price=Decimal(current_price),
        observed_at=FIXED_NOW,
        source="BROWSER_EXTENSION",
        correlation_id="cid-1",
        raw_capture_id="raw_1",
        sales_count=2300,
        coupon=coupon,
    )
    return compute_allowed_claims(
        candidate_id="cand_1",
        evaluation_id="eval_1",
        evaluation_decision="APPROVE",
        offer=offer,
    )


def _generated(
    *,
    headline: str = "Perfume em destaque",
    body: str = "Oferta por R$ 80,00.",
    cta: str = "Compre",
) -> GeneratedContent:
    return GeneratedContent(headline=headline, body=body, cta=cta)


def test_numeric_guard_accepts_only_evidence_backed_numbers() -> None:
    claims = _claims()

    assert numeric_guard(_generated(), claims=claims) == ()
    assert numeric_guard(_generated(body="De R$ 80,00 por R$ 80,00."), claims=claims) == ()

    errors = numeric_guard(_generated(body="Preço absurdo de R$ 999,00!"), claims=claims)
    assert len(errors) == 1
    assert errors[0].code == UNSUPPORTED_NUMERIC_CLAIM
    assert errors[0].guard == "numeric"


def test_claim_guard_blocks_forbidden_expressions() -> None:
    claims = _claims()

    assert claim_guard(_generated(), claims=claims) == ()

    errors = claim_guard(_generated(headline="Melhor preço da internet!"), claims=claims)
    assert len(errors) == 1
    assert errors[0].code == UNSUPPORTED_CLAIM
    assert errors[0].context["claim_code"] == "BEST_PRICE_ON_THE_INTERNET"

    last_units = claim_guard(_generated(body="Últimas unidades!"), claims=claims)
    assert last_units[0].context["claim_code"] == "LAST_UNITS"


def test_claim_guard_only_allows_coupon_when_confirmed() -> None:
    unconfirmed = _claims()
    confirmed = _claims(coupon=Coupon(state=CouponState.CONFIRMED, code="RADAR10"))

    assert claim_guard(_generated(body="Use o cupom hoje."), claims=confirmed) == ()
    assert numeric_guard(_generated(body="Use o cupom RADAR10 hoje."), claims=confirmed) == ()
    errors = claim_guard(_generated(body="Use o cupom hoje."), claims=unconfirmed)
    assert errors[0].context["claim_code"] == "UNVERIFIED_COUPON"


def test_channel_guard_rejects_content_over_the_limit() -> None:
    assert channel_guard(_generated(), channel=Channel.TELEGRAM) == ()
    oversized = _generated(body="x" * 5000)
    errors = channel_guard(oversized, channel=Channel.TELEGRAM)
    assert errors[0].code == "RAD-AI-014"


def test_compliance_guard_blocks_only_an_explicit_block() -> None:
    validation = validate_generated_content(
        generated=_generated(),
        claims=_claims(),
        channel=Channel.TELEGRAM,
        compliance_policy=APPROVED_COMPLIANCE_POLICY,
        now=FIXED_NOW,
    )
    assert validation.passed
    assert any(warning.code == "CONTENT_COMPLIANCE_NOT_ACTIVE" for warning in validation.warnings)

    blocked = build_compliance_policy(
        {
            "schema_version": "1.0",
            "policy_version": "compliance-test",
            "status": ComplianceStatus.BLOCKED.value,
        }
    )
    blocked_validation = validate_generated_content(
        generated=_generated(),
        claims=_claims(),
        channel=Channel.TELEGRAM,
        compliance_policy=blocked,
        now=FIXED_NOW,
    )
    assert not blocked_validation.passed
    assert blocked_validation.errors[0].code == "RAD-AI-015"


def test_parse_rejects_ai_invented_url() -> None:
    with pytest.raises(ContentGenerationError) as excinfo:
        parse_generate_content_response(
            {
                "headline": "Oferta",
                "body": "Compre em https://evil.example.com/MLB-1",
                "cta": "Compre",
                "warnings": [],
            },
            provider="stub",
        )
    assert excinfo.value.error.code == "RAD-AI-013"


def test_parse_rejects_unknown_sensitive_and_missing_fields() -> None:
    with pytest.raises(ContentGenerationError) as unknown:
        parse_generate_content_response(
            {"headline": "a", "body": "b", "cta": "c", "affiliate_url": "https://x"},
            provider="stub",
        )
    assert unknown.value.error.code == "RAD-AI-004"

    with pytest.raises(ContentGenerationError) as sensitive:
        parse_generate_content_response(
            {"headline": "a", "body": "b", "cta": "c", "warnings": [], "token": "abc"},
            provider="stub",
        )
    assert sensitive.value.error.code == "RAD-AI-007"

    with pytest.raises(ContentGenerationError) as missing:
        parse_generate_content_response(
            {"headline": "a", "cta": "c", "warnings": []}, provider="stub"
        )
    assert missing.value.error.code == "RAD-AI-004"


def test_renderer_inserts_backend_price_link_and_disclosure() -> None:
    rendered = render_content(
        generated=_generated(),
        price="80.00",
        affiliate_url="https://www.mercadolivre.com.br/social/radar-fake/MLB-1?matt_word=rbtgoffer",
        tracking={"tracking_context_id": "trk_1", "external_label": "rbtgoffer"},
    )

    assert rendered.price == "80.00"
    assert rendered.price_display == "80,00"
    assert rendered.disclosure == DISCLOSURE_TEXT
    assert "rbtgoffer" in rendered.affiliate_url
    assert rendered.affiliate_url in rendered.text
    assert DISCLOSURE_TEXT in rendered.text
    assert rendered.blocks[3] == "Preço: R$ 80,00"
    assert rendered.renderer_version == "renderer-1.0"


def _input() -> ContentGenerationInput:
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
        offer=AIReviewOfferFacts(current_price="80.00", sales_count=2300),
        evaluation=AIReviewEvaluationFacts(
            evaluation_id="eval_1", decision="APPROVE", deal_score="91.00"
        ),
        knowledge=knowledge,
        allowed_claims=_claims().to_contract()["claims"],
    )


def test_generated_and_final_content_are_separate_and_versioned() -> None:
    request = _input()
    generated = _generated()
    rendered = render_content(
        generated=generated,
        price="80.00",
        affiliate_url="https://www.mercadolivre.com.br/social/radar-fake/MLB-1?matt_word=rbtgoffer",
        tracking={"external_label": "rbtgoffer"},
    )
    validation = ContentValidation(guards=("numeric", "claim", "channel", "compliance"), errors=())
    record = build_content_generation(
        request=request,
        generated=generated,
        rendered=rendered,
        validation=validation,
        facts={"price": "80.00"},
        correlation_id="cid-1",
        audit_event_id="aud_1",
        created_at=FIXED_NOW,
    )

    contract = record.to_contract()
    assert contract["status"] == ContentGenerationStatus.VALIDATED.value
    assert contract["publishable"] is True
    assert contract["schema_version"] == CONTENT_SCHEMA_VERSION
    assert contract["generation_version"] == CONTENT_GENERATION_ENGINE_VERSION
    assert contract["generated_content"] == {
        "headline": "Perfume em destaque",
        "body": "Oferta por R$ 80,00.",
        "cta": "Compre",
        "warnings": [],
    }
    assert contract["final_content"]["affiliate_url"].endswith("matt_word=rbtgoffer")
    assert contract["generated_content"]["body"] != contract["final_content"]["text"]


def test_staleness_is_derived_from_the_fact_hash() -> None:
    request = _input()
    rendered = render_content(
        generated=_generated(),
        price="80.00",
        affiliate_url="https://www.mercadolivre.com.br/social/radar-fake/MLB-1?matt_word=rbtgoffer",
        tracking={"external_label": "rbtgoffer"},
    )
    validation = ContentValidation(guards=("numeric",), errors=())
    facts = {"price": "80.00", "channel": "TELEGRAM"}
    record = build_content_generation(
        request=request,
        generated=_generated(),
        rendered=rendered,
        validation=validation,
        facts=facts,
        correlation_id="cid-1",
        audit_event_id="aud_1",
        created_at=FIXED_NOW,
    )

    assert is_stale(record, current_facts=facts) is False
    assert is_stale(record, current_facts={**facts, "price": "90.00"}) is True
    assert record.to_contract(stale=True)["status"] == ContentGenerationStatus.STALE.value
    assert record.to_contract(stale=True)["publishable"] is False
