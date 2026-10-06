"""SQLAlchemy implementation of the append-only ContentGeneration store (RDR-019).

The ContentGeneration and its ``AuditEvent`` are written in **one** transaction, so
a failed write never leaves a partial record (AUT-141). The ``content_generation``
table carries SQLite triggers (migration ``0015``) that reject UPDATE/DELETE, so a
generated preview is never overwritten and staleness is derived on read instead of
mutating the row. The generated (AI copy) and final (renderer output) documents are
stored separately with their own versions (AUT-034, AUT-081).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from radar.domain.audit import CONTENT_GENERATION_RECORDED
from radar.domain.content import (
    ContentGeneration,
    ContentGenerationStatus,
    ContentWarning,
    GeneratedContent,
    RenderedContent,
)
from radar.domain.knowledge import Channel
from radar.domain.taxonomy import Brand
from radar.infrastructure.models import AuditEventRow, ContentGenerationRow


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat()


@dataclass(slots=True)
class SqlAlchemyContentGenerationRepository:
    """Persist and read append-only ContentGenerations against SQLite."""

    engine: Engine

    def save_content_generation(self, record: ContentGeneration) -> ContentGeneration:
        with Session(self.engine) as session, session.begin():
            session.add(_audit_event_to_row(record))
            session.flush()
            session.add(_content_generation_to_row(record))
        return record

    def list_content_generations(self, opportunity_id: str) -> tuple[ContentGeneration, ...]:
        with Session(self.engine) as session:
            rows = (
                session.execute(
                    select(ContentGenerationRow)
                    .where(ContentGenerationRow.opportunity_id == opportunity_id)
                    .order_by(ContentGenerationRow.created_at, ContentGenerationRow.id)
                )
                .scalars()
                .all()
            )
            return tuple(_content_generation_from_row(row) for row in rows)

    def get_content_generation(self, content_generation_id: str) -> ContentGeneration | None:
        with Session(self.engine) as session:
            row = session.get(ContentGenerationRow, content_generation_id)
            return None if row is None else _content_generation_from_row(row)

    def list_content_generations_by_ai_input_hash(
        self, opportunity_id: str, ai_input_hash: str
    ) -> tuple[ContentGeneration, ...]:
        """Return persisted generations of an equivalent input, newest first (RDR-055).

        Legacy rows written before migration ``0016`` carry an empty hash and can
        never match a real sha256, so they are never served as cache hits.
        """

        with Session(self.engine) as session:
            rows = (
                session.execute(
                    select(ContentGenerationRow)
                    .where(
                        ContentGenerationRow.opportunity_id == opportunity_id,
                        ContentGenerationRow.ai_input_hash == ai_input_hash,
                    )
                    .order_by(
                        ContentGenerationRow.created_at.desc(),
                        ContentGenerationRow.id.desc(),
                    )
                )
                .scalars()
                .all()
            )
            return tuple(_content_generation_from_row(row) for row in rows)


def _audit_event_to_row(record: ContentGeneration) -> AuditEventRow:
    return AuditEventRow(
        id=record.audit_event_id,
        event_type=CONTENT_GENERATION_RECORDED,
        entity_type="content_generation",
        entity_id=record.content_generation_id,
        source="content",
        correlation_id=record.correlation_id,
        payload=json.dumps(
            {
                "opportunity_id": record.opportunity_id,
                "candidate_id": record.candidate_id,
                "channel": record.channel.value,
                "generation_version": record.generation_version,
                "knowledge_version": record.knowledge_version,
                "prompt_version": record.prompt_version,
                "renderer_version": record.renderer_version,
                "fact_hash": record.fact_hash,
                "ai_input_hash": record.ai_input_hash,
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        recorded_at=_iso(record.created_at),
    )


def _content_generation_to_row(record: ContentGeneration) -> ContentGenerationRow:
    return ContentGenerationRow(
        id=record.content_generation_id,
        opportunity_id=record.opportunity_id,
        candidate_id=record.candidate_id,
        brand=record.brand.value,
        channel=record.channel.value,
        generation_version=record.generation_version,
        knowledge_version=record.knowledge_version,
        knowledge_hash=record.knowledge_hash,
        prompt_version=record.prompt_version,
        renderer_version=record.renderer_version,
        generated_content=json.dumps(
            record.generated.to_contract(), ensure_ascii=False, sort_keys=True
        ),
        final_content=json.dumps(record.rendered.to_contract(), ensure_ascii=False, sort_keys=True),
        guards=json.dumps(list(record.guards), ensure_ascii=False, sort_keys=True),
        warnings=json.dumps(
            [warning.to_contract() for warning in record.warnings],
            ensure_ascii=False,
            sort_keys=True,
        ),
        facts=json.dumps(dict(record.facts), ensure_ascii=False, sort_keys=True),
        fact_hash=record.fact_hash,
        ai_input_hash=record.ai_input_hash,
        status=record.status.value,
        correlation_id=record.correlation_id,
        audit_event_id=record.audit_event_id,
        schema_version=record.schema_version,
        created_at=_iso(record.created_at),
    )


def _content_generation_from_row(row: ContentGenerationRow) -> ContentGeneration:
    generated_payload: dict[str, Any] = json.loads(row.generated_content)
    final_payload: dict[str, Any] = json.loads(row.final_content)
    generated = GeneratedContent(
        headline=str(generated_payload["headline"]),
        body=str(generated_payload["body"]),
        cta=str(generated_payload["cta"]),
        warnings=tuple(
            ContentWarning(
                code=str(item["code"]),
                message=str(item["message"]),
                context=dict(item.get("context") or {}),
            )
            for item in generated_payload.get("warnings", [])
        ),
    )
    rendered = RenderedContent(
        headline=str(final_payload["headline"]),
        body=str(final_payload["body"]),
        cta=str(final_payload["cta"]),
        price=str(final_payload["price"]),
        price_display=str(final_payload["price_display"]),
        affiliate_url=str(final_payload["affiliate_url"]),
        disclosure=str(final_payload["disclosure"]),
        tracking=dict(final_payload.get("tracking") or {}),
        blocks=tuple(str(block) for block in final_payload.get("blocks", [])),
        text=str(final_payload["text"]),
        renderer_version=str(final_payload["renderer_version"]),
    )
    warnings = tuple(
        ContentWarning(
            code=str(item["code"]),
            message=str(item["message"]),
            context=dict(item.get("context") or {}),
        )
        for item in json.loads(row.warnings)
    )
    return ContentGeneration(
        content_generation_id=row.id,
        opportunity_id=row.opportunity_id,
        candidate_id=row.candidate_id,
        brand=Brand(row.brand),
        channel=Channel(row.channel),
        generation_version=row.generation_version,
        knowledge_version=row.knowledge_version,
        knowledge_hash=row.knowledge_hash,
        prompt_version=row.prompt_version,
        renderer_version=row.renderer_version,
        generated=generated,
        rendered=rendered,
        guards=tuple(str(guard) for guard in json.loads(row.guards)),
        warnings=warnings,
        facts=json.loads(row.facts),
        fact_hash=row.fact_hash,
        correlation_id=row.correlation_id,
        audit_event_id=row.audit_event_id,
        created_at=datetime.fromisoformat(row.created_at),
        ai_input_hash=row.ai_input_hash,
        status=ContentGenerationStatus(row.status),
        schema_version=row.schema_version,
    )


__all__ = [
    "SqlAlchemyContentGenerationRepository",
]
