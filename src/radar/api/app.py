"""Control Center API (RDR-010 / SPEC-01).

The health/version/config boundary, the manual capture boundary and the Home
health overview read model exist at this stage; the rest of the UI arrives in its
own tickets. Health reports fail closed: an unhealthy dependency yields HTTP 503
while the body keeps the structured contract, whereas ``GET /health/overview``
answers 200 with per-capability states for the Home strip. Invalid configuration
blocks app creation before serving. Capture validation failures return the
structured error contract with the Correlation ID. The compiled Control Center is
served locally when a build exists, without becoming a prerequisite for the Core.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.engine import Engine

from radar import __version__
from radar.api.affiliate_links import build_affiliate_link_router
from radar.api.ai_review import build_ai_review_router
from radar.api.allowed_claims import build_allowed_claims_router
from radar.api.captures import build_capture_router, register_capture_error_handlers
from radar.api.classification import build_classification_router
from radar.api.content_generations import build_content_generation_router
from radar.api.contracts import CORRELATION_HEADER
from radar.api.demand import build_demand_router
from radar.api.evaluation import build_evaluation_router
from radar.api.home_health import build_home_health_router
from radar.api.human_actions import build_human_action_router
from radar.api.jobs import build_job_router
from radar.api.operations import build_operations_router
from radar.api.opportunities import build_opportunity_router
from radar.api.price_opportunity import build_price_opportunity_router
from radar.api.publications import build_publication_router
from radar.api.purchase_source import build_purchase_source_router
from radar.api.recovery import build_recovery_router
from radar.api.repost import build_repost_router
from radar.api.reviews import build_review_router
from radar.api.schedules import build_schedule_router
from radar.api.seller_quality import build_seller_quality_router
from radar.api.settings import build_settings_router
from radar.application.correlation import new_correlation_id
from radar.bootstrap import build_health_service
from radar.domain.affiliate_link import AffiliateLinkProvider
from radar.domain.ai_review import AIProvider
from radar.domain.config import RadarConfig
from radar.domain.content import ContentProvider
from radar.domain.demand import DemandNormalization
from radar.domain.knowledge import KnowledgePack
from radar.domain.operations import AutomationPolicy, ChannelCompliancePolicy
from radar.domain.publication import PublicationPolicy, Publisher
from radar.domain.purchase_source import PurchaseSourcePolicy
from radar.domain.repost import RepostPolicy
from radar.domain.retry import RetryPolicy
from radar.domain.seller_quality import SellerQualityNormalization
from radar.domain.taxonomy import BrandTaxonomy
from radar.domain.tracking import TrackingLabelMapping
from radar.domain.workflow import WorkflowPolicy
from radar.infrastructure.affiliate_link_provider import FakeAffiliateLinkProvider
from radar.infrastructure.ai_provider import FakeAIProvider
from radar.infrastructure.automation_policy import AutomationPolicyLoader
from radar.infrastructure.compliance_policy import CompliancePolicyLoader
from radar.infrastructure.config import ConfigLoader
from radar.infrastructure.database import create_database_engine
from radar.infrastructure.demand import DemandLoader
from radar.infrastructure.knowledge import KnowledgePackLoader
from radar.infrastructure.publication_policy import PublicationPolicyLoader
from radar.infrastructure.publication_publisher import FakePublisher
from radar.infrastructure.purchase_source import PurchaseSourcePolicyLoader
from radar.infrastructure.repost import RepostPolicyLoader
from radar.infrastructure.retry import RetryPolicyLoader
from radar.infrastructure.seller_quality import SellerQualityLoader
from radar.infrastructure.settings import Settings
from radar.infrastructure.taxonomy import TaxonomyLoader
from radar.infrastructure.tracking_labels import TrackingLabelMappingLoader
from radar.infrastructure.workflow_policy import WorkflowPolicyLoader

#: Environment variable that overrides the Control Center build directory.
CONTROL_CENTER_DIST_ENV = "RADAR_CONTROL_CENTER_DIST"

#: Default Control Center build directory (relative to the repository root).
_DEFAULT_CONTROL_CENTER_DIST = Path("packages") / "control-center" / "dist"


def resolve_control_center_dist(override: Path | str | None = None) -> Path:
    """Resolve the directory that holds the compiled Control Center assets.

    Precedence: explicit ``override`` (used by tests) > ``RADAR_CONTROL_CENTER_DIST``
    > the repository default ``packages/control-center/dist``.
    """

    if override is not None:
        return Path(override)
    configured = os.environ.get(CONTROL_CENTER_DIST_ENV)
    if configured:
        return Path(configured)
    repository_root = Path(__file__).resolve().parents[3]
    return repository_root / _DEFAULT_CONTROL_CENTER_DIST


def mount_control_center(app: FastAPI, dist: Path | str | None = None) -> bool:
    """Serve the compiled Control Center locally when it exists (AUT-401).

    The mount is additive and fail-open for the Core: a missing build directory
    (or a missing ``index.html``) leaves the API untouched, so the UI is never a
    prerequisite for the Core to run. ``StaticFiles`` refuses directory listings
    and path traversal by default and is mounted on ``127.0.0.1`` only, so no
    public exposure is introduced (AUT-399, AUT-402).
    """

    directory = resolve_control_center_dist(dist)
    if not (directory / "index.html").is_file():
        return False
    app.mount("/", StaticFiles(directory=str(directory), html=True), name="control-center")
    return True


def create_app(
    settings: Settings | None = None,
    engine: Engine | None = None,
    config: RadarConfig | None = None,
    taxonomy: BrandTaxonomy | None = None,
    seller_quality: SellerQualityNormalization | None = None,
    demand: DemandNormalization | None = None,
    purchase_source_policy: PurchaseSourcePolicy | None = None,
    repost_policy: RepostPolicy | None = None,
    retry_policy: RetryPolicy | None = None,
    workflow_policy: WorkflowPolicy | None = None,
    automation_policy: AutomationPolicy | None = None,
    compliance_policy: ChannelCompliancePolicy | None = None,
    knowledge_pack: KnowledgePack | None = None,
    ai_provider: AIProvider | None = None,
    content_provider: ContentProvider | None = None,
    tracking_labels: TrackingLabelMapping | None = None,
    affiliate_link_provider: AffiliateLinkProvider | None = None,
    publication_policy: PublicationPolicy | None = None,
    publisher: Publisher | None = None,
    control_center_dist: Path | str | None = None,
) -> FastAPI:
    # Invalid configuration raises ConfigInvalidError, so the API never serves
    # with a config that failed schema validation (RDR-004). The taxonomy is
    # loaded the same way: an invalid taxonomy file blocks app creation instead
    # of serving an uncalibrated Brand Fit. Seller Quality, Demand and the
    # Purchase Source policy follow the same fail-closed contract
    # (RDR-024, RDR-025, RDR-031).
    resolved_config = config or ConfigLoader.from_env().load()
    resolved_settings = settings or Settings(
        database_url=resolved_config.database_url,
        log_level=resolved_config.log_level,
    )
    resolved_engine = engine or create_database_engine(resolved_settings.database_url)
    resolved_taxonomy = taxonomy or TaxonomyLoader.from_env().load()
    resolved_seller_quality = seller_quality or SellerQualityLoader.from_env().load()
    resolved_demand = demand or DemandLoader.from_env().load()
    resolved_purchase_source = (
        purchase_source_policy or PurchaseSourcePolicyLoader.from_env().load()
    )
    resolved_repost = repost_policy or RepostPolicyLoader.from_env().load()
    resolved_retry = retry_policy or RetryPolicyLoader.from_env().load()
    resolved_workflow = workflow_policy or WorkflowPolicyLoader.from_env().load()
    resolved_automation = automation_policy or AutomationPolicyLoader.from_env().load()
    resolved_compliance = compliance_policy or CompliancePolicyLoader.from_env().load()
    resolved_knowledge = knowledge_pack or KnowledgePackLoader.from_env().load()
    resolved_provider = ai_provider or FakeAIProvider()
    resolved_content_provider = content_provider or FakeAIProvider()
    resolved_tracking = tracking_labels or TrackingLabelMappingLoader.from_env().load()
    resolved_link_provider = affiliate_link_provider or FakeAffiliateLinkProvider()
    resolved_publication_policy = publication_policy or PublicationPolicyLoader.from_env().load()
    resolved_publisher = publisher or FakePublisher()
    health_service = build_health_service(resolved_settings, resolved_engine)

    app = FastAPI(title="Radar Engine API", version=__version__)
    app.state.settings = resolved_settings
    app.state.engine = resolved_engine
    app.state.config = resolved_config
    app.state.taxonomy = resolved_taxonomy
    app.state.seller_quality = resolved_seller_quality
    app.state.demand = resolved_demand
    app.state.purchase_source_policy = resolved_purchase_source
    app.state.repost_policy = resolved_repost
    app.state.retry_policy = resolved_retry
    app.state.workflow_policy = resolved_workflow
    app.state.automation_policy = resolved_automation
    app.state.compliance_policy = resolved_compliance
    app.state.knowledge_pack = resolved_knowledge
    app.state.ai_provider = resolved_provider
    app.state.content_provider = resolved_content_provider
    app.state.tracking_labels = resolved_tracking
    app.state.affiliate_link_provider = resolved_link_provider
    app.state.publication_policy = resolved_publication_policy
    app.state.publisher = resolved_publisher

    register_capture_error_handlers(app)
    app.include_router(build_capture_router(resolved_engine))
    app.include_router(build_classification_router(resolved_engine, resolved_taxonomy))
    app.include_router(build_price_opportunity_router(resolved_engine))
    app.include_router(build_seller_quality_router(resolved_engine, resolved_seller_quality))
    app.include_router(build_demand_router(resolved_engine, resolved_taxonomy, resolved_demand))
    app.include_router(build_evaluation_router(resolved_engine, resolved_taxonomy))
    app.include_router(build_purchase_source_router(resolved_engine, resolved_purchase_source))
    app.include_router(build_allowed_claims_router(resolved_engine))
    app.include_router(build_repost_router(resolved_engine, resolved_repost))
    app.include_router(build_job_router(resolved_engine, resolved_retry))
    app.include_router(build_schedule_router(resolved_engine))
    app.include_router(build_human_action_router(resolved_engine))
    app.include_router(build_opportunity_router(resolved_engine, resolved_workflow))
    app.include_router(
        build_operations_router(resolved_engine, resolved_automation, resolved_compliance)
    )
    app.include_router(
        build_settings_router(
            resolved_engine,
            resolved_automation,
            resolved_compliance,
            resolved_publication_policy,
        )
    )
    app.include_router(
        build_review_router(resolved_engine, resolved_automation, resolved_compliance)
    )
    app.include_router(build_recovery_router(resolved_engine))
    app.include_router(
        build_ai_review_router(resolved_engine, resolved_knowledge, resolved_provider)
    )
    app.include_router(
        build_affiliate_link_router(resolved_engine, resolved_tracking, resolved_link_provider)
    )
    app.include_router(
        build_content_generation_router(
            resolved_engine, resolved_knowledge, resolved_content_provider, resolved_compliance
        )
    )
    app.include_router(
        build_publication_router(
            resolved_engine,
            resolved_knowledge,
            resolved_content_provider,
            resolved_compliance,
            resolved_publication_policy,
            resolved_publisher,
            resolved_automation,
        )
    )
    app.include_router(build_home_health_router(resolved_engine, health_service))

    @app.get("/version")
    def version() -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "app_version": resolved_settings.app_version,
            "api_version": __version__,
        }

    @app.get("/config")
    def config_endpoint(request: Request) -> JSONResponse:
        correlation_id = request.headers.get(CORRELATION_HEADER) or new_correlation_id()
        payload = {
            "status": "VALID",
            "correlation_id": correlation_id,
            **resolved_config.to_contract(),
        }
        return JSONResponse(
            content=payload,
            headers={CORRELATION_HEADER: correlation_id, "Cache-Control": "no-store"},
        )

    @app.get("/health")
    def health(request: Request) -> JSONResponse:
        report = health_service.evaluate(request.headers.get(CORRELATION_HEADER))
        status_code = 200 if report.is_operational else 503
        return JSONResponse(
            content=report.to_contract(),
            status_code=status_code,
            headers={
                CORRELATION_HEADER: report.correlation_id,
                "Cache-Control": "no-store",
            },
        )

    # Mounted last so every API route takes precedence over the static assets.
    mount_control_center(app, control_center_dist)

    return app
