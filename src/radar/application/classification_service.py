"""Candidate classification orchestration (RDR-022, RDR-026).

The service reads a persisted Candidate's raw category through a narrow port,
applies the versioned :class:`~radar.domain.taxonomy.BrandTaxonomy` and returns
an explainable classification. It is deterministic and read-only: the same
Candidate and taxonomy version always yield the same result, so the public
boundary can recompute it and the future Evaluation (RDR-016) persists the
versioned snapshot instead of this ticket inventing a second store.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from radar.domain.capture import candidate_not_found_error
from radar.domain.taxonomy import (
    Brand,
    BrandTaxonomy,
    CandidateCategory,
    ClassificationResult,
    classify_category,
    taxonomy_version_mismatch_error,
)


class CandidateCategoryRepository(Protocol):
    """Persistence port exposing a Candidate's category context."""

    def get_candidate_category(self, candidate_id: str) -> CandidateCategory | None: ...


@dataclass(slots=True)
class ClassificationService:
    """Classify a Candidate and resolve approved Brand Fit."""

    repository: CandidateCategoryRepository
    taxonomy: BrandTaxonomy

    def classify(
        self,
        candidate_id: str,
        brand: Brand,
        *,
        taxonomy_version: str | None = None,
    ) -> ClassificationResult:
        """Return the explainable classification or a structured error.

        A requested ``taxonomy_version`` that differs from the active taxonomy
        fails closed (``RAD-CAP-007``) so a stale caller cannot silently consume
        values from a different calibration.
        """

        if taxonomy_version is not None and taxonomy_version != self.taxonomy.taxonomy_version:
            raise taxonomy_version_mismatch_error(taxonomy_version, self.taxonomy.taxonomy_version)

        context = self.repository.get_candidate_category(candidate_id)
        if context is None:
            raise candidate_not_found_error(candidate_id)

        return classify_category(
            candidate_id=candidate_id,
            brand=brand,
            raw_category=context.raw_category,
            taxonomy=self.taxonomy,
        )


__all__ = [
    "CandidateCategoryRepository",
    "ClassificationService",
]
