"""
Shared utilities for sql-on-fhir-py.
"""


import re


_SAFE_IDENTIFIER_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def quote_identifier(name: str) -> str:
    """Quote a SQL identifier, rejecting names that could enable injection.

    Public helper used by both ``viewdef`` (column/table references in
    generated SQL) and ``sqlquery`` (relatedArtifact labels and parameter
    names materialized as DuckDB views). The validation regex requires
    identifiers to start with a letter or underscore and contain only
    alphanumeric characters and underscores; valid identifiers are then
    double-quoted per DuckDB SQL identifier syntax.

    Raises:
        ValueError: when ``name`` is not a string, empty, or contains
            characters outside the safe-identifier regex.
    """
    if not isinstance(name, str) or not name or not _SAFE_IDENTIFIER_RE.match(name):
        raise ValueError(
            f"Invalid SQL identifier: {name!r}. "
            "SQL identifiers must start with a letter or underscore and contain "
            "only alphanumeric characters and underscores."
        )
    return f'"{name}"'


def pluralize_resource(resource: str) -> str:
    """Convert a FHIR resource type to its pluralized table name.

    Applies English pluralization rules suitable for FHIR resource types:
    - Special plurals (e.g., Person -> people)
    - Consonant + y -> ies (e.g., Library -> libraries)
    - Sibilants (s, x, ch, sh) -> es (e.g., DiagnosticFocus -> diagnosticfocuses)
    - Default: append s (e.g., Patient -> patients)

    Args:
        resource: FHIR resource type (e.g., "Patient", "Observation")

    Returns:
        Lowercase pluralized table name (e.g., "patients", "observations")
    """
    resource_lower = resource.lower()

    # Handle special plurals
    special_plurals = {
        "person": "people",
    }

    if resource_lower in special_plurals:
        return special_plurals[resource_lower]

    # Standard pluralization rules
    if resource_lower.endswith("y") and len(resource_lower) > 1 and resource_lower[-2] not in "aeiou":
        # Words ending in consonant + y: change y to ies
        return resource_lower[:-1] + "ies"
    elif resource_lower.endswith(("s", "x", "ch", "sh")):
        return resource_lower + "es"
    else:
        return resource_lower + "s"
