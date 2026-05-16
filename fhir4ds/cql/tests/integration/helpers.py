"""Shared helpers for CQL integration tests."""

from pathlib import Path

from ...parser import parse_cql


_INCLUDE_ALIAS_TO_FILENAME = {
    "AHA": "AdvancedIllnessandFrailty.cql",
    "AdultOutpatientEncounters": "AdultOutpatientEncounters.cql",
    "CumulativeMedicationDuration": "CumulativeMedicationDuration.cql",
    "FHIRHelpers": "FHIRHelpers.cql",
    "Hospice": "Hospice.cql",
    "PalliativeCare": "PalliativeCare.cql",
    "QICoreCommon": "QICoreCommon.cql",
    "SDE": "SupplementalDataElements.cql",
    "SupplementalDataElements": "SupplementalDataElements.cql",
    "Status": "Status.cql",
}


def make_cql_library_loader(cql_dir: Path):
    """Return a library_loader callable for CQLToSQLTranslator integration tests."""
    cache = {}

    def load(alias: str):
        filename = _INCLUDE_ALIAS_TO_FILENAME.get(alias, f"{alias}.cql")
        path = cql_dir / filename
        if not path.exists():
            return None
        if alias not in cache:
            cache[alias] = parse_cql(path.read_text())
        return cache[alias]

    return load
