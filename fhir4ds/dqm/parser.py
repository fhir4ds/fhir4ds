"""FHIR Measure parser — extracts population maps from Measure JSON."""

from __future__ import annotations

import logging

from .errors import MeasureParseError
from .types import (
    AuditPersona,
    GroupMap,
    PopulationEntry,
    PopulationMap,
    SupportingEvidenceDef,
)

_logger = logging.getLogger(__name__)


class MeasureParser:
    """Parse a FHIR Measure resource into a PopulationMap."""

    POPULATION_CODES = {
        "initial-population": AuditPersona.INCLUSION,
        "denominator": AuditPersona.INCLUSION,
        "denominator-exclusion": AuditPersona.EXCLUSION,
        "denominator-exception": AuditPersona.EXCLUSION,
        "numerator": AuditPersona.NUMERATOR,
        "numerator-exclusion": AuditPersona.EXCLUSION,
        "measure-population": AuditPersona.INCLUSION,
    }

    SUPPORTING_EVIDENCE_URL = (
        "http://hl7.org/fhir/StructureDefinition/cqf-supportingEvidenceDefinition"
    )

    def parse(self, measure: dict) -> PopulationMap:
        """Parse a FHIR Measure resource (or Bundle containing one) into a PopulationMap.

        Raises:
            MeasureParseError: If no group element found, required fields missing,
                or resourceType is not 'Measure'.
        """
        if measure.get("resourceType") == "Bundle":
            measure = self._extract_measure_from_bundle(measure)

        rt = measure.get("resourceType")
        if rt != "Measure":
            raise MeasureParseError(
                f"Expected resourceType 'Measure', got '{rt}'"
            )

        measure_id = measure.get("id", "unknown")
        cql_ref = self._extract_cql_library_ref(measure)
        groups_json = measure.get("group", [])
        if not groups_json:
            raise MeasureParseError(f"Measure '{measure_id}' has no group element")

        groups = [self._parse_group(g, i) for i, g in enumerate(groups_json)]
        return PopulationMap(measure_id=measure_id, cql_library_ref=cql_ref, groups=groups)

    def _extract_measure_from_bundle(self, bundle: dict) -> dict:
        """Extract the first Measure resource from a FHIR Bundle."""
        for entry in bundle.get("entry", []):
            resource = entry.get("resource", {})
            if resource.get("resourceType") == "Measure":
                return resource
        raise MeasureParseError("No Measure resource found in Bundle")

    def _extract_cql_library_ref(self, measure: dict) -> str | None:
        """Extract the CQL library canonical URL from relatedArtifact or library."""
        for artifact in measure.get("relatedArtifact", []):
            if (
                artifact.get("type") == "depends-on"
                and "Library" in artifact.get("resource", "")
            ):
                return artifact["resource"]
        libraries = measure.get("library", [])
        if libraries:
            return libraries[0]
        _logger.warning("No CQL library reference found in Measure '%s'", measure.get("id", "unknown"))
        return None

    POPULATION_BASIS_URL = "http://hl7.org/fhir/us/cqfmeasures/StructureDefinition/cqfm-populationBasis"

    def _extract_population_basis(self, group: dict) -> str:
        """Extract populationBasis from group extensions, defaulting to 'boolean'."""
        for ext in group.get("extension", []):
            url = ext.get("url", "")
            if url == self.POPULATION_BASIS_URL:
                return ext.get("valueCode", "boolean")
        return "boolean"

    def _parse_group(self, group: dict, index: int) -> GroupMap:
        """Parse a single group element from a Measure."""
        group_id = group.get("id", f"group-{index}")
        pop_basis = self._extract_population_basis(group)
        populations = [
            entry
            for pop in group.get("population", [])
            if (entry := self._parse_population(pop, group_id)) is not None
        ]
        return GroupMap(
            group_id=group_id, population_basis=pop_basis, populations=populations
        )

    def _parse_population(
        self, pop: dict, group_id: str
    ) -> PopulationEntry | None:
        """Parse a single population element."""
        code = self._extract_population_code(pop)
        if code is None:
            return None
        if code not in self.POPULATION_CODES:
            _logger.warning(
                "Skipping unrecognized population code '%s' in group '%s'",
                code, group_id,
            )
            return None

        cql_expr = self._extract_cql_expression(pop)
        if not cql_expr:
            _logger.warning(
                "Dropping population '%s' in group '%s': empty CQL expression",
                code, group_id,
            )
            return None

        evidence = self._extract_supporting_evidence(pop)

        return PopulationEntry(
            population_code=code,
            group_id=group_id,
            cql_expression=cql_expr,
            audit_persona=self.POPULATION_CODES[code],
            supporting_evidence=evidence,
        )

    def _extract_population_code(self, pop: dict) -> str | None:
        """Extract the population code from coding."""
        code_obj = pop.get("code", {})
        for coding in code_obj.get("coding", []):
            code = coding.get("code")
            if code in self.POPULATION_CODES:
                return code
        return None

    def _extract_cql_expression(self, pop: dict) -> str:
        """Extract the CQL expression name from criteria."""
        criteria = pop.get("criteria", {})
        return criteria.get("expression", "")

    def _extract_supporting_evidence(self, pop: dict) -> list[SupportingEvidenceDef]:
        """Extract cqf-supportingEvidenceDefinition extensions."""
        evidence: list[SupportingEvidenceDef] = []
        for ext in pop.get("extension", []):
            if ext.get("url") != self.SUPPORTING_EVIDENCE_URL:
                continue
            # The extension value is a DataRequirement with a cqfExpression extension
            value = ext.get("valueDataRequirement", ext.get("valueExpression", {}))
            if isinstance(value, dict):
                expr = value.get("expression", "")
                name = value.get("name", expr)
                if not expr:
                    # Try nested extension for cqfExpression
                    _CQF_EXPRESSION_URL = "http://hl7.org/fhir/StructureDefinition/cqf-expression"
                    for sub_ext in value.get("extension", []):
                        if sub_ext.get("url") == _CQF_EXPRESSION_URL:
                            val_expr = sub_ext.get("valueExpression", {})
                            expr = val_expr.get("expression", "")
                            name = val_expr.get("name", expr)
                            break
                if expr:
                    evidence.append(SupportingEvidenceDef(name=name, cql_expression=expr))
        return evidence
