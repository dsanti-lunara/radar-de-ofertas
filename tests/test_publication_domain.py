from __future__ import annotations

from datetime import UTC, datetime
from itertools import count
from typing import Any

import pytest

from radar.domain.knowledge import Channel
from radar.domain.publication import (
    APPROVED_PUBLICATION_POLICY,
    PUBLICATION_BLOCKED,
    PUBLICATION_POLICY_INVALID,
    PUBLICATION_PUBLISHER_INVALID,
    REASON_ALLOWED,
    REASON_BURST_LIMIT,
    REASON_COOLDOWN_ACTIVE,
    REASON_HARD_CAP_REACHED,
    REASON_QUIET_HOURS,
    Publication,
    PublicationError,
    PublicationEventType,
    PublicationStatus,
    build_publication,
    build_publication_policy,
    evaluate_publication_policy,
    parse_publisher_response,
)
from radar.domain.taxonomy import Brand
from radar.infrastructure.publication_publisher import FakePublisher

pytestmark = pytest.mark.unit


def _ids() -> Any:
    counter = count(1)

    def factory(prefix: str) -> str:
        return f"{prefix}_{next(counter)}"

    return factory


def _publication(
    *,
    brand: Brand = Brand.RADAR_BEAUTY,
    channel: Channel = Channel.TELEGRAM,
    destination_id: str = "dest-1",
    published_at: datetime,
    publication_id: str = "pub-1",
) -> Publication:
    return build_publication(
        opportunity_id="opp-1",
        content_generation_id="ctg-1",
        affiliate_link_id="lnk-1",
        brand=brand,
        channel=channel,
        destination_id=destination_id,
        idempotency_key=f"publish:{publication_id}",
        published_price="80.00",
        external_message_id=f"fake-{publication_id}",
        correlation_id="cid-1",
        audit_event_id=f"aud-{publication_id}",
        created_at=published_at,
        published_at=published_at,
        publication_id=publication_id,
        id_factory=_ids(),
    )


def test_approved_policy_follows_sdd_reference() -> None:
    policy = APPROVED_PUBLICATION_POLICY

    assert policy.default_limits.hard_cap_per_day == 12
    assert policy.default_limits.burst_limit == 2
    assert policy.default_limits.burst_window_minutes == 15
    # The SDD does not calibrate a cooldown or quiet windows: both stay explicit.
    assert policy.default_limits.cooldown_minutes is None
    assert policy.quiet_windows == ()
    assert policy.channel_limits == {}
    assert policy.content_hash


def test_policy_hash_is_stable_and_changes_with_content() -> None:
    first = build_publication_policy({"policy_version": "v1"})
    same = build_publication_policy({"policy_version": "v1"})
    other = build_publication_policy({"policy_version": "v1", "hard_cap_per_day": 5})

    assert first.content_hash == same.content_hash
    assert first.content_hash != other.content_hash


def test_policy_accepts_a_stricter_channel_override() -> None:
    policy = build_publication_policy(
        {
            "policy_version": "v1",
            "channels": {"WHATSAPP": {"hard_cap_per_day": 8, "burst_limit": 1}},
        }
    )

    assert policy.limits_for(Channel.WHATSAPP).hard_cap_per_day == 8
    assert policy.limits_for(Channel.WHATSAPP).burst_limit == 1
    assert policy.limits_for(Channel.TELEGRAM).hard_cap_per_day == 12


@pytest.mark.parametrize(
    "document",
    [
        {"policy_version": "v1", "schema_version": "2.0"},
        {"schema_version": "1.0"},
        {"policy_version": "v1", "hard_cap_per_day": 0},
        {"policy_version": "v1", "burst_limit": -1},
        {"policy_version": "v1", "timezone": "Not/AZone"},
        {"policy_version": "v1", "quiet_windows": [{"start": "25:00", "end": "07:00"}]},
        {"policy_version": "v1", "quiet_windows": [{"start": "22:00", "end": "22:00"}]},
        {"policy_version": "v1", "channels": {"INVALID": {"hard_cap_per_day": 1}}},
        {"policy_version": "v1", "channels": {"WHATSAPP": {"hard_cap_per_day": 20}}},
        {"policy_version": "v1", "channels": {"WHATSAPP": {"burst_limit": 3}}},
        {"policy_version": "v1", "channels": {"WHATSAPP": {"burst_window_minutes": 5}}},
    ],
)
def test_invalid_policy_fails_closed(document: dict[str, Any]) -> None:
    with pytest.raises(PublicationError) as excinfo:
        build_publication_policy(document)

    assert excinfo.value.error.code == PUBLICATION_POLICY_INVALID


def test_policy_allows_when_under_every_limit() -> None:
    decision = evaluate_publication_policy(
        APPROVED_PUBLICATION_POLICY,
        brand=Brand.RADAR_BEAUTY,
        channel=Channel.TELEGRAM,
        destination_id="dest-1",
        now=datetime(2026, 10, 6, 12, 0, tzinfo=UTC),
        publications=(),
    )

    assert decision.allowed is True
    assert decision.reason_code == REASON_ALLOWED


