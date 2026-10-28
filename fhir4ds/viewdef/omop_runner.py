"""OMOP CDM v5.5 mapping — thin configuration over the generic runner.

Rev 2 (view-as-join-target): the composition lives entirely in
``resources/omop/manifest.json`` (views, unions, projections,
materialize) and executes through :mod:`fhir4ds.viewdef.runner`.
The monolithic ConceptMap is the standard converter contract; the
conceptmap VD flattens it into the ``omop.omop_conceptmap`` join
target; event VDs join that VIEW via ``Join.view``.
"""

from pathlib import Path
from typing import Dict

from .runner import run_composition

OMOP_DIR = Path(__file__).parent / "resources" / "omop"
MANIFEST = OMOP_DIR / "manifest.json"


def create_omop_views(con, source_table: str = "resources") -> Dict[str, str]:
    """Create the omop.* view schema over the staged resources table.

    Returns a mapping of OMOP table name -> materialized view name.
    """
    return run_composition(con, MANIFEST, source_table)


__all__ = ["create_omop_views", "OMOP_DIR", "MANIFEST"]
