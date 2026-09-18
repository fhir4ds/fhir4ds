"""cqlDivide native C++ parity (v0.0.14 WASM C++ parity feature).

Guards the ported C++ ``cqlDivide`` scalar UDF against the Python
authority ``_cql_divide`` (fhir4ds/cql/duckdb/macros/math.py) across the
three execution legs that matter for browser parity:

1. native-loaded C++ extension (LOAD + Python supplements)
2. forced Python fallback (supplements only, no C++ extension)
3. no-Python/browser-style runtime (C++ extensions + pure SQL macros only)

The Python authority stays the desktop conformance authority; the C++
port must be byte-identical on every non-NULL result.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext

import duckdb
import pytest

from fhir4ds.cql.duckdb.extension import _register_python_supplements
from fhir4ds.cql.duckdb import register

from .wasm_runtime_helpers import no_python_connection


def _py_authority(a: str, b: str) -> Decimal | None:
    try:
        da = Decimal(str(a).strip())
        db = Decimal(str(b).strip())
    except (ValueError, InvalidOperation, ArithmeticError):
        return None
    if db == 0:
        return None
    try:
        with localcontext() as ctx:
            ctx.prec = 60
            quotient = da / db
            result = quotient.quantize(Decimal("1.00000000"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ArithmeticError):
        return None
    if result.copy_abs() >= Decimal(10) ** 28:
        return None
    return result


CASES: list[tuple[str, str, Decimal | None]] = [
    # exact / classic artifacts DuckDB / would produce
    ("10.0", "3.0", Decimal("3.33333333")),
    ("9.9", "3.0", Decimal("3.30000000")),
    ("0.3", "0.1", Decimal("3.00000000")),
    ("1", "3", Decimal("0.33333333")),
    ("2", "3", Decimal("0.66666667")),
    ("1", "7", Decimal("0.14285714")),
    # sign matrix
    ("-10", "3", Decimal("-3.33333333")),
    ("10", "-3", Decimal("-3.33333333")),
    ("-10", "-3", Decimal("3.33333333")),
    ("-1", "7", Decimal("-0.14285714")),
    # nulls: zero divisor, zero numerator
    ("1", "0", None),
    ("2", "0.0", None),
    ("0", "0", None),
    ("0", "5", Decimal("0.00000000")),
    # HALF_UP guard-digit rounding (ties and near-ties at scale 8)
    ("0.000000001", "1", Decimal("0.00000000")),
    ("0.000000005", "1", Decimal("0.00000001")),
    ("-0.000000005", "1", Decimal("-0.00000001")),
    ("0.0000000149", "1", Decimal("0.00000001")),
    ("0.000000015", "1", Decimal("0.00000002")),
    ("1.000000005", "1", Decimal("1.00000001")),
    ("-1.000000005", "1", Decimal("-1.00000001")),
    ("1.0000000049", "1", Decimal("1.00000000")),
    # extent boundary: 28 integer digits after rounding stays, beyond nulls
    ("99999999999999999999.99999999", "1", Decimal("99999999999999999999.99999999")),
    ("123456789012345678901234567.5", "1", Decimal("123456789012345678901234567.50000000")),
    ("9999999999999999999999999999", "1", Decimal("9999999999999999999999999999.00000000")),
    # 1e28 / 1 rounds to exactly 1e28 which is >= the 10^28 extent limit -> null
    ("1e28", "1", None),
    ("10000000000000000000000000000", "1", None),
    # non-numeric operands
    ("abc", "1", None),
    ("1", "abc", None),
    # whitespace / plus sign tolerated (Python str->Decimal semantics)
    ("  7.0  ", "2", Decimal("3.50000000")),
    ("+3", "2", Decimal("1.50000000")),
    # exponent notation (DOUBLE operands arrive via shortest round-trip)
    ("1e3", "1e-3", Decimal("1000000.00000000")),
    ("1e-30", "1e-30", Decimal("1.00000000")),
]


def _assert_identity(con: duckdb.DuckDBPyConnection, label: str) -> None:
    rows = con.execute(
        "SELECT function_name, function_type FROM duckdb_functions() "
        "WHERE lower(function_name) = 'cqldivide'"
    ).fetchall()
    assert rows, f"{label}: cqlDivide is not registered"
    for name, ftype in rows:
        assert ftype == "scalar", f"{label}: cqlDivide({name}) is {ftype}, expected scalar"


@pytest.mark.parametrize("a,b,expected", CASES, ids=lambda v: str(v))
def test_cql_divide_three_leg_parity(a: str, b: str, expected: Decimal | None) -> None:
    # Leg 1: native-loaded C++ extension
    native = duckdb.connect(config={"allow_unsigned_extensions": True})
    try:
        register(native, include_fhirpath=False)
        _assert_identity(native, "native")
        got = native.execute("SELECT cqlDivide(?, ?)", [a, b]).fetchone()[0]
    finally:
        native.close()
    assert _matches(got, expected), f"native cqlDivide({a!r}, {b!r}) = {got!r}, expected {expected!r}"

    # Leg 2: forced Python fallback
    py = duckdb.connect()
    try:
        _register_python_supplements(py, cpp_loaded=False, include_fhirpath=False)
        _assert_identity(py, "python")
        got = py.execute("SELECT cqlDivide(?, ?)", [a, b]).fetchone()[0]
    finally:
        py.close()
    assert _matches(got, expected), f"python cqlDivide({a!r}, {b!r}) = {got!r}, expected {expected!r}"

    # Leg 3: no-Python/browser-style runtime
    with no_python_connection() as nopy:
        _assert_identity(nopy, "no-python")
        got = nopy.execute("SELECT cqlDivide(?, ?)", [a, b]).fetchone()[0]
    assert _matches(got, expected), f"no-python cqlDivide({a!r}, {b!r}) = {got!r}, expected {expected!r}"


def _matches(got: object, expected: Decimal | None) -> bool:
    if expected is None:
        return got is None
    if got is None:
        return False
    return Decimal(str(got)) == expected


DIVISION_LIBRARY = """
library DivideFeature version '1.0'
define "D1": 10.0 / 3.0
define "D2": 0.3 div 0.1
define "D3": 1 / 0
define "D4": 9.9 / 3.0
define "D5": -1 / 7
"""

EXPECTED_TRANSLATED: dict[str, Decimal | None] = {
    "D1": Decimal("3.33333333"),
    "D2": Decimal("3"),
    "D3": None,
    "D4": Decimal("3.30000000"),
    "D5": Decimal("-0.14285714"),
}


def test_cql_divide_translated_library_three_leg_parity() -> None:
    from fhir4ds.cql.translator import translate_cql

    sqls = {k: v.to_sql() for k, v in translate_cql(DIVISION_LIBRARY).items()}
    assert "cqlDivide" in sqls["D1"], "translator must still route / through cqlDivide"

    legs: list[tuple[str, duckdb.DuckDBPyConnection]] = []
    native = duckdb.connect(config={"allow_unsigned_extensions": True})
    register(native, include_fhirpath=False)
    legs.append(("native", native))
    py = duckdb.connect()
    _register_python_supplements(py, cpp_loaded=False, include_fhirpath=False)
    legs.append(("python", py))

    try:
        for label, con in legs:
            for name, sql in sqls.items():
                got = con.execute(f"SELECT ({sql})").fetchone()[0]
                expected = EXPECTED_TRANSLATED[name]
                assert _matches(got, expected), (
                    f"{label} translated {name}: got {got!r}, expected {expected!r}"
                )
    finally:
        native.close()
        py.close()

    with no_python_connection() as nopy:
        for name, sql in sqls.items():
            got = nopy.execute(f"SELECT ({sql})").fetchone()[0]
            expected = EXPECTED_TRANSLATED[name]
            assert _matches(got, expected), (
                f"no-python translated {name}: got {got!r}, expected {expected!r}"
            )
