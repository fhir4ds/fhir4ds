"""FP-18 SKEPTIC regression tests: FHIRPath §6.6 div/mod and §6.7 date/time
arithmetic edge cases (spec-compliance campaign, 2026-08-18).

Covers:
- Exact truncated division for Integer/Long operands (§6.6.5/§6.6.6):
  binary64-mediated div/mod silently rounded 64-bit operands.
- Integer literal range lockstep (N1 §22.1: Integer is 32-bit signed;
  Long literals carry the `L` suffix).
- Error contract: Quantity operands to div/mod and invalid §6.7.1 units
  must raise FHIRPathError, not raw TypeError/ValueError.
- §6.6.7 `&` empty-operand semantics and calendar arithmetic clamping.
"""

from __future__ import annotations

import pytest

from ... import evaluate
from ...engine.errors import FHIRPathError
from decimal import Decimal


def _res() -> dict:
    return {"resourceType": "Patient", "id": "p1"}


class TestExactTruncatedDivision:
    """§6.6.5 div / §6.6.6 mod must be exact, truncating toward zero."""

    @pytest.mark.parametrize(
        "expr,expected",
        [
            ("5 div 2", [2]),
            ("-5 div 2", [-2]),
            ("5 div -2", [-2]),
            ("-5 div -2", [2]),
            ("5.5 div 0.7", [7]),
            ("-5.5 div 0.7", [-7]),
            ("10.0 div 4.0", [2]),
            ("5 mod 2", [1]),
            ("-5 mod 2", [-1]),
            ("5 mod -2", [1]),
            ("-5 mod -2", [-1]),
            ("5.5 mod 0.7", ["0.6"]),
            ("2.2 mod 1.8", ["0.4"]),
            ("10.0 mod 4.0", ["2.0"]),
            # 64-bit exactness (FP-18 QA-002): binary64 rounded these.
            ("9223372036854775807L div 1", [9223372036854775807]),
            ("9223372036854775806L div 2", [4611686018427387903]),
            ("2305843009213693951L mod 7", [1]),
            ("-9223372036854775807L div 3", [-3074457345618258602]),
        ],
    )
    def test_div_mod_values(self, expr: str, expected: list) -> None:
        result = evaluate(_res(), expr)
        if isinstance(expected[0], str):
            assert [str(v) for v in result] == expected
        else:
            assert result == expected

    @pytest.mark.parametrize("expr", ["5 div 0", "5 mod 0", "5.5 mod 0"])
    def test_div_mod_by_zero_empty(self, expr: str) -> None:
        assert evaluate(_res(), expr) == []


class TestIntegerLiteralRange:
    """N1 §22.1: Integer is 32-bit signed; Long literals use `L`."""

    def test_int32_max_literal_ok(self) -> None:
        assert evaluate(_res(), "2147483647") == [2147483647]

    def test_unsuffixed_literal_above_int32_rejected(self) -> None:
        with pytest.raises(FHIRPathError):
            evaluate(_res(), "2147483648")

    def test_large_literal_with_explicit_decimal_ok(self) -> None:
        assert evaluate(_res(), "2147483648.0 div 1") == [2147483648]

    def test_long_literal_out_of_int64_rejected(self) -> None:
        with pytest.raises(FHIRPathError):
            evaluate(_res(), "99999999999999999999L")


class TestErrorContract:
    """Invalid operand/unit must signal FHIRPathError (§6.6, §6.7.1)."""

    @pytest.mark.parametrize(
        "expr",
        ["1 'cm' div 2", "1 'cm' mod 2", "2 div 1 'cm'", "true div 1", "true mod 1"],
    )
    def test_quantity_and_boolean_operands_raise(self, expr: str) -> None:
        with pytest.raises(FHIRPathError):
            evaluate(_res(), expr)

    @pytest.mark.parametrize(
        "expr",
        ["@2012-01-01 + 25 hours", "@2012-01-01 + 1 'a'", "@T10:00:00 + 1 day"],
    )
    def test_invalid_temporal_units_raise(self, expr: str) -> None:
        with pytest.raises(FHIRPathError):
            evaluate(_res(), expr)


