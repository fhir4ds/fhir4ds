"""Domain 4 HISTORIAN (v0.0.26 iteration 13) regression coverage.

QA-D4H-001 (MEDIUM): translated ``during <sub-day-precision> of`` —
``starts/ends/during hour|minute|second|millisecond of`` — decomposed the
interval test into raw ``LEFT()``-truncated ISO-string comparisons, which
compare RAW LOCAL components and ignore timezone offsets. CQL 1.5 mandates
timezone normalization at hour-or-finer precision (§Same As: "only when the
comparison precision is hours, minutes, seconds, or milliseconds"; the Java
reference engine normalizes via ``DateTime.getNormalized``), and the
precision-aware interval UDFs (``intervalContainsPrecise`` /
``intervalIncludedInPrecise``) already normalize on BOTH engines. Fix: route
sub-day ``during <prec> of`` through those UDFs when the interval operand is
statically recognized; day-and-coarser keeps the optimized LEFT-decomposition
(pinned CQL-14 doctrine: raw components at day precision).

Persisted S3 truth table (mandated by the 4-SKEPTIC handoff): the
expression-layer ValueSet membership 3VL — loaded member → True,
loaded-empty → False, UNLOADED → SQL NULL — verified dual-engine (the
SKEPTIC's p3 check was a manual unpersisted probe).
"""

from __future__ import annotations

import json

import duckdb

from fhir4ds.cql.loader.fhir_loader import FHIRDataLoader
from fhir4ds.cql.duckdb.extension import register
from fhir4ds.cql.parser import parse_cql
from fhir4ds.cql.translator.translator import CQLToSQLTranslator

_SNOMED = "http://snomed.info/sct"

# Encounters whose period starts are the SAME instant class but different
# offsets (MP = [2026-06-15T00:00:00+00:00, 2026-06-15T02:00:00+00:00]):
_PATIENTS = []
_ENCOUNTERS = [
    # tz2: 03:00+02:00 == 01:00Z -> INSIDE the window
    ("tz2", "2026-06-15T03:00:00+02:00"),
    # tz4: 2026-06-14T23:00-01:00 == 2026-06-15T00:00Z == MP low -> INSIDE
    ("tz4", "2026-06-14T23:00:00-01:00"),
    # tz5: offset-naive control, hour 00 -> INSIDE
    ("tz5", "2026-06-15T00:30:00"),
    # tzn: 05:00+00:00 -> OUTSIDE (negative control)
    ("tzn", "2026-06-15T05:00:00+00:00"),
]
_RESOURCES = [{"resourceType": "Patient", "id": p} for p, _ in _ENCOUNTERS]
_RESOURCES += [
    {
        "resourceType": "Encounter",
        "id": f"e-{p}",
        "status": "finished",
        "subject": {"reference": f"Patient/{p}"},
        "period": {"start": start, "end": start},
    }
    for p, start in _ENCOUNTERS
]

_MP = ("2026-06-15T00:00:00+00:00", "2026-06-15T02:00:00+00:00")

_CQL_TZ = """library D4HourTZ version '1.0.0'
using FHIR version '4.0.1'
parameter "Measurement Period" Interval<DateTime>
context Patient
define StartHour:
  exists ([Encounter] E where E.period starts during hour of "Measurement Period")
define PointHour:
  exists ([Encounter] E where E.period.start during hour of "Measurement Period")
define EndHour:
  exists ([Encounter] E where E.period ends during hour of "Measurement Period")
define MinuteNorm:
  exists ([Encounter] E where E.period starts during minute of "Measurement Period")
"""


def _tz_connections():
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


def _tz_sql(con):
    tr = CQLToSQLTranslator(con)
    return tr.translate_library_to_population_sql(
        parse_cql(_CQL_TZ),
        output_columns={
            "start_hour": "StartHour",
            "point_hour": "PointHour",
            "end_hour": "EndHour",
            "minute_norm": "MinuteNorm",
        },
        parameters={"Measurement Period": _MP},
    )


