from __future__ import annotations

from datetime import UTC, datetime

import pytest

from radar.domain.affiliate_link import (
    AFFILIATE_LINK_URL_INVALID,
    AffiliateLinkRequest,
    LinkGenerationMethod,
    affiliate_link_input_invalid_error,
    affiliate_link_not_productive_error,
    build_affiliate_link,
    parse_affiliate_link_response,
    require_productive,
    validate_affiliate_url,
)
from radar.domain.capture import Marketplace
from radar.domain.errors import RadarException
from radar.domain.taxonomy import Brand
from radar.domain.tracking import (
    APPROVED_TRACKING_LABEL_MAPPING,
    build_tracking_context,
    build_tracking_label_mapping,
)

pytestmark = pytest.mark.unit

FIXED_NOW = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)


def _tracking(marketplace: Marketplace = Marketplace.MERCADO_LIVRE, label: str = "rbtgoffer"):
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


def test_validate_affiliate_url_rejects_invalid_host_and_scheme() -> None:
    with pytest.raises(RadarException) as invalid_host:
        validate_affiliate_url(
            "https://evil.example.com/x/MLB123", marketplace=Marketplace.MERCADO_LIVRE
        )
    assert invalid_host.value.error.code == AFFILIATE_LINK_URL_INVALID

    with pytest.raises(RadarException) as invalid_scheme:
        validate_affiliate_url("javascript:alert(1)", marketplace=Marketplace.MERCADO_LIVRE)
    assert invalid_scheme.value.error.code == AFFILIATE_LINK_URL_INVALID

    with pytest.raises(RadarException) as sensitive:
        validate_affiliate_url(
            "https://www.mercadolivre.com.br/x?token=abc", marketplace=Marketplace.MERCADO_LIVRE
        )
    assert sensitive.value.error.code == AFFILIATE_LINK_URL_INVALID


def test_validate_affiliate_url_preserves_the_literal_url() -> None:
    url = "https://meli.la/AbC123?matt_word=rbtgoffer&matt_tool=1234"
    assert validate_affiliate_url(url, marketplace=Marketplace.MERCADO_LIVRE) == url

    with pytest.raises(RadarException):
        validate_affiliate_url(f" {url}", marketplace=Marketplace.MERCADO_LIVRE)


def test_parse_rejects_wrong_product_and_unknown_source() -> None:
    request = _request()

    with pytest.raises(RadarException) as wrong_product:
        parse_affiliate_link_response(
            {
                "affiliate_url": "https://www.mercadolivre.com.br/social/x?matt_word=rbtgoffer",
                "source": "ML_LINK_GENERATOR",
                "product_reference": "MLB999",
            },
            provider="stub",
            request=request,
        )
    assert wrong_product.value.error.code == AFFILIATE_LINK_URL_INVALID

    with pytest.raises(RadarException) as unknown_source:
        parse_affiliate_link_response(
            {
                "affiliate_url": "https://www.mercadolivre.com.br/social/x?matt_word=rbtgoffer",
                "source": "SOMETHING_ELSE",
                "product_reference": "MLB123",
            },
            provider="stub",
            request=request,
        )
    assert unknown_source.value.error.code == AFFILIATE_LINK_URL_INVALID


def test_parse_accepts_a_matching_literal_link() -> None:
    request = _request()
    url = "https://www.mercadolivre.com.br/social/x/MLB123?matt_word=rbtgoffer"

    outcome = parse_affiliate_link_response(
        {"affiliate_url": url, "source": "ML_LINK_GENERATOR", "product_reference": "MLB123"},
        provider="stub",
        request=request,
    )

    assert outcome.affiliate_url == url
    assert outcome.generation_method is LinkGenerationMethod.ML_LINK_GENERATOR
    assert outcome.product_reference == "MLB123"


def test_build_link_is_its_own_entity_with_original_url_method_and_tracking() -> None:
    request = _request()
    outcome = parse_affiliate_link_response(
        {
            "affiliate_url": "https://www.mercadolivre.com.br/social/x/MLB123?matt_word=rbtgoffer",
            "source": "ML_LINK_GENERATOR",
            "product_reference": "MLB123",
        },
        provider="stub",
        request=request,
    )

    link = build_affiliate_link(
        request=request,
        outcome=outcome,
        correlation_id="cid-link",
        audit_event_id="aud_1",
        created_at=FIXED_NOW,
        affiliate_link_id="lnk_1",
    )

    contract = link.to_contract()
    assert contract["affiliate_link_id"] == "lnk_1"
    assert contract["opportunity_id"] == "opp_1"
    assert contract["original_url"] == "https://www.mercadolivre.com.br/p/MLB123"
    assert contract["generation_method"] == "ML_LINK_GENERATOR"
    assert contract["tracking"]["tracking_context_id"] == "trk_1"
    assert contract["tracking"]["external_label"] == "rbtgoffer"
    assert contract["productive"] is True


def test_fake_link_is_not_productive_and_require_productive_refuses() -> None:
    request = _request()
    outcome = parse_affiliate_link_response(
        {
            "affiliate_url": "https://www.mercadolivre.com.br/social/radar-fake/MLB123?matt_word=rbtgoffer",
            "source": "FAKE",
            "product_reference": "MLB123",
        },
        provider="fake",
        request=request,
    )
    link = build_affiliate_link(
        request=request,
        outcome=outcome,
        correlation_id="cid-link",
        audit_event_id="aud_1",
        created_at=FIXED_NOW,
        affiliate_link_id="lnk_1",
    )

    assert link.generation_method is LinkGenerationMethod.FAKE
    assert link.productive is False
    assert link.to_contract()["productive"] is False
    with pytest.raises(RadarException) as refused:
        require_productive(link)
    assert refused.value.error.code == affiliate_link_not_productive_error("lnk_1").error.code


def test_build_link_requires_a_configured_tracking_context() -> None:
    mapping = APPROVED_TRACKING_LABEL_MAPPING
    tracking = build_tracking_context(
        opportunity_id="opp_1",
        marketplace=Marketplace.MERCADO_LIVRE,
        brand=Brand.RADAR_BEAUTY,
        internal_reference="RADAR_BEAUTY:MERCADO_LIVRE",
        mapping=mapping,
    )
    request = AffiliateLinkRequest(
        opportunity_id="opp_1",
        marketplace=Marketplace.MERCADO_LIVRE,
        original_url="https://www.mercadolivre.com.br/p/MLB123",
        external_id="MLB123",
        tracking=tracking,
    )
    outcome = parse_affiliate_link_response(
        {
            "affiliate_url": "https://www.mercadolivre.com.br/social/x/MLB123?matt_word=rbtgoffer",
            "source": "FAKE",
            "product_reference": "MLB123",
        },
        provider="fake",
        request=request,
    )

    with pytest.raises(RadarException) as error:
        build_affiliate_link(
            request=request,
            outcome=outcome,
            correlation_id="cid-link",
            audit_event_id="aud_1",
            created_at=FIXED_NOW,
        )
    assert error.value.error.code == affiliate_link_input_invalid_error("x").error.code