class TestAmpAndCalendarArithmetic:
    def test_amp_empty_operand_is_empty_string(self) -> None:
        assert evaluate(_res(), "'a' & {}") == ["a"]
        assert evaluate(_res(), "{} & 'b'") == ["b"]

    def test_amp_non_string_singleton_converts(self) -> None:
        assert evaluate(_res(), "1 & 'b'") == ["1b"]
        assert evaluate(_res(), "true & 'x'") == ["truex"]

    @pytest.mark.parametrize(
        "expr,expected",
        [
            ("@2019-01-31 + 1 month", ["2019-02-28"]),
            ("@2020-02-29 + 1 year", ["2021-02-28"]),
            ("@2014 - 24 months", ["2012"]),
            ("@2019-03-01 + 2 weeks", ["2019-03-15"]),
            ("@2015-02-04T14:34:28+10:00 + 1 hour", ["2015-02-04T15:34:28+10:00"]),
            ("@2012-01-01T10 + 90 minutes", ["2012-01-01T11"]),
            ("@2012-01-01 + 1.5 days", ["2012-01-02"]),
            ("@2019-03-01 - 24 months", ["2017-03-01"]),
        ],
    )
    def test_calendar_arithmetic(self, expr: str, expected: list) -> None:
        assert evaluate(_res(), expr) == expected


class TestDualEngineParity:
    """Dual-engine lockstep: native C++ extension vs Python fallback UDF.

    Skips automatically when the bundled native extension cannot be loaded.
    """

    @pytest.fixture(scope="class")
    def connections(self):
        duckdb = pytest.importorskip("duckdb")
        import json

        ext = (
            __file__.rsplit("fhir4ds", 1)[0]
            + "extensions/fhirpath/build/release/repository/v1.5.2/"
            "linux_amd64/fhirpath.duckdb_extension"
        )
        import os

        if not os.path.exists(ext):
            pytest.skip("native fhirpath extension not built")
        native = duckdb.connect(config={"allow_unsigned_extensions": True})
        native.execute(f"LOAD '{ext}'")
        fallback = duckdb.connect()
        from ...duckdb import register_fhirpath

        register_fhirpath(fallback)
        yield native, fallback, json

    @pytest.mark.parametrize(
        "expr",
        [
            "9223372036854775807L div 1",
            "9223372036854775806L div 2",
            "2305843009213693951L mod 7",
            "-9223372036854775807L div 3",
            "0.10000000000000000000000000001 mod 0.1",
            "5.5 div 0.7",
            "5.5 mod 0.7",
            "-5 div 2",
            "5 mod -2",
            "10.0 mod 4.0",
        ],
    )
    def test_native_matches_fallback(self, connections, expr: str) -> None:
        native, fallback, json = connections
        resource = json.dumps({"resourceType": "Patient", "id": "p1"})
        n = native.execute("SELECT fhirpath(?, ?)", [resource, expr]).fetchone()[0]
        f = fallback.execute("SELECT fhirpath(?, ?)", [resource, expr]).fetchone()[0]
        assert n == f, f"native {n!r} != fallback {f!r} for {expr!r}"


class TestIsValidContract:
    """Execution-type errors from FP-18 operators must classify as valid
    expressions (native returns empty for these shapes)."""

    def test_div_mod_operand_mismatches_are_valid(self) -> None:
        from ...duckdb.udf import fhirpath_is_valid_udf

        for expr in ["1 'cm' div 2", "2 div 1 'cm'", "1 'cm' mod 2", "true div 1"]:
            assert fhirpath_is_valid_udf(expr) is True

    def test_invalid_temporal_units_are_valid(self) -> None:
        from ...duckdb.udf import fhirpath_is_valid_udf

        for expr in ["@2012-01-01 + 25 hours", "@T10:00:00 + 1 day"]:
            assert fhirpath_is_valid_udf(expr) is True

    def test_out_of_range_integer_literal_is_invalid(self) -> None:
        from ...duckdb.udf import fhirpath_is_valid_udf

        assert fhirpath_is_valid_udf("2147483648") is False
        assert fhirpath_is_valid_udf("99999999999999999999L") is False

    def test_int64_div_overflow_is_empty_everywhere(self) -> None:
        expr = "-9223372036854775808L div -1"
        assert evaluate(_res(), expr) == []


