"""CQL-01 spec-compliance regression tests: CQL 1.5 primitive types.

Execution-level tests (translate_cql -> SQL -> DuckDB with registered CQL
macros) covering chunk CQL-01 fixes:

- QA-001: Integer/Long arithmetic overflow returns null at runtime
  (CQL 1.5 logical spec: "If the result ... cannot be represented
  (i.e. arithmetic overflow), the result is null").
- QA-002: `maximum Decimal + maximum Decimal` is numeric addition, not
  string concatenation (result limited to implementation precision).
- QA-003: ToDecimal accepts strings with more fractional digits than the
  implementation scale, limiting the value (rounding), null only for
  malformed input.
- QA-004: Decimal literals with >8 fractional digits are precision-limited,
  not rejected.
- QA-005: Truncate returns an Integer.
- QA-006: CanConvert(x, T) lowers to a supported runtime conversion check.
"""

import duckdb
import pytest

from ... import translate_cql
from ...duckdb.extension import register_cql


def evaluate(expr: str, name: str = "X"):
    cql = f"library T version '1.0'\ndefine {name}:\n  {expr}\n"
    result = translate_cql(cql)
    con = duckdb.connect()
    register_cql(con)
    return con.execute(f"SELECT {result[name].to_sql()}").fetchone()[0]


class TestIntegerOverflowNull:
    """QA-001: runtime Integer/Long overflow must yield null, not errors."""

    def test_maximum_integer_plus_one_is_null(self):
        assert evaluate("maximum Integer + 1") is None

    def test_minimum_integer_minus_one_is_null(self):
        assert evaluate("minimum Integer - 1") is None

    def test_maximum_long_plus_one_is_null(self):
        assert evaluate("maximum Long + 1") is None

    def test_minimum_long_minus_one_is_null(self):
        assert evaluate("minimum Long - 1") is None

    def test_in_range_runtime_arithmetic_unaffected(self):
        assert evaluate("maximum Long - 1") == 9223372036854775806
        assert evaluate("maximum Integer - 1") == 2147483646

    def test_extent_values_unchanged(self):
        assert evaluate("maximum Integer") == 2147483647
        assert evaluate("minimum Integer") == -2147483648
        assert evaluate("maximum Long") == 9223372036854775807
        assert evaluate("minimum Long") == -9223372036854775808


class TestDecimalExtentArithmetic:
    """QA-002: Decimal extents are numeric operands for '+'."""

    def test_maximum_decimal_addition_is_numeric(self):
        value = evaluate("maximum Decimal + maximum Decimal")
        # Numeric addition limited to implementation precision (38,8);
        # must NOT be a concatenated string.
        assert value is not None
        assert not isinstance(value, str)
        assert str(value).replace(".", "").isdigit()

    def test_maximum_decimal_value(self):
        assert str(evaluate("maximum Decimal")) == "99999999999999999999.99999999"


class TestToDecimalScaleLimiting:
    """QA-003: ToDecimal limits precision instead of returning null."""

    def test_more_than_8_fractional_digits_rounds(self):
        assert str(evaluate("ToDecimal('0.123456789')")) == "0.12345679"

    def test_8_fractional_digits_unchanged(self):
        assert str(evaluate("ToDecimal('0.12345678')")) == "0.12345678"

    def test_malformed_string_still_null(self):
        assert evaluate("ToDecimal('abc')") is None
        assert evaluate("ToDecimal('+-0.1')") is None
        assert evaluate("ToDecimal('1e3')") is None


class TestDecimalLiteralScaleLimiting:
    """QA-004: >8 fractional digit literals are limited, not rejected."""

    def test_literal_rounds_half_up(self):
        assert str(evaluate("1.555555555")) == "1.55555556"

    def test_literal_in_arithmetic(self):
        assert str(evaluate("1.555555555 + 0")) == "1.55555556"

    def test_28_integer_digit_limit_still_enforced(self):
        from ...parser import parse_cql
        with pytest.raises(ValueError):
            parse_cql(
                "library T\ndefine X:\n  12345678901234567890123456789.0"
            )


class TestTruncateReturnsInteger:
    """QA-005: Truncate(argument Decimal) Integer."""

    def test_truncate_integer_type(self):
        assert isinstance(evaluate("Truncate(1.9)"), int)
        assert evaluate("Truncate(1.9)") == 1

    def test_truncate_negative(self):
        assert evaluate("Truncate(-1.5)") == -1

    def test_truncate_null(self):
        assert evaluate("Truncate(null)") is None


