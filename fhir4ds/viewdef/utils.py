"""
Shared utilities for sql-on-fhir-py.
"""


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