class TestFP18Historian2026_08_18:
    """FP-18 HISTORIAN launch (2026-08-18) regression coverage.

    Pins:
    - QA-006: `-2147483648` (valid Integer minimum, §4.1.3 — the minus sign
      is unary negation, not part of the literal) must evaluate; overflow
      past INT32 under `-`/`+`/`*` degrades to the exact Decimal value
      (cross-engine doctrine, see `_numeric_arithmetic_result`).
    - QA-002: §6.7 Time ± Quantity results render WITHOUT a leading 'T'
      (§5.5.8 Time toString format hh:mm:ss.fff), matching Time literal
      rendering on both engines.
    """

    def test_int32_minimum_literal_evaluates(self) -> None:
        assert evaluate(_res(), "-2147483648") == [-2147483648]

    def test_int32_minimum_minus_one_degrades_to_decimal(self) -> None:
        # Integer arithmetic overflow degrades to the exact Decimal value
        # (documented cross-engine doctrine shared with the native engine).
        assert evaluate(_res(), "-2147483648 - 1") == [Decimal("-2147483649")]
        assert evaluate(_res(), "2147483647 + 1") == [Decimal("2147483648")]

    def test_int32_bounds_still_enforced(self) -> None:
        with pytest.raises(FHIRPathError):
            evaluate(_res(), "2147483648")
        with pytest.raises(FHIRPathError):
            evaluate(_res(), "-2147483649")

    @pytest.mark.parametrize(
        "expr,expected",
        [
            ("@T10:30:00 + 1 minutes", ["10:31:00"]),
            ("@T10:30:00 + 90 minutes", ["12:00:00"]),
            ("@T10:30:00 - 90 minutes", ["09:00:00"]),
            ("@T10:30 + 90 minutes", ["12:00"]),
            ("@T10:30:00 + 90 's'", ["10:31:30"]),
        ],
    )
    def test_time_arithmetic_renders_without_leading_t(self, expr: str, expected: list) -> None:
        assert evaluate(_res(), expr) == expected


class TestDualEngineParityHistorianFP18:
    """FP-18 HISTORIAN QA-002: native §6.7 Time ± Quantity results must
    render without the leading 'T' (§5.5.8), matching the fallback."""

    @pytest.fixture(scope="class")
    def connections(self):
        duckdb = pytest.importorskip("duckdb")
        import json
        import os

        ext = (
            __file__.rsplit("fhir4ds", 1)[0]
            + "extensions/fhirpath/build/release/repository/v1.5.2/"
            "linux_amd64/fhirpath.duckdb_extension"
        )
        if not os.path.exists(ext):
            pytest.skip("native fhirpath extension not built")
        native = duckdb.connect(config={"allow_unsigned_extensions": True})
        native.execute(f"LOAD '{ext}'")
        fallback = duckdb.connect()
        from ...duckdb import register_fhirpath

        register_fhirpath(fallback)
        yield native, fallback, json

    def test_time_arithmetic_parity_no_leading_t(self, connections) -> None:
        native, fallback, json = connections
        resource = json.dumps({"resourceType": "Observation", "t": "10:30:00"})
        for expr in [
            "@T10:30:00 + 1 minutes",
            "t + 90 minutes",
            "@T10:30:00 - 30 seconds",
        ]:
            n = native.execute(
                "SELECT fhirpath_text(?, ?)", [resource, expr]
            ).fetchone()[0]
            f = fallback.execute(
                "SELECT fhirpath_text(?, ?)", [resource, expr]
            ).fetchone()[0]
            assert n == f, f"native {n!r} != fallback {f!r} for {expr!r}"
            assert not str(n).startswith("T"), f"leading T leaked: {n!r}"


