"""Manual capture and price-history public endpoints and structured errors.

``POST /captures/manual`` receives the versioned capture, persists the
RawCapture/Evidence graph and returns the resulting Candidate.
``GET /candidates/{candidate_id}`` reads that Candidate back and
``GET /marketplace-products/{id}/price-history`` returns the append-only price
series with provenance, so the persisted behaviour is observable from the public
boundary.

(RDR-011, RDR-012, RDR-013, RDR-014, RDR-015, RDR-021.)
"""

from __future__ import annotations

from fastapi import APIRouter, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.engine import Engine

from radar.api.contracts import (
    CORRELATION_HEADER,
    SENSITIVE_FIELD_ERROR_TYPE,
    ManualCaptureContract,
)
from radar.application.capture_service import ManualCaptureService
from radar.application.correlation import bind_correlation_id, new_correlation_id
from radar.domain.affiliate_link import (
    AFFILIATE_LINK_INPUT_INVALID,
    AFFILIATE_LINK_NOT_FOUND,
    AFFILIATE_LINK_NOT_PRODUCTIVE,
    AFFILIATE_LINK_OPPORTUNITY_NOT_LINKABLE,
    AFFILIATE_LINK_PROVIDER_UNAVAILABLE,
    AFFILIATE_LINK_URL_INVALID,
)
from radar.domain.ai_review import (
    AI_AUTH_REQUIRED,
    AI_INVALID_RESPONSE,
    AI_POLICY_VIOLATION,
    AI_PROVIDER_UNAVAILABLE,
    AI_REFUSAL,
    AI_REVIEW_INPUT_INVALID,
    AI_REVIEW_NOT_FOUND,
    AI_USAGE_UNAVAILABLE,
)
from radar.domain.allowed_claims import ALLOWED_CLAIMS_INPUT_INVALID, EVALUATION_NOT_FOUND
from radar.domain.capture import (
    CANDIDATE_NOT_FOUND,
    CAPTURE_IDENTITY_CONFLICT,
    CAPTURE_PAYLOAD_INVALID,
    CAPTURE_SCHEMA_VERSION,
    CAPTURE_SENSITIVE_FIELD,
    MARKETPLACE_PRODUCT_NOT_FOUND,
)
from radar.domain.demand import DEMAND_INPUT_INVALID
from radar.domain.errors import RadarError, RadarException
from radar.domain.evaluation import EVALUATION_INPUT_INVALID
from radar.domain.human_action import HUMAN_ACTION_NOT_FOUND
from radar.domain.job import (
    JOB_INPUT_INVALID,
    JOB_LEASE_NOT_HELD,
    JOB_NOT_CLAIMABLE,
    JOB_NOT_FOUND,
    JOB_STATE_INVALID,
    LOCK_UNAVAILABLE,
)
from radar.domain.operations import (
    AUTOMATION_POLICY_INVALID,
    COMPLIANCE_POLICY_INVALID,
    OPERATIONS_INPUT_INVALID,
)
from radar.domain.opportunity import (
    OPPORTUNITY_INPUT_INVALID,
    OPPORTUNITY_NOT_FOUND,
    OPPORTUNITY_TRANSITION_INVALID,
)
from radar.domain.price_opportunity import PRICE_OPPORTUNITY_INPUT_INVALID
from radar.domain.purchase_source import PURCHASE_SOURCE_INPUT_INVALID
from radar.domain.recovery import RECOVERY_INPUT_INVALID
from radar.domain.repost import REPOST_INPUT_INVALID
from radar.domain.schedule import SCHEDULE_INPUT_INVALID, SCHEDULE_NOT_FOUND
from radar.domain.seller_quality import SELLER_QUALITY_INPUT_INVALID
from radar.domain.taxonomy import (
    CLASSIFICATION_INPUT_INVALID,
    TAXONOMY_VERSION_MISMATCH,
)
from radar.domain.tracking import (
    TRACKING_LABEL_INVALID,
    TRACKING_LABELS_INVALID,
    TRACKING_MAPPING_NOT_CONFIGURED,
)
from radar.domain.workflow import (
    REVALIDATION_REQUIRED,
    WORKFLOW_POLICY_INVALID,
)
from radar.infrastructure.capture_repository import SqlAlchemyCaptureRepository


def resolve_correlation_id(request: Request) -> str:
    """Use the caller's Correlation ID or generate one when absent."""

    return request.headers.get(CORRELATION_HEADER) or new_correlation_id()


