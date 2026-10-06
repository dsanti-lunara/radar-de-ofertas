"""Deterministic Fake publisher (AUT-359, AUT-421).

``FakePublisher`` is the development publisher of the publication step: it
satisfies the framework-free :class:`~radar.domain.publication.Publisher`
contract without any network, credential, clock or filesystem access. It returns
a deterministic ``external_message_id`` derived from the channel, the internal
destination and the publication id, so the Publication lifecycle, idempotency and
persistence can be exercised offline.

The fake can also simulate the crash window of ADR 0001: with
``crash_after_accept=True`` it records the accepted message and then raises
:class:`~radar.domain.publication.PublicationResultUnknown`, so the service must
treat the outcome as *unknown* (suspend + HumanAction, never an automatic
resend), not as a confirmed failure.

The real ``TelegramPublisher`` (RDR-071) and the WhatsApp Browser Bridge
publisher (RDR-108) belong to their own tickets and remain gated by the
destination registry, compliance and the authorization gate.
"""

from __future__ import annotations

from typing import Any

from radar.domain.publication import (
    PublicationResultUnknown,
    PublicationSendRequest,
    publication_result_unknown_error,
)

#: Provider identity recorded on every send produced by the fake.
FAKE_PUBLISHER_NAME = "fake"


class FakePublisher:
    """Deterministic, offline implementation of the ``Publisher`` contract."""

    def __init__(self, *, crash_after_accept: bool = False) -> None:
        self._name = FAKE_PUBLISHER_NAME
        self._crash_after_accept = crash_after_accept
        #: Every send the fake *accepted*, in order; survives a service restart so
        #: tests can prove no automatic resend happened.
        self.accepted: list[PublicationSendRequest] = []

    @property
    def name(self) -> str:
        return self._name

    def send(self, request: PublicationSendRequest) -> dict[str, Any]:
        """Return a deterministic fake receipt for the requested publication.

        The fake is idempotent by construction: the same ``publication_id`` yields
        the same ``external_message_id``, so a replay never looks like a new send.
        It never invents a commercial message and only echoes the backend-prepared
        content back into the receipt-free contract.

        ``crash_after_accept`` models a crash in the send window: the message is
        accepted (recorded) and then the result is reported as unknown, so the
        caller must suspend the publication instead of confirming or resending it.
        """

        self.accepted.append(request)
        if self._crash_after_accept:
            raise publication_result_unknown_error(
                context={
                    "provider": self._name,
                    "publication_id": request.publication_id,
                    "destination_id": request.destination_id,
                }
            )
        return {
            "external_message_id": (
                f"fake-{request.channel.value.lower()}-{request.destination_id}-"
                f"{request.publication_id}"
            )
        }

    def accepted_count(self) -> int:
        """Number of accepted sends recorded by this fake instance."""

        return len(self.accepted)


__all__ = [
    "FAKE_PUBLISHER_NAME",
    "FakePublisher",
    "PublicationResultUnknown",
]
