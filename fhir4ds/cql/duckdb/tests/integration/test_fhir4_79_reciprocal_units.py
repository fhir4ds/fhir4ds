"""FHIR4-79: per-volume (reciprocal) unit codes must convert, and a
spec-defined conversion null must not be logged as a warning.

CQL 1.5 Appendix B §ConvertQuantity: "If the units are not comparable, the
result is null." Null is therefore the SPECIFIED result for an
incommensurable conversion, not a failure. Callers legitimately probe
candidate targets — ``fhir4ds/dedup/values.py`` walks nine canonical units
per quantity — so logging a WARNING per attempt turns one measurement unit
into a warning stream: a single fhir4px dedup run produced 13,758
"UDF quantityConvert failed" lines, all from ``1 / microliter`` values that
are incommensurable with every candidate canonical target.

The same unit is genuine UCUM ``1/uL`` (per microliter). Converting it to a
*compatible* reciprocal target (``1/L``) must produce the right magnitude:
5 per uL is 5,000,000 per L. Before this card the native C++ conversion
layer (flat table, no compound/reciprocal decomposition — the CQL-03
HISTORIAN QA-004 deferred family) answered NULL while the pint-backed Python
implementation answered correctly, so the same expression answered NULL
on desktop and non-NULL on the forced-Python fallback.

Known gaps, deliberately NOT changed here (see the doctrine pin at the bottom),
both pre-existing and shared with the CQL-03 HISTORIAN QA-004 deferred family
(the native quantity layer has no compound/reciprocal decomposition):

* a *display* spelling such as ``1 / microliter`` is not a UCUM code, so
  identical-unit comparison stays NULL on both engines per CQL 1.5 §Equal
  (invalid units ⇒ null), while the UCUM spelling ``1/uL`` compares by value;
* CROSS-unit comparison of reciprocal units (``5 '1/uL' > 1 '1/L'``) answers
  the CQL-correct ``true`` through the pint-backed Python authority and NULL
  through the native ``quantity_compare`` (``units_compatible`` cannot resolve
  a reciprocal). Flipping ``quantityCompare`` to the Python authority is a
  separate, much larger card — it is the per-row comparison primitive of every
  Quantity measure.
"""

from __future__ import annotations

import json
import logging

import duckdb
import pytest

from fhir4ds.core import register


def _cpp_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    status = register(con)
    assert status == {"fhirpath_cpp": True, "cql_cpp": True}
    return con


def _python_fallback_connection(monkeypatch) -> duckdb.DuckDBPyConnection:
    monkeypatch.setattr(duckdb, "__version__", "0.0.0-forced-python-fallback")
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    status = register(con)
    assert status == {"fhirpath_cpp": False, "cql_cpp": False}
    return con


def _quantity(value, code: str) -> str:
    return json.dumps(
        {
            "value": value,
            "unit": code,
            "code": code,
            "system": "http://unitsofmeasure.org",
        }
    )


# Every spelling the engine can meet in real data: the UCUM code (``1/uL``),
# the FHIR ``unit`` display promoted to a code by FHIRHelpers'
# ``Coalesce(code, unit, '1')`` (``1 / microliter``), and the JSON code the
# engine itself normalizes a CQL literal to (``1/microliter``).
_PER_VOLUME_CODES = ["1/uL", "1 / microliter", "1/microliter"]


@pytest.mark.parametrize("code", _PER_VOLUME_CODES)
def test_quantity_convert_reciprocal_unit_magnitude_cpp(code: str) -> None:
    """5 per microliter is 5,000,000 per litre on the native-loaded engine."""
    con = _cpp_connection()
    row = con.execute(
        "SELECT quantityConvert(?, '1/L')", [_quantity(5, code)]
    ).fetchone()
    assert row[0] is not None, f"quantityConvert(5 {code!r} -> '1/L') returned NULL"
    converted = json.loads(row[0])
    assert converted["code"] == "1/L"
    # Pint works in binary64: 5 / 1e-6 carries the usual ~1e-16 relative
    # error. The magnitude must be 5e6, not 5, not 5e-6, not NULL.
    assert converted["value"] == pytest.approx(5_000_000.0, rel=1e-12)


@pytest.mark.parametrize("code", _PER_VOLUME_CODES)
def test_quantity_convert_reciprocal_unit_magnitude_python_fallback(
    monkeypatch, code: str
) -> None:
    con = _python_fallback_connection(monkeypatch)
    row = con.execute(
        "SELECT quantityConvert(?, '1/L')", [_quantity(5, code)]
    ).fetchone()
    assert row[0] is not None
    converted = json.loads(row[0])
    assert converted["code"] == "1/L"
    assert converted["value"] == pytest.approx(5_000_000.0, rel=1e-12)


def test_quantity_convert_reciprocal_roundtrip_and_scaling() -> None:
    """The reciprocal conversion scales linearly and round-trips."""
    con = _cpp_connection()
    per_litre = json.loads(
        con.execute(
            "SELECT quantityConvert(?, '1/L')", [_quantity(2.5, "1/uL")]
        ).fetchone()[0]
    )
    assert per_litre["value"] == pytest.approx(2_500_000.0, rel=1e-12)

    back = json.loads(
        con.execute(
            "SELECT quantityConvert(?, '1/uL')", [_quantity(2_500_000, "1/L")]
        ).fetchone()[0]
    )
    assert back["code"] == "1/uL"
    assert back["value"] == pytest.approx(2.5, rel=1e-12)


