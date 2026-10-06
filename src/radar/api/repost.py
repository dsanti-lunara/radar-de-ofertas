"""Candidate repost/dedupe public endpoints (RDR-033).

``POST /candidates/{candidate_id}/repost`` applies the dedupe/repost guardrail to
the persisted Candidate against the publication history supplied by the caller (a
*fake* history until the real publisher exists) and persists an append-only
decision with its Evidence. ``GET /candidates/{candidate_id}/repost`` returns the
stored decisions oldest first, so the guardrail is observable and auditable from
the public boundary.

A material coupon/condition is only accepted with ``Evidence``; an irrelevant
change never releases a repost while the cooldown is active, and an expired
cooldown still requires a strong Deal. No AI, affiliate link or publication is
triggered here. Structured errors reuse the shared ``RadarException`` handler
registered by the capture boundary.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy.engine import Engine

from radar.api.captures import resolve_correlation_id
from radar.api.contracts import (
    CORRELATION_HEADER,
    RepostEvidenceContract,
    RepostPublicationContract,
    RepostRequestContract,
)
from radar.application.correlation import bind_correlation_id
from radar.application.repost_service import RepostService
from radar.domain.capture import (
    CaptureValidationError,
    parse_money,
    sanitize_single_line,
)
from radar.domain.price_opportunity import Coupon, CouponState
from radar.domain.repost import (
    REPOST_SCHEMA_VERSION,
    PublicationSnapshot,
    RepostEvidence,
    RepostPolicy,
    repost_input_invalid_error,
)
from radar.infrastructure.capture_repository import SqlAlchemyCaptureRepository
from radar.infrastructure.evaluation_repository import SqlAlchemyEvaluationRepository
from radar.infrastructure.repost_repository import SqlAlchemyRepostDecisionRepository


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    return sanitize_single_line(value) or None


def _money(value: str | int, *, field_name: str) -> Decimal:
    try:
        return parse_money(value, field_name=field_name)
    except CaptureValidationError as exc:
        raise repost_input_invalid_error(exc.error.message, context={"field": field_name}) from exc


def _optional_money(value: str | int | None, *, field_name: str) -> Decimal | None:
    if value is None:
        return None
    return _money(value, field_name=field_name)


def _parse_coupon(state: str | None, amount: str | int | None, code: str | None) -> Coupon | None:
    if state is None and amount is None and code is None:
        return None
    if state is None:
        raise repost_input_invalid_error(
            "coupon_state é obrigatório quando cupom é informado",
            context={"field": "coupon_state"},
        )
    try:
        coupon_state = CouponState(state)
    except ValueError as exc:
        raise repost_input_invalid_error(
            "coupon_state inválido",
            context={"field": "coupon_state", "allowed": [item.value for item in CouponState]},
        ) from exc
    return Coupon(
        state=coupon_state,
        amount=_optional_money(amount, field_name="coupon_amount"),
        code=_clean(code),
    )


def _parse_conditions(conditions: Mapping[str, str]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for raw_key, raw_value in conditions.items():
        key = sanitize_single_line(str(raw_key))
        if not key:
            raise repost_input_invalid_error("condição sem chave", context={"field": "conditions"})
        parsed[key] = sanitize_single_line(str(raw_value))
    return parsed


def _parse_publication(publication: RepostPublicationContract) -> PublicationSnapshot:
    return PublicationSnapshot(
        published_at=publication.published_at,
        price=_money(publication.price, field_name="price"),
        publication_id=_clean(publication.publication_id),
        coupon=_parse_coupon(
            publication.coupon_state, publication.coupon_amount, publication.coupon_code
        ),
        conditions=_parse_conditions(publication.conditions),
    )


def _parse_evidence(evidence: RepostEvidenceContract) -> RepostEvidence:
    return RepostEvidence(
        evidence_type=evidence.evidence_type,
        reference_id=sanitize_single_line(evidence.reference_id),
        field=sanitize_single_line(evidence.field),
        value=sanitize_single_line(evidence.value),
        source=sanitize_single_line(evidence.source),
    )


def build_repost_router(engine: Engine, policy: RepostPolicy) -> APIRouter:
    """Build the repost router wired to the SQLite stores and policy."""

    router = APIRouter(tags=["repost"])
    service = RepostService(
        repository=SqlAlchemyCaptureRepository(engine=engine),
        evaluations=SqlAlchemyEvaluationRepository(engine=engine),
        store=SqlAlchemyRepostDecisionRepository(engine=engine),
        policy=policy,
    )

    @router.post("/candidates/{candidate_id}/repost", status_code=201)
    def decide_repost(
        candidate_id: str,
        payload: RepostRequestContract,
        request: Request,
    ) -> JSONResponse:
        correlation_id = bind_correlation_id(resolve_correlation_id(request))
        record = service.decide(
            candidate_id,
            correlation_id=correlation_id,
            publications=[_parse_publication(item) for item in payload.publications],
            coupon=_parse_coupon(payload.coupon_state, payload.coupon_amount, payload.coupon_code),
            conditions=_parse_conditions(payload.conditions),
            evidence=[_parse_evidence(item) for item in payload.evidence],
        )
        return JSONResponse(
            status_code=201,
            content=record.to_contract(),
            headers={CORRELATION_HEADER: correlation_id, "Cache-Control": "no-store"},
        )

    @router.get("/candidates/{candidate_id}/repost")
    def list_repost_decisions(candidate_id: str, request: Request) -> JSONResponse:
        correlation_id = bind_correlation_id(resolve_correlation_id(request))
        decisions = service.list_decisions(candidate_id)
        return JSONResponse(
            status_code=200,
            content={
                "schema_version": REPOST_SCHEMA_VERSION,
                "status": "OK",
                "candidate_id": candidate_id,
                "count": len(decisions),
                "decisions": [decision.to_contract() for decision in decisions],
                "correlation_id": correlation_id,
            },
            headers={CORRELATION_HEADER: correlation_id, "Cache-Control": "no-store"},
        )

    return router


__all__ = [
    "build_repost_router",
]
