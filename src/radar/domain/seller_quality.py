"""Deterministic Seller Quality composition (RDR-024).

This module implements the *Seller Quality* component of the Deal Score
described in ``docs/05_SCORING_ENGINE.md``. The approved macro weights are
frozen: ``marketplace reputation 40%``, ``rating 25%``, ``sales history 20%``
and ``official/trusted status 15%`` (AUT-046, AUT-050). Each component is
resolved independently and carries the origin of its signal.

Two rules are load-bearing:

* the SDD freezes the weights but does **not** calibrate the normalization of the
  four signals. Normalization is therefore operational, versioned and hashed
  configuration (AUT-045, AUT-207), exactly like the brand taxonomy: a raw value
  without a configured mapping is an explicit gap (``score=None``) instead of an
  invented constant;
* absent data never becomes an arbitrary zero (``docs/05_SCORING_ENGINE.md``).
  A missing signal yields ``score=None`` with a ``SELLER_QUALITY_MISSING_DATA``
  warning for the Confidence Engine (RDR-029); the returned ``seller_quality`` is
  a partial score computed over the calibrated components only.

Invalid or contradictory seller data also produces explicit warnings instead of
silently bending the score.

The module is framework-free (no FastAPI/SQLAlchemy/Chrome) so the domain stays
independent from infrastructure (AUT-397).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from enum import StrEnum
from itertools import pairwise
from typing import Any

from radar.domain.errors import RadarError, RadarException

#: Version of the public Seller Quality contract.
SELLER_QUALITY_SCHEMA_VERSION = "1.0"

#: Schema version of the normalization configuration document.
SELLER_QUALITY_NORMALIZATION_SCHEMA_VERSION = "1.0"

#: Scoring version stored alongside the breakdown (``docs/05_SCORING_ENGINE.md``).
SELLER_QUALITY_SCORING_VERSION = "seller-quality-1.0"

#: Error codes (see ``docs/ERROR_CATALOG.md``).
SELLER_QUALITY_INPUT_INVALID = "RAD-CAP-009"
SELLER_QUALITY_NORMALIZATION_INVALID = "RAD-CFG-006"

#: Approved component weights, frozen by ``docs/05_SCORING_ENGINE.md``.
WEIGHT_MARKETPLACE_REPUTATION = 40
WEIGHT_RATING = 25
WEIGHT_SALES_HISTORY = 20
WEIGHT_TRUSTED_STATUS = 15

#: Warning codes emitted by the composition.
WARNING_MISSING_DATA = "SELLER_QUALITY_MISSING_DATA"
WARNING_INVALID_DATA = "SELLER_QUALITY_INVALID_DATA"
WARNING_NORMALIZATION_NOT_DEFINED = "SELLER_QUALITY_NORMALIZATION_NOT_DEFINED"
WARNING_CONTRADICTION = "SELLER_QUALITY_CONTRADICTION"

#: Human-readable reason attached to each component.
REASON_OK = "ok"
REASON_MISSING_DATA = "missing_data"
REASON_INVALID_DATA = "invalid_data"
REASON_NORMALIZATION_NOT_DEFINED = "normalization_not_defined"


class SellerQualityComponentName(StrEnum):
    """Canonical component names of the Seller Quality breakdown."""

    MARKETPLACE_REPUTATION = "marketplace_reputation"
    RATING = "rating"
    SALES_HISTORY = "sales_history"
    TRUSTED_STATUS = "trusted_status"


class SellerQualityError(RadarException):
    """Raised when a Seller Quality request cannot be satisfied."""


class SellerQualityNormalizationInvalidError(RadarException):
    """Raised when the Seller Quality normalization config is invalid."""


def seller_quality_input_invalid_error(
    message: str, *, context: Mapping[str, Any] | None = None
) -> SellerQualityError:
    """Build the structured error for invalid Seller Quality inputs."""

    return SellerQualityError(
        RadarError(
            code=SELLER_QUALITY_INPUT_INVALID,
            message=message,
            retryable=False,
            action="Corrigir os parâmetros da avaliação de vendedor e consultar novamente",
            context=dict(context or {}),
        )
    )


def _normalization_invalid(
    message: str, *, context: Mapping[str, Any] | None = None
) -> SellerQualityNormalizationInvalidError:
    return SellerQualityNormalizationInvalidError(
        RadarError(
            code=SELLER_QUALITY_NORMALIZATION_INVALID,
            message=message,
            retryable=False,
            action="Corrigir o arquivo de normalização de Seller Quality e validar novamente",
            context=dict(context or {}),
        )
    )


def normalize_label(value: str | None) -> str | None:
    """Normalize a categorical seller label into a comparable key.

    Lowercases, collapses whitespace and treats ``_``/``-`` as spaces so
    ``Gold`` and ``gold`` resolve to the same key. A blank value yields ``None``
    so a missing/empty label stays explicit.
    """

    if value is None:
        return None
    cleaned = " ".join(str(value).strip().lower().replace("_", " ").replace("-", " ").split())
    return cleaned or None


@dataclass(frozen=True, slots=True)
class ScoreBand:
    """One inclusive band of a numeric normalization (``min <= value <= max``).

    ``maximum`` is ``None`` for an open-ended band. Bands are stored sorted and
    non-overlapping by :func:`build_seller_quality_normalization`.
    """

    minimum: Decimal
    maximum: Decimal | None
    score: int

    def matches(self, value: Decimal) -> bool:
        if value < self.minimum:
            return False
        return self.maximum is None or value <= self.maximum


@dataclass(frozen=True, slots=True)
class SellerSignal[T]:
    """One seller signal and the origin it was read from."""

    value: T
    source: str


@dataclass(frozen=True, slots=True)
class SellerFacts:
    """Seller identity and the raw signals available for one Candidate."""

    seller_id: str | None = None
    seller_name: str | None = None
    reputation: SellerSignal[str] | None = None
    rating: SellerSignal[Decimal] | None = None
    sales_count: SellerSignal[int] | None = None
    trusted: SellerSignal[bool] | None = None

    @property
    def has_identity(self) -> bool:
        return bool((self.seller_id or "").strip() or (self.seller_name or "").strip())

    @property
    def present_signals(self) -> tuple[SellerQualityComponentName, ...]:
        present: list[SellerQualityComponentName] = []
        if self.reputation is not None:
            present.append(SellerQualityComponentName.MARKETPLACE_REPUTATION)
        if self.rating is not None:
            present.append(SellerQualityComponentName.RATING)
        if self.sales_count is not None:
            present.append(SellerQualityComponentName.SALES_HISTORY)
        if self.trusted is not None:
            present.append(SellerQualityComponentName.TRUSTED_STATUS)
        return tuple(present)


@dataclass(frozen=True, slots=True)
class SellerQualityNormalization:
    """Versioned, hashed normalization of raw seller signals to ``0..100``.

    ``reputation_scores`` maps a normalized label to its approved score;
    ``rating_bands``/``sales_bands`` are inclusive numeric bands; and
    ``trusted_scores`` maps the boolean official/trusted status. A raw value with
    no entry is an explicit gap, never an invented constant.
    """

    normalization_version: str
    content_hash: str
    reputation_scores: Mapping[str, int] = field(default_factory=dict)
    rating_bands: tuple[ScoreBand, ...] = ()
    sales_bands: tuple[ScoreBand, ...] = ()
    trusted_scores: Mapping[bool, int] = field(default_factory=dict)

    def score_reputation(self, label: str | None) -> int | None:
        normalized = normalize_label(label)
        if normalized is None:
            return None
        return self.reputation_scores.get(normalized)

    def score_rating(self, rating: Decimal) -> int | None:
        return _match_band(self.rating_bands, rating)

    def score_sales(self, sales_count: int) -> int | None:
        return _match_band(self.sales_bands, Decimal(sales_count))

    def score_trusted(self, trusted: bool) -> int | None:
        return self.trusted_scores.get(bool(trusted))


def _match_band(bands: tuple[ScoreBand, ...], value: Decimal) -> int | None:
    for band in bands:
        if band.matches(value):
            return band.score
    return None


@dataclass(frozen=True, slots=True)
class SellerQualityWarning:
    """Explicit, non-fatal gap emitted by the composition."""

    code: str
    message: str
    context: Mapping[str, Any] = field(default_factory=dict)

    def to_contract(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.context:
            payload["context"] = dict(self.context)
        return payload


@dataclass(frozen=True, slots=True)
class SellerQualityComponent:
    """One explainable component of the Seller Quality breakdown."""

    name: SellerQualityComponentName
    weight: int
    score: int | None
    calibrated: bool
    raw: Any = None
    source: str | None = None
    reason: str = REASON_OK

    def to_contract(self) -> dict[str, Any]:
        return {
            "name": self.name.value,
            "weight": self.weight,
            "score": self.score,
            "calibrated": self.calibrated,
            "raw": _serialize_raw(self.raw),
            "source": self.source,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class SellerQualityResult:
    """Queryable, versioned Seller Quality for one Candidate."""

    candidate_id: str
    seller_id: str | None
    seller_name: str | None
    seller_quality: int | None
    fully_calibrated: bool
    weight_covered: int
    normalization_version: str
    normalization_hash: str
    components: tuple[SellerQualityComponent, ...]
    warnings: tuple[SellerQualityWarning, ...]

    def component(self, name: SellerQualityComponentName) -> SellerQualityComponent:
        """Return one component by name (every component is always present)."""

        for item in self.components:
            if item.name is name:
                return item
        raise KeyError(name.value)

    def to_contract(self) -> dict[str, Any]:
        return {
            "schema_version": SELLER_QUALITY_SCHEMA_VERSION,
            "status": "EVALUATED",
            "candidate_id": self.candidate_id,
            "seller": {"id": self.seller_id, "name": self.seller_name},
            "seller_quality": self.seller_quality,
            "fully_calibrated": self.fully_calibrated,
            "weight_covered": self.weight_covered,
            "scoring_version": SELLER_QUALITY_SCORING_VERSION,
            "normalization_version": self.normalization_version,
            "normalization_hash": self.normalization_hash,
            "components": [component.to_contract() for component in self.components],
            "warnings": [warning.to_contract() for warning in self.warnings],
        }


def _serialize_raw(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, str)):
        return value
    return None if value is None else str(value)


def _missing_component(name: SellerQualityComponentName, weight: int) -> SellerQualityComponent:
    return SellerQualityComponent(
        name=name,
        weight=weight,
        score=None,
        calibrated=False,
        raw=None,
        source=None,
        reason=REASON_MISSING_DATA,
    )


def _missing_warning(name: SellerQualityComponentName) -> SellerQualityWarning:
    return SellerQualityWarning(
        code=WARNING_MISSING_DATA,
        message="Sinal de vendedor ausente; não vira zero e afeta o Confidence",
        context={"component": name.value},
    )


def _invalid_warning(
    name: SellerQualityComponentName, raw: Any, reason: str
) -> SellerQualityWarning:
    return SellerQualityWarning(
        code=WARNING_INVALID_DATA,
        message="Sinal de vendedor inválido; ignorado no cálculo e reportado para revisão",
        context={"component": name.value, "raw": _serialize_raw(raw), "reason": reason},
    )


def _gap_warning(name: SellerQualityComponentName, raw: Any) -> SellerQualityWarning:
    return SellerQualityWarning(
        code=WARNING_NORMALIZATION_NOT_DEFINED,
        message=(
            "Sinal sem normalização configurada; lacuna explícita sem constante "
            "inventada (calibração humana necessária)"
        ),
        context={"component": name.value, "raw": _serialize_raw(raw)},
    )


def _evaluate_reputation(
    signal: SellerSignal[str] | None,
    normalization: SellerQualityNormalization,
) -> tuple[SellerQualityComponent, SellerQualityWarning | None]:
    name = SellerQualityComponentName.MARKETPLACE_REPUTATION
    weight = WEIGHT_MARKETPLACE_REPUTATION
    if signal is None:
        return _missing_component(name, weight), _missing_warning(name)
    if normalize_label(signal.value) is None:
        return (
            SellerQualityComponent(
                name=name,
                weight=weight,
                score=None,
                calibrated=False,
                raw=signal.value,
                source=signal.source,
                reason=REASON_INVALID_DATA,
            ),
            _invalid_warning(name, signal.value, "empty_label"),
        )
    score = normalization.score_reputation(signal.value)
    if score is None:
        return (
            SellerQualityComponent(
                name=name,
                weight=weight,
                score=None,
                calibrated=False,
                raw=signal.value,
                source=signal.source,
                reason=REASON_NORMALIZATION_NOT_DEFINED,
            ),
            _gap_warning(name, signal.value),
        )
    return (
        SellerQualityComponent(
            name=name,
            weight=weight,
            score=score,
            calibrated=True,
            raw=signal.value,
            source=signal.source,
            reason=REASON_OK,
        ),
        None,
    )


def _evaluate_rating(
    signal: SellerSignal[Decimal] | None,
    normalization: SellerQualityNormalization,
) -> tuple[SellerQualityComponent, SellerQualityWarning | None]:
    name = SellerQualityComponentName.RATING
    weight = WEIGHT_RATING
    if signal is None:
        return _missing_component(name, weight), _missing_warning(name)
    value = signal.value
    if not value.is_finite() or value < 0:
        return (
            SellerQualityComponent(
                name=name,
                weight=weight,
                score=None,
                calibrated=False,
                raw=value,
                source=signal.source,
                reason=REASON_INVALID_DATA,
            ),
            _invalid_warning(name, value, "out_of_range"),
        )
    score = normalization.score_rating(value)
    if score is None:
        return (
            SellerQualityComponent(
                name=name,
                weight=weight,
                score=None,
                calibrated=False,
                raw=value,
                source=signal.source,
                reason=REASON_NORMALIZATION_NOT_DEFINED,
            ),
            _gap_warning(name, value),
        )
    return (
        SellerQualityComponent(
            name=name,
            weight=weight,
            score=score,
            calibrated=True,
            raw=value,
            source=signal.source,
            reason=REASON_OK,
        ),
        None,
    )


def _evaluate_sales(
    signal: SellerSignal[int] | None,
    normalization: SellerQualityNormalization,
) -> tuple[SellerQualityComponent, SellerQualityWarning | None]:
    name = SellerQualityComponentName.SALES_HISTORY
    weight = WEIGHT_SALES_HISTORY
    if signal is None:
        return _missing_component(name, weight), _missing_warning(name)
    value = signal.value
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return (
            SellerQualityComponent(
                name=name,
                weight=weight,
                score=None,
                calibrated=False,
                raw=value,
                source=signal.source,
                reason=REASON_INVALID_DATA,
            ),
            _invalid_warning(name, value, "out_of_range"),
        )
    score = normalization.score_sales(value)
    if score is None:
        return (
            SellerQualityComponent(
                name=name,
                weight=weight,
                score=None,
                calibrated=False,
                raw=value,
                source=signal.source,
                reason=REASON_NORMALIZATION_NOT_DEFINED,
            ),
            _gap_warning(name, value),
        )
    return (
        SellerQualityComponent(
            name=name,
            weight=weight,
            score=score,
            calibrated=True,
            raw=value,
            source=signal.source,
            reason=REASON_OK,
        ),
        None,
    )


def _evaluate_trusted(
    signal: SellerSignal[bool] | None,
    normalization: SellerQualityNormalization,
) -> tuple[SellerQualityComponent, SellerQualityWarning | None]:
    name = SellerQualityComponentName.TRUSTED_STATUS
    weight = WEIGHT_TRUSTED_STATUS
    if signal is None:
        return _missing_component(name, weight), _missing_warning(name)
    if not isinstance(signal.value, bool):
        return (
            SellerQualityComponent(
                name=name,
                weight=weight,
                score=None,
                calibrated=False,
                raw=signal.value,
                source=signal.source,
                reason=REASON_INVALID_DATA,
            ),
            _invalid_warning(name, signal.value, "out_of_range"),
        )
    score = normalization.score_trusted(signal.value)
    if score is None:
        return (
            SellerQualityComponent(
                name=name,
                weight=weight,
                score=None,
                calibrated=False,
                raw=signal.value,
                source=signal.source,
                reason=REASON_NORMALIZATION_NOT_DEFINED,
            ),
            _gap_warning(name, signal.value),
        )
    return (
        SellerQualityComponent(
            name=name,
            weight=weight,
            score=score,
            calibrated=True,
            raw=signal.value,
            source=signal.source,
            reason=REASON_OK,
        ),
        None,
    )


def compute_seller_quality(
    *,
    candidate_id: str,
    facts: SellerFacts,
    normalization: SellerQualityNormalization,
) -> SellerQualityResult:
    """Compute the deterministic Seller Quality breakdown.

    The function never mutates its inputs and is reproducible for the same facts
    and normalization version. Missing, invalid or uncalibrated signals are
    reported explicitly and excluded from the partial aggregate instead of being
    counted as zero.
    """

    warnings: list[SellerQualityWarning] = []

    present = facts.present_signals
    if present and not facts.has_identity:
        warnings.append(
            SellerQualityWarning(
                code=WARNING_CONTRADICTION,
                message=(
                    "Sinais de vendedor informados sem identidade de vendedor; "
                    "dados contraditórios para revisão"
                ),
                context={"components": [name.value for name in present]},
            )
        )

    components: list[SellerQualityComponent] = []
    for component, warning in (
        _evaluate_reputation(facts.reputation, normalization),
        _evaluate_rating(facts.rating, normalization),
        _evaluate_sales(facts.sales_count, normalization),
        _evaluate_trusted(facts.trusted, normalization),
    ):
        components.append(component)
        if warning is not None:
            warnings.append(warning)

    calibrated_components = [
        component
        for component in components
        if component.calibrated and component.score is not None
    ]
    weight_covered = sum(component.weight for component in calibrated_components)
    if calibrated_components and weight_covered > 0:
        weighted = sum(
            Decimal(component.score or 0) * component.weight for component in calibrated_components
        )
        seller_quality: int | None = int(
            (weighted / Decimal(weight_covered)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        )
    else:
        seller_quality = None

    return SellerQualityResult(
        candidate_id=candidate_id,
        seller_id=facts.seller_id,
        seller_name=facts.seller_name,
        seller_quality=seller_quality,
        fully_calibrated=all(component.calibrated for component in components),
        weight_covered=weight_covered,
        normalization_version=normalization.normalization_version,
        normalization_hash=normalization.content_hash,
        components=tuple(components),
        warnings=tuple(warnings),
    )


def _content_hash(document: Mapping[str, Any]) -> str:
    canonical = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _require_score(value: Any, *, component: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 100:
        raise _normalization_invalid(
            "score de normalização deve ser inteiro entre 0 e 100",
            context={
                "component": component,
                "score": value if isinstance(value, (int, str)) else None,
            },
        )
    return value


def _to_decimal(value: Any, *, component: str, field_name: str) -> Decimal:
    if isinstance(value, (bool, float)):
        raise _normalization_invalid(
            "limite de banda deve ser decimal/inteiro, não float binário",
            context={"component": component, "field": field_name},
        )
    if isinstance(value, Decimal):
        amount = value
    elif isinstance(value, int):
        amount = Decimal(value)
    elif isinstance(value, str):
        try:
            amount = Decimal(value.strip())
        except InvalidOperation as exc:
            raise _normalization_invalid(
                "limite de banda inválido",
                context={"component": component, "field": field_name},
            ) from exc
    else:
        raise _normalization_invalid(
            "limite de banda inválido",
            context={"component": component, "field": field_name},
        )
    if not amount.is_finite() or amount < 0:
        raise _normalization_invalid(
            "limite de banda deve ser finito e >= 0",
            context={"component": component, "field": field_name},
        )
    return amount


def _build_bands(value: Any, *, component: str) -> tuple[ScoreBand, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise _normalization_invalid(
            "bandas de normalização devem ser uma lista", context={"component": component}
        )
    bands: list[ScoreBand] = []
    for entry in value:
        if not isinstance(entry, Mapping):
            raise _normalization_invalid(
                "banda de normalização deve ser um objeto", context={"component": component}
            )
        minimum = _to_decimal(entry.get("min"), component=component, field_name="min")
        maximum = (
            None
            if entry.get("max") is None
            else _to_decimal(entry.get("max"), component=component, field_name="max")
        )
        if maximum is not None and maximum < minimum:
            raise _normalization_invalid(
                "max da banda deve ser >= min",
                context={"component": component, "min": str(minimum), "max": str(maximum)},
            )
        score = _require_score(entry.get("score"), component=component)
        bands.append(ScoreBand(minimum=minimum, maximum=maximum, score=score))
    bands.sort(key=lambda band: band.minimum)
    for previous, current in pairwise(bands):
        if previous.maximum is None or previous.maximum >= current.minimum:
            raise _normalization_invalid(
                "bandas de normalização não podem se sobrepor",
                context={"component": component},
            )
    return tuple(bands)


def _build_label_scores(value: Any, *, component: str) -> dict[str, int]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise _normalization_invalid(
            "mapa de labels deve ser um objeto", context={"component": component}
        )
    scores: dict[str, int] = {}
    for raw_label, score in value.items():
        normalized = normalize_label(str(raw_label))
        if normalized is None:
            raise _normalization_invalid(
                "label de normalização vazio", context={"component": component}
            )
        scores[normalized] = _require_score(score, component=component)
    return scores


def _build_trusted_scores(value: Any) -> dict[bool, int]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise _normalization_invalid(
            "trusted_status deve ser um objeto", context={"component": "trusted_status"}
        )
    scores: dict[bool, int] = {}
    for raw_key, score in value.items():
        key = str(raw_key).strip().lower()
        if key not in {"true", "false"}:
            raise _normalization_invalid(
                "trusted_status aceita apenas as chaves true/false",
                context={"component": "trusted_status", "key": str(raw_key)},
            )
        scores[key == "true"] = _require_score(score, component="trusted_status")
    return scores


def _band_document(bands: tuple[ScoreBand, ...]) -> list[dict[str, Any]]:
    return [
        {
            "min": str(band.minimum),
            "max": None if band.maximum is None else str(band.maximum),
            "score": band.score,
        }
        for band in bands
    ]


def build_seller_quality_normalization(
    document: Mapping[str, Any],
) -> SellerQualityNormalization:
    """Build and validate a normalization config from a plain document.

    Raises :class:`SellerQualityNormalizationInvalidError` (``RAD-CFG-006``) on a
    missing version, an out-of-range score, an invalid band or overlapping bands.
    """

    if not isinstance(document, Mapping):
        raise _normalization_invalid("Normalização de Seller Quality deve ser um objeto")

    schema_version = document.get("schema_version")
    if schema_version is not None and str(schema_version) != (
        SELLER_QUALITY_NORMALIZATION_SCHEMA_VERSION
    ):
        raise _normalization_invalid(
            "schema_version de normalização não suportada",
            context={"schema_version": str(schema_version)},
        )

    version = str(document.get("normalization_version") or "").strip()
    if not version:
        raise _normalization_invalid("normalization_version é obrigatório")

    reputation_scores = _build_label_scores(
        document.get("marketplace_reputation"), component="marketplace_reputation"
    )
    rating_bands = _build_bands(document.get("rating"), component="rating")
    sales_bands = _build_bands(document.get("sales_history"), component="sales_history")
    trusted_scores = _build_trusted_scores(document.get("trusted_status"))

    normalized_document: dict[str, Any] = {
        "schema_version": SELLER_QUALITY_NORMALIZATION_SCHEMA_VERSION,
        "normalization_version": version,
        "marketplace_reputation": dict(sorted(reputation_scores.items())),
        "rating": _band_document(rating_bands),
        "sales_history": _band_document(sales_bands),
        "trusted_status": {
            ("true" if key else "false"): trusted_scores[key] for key in sorted(trusted_scores)
        },
    }
    return SellerQualityNormalization(
        normalization_version=version,
        content_hash=_content_hash(normalized_document),
        reputation_scores=reputation_scores,
        rating_bands=rating_bands,
        sales_bands=sales_bands,
        trusted_scores=trusted_scores,
    )


#: Approved baseline normalization (RDR-024).
#:
#: The SDD freezes the Seller Quality weights but does **not** calibrate the
#: normalization of the four signals. The baseline is therefore intentionally
#: empty: every signal is reported as an explicit calibration gap
#: (``SELLER_QUALITY_NORMALIZATION_NOT_DEFINED``) until a human-approved,
#: versioned config supplies the mappings. No value is invented here.
APPROVED_SELLER_QUALITY_DOCUMENT: dict[str, Any] = {
    "schema_version": SELLER_QUALITY_NORMALIZATION_SCHEMA_VERSION,
    "normalization_version": "seller-quality-normalization-1.0",
}

#: The approved baseline used when no operator file is configured.
APPROVED_SELLER_QUALITY_NORMALIZATION: SellerQualityNormalization = (
    build_seller_quality_normalization(APPROVED_SELLER_QUALITY_DOCUMENT)
)


__all__ = [
    "APPROVED_SELLER_QUALITY_DOCUMENT",
    "APPROVED_SELLER_QUALITY_NORMALIZATION",
    "REASON_INVALID_DATA",
    "REASON_MISSING_DATA",
    "REASON_NORMALIZATION_NOT_DEFINED",
    "REASON_OK",
    "SELLER_QUALITY_INPUT_INVALID",
    "SELLER_QUALITY_NORMALIZATION_INVALID",
    "SELLER_QUALITY_NORMALIZATION_SCHEMA_VERSION",
    "SELLER_QUALITY_SCHEMA_VERSION",
    "SELLER_QUALITY_SCORING_VERSION",
    "WARNING_CONTRADICTION",
    "WARNING_INVALID_DATA",
    "WARNING_MISSING_DATA",
    "WARNING_NORMALIZATION_NOT_DEFINED",
    "WEIGHT_MARKETPLACE_REPUTATION",
    "WEIGHT_RATING",
    "WEIGHT_SALES_HISTORY",
    "WEIGHT_TRUSTED_STATUS",
    "ScoreBand",
    "SellerFacts",
    "SellerQualityComponent",
    "SellerQualityComponentName",
    "SellerQualityError",
    "SellerQualityNormalization",
    "SellerQualityNormalizationInvalidError",
    "SellerQualityResult",
    "SellerQualityWarning",
    "SellerSignal",
    "build_seller_quality_normalization",
    "compute_seller_quality",
    "normalize_label",
    "seller_quality_input_invalid_error",
]
