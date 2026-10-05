"""Deterministic, category-versioned Demand normalization (RDR-025).

This module implements the *Demand* component of the Deal Score described in
``docs/05_SCORING_ENGINE.md``. Demand may use ``sales_count``, ``rating_count``,
a ``trend`` signal, an ``affiliate portal`` signal and ``badges``; the SDD
requires the normalization to evolve by category but does **not** calibrate the
mapping or the composition weights. Those are therefore operational, versioned
and hashed configuration (AUT-045, AUT-050, AUT-207), exactly like the brand
taxonomy and the Seller Quality normalization: a signal without a configured
mapping/weight is an explicit gap instead of an invented constant.

Two rules are load-bearing:

* absent data never becomes an arbitrary zero: a missing signal is
  ``score=None`` with a ``DEMAND_MISSING_DATA`` warning for the Confidence Engine
  (RDR-029), and the returned ``demand`` is a partial score computed only over
  the calibrated components. The module never invents volume or conversions;
* an incomplete category configuration is reported as ``fully_calibrated=False``
  with explicit warnings, so a result is never presented as validated when the
  normalization that produced it is incomplete.

Each component records the origin (``source``) of the signal it was read from so
``sales/rating counts``, trends and badges stay traceable.

The module is framework-free (no FastAPI/SQLAlchemy/Chrome) and never calls AI
to compute a score (AUT-031, AUT-397). The ``category`` consumed here is the
canonical category already resolved by the versioned brand taxonomy (RDR-022);
this module does not resolve raw categories itself.
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
from radar.domain.taxonomy import CanonicalCategory

#: Version of the public Demand contract.
DEMAND_SCHEMA_VERSION = "1.0"

#: Schema version of the Demand normalization configuration document.
DEMAND_NORMALIZATION_SCHEMA_VERSION = "1.0"

#: Scoring version stored alongside the breakdown (``docs/05_SCORING_ENGINE.md``).
DEMAND_SCORING_VERSION = "demand-1.0"

#: Error codes (see ``docs/ERROR_CATALOG.md``).
DEMAND_INPUT_INVALID = "RAD-CAP-010"
DEMAND_NORMALIZATION_INVALID = "RAD-CFG-007"

#: Warning codes emitted by the composition.
WARNING_MISSING_DATA = "DEMAND_MISSING_DATA"
WARNING_INVALID_DATA = "DEMAND_INVALID_DATA"
WARNING_NORMALIZATION_NOT_DEFINED = "DEMAND_NORMALIZATION_NOT_DEFINED"
WARNING_CATEGORY_NOT_DEFINED = "DEMAND_CATEGORY_NOT_DEFINED"

#: Human-readable reason attached to each component.
REASON_OK = "ok"
REASON_MISSING_DATA = "missing_data"
REASON_INVALID_DATA = "invalid_data"
REASON_NORMALIZATION_NOT_DEFINED = "normalization_not_defined"

#: The set of known canonical category values, used to validate demand files.
_CANONICAL_CATEGORIES: frozenset[str] = frozenset(category.value for category in CanonicalCategory)


class DemandSignalName(StrEnum):
    """Canonical signals of the Demand breakdown (``docs/05_SCORING_ENGINE.md``)."""

    SALES_COUNT = "sales_count"
    RATING_COUNT = "rating_count"
    TREND = "trend"
    AFFILIATE_PORTAL = "affiliate_portal"
    BADGES = "badges"


class DemandError(RadarException):
    """Raised when a Demand request cannot be satisfied."""


class DemandNormalizationInvalidError(RadarException):
    """Raised when the Demand normalization config is invalid."""


def demand_input_invalid_error(
    message: str, *, context: Mapping[str, Any] | None = None
) -> DemandError:
    """Build the structured error for invalid Demand inputs."""

    return DemandError(
        RadarError(
            code=DEMAND_INPUT_INVALID,
            message=message,
            retryable=False,
            action="Corrigir os sinais da avaliação de demanda e consultar novamente",
            context=dict(context or {}),
        )
    )


def _normalization_invalid(
    message: str, *, context: Mapping[str, Any] | None = None
) -> DemandNormalizationInvalidError:
    return DemandNormalizationInvalidError(
        RadarError(
            code=DEMAND_NORMALIZATION_INVALID,
            message=message,
            retryable=False,
            action="Corrigir o arquivo de normalização de Demand e validar novamente",
            context=dict(context or {}),
        )
    )


def normalize_label(value: str | None) -> str | None:
    """Normalize a categorical demand label into a comparable key.

    Lowercases, collapses whitespace and treats ``_``/``-`` as spaces so
    ``Best_Seller`` and ``best seller`` resolve to the same key. A blank value
    yields ``None`` so a missing/empty label stays explicit.
    """

    if value is None:
        return None
    cleaned = " ".join(str(value).strip().lower().replace("_", " ").replace("-", " ").split())
    return cleaned or None


@dataclass(frozen=True, slots=True)
class ScoreBand:
    """One inclusive band of a numeric normalization (``min <= value <= max``).

    ``maximum`` is ``None`` for an open-ended band. Bands are stored sorted and
    non-overlapping by :func:`build_demand_normalization`.
    """

    minimum: Decimal
    maximum: Decimal | None
    score: int

    def matches(self, value: Decimal) -> bool:
        if value < self.minimum:
            return False
        return self.maximum is None or value <= self.maximum


@dataclass(frozen=True, slots=True)
class DemandSignal[T]:
    """One demand signal and the origin it was read from."""

    value: T
    source: str


@dataclass(frozen=True, slots=True)
class DemandCategoryNormalization:
    """Versioned normalization and composition weights of one category.

    ``weights`` maps each signal to its approved composition weight and the
    per-signal mappings normalize the raw value to ``0..100``. A signal without a
    weight or without a mapping is an explicit calibration gap, never an invented
    constant.
    """

    category: str
    weights: Mapping[DemandSignalName, int] = field(default_factory=dict)
    sales_count_bands: tuple[ScoreBand, ...] = ()
    rating_count_bands: tuple[ScoreBand, ...] = ()
    trend_scores: Mapping[str, int] = field(default_factory=dict)
    affiliate_portal_scores: Mapping[str, int] = field(default_factory=dict)
    badge_scores: Mapping[str, int] = field(default_factory=dict)

    def weight_for(self, name: DemandSignalName) -> int | None:
        return self.weights.get(name)


@dataclass(frozen=True, slots=True)
class DemandNormalization:
    """Versioned, hashed normalization of raw demand signals, per category."""

    normalization_version: str
    content_hash: str
    categories: Mapping[str, DemandCategoryNormalization] = field(default_factory=dict)

    def for_category(self, category: str | None) -> DemandCategoryNormalization | None:
        if category is None:
            return None
        return self.categories.get(category)


@dataclass(frozen=True, slots=True)
class DemandFacts:
    """Signals available for one Candidate and its resolved canonical category."""

    raw_category: str | None = None
    category: str | None = None
    sales_count: DemandSignal[int] | None = None
    rating_count: DemandSignal[int] | None = None
    trend: DemandSignal[str] | None = None
    affiliate_portal: DemandSignal[str] | None = None
    badges: DemandSignal[tuple[str, ...]] | None = None

    @property
    def present_signals(self) -> tuple[DemandSignalName, ...]:
        present: list[DemandSignalName] = []
        if self.sales_count is not None:
            present.append(DemandSignalName.SALES_COUNT)
        if self.rating_count is not None:
            present.append(DemandSignalName.RATING_COUNT)
        if self.trend is not None:
            present.append(DemandSignalName.TREND)
        if self.affiliate_portal is not None:
            present.append(DemandSignalName.AFFILIATE_PORTAL)
        if self.badges is not None:
            present.append(DemandSignalName.BADGES)
        return tuple(present)


@dataclass(frozen=True, slots=True)
class DemandWarning:
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
class DemandComponent:
    """One explainable component of the Demand breakdown."""

    name: DemandSignalName
    weight: int | None
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
class DemandResult:
    """Queryable, versioned Demand for one Candidate."""

    candidate_id: str
    raw_category: str | None
    category: str | None
    demand: int | None
    fully_calibrated: bool
    weight_covered: int
    normalization_version: str
    normalization_hash: str
    components: tuple[DemandComponent, ...]
    warnings: tuple[DemandWarning, ...]

    def component(self, name: DemandSignalName) -> DemandComponent:
        """Return one component by name (every component is always present)."""

        for item in self.components:
            if item.name is name:
                return item
        raise KeyError(name.value)

    def to_contract(self) -> dict[str, Any]:
        return {
            "schema_version": DEMAND_SCHEMA_VERSION,
            "status": "EVALUATED",
            "candidate_id": self.candidate_id,
            "raw_category": self.raw_category,
            "category": self.category,
            "demand": self.demand,
            "fully_calibrated": self.fully_calibrated,
            "weight_covered": self.weight_covered,
            "scoring_version": DEMAND_SCORING_VERSION,
            "normalization_version": self.normalization_version,
            "normalization_hash": self.normalization_hash,
            "components": [component.to_contract() for component in self.components],
            "warnings": [warning.to_contract() for warning in self.warnings],
        }


def _serialize_raw(value: Any) -> Any:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, str)):
        return value
    if isinstance(value, (list, tuple)):
        return [_serialize_raw(item) for item in value]
    return None if value is None else str(value)


def _match_band(bands: tuple[ScoreBand, ...], value: Decimal) -> int | None:
    for band in bands:
        if band.matches(value):
            return band.score
    return None


def _missing_component(name: DemandSignalName, weight: int | None) -> DemandComponent:
    return DemandComponent(
        name=name,
        weight=weight,
        score=None,
        calibrated=False,
        raw=None,
        source=None,
        reason=REASON_MISSING_DATA,
    )


def _missing_warning(name: DemandSignalName) -> DemandWarning:
    return DemandWarning(
        code=WARNING_MISSING_DATA,
        message="Sinal de demanda ausente; não vira zero e afeta o Confidence",
        context={"component": name.value},
    )


def _invalid_warning(name: DemandSignalName, raw: Any, reason: str) -> DemandWarning:
    return DemandWarning(
        code=WARNING_INVALID_DATA,
        message="Sinal de demanda inválido; ignorado no cálculo e reportado para revisão",
        context={"component": name.value, "raw": _serialize_raw(raw), "reason": reason},
    )


def _gap_warning(name: DemandSignalName, raw: Any) -> DemandWarning:
    return DemandWarning(
        code=WARNING_NORMALIZATION_NOT_DEFINED,
        message=(
            "Sinal sem normalização configurada para a categoria; lacuna explícita "
            "sem constante inventada (calibração humana necessária)"
        ),
        context={"component": name.value, "raw": _serialize_raw(raw)},
    )


def _weight_for(category: DemandCategoryNormalization | None, name: DemandSignalName) -> int | None:
    if category is None:
        return None
    return category.weight_for(name)


def _evaluate_numeric(
    name: DemandSignalName,
    signal: DemandSignal[int] | None,
    category: DemandCategoryNormalization | None,
) -> tuple[DemandComponent, DemandWarning | None]:
    weight = _weight_for(category, name)
    if signal is None:
        return _missing_component(name, weight), _missing_warning(name)
    value = signal.value
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return (
            DemandComponent(
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
    if category is None:
        return (
            DemandComponent(
                name=name,
                weight=weight,
                score=None,
                calibrated=False,
                raw=value,
                source=signal.source,
                reason=REASON_NORMALIZATION_NOT_DEFINED,
            ),
            None,
        )
    bands = (
        category.sales_count_bands
        if name is DemandSignalName.SALES_COUNT
        else category.rating_count_bands
    )
    score = _match_band(bands, Decimal(value))
    if score is None or weight is None:
        return (
            DemandComponent(
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
        DemandComponent(
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


def _evaluate_label(
    name: DemandSignalName,
    signal: DemandSignal[str] | None,
    category: DemandCategoryNormalization | None,
) -> tuple[DemandComponent, DemandWarning | None]:
    weight = _weight_for(category, name)
    if signal is None:
        return _missing_component(name, weight), _missing_warning(name)
    normalized = normalize_label(signal.value)
    if normalized is None:
        return (
            DemandComponent(
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
    if category is None:
        return (
            DemandComponent(
                name=name,
                weight=weight,
                score=None,
                calibrated=False,
                raw=signal.value,
                source=signal.source,
                reason=REASON_NORMALIZATION_NOT_DEFINED,
            ),
            None,
        )
    scores = (
        category.trend_scores
        if name is DemandSignalName.TREND
        else category.affiliate_portal_scores
    )
    score = scores.get(normalized)
    if score is None or weight is None:
        return (
            DemandComponent(
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
        DemandComponent(
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


def _evaluate_badges(
    signal: DemandSignal[tuple[str, ...]] | None,
    category: DemandCategoryNormalization | None,
) -> tuple[DemandComponent, DemandWarning | None]:
    name = DemandSignalName.BADGES
    weight = _weight_for(category, name)
    if signal is None:
        return _missing_component(name, weight), _missing_warning(name)
    value = signal.value
    if not isinstance(value, tuple) or any(not isinstance(item, str) for item in value):
        return (
            DemandComponent(
                name=name,
                weight=weight,
                score=None,
                calibrated=False,
                raw=value,
                source=signal.source,
                reason=REASON_INVALID_DATA,
            ),
            _invalid_warning(name, value, "invalid_badges"),
        )
    if not value:
        # An empty badge set carries no information; it never scores zero.
        return _missing_component(name, weight), _missing_warning(name)
    cleaned = [normalize_label(item) for item in value]
    if any(item is None for item in cleaned):
        return (
            DemandComponent(
                name=name,
                weight=weight,
                score=None,
                calibrated=False,
                raw=value,
                source=signal.source,
                reason=REASON_INVALID_DATA,
            ),
            _invalid_warning(name, value, "empty_label"),
        )
    if category is None:
        return (
            DemandComponent(
                name=name,
                weight=weight,
                score=None,
                calibrated=False,
                raw=value,
                source=signal.source,
                reason=REASON_NORMALIZATION_NOT_DEFINED,
            ),
            None,
        )
    scores = [category.badge_scores.get(item or "") for item in cleaned]
    unmapped = [item for item, score in zip(cleaned, scores, strict=True) if score is None]
    if weight is None or unmapped:
        warning = DemandWarning(
            code=WARNING_NORMALIZATION_NOT_DEFINED,
            message=(
                "Badge sem normalização configurada para a categoria; lacuna "
                "explícita sem constante inventada (calibração humana necessária)"
            ),
            context={
                "component": name.value,
                "raw": _serialize_raw(value),
                "unmapped": unmapped,
            },
        )
        return (
            DemandComponent(
                name=name,
                weight=weight,
                score=None,
                calibrated=False,
                raw=value,
                source=signal.source,
                reason=REASON_NORMALIZATION_NOT_DEFINED,
            ),
            warning,
        )
    return (
        DemandComponent(
            name=name,
            weight=weight,
            score=max(score for score in scores if score is not None),
            calibrated=True,
            raw=value,
            source=signal.source,
            reason=REASON_OK,
        ),
        None,
    )


def compute_demand(
    *,
    candidate_id: str,
    facts: DemandFacts,
    normalization: DemandNormalization,
) -> DemandResult:
    """Compute the deterministic Demand breakdown for one Candidate.

    The function never mutates its inputs and is reproducible for the same facts
    and normalization version. An absent signal stays an explicit gap instead of
    an invented zero, and an incomplete category configuration yields
    ``fully_calibrated=False`` so the result is never presented as validated.
    """

    warnings: list[DemandWarning] = []
    category = normalization.for_category(facts.category)

    if facts.category is None:
        warnings.append(
            DemandWarning(
                code=WARNING_CATEGORY_NOT_DEFINED,
                message=(
                    "Categoria do Candidate não resolvida; normalização de demanda "
                    "por categoria requer classificação aprovada"
                ),
                context={"raw_category": facts.raw_category},
            )
        )
    elif category is None:
        warnings.append(
            DemandWarning(
                code=WARNING_NORMALIZATION_NOT_DEFINED,
                message=(
                    "Categoria sem configuração de demanda; lacuna explícita sem "
                    "valor inventado (calibração humana necessária)"
                ),
                context={"category": facts.category},
            )
        )

    components: list[DemandComponent] = []
    for component, warning in (
        _evaluate_numeric(DemandSignalName.SALES_COUNT, facts.sales_count, category),
        _evaluate_numeric(DemandSignalName.RATING_COUNT, facts.rating_count, category),
        _evaluate_label(DemandSignalName.TREND, facts.trend, category),
        _evaluate_label(DemandSignalName.AFFILIATE_PORTAL, facts.affiliate_portal, category),
        _evaluate_badges(facts.badges, category),
    ):
        components.append(component)
        if warning is not None:
            warnings.append(warning)

    calibrated_components = [
        component
        for component in components
        if component.calibrated and component.score is not None and component.weight is not None
    ]
    weight_covered = sum(component.weight or 0 for component in calibrated_components)
    if calibrated_components and weight_covered > 0:
        weighted = sum(
            Decimal(component.score or 0) * (component.weight or 0)
            for component in calibrated_components
        )
        demand: int | None = int(
            (weighted / Decimal(weight_covered)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        )
    else:
        demand = None

    return DemandResult(
        candidate_id=candidate_id,
        raw_category=facts.raw_category,
        category=facts.category,
        demand=demand,
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


def _require_score(value: Any, *, category: str, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 100:
        raise _normalization_invalid(
            "score de normalização deve ser inteiro entre 0 e 100",
            context={"category": category, "field": field_name, "score": _serialize_raw(value)},
        )
    return value


def _require_weight(value: Any, *, category: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 100:
        raise _normalization_invalid(
            "peso de composição deve ser inteiro entre 0 e 100",
            context={"category": category, "weight": _serialize_raw(value)},
        )
    return value


def _to_decimal(value: Any, *, category: str, field_name: str) -> Decimal:
    if isinstance(value, (bool, float)):
        raise _normalization_invalid(
            "limite de banda deve ser decimal/inteiro, não float binário",
            context={"category": category, "field": field_name},
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
                context={"category": category, "field": field_name},
            ) from exc
    else:
        raise _normalization_invalid(
            "limite de banda inválido",
            context={"category": category, "field": field_name},
        )
    if not amount.is_finite() or amount < 0:
        raise _normalization_invalid(
            "limite de banda deve ser finito e >= 0",
            context={"category": category, "field": field_name},
        )
    return amount


def _build_bands(value: Any, *, category: str, field_name: str) -> tuple[ScoreBand, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise _normalization_invalid(
            "bandas de normalização devem ser uma lista",
            context={"category": category, "field": field_name},
        )
    bands: list[ScoreBand] = []
    for entry in value:
        if not isinstance(entry, Mapping):
            raise _normalization_invalid(
                "banda de normalização deve ser um objeto",
                context={"category": category, "field": field_name},
            )
        minimum = _to_decimal(entry.get("min"), category=category, field_name=f"{field_name}.min")
        maximum = (
            None
            if entry.get("max") is None
            else _to_decimal(entry.get("max"), category=category, field_name=f"{field_name}.max")
        )
        if maximum is not None and maximum < minimum:
            raise _normalization_invalid(
                "max da banda deve ser >= min",
                context={
                    "category": category,
                    "field": field_name,
                    "min": str(minimum),
                    "max": str(maximum),
                },
            )
        score = _require_score(
            entry.get("score"), category=category, field_name=f"{field_name}.score"
        )
        bands.append(ScoreBand(minimum=minimum, maximum=maximum, score=score))
    bands.sort(key=lambda band: band.minimum)
    for previous, current in pairwise(bands):
        if previous.maximum is None or previous.maximum >= current.minimum:
            raise _normalization_invalid(
                "bandas de normalização não podem se sobrepor",
                context={"category": category, "field": field_name},
            )
    return tuple(bands)


def _build_label_scores(value: Any, *, category: str, field_name: str) -> dict[str, int]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise _normalization_invalid(
            "mapa de labels deve ser um objeto",
            context={"category": category, "field": field_name},
        )
    scores: dict[str, int] = {}
    for raw_label, score in value.items():
        normalized = normalize_label(str(raw_label))
        if normalized is None:
            raise _normalization_invalid(
                "label de normalização vazio",
                context={"category": category, "field": field_name},
            )
        scores[normalized] = _require_score(
            score, category=category, field_name=f"{field_name}.{normalized}"
        )
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


def build_demand_normalization(document: Mapping[str, Any]) -> DemandNormalization:
    """Build and validate a Demand normalization config from a plain document.

    Raises :class:`DemandNormalizationInvalidError` (``RAD-CFG-007``) on a missing
    version, an unknown category/signal, an out-of-range score/weight, an invalid
    band or overlapping bands.
    """

    if not isinstance(document, Mapping):
        raise _normalization_invalid("Normalização de Demand deve ser um objeto")

    schema_version = document.get("schema_version")
    if schema_version is not None and str(schema_version) != DEMAND_NORMALIZATION_SCHEMA_VERSION:
        raise _normalization_invalid(
            "schema_version de normalização não suportada",
            context={"schema_version": str(schema_version)},
        )

    version = str(document.get("normalization_version") or "").strip()
    if not version:
        raise _normalization_invalid("normalization_version é obrigatório")

    categories_document = document.get("categories")
    if categories_document is None:
        categories_document = {}
    if not isinstance(categories_document, Mapping):
        raise _normalization_invalid("categories deve ser um objeto")

    categories: dict[str, DemandCategoryNormalization] = {}
    for raw_category, category_document in categories_document.items():
        category = str(raw_category)
        if category not in _CANONICAL_CATEGORIES:
            raise _normalization_invalid(
                "Categoria canônica desconhecida na normalização de Demand",
                context={"category": category},
            )
        if not isinstance(category_document, Mapping):
            raise _normalization_invalid(
                "Configuração de categoria deve ser um objeto", context={"category": category}
            )

        weights_document = category_document.get("weights") or {}
        if not isinstance(weights_document, Mapping):
            raise _normalization_invalid(
                "weights deve ser um objeto", context={"category": category}
            )
        weights: dict[DemandSignalName, int] = {}
        for raw_name, raw_weight in weights_document.items():
            try:
                name = DemandSignalName(str(raw_name))
            except ValueError as exc:
                raise _normalization_invalid(
                    "Sinal de demanda desconhecido em weights",
                    context={"category": category, "signal": str(raw_name)},
                ) from exc
            weights[name] = _require_weight(raw_weight, category=category)

        categories[category] = DemandCategoryNormalization(
            category=category,
            weights=weights,
            sales_count_bands=_build_bands(
                category_document.get("sales_count"),
                category=category,
                field_name="sales_count",
            ),
            rating_count_bands=_build_bands(
                category_document.get("rating_count"),
                category=category,
                field_name="rating_count",
            ),
            trend_scores=_build_label_scores(
                category_document.get("trend"), category=category, field_name="trend"
            ),
            affiliate_portal_scores=_build_label_scores(
                category_document.get("affiliate_portal"),
                category=category,
                field_name="affiliate_portal",
            ),
            badge_scores=_build_label_scores(
                category_document.get("badges"), category=category, field_name="badges"
            ),
        )

    normalized_document: dict[str, Any] = {
        "schema_version": DEMAND_NORMALIZATION_SCHEMA_VERSION,
        "normalization_version": version,
        "categories": {
            category: {
                "weights": {
                    name.value: sorted_category.weights[name]
                    for name in sorted(sorted_category.weights)
                },
                "sales_count": _band_document(sorted_category.sales_count_bands),
                "rating_count": _band_document(sorted_category.rating_count_bands),
                "trend": dict(sorted(sorted_category.trend_scores.items())),
                "affiliate_portal": dict(sorted(sorted_category.affiliate_portal_scores.items())),
                "badges": dict(sorted(sorted_category.badge_scores.items())),
            }
            for category, sorted_category in sorted(categories.items())
        },
    }
    return DemandNormalization(
        normalization_version=version,
        content_hash=_content_hash(normalized_document),
        categories=categories,
    )


#: Approved baseline normalization (RDR-025).
#:
#: The SDD requires Demand normalization to evolve by category but does **not**
#: calibrate the mapping or the composition weights. The baseline is therefore
#: intentionally empty: every signal/category is reported as an explicit
#: calibration gap until a human-approved, versioned config supplies the
#: mappings. No value is invented here.
APPROVED_DEMAND_DOCUMENT: dict[str, Any] = {
    "schema_version": DEMAND_NORMALIZATION_SCHEMA_VERSION,
    "normalization_version": "demand-normalization-1.0",
    "categories": {},
}

#: The approved baseline used when no operator file is configured.
APPROVED_DEMAND_NORMALIZATION: DemandNormalization = build_demand_normalization(
    APPROVED_DEMAND_DOCUMENT
)


__all__ = [
    "APPROVED_DEMAND_DOCUMENT",
    "APPROVED_DEMAND_NORMALIZATION",
    "DEMAND_INPUT_INVALID",
    "DEMAND_NORMALIZATION_INVALID",
    "DEMAND_NORMALIZATION_SCHEMA_VERSION",
    "DEMAND_SCHEMA_VERSION",
    "DEMAND_SCORING_VERSION",
    "REASON_INVALID_DATA",
    "REASON_MISSING_DATA",
    "REASON_NORMALIZATION_NOT_DEFINED",
    "REASON_OK",
    "WARNING_CATEGORY_NOT_DEFINED",
    "WARNING_INVALID_DATA",
    "WARNING_MISSING_DATA",
    "WARNING_NORMALIZATION_NOT_DEFINED",
    "DemandCategoryNormalization",
    "DemandComponent",
    "DemandError",
    "DemandFacts",
    "DemandNormalization",
    "DemandNormalizationInvalidError",
    "DemandResult",
    "DemandSignal",
    "DemandSignalName",
    "DemandWarning",
    "ScoreBand",
    "build_demand_normalization",
    "compute_demand",
    "demand_input_invalid_error",
    "normalize_label",
]
