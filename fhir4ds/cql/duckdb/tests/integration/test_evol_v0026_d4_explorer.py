"""Domain 4 EXPLORER (v0.0.26 iteration 14) regression coverage.

QA-D4E-001 (MEDIUM): interval parameter bounds carrying timezone offsets
were cast through DuckDB's naive ``TIMESTAMP`` before reaching the temporal
SQL surface — ``CAST('2026-06-15T02:00:00+02:00' AS TIMESTAMP)`` silently
DROPS the offset (keeps local wall time 02:00 instead of the instant
00:00Z). Every non-``Z``/non-naive Measurement Period bound was therefore
shifted by its offset amount, silently moving population windows; this also
defeated the QA-D4H-001 sub-day tz-normalization fix one step upstream (it
normalized the *event* side while the *interval* side was already
corrupted). Fix: offset-bearing bound literals flow verbatim (the
VARCHAR-based temporal UDFs parse ISO-8601 offsets natively); naive texts
keep the TIMESTAMP normalization cast.
"""

from __future__ import annotations

import duckdb

from fhir4ds.cql.loader.fhir_loader import FHIRDataLoader
from fhir4ds.cql.duckdb.extension import register
from fhir4ds.cql.parser import parse_cql
from fhir4ds.cql.translator.translator import CQLToSQLTranslator

_RESOURCES = [{"resourceType": "Patient", "id": p} for p in ("lo", "mid", "out")]
_RESOURCES += [
    {
        "resourceType": "Encounter",
        "id": f"e-{p}",
        "status": "finished",
        "subject": {"reference": f"Patient/{p}"},
        "period": {"start": start, "end": start},
    }
    for p, start in (
        # exact UTC instant of the MP low (02:00+02:00 == 00:00Z)
        ("lo", "2026-06-15T00:00:00Z"),
        ("mid", "2026-06-15T03:00:00Z"),
        # 1 ms before the UTC low
        ("out", "2026-06-14T23:59:59.999Z"),
    )
]

# MP low carries a NON-ZERO offset: [2026-06-15T02:00:00+02:00, 2026-06-15T06:00:00Z]
# == [00:00Z, 06:00Z]. Before the fix the low bound became naive 02:00,
# dropping 'lo' from the window and keeping 'out'... no: 'out' stays out;
# the observable regression is 'lo' (exact UTC low) evaluating False.
_MP = ("2026-06-15T02:00:00+02:00", "2026-06-15T06:00:00Z")

_CQL = """library D4X version '1.0.0'
using FHIR version '4.0.1'
parameter "Measurement Period" Interval<DateTime>
context Patient
define "IPP": exists ([Encounter] E where E.period starts during hour of "Measurement Period")
"""


def _connections():
    # No pre-created resources table: FHIRDataLoader builds its own schema.
    native = duckdb.connect(config={"allow_unsigned_extensions": True})
    register(native)
    py = duckdb.connect()
    ver = duckdb.__version__
    duckdb.__version__ = "0.0.0-forced-python-fallback"
    register(py)
    duckdb.__version__ = ver
    for con in (native, py):
        FHIRDataLoader(con).load_resources(_RESOURCES)
    return native, py


def _sql(con):
    return CQLToSQLTranslator(con).translate_library_to_population_sql(
        parse_cql(_CQL),
        output_columns={"ipp": "IPP"},
        parameters={"Measurement Period": _MP},
    )


def test_offset_interval_parameter_bounds_keep_instant_d4_explorer():
    """MP low bound with a non-Z offset must compare as its UTC instant."""
    native, py = _connections()
    try:
        expected = {"lo": True, "mid": True, "out": False}
        for con in (native, py):
            rows = {
                r[0]: bool(r[1])
                for r in con.execute(_sql(con)).fetchall()
            }
            assert rows == expected, (rows, con)
    finally:
        native.close()
        py.close()


def test_offset_bound_literal_not_cast_through_naive_timestamp_d4_explorer():
    """SQL-shape guard: an offset-bearing bound literal must NOT pass
    through CAST(... AS TIMESTAMP) (which silently strips the offset)."""
    native, _ = _connections()
    try:
        sql = _sql(native)
        assert "2026-06-15T02:00:00+02:00" in sql
        assert "CAST(CAST('2026-06-15T02:00:00+02:00' AS TIMESTAMP) AS VARCHAR)" not in sql
        assert "'2026-06-15T02:00:00+02:00' AS TIMESTAMP" not in sql
    finally:
        native.close()


def test_naive_bounds_keep_timestamp_normalization_d4_explorer():
    """Control: naive date-only bounds keep the padded TIMESTAMP path
    (date-only low -> T00:00:00.000, end-of-day high behavior unchanged)."""
    native, _ = _connections()
    try:
        sql = CQLToSQLTranslator(native).translate_library_to_population_sql(
            parse_cql(_CQL),
            output_columns={"ipp": "IPP"},
            parameters={"Measurement Period": ("2026-06-15", "2026-06-15")},
        )
        assert "2026-06-15T00:00:00.000" in sql
        assert "2026-06-15T23:59:59.999" in sql
    finally:
        native.close()


# ── QA-D4E-002: exists() over intersect/except of query defines ────────

