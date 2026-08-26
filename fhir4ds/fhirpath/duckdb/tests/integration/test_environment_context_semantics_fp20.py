"""FP-20 regression tests: FHIRPath §9-§12 environment/context semantics.

Pins (native C++ extension vs Python fallback parity):
- %context is the ORIGINAL node per FHIRPath §9 (does not change with
  select/where focus).
- %resource / %rootResource host variables resolve on both paths.
- Backtick and single-quoted environment variable forms are equivalent.
- Undefined environment variables are a RUNTIME concern: syntactically valid
  (fhirpath_is_valid true) and evaluate to empty on both paths.
- §10 type() reflection shape: {namespace, name} only; the STU metamodel
  fields (baseType / elementType / element) are an intended gap and must
  stay empty consistently on both engines.
"""

from __future__ import annotations

import json

import duckdb

from fhir4ds.fhirpath.duckdb import register_fhirpath

RESOURCE = json.dumps(
    {
        "resourceType": "Patient",
        "id": "p1",
        "active": True,
        "name": [
            {"family": "Smith", "given": ["John"]},
            {"family": "Jones", "given": ["Mary"]},
        ],
        "address": [{"city": "Melbourne"}],
    }
)


def _native() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    if not register_fhirpath(con):
        raise RuntimeError("native fhirpath extension did not load")
    return con


def _fallback() -> duckdb.DuckDBPyConnection:
    old = duckdb.__version__
    duckdb.__version__ = "0.0.0-forced-python-fallback"
    try:
        con = duckdb.connect(config={"allow_unsigned_extensions": True})
        loaded = register_fhirpath(con)
    finally:
        duckdb.__version__ = old
    if loaded:
        raise RuntimeError("fallback forcing failed")
    return con


def _text(con: duckdb.DuckDBPyConnection, expr: str) -> str | None:
    return con.execute(
        "SELECT fhirpath_text(?::JSON, ?)", [RESOURCE, expr]
    ).fetchone()[0]


def _list(con: duckdb.DuckDBPyConnection, expr: str) -> list | None:
    return con.execute(
        "SELECT fhirpath(?::JSON, ?)", [RESOURCE, expr]
    ).fetchone()[0]


def _is_valid(con: duckdb.DuckDBPyConnection, expr: str) -> bool:
    return con.execute("SELECT fhirpath_is_valid(?)", [expr]).fetchone()[0]


def test_context_is_original_node_through_focus_changes_fp20() -> None:
    native, fallback = _native(), _fallback()
    try:
        for expr in [
            "%context.id",
            "name.select(%context.id)",
            "name.where(family='Jones').select(%context.id)",
            "%resource.id",
            "%rootResource.id",
        ]:
            n = _list(native, expr)
            f = _list(fallback, expr)
            assert n == f, f"parity diff for {expr}: {n} vs {f}"
            assert n == ["p1"] * len(n) and n, expr
    finally:
        native.close()
        fallback.close()


def test_environment_variable_forms_equivalent_fp20() -> None:
    native, fallback = _native(), _fallback()
    try:
        assert _text(native, "%ucum") == "http://unitsofmeasure.org"
        assert _text(native, "%`ucum`") == "http://unitsofmeasure.org"
        assert (
            _text(native, "%`vs-administrative-gender`")
            == "http://hl7.org/fhir/ValueSet/administrative-gender"
        )
        assert _text(native, "%sct") == "http://snomed.info/sct"
        assert _text(native, "%loinc") == "http://loinc.org"
        for expr in ["%ucum", "%`ucum`", "%sct", "%loinc"]:
            assert _text(native, expr) == _text(fallback, expr), expr
    finally:
        native.close()
        fallback.close()


def test_undefined_environment_variable_is_runtime_not_syntax_fp20() -> None:
    native, fallback = _native(), _fallback()
    try:
        for expr in ["%unknown", "%`unknown-var`"]:
            # Syntax-level validity must hold on both engines...
            assert _is_valid(native, expr) is True, expr
            assert _is_valid(fallback, expr) is True, expr
            # ...and evaluation is empty on both engines (runtime concern).
            assert _list(native, expr) == [], expr
            assert _list(fallback, expr) == [], expr
    finally:
        native.close()
        fallback.close()


def test_type_reflection_shape_fp20() -> None:
    native, fallback = _native(), _fallback()
    try:
        # §10: namespace/name exposed and parity-stable.
        for expr, expected in [
            ("1.type().name", "Integer"),
            ("1.type().namespace", "System"),
            ("'x'.type().name", "String"),
            ("true.type().name", "Boolean"),
            ("1 'cm'.type().name", "Quantity"),
            ("Patient.type().name", "Patient"),
            ("Patient.type().namespace", "FHIR"),
            ("name.type().name", "HumanName"),
            ("Patient.ofType(FHIR.`Patient`).type().name", "Patient"),
        ]:
            n = _text(native, expr)
            f = _text(fallback, expr)
            assert n == expected, f"{expr}: {n}"
            assert n == f, f"parity diff for {expr}: {n} vs {f}"
        # Intended gap: STU metamodel fields are empty on BOTH engines.
        for expr in [
            "'x'.type().baseType",
            "address.type().elementType",
            "Patient.type().element",
        ]:
            n = _list(native, expr)
            f = _list(fallback, expr)
            assert n == [] and n == f, f"{expr}: {n} vs {f}"
    finally:
        native.close()
        fallback.close()