class TestCanConvert:
    """QA-006: CanConvert lowers to a supported runtime check."""

    def test_can_convert_true(self):
        assert evaluate("CanConvert(1, Decimal)") is True
        assert evaluate("CanConvert('1', Integer)") is True

    def test_can_convert_false(self):
        assert evaluate("CanConvert(1.5, Integer)") is False
        assert evaluate("CanConvert('x', Integer)") is False

    def test_unsupported_target_raises_translation_error(self):
        from ...errors import TranslationError
        with pytest.raises(TranslationError):
            evaluate("CanConvert(1, SomeUnknownModelType)")


class TestDecimalDivision:
    """HISTORIAN QA-001: `/` is Decimal division at implementation scale 8.

    CQL 1.5 §16.4 Divide: "this operator is Decimal division"; Decimal
    values are limited to the implementation precision/scale (28/8). The
    DuckDB-native `/` promotes DECIMAL to DOUBLE and produces artifacts
    (spec example ``9.9 / 3.0 // 3.3`` used to yield 3.3000000000000003).
    """

    def test_spec_example_99_div_3(self):
        assert str(evaluate("9.9 / 3.0")) == "3.30000000"

    def test_third_rounds_to_scale_8(self):
        assert evaluate("1 / 3 = 0.33333333") is True
        assert str(evaluate("1 / 3")) == "0.33333333"

    def test_division_by_zero_is_null(self):
        assert evaluate("2.2 / 0") is None
        assert evaluate("1 / 0") is None

    def test_division_null_propagation(self):
        assert evaluate("2.2 / null") is None

    def test_integer_operands_promote_to_decimal(self):
        assert str(evaluate("4 / 2")) == "2.00000000"

    def test_negative_division(self):
        assert str(evaluate("-9.9 / 3.0")) == "-3.30000000"

    def test_extreme_representable_quotient(self):
        # Largest representable quotient: 28 significant digits (the
        # implementation Decimal precision), computed exactly — not a
        # DOUBLE approximation.
        assert str(evaluate("maximum Decimal / 0.00000001")) == (
            "9999999999999999999999999999.00000000"
        )


class TestSumListTyping:
    """HISTORIAN QA-002: Sum over primitive lists keeps the spec result type.

    CQL 1.5 §20 Sum: Sum(List<Integer>) Integer, Sum(List<Long>) Long,
    Sum(List<Decimal>) Decimal; arithmetic overflow yields null.
    """

    def test_decimal_sum_is_exact(self):
        assert evaluate("Sum({0.1, 0.2}) = 0.3") is True
        assert str(evaluate("Sum({0.1, 0.2})")) == "0.3"

    def test_integer_sum_returns_integer(self):
        assert isinstance(evaluate("Sum({1, 2})"), int)
        assert str(evaluate("ToString(Sum({1, 2}))")) == "3"

    def test_long_sum_returns_long(self):
        assert evaluate("Sum({1L, 2L})") == 3
        assert str(evaluate("ToString(Sum({1L, 2L}))")) == "3"

    def test_long_sum_overflow_is_null(self):
        assert evaluate("Sum({maximum Long, 1})") is None

    def test_integer_sum_overflow_is_null(self):
        assert evaluate("Sum({maximum Integer, 1})") is None

    def test_null_elements_skipped(self):
        assert evaluate("Sum({null as Integer, 1})") == 1

    def test_all_null_elements_is_null(self):
        assert evaluate("Sum({null as Long, null as Long})") is None

    def test_null_list_is_null(self):
        assert evaluate("Sum(null as List<Long>)") is None


class TestAvgListTyping:
    """HISTORIAN QA-003: Avg/Median over primitive lists return Decimal.

    CQL 1.5 §20: Avg returns Decimal for Integer/Long/Decimal sources;
    the result must not carry binary floating-point artifacts.
    """

    def test_avg_decimal_exact(self):
        assert evaluate("Avg({0.1, 0.2}) = 0.15") is True
        assert str(evaluate("Avg({0.1, 0.2})")) == "0.15000000"

    def test_avg_integer_source(self):
        assert str(evaluate("Avg({1, 2})")) == "1.50000000"

    def test_avg_long_source(self):
        assert str(evaluate("Avg({1L, 2L})")) == "1.50000000"

    def test_median_decimal_typed(self):
        assert str(evaluate("Median({0.1, 0.2})")) == "0.15000000"

    def test_stddev_decimal_typed(self):
        assert str(evaluate("StdDev({1.0, 2.0, 3.0})")) == "1.00000000"


