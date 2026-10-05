"""Versioned brand taxonomy and explainable Brand Fit (RDR-022, RDR-026).

This module classifies a captured Candidate into a canonical category and
resolves the approved Brand Fit for Radar Beauty and Casa em Ordem. The taxonomy
is a versioned, hashed configuration artifact (AUT-045, AUT-207): commercial
mappings are data, not hardcoded conditionals, and every result carries the
``taxonomy_version``/``taxonomy_hash`` it was computed from.

Two rules are load-bearing and deliberately conservative:

* a raw category with no defined mapping never receives an invented category or
  score: the gap is explicit (``CATEGORY_MAPPING_NOT_DEFINED``) and requires
  approved calibration (AUT-030, issue TKT-05 acceptance criterion 3);
* a category that resolves outside the brand scope produces the
  ``OUT_OF_SCOPE_CATEGORY`` Hard Rule, which the Evaluation contract must honor
  before any score or AI step (AUT-056, ``docs/05_SCORING_ENGINE.md``).

The module is framework-free (no FastAPI/SQLAlchemy/Chrome) so the domain stays
independent from infrastructure (AUT-397).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from radar.domain.errors import RadarError, RadarException

#: Version of the taxonomy document schema.
TAXONOMY_SCHEMA_VERSION = "1.0"

#: Version of the public classification contract.
CLASSIFICATION_SCHEMA_VERSION = "1.0"

#: Error codes (see ``docs/ERROR_CATALOG.md``).
CLASSIFICATION_INPUT_INVALID = "RAD-CAP-006"
TAXONOMY_VERSION_MISMATCH = "RAD-CAP-007"
TAXONOMY_INVALID = "RAD-CFG-005"

#: Warning codes emitted by classification.
WARNING_CATEGORY_NOT_PROVIDED = "CATEGORY_NOT_PROVIDED"
WARNING_CATEGORY_MAPPING_NOT_DEFINED = "CATEGORY_MAPPING_NOT_DEFINED"
WARNING_BRAND_FIT_CALIBRATION_REQUIRED = "BRAND_FIT_CALIBRATION_REQUIRED"

#: Hard Rule emitted when the category is not in the brand scope
#: (``docs/05_SCORING_ENGINE.md``).
HARD_RULE_OUT_OF_SCOPE_CATEGORY = "OUT_OF_SCOPE_CATEGORY"


class Brand(StrEnum):
    """Brands supported by the V1 pipeline (``docs/04_DATA_CONTRACTS.md``)."""

    RADAR_BEAUTY = "RADAR_BEAUTY"
    CASA_EM_ORDEM = "CASA_EM_ORDEM"


class CanonicalCategory(StrEnum):
    """Canonical categories of the versioned brand taxonomy.

    Radar Beauty values mirror ``docs/05_SCORING_ENGINE.md``; Casa em Ordem
    groups mirror the priorities of ``docs/01_SCOPE_AND_PRINCIPLES.md``.
    """

    # Radar Beauty.
    PERFUME = "perfume"
    BODY_SPLASH = "body_splash"
    HAIR = "hair"
    SKINCARE = "skincare"
    MAKEUP = "makeup"
    ACCESSORIES = "accessories"
    # Casa em Ordem.
    ORGANIZATION = "organization"
    KITCHEN = "kitchen"
    UTILITIES = "utilities"
    CLEANING = "cleaning"
    LAUNDRY = "laundry"
    BATHROOM = "bathroom"
    DECOR = "decor"
    SMART_HOME = "smart_home"


#: The set of known canonical category values, used to validate taxonomy files.
_CANONICAL_CATEGORIES: frozenset[str] = frozenset(category.value for category in CanonicalCategory)


class TaxonomyInvalidError(RadarException):
    """Raised when a taxonomy document fails schema or semantic validation."""


class ClassificationError(RadarException):
    """Raised when a classification request cannot be satisfied."""


def _invalid(message: str, *, context: Mapping[str, Any] | None = None) -> TaxonomyInvalidError:
    return TaxonomyInvalidError(
        RadarError(
            code=TAXONOMY_INVALID,
            message=message,
            retryable=False,
            action="Corrigir o arquivo de taxonomy e validar novamente",
            context=dict(context or {}),
        )
    )


def classification_input_invalid_error(brand: str) -> ClassificationError:
    """Build the structured error for an unknown brand."""

    return ClassificationError(
        RadarError(
            code=CLASSIFICATION_INPUT_INVALID,
            message="Brand desconhecida para classificação",
            retryable=False,
            action="Usar uma brand suportada: RADAR_BEAUTY ou CASA_EM_ORDEM",
            context={"brand": brand},
        )
    )


def taxonomy_version_mismatch_error(requested: str, active: str) -> ClassificationError:
    """Build the structured error for a stale taxonomy version request."""

    return ClassificationError(
        RadarError(
            code=TAXONOMY_VERSION_MISMATCH,
            message="taxonomy_version solicitada difere da taxonomia ativa",
            retryable=False,
            action="Reclassificar com a taxonomy_version ativa ou atualizar a configuração",
            context={"requested": requested, "active": active},
        )
    )


def normalize_category(value: str | None) -> str | None:
    """Normalize a raw category into a comparable alias key.

    Lowercases, collapses whitespace and treats ``_``/``-`` as spaces so
    ``body_splash`` and ``Body Splash`` resolve to the same key. An empty or
    blank value yields ``None`` so a missing category is explicit.
    """

    if value is None:
        return None
    cleaned = " ".join(str(value).strip().lower().replace("_", " ").replace("-", " ").split())
    return cleaned or None


@dataclass(frozen=True, slots=True)
class CategoryRule:
    """Scope rule of one canonical category for one brand.

    ``brand_fit`` is ``None`` when the approved calibration does not define a
    value; classification never substitutes an invented number for it.
    """

    category: str
    priority: int
    brand_fit: int | None = None

    @property
    def calibrated(self) -> bool:
        return self.brand_fit is not None


@dataclass(frozen=True, slots=True)
class BrandTaxonomy:
    """Versioned, hashed mapping from raw categories to approved Brand Fit."""

    taxonomy_version: str
    content_hash: str
    aliases: Mapping[str, str]
    rules: Mapping[str, Mapping[str, CategoryRule]]

    def resolve(self, raw_category: str | None) -> str | None:
        """Resolve a raw category into a canonical category, if mapped."""

        normalized = normalize_category(raw_category)
        if normalized is None:
            return None
        return self.aliases.get(normalized)

    def rule_for(self, brand: Brand, category: str) -> CategoryRule | None:
        """Return the scope rule of a canonical category for a brand."""

        return self.rules.get(brand.value, {}).get(category)


@dataclass(frozen=True, slots=True)
class ClassificationWarning:
    """Explicit, non-fatal gap produced while classifying a Candidate."""

    code: str
    message: str
    context: Mapping[str, Any] = field(default_factory=dict)

    def to_contract(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.context:
            payload["context"] = dict(self.context)
        return payload


@dataclass(frozen=True, slots=True)
class HardRuleViolation:
    """Hard Rule that precedes score and AI in the Evaluation contract."""

    rule: str
    message: str
    context: Mapping[str, Any] = field(default_factory=dict)

    def to_contract(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"rule": self.rule, "message": self.message}
        if self.context:
            payload["context"] = dict(self.context)
        return payload


@dataclass(frozen=True, slots=True)
class ClassificationResult:
    """Explainable classification of one Candidate against one brand."""

    candidate_id: str
    brand: Brand
    raw_category: str | None
    category: str | None
    priority: int | None
    brand_fit: int | None
    calibrated: bool
    taxonomy_version: str
    taxonomy_hash: str
    warnings: tuple[ClassificationWarning, ...] = ()
    hard_rules: tuple[HardRuleViolation, ...] = ()

    @property
    def calibration_required(self) -> bool:
        return not self.calibrated

    def to_contract(self) -> dict[str, Any]:
        return {
            "schema_version": CLASSIFICATION_SCHEMA_VERSION,
            "status": "CLASSIFIED",
            "candidate_id": self.candidate_id,
            "brand": self.brand.value,
            "raw_category": self.raw_category,
            "category": self.category,
            "priority": self.priority,
            "brand_fit": self.brand_fit,
            "calibrated": self.calibrated,
            "calibration_required": self.calibration_required,
            "taxonomy_version": self.taxonomy_version,
            "taxonomy_hash": self.taxonomy_hash,
            "warnings": [warning.to_contract() for warning in self.warnings],
            "hard_rules": [rule.to_contract() for rule in self.hard_rules],
        }


@dataclass(frozen=True, slots=True)
class CandidateCategory:
    """Raw category context read from a persisted Candidate."""

    candidate_id: str
    marketplace_product_id: str
    marketplace: str
    raw_category: str | None


def classify_category(
    *,
    candidate_id: str,
    brand: Brand,
    raw_category: str | None,
    taxonomy: BrandTaxonomy,
) -> ClassificationResult:
    """Classify one Candidate category and resolve Brand Fit, failing closed.

    The result always carries the taxonomy version/hash. An unclassifiable
    Candidate yields ``calibrated=False`` with an explicit warning and no
    invented value; a category outside the brand scope yields the
    ``OUT_OF_SCOPE_CATEGORY`` Hard Rule.
    """

    base: dict[str, Any] = {
        "candidate_id": candidate_id,
        "brand": brand,
        "raw_category": raw_category,
        "taxonomy_version": taxonomy.taxonomy_version,
        "taxonomy_hash": taxonomy.content_hash,
    }

    if normalize_category(raw_category) is None:
        return ClassificationResult(
            category=None,
            priority=None,
            brand_fit=None,
            calibrated=False,
            warnings=(
                ClassificationWarning(
                    code=WARNING_CATEGORY_NOT_PROVIDED,
                    message="Candidate sem categoria capturada; classificação requer dado de origem",
                    context={"brand": brand.value},
                ),
            ),
            **base,
        )

    category = taxonomy.resolve(raw_category)
    if category is None:
        return ClassificationResult(
            category=None,
            priority=None,
            brand_fit=None,
            calibrated=False,
            warnings=(
                ClassificationWarning(
                    code=WARNING_CATEGORY_MAPPING_NOT_DEFINED,
                    message="Mapeamento de categoria não definido na taxonomia; calibração aprovada é necessária",
                    context={"raw_category": raw_category, "brand": brand.value},
                ),
            ),
            **base,
        )

    rule = taxonomy.rule_for(brand, category)
    if rule is None:
        return ClassificationResult(
            category=category,
            priority=None,
            brand_fit=None,
            calibrated=False,
            hard_rules=(
                HardRuleViolation(
                    rule=HARD_RULE_OUT_OF_SCOPE_CATEGORY,
                    message="Categoria fora do escopo da marca; Hard Rule precede score e IA",
                    context={"brand": brand.value, "category": category},
                ),
            ),
            **base,
        )

    if not rule.calibrated:
        return ClassificationResult(
            category=category,
            priority=rule.priority,
            brand_fit=None,
            calibrated=False,
            warnings=(
                ClassificationWarning(
                    code=WARNING_BRAND_FIT_CALIBRATION_REQUIRED,
                    message="Brand Fit sem valor aprovado para esta marca; calibração aprovada é necessária",
                    context={"brand": brand.value, "category": category},
                ),
            ),
            **base,
        )

    return ClassificationResult(
        category=category,
        priority=rule.priority,
        brand_fit=rule.brand_fit,
        calibrated=True,
        **base,
    )


#: Approved taxonomy baseline (RDR-022, RDR-026).
#:
#: Radar Beauty Brand Fit values are the approved initial values from
#: ``docs/05_SCORING_ENGINE.md``. Casa em Ordem priorities come from
#: ``docs/01_SCOPE_AND_PRINCIPLES.md`` but its Brand Fit values are **not**
#: calibrated in the SDDs, so they are intentionally absent: classification must
#: report a calibration gap instead of inventing a score.
APPROVED_TAXONOMY_DOCUMENT: dict[str, Any] = {
    "schema_version": TAXONOMY_SCHEMA_VERSION,
    "taxonomy_version": "brand-taxonomy-1.0",
    "brands": {
        "RADAR_BEAUTY": {
            "categories": {
                "perfume": {"priority": 1, "brand_fit": 100},
                "body_splash": {"priority": 1, "brand_fit": 100},
                "hair": {"priority": 2, "brand_fit": 85},
                "skincare": {"priority": 2, "brand_fit": 85},
                "makeup": {"priority": 3, "brand_fit": 65},
                "accessories": {"priority": 3, "brand_fit": 60},
            }
        },
        "CASA_EM_ORDEM": {
            "categories": {
                "organization": {"priority": 1},
                "kitchen": {"priority": 1},
                "utilities": {"priority": 1},
                "cleaning": {"priority": 2},
                "laundry": {"priority": 2},
                "bathroom": {"priority": 2},
                "decor": {"priority": 3},
                "smart_home": {"priority": 3},
            }
        },
    },
    "aliases": {
        "perfume": "perfume",
        "perfumes": "perfume",
        "fragrance": "perfume",
        "fragrancia": "perfume",
        "fragrância": "perfume",
        "body splash": "body_splash",
        "body_splash": "body_splash",
        "hair": "hair",
        "cabelo": "hair",
        "cabelos": "hair",
        "hair care": "hair",
        "skincare": "skincare",
        "skin care": "skincare",
        "cuidados com a pele": "skincare",
        "makeup": "makeup",
        "make up": "makeup",
        "maquiagem": "makeup",
        "accessories": "accessories",
        "acessorios": "accessories",
        "acessórios": "accessories",
        "organization": "organization",
        "organizacao": "organization",
        "organização": "organization",
        "kitchen": "kitchen",
        "cozinha": "kitchen",
        "utilities": "utilities",
        "utilidades": "utilities",
        "cleaning": "cleaning",
        "limpeza": "cleaning",
        "laundry": "laundry",
        "lavanderia": "laundry",
        "bathroom": "bathroom",
        "banheiro": "bathroom",
        "decor": "decor",
        "decoracao": "decor",
        "decoração": "decor",
        "smart home": "smart_home",
        "smart_home": "smart_home",
        "casa inteligente": "smart_home",
    },
}


def _content_hash(document: Mapping[str, Any]) -> str:
    canonical = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_taxonomy(document: Mapping[str, Any]) -> BrandTaxonomy:
    """Build and validate a :class:`BrandTaxonomy` from a plain document.

    Raises :class:`TaxonomyInvalidError` (``RAD-CFG-005``) on a missing version,
    an unknown brand/category, an invalid priority, an out-of-range Brand Fit or
    an alias pointing to a category that no brand defines.
    """

    if not isinstance(document, Mapping):
        raise _invalid("Taxonomia deve ser um objeto")

    schema_version = document.get("schema_version")
    if schema_version is not None and str(schema_version) != TAXONOMY_SCHEMA_VERSION:
        raise _invalid(
            "schema_version de taxonomia não suportada",
            context={"schema_version": str(schema_version)},
        )

    version = str(document.get("taxonomy_version") or "").strip()
    if not version:
        raise _invalid("taxonomy_version é obrigatório na taxonomia")

    brands_document = document.get("brands")
    if not isinstance(brands_document, Mapping) or not brands_document:
        raise _invalid("Taxonomia deve definir brands")

    rules: dict[str, dict[str, CategoryRule]] = {}
    known_categories: set[str] = set()
    for brand_value, brand_document in brands_document.items():
        try:
            brand = Brand(str(brand_value))
        except ValueError as exc:
            raise _invalid(
                "Brand desconhecida na taxonomia", context={"brand": str(brand_value)}
            ) from exc
        if not isinstance(brand_document, Mapping):
            raise _invalid("Definição de brand deve ser um objeto", context={"brand": brand.value})
        categories_document = brand_document.get("categories", {})
        if not isinstance(categories_document, Mapping):
            raise _invalid("categories deve ser um objeto", context={"brand": brand.value})
        brand_rules: dict[str, CategoryRule] = {}
        for category_value, rule_document in categories_document.items():
            category = str(category_value)
            if category not in _CANONICAL_CATEGORIES:
                raise _invalid(
                    "Categoria canônica desconhecida na taxonomia",
                    context={"brand": brand.value, "category": category},
                )
            if not isinstance(rule_document, Mapping):
                raise _invalid(
                    "Regra de categoria deve ser um objeto",
                    context={"brand": brand.value, "category": category},
                )
            priority = rule_document.get("priority")
            if not isinstance(priority, int) or isinstance(priority, bool) or priority < 1:
                raise _invalid(
                    "priority deve ser inteiro >= 1",
                    context={"brand": brand.value, "category": category},
                )
            brand_fit = rule_document.get("brand_fit")
            if brand_fit is not None and (
                not isinstance(brand_fit, int)
                or isinstance(brand_fit, bool)
                or not 0 <= brand_fit <= 100
            ):
                raise _invalid(
                    "brand_fit deve ser inteiro entre 0 e 100",
                    context={"brand": brand.value, "category": category},
                )
            brand_rules[category] = CategoryRule(
                category=category, priority=priority, brand_fit=brand_fit
            )
            known_categories.add(category)
        rules[brand.value] = brand_rules

    aliases_document = document.get("aliases", {})
    if not isinstance(aliases_document, Mapping):
        raise _invalid("aliases deve ser um objeto")
    aliases: dict[str, str] = {}
    for raw_value, category_value in aliases_document.items():
        normalized = normalize_category(str(raw_value))
        target = str(category_value)
        if normalized is None:
            raise _invalid("Alias de categoria vazio", context={"alias": str(raw_value)})
        if target not in known_categories:
            raise _invalid(
                "Alias aponta para categoria não definida por nenhuma brand",
                context={"alias": str(raw_value), "category": target},
            )
        aliases[normalized] = target

    normalized_document = {
        "schema_version": TAXONOMY_SCHEMA_VERSION,
        "taxonomy_version": version,
        "brands": {
            brand: {
                category: {
                    "priority": rule.priority,
                    "brand_fit": rule.brand_fit,
                }
                for category, rule in sorted(brand_rules.items())
            }
            for brand, brand_rules in sorted(rules.items())
        },
        "aliases": dict(sorted(aliases.items())),
    }
    return BrandTaxonomy(
        taxonomy_version=version,
        content_hash=_content_hash(normalized_document),
        aliases=aliases,
        rules=rules,
    )


#: The approved, hashed taxonomy used when no operator file is configured.
APPROVED_TAXONOMY: BrandTaxonomy = build_taxonomy(APPROVED_TAXONOMY_DOCUMENT)


__all__ = [
    "APPROVED_TAXONOMY",
    "APPROVED_TAXONOMY_DOCUMENT",
    "CLASSIFICATION_INPUT_INVALID",
    "CLASSIFICATION_SCHEMA_VERSION",
    "HARD_RULE_OUT_OF_SCOPE_CATEGORY",
    "TAXONOMY_INVALID",
    "TAXONOMY_SCHEMA_VERSION",
    "TAXONOMY_VERSION_MISMATCH",
    "WARNING_BRAND_FIT_CALIBRATION_REQUIRED",
    "WARNING_CATEGORY_MAPPING_NOT_DEFINED",
    "WARNING_CATEGORY_NOT_PROVIDED",
    "Brand",
    "BrandTaxonomy",
    "CandidateCategory",
    "CanonicalCategory",
    "CategoryRule",
    "ClassificationError",
    "ClassificationResult",
    "ClassificationWarning",
    "HardRuleViolation",
    "TaxonomyInvalidError",
    "build_taxonomy",
    "classification_input_invalid_error",
    "classify_category",
    "normalize_category",
    "taxonomy_version_mismatch_error",
]
