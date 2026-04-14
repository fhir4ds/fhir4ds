"""Audit engine — relevance-prune evidence per population persona."""

from __future__ import annotations

from .types import AuditPersona, AuditOrStrategy, PopulationMap  # noqa: F401


class AuditEngine:
    """Relevance-prune evidence per population persona."""

    RELEVANCE_STRATEGIES = {
        AuditPersona.INCLUSION: "always",
        AuditPersona.EXCLUSION: "only_when_excluded",
        AuditPersona.NUMERATOR: "always",
    }

    def prune_evidence(
        self, row: dict, population_code: str, persona: AuditPersona
    ) -> list[dict]:
        """Prune evidence based on the population persona.

        For exclusion populations, evidence is only relevant when the patient
        IS excluded (i.e., the exclusion criterion is True). When the patient
        is NOT excluded, the exclusion evidence is irrelevant.
        """
        col_key = population_code.replace("-", "_")
        pop_value = row.get(col_key)

        # Extract evidence from struct if present
        if isinstance(pop_value, dict):
            evidence = pop_value.get("evidence", [])
            is_satisfied = pop_value.get("result", False)
        else:
            evidence = []
            is_satisfied = bool(pop_value)

        if not evidence:
            return []

        strategy = self.RELEVANCE_STRATEGIES.get(persona, "always")
        if strategy == "only_when_excluded" and not is_satisfied:
            return []

        return list(evidence)