_CQL_SETOPS = """library D4S version '1.0.0'
using FHIR version '4.0.1'
valueset "NumProc VS": 'http://example.org/ValueSet/numproc'
valueset "NumProc2 VS": 'http://example.org/ValueSet/numproc2'
parameter "Measurement Period" Interval<DateTime>
context Patient
define "ArmA": [Procedure: "NumProc VS"] P where P.performed during day of "Measurement Period"
define "ArmB": [Procedure: "NumProc2 VS"] P where P.performed during day of "Measurement Period"
define "IntersectAB": exists (ArmA intersect ArmB)
define "ExceptAB": exists (ArmA except ArmB)
define "UnionAB": exists (ArmA union ArmB)
define "WinH1": [Procedure: "NumProc VS"] P where P.performed during day of Interval[@2026-01-01, @2026-06-30]
define "WinH2": [Procedure: "NumProc VS"] P where P.performed during day of Interval[@2026-04-01, @2026-12-31]
define "IntersectWin": exists (WinH1 intersect WinH2)
"""

_SETOP_RESOURCES = [{"resourceType": "Patient", "id": p} for p in ("s1", "s2", "s3", "s4")]
_SETOP_RESOURCES += [
    # s1: only arm A
    {"resourceType": "Procedure", "id": "pr-s1", "status": "completed",
     "subject": {"reference": "Patient/s1"}, "performedDateTime": "2026-03-01",
     "code": {"coding": [{"system": "http://snomed.info/sct", "code": "44493007"}]}},
    # s2: arms A and B (distinct procedures: intersect empty, except/union nonempty)
    {"resourceType": "Procedure", "id": "pr-s2a", "status": "completed",
     "subject": {"reference": "Patient/s2"}, "performedDateTime": "2026-03-01",
     "code": {"coding": [{"system": "http://snomed.info/sct", "code": "44493007"}]}},
    {"resourceType": "Procedure", "id": "pr-s2b", "status": "completed",
     "subject": {"reference": "Patient/s2"}, "performedDateTime": "2026-04-01",
     "code": {"coding": [{"system": "http://snomed.info/sct", "code": "80146002"}]}},
    # s3: no procedures at all
    # s4: two num-VS procedures, Mar (H1 only) + May (H1 and H2) -> windows OVERLAP
    {"resourceType": "Procedure", "id": "pr-s4a", "status": "completed",
     "subject": {"reference": "Patient/s4"}, "performedDateTime": "2026-03-01",
     "code": {"coding": [{"system": "http://snomed.info/sct", "code": "44493007"}]}},
    {"resourceType": "Procedure", "id": "pr-s4b", "status": "completed",
     "subject": {"reference": "Patient/s4"}, "performedDateTime": "2026-05-01",
     "code": {"coding": [{"system": "http://snomed.info/sct", "code": "44493007"}]}},
]

# (patient): IntersectAB, ExceptAB, UnionAB, IntersectWin
_SETOP_EXPECT = {
    "s1": (False, True, True, False),   # Mar proc in H1 only -> windows disjoint
    "s2": (False, True, True, False),
    "s3": (False, False, False, False),
    "s4": (False, True, True, True),    # May proc in BOTH windows -> intersect nonempty
}


_VS_NUM = {
    "resourceType": "ValueSet", "id": "numproc", "url": "http://example.org/ValueSet/numproc",
    "compose": {"include": [{"system": "http://snomed.info/sct",
                             "concept": [{"code": "44493007"}]}]},
}
_VS_NUM2 = {
    "resourceType": "ValueSet", "id": "numproc2", "url": "http://example.org/ValueSet/numproc2",
    "compose": {"include": [{"system": "http://snomed.info/sct",
                             "concept": [{"code": "80146002"}]}]},
}


def _setop_connections():
    native = duckdb.connect(config={"allow_unsigned_extensions": True})
    register(native)
    py = duckdb.connect()
    ver = duckdb.__version__
    duckdb.__version__ = "0.0.0-forced-python-fallback"
    register(py)
    duckdb.__version__ = ver
    for con in (native, py):
        loader = FHIRDataLoader(con)
        loader.load_valuesets([_VS_NUM, _VS_NUM2])
        loader.load_resources(_SETOP_RESOURCES)
    return native, py


def _setop_sql(con):
    return CQLToSQLTranslator(con).translate_library_to_population_sql(
        parse_cql(_CQL_SETOPS),
        output_columns={"iab": "IntersectAB", "eab": "ExceptAB", "uab": "UnionAB",
                        "iw": "IntersectWin"},
        parameters={"Measurement Period": ("2026-01-01", "2026-12-31")},
    )


def test_exists_over_intersect_except_query_defines_d4_explorer():
    """QA-D4E-002: exists(ArmA intersect/except ArmB) must test non-
    emptiness. The set-op source fell through to the scalar ``IS NOT NULL``
    default, and the later setop->correlated-EXISTS pass then produced the
    tautology ``EXISTS(...) IS NOT NULL`` — TRUE for every patient,
    including patients with zero procedures (silent wrong populations)."""
    native, py = _setop_connections()
    try:
        for con in (native, py):
            FHIRDataLoader(con).load_resources(_SETOP_RESOURCES)
            rows = {
                r[0]: (bool(r[1]), bool(r[2]), bool(r[3]), bool(r[4]))
                for r in con.execute(_setop_sql(con)).fetchall()
                if r[0] in _SETOP_EXPECT
            }
            assert rows == _SETOP_EXPECT, (rows, con)
    finally:
        native.close()
        py.close()


def test_exists_setop_sql_has_no_tautological_is_not_null_d4_explorer():
    """SQL-shape guard: the exists-over-setop predicate must not render as
    ``EXISTS (...) IS NOT NULL`` (a tautology)."""
    native, _ = _connections()
    try:
        sql = _setop_sql(native)
        assert "IS NOT NULL\n" not in sql
        assert ") IS NOT NULL" not in sql.replace("patient_id IS NOT NULL", "")
    finally:
        native.close()