def _error_status(error_code: str) -> int:
    if error_code in (
        CANDIDATE_NOT_FOUND,
        MARKETPLACE_PRODUCT_NOT_FOUND,
        EVALUATION_NOT_FOUND,
        HUMAN_ACTION_NOT_FOUND,
        JOB_NOT_FOUND,
        SCHEDULE_NOT_FOUND,
        OPPORTUNITY_NOT_FOUND,
        AI_REVIEW_NOT_FOUND,
        AFFILIATE_LINK_NOT_FOUND,
    ):
        return 404
    if error_code in (
        AI_AUTH_REQUIRED,
        AI_PROVIDER_UNAVAILABLE,
        AI_USAGE_UNAVAILABLE,
        AFFILIATE_LINK_PROVIDER_UNAVAILABLE,
    ):
        return 503
    if error_code in (
        AI_INVALID_RESPONSE,
        AI_POLICY_VIOLATION,
        AI_REFUSAL,
    ):
        return 502
    if error_code in (
        CAPTURE_IDENTITY_CONFLICT,
        JOB_LEASE_NOT_HELD,
        JOB_NOT_CLAIMABLE,
        JOB_STATE_INVALID,
        LOCK_UNAVAILABLE,
        OPPORTUNITY_TRANSITION_INVALID,
        REVALIDATION_REQUIRED,
        AFFILIATE_LINK_NOT_PRODUCTIVE,
        AFFILIATE_LINK_OPPORTUNITY_NOT_LINKABLE,
        TRACKING_MAPPING_NOT_CONFIGURED,
    ):
        return 409
    if error_code in (
        AI_REVIEW_INPUT_INVALID,
        ALLOWED_CLAIMS_INPUT_INVALID,
        CAPTURE_PAYLOAD_INVALID,
        CAPTURE_SENSITIVE_FIELD,
        CLASSIFICATION_INPUT_INVALID,
        DEMAND_INPUT_INVALID,
        EVALUATION_INPUT_INVALID,
        JOB_INPUT_INVALID,
        OPERATIONS_INPUT_INVALID,
        AUTOMATION_POLICY_INVALID,
        COMPLIANCE_POLICY_INVALID,
        OPPORTUNITY_INPUT_INVALID,
        PRICE_OPPORTUNITY_INPUT_INVALID,
        PURCHASE_SOURCE_INPUT_INVALID,
        RECOVERY_INPUT_INVALID,
        REPOST_INPUT_INVALID,
        SCHEDULE_INPUT_INVALID,
        SELLER_QUALITY_INPUT_INVALID,
        TAXONOMY_VERSION_MISMATCH,
        WORKFLOW_POLICY_INVALID,
        AFFILIATE_LINK_INPUT_INVALID,
        AFFILIATE_LINK_URL_INVALID,
        TRACKING_LABEL_INVALID,
        TRACKING_LABELS_INVALID,
    ):
        return 422
    return 500


def _error_response(request: Request, error: RadarError, *, status_code: int) -> JSONResponse:
    correlation_id = resolve_correlation_id(request)
    return JSONResponse(
        status_code=status_code,
        content={
            "schema_version": CAPTURE_SCHEMA_VERSION,
            "status": "INVALID",
            "correlation_id": correlation_id,
            "error": error.to_contract(),
        },
        headers={CORRELATION_HEADER: correlation_id, "Cache-Control": "no-store"},
    )


#: Job/lock/human-action paths whose validation failures use the Workflow code.
_JOB_PATH_PREFIXES = ("/jobs", "/locks", "/human-actions")

#: Scheduler paths whose validation failures use the Schedule Workflow code.
_SCHEDULE_PATH_PREFIXES = ("/schedules",)

#: Opportunity paths (including ``/candidates/{id}/opportunities``) use their code.
_OPPORTUNITY_PATH_PREFIXES = ("/opportunities",)

#: Operational control paths use the operations input code.
_OPERATIONS_PATH_PREFIXES = ("/operations", "/integrations")

#: Recovery paths use the recovery input code.
_RECOVERY_PATH_PREFIXES = ("/recovery",)

#: AI review paths (including ``/candidates/{id}/ai-review``) use their code.
_AI_REVIEW_PATH_PREFIXES = ("/ai-reviews",)
_AI_REVIEW_PATH_SUFFIXES = ("/ai-review", "/ai-reviews")

#: Affiliate link paths (including ``/candidates/{id}/affiliate-link``) use their code.
_AFFILIATE_LINK_PATH_PREFIXES = ("/affiliate-links",)
_AFFILIATE_LINK_PATH_SUFFIXES = ("/affiliate-link", "/affiliate-links")


def _is_job_path(request: Request) -> bool:
    return request.url.path.startswith(_JOB_PATH_PREFIXES)


def _is_schedule_path(request: Request) -> bool:
    return request.url.path.startswith(_SCHEDULE_PATH_PREFIXES)


def _is_opportunity_path(request: Request) -> bool:
    path = request.url.path
    return path.startswith(_OPPORTUNITY_PATH_PREFIXES) or path.endswith("/opportunities")


def _is_operations_path(request: Request) -> bool:
    return request.url.path.startswith(_OPERATIONS_PATH_PREFIXES)


def _is_recovery_path(request: Request) -> bool:
    return request.url.path.startswith(_RECOVERY_PATH_PREFIXES)


def _is_ai_review_path(request: Request) -> bool:
    path = request.url.path
    return path.startswith(_AI_REVIEW_PATH_PREFIXES) or path.endswith(_AI_REVIEW_PATH_SUFFIXES)


def _is_affiliate_link_path(request: Request) -> bool:
    path = request.url.path
    return path.startswith(_AFFILIATE_LINK_PATH_PREFIXES) or path.endswith(
        _AFFILIATE_LINK_PATH_SUFFIXES
    )


