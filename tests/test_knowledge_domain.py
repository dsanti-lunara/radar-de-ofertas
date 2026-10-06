from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from radar.domain.knowledge import (
    APPROVED_KNOWLEDGE_PACK,
    KNOWLEDGE_INVALID,
    Channel,
    KnowledgeInvalidError,
    build_knowledge_pack,
    select_knowledge_context,
)
from radar.domain.taxonomy import Brand
from radar.infrastructure.knowledge import KnowledgePackLoader

pytestmark = pytest.mark.unit


def _build(entries: list[dict[str, Any]]) -> Any:
    return build_knowledge_pack(
        {
            "schema_version": "1.0",
            "knowledge_version": "knowledge-pack-test",
            "prompt_version": "editorial-review-test",
            "entries": entries,
        }
    )


def _entry(**overrides: Any) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "brand": "RADAR_BEAUTY",
        "channel": "TELEGRAM",
        "system_contract": ["use only provided facts"],
        "brand_guidance": ["direct tone"],
        "channel_guidance": ["short message"],
    }
    entry.update(overrides)
    return entry


def test_approved_baseline_is_versioned_hashed_and_empty() -> None:
    assert APPROVED_KNOWLEDGE_PACK.knowledge_version == "knowledge-pack-1.0"
    assert APPROVED_KNOWLEDGE_PACK.prompt_version == "editorial-review-1.0"
    assert APPROVED_KNOWLEDGE_PACK.content_hash
    assert APPROVED_KNOWLEDGE_PACK.entries == {}

    context = select_knowledge_context(
        APPROVED_KNOWLEDGE_PACK,
        brand=Brand.RADAR_BEAUTY,
        channel=Channel.TELEGRAM,
        task="EDITORIAL_REVIEW",
    )

    assert context.configured is False
    assert context.warning_code == "KNOWLEDGE_CONTEXT_NOT_CONFIGURED"
    assert context.knowledge_hash == APPROVED_KNOWLEDGE_PACK.content_hash
    assert context.knowledge_version == "knowledge-pack-1.0"
    assert context.prompt_version == "editorial-review-1.0"


def test_entry_configures_the_brand_channel_context() -> None:
    pack = _build([_entry()])

    context = select_knowledge_context(
        pack,
        brand=Brand.RADAR_BEAUTY,
        channel=Channel.TELEGRAM,
        task="EDITORIAL_REVIEW",
    )

    assert context.configured is True
    assert context.warning_code is None
    assert context.brand_guidance == ("direct tone",)
    assert context.channel_guidance == ("short message",)
    assert context.system_contract == ("use only provided facts",)
    assert context.knowledge_version == "knowledge-pack-test"
    assert context.prompt_version == "editorial-review-test"


def test_context_is_scoped_to_brand_and_channel() -> None:
    pack = _build([_entry()])

    other = select_knowledge_context(
        pack,
        brand=Brand.CASA_EM_ORDEM,
        channel=Channel.WHATSAPP,
        task="EDITORIAL_REVIEW",
    )

    assert other.configured is False
    assert other.brand is Brand.CASA_EM_ORDEM
    assert other.channel is Channel.WHATSAPP


def test_hash_changes_when_the_content_changes() -> None:
    first = _build([_entry()])
    second = _build([_entry(brand_guidance=["another tone"])])

    assert first.content_hash != second.content_hash
    # The same content always hashes the same way (AUT-207).
    assert first.content_hash == _build([_entry()]).content_hash


def test_invalid_pack_fails_closed_with_structured_error() -> None:
    with pytest.raises(KnowledgeInvalidError) as schema:
        build_knowledge_pack({"schema_version": "2.0"})
    assert schema.value.error.code == KNOWLEDGE_INVALID

    with pytest.raises(KnowledgeInvalidError) as sensitive:
        build_knowledge_pack({"schema_version": "1.0", "token": "should-not-be-here"})
    assert sensitive.value.error.code == KNOWLEDGE_INVALID
    assert "token" in sensitive.value.error.context["fields"]

    with pytest.raises(KnowledgeInvalidError) as brand:
        _build([_entry(brand="NOT_A_BRAND")])
    assert brand.value.error.code == KNOWLEDGE_INVALID

    with pytest.raises(KnowledgeInvalidError) as duplicate:
        _build([_entry(), _entry()])
    assert duplicate.value.error.code == KNOWLEDGE_INVALID

    with pytest.raises(KnowledgeInvalidError) as unknown:
        _build([_entry(extra="x")])
    assert unknown.value.error.code == KNOWLEDGE_INVALID


def test_example_knowledge_pack_is_valid_and_configures_a_slice() -> None:
    path = Path(__file__).resolve().parents[1] / "config" / "knowledge-pack.example.json"

    pack = KnowledgePackLoader.from_env(env={}, knowledge_path=path).load()

    context = select_knowledge_context(
        pack,
        brand=Brand.RADAR_BEAUTY,
        channel=Channel.TELEGRAM,
        task="EDITORIAL_REVIEW",
    )
    assert context.configured is True
    assert context.system_contract
    assert context.knowledge_hash == pack.content_hash