def test_subday_during_precision_normalizes_timezones_d4_historian():
    """QA-D4H-001: at hour/minute precision, offset-bearing events must
    compare as normalized instants. Raw-component comparison classified
    tz2 (local hour 03) and tz4 (local date 06-14) as outside. tz5 is
    offset-naive: per CQL #datetime-2 it assumes the evaluation-request
    offset (AMUX-165), so its expectation is computed from that offset."""
    native, py = _tz_connections()
    try:
        rn = {
            row[0]: row[1:]
            for row in native.execute(_tz_sql(native)).fetchall()
        }
        rp = {
            row[0]: row[1:]
            for row in py.execute(_tz_sql(py)).fetchall()
        }
    finally:
        native.close()
        py.close()
    assert sorted(rn) == ["tz2", "tz4", "tz5", "tzn"], rn
    # starts/point/ends during hour of MP: tz2, tz4 in; tzn out. tz5 is the
    # offset-naive control: per CQL #datetime-2 (AMUX-165, cql-tests #88)
    # an offset-less DateTime assumes the timezone offset of the evaluation
    # request timestamp, so its membership is evaluated at that assumed
    # offset (00:30 local shifted by the evaluation-request offset) —
    # computed here so the pin holds in any host timezone.
    from fhir4ds.cql.duckdb.udf.datetime import _evaluation_request_offset_minutes

    _assumed = _evaluation_request_offset_minutes()
    _tz5_instant_minute = 30 - _assumed  # minute-of-day, UTC
    tz5_expect = 0 <= _tz5_instant_minute <= 120
    for p, expect in (("tz2", True), ("tz4", True), ("tz5", tz5_expect), ("tzn", False)):
        row = rn[p]
        assert bool(row[0]) is expect, (p, "StartHour", row)
        assert bool(row[1]) is expect, (p, "PointHour", row)
        assert bool(row[2]) is expect, (p, "EndHour", row)
    # dual-engine parity
    assert rn == rp, (rn, rp)


def test_subday_during_minute_precision_boundary_d4_historian():
    """Minute precision discriminates the 02:30Z case: an event at
    2026-06-15T01:30:00-01:00 (== 02:30Z) is OUTSIDE [00:00Z, 02:00Z]."""
    res = list(_RESOURCES) + [
        {"resourceType": "Patient", "id": "tz3"},
        {
            "resourceType": "Encounter",
            "id": "e-tz3",
            "status": "finished",
            "subject": {"reference": "Patient/tz3"},
            "period": {"start": "2026-06-15T01:30:00-01:00",
                       "end": "2026-06-15T01:30:00-01:00"},
        },
    ]
    native = duckdb.connect(config={"allow_unsigned_extensions": True})
    register(native)
    try:
        FHIRDataLoader(native).load_resources(res)
        rows = {
            row[0]: row[4]
            for row in native.execute(_tz_sql(native)).fetchall()
        }
    finally:
        native.close()
    assert bool(rows["tz3"]) is False, rows  # 02:30Z outside
    assert bool(rows["tz2"]) is True, rows   # 01:00Z inside


# ── Persisted S3: expression-layer ValueSet membership 3VL ───────────
_VS_URL = "http://example.org/ValueSet/numproc"
_EMPTY_URL = "http://example.org/ValueSet/empty"
# Translator convention: full FHIR resource + path to the coding container
# (the native C++ extraction is lenient about bare CodeableConcept inputs;
# the Python fallback extractCodes is not — use the canonical shape).
_MEMBER_RES = json.dumps(
    {
        "resourceType": "Procedure",
        "id": "pm",
        "status": "completed",
        "code": {"coding": [{"system": _SNOMED, "code": "44493007"}]},
    }
)


def _vs_connections():
    native = duckdb.connect(config={"allow_unsigned_extensions": True})
    register(native)
    py = duckdb.connect()
    ver = duckdb.__version__
    duckdb.__version__ = "0.0.0-forced-python-fallback"
    register(py)
    duckdb.__version__ = ver
    for con in (native, py):
        FHIRDataLoader(con).load_valuesets(
            [
                {
                    "resourceType": "ValueSet",
                    "id": "v1",
                    "url": _VS_URL,
                    "compose": {"include": [{"system": _SNOMED,
                                             "concept": [{"code": "44493007"}]}]},
                },
                {
                    "resourceType": "ValueSet",
                    "id": "v2",
                    "url": _EMPTY_URL,
                    "expansion": {"contains": []},
                },
            ]
        )
    return native, py


def test_valueset_membership_truth_table_3vl_d4_historian():
    """Loaded member -> True; loaded-but-EMPTY ValueSet -> False (not null);
    UNLOADED ValueSet -> SQL NULL (unknown), never a silent False."""
    native, py = _vs_connections()
    try:
        results = []
        for con in (native, py):
            q = "SELECT fhirpath_in_valueset(?, 'code', ?)"
            member = con.execute(q, [_MEMBER_RES, _VS_URL]).fetchone()[0]
            empty = con.execute(q, [_MEMBER_RES, _EMPTY_URL]).fetchone()[0]
            unloaded = con.execute(
                q, [_MEMBER_RES, "http://example.org/ValueSet/never-loaded"]
            ).fetchone()[0]
            results.append((member, empty, unloaded))
    finally:
        native.close()
        py.close()
    for member, empty, unloaded in results:
        assert member is True
        assert empty is False
        assert unloaded is None