def test_converts_to_quantity_accepts_reciprocal_unit() -> None:
    """The referee probe: a per-microliter quantity literal is convertible."""
    con = _cpp_connection()
    code, value = con.execute(
        "SELECT json_extract_string(ToQuantity(?), '$.code'), "
        "       json_extract(ToQuantity(?), '$.value') "
        "FROM (SELECT '5 ''1 / microliter''' AS q)",
        ["5 '1 / microliter'", "5 '1 / microliter'"],
    ).fetchone()
    assert code == "1 / microliter"
    assert float(value) == 5.0
    assert (
        con.execute(
            "SELECT ConvertsToQuantity('5 ''1 / microliter''')"
        ).fetchone()[0]
        is True
    )
    assert (
        con.execute(
            "SELECT CanConvertQuantity(ToQuantity('5 ''1 / microliter'''), '1/L')"
        ).fetchone()[0]
        is True
    )


def test_quantity_convert_incommensurable_units_is_a_quiet_null(caplog) -> None:
    """An incommensurable conversion is a null (spec), logged at DEBUG."""
    con = _cpp_connection()
    quantity_logger = logging.getLogger("fhir4ds.cql.duckdb.udf.quantity")
    with caplog.at_level(logging.DEBUG, logger=quantity_logger.name):
        row = con.execute(
            "SELECT quantityConvert(?, 'g')", [_quantity(5, "1 / microliter")]
        ).fetchone()
    assert row[0] is None, "per-volume -> mass is not a convertible pair"
    warnings = [
        record.getMessage()
        for record in caplog.records
        if record.levelno >= logging.WARNING
        and "quantityConvert" in record.getMessage()
    ]
    assert warnings == [], f"spec-defined conversion null logged at WARNING: {warnings}"


def test_dedup_value_probe_for_per_volume_unit_does_not_warn(caplog) -> None:
    """The 13,758-warning reproducer: dedup's canonical-target probe.

    The value partition key still falls back to the raw unit (a conservative
    miss — per-volume mass is incommensurable with every canonical target),
    but the probe must not emit one WARNING per attempted target.
    """
    from fhir4ds.dedup.values import CANONICAL_UNITS, normalize_value

    observation = {
        "resourceType": "Observation",
        "id": "obs-per-volume",
        "valueQuantity": {"value": 5, "unit": "1 / microliter"},
    }
    quantity_logger = logging.getLogger("fhir4ds.cql.duckdb.udf.quantity")
    with caplog.at_level(logging.DEBUG, logger=quantity_logger.name):
        key = normalize_value(observation)

    assert key == "5.00|1 / microliter"
    warnings = [
        record.getMessage()
        for record in caplog.records
        if record.levelno >= logging.WARNING
        and "quantityConvert" in record.getMessage()
    ]
    assert warnings == [], (
        f" probing {len(CANONICAL_UNITS)} canonical targets emitted "
        f"{len(warnings)} warnings for an incommensurable unit"
    )


@pytest.mark.parametrize(
    ("source", "target", "value", "expected_value"),
    [
        # Affine temperature conversions: pint refuses these outright, and the
        # native C++ quantity_convert answered them, so the Python authority
        # (this card) must produce the SAME values — the Celsius pivot keeps
        # 5 '[degF]' -> 'Cel' at exactly -15.0.
        ("[degF]", "Cel", 5, -15.0),
        ("Cel", "[degF]", 0, 32.0),
        ("Cel", "K", 100, 373.15),
        ("K", "Cel", 300, 26.850000000000023),
        ("[degF]", "K", 32, 273.15),
        ("Cel", "Cel", 20, 20.0),
    ],
)
def test_quantity_convert_offset_temperature_matches_native_values(
    source: str, target: str, value: float, expected_value: float
) -> None:
    con = _cpp_connection()
    row = con.execute(
        "SELECT quantityConvert(?, ?)", [_quantity(value, source), target]
    ).fetchone()
    assert row[0] is not None, f"{value} {source!r} -> {target!r} answered NULL"
    converted = json.loads(row[0])
    assert converted["code"] == target
    assert converted["value"] == expected_value


def test_quantity_convert_temperature_vs_mass_is_null() -> None:
    con = _cpp_connection()
    assert (
        con.execute(
            "SELECT quantityConvert(?, 'mg')", [_quantity(5, "[degF]")]
        ).fetchone()[0]
        is None
    )


def test_same_code_comparison_of_display_spelling_stays_null_doctrine_pin() -> None:
    """Doctrine pin (known gap, both engines agree).

    CQL 1.5 §Equal (Quantity) yields null for quantities whose unit is not a
    valid UCUM unit; ``microliter`` is the UCUM *name*, not the code (``uL``),
    so the display spelling stays incomparable — while the UCUM spelling
    compares by value. Changing this is a validity-predicate change in
    ``extensions/cql/src/cql/quantity.cpp`` and needs a native rebuild.
    """
    con = _cpp_connection()
    assert (
        con.execute(
            "SELECT quantityCompare(?, ?, '>')",
            [_quantity(5, "1/uL"), _quantity(6, "1/uL")],
        ).fetchone()[0]
        is False
    )
    assert (
        con.execute(
            "SELECT quantityCompare(?, ?, '>')",
            [_quantity(5, "1 / microliter"), _quantity(6, "1 / microliter")],
        ).fetchone()[0]
        is None
    )
