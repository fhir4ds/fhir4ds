"""OMOP CDM v5.5 mapping — thin configuration over the generic runner.

Rev 2 (view-as-join-target): the composition lives entirely in
``resources/omop/manifest.json`` (views, unions, projections,
materialize) and executes through :mod:`fhir4ds.viewdef.runner`.
The monolithic ConceptMap is the standard converter contract; the
conceptmap VD flattens it into the ``omop.omop_conceptmap`` join
target; event VDs join that VIEW via ``Join.view``.
"""

from pathlib import Path
from typing import Dict, Sequence

from .runner import _HASH_MASK, load_manifest, run_composition

OMOP_DIR = Path(__file__).parent / "resources" / "omop"
MANIFEST = OMOP_DIR / "manifest.json"


def create_omop_views(con, source_table: str = "resources") -> Dict[str, str]:
    """Create the omop.* view schema over the staged resources table.

    Returns a mapping of OMOP table name -> materialized view name.
    """
    return run_composition(con, MANIFEST, source_table)


def omop_key_projection_sql(
    table: str, inner_sql: str, columns: Sequence[str]
) -> str:
    """Wrap ``inner_sql`` with the manifest's key projection for ``table``.

    The composition runner projects every column of a table. A browser
    sample runs one ViewDefinition (or an author's SQLQuery), which may
    project a subset, so this rewrites only the surrogate keys and concept
    defaults that are actually present — the demo then shows the same
    BIGINT person ids as the composed tables instead of the source
    strings.

    ``inner_sql`` must yield the natural keys as text (fresh view output):
    hashing an already-projected integer would hash a different value.
    Unknown tables and rows with no projected column are returned as-is.
    """
    projection = load_manifest(MANIFEST).get("projections", {}).get(table)
    if not projection:
        return inner_sql
    present = set(columns)
    exprs = [
        f'CASE WHEN "{col}" IS NULL THEN NULL '
        f'ELSE CAST(hash("{col}") & {_HASH_MASK} AS BIGINT) END AS "{col}"'
        for col in projection.get("hash_keys", [])
        if col in present
    ]
    exprs += [
        f'CAST(COALESCE(TRY_CAST("{col}" AS BIGINT), {default}) AS BIGINT) AS "{col}"'
        for col, default in (projection.get("defaults") or {}).items()
        if col in present
    ]
    if not exprs:
        return inner_sql
    body = ",\n    ".join(exprs)
    return f"SELECT * REPLACE (\n    {body}\n) FROM (\n{inner_sql}\n)"


__all__ = [
    "create_omop_views",
    "omop_key_projection_sql",
    "OMOP_DIR",
    "MANIFEST",
]
