"""Deterministic Fake affiliate link provider (AUT-359, AUT-421).

``FakeAffiliateLinkProvider`` is the development provider of the link step: it
satisfies the framework-free
:class:`~radar.domain.affiliate_link.AffiliateLinkProvider` contract without any
network, credential, clock or filesystem access. It builds a deterministic URL
from the expected product and the resolved tracking label, so the entity,
validation and persistence can be exercised offline.

The returned ``source`` is ``FAKE``, so the resulting
:class:`~radar.domain.affiliate_link.AffiliateLink` is never productive
(AUT-422). The real marketplace adapters remain gated by Browser
Reconnaissance/SPIKE and are not implemented here.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from radar.domain.affiliate_link import AffiliateLinkRequest
from radar.domain.capture import Marketplace
from radar.domain.tracking import (
    tracking_mapping_not_configured_error,
    validate_tracking_label,
)

#: Provider identity recorded on every link produced by the fake.
FAKE_LINK_PROVIDER_NAME = "fake"

#: Provider source value that maps to ``LinkGenerationMethod.FAKE``.
FAKE_LINK_SOURCE = "FAKE"


class FakeAffiliateLinkProvider:
    """Deterministic, offline implementation of the ``AffiliateLinkProvider``."""

    def __init__(self) -> None:
        self._name = FAKE_LINK_PROVIDER_NAME

    @property
    def name(self) -> str:
        return self._name

    def generate(self, request: AffiliateLinkRequest) -> dict[str, Any]:
        """Return a deterministic fake link for the expected product and label.

        The external label must already be resolved by the versioned mapping; the
        fake re-validates its charset/length as defense in depth and never assumes
        a label exists (a missing label fails closed).
        """

        label = request.tracking.external_label
        if label is None:
            raise tracking_mapping_not_configured_error(
                internal_reference=request.tracking.internal_reference,
                marketplace=request.marketplace,
            )
        validated_label = validate_tracking_label(label)
        product = quote(request.external_id, safe="")
        if request.marketplace is Marketplace.MERCADO_LIVRE:
            affiliate_url = (
                "https://www.mercadolivre.com.br/social/radar-fake/"
                f"{product}?matt_word={validated_label}"
            )
        else:
            affiliate_url = f"https://s.shopee.com.br/fake/{product}?sub_id={validated_label}"
        return {
            "affiliate_url": affiliate_url,
            "source": FAKE_LINK_SOURCE,
            "product_reference": request.external_id,
        }


__all__ = [
    "FAKE_LINK_PROVIDER_NAME",
    "FAKE_LINK_SOURCE",
    "FakeAffiliateLinkProvider",
]
