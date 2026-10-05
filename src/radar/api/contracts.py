"""HTTP contracts for manual capture (SPEC-01, ``docs/04_DATA_CONTRACTS.md``).

The Pydantic models are the versioned public boundary. They are intentionally
strict (``extra="forbid"``) and reject known sensitive field names anywhere in
the payload before any domain work happens, so a malformed or sensitive capture
never reaches persistence.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic_core import PydanticCustomError

from radar.domain.capture import (
    CAPTURE_SCHEMA_VERSION,
    CaptureIntake,
    CaptureSource,
    Marketplace,
    find_sensitive_fields,
)

#: Request/response header carrying the pipeline Correlation ID (AUT-040).
CORRELATION_HEADER = "X-Correlation-ID"

#: Custom validator type used to classify a rejected sensitive field.
SENSITIVE_FIELD_ERROR_TYPE = "radar_sensitive_field"


class _StrictContract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CaptureSellerContract(_StrictContract):
    name: str | None = Field(default=None, max_length=512)
    id: str | None = Field(default=None, max_length=128)


class CaptureProductContract(_StrictContract):
    external_id: str = Field(min_length=1, max_length=128)
    title: str | None = Field(default=None, max_length=512)
    url: str | None = Field(default=None, max_length=2048)


class CaptureOfferContract(_StrictContract):
    current_price: str | int
    original_price: str | int | None = None
    sales_count: int | None = Field(default=None, ge=0)
    seller: CaptureSellerContract | None = None

    @field_validator("current_price", "original_price", mode="before")
    @classmethod
    def _reject_boolean_money(cls, value: object) -> object:
        # ``bool`` is a subclass of ``int``; a JSON ``true`` must never become a price.
        if isinstance(value, bool):
            raise ValueError("Valores monetários devem ser strings decimais")
        return value


class ManualCaptureContract(_StrictContract):
    """Versioned ``ManualCapture`` input received by the public boundary."""

    schema_version: str = CAPTURE_SCHEMA_VERSION
    marketplace: Marketplace
    source: CaptureSource
    product: CaptureProductContract
    offer: CaptureOfferContract
    captured_at: datetime | None = None

    @model_validator(mode="before")
    @classmethod
    def _reject_sensitive_fields(cls, data: Any) -> Any:
        if isinstance(data, Mapping):
            hits = find_sensitive_fields(data)
            if hits:
                raise PydanticCustomError(
                    SENSITIVE_FIELD_ERROR_TYPE,
                    "Campos sensíveis não são aceitos na captura",
                    {"fields": list(hits)},
                )
        return data

    def to_intake(self) -> CaptureIntake:
        """Map the validated contract to the framework-free domain intake."""

        seller = self.offer.seller
        return CaptureIntake(
            marketplace=self.marketplace,
            source=self.source,
            external_id=self.product.external_id,
            current_price=self.offer.current_price,
            original_price=self.offer.original_price,
            title=self.product.title,
            url=self.product.url,
            sales_count=self.offer.sales_count,
            seller_name=seller.name if seller is not None else None,
            seller_id=seller.id if seller is not None else None,
            captured_at=self.captured_at,
            schema_version=self.schema_version,
        )