def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = exc.errors()
    sensitive = [item for item in errors if item.get("type") == SENSITIVE_FIELD_ERROR_TYPE]
    schedule_path = _is_schedule_path(request)
    job_path = _is_job_path(request)
    opportunity_path = _is_opportunity_path(request)
    operations_path = _is_operations_path(request)
    recovery_path = _is_recovery_path(request)
    ai_review_path = _is_ai_review_path(request)
    affiliate_link_path = _is_affiliate_link_path(request)
    workflow_path = (
        schedule_path
        or job_path
        or opportunity_path
        or operations_path
        or recovery_path
        or ai_review_path
        or affiliate_link_path
    )
    if affiliate_link_path:
        workflow_code = AFFILIATE_LINK_INPUT_INVALID
        workflow_label = "affiliate link"
    elif ai_review_path:
        workflow_code = AI_REVIEW_INPUT_INVALID
        workflow_label = "AI review"
    elif operations_path:
        workflow_code = OPERATIONS_INPUT_INVALID
        workflow_label = "operations"
    elif recovery_path:
        workflow_code = RECOVERY_INPUT_INVALID
        workflow_label = "recovery"
    elif opportunity_path:
        workflow_code = OPPORTUNITY_INPUT_INVALID
        workflow_label = "Opportunity"
    elif schedule_path:
        workflow_code = SCHEDULE_INPUT_INVALID
        workflow_label = "schedule"
    else:
        workflow_code = JOB_INPUT_INVALID
        workflow_label = "job"
    if sensitive:
        fields: list[str] = []
        for item in sensitive:
            context = item.get("ctx") or {}
            fields.extend(str(name) for name in context.get("fields", []))
        error = RadarError(
            code=workflow_code if workflow_path else CAPTURE_SENSITIVE_FIELD,
            message=(
                f"Payload de {workflow_label} contém campos sensíveis não permitidos"
                if workflow_path
                else "Payload contém campos sensíveis não permitidos"
            ),
            retryable=False,
            action=(
                f"Remover os campos sensíveis e reenviar o {workflow_label}"
                if workflow_path
                else "Remover os campos sensíveis e reenviar a captura"
            ),
            context={"fields": sorted(set(fields))},
        )
    else:
        fields = [".".join(str(part) for part in item.get("loc", ())) for item in errors]
        error = RadarError(
            code=workflow_code if workflow_path else CAPTURE_PAYLOAD_INVALID,
            message=(
                f"Payload de {workflow_label} inválido"
                if workflow_path
                else "Payload de captura inválido"
            ),
            retryable=False,
            action=(
                f"Corrigir o payload do {workflow_label} e enviar novamente"
                if workflow_path
                else "Corrigir o payload da captura e enviar novamente"
            ),
            context={"fields": fields},
        )
    return _error_response(request, error, status_code=422)


def register_capture_error_handlers(app: FastAPI) -> None:
    """Expose capture validation failures as one structured error contract."""

    @app.exception_handler(RequestValidationError)
    def _handle_validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        return _validation_error(request, exc)

    @app.exception_handler(RadarException)
    def _handle_radar_exception(request: Request, exc: RadarException) -> JSONResponse:
        return _error_response(request, exc.error, status_code=_error_status(exc.error.code))


def build_capture_router(engine: Engine) -> APIRouter:
    """Build the capture router wired to the SQLite repository."""

    router = APIRouter(tags=["capture"])
    service = ManualCaptureService(repository=SqlAlchemyCaptureRepository(engine=engine))

    @router.post("/captures/manual", status_code=201)
    def create_manual_capture(payload: ManualCaptureContract, request: Request) -> JSONResponse:
        correlation_id = bind_correlation_id(resolve_correlation_id(request))
        result = service.capture(payload.to_intake(), correlation_id=correlation_id)
        return JSONResponse(
            status_code=201,
            content={"status": "CAPTURED", **result.to_contract()},
            headers={CORRELATION_HEADER: correlation_id, "Cache-Control": "no-store"},
        )

    @router.get("/candidates/{candidate_id}")
    def get_candidate(candidate_id: str, request: Request) -> JSONResponse:
        correlation_id = bind_correlation_id(resolve_correlation_id(request))
        result = service.get_candidate(candidate_id)
        return JSONResponse(
            status_code=200,
            content={"status": "OK", **result.to_contract()},
            headers={CORRELATION_HEADER: correlation_id, "Cache-Control": "no-store"},
        )

    @router.get("/marketplace-products/{marketplace_product_id}/price-history")
    def get_price_history(marketplace_product_id: str, request: Request) -> JSONResponse:
        correlation_id = bind_correlation_id(resolve_correlation_id(request))
        history = service.get_price_history(marketplace_product_id)
        return JSONResponse(
            status_code=200,
            content=history.to_contract(correlation_id=correlation_id),
            headers={CORRELATION_HEADER: correlation_id, "Cache-Control": "no-store"},
        )

    return router


__all__ = [
    "build_capture_router",
    "register_capture_error_handlers",
    "resolve_correlation_id",
]
