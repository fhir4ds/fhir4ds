"""QA-025 (iter 16): Interval parameters supplied as JSON arrays must lower like tuples.

The operations evaluate_library envelope forwards browser/env-supplied JSON
parameters verbatim; JSON arrays decode to Python lists, so the natural
spelling ``{"Measurement Period": [start, end]}`` previously fell through the
raw-binding else-branch and produced ``intervalStart([...])`` list literals
that binder-error at execution.
"""

from __future__ import annotations

from fhir4ds.cql.parser import parse_cql
from fhir4ds.cql.translator.translator import CQLToSQLTranslator

_LIB = """library PT version '1.0.0'
using FHIR version '4.0.1'
parameter "Measurement Period" Interval<DateTime>
context Patient
define "In MP":
  Interval[@2026-01-01T00:00:00.0, @2026-06-30T23:59:59.999] during "Measurement Period"
"""


def _translate(params: dict) -> str:
    lib = parse_cql(_LIB)
    return CQLToSQLTranslator().translate_library_to_population_sql(
        lib,
        output_columns={"R": "In MP"},
        parameters=params,
    )


def test_interval_parameter_list_binding_lowers_like_tuple_qa025() -> None:
    sql = _translate(
        {"Measurement Period": ["2026-01-01T00:00:00.0", "2026-12-31T23:59:59.999"]}
    )
    # The list spelling must lower to the same bound-literal form as tuples:
    # scalar CAST bounds, never a list literal inside the interval UDF.
    assert "intervalStart([" not in sql
    assert "intervalEnd([" not in sql
    assert "['2026-01-01T00:00:00.0'" not in sql
    assert "'2026-01-01T00:00:00.0'" in sql
    assert "'2026-12-31T23:59:59.999'" in sql


def test_interval_parameter_tuple_binding_unchanged_qa025() -> None:
    sql = _translate(
        {"Measurement Period": ("2026-01-01T00:00:00.0", "2026-12-31T23:59:59.999")}
    )
    assert "intervalStart([" not in sql
    assert "'2026-12-31T23:59:59.999'" in sql
