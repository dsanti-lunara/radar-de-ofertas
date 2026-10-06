"""Workflow Engine orchestration: Candidate -> Opportunity and transitions.

The service drives the deterministic plan from :mod:`radar.domain.workflow`
against the persisted Candidate/Evaluation and a :class:`WorkflowStore` port. It
implements the objective of TKT-16 (RDR-017, RDR-041):

* an Opportunity is only created when the latest immutable Evaluation decided
  ``APPROVE`` (AUT-032); ``REJECT`` never advances and ``REVIEW`` creates an
  explicit ``REVIEW_CANDIDATE`` HumanAction without touching the old Evaluation
  (AUT-126, AUT-147);
* the engine -- not a worker -- creates the next Job
  (``GENERATE_AFFILIATE_LINK``) in the same transaction that persists the
  Opportunity, so a worker never calls another worker (AUT-119, AUT-120);
* an invalid transition is rejected and audited; an aged Candidate/Opportunity
  raises ``RAD-WF-005`` before the dependent step (AUT-135, AUT-144).

The service is framework-free (no FastAPI/SQLAlchemy/Chrome) and never calls AI
(AUT-397, AUT-031).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from radar.domain.allowed_claims import evaluation_not_found_error
from radar.domain.audit import (
    HUMAN_ACTION_CREATED,
    JOB_ENQUEUED,
    OPPORTUNITY_CREATED,
    OPPORTUNITY_TRANSITION_REJECTED,
    OPPORTUNITY_TRANSITIONED,
    WORKFLOW_NEXT_JOB_ENQUEUED,
    AuditEvent,
)
from radar.domain.capture import (
    CandidateState,
    IdFactory,
    candidate_not_found_error,
    default_id_factory,
)
from radar.domain.evaluation import Evaluation
from radar.domain.human_action import HumanAction, HumanActionType, build_human_action
from radar.domain.job import Job, create_job
from radar.domain.opportunity import (
    Opportunity,
    OpportunityError,
    OpportunityState,
    coerce_opportunity_state,
    create_opportunity,
    opportunity_not_found_error,
    transition_opportunity,
)
from radar.domain.workflow import (
    APPROVED_WORKFLOW_POLICY,
    CANDIDATE_REVIEW_REQUIRED,
    WARNING_TTL_NOT_CONFIGURED,
    WorkflowOutcome,
    WorkflowPlan,
    WorkflowPolicy,
    plan_advance,
    revalidation_required_error,
)

#: Opportunity states that consume link/content/publish and therefore require
#: revalidation when the Opportunity TTL is configured (AUT-135).
_REVALIDATION_GATED_TARGETS: frozenset[OpportunityState] = frozenset(
    {
        OpportunityState.LINK_PENDING,
        OpportunityState.LINK_READY,
        OpportunityState.CONTENT_PENDING,
        OpportunityState.READY_TO_PUBLISH,
        OpportunityState.PUBLISHED,
    }
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _utc(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)


class EvaluationStore(Protocol):
    """Read port for the immutable Evaluations of a Candidate."""

    def list_evaluations(self, candidate_id: str) -> tuple[Evaluation, ...]: ...


class WorkflowStore(Protocol):
    """Persistence port for Opportunities and their workflow transitions."""

    def get_candidate_state(self, candidate_id: str) -> CandidateState | None: ...

    def find_opportunity_for_evaluation(self, evaluation_id: str) -> Opportunity | None: ...

    def get_opportunity(self, opportunity_id: str) -> Opportunity | None: ...

    def list_opportunities(self, candidate_id: str | None = None) -> list[Opportunity]: ...

    def list_opportunity_events(self, opportunity_id: str) -> list[AuditEvent]: ...

    def commit_advance(
        self,
        opportunity: Opportunity,
        next_job: Job,
        audit_events: tuple[AuditEvent, ...],
    ) -> Opportunity: ...

    def save_review(
        self, human_action: HumanAction, audit_events: tuple[AuditEvent, ...]
    ) -> None: ...

    def commit_transition(
        self,
        opportunity: Opportunity,
        *,
        previous_state: OpportunityState,
        audit_events: tuple[AuditEvent, ...],
    ) -> Opportunity: ...

    def record_rejected_transition(self, audit_event: AuditEvent) -> None: ...


@dataclass(frozen=True, slots=True)
class OpportunityAdvanceResult:
    """Observable outcome of advancing a Candidate through the engine."""

    status: str
    candidate_id: str
    evaluation_id: str | None
    decision: str | None
    brand: str | None
    priority: int
    plan: WorkflowPlan
    correlation_id: str
    opportunity: Opportunity | None = None
    next_job: Job | None = None
    human_action: HumanAction | None = None
    warnings: tuple[dict[str, Any], ...] = field(default_factory=tuple)

    def to_contract(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "status": self.status,
            "candidate_id": self.candidate_id,
            "evaluation_id": self.evaluation_id,
            "decision": self.decision,
            "brand": self.brand,
            "priority": self.priority,
            "plan": self.plan.to_contract(),
            "opportunity": None if self.opportunity is None else self.opportunity.to_contract(),
            "next_job": None if self.next_job is None else self.next_job.to_contract(),
            "human_action": None if self.human_action is None else self.human_action.to_contract(),
            "warnings": [dict(warning) for warning in self.warnings],
            "correlation_id": self.correlation_id,
        }


@dataclass(slots=True)
class WorkflowService:
    """Advance approved Candidates and drive Opportunity transitions."""

    store: WorkflowStore
    evaluation_store: EvaluationStore
    policy: WorkflowPolicy = APPROVED_WORKFLOW_POLICY
    clock: Callable[[], datetime] = _utcnow
    id_factory: IdFactory = default_id_factory

    def advance(
        self,
        candidate_id: str,
        *,
        correlation_id: str,
        priority: int = 0,
    ) -> OpportunityAdvanceResult:
        """Plan and execute the next workflow step for a Candidate (RDR-041)."""

        candidate_state = self.store.get_candidate_state(candidate_id)
        if candidate_state is None:
            raise candidate_not_found_error(candidate_id)
        evaluations = self.evaluation_store.list_evaluations(candidate_id)
        if not evaluations:
            raise evaluation_not_found_error(candidate_id)

        latest = evaluations[-1]
        now = self.clock()
        plan = plan_advance(
            candidate_state=candidate_state,
            evaluation=latest,
            now=now,
            policy=self.policy,
        )
        warnings = self._warnings(plan)

        if plan.outcome is WorkflowOutcome.REJECTED:
            return self._result(
                status="REJECTED",
                candidate_id=candidate_id,
                evaluation=latest,
                plan=plan,
                priority=priority,
                correlation_id=correlation_id,
                warnings=warnings,
            )
        if plan.outcome is WorkflowOutcome.REVIEW_REQUIRED:
            human_action = self._create_review_action(
                candidate_id=candidate_id, correlation_id=correlation_id, now=now
            )
            return self._result(
                status="REVIEW_REQUIRED",
                candidate_id=candidate_id,
                evaluation=latest,
                plan=plan,
                priority=priority,
                correlation_id=correlation_id,
                human_action=human_action,
                warnings=warnings,
            )
        return self._create_opportunity(
            candidate_id=candidate_id,
            evaluation=latest,
            plan=plan,
            priority=priority,
            correlation_id=correlation_id,
            now=now,
            warnings=warnings,
        )

    def get(self, opportunity_id: str) -> tuple[Opportunity, tuple[AuditEvent, ...]]:
        """Return an Opportunity and its append-only audit trail."""

        opportunity = self.store.get_opportunity(opportunity_id)
        if opportunity is None:
            raise opportunity_not_found_error(opportunity_id)
        return opportunity, tuple(self.store.list_opportunity_events(opportunity_id))

    def list(self, candidate_id: str | None = None) -> list[Opportunity]:
        """Return persisted Opportunities, optionally for one Candidate."""

        return self.store.list_opportunities(candidate_id)

    def transition(
        self,
        opportunity_id: str,
        *,
        target_state: object,
        correlation_id: str,
    ) -> Opportunity:
        """Apply an explicit, audited Opportunity transition (RDR-041).

        An unknown/illegal transition is recorded in ``audit_event`` and then
        rejected with ``RAD-WF-015``; an aged Opportunity is rejected with
        ``RAD-WF-005`` before the link/content/publish step.
        """

        opportunity = self.store.get_opportunity(opportunity_id)
        if opportunity is None:
            raise opportunity_not_found_error(opportunity_id)
        now = self.clock()
        resolved_target = coerce_opportunity_state(target_state)

        if resolved_target in _REVALIDATION_GATED_TARGETS and self.policy.opportunity_is_aged(
            created_at=opportunity.created_at, now=now
        ):
            age_seconds = int((_utc(now) - _utc(opportunity.created_at)).total_seconds())
            raise revalidation_required_error(
                entity_type="opportunity",
                entity_id=opportunity.opportunity_id,
                age_seconds=age_seconds,
                ttl_seconds=self.policy.opportunity_ttl_seconds or 0,
            )

        try:
            transitioned = transition_opportunity(opportunity, target=resolved_target, now=now)
        except OpportunityError as exc:
            self.store.record_rejected_transition(
                self._audit_event(
                    event_type=OPPORTUNITY_TRANSITION_REJECTED,
                    entity_type="opportunity",
                    entity_id=opportunity.opportunity_id,
                    correlation_id=correlation_id,
                    now=now,
                    payload={
                        "current_state": opportunity.state.value,
                        "target_state": resolved_target.value,
                        "reason": exc.error.code,
                    },
                )
            )
            raise

        return self.store.commit_transition(
            transitioned,
            previous_state=opportunity.state,
            audit_events=(
                self._audit_event(
                    event_type=OPPORTUNITY_TRANSITIONED,
                    entity_type="opportunity",
                    entity_id=transitioned.opportunity_id,
                    correlation_id=correlation_id,
                    now=now,
                    payload={
                        "previous_state": opportunity.state.value,
                        "state": transitioned.state.value,
                    },
                ),
            ),
        )

    # -- internals ----------------------------------------------------------

    def _create_opportunity(
        self,
        *,
        candidate_id: str,
        evaluation: Evaluation,
        plan: WorkflowPlan,
        priority: int,
        correlation_id: str,
        now: datetime,
        warnings: tuple[dict[str, Any], ...],
    ) -> OpportunityAdvanceResult:
        existing = self.store.find_opportunity_for_evaluation(evaluation.evaluation_id)
        if existing is not None:
            return self._result(
                status="OPPORTUNITY_EXISTS",
                candidate_id=candidate_id,
                evaluation=evaluation,
                plan=plan,
                priority=priority,
                correlation_id=correlation_id,
                opportunity=existing,
                warnings=warnings,
            )

        assert plan.next_state is not None
        assert plan.next_job_type is not None
        opportunity_id = str(self.id_factory("opp"))
        creation_audit_id = str(self.id_factory("aud"))
        opportunity = create_opportunity(
            candidate_id=candidate_id,
            evaluation_id=evaluation.evaluation_id,
            brand=evaluation.brand,
            correlation_id=correlation_id,
            now=now,
            audit_event_id=creation_audit_id,
            priority=priority,
            opportunity_id=opportunity_id,
            id_factory=self.id_factory,
        )
        transitioned = transition_opportunity(opportunity, target=plan.next_state, now=now)

        next_job = create_job(
            job_type=plan.next_job_type,
            correlation_id=correlation_id,
            now=now,
            payload={
                "candidate_id": candidate_id,
                "evaluation_id": evaluation.evaluation_id,
            },
            priority=priority,
            entity_type="opportunity",
            entity_id=opportunity_id,
            id_factory=self.id_factory,
        )
        audit_events = (
            AuditEvent(
                id=creation_audit_id,
                event_type=OPPORTUNITY_CREATED,
                entity_type="opportunity",
                entity_id=opportunity_id,
                source="workflow",
                correlation_id=correlation_id,
                recorded_at=now,
                payload={
                    "candidate_id": candidate_id,
                    "evaluation_id": evaluation.evaluation_id,
                    "brand": evaluation.brand.value,
                    "state": opportunity.state.value,
                    "priority": priority,
                },
            ),
            self._audit_event(
                event_type=OPPORTUNITY_TRANSITIONED,
                entity_type="opportunity",
                entity_id=opportunity_id,
                correlation_id=correlation_id,
                now=now,
                payload={
                    "previous_state": opportunity.state.value,
                    "state": transitioned.state.value,
                    "reason": plan.reason,
                },
            ),
            self._audit_event(
                event_type=JOB_ENQUEUED,
                entity_type="job",
                entity_id=next_job.id,
                correlation_id=correlation_id,
                now=now,
                payload={
                    "type": next_job.type.value,
                    "priority": next_job.priority,
                    "status": next_job.status.value,
                    "attempts": next_job.attempts,
                },
            ),
            self._audit_event(
                event_type=WORKFLOW_NEXT_JOB_ENQUEUED,
                entity_type="opportunity",
                entity_id=opportunity_id,
                correlation_id=correlation_id,
                now=now,
                payload={"job_id": next_job.id, "job_type": next_job.type.value},
            ),
        )
        committed = self.store.commit_advance(transitioned, next_job, audit_events)
        race_lost = committed.opportunity_id != transitioned.opportunity_id
        return self._result(
            status="OPPORTUNITY_EXISTS" if race_lost else "OPPORTUNITY_CREATED",
            candidate_id=candidate_id,
            evaluation=evaluation,
            plan=plan,
            priority=priority,
            correlation_id=correlation_id,
            opportunity=committed,
            next_job=None if race_lost else next_job,
            warnings=warnings,
        )

    def _create_review_action(
        self, *, candidate_id: str, correlation_id: str, now: datetime
    ) -> HumanAction:
        human_action = build_human_action(
            action_type=HumanActionType.REVIEW_CANDIDATE,
            entity_type="candidate",
            entity_id=candidate_id,
            reason="CANDIDATE_REVIEW_REQUIRED",
            error_code=CANDIDATE_REVIEW_REQUIRED,
            correlation_id=correlation_id,
            now=now,
            id_factory=self.id_factory,
        )
        self.store.save_review(
            human_action,
            (
                self._audit_event(
                    event_type=HUMAN_ACTION_CREATED,
                    entity_type="human_action",
                    entity_id=human_action.id,
                    correlation_id=correlation_id,
                    now=now,
                    payload={
                        "action_type": human_action.action_type.value,
                        "reason": human_action.reason,
                        "entity_type": human_action.entity_type,
                        "entity_id": human_action.entity_id,
                    },
                ),
            ),
        )
        return human_action

    def _result(
        self,
        *,
        status: str,
        candidate_id: str,
        evaluation: Evaluation,
        plan: WorkflowPlan,
        priority: int,
        correlation_id: str,
        opportunity: Opportunity | None = None,
        next_job: Job | None = None,
        human_action: HumanAction | None = None,
        warnings: tuple[dict[str, Any], ...] = (),
    ) -> OpportunityAdvanceResult:
        return OpportunityAdvanceResult(
            status=status,
            candidate_id=candidate_id,
            evaluation_id=evaluation.evaluation_id,
            decision=evaluation.decision.value,
            brand=evaluation.brand.value,
            priority=priority,
            plan=plan,
            correlation_id=correlation_id,
            opportunity=opportunity,
            next_job=next_job,
            human_action=human_action,
            warnings=warnings,
        )

    def _warnings(self, plan: WorkflowPlan) -> tuple[dict[str, Any], ...]:
        if plan.ttl_configured:
            return ()
        return (
            {
                "code": WARNING_TTL_NOT_CONFIGURED,
                "message": (
                    "TTL de Candidate não configurado; o gate de aging/revalidação "
                    "permanece desligado até uma policy versionada"
                ),
            },
        )

    def _audit_event(
        self,
        *,
        event_type: str,
        entity_type: str,
        entity_id: str,
        correlation_id: str,
        now: datetime,
        payload: dict[str, Any],
    ) -> AuditEvent:
        return AuditEvent(
            id=str(self.id_factory("aud")),
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            source="workflow",
            correlation_id=correlation_id,
            recorded_at=now,
            payload=payload,
        )


__all__ = [
    "EvaluationStore",
    "OpportunityAdvanceResult",
    "WorkflowService",
    "WorkflowStore",
]