def test_quiet_hours_block_before_the_publisher() -> None:
    policy = build_publication_policy(
        {
            "policy_version": "v1",
            "timezone": "America/Maceio",
            "quiet_windows": [{"start": "22:00", "end": "07:00"}],
        }
    )

    # 02:00 UTC == 23:00 America/Maceio, inside the quiet window.
    decision = evaluate_publication_policy(
        policy,
        brand=Brand.RADAR_BEAUTY,
        channel=Channel.TELEGRAM,
        destination_id="dest-1",
        now=datetime(2026, 10, 6, 2, 0, tzinfo=UTC),
        publications=(),
    )

    assert decision.allowed is False
    assert decision.reason_code == REASON_QUIET_HOURS


def test_hard_cap_blocks_after_the_daily_limit() -> None:
    policy = build_publication_policy({"policy_version": "v1", "hard_cap_per_day": 2})
    now = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)
    publications = (
        _publication(published_at=datetime(2026, 10, 6, 8, 0, tzinfo=UTC), publication_id="a"),
        _publication(published_at=datetime(2026, 10, 6, 9, 0, tzinfo=UTC), publication_id="b"),
    )

    decision = evaluate_publication_policy(
        policy,
        brand=Brand.RADAR_BEAUTY,
        channel=Channel.TELEGRAM,
        destination_id="dest-1",
        now=now,
        publications=publications,
    )

    assert decision.allowed is False
    assert decision.reason_code == REASON_HARD_CAP_REACHED
    assert decision.hard_cap_count == 2


def test_burst_blocks_within_the_window() -> None:
    policy = build_publication_policy({"policy_version": "v1", "burst_limit": 2})
    now = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)
    publications = (
        _publication(published_at=datetime(2026, 10, 6, 11, 50, tzinfo=UTC), publication_id="a"),
        _publication(published_at=datetime(2026, 10, 6, 11, 55, tzinfo=UTC), publication_id="b"),
    )

    decision = evaluate_publication_policy(
        policy,
        brand=Brand.RADAR_BEAUTY,
        channel=Channel.TELEGRAM,
        destination_id="dest-1",
        now=now,
        publications=publications,
    )

    assert decision.allowed is False
    assert decision.reason_code == REASON_BURST_LIMIT
    assert decision.burst_count == 2


def test_cooldown_blocks_a_recent_destination_send() -> None:
    policy = build_publication_policy(
        {"policy_version": "v1", "burst_limit": 5, "cooldown_minutes": 60}
    )
    now = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)
    publications = (
        _publication(
            destination_id="dest-1",
            published_at=datetime(2026, 10, 6, 11, 30, tzinfo=UTC),
            publication_id="a",
        ),
    )

    decision = evaluate_publication_policy(
        policy,
        brand=Brand.RADAR_BEAUTY,
        channel=Channel.TELEGRAM,
        destination_id="dest-1",
        now=now,
        publications=publications,
    )

    assert decision.allowed is False
    assert decision.reason_code == REASON_COOLDOWN_ACTIVE


def test_published_publication_is_its_own_entity_with_events() -> None:
    published_at = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)
    publication = _publication(published_at=published_at)

    contract = publication.to_contract()

    assert contract["status"] == PublicationStatus.PUBLISHED.value
    assert contract["publication_id"] == "pub-1"
    assert contract["content_generation_id"] == "ctg-1"
    assert contract["opportunity_id"] == "opp-1"
    assert contract["affiliate_link_id"] == "lnk-1"
    assert contract["external_message_id"] == "fake-pub-1"
    assert contract["published_price"] == "80.00"
    assert [event["event_type"] for event in contract["events"]] == [
        PublicationEventType.CREATED.value,
        PublicationEventType.PUBLISHED.value,
    ]


def test_fake_publisher_is_deterministic() -> None:
    from radar.domain.publication import PublicationSendRequest

    publisher = FakePublisher()
    request = PublicationSendRequest(
        publication_id="pub-1",
        idempotency_key="publish:1",
        channel=Channel.TELEGRAM,
        destination_id="dest-1",
        content_text="text",
        affiliate_url="https://example.com",
        correlation_id="cid-1",
    )

    first = publisher.send(request)
    second = publisher.send(request)

    assert first == second
    assert first["external_message_id"] == "fake-telegram-dest-1-pub-1"
    assert parse_publisher_response(first, provider=publisher.name) == "fake-telegram-dest-1-pub-1"


@pytest.mark.parametrize(
    "raw",
    [
        "not-a-mapping",
        {"external_message_id": ""},
        {},
        {"external_message_id": "x", "token": "secret"},
        {"external_message_id": "x", "unknown": 1},
    ],
)
def test_invalid_publisher_response_fails_closed(raw: object) -> None:
    with pytest.raises(PublicationError) as excinfo:
        parse_publisher_response(raw, provider="stub")

    assert excinfo.value.error.code == PUBLICATION_PUBLISHER_INVALID


def test_blocked_error_carries_the_reason_code() -> None:
    from radar.domain.publication import publication_blocked_error

    error = publication_blocked_error(reason_code=REASON_QUIET_HOURS, message="blocked")

    assert error.error.code == PUBLICATION_BLOCKED
    assert error.error.context["reason_code"] == REASON_QUIET_HOURS
