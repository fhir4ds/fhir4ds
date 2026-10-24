"""OMOP CDM v5.5 composite runner.

Composes the per-table OMOP ViewDefinitions into a schema of DuckDB
views under ``omop.*``:

- materializes each child VD's SQL as ``omop.<table>_<child>`` views
- emits the table-level UNION ALL view (design §4 union pattern:
  resource-specific child views -> table-level union)
- applies the integer-key projection (design §5): VDs emit natural-key
  strings; the runner wraps the union in the 63-bit positive hash
  (``hash(key) & 9223372036854775807``) for ``person_id`` /
  ``visit_occurrence_id`` / ``*_occurrence_id`` / ``*_exposure_id``
  columns and COALESCEs concept columns to 0 (valid OMOP no-map).
"""

import json
from pathlib import Path
from typing import Dict, List

from .parser import parse_view_definition
from .generator import SQLGenerator

OMOP_DIR = Path(__file__).parent / "resources" / "omop"

# OMOP table -> ordered list of child view file stems.
TABLE_UNIONS: Dict[str, List[str]] = {
    "drug_exposure": [
        "drug-exposure-medication-request-view",
        "drug-exposure-medication-statement-view",
        "drug-exposure-medication-administration-view",
        "drug-exposure-immunization-view",
    ],
}

# Single-view tables (no union): view stem -> OMOP table name.
SINGLE_VIEWS: Dict[str, str] = {
    "person-view": "person",
    "visit-occurrence-view": "visit_occurrence",
    "condition-occurrence-view": "condition_occurrence",
    "procedure-occurrence-view": "procedure_occurrence",
    "device-exposure-view": "device_exposure",
    "measurement-view": "measurement",
    "observation-view": "observation",
    "death-view": "death",
}

# Natural-key string columns projected to positive 63-bit integer keys.
_HASH_KEY_COLUMNS = frozenset({
    "person_id", "visit_occurrence_id", "condition_occurrence_id",
    "procedure_occurrence_id", "drug_exposure_id", "device_exposure_id",
    "measurement_id", "observation_id", "observation_period_id",
})

# Concept-id columns defaulted to 0 when unmapped (valid OMOP).
_CONCEPT_DEFAULT_COLUMNS = frozenset({
    "gender_concept_id", "visit_concept_id", "visit_type_concept_id",
    "condition_concept_id", "condition_type_concept_id",
    "procedure_concept_id", "procedure_type_concept_id",
    "drug_concept_id", "drug_type_concept_id",
    "device_concept_id", "device_type_concept_id",
    "measurement_concept_id", "measurement_type_concept_id",
    "observation_concept_id", "observation_type_concept_id",
    "death_type_concept_id", "condition_status_concept_id",
})

_HASH_MASK = "9223372036854775807"


def _load_view_sql(stem: str, source_table: str) -> str:
    vd = parse_view_definition(json.loads((OMOP_DIR / f"{stem}.json").read_text()))
    return SQLGenerator(source_table=source_table).generate(vd)


def _wrap_projection(select_sql: str, columns: List[str]) -> str:
    """Wrap a SELECT in the integer-key / concept-default projection."""
    exprs = []
    for col in columns:
        if col in _HASH_KEY_COLUMNS:
            exprs.append(
                f"CAST(hash({col}) & {_HASH_MASK} AS BIGINT) AS {col}"
            )
        elif col in _CONCEPT_DEFAULT_COLUMNS:
            exprs.append(f"CAST(COALESCE(TRY_CAST({col} AS BIGINT), 0) AS BIGINT) AS {col}")
        else:
            exprs.append(col)
    return f"SELECT {', '.join(exprs)} FROM (\n{select_sql}\n)"


def _result_columns(con, sql: str) -> List[str]:
    # Execute against the staged table once to learn column order.
    return [d[0] for d in con.execute(f"SELECT * FROM ({sql}) LIMIT 0").description]


def create_omop_views(con, source_table: str = "resources") -> Dict[str, str]:
    """Create the omop.* view schema over the staged resources table.

    Returns a mapping of OMOP table name -> the final composed SQL
    (useful for tests / inspection).
    """
    con.execute("CREATE SCHEMA IF NOT EXISTS omop")
    created: Dict[str, str] = {}

    child_columns: Dict[str, List[str]] = {}

    # Union tables: child views + table-level UNION ALL.
    for table, stems in TABLE_UNIONS.items():
        child_sqls = []
        for stem in stems:
            sql = _load_view_sql(stem, source_table)
            stem_suffix = stem.replace("drug-exposure-", "").replace("-view", "").replace("-", "_")
            name = f"omop.{table}__{stem_suffix}"
            con.execute(f"CREATE OR REPLACE VIEW {name} AS\n{sql}")
            child_sqls.append(f"SELECT * FROM {name}")
            if table not in child_columns:
                child_columns[table] = _result_columns(con, sql)
        union_sql = "\nUNION ALL\n".join(child_sqls)
        final = _wrap_projection(union_sql, child_columns[table])
        con.execute(f"CREATE OR REPLACE VIEW omop.{table} AS\n{final}")
        created[table] = final

    # Single-view tables.
    for stem, table in SINGLE_VIEWS.items():
        sql = _load_view_sql(stem, source_table)
        cols = _result_columns(con, sql)
        final = _wrap_projection(sql, cols)
        con.execute(f"CREATE OR REPLACE VIEW omop.{table} AS\n{final}")
        created[table] = final

    return created


__all__ = ["create_omop_views", "OMOP_DIR", "TABLE_UNIONS", "SINGLE_VIEWS"]