class TestFP18Explorer2026_08_18:
    """FP-18 EXPLORER launch 3 (2026-08-18): §6.6 unary-minus Long
    overflow doctrine and §6.6.7 `&` implicit conversion of complex JSON
    values."""

    def test_unary_minus_long_min_overflow_degrades_to_decimal(self) -> None:
        # §6.6 overflow doctrine: Integer/Long arithmetic overflow degrades
        # to the exact Decimal value (binary `+` path does this on both
        # engines); unary negation must not emit an out-of-int64 raw int.
        out = evaluate(_res(), "- -9223372036854775808L")
        assert out == [Decimal("9223372036854775808")]
        assert isinstance(out[0], Decimal)

    def test_unary_minus_long_min_nested(self) -> None:
        assert evaluate(_res(), "-(- -9223372036854775808L)") == [
            Decimal("-9223372036854775808")
        ]

    def test_unary_minus_in_range_longs_unchanged(self) -> None:
        assert evaluate(_res(), "- -9223372036854775807L") == [9223372036854775807]
        assert evaluate(_res(), "- 9223372036854775808L") == [-9223372036854775808]

    def test_amp_complex_value_uses_json_serialization(self) -> None:
        # §6.6.7: implicit string conversion of complex JSON values must
        # serialize as compact JSON (native yyjson behavior), never Python
        # dict repr with single quotes/spaces.
        res = {
            "resourceType": "Observation",
            "qs": {"value": 3, "unit": "cm", "code": "cm"},
            "nested": {"a": [1, {"b": "x"}]},
        }
        assert evaluate(res, "qs & ''") == ['{"value":3,"unit":"cm","code":"cm"}']
        assert evaluate(res, "'x' & qs") == ['x{"value":3,"unit":"cm","code":"cm"}']
        assert evaluate(res, "nested & ''") == ['{"a":[1,{"b":"x"}]}']

    def test_amp_primitive_conversions_unchanged(self) -> None:
        res = {"resourceType": "Patient"}
        assert evaluate(res, "1 & 2") == ["12"]
        assert evaluate(res, "true & 'x'") == ["truex"]
        assert evaluate(res, "5 'cm' & ''") == ["5 'cm'"]
        assert evaluate(res, "@2020-06-01 & ''") == ["2020-06-01"]


class TestDualEngineParityExplorerFP18:
    """Native-vs-fallback parity for the EXPLORER launch-3 fixes."""

    @pytest.fixture(scope="class")
    def connections(self):
        duckdb = pytest.importorskip("duckdb")
        import json
        import os

        ext = (
            __file__.rsplit("fhir4ds", 1)[0]
            + "extensions/fhirpath/build/release/repository/v1.5.2/"
            "linux_amd64/fhirpath.duckdb_extension"
        )
        if not os.path.exists(ext):
            pytest.skip("native fhirpath extension not built")
        native = duckdb.connect(config={"allow_unsigned_extensions": True})
        native.execute(f"LOAD '{ext}'")
        fallback = duckdb.connect()
        from ...duckdb import register_fhirpath

        register_fhirpath(fallback)
        yield native, fallback, json

    def test_unary_minus_long_min_parity(self, connections) -> None:
        native, fallback, json = connections
        resource = json.dumps({"resourceType": "Patient"})
        for expr in [
            "- -9223372036854775808L",
            "-(- -9223372036854775808L)",
            "- -9223372036854775807L",
        ]:
            n = native.execute(
                "SELECT fhirpath_text(?, ?)", [resource, expr]
            ).fetchone()[0]
            f = fallback.execute(
                "SELECT fhirpath_text(?, ?)", [resource, expr]
            ).fetchone()[0]
            assert n == f, f"native {n!r} != fallback {f!r} for {expr!r}"
        n = native.execute(
            "SELECT fhirpath_text(?, ?)", [resource, "- -9223372036854775808L"]
        ).fetchone()[0]
        assert n == "9223372036854775808.0"

    def test_amp_complex_value_parity(self, connections) -> None:
        native, fallback, json = connections
        resource = json.dumps(
            {
                "resourceType": "Observation",
                "qs": {"value": 3, "unit": "cm", "code": "cm"},
            }
        )
        for expr in ["qs & ''", "'x' & qs"]:
            n = native.execute(
                "SELECT fhirpath_text(?, ?)", [resource, expr]
            ).fetchone()[0]
            f = fallback.execute(
                "SELECT fhirpath_text(?, ?)", [resource, expr]
            ).fetchone()[0]
            assert n == f, f"native {n!r} != fallback {f!r} for {expr!r}"
            # Python-repr leak guard: canonical JSON has no spaces after ':'
            assert ": " not in str(f) and ", " not in str(f)
