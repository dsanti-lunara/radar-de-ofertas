"""SQLAlchemy persistence for Opportunities and their workflow transitions.

The Workflow Engine creates an Opportunity and the next Job in **one**
transaction, together with the audit events, so the advance is atomic and
observable (RDR-017, RDR-041). The ``uq_opportunity_evaluation`` unique constraint
makes the advance idempotent: a repeated or concurrent request for the same
immutable Evaluation can never create a second Opportunity or a duplicate next
Job. Every valid transition updates the row with an optimistic conditional
``UPDATE`` and records ``OPPORTUNITY_TRANSITIONED``; a rejected transition is
recorded append-only in ``audit_event`` before the structured error is raised, so
the refusal is auditable (AUT-010, AUT-141).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from radar.domain.audit import AuditEvent
from radar.domain.capture import CandidateState
from radar.domain.human_action import HumanAction
from radar.domain.job import Job
from radar.domain.opportunity import (
    Opportunity,
    OpportunityState,
    opportunity_transition_invalid_error,
)
from radar.domain.taxonomy import Brand
from radar.infrastructure.human_action_repository import human_action_to_row
from radar.infrastructure.job_repository import job_to_row
from radar.infrastructure.models import (
    AuditEventRow,
    CandidateRow,
    OpportunityRow,
)


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat()


def _parse(moment: str) -> datetime:
    return datetime.fromisoformat(moment)


@dataclass(slots=True)
class SqlAlchemyWorkflowRepository:
    """Persist Opportunities and their workflow transitions on SQLite."""

    engine: Engine

    # -- Reads --------------------------------------------------------------

    def get_candidate_state(self, candidate_id: str) -> CandidateState | None:
        """Return the current state of a Candidate or ``None`` when absent."""

        with Session(self.engine) as session:
            row = session.get(CandidateRow, candidate_id)
            return None if row is None else CandidateState(row.state)

    def find_opportunity_for_evaluation(self, evaluation_id: str) -> Opportunity | None:
        """Return the Opportunity created for an Evaluation, if any (idempotency)."""

        with Session(self.engine) as session:
            row = session.execute(
                select(OpportunityRow).where(OpportunityRow.evaluation_id == evaluation_id)
            ).scalar_one_or_none()
            return None if row is None else _opportunity_from_row(row)

    def get_opportunity(self, opportunity_id: str) -> Opportunity | None:
        """Return an Opportunity by id or ``None`` when it does not exist."""

        with Session(self.engine) as session:
            row = session.get(OpportunityRow, opportunity_id)
            return None if row is None else _opportunity_from_row(row)

    def list_opportunities(self, candidate_id: str | None = None) -> list[Opportunity]:
        """Return Opportunities, optionally for one Candidate, oldest first."""

        statement = select(OpportunityRow).order_by(
            OpportunityRow.created_at.asc(), OpportunityRow.id.asc()
        )
        if candidate_id is not None:
            statement = statement.where(OpportunityRow.candidate_id == candidate_id)
        with Session(self.engine) as session:
            rows = session.execute(statement).scalars().all()
        return [_opportunity_from_row(row) for row in rows]

    def list_opportunity_events(self, opportunity_id: str) -> list[AuditEvent]:
        """Return the append-only audit trail of one Opportunity, oldest first."""

        with Session(self.engine) as session:
            rows = (
                session.execute(
                    select(AuditEventRow)
                    .where(
                        AuditEventRow.entity_type == "opportunity",
                        AuditEventRow.entity_id == opportunity_id,
                    )
                    .order_by(AuditEventRow.recorded_at.asc(), AuditEventRow.id.asc())
                )
                .scalars()
                .all()
            )
        return [_audit_event_from_row(row) for row in rows]

    # -- Writes -------------------------------------------------------------

    def commit_advance(
        self,
        opportunity: Opportunity,
        next_job: Job,
        audit_events: tuple[AuditEvent, ...],
    ) -> Opportunity:
        """Persist the Opportunity, its next Job and the audit trail atomically.

        If a concurrent advance already created the Opportunity for the same
        Evaluation, the unique constraint fires and the persisted winner is
        returned, so the caller never sees a duplicate side effect (AUT-039,
        AUT-132).
        """

        try:
            with Session(self.engine) as session, session.begin():
                for event in audit_events:
                    session.add(_audit_event_to_row(event))
                session.flush()
                session.add(_opportunity_to_row(opportunity))
                session.add(job_to_row(next_job))
        except IntegrityError as exc:
            existing = self.find_opportunity_for_evaluation(opportunity.evaluation_id)
            if existing is not None:
                return existing
            raise exc
        return opportunity

    def save_review(self, human_action: HumanAction, audit_events: tuple[AuditEvent, ...]) -> None:
        """Persist a ``REVIEW`` HumanAction and its audit event atomically."""

        with Session(self.engine) as session, session.begin():
            for event in audit_events:
                session.add(_audit_event_to_row(event))
            session.flush()
            session.add(human_action_to_row(human_action))

    def commit_transition(
        self,
        opportunity: Opportunity,
        *,
        previous_state: OpportunityState,
        audit_events: tuple[AuditEvent, ...],
    ) -> Opportunity:
        """Apply a valid transition with an optimistic conditional ``UPDATE``.

        A concurrent transition that already moved the row is rejected with
        ``RAD-WF-015``; the transaction rolls back, so no audit event is written
        for a transition that did not happen.
        """

        with Session(self.engine) as session, session.begin():
            for event in audit_events:
                session.add(_audit_event_to_row(event))
            session.flush()
            updated_id = session.execute(
                update(OpportunityRow)
                .where(
                    OpportunityRow.id == opportunity.opportunity_id,
                    OpportunityRow.state == previous_state.value,
                )
                .values(state=opportunity.state.value, updated_at=_iso(opportunity.updated_at))
                .returning(OpportunityRow.id)
            ).scalar_one_or_none()
            if updated_id is None:
                raise opportunity_transition_invalid_error(
                    opportunity.opportunity_id,
                    current=previous_state,
                    target=opportunity.state,
                )
        return opportunity

    def record_rejected_transition(self, audit_event: AuditEvent) -> None:
        """Persist the audit of a rejected transition (append-only)."""

        with Session(self.engine) as session, session.begin():
            session.add(_audit_event_to_row(audit_event))


def _opportunity_to_row(opportunity: Opportunity) -> OpportunityRow:
    return OpportunityRow(
        id=opportunity.opportunity_id,
        candidate_id=opportunity.candidate_id,
        evaluation_id=opportunity.evaluation_id,
        brand=opportunity.brand.value,
        priority=opportunity.priority,
        state=opportunity.state.value,
        correlation_id=opportunity.correlation_id,
        audit_event_id=opportunity.audit_event_id,
        schema_version=opportunity.schema_version,
        created_at=_iso(opportunity.created_at),
        updated_at=_iso(opportunity.updated_at),
    )


def _opportunity_from_row(row: OpportunityRow) -> Opportunity:
    return Opportunity(
        opportunity_id=row.id,
        candidate_id=row.candidate_id,
        evaluation_id=row.evaluation_id,
        brand=Brand(row.brand),
        state=OpportunityState(row.state),
        priority=row.priority,
        correlation_id=row.correlation_id,
        audit_event_id=row.audit_event_id,
        created_at=_parse(row.created_at),
        updated_at=_parse(row.updated_at),
        schema_version=row.schema_version,
    )


def _audit_event_to_row(event: AuditEvent) -> AuditEventRow:
    return AuditEventRow(
        id=event.id,
        event_type=event.event_type,
        entity_type=event.entity_type,
        entity_id=event.entity_id,
        source=event.source,
        correlation_id=event.correlation_id,
        payload=json.dumps(dict(event.payload), ensure_ascii=False, sort_keys=True),
        recorded_at=_iso(event.recorded_at),
    )


def _audit_event_from_row(row: AuditEventRow) -> AuditEvent:
    return AuditEvent(
        id=row.id,
        event_type=row.event_type,
        entity_type=row.entity_type,
        entity_id=row.entity_id,
        source=row.source,
        correlation_id=row.correlation_id,
        recorded_at=_parse(row.recorded_at),
        payload={} if row.payload is None else json.loads(row.payload),
    )


__all__ = [
    "SqlAlchemyWorkflowRepository",
]
