from __future__ import annotations

import pytest

from radar.domain.affiliate_link import AffiliateLinkRequest
from radar.domain.capture import Marketplace
from radar.domain.errors import RadarException
from radar.domain.taxonomy import Brand
from radar.domain.tracking import (
    APPROVED_TRACKING_LABEL_MAPPING,
    TRACKING_LABEL_INVALID,
    TRACKING_MAPPING_NOT_CONFIGURED,
    TrackingContext,
    build_tracking_context,
    build_tracking_label_mapping,
)
from radar.infrastructure.affiliate_link_provider import FakeAffiliateLinkProvider

pytestmark = pytest.mark.unit


def _tracking(marketplace: Marketplace, label: str = "rbtgoffer"):
    mapping = build_tracking_label_mapping(
        {
            "schema_version": "1.0",
            "mapping_version": "tracking-labels-test",
            "entries": [
                {
                    "internal_reference": "RADAR_BEAUTY:MERCADO_LIVRE",
                    "marketplace": marketplace.value,
                    "label": label,
                }
            ],
        }
    )
    return build_tracking_context(
        opportunity_id="opp_1",
        marketplace=marketplace,
        brand=Brand.RADAR_BEAUTY,
        internal_reference="RADAR_BEAUTY:MERCADO_LIVRE",
        mapping=mapping,
        tracking_context_id="trk_1",
    )


def _request(marketplace: Marketplace = Marketplace.MERCADO_LIVRE) -> AffiliateLinkRequest:
    return AffiliateLinkRequest(
        opportunity_id="opp_1",
        marketplace=marketplace,
        original_url="https://www.mercadolivre.com.br/p/MLB123",
        external_id="MLB123",
        tracking=_tracking(marketplace),
    )


def test_fake_provider_is_deterministic_and_embeds_product_and_label() -> None:
    provider = FakeAffiliateLinkProvider()
    request = _request()

    first = provider.generate(request)
    second = provider.generate(request)

    assert first == second
    assert first["source"] == "FAKE"
    assert first["product_reference"] == "MLB123"
    assert "MLB123" in first["affiliate_url"]
    assert "matt_word=rbtgoffer" in first["affiliate_url"]
    assert first["affiliate_url"].startswith("https://www.mercadolivre.com.br/")


def test_fake_provider_supports_shopee_host() -> None:
    provider = FakeAffiliateLinkProvider()
    request = _request(Marketplace.SHOPEE)

    result = provider.generate(request)

    assert result["affiliate_url"].startswith("https://s.shopee.com.br/")
    assert "sub_id=rbtgoffer" in result["affiliate_url"]


def test_fake_provider_requires_a_configured_label() -> None:
    provider = FakeAffiliateLinkProvider()
    tracking = build_tracking_context(
        opportunity_id="opp_1",
        marketplace=Marketplace.MERCADO_LIVRE,
        brand=Brand.RADAR_BEAUTY,
        internal_reference="RADAR_BEAUTY:MERCADO_LIVRE",
        mapping=APPROVED_TRACKING_LABEL_MAPPING,
    )
    request = AffiliateLinkRequest(
        opportunity_id="opp_1",
        marketplace=Marketplace.MERCADO_LIVRE,
        original_url="https://www.mercadolivre.com.br/p/MLB123",
        external_id="MLB123",
        tracking=tracking,
    )

    with pytest.raises(RadarException) as error:
        provider.generate(request)
    assert error.value.error.code == TRACKING_MAPPING_NOT_CONFIGURED


def test_fake_provider_rejects_an_invalid_label_as_defense_in_depth() -> None:
    provider = FakeAffiliateLinkProvider()
    invalid = TrackingContext(
        tracking_context_id="trk_1",
        opportunity_id="opp_1",
        marketplace=Marketplace.MERCADO_LIVRE,
        brand=Brand.RADAR_BEAUTY,
        internal_reference="RADAR_BEAUTY:MERCADO_LIVRE",
        mapping_version="v1",
        mapping_hash="hash",
        external_label="NOT_lower",
        configured=True,
    )
    request = AffiliateLinkRequest(
        opportunity_id="opp_1",
        marketplace=Marketplace.MERCADO_LIVRE,
        original_url="https://www.mercadolivre.com.br/p/MLB123",
        external_id="MLB123",
        tracking=invalid,
    )

    with pytest.raises(RadarException) as error:
        provider.generate(request)
    assert error.value.error.code == TRACKING_LABEL_INVALID
