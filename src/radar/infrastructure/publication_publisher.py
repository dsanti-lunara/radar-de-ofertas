"""Deterministic Fake publisher (AUT-359, AUT-421).

``FakePublisher`` is the development publisher of the publication step: it
satisfies the framework-free :class:`~radar.domain.publication.Publisher`
contract without any network, credential, clock or filesystem access. It returns
a deterministic ``external_message_id`` derived from the channel, the internal
destination and the publication id, so the Publication lifecycle, idempotency and
persistence can be exercised offline.

The real ``TelegramPublisher`` (RDR-071) and the WhatsApp Browser Bridge
publisher (RDR-108) belong to their own tickets and remain gated by the
destination registry, compliance and the authorization gate.
"""

from __future__ import annotations

from typing import Any

from radar.domain.publication import PublicationSendRequest

#: Provider identity recorded on every send produced by the fake.
FAKE_PUBLISHER_NAME = "fake"


class FakePublisher:
    """Deterministic, offline implementation of the ``Publisher`` contract."""

    def __init__(self) -> None:
        self._name = FAKE_PUBLISHER_NAME

    @property
    def name(self) -> str:
        return self._name

    def send(self, request: PublicationSendRequest) -> dict[str, Any]:
        """Return a deterministic fake receipt for the requested publication.

        The fake is idempotent by construction: the same ``publication_id`` yields
        the same ``external_message_id``, so a replay never looks like a new send.
        It never invents a commercial message and only echoes the backend-prepared
        content back into the receipt-free contract.
        """

        return {
            "external_message_id": (
                f"fake-{request.channel.value.lower()}-{request.destination_id}-"
                f"{request.publication_id}"
            )
        }


__all__ = [
    "FAKE_PUBLISHER_NAME",
    "FakePublisher",
]
