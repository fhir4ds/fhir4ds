"""Data types for dqm-py."""

from dataclasses import dataclass, field
from enum import Enum


class AuditPersona(str, Enum):
    """Determines how evidence is pruned and narrated per population."""

    INCLUSION = "inclusion"
    EXCLUSION = "exclusion"
    NUMERATOR = "numerator"


class AuditMode(str, Enum):
    """Controls audit granularity."""

    NONE = "none"  # No audit (default)
    POPULATION = "population"  # Population-only: evidence from retrieve CTEs, no expression wrapping
    FULL = "full"  # Full expression wrapping: audit_and/or/leaf macros


class AuditOrStrategy(str, Enum):
    """Controls evidence collection for OR expressions."""

    TRUE_BRANCH = "true_branch"  # Only show evidence from the branch that fired
    ALL = "all"  # Show evidence from both branches regardless


@dataclass
class SupportingEvidenceDef:
    """A cqf-supportingEvidenceDefinition reference from a Measure population."""

    name: str
    cql_expression: str


@dataclass
class PopulationEntry:
    """A single population within a Measure group."""

    population_code: str
    group_id: str
    cql_expression: str
    audit_persona: AuditPersona
    supporting_evidence: list[SupportingEvidenceDef] = field(default_factory=list)


@dataclass
class GroupMap:
    """One group from a FHIR Measure, containing populations."""

    group_id: str
    population_basis: str  # "boolean" or resource type like "Encounter"
    populations: list[PopulationEntry] = field(default_factory=list)


@dataclass
class PopulationMap:
    """The complete mapping from a FHIR Measure to CQL definitions."""

    measure_id: str
    cql_library_ref: str | None
    groups: list[GroupMap] = field(default_factory=list)
