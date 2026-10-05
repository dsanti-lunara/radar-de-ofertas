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
from radar.domain.price_opportunity import PRICE_OPPORTUNITY_INPUT_INVALID
from radar.domain.seller_quality import SELLER_QUALITY_INPUT_INVALID
from radar.domain.taxonomy import (
    CLASSIFICATION_INPUT_INVALID,
    TAXONOMY_VERSION_MISMATCH,
)
from radar.infrastructure.capture_repository import SqlAlchemyCaptureRepository


def resolve_correlation_id(request: Request) -> str:
    """Use the caller's Correlation ID or generate one when absent."""

    return request.headers.get(CORRELATION_HEADER) or new_correlation_id()


def _error_status(error_code: str) -> int:
    if error_code in (CANDIDATE_NOT_FOUND, MARKETPLACE_PRODUCT_NOT_FOUND):
        return 404
    if error_code == CAPTURE_IDENTITY_CONFLICT:
        return 409
    if error_code in (
        CAPTURE_PAYLOAD_INVALID,
        CAPTURE_SENSITIVE_FIELD,
        CLASSIFICATION_INPUT_INVALID,
        DEMAND_INPUT_INVALID,
        PRICE_OPPORTUNITY_INPUT_INVALID,
        SELLER_QUALITY_INPUT_INVALID,
        TAXONOMY_VERSION_MISMATCH,
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


def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = exc.errors()
    sensitive = [item for item in errors if item.get("type") == SENSITIVE_FIELD_ERROR_TYPE]
    if sensitive:
        fields: list[str] = []
        for item in sensitive:
            context = item.get("ctx") or {}
            fields.extend(str(name) for name in context.get("fields", []))
        error = RadarError(
            code=CAPTURE_SENSITIVE_FIELD,
            message="Payload contém campos sensíveis não permitidos",
            retryable=False,
            action="Remover os campos sensíveis e reenviar a captura",
            context={"fields": sorted(set(fields))},
        )
    else:
        fields = [".".join(str(part) for part in item.get("loc", ())) for item in errors]
        error = RadarError(
            code=CAPTURE_PAYLOAD_INVALID,
            message="Payload de captura inválido",
            retryable=False,
            action="Corrigir o payload da captura e enviar novamente",
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