class TestDefineAliasArithmeticExactness:
    """CQL-01 EXPLORER: arithmetic over library-defined scalar constants.

    Definition-alias scalar references must not be forced through DOUBLE
    when mixed with numeric literals: Decimal arithmetic stays exact at
    implementation precision (CQL 1.5 09-b Types/Arithmetic) and
    Integer/Long overflow yields null (CQL 1.5 logical spec §9.1.1).
    """

    @staticmethod
    def evaluate_population(defines: str, output: str):
        from ...parser import parse_cql
        from ...translator import CQLToSQLTranslator

        cql = (
            "library T version '1'\n"
            "using FHIR version '4.0.1'\n"
            "context Patient\n" + defines
        )
        sql = CQLToSQLTranslator().translate_library_to_population_sql(
            parse_cql(cql), output_columns={output: output}
        )
        con = duckdb.connect()
        register_cql(con)
        try:
            con.execute(
                "CREATE TABLE resources (id VARCHAR, resourceType VARCHAR, "
                "resource JSON, patient_ref VARCHAR)"
            )
            con.execute(
                "INSERT INTO resources VALUES ('p1', 'Patient', ?::JSON, 'p1')",
                ['{"resourceType":"Patient","id":"p1"}'],
            )
            rows = con.execute(sql).fetchall()
            return rows[0][1] if rows else None
        finally:
            con.close()

    def test_decimal_alias_plus_literal_exact(self):
        value = self.evaluate_population(
            "define M: 0.1\ndefine N: M + 0.2\ndefine Out: N", "Out"
        )
        assert str(value) == "0.30000000"
        assert self.evaluate_population(
            "define M: 0.1\ndefine N: M + 0.2\ndefine Out: N = 0.3", "Out"
        ) is True

    def test_decimal_alias_chain_equality_exact(self):
        got = self.evaluate_population(
            "define D: 0.1\ndefine Out: D + 0.2 = 0.3", "Out"
        )
        assert got is True

    def test_integer_alias_overflow_null(self):
        got = self.evaluate_population(
            "define I: 2147483647\ndefine Out: I + 1", "Out"
        )
        assert got is None

    def test_long_alias_overflow_null(self):
        got = self.evaluate_population(
            "define L: 9223372036854775807L\ndefine Out: L + 1", "Out"
        )
        assert got is None

    def test_integer_alias_in_range_keeps_integer_type(self):
        got = self.evaluate_population(
            "define I: 2147483646\ndefine Out: I + 1", "Out"
        )
        assert got == 2147483647
        assert isinstance(got, int)

    def test_long_alias_in_range_keeps_long_type(self):
        got = self.evaluate_population(
            "define L: 2147483647L\ndefine Out: L * 2", "Out"
        )
        assert got == 4294967294


class TestDecimalLiteralExtent:
    """CQL-01 EXPLORER: out-of-extent Decimal literals are fixture-pinned INTENDED.

    The official CQL conformance fixtures (ValueLiteralsAndSelectors.xml)
    pin 28-int-digit literals such as 10000000000000000000000000000.00000000
    (+/-10*1000000000000000000000000000.00000000 forms) as VALID Decimal
    selectors. Official fixtures outrank the (10^28-1)/10^8 "maximum Decimal"
    prose, so the translator must not reject out-of-extent Decimal literals
    (Integer/Long range rejections remain because fixtures pin those).
    """

    def test_boundary_extent_literal_accepted(self):
        assert evaluate("99999999999999999999.99999999") is not None

    def test_28_int_digit_literal_accepted_per_parser_policy(self):
        # Parser policy (CQL §2.3, fixture-compatible): up to 28 integer
        # digits accepted; 29 rejected with a translation ValueError.
        assert evaluate("1000000000000000000000000000.00000000") is not None

    def test_29_int_digit_literal_rejected(self):
        with pytest.raises(ValueError, match="28 integer digits"):
            evaluate("100000000000000000000000000000.0")

    def test_plain_decimal_literals_unaffected(self):
        assert evaluate("0.1 + 0.2 = 0.3") is True
