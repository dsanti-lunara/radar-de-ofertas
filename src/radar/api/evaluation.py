"""Candidate Evaluation public endpoints (RDR-016, RDR-027..RDR-030).

``POST /candidates/{candidate_id}/evaluations`` composes and persists an
immutable Evaluation from the normalized component scores of the dependent
tickets and the active taxonomy. ``GET /candidates/{candidate_id}/evaluations``
returns the stored evaluations oldest first, so the decision is observable from
the public boundary.

The Evaluation is append-only: repeated evaluations create new versions and old
ones are never overwritten (AUT-030). No AI call, affiliate link or publication
is triggered here; a Hard Rule blocks before those steps (AUT-056). Structured
errors reuse the shared ``RadarException`` handler registered by the capture
boundary.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy.engine import Engine

from radar.api.captures import resolve_correlation_id
from radar.api.contracts import (
    CORRELATION_HEADER,
    EvaluationRequestContract,
)
from radar.application.correlation import bind_correlation_id
from radar.application.evaluation_service import EvaluationService
from radar.domain.evaluation import (
    EVALUATION_SCHEMA_VERSION,
    ConfidenceFacts,
    DealFacts,
    HardRule,
    MonetizationFacts,
    evaluation_input_invalid_error,
)
from radar.domain.taxonomy import BrandTaxonomy
from radar.infrastructure.capture_repository import SqlAlchemyCaptureRepository
from radar.infrastructure.evaluation_repository import SqlAlchemyEvaluationRepository


def _parse_hard_rules(values: list[str]) -> tuple[HardRule, ...]:
    """Validate declared Hard Rules, failing closed on an unknown rule."""

    rules: list[HardRule] = []
    for value in values:
        try:
            rules.append(HardRule(value))
        except ValueError as exc:
            raise evaluation_input_invalid_error(
                "Hard Rule desconhecida na avaliação",
                context={"hard_rule": value},
            ) from exc
    return tuple(rules)


def build_evaluation_router(engine: Engine, taxonomy: BrandTaxonomy) -> APIRouter:
    """Build the Evaluation router wired to the SQLite store and taxonomy."""

    router = APIRouter(tags=["evaluation"])
    service = EvaluationService(
        repository=SqlAlchemyCaptureRepository(engine=engine),
        store=SqlAlchemyEvaluationRepository(engine=engine),
        taxonomy=taxonomy,
    )

    @router.post("/candidates/{candidate_id}/evaluations", status_code=201)
    def evaluate_candidate(
        candidate_id: str,
        payload: EvaluationRequestContract,
        request: Request,
    ) -> JSONResponse:
        correlation_id = bind_correlation_id(resolve_correlation_id(request))
        evaluation = service.evaluate(
            candidate_id,
            brand=payload.brand,
            deal=DealFacts(
                price_opportunity=payload.deal.price_opportunity,
                seller_quality=payload.deal.seller_quality,
                demand=payload.deal.demand,
            ),
            monetization=MonetizationFacts(
                estimated_commission=payload.monetization.estimated_commission,
                effective_commission_percent=payload.monetization.effective_commission_percent,
                conversion_evidence=payload.monetization.conversion_evidence,
                extra_commission=payload.monetization.extra_commission,
            ),
            confidence=ConfidenceFacts(
                source_reliability=payload.confidence.source_reliability,
                freshness=payload.confidence.freshness,
                completeness=payload.confidence.completeness,
                price_history_depth=payload.confidence.price_history_depth,
                cross_validation=payload.confidence.cross_validation,
            ),
            declared_hard_rules=_parse_hard_rules(payload.hard_rules),
            correlation_id=correlation_id,
        )
        return JSONResponse(
            status_code=201,
            content={"status": "EVALUATED", **evaluation.to_contract()},
            headers={CORRELATION_HEADER: correlation_id, "Cache-Control": "no-store"},
        )

    @router.get("/candidates/{candidate_id}/evaluations")
    def list_candidate_evaluations(candidate_id: str, request: Request) -> JSONResponse:
        correlation_id = bind_correlation_id(resolve_correlation_id(request))
        evaluations = service.list_evaluations(candidate_id)
        return JSONResponse(
            status_code=200,
            content={
                "schema_version": EVALUATION_SCHEMA_VERSION,
                "status": "OK",
                "candidate_id": candidate_id,
                "count": len(evaluations),
                "evaluations": [evaluation.to_contract() for evaluation in evaluations],
                "correlation_id": correlation_id,
            },
            headers={CORRELATION_HEADER: correlation_id, "Cache-Control": "no-store"},
        )

    return router


__all__ = [
    "build_evaluation_router",
]
