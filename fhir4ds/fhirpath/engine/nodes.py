from collections import abc
import calendar
import copy
from datetime import datetime, timedelta, timezone
from dateutil.relativedelta import relativedelta
from dateutil import parser, tz
from decimal import ROUND_HALF_UP, ROUND_UP, Decimal
import math
import json
from pathlib import Path
import re
import time
from typing import Optional

_MODELS_DIR = Path(__file__).parent.parent / "models" / "r4"


def _load_json(filename: str):
    """Load a JSON file from the models/r4/ directory."""
    with open(_MODELS_DIR / filename) as f:
        return json.load(f)


_VALID_FHIR_TYPES = (
    set(_load_json("valid_fhir_types.json"))
    | set(_load_json("type2Parent.json"))
    | set(_load_json("fhir_type_hierarchy.json"))
)


# Time regex - NO timezone allowed for Time literals per FHIRPath spec
# Time literals are @T14, @T14:34, @T14:34:28, @T14:34:28.123
# Time with timezone (Z or offset) should be an error
timeRE = re.compile(
    r"^T?([0-9]{2})(?::([0-9]{2}))?(?::([0-9]{2}))?(?:\.([0-9]+))?$"
)
# Time regex that matches time WITH timezone (for error detection)
timeWithTzRE = re.compile(
    r"^T?([0-9]{2})(?::([0-9]{2}))?(?::([0-9]{2}))?(?:\.([0-9]+))?(Z|(\+|-)[0-9]{2}(:[0-9]{2})?)$"
)
# Date regex - matches year, year-month, or full date WITHOUT 'T'
dateRE = re.compile(r"^(?P<year>[0-9]{4})(?:-(?P<month>[0-9]{2})(?:-(?P<day>[0-9]{2}))?)?$")
# DateTime regex - matches date with 'T' (optionally followed by time components and timezone)
# Key change: T can be followed by optional time, or just T alone (e.g., @2015T)
dateTimeRE = re.compile(r"^(?P<year>[0-9]{4})(?:-(?P<month>[0-9]{2})(?:-(?P<day>[0-9]{2}))?)?T(?:(?P<hour>[0-9]{2})(?::(?P<minute>[0-9]{2}))?(?::(?P<second>[0-9]{2}))?(?:\.(?P<millisecond>[0-9]+))?(?P<timezone>Z|(\+|-)[0-9]{2}:[0-9]{2})?)?$")


class FP_Type:
    """
    Class FP_Type is the superclass for FHIRPath types that required special handling
    """

    def equals(self):
        """
        Tests whether this object is equal to another.  Returns either True,
        false, or undefined (where in the FHIRPath specification empty would be
        returned).  The undefined return value indicates that the values were the
        same to the shared precision, but that they had differnent levels of
        precision.
        """
        return False

    def equivalentTo(self):
        """
        Tests whether this object is equivalant to another.  Returns either True,
        false, or undefined (where in the FHIRPath specification empty would be
        returned).
        """
        return False

    def toString(self):
        return str(self)

    def toJSON(self):
        return str(self)

    def compare(self):
        raise NotImplementedError()


class FP_Quantity(FP_Type):
    """
    A map of the UCUM units that must be paired with integer values when doing arithmetic.
    """

    timeUnitsToUCUM = {
        "years": "'a'",
        "months": "'mo'",
        "weeks": "'wk'",
        "days": "'d'",
        "hours": "'h'",
        "minutes": "'min'",
        "seconds": "'s'",
        "milliseconds": "'ms'",
        "year": "'a'",
        "month": "'mo'",
        "week": "'wk'",
        "day": "'d'",
        "hour": "'h'",
        "minute": "'min'",
        "second": "'s'",
        "millisecond": "'ms'",
        "'a'": "'a'",
        "'mo'": "'mo'",
        "'wk'": "'wk'",
        "'d'": "'d'",
        "'h'": "'h'",
        "'min'": "'min'",
        "'s'": "'s'",
        "'ms'": "'ms'",
    }

    mapUCUMCodeToTimeUnits = {
        "'a'": "year",
        "'mo'": "month",
        "'wk'": "week",
        "'d'": "day",
        "'h'": "hour",
        "'min'": "minute",
        "'s'": "second",
        "'ms'": "millisecond",
    }

    """
    A map of the UCUM units that must be paired with integer values when doing arithmetic.
    """
    integerUnits = {
        "'a'": True,
        "'mo'": True,
        "'wk'": True,
        "'d'": True,
        "'h'": True,
        "'min'": True,
    }

    _years_and_months = [
        "'a'",
        "year",
        "years",
        "'mo'",
        "month",
        "months",
    ]

    _weeks_days_and_time = [
        "'wk'",
        "week",
        "weeks",
        "'d'",
        "day",
        "days",
        "'h'",
        "hour",
        "hours",
        "'min'",
        "minute",
        "minutes",
        "'s'",
        "second",
        "seconds",
        "'ms'",
        "millisecond",
        "milliseconds",
    ]
    _calendar_duration_units = {
        "year",
        "years",
        "month",
        "months",
        "week",
        "weeks",
        "day",
        "days",
        "hour",
        "hours",
        "minute",
        "minutes",
        "second",
        "seconds",
        "millisecond",
        "milliseconds",
    }
    _ucum_duration_units = {
        "'a'",
        "'mo'",
        "'wk'",
        "'d'",
        "'h'",
        "'min'",
        "'s'",
        "'ms'",
        "a",
        "mo",
        "wk",
        "d",
        "h",
        "min",
        "s",
        "ms",
    }
    # FP-01 SKEPTIC QA-003 (2026-08-16): calendar year/month keywords are
    # not comparable with their UCUM year/month analogues (§6.1.1/§6.2:
    # `1 year = 1 'a'` // empty, `1 year > 1 'a'` // empty), but they ARE
    # comparable with day-and-below durations via the §5.5.7 factors
    # (1 month = 30 days, and 30 'd' is exactly 30 days).
    _year_month_ucum_units = {"'a'", "'mo'", "a", "mo"}
    _second_or_millisecond_duration_units = {
        "second",
        "seconds",
        "millisecond",
        "milliseconds",
        "'s'",
        "'ms'",
        "s",
        "ms",
    }

    _arithmetic_duration_units = {
        "years": "year",
        "months": "month",
        "weeks": "week",
        "days": "day",
        "hours": "hour",
        "minutes": "minute",
        "seconds": "second",
        "milliseconds": "millisecond",
        "year": "year",
        "month": "month",
        "week": "week",
        "day": "day",
        "hour": "hour",
        "minute": "minute",
        "second": "second",
        "millisecond": "millisecond",
        "'wk'": "week",
        "'d'": "day",
        "'h'": "hour",
        "'min'": "minute",
        "'s'": "second",
        "'ms'": "millisecond",
        "'year'": "year",
        "'month'": "month",
        "'week'": "week",
        "'day'": "day",
        "'hour'": "hour",
        "'minute'": "minute",
        "'second'": "second",
        "'millisecond'": "millisecond",
    }

    # Conversion factor groups are intentionally separated by dimension to prevent
    # cross-dimension conversions (e.g., 'cm' to 'seconds' is not possible).
    # conv_unit_to() checks each group independently and returns None if no match.
    _year_month_conversion_factor = {
        "'a'": 12, "'mo'": 1,
        "year": 12, "years": 12,
        "month": 1, "months": 1,
    }
    _m_cm_mm_conversion_factor = {"'m'": Decimal("1"), "'cm'": Decimal("0.01"), "'mm'": Decimal("0.001")}
    _lbs_kg_conversion_factor = {"'kg'": Decimal("1"), "'[lb_av]'": Decimal("0.453592")}
    _g_mg_conversion_factor = {
        "'kg'": Decimal("1000"),
        "'g'": Decimal("1"),
        "'mg'": Decimal("0.001"),
    }
    _ucum_base_conversion_factor = {
        "ms": ("'s'", Decimal("0.001")),
        "'ms'": ("'s'", Decimal("0.001")),
        "millisecond": ("'s'", Decimal("0.001")),
        "milliseconds": ("'s'", Decimal("0.001")),
        "s": ("'s'", Decimal("1")),
        "'s'": ("'s'", Decimal("1")),
        "second": ("'s'", Decimal("1")),
        "seconds": ("'s'", Decimal("1")),
        "min": ("'s'", Decimal("60")),
        "'min'": ("'s'", Decimal("60")),
        "minute": ("'s'", Decimal("60")),
        "minutes": ("'s'", Decimal("60")),
        "h": ("'s'", Decimal("3600")),
        "'h'": ("'s'", Decimal("3600")),
        "hour": ("'s'", Decimal("3600")),
        "hours": ("'s'", Decimal("3600")),
        "d": ("'s'", Decimal("86400")),
        "'d'": ("'s'", Decimal("86400")),
        "day": ("'s'", Decimal("86400")),
        "days": ("'s'", Decimal("86400")),
        "wk": ("'s'", Decimal("604800")),
        "'wk'": ("'s'", Decimal("604800")),
        "week": ("'s'", Decimal("604800")),
        "weeks": ("'s'", Decimal("604800")),
        "mo": ("'s'", Decimal("2629746")),
        "month": ("'s'", Decimal("2629746")),
        "months": ("'s'", Decimal("2629746")),
        "a": ("'s'", Decimal("31556952")),
        "year": ("'s'", Decimal("31556952")),
        "years": ("'s'", Decimal("31556952")),
        "mm": ("'m'", Decimal("0.001")),
        "'mm'": ("'m'", Decimal("0.001")),
        "cm": ("'m'", Decimal("0.01")),
        "'cm'": ("'m'", Decimal("0.01")),
        "m": ("'m'", Decimal("1")),
        "'m'": ("'m'", Decimal("1")),
        "km": ("'m'", Decimal("1000")),
        "'km'": ("'m'", Decimal("1000")),
        "[in_i]": ("'m'", Decimal("0.0254")),
        "'[in_i]'": ("'m'", Decimal("0.0254")),
        "in": ("'m'", Decimal("0.0254")),
        "inch": ("'m'", Decimal("0.0254")),
        "[ft_i]": ("'m'", Decimal("0.3048")),
        "'[ft_i]'": ("'m'", Decimal("0.3048")),
        "ft": ("'m'", Decimal("0.3048")),
        "foot": ("'m'", Decimal("0.3048")),
        "m2": ("'m2'", Decimal("1")),
        "'m2'": ("'m2'", Decimal("1")),
        "cm2": ("'m2'", Decimal("0.0001")),
        "'cm2'": ("'m2'", Decimal("0.0001")),
        "ug": ("'g'", Decimal("0.000001")),
        "'ug'": ("'g'", Decimal("0.000001")),
        "mg": ("'g'", Decimal("0.001")),
        "'mg'": ("'g'", Decimal("0.001")),
        "g": ("'g'", Decimal("1")),
        "'g'": ("'g'", Decimal("1")),
        "kg": ("'g'", Decimal("1000")),
        "'kg'": ("'g'", Decimal("1000")),
        "[lb_av]": ("'g'", Decimal("453.59237")),
        "'[lb_av]'": ("'g'", Decimal("453.59237")),
        "lb": ("'g'", Decimal("453.59237")),
        "[oz_av]": ("'g'", Decimal("28.349523")),
        "'[oz_av]'": ("'g'", Decimal("28.349523")),
        "oz": ("'g'", Decimal("28.349523")),
        "uL": ("'L'", Decimal("0.000001")),
        "mL": ("'L'", Decimal("0.001")),
        "dL": ("'L'", Decimal("0.1")),
        "L": ("'L'", Decimal("1")),
        "Pa": ("'Pa'", Decimal("1")),
        "kPa": ("'Pa'", Decimal("1000")),
        "mm[Hg]": ("'Pa'", Decimal("133.322")),
        "mmHg": ("'Pa'", Decimal("133.322")),
        "cm[H2O]": ("'Pa'", Decimal("98.0665")),
        "cmH2O": ("'Pa'", Decimal("98.0665")),
        # FP-02 HISTORIAN QA-004 (2026-08-16): curated UCUM derived units
        # (N1 §6.1.1: quantity equality/ordering must convert commensurable
        # units "to the same unit, or a common unit"). Base forms use the
        # SAME sorted, quoted spelling `_render_unit_exponents` produces so
        # single-entry and multi-term reductions agree on one canonical
        # string: 1 J = 1 kg.m2/s2 = 1000 g.m2/s2, 1 N = 1000 g.m/s2,
        # 1 W = 1000 g.m2/s3, 1 V = 1000 A.g.m2/s3, 1 A is its own base.
        "J": ("'g.m2/s2'", Decimal("1000")),
        "'J'": ("'g.m2/s2'", Decimal("1000")),
        "kJ": ("'g.m2/s2'", Decimal("1000000")),
        "'kJ'": ("'g.m2/s2'", Decimal("1000000")),
        "N": ("'g.m/s2'", Decimal("1000")),
        "'N'": ("'g.m/s2'", Decimal("1000")),
        "kN": ("'g.m/s2'", Decimal("1000000")),
        "'kN'": ("'g.m/s2'", Decimal("1000000")),
        "W": ("'g.m2/s3'", Decimal("1000")),
        "'W'": ("'g.m2/s3'", Decimal("1000")),
        "kW": ("'g.m2/s3'", Decimal("1000000")),
        "'kW'": ("'g.m2/s3'", Decimal("1000000")),
        "mW": ("'g.m2/s3'", Decimal("1")),
        "'mW'": ("'g.m2/s3'", Decimal("1")),
        "A": ("'A'", Decimal("1")),
        "'A'": ("'A'", Decimal("1")),
        "mA": ("'A'", Decimal("0.001")),
        "'mA'": ("'A'", Decimal("0.001")),
        "V": ("'g.m2/A.s3'", Decimal("1000")),
        "'V'": ("'g.m2/A.s3'", Decimal("1000")),
        "kV": ("'g.m2/A.s3'", Decimal("1000000")),
        "'kV'": ("'g.m2/A.s3'", Decimal("1000000")),
        "mV": ("'g.m2/A.s3'", Decimal("1")),
        "'mV'": ("'g.m2/A.s3'", Decimal("1")),
        "Cel": ("'Cel'", Decimal("1")),
        "mg/dL": ("'mg/dL'", Decimal("1")),
        "g/dL": ("'mg/dL'", Decimal("1000")),
        "mmol/L": ("'mmol/L'", Decimal("1")),
        "ug/mL": ("'ug/mL'", Decimal("1")),
        "/min": ("'/min'", Decimal("1")),
        "1": ("'1'", Decimal("1")),
        "%": ("'1'", Decimal("0.01")),
    }

    datetime_multipliers = {
        **{key: Decimal("604800") for key in ["'wk'", "week", "weeks"]},
        **{key: Decimal("86400") for key in ["'d'", "day", "days"]},
        **{key: Decimal("3600") for key in ["'h'", "hour", "hours"]},
        **{key: Decimal("60") for key in ["'min'", "minute", "minutes"]},
        **{key: Decimal("1") for key in ["'s'", "second", "seconds"]},
        **{key: Decimal("0.001") for key in ["'ms'", "millisecond", "milliseconds"]},
    }

    # FP-01 SKEPTIC QA-003 (2026-08-16): FHIRPath N1 §5.5.7 defines calendar
    # duration conversion factors for UNANCHORED calculations: 1 month = 30
    # days, 1 year = 365 days (and 1 year = 12 months). §6.1.1/§6.2 require
    # unit-aware equality/comparison to honor "the calendar durations as
    # defined in the toQuantity function". UCUM 'mo'/'a' are definite
    # durations and keep their UCUM mean-duration seconds; only the calendar
    # KEYWORDS use these factors. Note the spec table is month-based for
    # year↔month pairs (1 year = 12 months) and day-based for year/month vs
    # day-and-below (12 × 30 days = 360 days ≠ 365 days), so year↔month pairs
    # must be compared in months, never through these seconds factors.
    _calendar_unanchored_seconds_factor = {
        "month": Decimal("2592000"),
        "months": Decimal("2592000"),
        "year": Decimal("31536000"),
        "years": Decimal("31536000"),
    }

    @staticmethod
    def _unanchored_duration_seconds(unit, value):
        """Seconds value of a time-valued quantity for unanchored equality,
        equivalence, and ordering per §5.5.7: calendar month/year keywords use
        the 30-day/365-day factors; every other time unit (UCUM durations and
        calendar week-and-below keywords, which the spec defines as exactly
        equal to their UCUM counterparts) converts through the UCUM base
        table. Returns (seconds, "'s'") or None for non-time units."""
        factor = FP_Quantity._calendar_unanchored_seconds_factor.get(unit)
        if factor is not None:
            return Decimal(str(value)) * factor, "'s'"
        base = FP_Quantity.conv_unit_to_base(unit, value)
        if base.unit not in ("'s'", "s"):
            return None
        return Decimal(str(base.value)), "'s'"

    def __init__(self, value, unit):
        super().__init__()
        # FP-01 SKEPTIC QA-001/QA-002/QA-006 (2026-08-16): FHIRPath
        # §4.1.8 allows a Quantity literal's unit to be a single-quoted
        # calendar duration keyword, singular or plural (`4 'year'`,
        # `2 'days'`), and the Time-valued Quantities table defines
        # `'year'` etc. as the *unit representation* of the calendar
        # keywords — the same quantity as the bare keyword form.
        # Canonicalize quoted keyword spellings to the bare form so the
        # equality/comparison/arithmetic guards that match bare
        # spellings treat them identically. This mirrors the native C++
        # lexer, which stores STRING units unquoted. Genuine UCUM units
        # ('a', 'mo', 'wk', ...) are NOT keyword spellings and keep
        # their quotes.
        if isinstance(unit, str) and len(unit) >= 2 and unit[0] == "'" and unit[-1] == "'":
            inner = unit[1:-1]
            if inner in self._calendar_duration_units:
                unit = inner
        self.asStr = f"{self._format_quantity_number(value)} {unit}"
        self.value = value
        self.unit = unit

    @staticmethod
    def _format_quantity_number(value):
        if isinstance(value, Decimal):
            return format(value, "f")
        if isinstance(value, float):
            text = str(value)
            if "e" in text.lower():
                text = format(Decimal(text), "f")
                if "." in text:
                    text = text.rstrip("0").rstrip(".")
                return "0" if text in {"", "-0"} else text
        return str(value)

    def __str__(self):
        return self.asStr

    def __repr__(self):
        return f"{type(self)}<{self.asStr}>"

    def __hash__(self):
        if self.unit in self._years_and_months:
            value_in_months = self.value
            if self.unit in ["'a'", "year", "years"]:
                value_in_months *= 12
            return hash(("months", value_in_months))
        elif self.unit in self._weeks_days_and_time:
            value_in_seconds = self.value * self.datetime_multipliers[self.unit]
            return hash(("seconds", value_in_seconds))
        else:
            return hash((self.value, self.unit))

    def __eq__(self, other):
        if isinstance(other, FP_Quantity):
            # Fast path: same unit → direct value comparison
            if self.unit == other.unit:
                return self.value == other.value
            if self.unit in self._years_and_months and other.unit in self._years_and_months:
                mixed_calendar_ucum = (
                    self.unit in self._calendar_duration_units
                    and other.unit in self._ucum_duration_units
                ) or (
                    self.unit in self._ucum_duration_units
                    and other.unit in self._calendar_duration_units
                )
                # FP-01 HISTORIAN QA-001 (2026-08-16): mixed calendar-vs-UCUM
                # year/month pairs stay indeterminate — the OFFICIAL R4
                # fixtures pin `'1 'a''.toQuantity() = 1 year` to EMPTY
                # (testStringQuantityYearLiteralToQuantity has no <output>),
                # outranking the N1/master §6.1.1 prose that says false.
                if mixed_calendar_ucum:
                    return None
                return self._compare_years_and_months(other, year_units=["'a'", "year", "years"])
            elif self.unit in self._weeks_days_and_time and other.unit in self._weeks_days_and_time:
                self_value_in_seconds = self.value * self.datetime_multipliers[self.unit]
                other_value_in_seconds = other.value * self.datetime_multipliers[other.unit]
                return self_value_in_seconds == other_value_in_seconds
            else:
                # FP-01 SKEPTIC QA-003 (2026-08-16): cross-group time-valued
                # durations (calendar year/month vs weeks/days/time) compare
                # with the §5.5.7 unanchored factors. Mixed calendar-vs-UCUM
                # year/month pairs stay indeterminate (§6.1.1; pinned EMPTY
                # by the official R4 toQuantity fixtures, FP-01 HISTORIAN
                # QA-001 2026-08-16), and UCUM-only pairs (e.g. 'mo' vs
                # 'd') compare through UCUM seconds.
                self_ym = self.unit in self._years_and_months
                other_ym = other.unit in self._years_and_months
                if self_ym != other_ym:
                    mixed_year_month_ucum = (
                        self.unit in self._calendar_duration_units
                        and other.unit in self._year_month_ucum_units
                    ) or (
                        self.unit in self._year_month_ucum_units
                        and other.unit in self._calendar_duration_units
                    )
                    if mixed_year_month_ucum:
                        return None
                    self_seconds = self._unanchored_duration_seconds(self.unit, self.value)
                    other_seconds = self._unanchored_duration_seconds(other.unit, other.value)
                    if (
                        self_seconds is not None
                        and other_seconds is not None
                        and self_seconds[1] == other_seconds[1]
                    ):
                        return self_seconds[0] == other_seconds[0]
                    return None
                # FHIRPath §6.1: incompatible units → empty (None)
                converted = FP_Quantity.conv_unit_to(self.unit, self.value, other.unit)
                if converted is not None:
                    return other.value == converted.value and other.unit == converted.unit
                return None
        else:
            return super().__eq__(other)

    @staticmethod
    def _strip_unit_quotes(unit):
        """Strip surrounding single quotes from UCUM unit strings."""
        if unit.startswith("'") and unit.endswith("'"):
            return unit[1:-1]
        return unit

    @staticmethod
    def _normalize_quantity_value(value):
        if isinstance(value, Decimal):
            if value == value.to_integral_value():
                return value.quantize(Decimal("1"))
            return value.normalize()
        return value

    @staticmethod
    def _divide_and_render(numerator, denominator):
        """FP-08 HISTORIAN QA-001 (2026-08-17): §5.5.7 conversion division
        mirroring the native exact long-division rendering: when the
        quotient terminates exactly, trailing scale zeros are trimmed
        (180 cm / 100 -> "1.8", not "1.80"); a non-terminating quotient
        keeps the 28-significant-digit ROUND_HALF_EVEN result verbatim
        (trailing zero from rounding is significant)."""
        quotient = numerator / denominator
        from fractions import Fraction

        exact = Fraction(numerator) / Fraction(denominator)
        den = exact.denominator
        for prime in (2, 5):
            while den % prime == 0:
                den //= prime
        if den == 1:
            return FP_Quantity._normalize_quantity_value(quotient)
        return quotient

    @staticmethod
    def conv_unit_to_base(unit, value):
        clean_unit = FP_Quantity._strip_unit_quotes(unit)
        conversion = FP_Quantity._ucum_base_conversion_factor.get(unit)
        if conversion is None:
            conversion = FP_Quantity._ucum_base_conversion_factor.get(clean_unit)
        if conversion is None:
            # FP-02 SKEPTIC QA-003 (2026-08-16): multi-term UCUM expressions
            # ('m2/m', 'm.m2', 'g.m/s2', exponent-suffixed single terms such
            # as 'm3') convert term-by-term through the UCUM table with
            # exponent merging, per §6.6.1 `3 'cm' * 12 'cm2' // 36 'cm3'`
            # and §6.6.2 `12 'cm2' / 3 'cm' // 4.0 'cm'` — UCUM semantics
            # reduce identical base symbols (m2/m -> m). Unparseable or
            # partially-unknown units stay unconvertible (returned as-is).
            terms = FP_Quantity._parse_unit_exponents(clean_unit)
            if terms is not None:
                merged: dict[str, int] = {}
                converted_value = Decimal(str(value))
                for symbol, exponent in terms.items():
                    term_conversion = FP_Quantity._ucum_base_conversion_factor.get(symbol)
                    if term_conversion is None:
                        return FP_Quantity(value, unit)
                    base_symbol = FP_Quantity._strip_unit_quotes(term_conversion[0])
                    factor = term_conversion[1]
                    # FP-02 HISTORIAN QA-004 (2026-08-16): derived-unit
                    # bases are themselves term expressions ('J' ->
                    # 'g.m2/s2'); expand them so multi-term operands
                    # ('kg.m2/s2', 'N.m') merge on true base symbols and
                    # land on the same canonical string as the direct
                    # entry. Single-symbol bases parse to themselves, so
                    # this is behavior-preserving for the existing table.
                    sub_terms = FP_Quantity._parse_unit_exponents(base_symbol)
                    if sub_terms is not None:
                        for sub_symbol, sub_exponent in sub_terms.items():
                            merged[sub_symbol] = (
                                merged.get(sub_symbol, 0) + exponent * sub_exponent
                            )
                    else:
                        merged[base_symbol] = merged.get(base_symbol, 0) + exponent
                    if factor != Decimal(1):
                        converted_value *= factor**exponent
                if not any(merged.values()):
                    merged = {}
                return FP_Quantity(
                    FP_Quantity._normalize_quantity_value(converted_value),
                    FP_Quantity._render_unit_exponents(merged),
                )
            return FP_Quantity(value, unit)

        base_unit, factor = conversion
        converted_value = Decimal(str(value)) * factor
        return FP_Quantity(FP_Quantity._normalize_quantity_value(converted_value), base_unit)

    @staticmethod
    def _parse_unit_exponents(unit):
        """Parse a bare UCUM term expression into {base symbol: exponent}.

        Supports the forms produced by quantity arithmetic and accepted from
        users: '.'-separated numerator terms, '/'-separated denominator terms
        (each '/' segment after the first contributes negative exponents),
        optional integer exponents per term (m2, s-1), and the dimensionless
        '1'. Returns None when the string is not a pure term expression
        (empty, whitespace, or a term with no symbol/exponent split).
        """
        clean = FP_Quantity._strip_unit_quotes(unit)
        if not clean or any(ch.isspace() for ch in clean):
            return None
        exponents: dict[str, int] = {}
        for index, segment in enumerate(clean.split("/")):
            sign = 1 if index == 0 else -1
            if not segment:
                return None
            for term in segment.split("."):
                if not term:
                    return None
                if term == "1":
                    # Dimensionless term: '1', or the numerator of '1/s'.
                    continue
                match = re.fullmatch(r"(.*?)(-?\d+)?", term)
                if not match or not match.group(1):
                    return None
                symbol = match.group(1)
                exponent = int(match.group(2)) if match.group(2) is not None else 1
                exponents[symbol] = exponents.get(symbol, 0) + sign * exponent
        return {s: e for s, e in exponents.items() if e != 0}

    @staticmethod
    def _render_unit_exponents(exponents):
        """Render {base symbol: exponent} back to a quoted UCUM unit string.

        Symbols render in sorted order so both engines (and repeated
        operations) produce one canonical spelling; zero exponents are
        dropped; a fully-cancelled map renders as the dimensionless "'1'".
        """
        pruned = {s: e for s, e in exponents.items() if e != 0}
        if not pruned:
            return "'1'"
        numerator = ".".join(
            symbol + (str(exp) if exp != 1 else "") for symbol, exp in sorted(pruned.items()) if exp > 0
        )
        denominator = ".".join(
            symbol + (str(-exp) if -exp != 1 else "") for symbol, exp in sorted(pruned.items()) if exp < 0
        )
        if numerator and denominator:
            return f"'{numerator}/{denominator}'"
        if denominator:
            return f"'1/{denominator}'"
        return f"'{numerator}'"

    def __mul__(self, other):
        """Multiply quantity by a number or another quantity."""
        if isinstance(other, (int, float, Decimal)):
            return FP_Quantity(self.value * other, self.unit)
        if isinstance(other, FP_Quantity):
            # FP-02 HISTORIAN QA-002 (2026-08-16): N1 §6.6.1 composes in
            # OPERAND unit space — `12 'cm' * 3 'cm' // 36 'cm2'`,
            # `3 'cm' * 12 'cm2' // 36 'cm3'` — merging the operand units'
            # term exponents directly and multiplying the operand values.
            # Comparisons still reduce through the base table, so official
            # fixture testQuantity9 (`2.0 'cm' * 2.0 'm' = 0.040 'm2'` ->
            # true) keeps holding via 'cm.m' -> m2 reduction.
            bare_self = FP_Quantity._strip_unit_quotes(self.unit)
            bare_other = FP_Quantity._strip_unit_quotes(other.unit)
            self_terms = FP_Quantity._parse_unit_exponents(bare_self)
            other_terms = FP_Quantity._parse_unit_exponents(bare_other)
            if self_terms is not None and other_terms is not None:
                new_value = FP_Quantity._normalize_quantity_value(self.value * other.value)
                merged = dict(self_terms)
                for symbol, exponent in other_terms.items():
                    merged[symbol] = merged.get(symbol, 0) + exponent
                return FP_Quantity(new_value, FP_Quantity._render_unit_exponents(merged))
            self_base = FP_Quantity.conv_unit_to_base(self.unit, self.value)
            other_base = FP_Quantity.conv_unit_to_base(other.unit, other.value)
            new_value = FP_Quantity._normalize_quantity_value(self_base.value * other_base.value)
            bare_self = FP_Quantity._strip_unit_quotes(self_base.unit)
            bare_other = FP_Quantity._strip_unit_quotes(other_base.unit)
            # FP-02 SKEPTIC QA-003 (2026-08-16): unparseable units keep the
            # base-symbol exponent merge (m.m2 -> m3) instead of string
            # concatenation, and the dimensionless '1' instead of '12'.
            self_terms = FP_Quantity._parse_unit_exponents(bare_self)
            other_terms = FP_Quantity._parse_unit_exponents(bare_other)
            if self_terms is not None and other_terms is not None:
                merged = dict(self_terms)
                for symbol, exponent in other_terms.items():
                    merged[symbol] = merged.get(symbol, 0) + exponent
                return FP_Quantity(new_value, FP_Quantity._render_unit_exponents(merged))
            if self_base.unit == other_base.unit:
                return FP_Quantity(new_value, f"'{bare_self}2'")
            return FP_Quantity(new_value, f"'{bare_self}.{bare_other}'")
        return NotImplemented

    def __rmul__(self, other):
        """Right multiplication (number * quantity)."""
        if isinstance(other, (int, float, Decimal)):
            return FP_Quantity(self.value * other, self.unit)
        return NotImplemented

    def __truediv__(self, other):
        """Divide quantity by a number or another quantity."""
        if isinstance(other, (int, float, Decimal)):
            if other == 0:
                return []
            # FP-18 HISTORIAN QA-003 (2026-06-30): Per §6.6.2 "The result
            # of a division is always Decimal, even if the inputs are both
            # Integer". Wrap result to ensure Decimal form with at least
            # one decimal place for whole-number results.
            result_value = self.value / other
            if isinstance(result_value, Decimal) and result_value == result_value.to_integral_value():
                result_value = result_value.quantize(Decimal("0.1"))
            return FP_Quantity(result_value, self.unit)
        if isinstance(other, FP_Quantity):
            if other.value == 0:
                return []
            # FP-02 HISTORIAN QA-002 (2026-08-16): N1 §6.6.2 composes in
            # OPERAND unit space — `12 'cm2' / 3 'cm' // 4.0 'cm'` —
            # merging the operand units' term exponents and dividing the
            # operand values. Comparisons still reduce through the base
            # table ('m2/m' spellings and products stay commensurable).
            bare_self = FP_Quantity._strip_unit_quotes(self.unit)
            bare_other = FP_Quantity._strip_unit_quotes(other.unit)
            self_terms = FP_Quantity._parse_unit_exponents(bare_self)
            other_terms = FP_Quantity._parse_unit_exponents(bare_other)
            if self_terms is not None and other_terms is not None:
                new_value = self.value / other.value
                # FP-18 HISTORIAN QA-003 (2026-06-30): force Decimal form
                # for whole-number results per §6.6.2 "the result of a
                # division is always Decimal".
                if isinstance(new_value, Decimal) and new_value == new_value.to_integral_value():
                    new_value = new_value.quantize(Decimal("0.1"))
                merged = dict(self_terms)
                for symbol, exponent in other_terms.items():
                    merged[symbol] = merged.get(symbol, 0) - exponent
                return FP_Quantity(new_value, FP_Quantity._render_unit_exponents(merged))
            self_base = FP_Quantity.conv_unit_to_base(self.unit, self.value)
            other_base = FP_Quantity.conv_unit_to_base(other.unit, other.value)
            if other_base.value == 0:
                return []
            new_value = FP_Quantity._normalize_quantity_value(self_base.value / other_base.value)
            # FP-18 HISTORIAN QA-003 (2026-06-30): Force Decimal form for
            # whole-number results per §6.6.2.
            if isinstance(new_value, Decimal) and new_value == new_value.to_integral_value():
                new_value = new_value.quantize(Decimal("0.1"))
            if self_base.unit == other_base.unit:
                return FP_Quantity(new_value, "'1'")
            bare_self = FP_Quantity._strip_unit_quotes(self_base.unit)
            bare_other = FP_Quantity._strip_unit_quotes(other_base.unit)
            # FP-02 SKEPTIC QA-003 (2026-08-16): unparseable units divide by
            # merging base-symbol exponents so m2/m reduces to m and the
            # result stays comparable/convertible.
            self_terms = FP_Quantity._parse_unit_exponents(bare_self)
            other_terms = FP_Quantity._parse_unit_exponents(bare_other)
            if self_terms is not None and other_terms is not None:
                merged = dict(self_terms)
                for symbol, exponent in other_terms.items():
                    merged[symbol] = merged.get(symbol, 0) - exponent
                return FP_Quantity(new_value, FP_Quantity._render_unit_exponents(merged))
            return FP_Quantity(new_value, f"'{bare_self}/{bare_other}'")
        return NotImplemented

    def __rtruediv__(self, other):
        """Right division (number / quantity)."""
        if isinstance(other, (int, float, Decimal)):
            if self.value == 0:
                return []
            bare_unit = FP_Quantity._strip_unit_quotes(self.unit)
            # FP-18 HISTORIAN QA-003 (2026-06-30): Per §6.6.2 division result
            # is always Decimal. Force Decimal form for whole-number results.
            result_value = other / self.value
            if isinstance(result_value, Decimal) and result_value == result_value.to_integral_value():
                result_value = result_value.quantize(Decimal("0.1"))
            # FP-02 SKEPTIC QA-003 (2026-08-16): merge exponents so
            # `1 / 4 's'` -> '1/s' and multi-term dividends reduce
            # (`1 / (10 'g' / 2 's')` -> 's/g') rather than double-nesting.
            self_terms = FP_Quantity._parse_unit_exponents(bare_unit)
            if self_terms is not None:
                merged = {symbol: -exponent for symbol, exponent in self_terms.items()}
                return FP_Quantity(result_value, FP_Quantity._render_unit_exponents(merged))
            return FP_Quantity(result_value, f"'1/{bare_unit}'")
        return NotImplemented

    def deep_equal(self, other):
        if isinstance(other, FP_Quantity):
            if self.unit in self._years_and_months and other.unit in self._years_and_months:
                return self._compare_years_and_months(other, year_units=["'a'", "year", "years"])
            else:
                if self.unit != other.unit:
                    converted = FP_Quantity.conv_unit_to(self.unit, self.value, other.unit)
                    if converted is not None:
                        reverse_converted = FP_Quantity.conv_unit_to(
                            converted.unit, converted.value, self.unit
                        )
                        if reverse_converted is not None:
                            return (
                                self.value == reverse_converted.value
                                and self.unit == reverse_converted.unit
                            )
                    # FP-01 SKEPTIC QA-003 (2026-08-16): fall back to §5.5.7
                    # unanchored calendar factors for cross-group time-valued
                    # durations (e.g. `1 month` vs `30 day`), mirroring the
                    # `=` operator's equality() path so membership/distinct
                    # stay consistent with the spec conversion factors.
                    mixed_year_month_ucum = (
                        self.unit in self._calendar_duration_units
                        and other.unit in self._year_month_ucum_units
                    ) or (
                        self.unit in self._year_month_ucum_units
                        and other.unit in self._calendar_duration_units
                    )
                    if not mixed_year_month_ucum:
                        self_seconds = self._unanchored_duration_seconds(self.unit, self.value)
                        other_seconds = self._unanchored_duration_seconds(other.unit, other.value)
                        if (
                            self_seconds is not None
                            and other_seconds is not None
                            and self_seconds[1] == other_seconds[1]
                        ):
                            return self_seconds[0] == other_seconds[0]
                    return False
                return self.__eq__(other)
        else:
            return super().__eq__(other)

    def conv_unit_to(fromUnit, value, toUnit):
        from_year_month_magnitude = FP_Quantity._year_month_conversion_factor.get(fromUnit)
        to_year_month_magnitude = FP_Quantity._year_month_conversion_factor.get(toUnit)
        if from_year_month_magnitude and to_year_month_magnitude:
            return FP_Quantity(from_year_month_magnitude * value / to_year_month_magnitude, toUnit)

        elif (
            fromUnit in FP_Quantity._weeks_days_and_time
            and toUnit in FP_Quantity._weeks_days_and_time
        ):
            value_in_seconds = value * FP_Quantity.datetime_multipliers.get(fromUnit)
            new_value = FP_Quantity._divide_and_render(
                value_in_seconds, FP_Quantity.datetime_multipliers.get(toUnit)
            )
            return FP_Quantity(new_value, toUnit)

        from_m_cm_mm_magnitude = FP_Quantity._m_cm_mm_conversion_factor.get(fromUnit)
        to_m_cm_mm_magnitude = FP_Quantity._m_cm_mm_conversion_factor.get(toUnit)
        if from_m_cm_mm_magnitude and to_m_cm_mm_magnitude:
            return FP_Quantity(
                FP_Quantity._divide_and_render(
                    from_m_cm_mm_magnitude * value, to_m_cm_mm_magnitude
                ),
                toUnit,
            )

        from_lbs_kg_magnitude = FP_Quantity._lbs_kg_conversion_factor.get(fromUnit)
        to_lbs_kg_magnitude = FP_Quantity._lbs_kg_conversion_factor.get(toUnit)
        if from_lbs_kg_magnitude and to_lbs_kg_magnitude:
            converted_value = (from_lbs_kg_magnitude * value) / to_lbs_kg_magnitude
            rounded_value = converted_value.quantize(Decimal("1."), rounding=ROUND_UP)
            return FP_Quantity(rounded_value, toUnit)

        from_g_mg_magnitude = FP_Quantity._g_mg_conversion_factor.get(fromUnit)
        to_g_mg_magnitude = FP_Quantity._g_mg_conversion_factor.get(toUnit)
        if from_g_mg_magnitude and to_g_mg_magnitude:
            result = FP_Quantity._normalize_quantity_value(
                from_g_mg_magnitude * Decimal(str(value)) / to_g_mg_magnitude
            )
            return FP_Quantity(result, toUnit)

        # FP-02 SKEPTIC QA-003 (2026-08-16): multi-term or exponent-merged
        # UCUM units ('m2/m', 'm3', 'g.m/s2') convert through base
        # reduction when no direct group applies, so ordering (§6.2),
        # equivalence (§6.1.2), and arithmetic comparisons accept the
        # reduced spellings the §6.6.1/§6.6.2 examples produce.
        if FP_Quantity._unit_reduces_to_base(fromUnit):
            from_base = FP_Quantity.conv_unit_to_base(fromUnit, value)
            to_direct = toUnit in FP_Quantity._ucum_base_conversion_factor or (
                FP_Quantity._strip_unit_quotes(toUnit)
                in FP_Quantity._ucum_base_conversion_factor
            )
            if to_direct or FP_Quantity._unit_reduces_to_base(toUnit):
                to_base = FP_Quantity.conv_unit_to_base(toUnit, Decimal(1))
                if to_base.unit == from_base.unit and to_base.value != 0:
                    return FP_Quantity(
                        FP_Quantity._normalize_quantity_value(
                            Decimal(str(from_base.value)) / Decimal(str(to_base.value))
                        ),
                        toUnit,
                    )

        # FP-08 EXPLORER QA-001 (2026-08-17): direct-table-key units must
        # also bridge through base reduction. `_unit_reduces_to_base()`
        # deliberately returns False for direct keys, so derived-unit
        # families ('J'->'kJ', 'N'->'kN', 'W'->'kW') and exponent-suffixed
        # area/volume keys ('m2'->'cm2') plus direct<->expression pairs
        # ('kJ'->'kg.m2/s2') fell through to None here while the native
        # evaluator converts them and §6.1.1 equality already accepts them
        # via conv_unit_to_base. The time domain (base unit "'s'") is
        # excluded so the duration doctrines above stay intact: calendar
        # year/month vs UCUM 'a'/'mo' pairs and `1 year -> 's'` remain
        # unconvertible (§5.5.7 category table, §6.1.1 fixture pins), and
        # the week/day/time groups are handled by the earlier branches.
        if FP_Quantity._strip_unit_quotes(fromUnit) in FP_Quantity._ucum_base_conversion_factor:
            to_is_convertible = (
                FP_Quantity._strip_unit_quotes(toUnit)
                in FP_Quantity._ucum_base_conversion_factor
            ) or FP_Quantity._unit_reduces_to_base(toUnit)
            if to_is_convertible:
                from_base = FP_Quantity.conv_unit_to_base(fromUnit, value)
                to_base = FP_Quantity.conv_unit_to_base(toUnit, Decimal(1))
                if (
                    to_base.unit == from_base.unit
                    and from_base.unit != "'s'"
                    and to_base.value != 0
                ):
                    return FP_Quantity(
                        FP_Quantity._divide_and_render(
                            Decimal(str(from_base.value)),
                            Decimal(str(to_base.value)),
                        ),
                        toUnit,
                    )
        return None

    # FP-08 SKEPTIC QA-001/QA-002 (2026-08-17): §5.5.7 toQuantity() has its
    # OWN canonical conversion-factor table ("1 year = 12 months or 365
    # days", "1 month = 30 days", "1 day = 24 hours", "1 hour = 60
    # minutes", "1 minute = 60 seconds"). The equality-oriented group
    # separation in conv_unit_to() (landed for §6.1 calendar-vs-UCUM
    # semantics: 12 x 30 days = 360 != 365 days) must NOT block
    # calendar-keyword to calendar-keyword conversion in toQuantity().
    # This table is used ONLY by to_quantity()/converts_to_quantity() and
    # never by equality/ordering/arithmetic conversion paths.
    # Each duration unit maps to (kind, num, den):
    #   kind "ym"  -> magnitude in months (year=12, month=1)
    #   kind "sec" -> magnitude in seconds (exact rationals)
    # Cross-kind conversion is allowed only when BOTH units are bare
    # calendar duration keywords (no UCUM quotes), bridging the year/month
    # side through the direct table rows (year = 365 days, month = 30
    # days) so year<->month keeps the direct factor 12 (365/30 != 12).
    _duration_spec_table = {
        "year": ("ym", 12, 1), "years": ("ym", 12, 1), "'a'": ("ym", 12, 1),
        "month": ("ym", 1, 1), "months": ("ym", 1, 1), "'mo'": ("ym", 1, 1),
        "week": ("sec", 604800, 1), "weeks": ("sec", 604800, 1), "'wk'": ("sec", 604800, 1),
        "day": ("sec", 86400, 1), "days": ("sec", 86400, 1), "'d'": ("sec", 86400, 1),
        "hour": ("sec", 3600, 1), "hours": ("sec", 3600, 1), "'h'": ("sec", 3600, 1),
        "minute": ("sec", 60, 1), "minutes": ("sec", 60, 1), "'min'": ("sec", 60, 1),
        "second": ("sec", 1, 1), "seconds": ("sec", 1, 1), "'s'": ("sec", 1, 1),
        "millisecond": ("sec", 1, 1000), "milliseconds": ("sec", 1, 1000), "'ms'": ("sec", 1, 1000),
    }
    # Direct §5.5.7 rows for bridging year/month into the seconds group.
    _ym_seconds_bridge = {
        "year": (365 * 86400, 1), "years": (365 * 86400, 1),
        "month": (30 * 86400, 1), "months": (30 * 86400, 1),
    }

    @staticmethod
    def conv_duration_to_spec(fromUnit, value, toUnit):
        """§5.5.7 toQuantity()-only duration conversion via the spec's
        canonical conversion-factor table. Returns FP_Quantity or None when
        the pair is not a duration pair or the calendar-vs-UCUM category
        doctrine (§4.1.8/§6.1) forbids the conversion."""
        table = FP_Quantity._duration_spec_table
        from_entry = table.get(fromUnit)
        to_entry = table.get(toUnit)
        if not from_entry or not to_entry:
            return None
        from_kind, from_num, from_den = from_entry
        to_kind, to_num, to_den = to_entry
        if from_kind != to_kind:
            # Cross-category (year/month vs day-and-below): allowed only
            # for bare calendar keywords on BOTH sides, per the §5.5.7
            # table rows (1 year = 365 days, 1 month = 30 days). UCUM
            # codes keep the §6.1 category rejection (1 year -> 's'
            # remains empty, pinned by
            # test_calendar_vs_ucum_duration_group_separation_fp08_explorer).
            from_bare = fromUnit in FP_Quantity._ym_seconds_bridge or (
                from_kind == "sec" and not (fromUnit.startswith("'") and fromUnit.endswith("'"))
            )
            to_bare = toUnit in FP_Quantity._ym_seconds_bridge or (
                to_kind == "sec" and not (toUnit.startswith("'") and toUnit.endswith("'"))
            )
            if not (from_bare and to_bare):
                return None
            if from_kind == "ym":
                from_num, from_den = FP_Quantity._ym_seconds_bridge[fromUnit]
            else:
                to_num, to_den = FP_Quantity._ym_seconds_bridge[toUnit]
        if not isinstance(value, Decimal):
            value = Decimal(str(value))
        # Single division => one 28-significant-digit rounding, matching
        # the pre-existing conv_unit_to() Decimal style (§4.1.4), with
        # exact-quotient trailing-zero trimming for native parity
        # (FP-08 HISTORIAN QA-001).
        numerator = value * from_num * to_den
        denominator = from_den * to_num
        return FP_Quantity(FP_Quantity._divide_and_render(numerator, denominator), toUnit)

    @staticmethod
    def _unit_reduces_to_base(unit):
        """True when the unit is a multi-term/exponent UCUM expression whose
        every symbol is convertible through the UCUM base table ('m2/m',
        'm3', 'g.m/s2'), i.e. neither a direct table key nor unconvertible.
        """
        if unit in FP_Quantity._ucum_base_conversion_factor:
            return False
        clean = FP_Quantity._strip_unit_quotes(unit)
        if clean in FP_Quantity._ucum_base_conversion_factor:
            return False
        terms = FP_Quantity._parse_unit_exponents(clean)
        if terms is None:
            return False
        return all(
            symbol in FP_Quantity._ucum_base_conversion_factor for symbol in terms
        )

    def _compare_years_and_months(self, other, year_units=None):
        year_units = year_units or ["year", "years"]
        self_value_in_months = self.value
        other_value_in_months = other.value

        if self.unit in year_units:
            self_value_in_months *= 12
        if other.unit in year_units:
            other_value_in_months *= 12
        return self_value_in_months == other_value_in_months

    def compare(self, other):
        """
        Compare this quantity to another quantity.
        Returns -1 if self < other, 0 if self == other, 1 if self > other.
        Returns None if the quantities cannot be compared (incompatible units).
        """
        if not isinstance(other, FP_Quantity):
            return None

        mixed_calendar_ucum = (
            self.unit in self._calendar_duration_units and other.unit in self._ucum_duration_units
        ) or (
            self.unit in self._ucum_duration_units and other.unit in self._calendar_duration_units
        )
        # FP-01 SKEPTIC QA-003/QA-004 (2026-08-16): comparable despite the
        # calendar/UCUM mix when a calendar year/month keyword faces a UCUM
        # week/day/time code — `30 'd'` is exactly 30 days, so §5.5.7 factors
        # still apply (`1 month > 29 'd'` // true). Only the year/month UCUM
        # analogues ('a'/'mo') stay un-comparable per §6.2 (`1 'mo' > 29
        # days` // empty, `1 year > 1 'a'` // empty).
        calendar_ym_vs_ucum_weeks_days_time = (
            self.unit in self._years_and_months
            and self.unit in self._calendar_duration_units
            and other.unit in self._weeks_days_and_time
            and other.unit in self._ucum_duration_units
        ) or (
            other.unit in self._years_and_months
            and other.unit in self._calendar_duration_units
            and self.unit in self._weeks_days_and_time
            and self.unit in self._ucum_duration_units
        )
        # FP-02 HISTORIAN QA-003 (2026-08-16): a calendar week/day/time
        # KEYWORD facing a UCUM week/day/time code is exactly convertible
        # (both sides carry exact second multipliers via
        # datetime_multipliers / the UCUM base table), so ordering is
        # decidable — `1 day > 23 'h'` // true — matching the equality
        # surface (`1 day = 24 'h'` // true). Only year/month keyword-vs-
        # 'a'/'mo' pairs stay un-comparable (§6.1.1/§6.2, fixture-pinned
        # empty by FP-01 HISTORIAN QA-001). This subsumes the previous
        # second/millisecond-only exemption.
        calendar_wdt_vs_ucum_wdt = (
            self.unit in self._weeks_days_and_time
            and other.unit in self._weeks_days_and_time
        )
        if mixed_calendar_ucum and not (
            calendar_wdt_vs_ucum_wdt or calendar_ym_vs_ucum_weeks_days_time
        ):
            return None

        # Handle years and months comparison
        if self.unit in self._years_and_months and other.unit in self._years_and_months:
            self_value_in_months = self.value
            other_value_in_months = other.value
            year_units = ["'a'", "year", "years"]
            if self.unit in year_units:
                self_value_in_months *= 12
            if other.unit in year_units:
                other_value_in_months *= 12
            if self_value_in_months < other_value_in_months:
                return -1
            elif self_value_in_months > other_value_in_months:
                return 1
            return 0

        # Handle weeks, days, and time comparison
        if self.unit in self._weeks_days_and_time and other.unit in self._weeks_days_and_time:
            self_value_in_seconds = self.value * self.datetime_multipliers[self.unit]
            other_value_in_seconds = other.value * self.datetime_multipliers[other.unit]
            if self_value_in_seconds < other_value_in_seconds:
                return -1
            elif self_value_in_seconds > other_value_in_seconds:
                return 1
            return 0

        # FP-01 SKEPTIC QA-003/QA-004 (2026-08-16): Cross-group time-valued
        # ordering such as `1 month > 29 days` uses the §5.5.7 calendar
        # conversion factors (1 month = 30 days, 1 year = 365 days) for the
        # calendar keyword operand, per §6.2 "as well as the calendar
        # durations as defined in the toQuantity function". Mixed
        # calendar-vs-UCUM year/month pairs were already rejected above.
        cross_group = (
            self.unit in self._years_and_months and other.unit in self._weeks_days_and_time
        ) or (
            self.unit in self._weeks_days_and_time and other.unit in self._years_and_months
        )
        if cross_group:
            self_seconds = self._unanchored_duration_seconds(self.unit, self.value)
            other_seconds = self._unanchored_duration_seconds(other.unit, other.value)
            if (
                self_seconds is not None
                and other_seconds is not None
                and self_seconds[1] == other_seconds[1]
            ):
                if self_seconds[0] < other_seconds[0]:
                    return -1
                if self_seconds[0] > other_seconds[0]:
                    return 1
                return 0
            return None

        # Try to convert units for comparison
        if self.unit != other.unit:
            converted = FP_Quantity.conv_unit_to(self.unit, self.value, other.unit)
            if converted is not None:
                if converted.value < other.value:
                    return -1
                elif converted.value > other.value:
                    return 1
                return 0
            # FP-02 SKEPTIC QA-004 (found in FIX, 2026-08-16): §6.2 quantity
            # ordering must use the same UCUM base-table comparability the
            # §6.1.1 equality path (`_quantity_base`) already uses — pairs
            # such as `1 'mm[Hg]' < 200 'Pa'` ordered in the native path but
            # returned empty here because conv_unit_to only knows the
            # special groups. Unknown units come back unchanged, so two
            # different unknown units still compare as None; offset
            # temperature units map to distinct bases and stay incomparable.
            self_base = FP_Quantity.conv_unit_to_base(self.unit, self.value)
            other_base = FP_Quantity.conv_unit_to_base(other.unit, other.value)
            if self_base.unit == other_base.unit:
                if self_base.value < other_base.value:
                    return -1
                if self_base.value > other_base.value:
                    return 1
                return 0
            # FHIRPath §6.1: incompatible units → cannot compare
            return None

        # Same units, direct comparison
        if self.value < other.value:
            return -1
        elif self.value > other.value:
            return 1
        return 0


class FP_TimeBase(FP_Type):
    datetime_multipliers = [
        {"key": "year", "value": (365 * 12 * 24 * 60 * 60)},
        {"key": "month", "value": (12 * 24 * 60 * 60)},
        {"key": "day", "value": (24 * 60 * 60)},
        {"key": "hour", "value": (60 * 60)},
        {"key": "minute", "value": 60},
        {"key": "second", "value": 1},
        {"key": "tz", "value": (60 * 60)},
    ]

    def _extractAsMatchList(self, matchData, matchGroupsIndices, is_date=True):
        result = []
        for matchGroupIndex in matchGroupsIndices:
            if is_date:
                group = matchData.group(matchGroupIndex["key"])
            else:
                index = matchGroupIndex["index"]
                group = matchData.group(index) if index <= matchData.lastindex else None
            result.append(group if group is not None else None)
        return result

    def _calculatePrecision(self, dt_list):
        # Count precision elements, excluding timezone (last element if it looks like a timezone)
        # Timezone can be Z, +HH:MM, or -HH:MM
        precision = 0
        for i, item in enumerate(dt_list):
            if item is None:
                continue
            # Check if this is a timezone (index 7 for DateTime, index 4 for Time)
            if i == len(dt_list) - 1 and (item == "Z" or item.startswith(("+", "-"))):
                continue  # Skip timezone in precision calculation
            precision += 1
        return precision

    def _getMatchAsList(self):
        raise NotImplementedError()

    def _getDateTimeInt(self):
        raise NotImplementedError()

    # FP-14 EXPLORER QA-001/QA-002/QA-003 (2026-08-18): §6.2 requires
    # seconds + fractional seconds to compare as a single decimal precision
    # with decimal comparison semantics (and fixtures testLessThan26/27 pin
    # that trailing-zero fractions add no precision). Python `datetime`
    # caps at microseconds and `strptime("%f")` at 6 digits, so the old
    # `_getDateTimeInt()`-based comparison truncated 7-9 digit fractions
    # and cross-compared incommensurate FP_Date/FP_DateTime numeric scales.
    # Comparisons therefore walk components and compare the raw fraction
    # digit strings decimally (a missing fraction is "0").
    def _fraction_digits(self):
        lst = self._getMatchAsList()
        # FP_Time: 5-element list, fraction at index 3
        if len(lst) == 5:
            return lst[3]
        # FP_Date / FP_DateTime: 8-element lists, fraction at index 6
        if len(lst) >= 7:
            return lst[6]
        return None

    @staticmethod
    def _compare_decimal_fractions(fa, fb):
        fa = fa or "0"
        fb = fb or "0"
        width = max(len(fa), len(fb))
        fa = fa.ljust(width, "0")
        fb = fb.ljust(width, "0")
        return (fa > fb) - (fa < fb)

    def equals(self, otherDateTime):
        """
            From the 2020 August:
            For DateTime and Time equality, the comparison is performed by
            considering each precision in order, beginning with years (or hours for
            time values), and respecting timezone offsets. If the values are the
            same, comparison proceeds to the next precision; if the values are
            different, the comparison stops and the result is false. If one input has
            a value for the precision and the other does not, the comparison stops
            and the result is empty ({ }); if neither input has a value for the
            precision, or the last precision has been reached, the comparison stops
            and the result is true.
            Note:  Per the spec above
        :return:
            2012-01 = 2012 returns empty
            2012-01 = 2011 returns false
            2012-01 ~ 2012 returns false
        """
        # Date and DateTime are different types per FHIRPath spec
        # Comparing Date with DateTime should return None (empty)
        # because they are at different "levels" - Date has no time component
        # and DateTime potentially has time components
        if type(self) != type(otherDateTime):
            # Check if one is Date and one is DateTime
            if isinstance(self, FP_Date) and isinstance(otherDateTime, FP_DateTime):
                # Date vs DateTime comparison - return None (empty)
                # This is because DateTime has potential time components that Date doesn't
                return None
            if isinstance(self, FP_DateTime) and isinstance(otherDateTime, FP_Date):
                return None
            # Different types (e.g., Date vs Time) - return False
            return False

        thisdt_list = self._getMatchAsList()
        otherdt_list = otherDateTime._getMatchAsList()

        normalized_thisdt_list = self._normalize_datetime(thisdt_list)
        normalized_otherdt_list = self._normalize_datetime(otherdt_list)

        indices_to_remove = [
            i
            for i in range(len(normalized_thisdt_list))
            if normalized_thisdt_list[i] == normalized_otherdt_list[i] == None
        ]

        for i in reversed(indices_to_remove):
            del normalized_thisdt_list[i]
            del normalized_otherdt_list[i]

        normalized_thisdt_precision = self._calculatePrecision(normalized_thisdt_list)
        normalized_otherdt_precision = self._calculatePrecision(normalized_otherdt_list)

        # Check for timezone mismatch - if one has timezone and other doesn't, return None (empty)
        tz_thisdt_list = len(thisdt_list) >= 8 and thisdt_list[7] is not None
        tz_otherdt_list = len(otherdt_list) >= 8 and otherdt_list[7] is not None
        if (tz_thisdt_list and not tz_otherdt_list) or (tz_otherdt_list and not tz_thisdt_list):
            return None

        if normalized_thisdt_precision == normalized_otherdt_precision:
            # FP-14 EXPLORER QA-001: compare components + the decimal
            # fraction exactly; `_getDateTimeInt()` truncates fractional
            # seconds at microseconds (dateutil/datetime cap).
            if normalized_thisdt_list != normalized_otherdt_list:
                return False
            return (
                self._compare_decimal_fractions(
                    self._fraction_digits(), otherDateTime._fraction_digits()
                )
                == 0
            )

        if normalized_thisdt_precision != normalized_otherdt_precision:
            min_precision = min(normalized_thisdt_precision, normalized_otherdt_precision)
            for i in range(min_precision):
                if normalized_thisdt_list[i] is None or normalized_otherdt_list[i] is None:
                    return None
                if normalized_thisdt_list[i] != normalized_otherdt_list[i]:
                    return False

            return None

    def _normalize_datetime(self, dt_list):
        def to_str(number):
            return "0" + str(number) if 0 < number < 10 else str(number)

        if len(dt_list) < 6:
            year, month, day = (None, None, None)
            hour, minute, second = (int(dt_list[i]) if dt_list[i] else None for i in range(3))
            timezone_str = dt_list[4] if len(dt_list) > 4 else None
        else:
            year, month, day = (int(dt_list[i]) if dt_list[i] else None for i in range(3))
            hour, minute, second = (int(dt_list[i]) if dt_list[i] else None for i in range(3, 6))
            timezone_str = dt_list[7] if len(dt_list) > 7 else None

        dt = datetime(year or 2023, month or 1, day or 1, hour or 0, minute or 0, second or 0)
        if timezone_str and timezone_str != "Z":
            tz_hours, tz_minutes = map(int, timezone_str[1:].split(":"))
            tz_delta = timedelta(hours=tz_hours, minutes=tz_minutes)
            dt = dt - tz_delta if timezone_str.startswith("+") else dt + tz_delta

        return [
            to_str(dt.year) if year is not None else None,
            to_str(dt.month) if month is not None else None,
            to_str(dt.day) if day is not None else None,
            to_str(dt.hour) if hour is not None else None,
            to_str(dt.minute) if minute is not None else None,
            to_str(dt.second) if second is not None else None,
        ]

    def compare(self, otherDateTime):
        # Allow Date vs DateTime comparison for inequality operations
        # Both are FP_TimeBase subclasses and can be compared by date components
        if not isinstance(otherDateTime, FP_TimeBase):
            raise TypeError

        thisDateTimeList = self._getMatchAsList()
        otherDateTimeList = otherDateTime._getMatchAsList()

        # Per FHIRPath §6.5: only normalize to UTC when both values carry a
        # timezone offset.  When one has a timezone and the other does not,
        # UTC normalization skews the date components and produces incorrect
        # definitive results where the spec requires uncertainty (empty).
        this_has_tz = len(thisDateTimeList) > 7 and thisDateTimeList[7] is not None
        other_has_tz = len(otherDateTimeList) > 7 and otherDateTimeList[7] is not None
        timezone_mismatch = this_has_tz != other_has_tz
        if timezone_mismatch:
            # Strip timezone from whichever has it so normalization is a no-op
            if this_has_tz:
                thisDateTimeList = thisDateTimeList[:7] + [None]
            if other_has_tz:
                otherDateTimeList = otherDateTimeList[:7] + [None]

        normalized_thisdt_list = self._normalize_datetime(thisDateTimeList)
        normalized_otherdt_list = self._normalize_datetime(otherDateTimeList)
        indices_to_remove = [
            i
            for i in range(len(normalized_thisdt_list))
            if normalized_thisdt_list[i] == normalized_otherdt_list[i] == None
        ]
        for i in reversed(indices_to_remove):
            del normalized_thisdt_list[i]
            del normalized_otherdt_list[i]

        normalized_thisdt_precision = self._calculatePrecision(normalized_thisdt_list)
        normalized_otherdt_precision = self._calculatePrecision(normalized_otherdt_list)

        if normalized_thisdt_precision != normalized_otherdt_precision:
            min_precision = min(normalized_thisdt_precision, normalized_otherdt_precision)
            for i in range(min_precision):
                if normalized_thisdt_list[i] is None or normalized_otherdt_list[i] is None:
                    return -1
                if normalized_thisdt_list[i] > normalized_otherdt_list[i]:
                    return 1
                if normalized_thisdt_list[i] < normalized_otherdt_list[i]:
                    return -1
            return None

        if timezone_mismatch:
            for left, right in zip(normalized_thisdt_list, normalized_otherdt_list, strict=True):
                if left is None or right is None:
                    return None
                if left < right:
                    return -1
                if left > right:
                    return 1
            return 0

        # FP-14 EXPLORER QA-001/QA-003: componentwise walk plus exact
        # decimal-fraction compare. The previous `_getDateTimeInt()` branch
        # (a) truncated sub-microsecond fractions (datetime cap) and
        # (b) mixed FP_Date multiplier-sum ints with FP_DateTime epoch
        # timestamps for equal-precision Date-vs-DateTime comparisons,
        # flipping the result (e.g. @2015-01-01 < @2016-01-01T -> false).
        for left, right in zip(normalized_thisdt_list, normalized_otherdt_list, strict=True):
            if left is None or right is None:
                return None
            if left < right:
                return -1
            if left > right:
                return 1
        return self._compare_decimal_fractions(
            self._fraction_digits(), otherDateTime._fraction_digits()
        )

    # Conversion divisors for truncating fine-grained units to coarser ones.
    # Key: (from_unit, to_unit) -> divisor
    _UNIT_DIVISORS = {
        ("day", "year"): 365,
        ("day", "month"): 30,
        ("hour", "month"): 24 * 30,
        ("hour", "day"): 24,
        ("minute", "hour"): 60,
        ("minute", "day"): 24 * 60,
        ("second", "hour"): 3600,
        ("second", "minute"): 60,
        ("second", "day"): 86400,
        ("millisecond", "second"): 1_000,
        ("millisecond", "hour"): 3_600_000,
        ("millisecond", "minute"): 60_000,
        ("millisecond", "day"): 86_400_000,
    }

    @staticmethod
    def _truncate_toward_zero(value, divisor):
        """Truncate integer division toward zero (floor for positive, ceil for negative)."""
        return math.floor(value / divisor) if value >= 0 else math.ceil(value / divisor)

    def plus(self, time_quantity):
        raw_value = Decimal(str(time_quantity.value))
        value = int(raw_value)
        time_unit = FP_Quantity._arithmetic_duration_units.get(time_quantity.unit)
        if time_unit is None:
            valid_units = ", ".join(FP_Quantity._arithmetic_duration_units.keys())
            raise ValueError(
                f"For date/time arithmetic, the unit of the quantity must be one of the following time-based units: {valid_units}"
        )
        dt_list = self._getMatchAsList()
        if isinstance(self, FP_DateTime):
            return self._plus_datetime(value, time_unit, dt_list)
        if isinstance(self, FP_Date):
            return self._plus_date(value, time_unit, dt_list)
        if isinstance(self, FP_Time):
            return self._plus_time(value, time_unit, dt_list, time_quantity)

    def _plus_datetime(self, value, time_unit, dt_list):
        precision = self._calculatePrecision(dt_list)
        date_obj = self._convertDatetimeLocal(dt_list)
        trunc = FP_TimeBase._truncate_toward_zero
        divs = FP_TimeBase._UNIT_DIVISORS

        if time_unit == "year":
            result = date_obj + relativedelta(years=value)
        elif time_unit == "month":
            result = date_obj + relativedelta(months=value)
        elif time_unit in ("day", "week"):
            if time_unit == "week":
                value *= 7
            if precision == 1:
                result = date_obj + relativedelta(years=trunc(value, divs[("day", "year")]))
            elif precision == 2:
                result = date_obj + relativedelta(months=trunc(value, divs[("day", "month")]))
            else:
                result = date_obj + relativedelta(days=value)
        elif time_unit == "hour":
            if precision == 2:
                result = date_obj + relativedelta(months=trunc(value, divs[("hour", "month")]))
            elif precision == 3:
                result = date_obj + relativedelta(days=trunc(value, divs[("hour", "day")]))
            elif precision >= 4:
                result = date_obj + timedelta(hours=value)
            else:
                result = date_obj
        elif time_unit in ("minute", "second", "millisecond"):
            target_unit_by_precision = {4: "hour", 5: "minute"}
            target = target_unit_by_precision.get(precision)
            if target is not None:
                result = date_obj + relativedelta(
                    **{target + "s": trunc(value, divs[(time_unit, target)])}
                )
            elif precision >= 6:
                if time_unit == "second":
                    result = date_obj + timedelta(seconds=value)
                elif time_unit == "millisecond":
                    result = date_obj + timedelta(milliseconds=value)
                else:
                    result = date_obj + timedelta(minutes=value)
            else:
                result = date_obj
        else:
            result = date_obj
        return self._extractDateByPrecision(result, precision, self._timezone)

    def _plus_date(self, value, time_unit, dt_list):
        precision = self._precision
        date_obj = self._convertDatetimeLocal(dt_list)
        trunc = FP_TimeBase._truncate_toward_zero
        divs = FP_TimeBase._UNIT_DIVISORS

        if time_unit == "year":
            result = date_obj + relativedelta(years=value)
        elif time_unit == "month":
            result = date_obj + relativedelta(months=value)
        elif time_unit in ("day", "week"):
            if time_unit == "week":
                value *= 7
            if precision == 1:
                result = date_obj + relativedelta(years=trunc(value, divs[("day", "year")]))
            elif precision == 2:
                result = date_obj + relativedelta(months=trunc(value, divs[("day", "month")]))
            else:
                result = date_obj + relativedelta(days=value)
        else:
            raise ValueError(
                "For date arithmetic, the unit of the quantity must be years, months, weeks, or days"
            )
        return self._extractDateByPrecision(result, precision)

    def _plus_time(self, value, time_unit, dt_list, time_quantity):
        precision = self._calculateTimePrecision(dt_list)
        date_obj = self._convertTime(dt_list)
        if time_unit not in ("hour", "minute", "second", "millisecond"):
            raise ValueError(
                "For time arithmetic, the unit of the quantity must be hours, minutes, seconds, or milliseconds"
            )

        if precision == 1:
            if time_unit == "hour":
                result = date_obj + relativedelta(hours=value)
            else:
                trunc = FP_TimeBase._truncate_toward_zero
                divs = FP_TimeBase._UNIT_DIVISORS
                result = date_obj + relativedelta(
                    hours=trunc(value, divs[(time_unit, "hour")])
                )
        elif precision == 2:
            if time_unit == "hour":
                result = date_obj + relativedelta(minutes=value * 60)
            elif time_unit == "minute":
                result = date_obj + relativedelta(minutes=value)
            else:
                trunc = FP_TimeBase._truncate_toward_zero
                divs = FP_TimeBase._UNIT_DIVISORS
                result = date_obj + relativedelta(
                    minutes=trunc(value, divs[(time_unit, "minute")])
                )
        elif precision == 3:
            if time_unit == "hour":
                result = date_obj + relativedelta(minutes=value * 60)
            elif time_unit == "minute":
                result = date_obj + relativedelta(minutes=value)
            elif time_unit == "second":
                result = date_obj + relativedelta(seconds=value)
            elif time_unit == "millisecond":
                trunc = FP_TimeBase._truncate_toward_zero
                divs = FP_TimeBase._UNIT_DIVISORS
                result = date_obj + relativedelta(
                    seconds=trunc(value, divs[(time_unit, "second")])
                )
            else:
                result = date_obj
        elif precision == 4:
            if time_unit == "hour":
                result = date_obj + relativedelta(minutes=value * 60)
            elif time_unit == "minute":
                result = date_obj + relativedelta(minutes=value)
            elif time_unit == "second":
                result = date_obj + relativedelta(seconds=value)
            elif time_unit == "millisecond":
                result = date_obj + relativedelta(microseconds=value * 1000)
            else:
                result = date_obj
        else:
            result = date_obj
        # FP-01 HISTORIAN QA-002 (2026-08-16): the arithmetic result must be
        # an FP_Time value in canonical T-less lexical form (§5.5.1 toString
        # representation table: Time renders as hh:mm:ss.fff), identical to
        # how Time literals are stored. Returning the raw "T..."-prefixed
        # string leaked the literal marker into results (`T15:04:28`) and
        # degraded the value to a plain String.
        return FP_Time(self._extractTimeByPrecision(result, precision) + (dt_list[4] or ""))

    @staticmethod
    def check_string(cls, str_val):
        val = cls(str_val)
        return val

    @staticmethod
    def get_match_data(str_val):
        # First check for time with timezone - this should raise an error
        if re.match(timeWithTzRE, str_val):
            raise ValueError(f"Time literal cannot have a timezone: {str_val}")
        # Check for DateTime (date with 'T')
        match = re.match(dateTimeRE, str_val)
        if match:
            return FP_DateTime(str_val)
        # Check for Date (date without 'T')
        match = re.match(dateRE, str_val)
        if match:
            return FP_Date(str_val)
        # Check for Time
        match = re.match(timeRE, str_val)
        if match:
            return FP_Time(str_val)
        return None


class FP_Date(FP_TimeBase):
    """
    FP_Date represents a FHIRPath Date literal (e.g., @2015, @2015-02, @2015-02-04).
    Unlike DateTime, Date does not include time components.
    """
    matchGroupsIndices = [
        {"key": "year", "index": 0},
        {"key": "month", "index": 4},
        {"key": "day", "index": 6},
    ]

    def __new__(cls, dateStr):
        if not isinstance(dateStr, str):
            return None

        m = re.match(dateRE, dateStr)
        if not m:
            return None

        # Validate semantic ranges (FHIRPath §2.3: date must be valid)
        year_int = int(m.group("year"))
        if not (1 <= year_int <= 9999):
            return None
        month = m.group("month")
        day = m.group("day")
        if month is not None and not (1 <= int(month) <= 12):
            return None
        if day is not None:
            month_int = int(month) if month else 1
            max_day = calendar.monthrange(year_int, month_int)[1]
            if not (1 <= int(day) <= max_day):
                return None

        return super(FP_Date, cls).__new__(cls)

    def __init__(self, dateStr):
        self.asStr = dateStr if isinstance(dateStr, str) else None
        self._dateMatchData = (
            re.match(dateRE, self.asStr) if isinstance(self.asStr, str) else None
        )
        self._dateMatchStr = None
        self._dateAsList = []
        self._precision = 0

        if self._dateMatchData:
            self._dateMatchStr = self._dateMatchData.group(0)
            self._dateAsList = [
                self._dateMatchData.group("year"),
                self._dateMatchData.group("month"),
                self._dateMatchData.group("day"),
                None,  # hour
                None,  # minute
                None,  # second
                None,  # millisecond
                None,  # timezone
            ]
            self._precision = sum(1 for i in self._dateAsList[:3] if i is not None)

    def __str__(self):
        return self.asStr

    def __eq__(self, other):
        if isinstance(other, str):
            return self.getDateMatchStr() == other
        return super().__eq__(other)

    def __deepcopy__(self, memo):
        return type(self)(copy.deepcopy(self.asStr, memo))

    def getDateMatchStr(self):
        return self._dateMatchStr

    def _getMatchAsList(self):
        return self._dateAsList

    def _getDateTimeInt(self):
        """
        Return date converted to an integer for comparison.
        """
        if not self._dateMatchData:
            return None

        integer_result = 0
        for i, prec in enumerate(range(self._precision)):
            integer_result += int(self._dateAsList[prec]) * self.datetime_multipliers[prec]["value"]

        return integer_result

    def _convertDatetimeLocal(self, date_list):
        """
        Convert date_list to a datetime object.
        """
        year = date_list[0] if date_list[0] is not None else "0"
        month = date_list[1] if date_list[1] is not None else "01"
        day = date_list[2] if date_list[2] is not None else "01"
        date_string = f"{year}-{month}-{day}"
        return datetime.strptime(date_string, "%Y-%m-%d")

    def _extractDateByPrecision(self, date_obj, precision):
        """
        Format a datetime object at the given precision for Date type (no time component).
        Precision: 1=year, 2=month, 3=day
        """
        formats = {1: "%Y", 2: "%Y-%m", 3: "%Y-%m-%d"}
        return date_obj.strftime(formats.get(precision, "%Y-%m-%d"))


class FP_Time(FP_TimeBase):
    matchGroupsIndices = [
        {"key": "hour", "index": 1},
        {"key": "minute", "index": 2},
        {"key": "second", "index": 3},
        {"key": "millisecond", "index": 4},
        {"key": "timezone", "index": 5},
    ]

    def __new__(cls, dateStr):
        if not isinstance(dateStr, str):
            return None

        m = re.match(timeRE, dateStr)
        if not m:
            return None
        hour, minute, second = m.group(1), m.group(2), m.group(3)
        fraction = m.group(4)
        if hour is not None and not (0 <= int(hour) <= 23):
            return None
        if minute is not None and not (0 <= int(minute) <= 59):
            return None
        if second is not None and not (0 <= int(second) <= 59):
            return None
        # FHIRPath §5.5.9 format `hh:mm:ss.fff` — a fraction (millisecond)
        # component is permitted only when preceded by hour, minute, AND
        # second. `'10.30'` must be rejected entirely; it must not partially
        # parse as HH=`10` with fraction=`30`. Native C++ enforces this
        # strictly; the Python fallback must match.
        if fraction is not None and (minute is None or second is None):
            return None

        return super(FP_Time, cls).__new__(cls)

    def __init__(self, timeStr):
        self.asStr = timeStr if isinstance(timeStr, str) else None
        self._timeMatchData = re.match(timeRE, self.asStr)
        self._timeMatchStr = None
        self._timeAsList = []
        self._precision = 0
        self._pyTimeObject = None

        if self._timeMatchData:
            self._timeMatchStr = self._timeMatchData.group(0)
            self._timeAsList = self._extractAsMatchList(
                self._timeMatchData, self.matchGroupsIndices, is_date=False
            )
            self._precision = self._calculatePrecision(self._timeAsList)
            formats = [
                "T%H:%M:%S%z",
                "T%H:%M:%S.%f%z",
                "T%H:%M:%S",
                "T%H:%M:%S.%f",
                "T%H:%M%z",
                # FP-08 SKEPTIC QA-003 (2026-08-17): non-timezone T-prefixed
                # partial forms must parse too; without "T%H:%M"/"T%H" the
                # strptime loop never sets _pyTimeObject for 'T14:34'/'T14',
                # so FP_TimeBase.equals() compares _getDateTimeInt() None vs
                # int and `'T14:34'.toTime() = @T14:34` wrongly returns false
                # while native returns true.
                "T%H:%M",
                "T%H",
                "%H:%M:%S%z",
                "%H:%M:%S.%f%z",
                "%H:%M:%S",
                "%H:%M:%S.%f",
                "%H:%M%z",
                "%H:%M",
                "%H%z",
                "%H",
            ]

            for fmt in formats:
                try:
                    parsed_datetime = datetime.strptime(self.asStr, fmt)
                    if parsed_datetime.tzinfo:
                        parsed_datetime = parsed_datetime.astimezone(timezone.utc)
                    self._pyTimeObject = parsed_datetime.time()
                    break
                except ValueError:
                    continue

            # FP-14 EXPLORER QA-002 (2026-08-18): strptime("%f") accepts at
            # most 6 fractional digits, so §4.1.7 Time literals with 7-9
            # digit fractions left `_pyTimeObject` None and every ordering
            # errored to empty. Build the time object manually (fraction
            # truncated to microseconds is fine here: ordering uses the
            # exact digit strings via `_compare_decimal_fractions`; this
            # object backs display/arithmetic only).
            if self._pyTimeObject is None and self._timeMatchData.group(1) is not None:
                _h = self._timeMatchData.group(1)
                _mi = self._timeMatchData.group(2)
                _s = self._timeMatchData.group(3)
                _frac = self._timeMatchData.group(4)
                try:
                    self._pyTimeObject = datetime(
                        2000,
                        1,
                        1,
                        int(_h),
                        int(_mi or 0),
                        int(_s or 0),
                        int((_frac + "000000")[:6]) if _frac else 0,
                    ).time()
                except ValueError:
                    pass

    def __str__(self):
        if self._timeMatchData:
            hour = self._timeMatchData.group(1)
            minute = self._timeMatchData.group(2)
            second = self._timeMatchData.group(3)
            fraction = self._timeMatchData.group(4)
            if second is not None:
                value = f"{hour}:{minute}:{second}"
                if fraction is not None:
                    value += f".{fraction}"
                return value
            if minute is not None:
                return f"{hour}:{minute}"
            return hour
        return self.asStr

    def __eq__(self, other):
        if isinstance(other, str):
            return self.getTimeMatchStr() == other
        return super().__eq__(other)

    def getTimeMatchStr(self):
        return self._timeMatchStr

    def _getMatchAsList(self):
        return self._timeAsList

    def _getDateTimeInt(self):
        """
        :return: If self.timeMatchData returns DateTime object converted to seconds int, else returns None
        """
        if self._pyTimeObject:
            return timedelta(
                hours=self._pyTimeObject.hour,
                minutes=self._pyTimeObject.minute,
                seconds=self._pyTimeObject.second,
                microseconds=self._pyTimeObject.microsecond,
            ).total_seconds()
        return None

    def _extractTimeByPrecision(self, date_obj, precision):
        # FP-01 HISTORIAN QA-002 (2026-08-16): canonical Time lexical form is
        # T-less (§5.5.1 toString table: Time -> hh:mm:ss.fff). The leading
        # "T" belongs only to the @T literal syntax, not to values.
        format = {1: "%H", 2: "%H:%M", 3: "%H:%M:%S", 4: "%H:%M:%S.%f"}
        if precision == 4:
            return date_obj.strftime("%H:%M:%S.") + date_obj.strftime("%f")[:3]
        return date_obj.strftime(format.get(precision)) if precision in format else None

    def _calculateTimePrecision(self, dt_list):
        return sum(1 for i in dt_list[0:4] if i is not None)

    def _convertTime(self, time_list):
        hour = time_list[0] if time_list[0] is not None else 00
        minute = time_list[1] if time_list[1] is not None else 00
        second = time_list[2] if time_list[2] is not None else 00
        millisecond = time_list[3] if time_list[3] is not None else 000
        return datetime.strptime(f"{hour}:{minute}:{second}.{millisecond}", "%H:%M:%S.%f")


class FP_DateTime(FP_TimeBase):
    matchGroupsIndices = [
        {"key": "year", "index": 0},
        {"key": "month", "index": 4},
        {"key": "day", "index": 6},
        {"key": "hour", "index": 8},
        {"key": "minute", "index": 9},
        {"key": "second", "index": 10},
        {"key": "millisecond", "index": 11},
        {"key": "timezone", "index": 12},
    ]
    minPrecision = 3

    def __new__(cls, dateStr):
        if not isinstance(dateStr, str):
            return None

        m = re.match(dateTimeRE, dateStr)
        if not m:
            return None

        # Validate semantic ranges
        year_int = int(m.group("year"))
        if not (1 <= year_int <= 9999):
            return None
        month = m.group("month")
        day = m.group("day")
        hour = m.group("hour")
        minute = m.group("minute")
        second = m.group("second")
        timezone = m.group("timezone")
        if month is not None and not (1 <= int(month) <= 12):
            return None
        if day is not None:
            month_int = int(month) if month else 1
            max_day = calendar.monthrange(year_int, month_int)[1]
            if not (1 <= int(day) <= max_day):
                return None
        if hour is not None and not (0 <= int(hour) <= 23):
            return None
        if minute is not None and not (0 <= int(minute) <= 59):
            return None
        if second is not None and not (0 <= int(second) <= 59):
            return None
        if timezone and timezone != "Z":
            tz_body = timezone[1:]
            tz_hour, tz_minute = tz_body.split(":")
            tz_hour_int = int(tz_hour)
            tz_minute_int = int(tz_minute)
            if tz_hour_int > 14 or tz_minute_int > 59 or (tz_hour_int == 14 and tz_minute_int != 0):
                return None

        return super(FP_DateTime, cls).__new__(cls)

    def __init__(self, dateStr):
        self.asStr = dateStr if isinstance(dateStr, str) else None
        self._dateTimeMatchData = (
            re.match(dateTimeRE, self.asStr) if isinstance(self.asStr, str) else None
        )
        self._dateTimeMatchStr = None
        self._dateTimeAsList = []
        self._precision = 0
        self._timezone = None  # Store original timezone string

        if self._dateTimeMatchData:
            self._dateTimeMatchStr = self._dateTimeMatchData.group(0)
            self._dateTimeAsList = self._extractAsMatchList(
                self._dateTimeMatchData, self.matchGroupsIndices
            )
            self._precision = self._calculatePrecision(self._dateTimeAsList)
            # Extract and store original timezone from input
            self._timezone = self._dateTimeAsList[7] if len(self._dateTimeAsList) > 7 else None

    def __str__(self):
        return self.asStr

    def __eq__(self, other):
        if isinstance(other, str):
            return self.getDateTimeMatchStr() == other
        return super().__eq__(other)

    def __deepcopy__(self, memo):
        return type(self)(copy.deepcopy(self.asStr, memo))

    def getDateTimeMatchStr(self):
        return self._dateTimeMatchStr

    def _getMatchAsList(self):
        return self._dateTimeAsList

    def _getDateTimeObject(self):
        if self._dateTimeMatchData:
            if "Z" in self.asStr:
                date_str = self.asStr.replace("Z", "+00:00")
            else:
                date_str = self.asStr
            return parser.parse(date_str)
        return None

    def _getDateTimeInt(self):
        """
        :return: If self.timeMatchData returns DateTime object converted to seconds int, else returns None
        """
        if not self._dateTimeMatchData:
            return None

        if self._precision >= FP_DateTime.minPrecision:
            dateTimeObject = self._getDateTimeObject()
            return dateTimeObject.timestamp()

        integer_result = 0
        for prec in range(self._precision):
            integer_result += (
                int(self._dateTimeAsList[prec]) * self.datetime_multipliers[prec]["value"]
            )

        return integer_result

    def _extractDateByPrecision(self, date_obj: datetime, precision, timezone_str=None):
        """
        Format a datetime object at the given precision.

        Args:
            date_obj: The datetime object to format
            precision: The precision level (1=year, 2=month, 3=day, 4=hour, 5=minute, 6=second, 7=millisecond)
            timezone_str: Original timezone string to preserve (e.g., "+10:00", "Z", or None)
        """
        if date_obj.tzinfo is None or date_obj.tzinfo.utcoffset(date_obj) is None:
            date_obj = date_obj.replace(tzinfo=tz.tzutc())
        format = {
            1: "%Y",
            2: "%Y-%m",
            3: "%Y-%m-%d",
            4: "%Y-%m-%dT%H",
            5: "%Y-%m-%dT%H:%M",
            6: "%Y-%m-%dT%H:%M:%S",
            7: "%Y-%m-%dT%H:%M:%S",
        }
        formatted_date = date_obj.strftime(format.get(precision, ""))
        if precision == 7:
            milliseconds = date_obj.strftime("%f")[:3]
            formatted_date = f"{formatted_date}.{milliseconds}"
        if precision >= 4 and timezone_str:
            # Preserve the authored timezone spelling, including "Z"
            # (parity with the native evaluator, which keeps "Z" through
            # temporal arithmetic).
            formatted_date += timezone_str
        return formatted_date

    def _convertDatetime(self, date_list):
        n_date_list = self._normalize_datetime(date_list)
        year = n_date_list[0] if n_date_list[0] is not None else "0"
        month = n_date_list[1] if n_date_list[1] is not None else "01"
        day = n_date_list[2] if n_date_list[2] is not None else "01"
        hour = n_date_list[3] if n_date_list[3] is not None else "00"
        minute = n_date_list[4] if n_date_list[4] is not None else "00"
        second = n_date_list[5] if n_date_list[5] is not None else "00"
        millisecond = date_list[6] if date_list[6] is not None else "000"
        date_string = f"{year}-{month}-{day} {hour}:{minute}:{second}.{millisecond}"
        return datetime.strptime(date_string, "%Y-%m-%d %H:%M:%S.%f")

    def _convertDatetimeLocal(self, date_list):
        """
        Convert date_list to a datetime object in its original timezone (not normalized).
        This is used for arithmetic operations where we want to preserve the original timezone.
        """
        year = date_list[0] if date_list[0] is not None else "0"
        month = date_list[1] if date_list[1] is not None else "01"
        day = date_list[2] if date_list[2] is not None else "01"
        hour = date_list[3] if date_list[3] is not None else "00"
        minute = date_list[4] if date_list[4] is not None else "00"
        second = date_list[5] if date_list[5] is not None else "00"
        millisecond = date_list[6] if date_list[6] is not None else "000"
        date_string = f"{year}-{month}-{day} {hour}:{minute}:{second}.{millisecond}"
        return datetime.strptime(date_string, "%Y-%m-%d %H:%M:%S.%f")


# FHIR choice type TitleCase suffixes used to infer type from paths like
# "Observation.valueQuantity" → type "Quantity".  Ordered longest-first so
# that e.g. "CodeableConcept" matches before "Concept".
_CHOICE_TYPE_SUFFIXES = sorted([
    "DateTime", "Date", "Time", "Instant",
    "Boolean", "Integer", "Decimal", "String",
    "Quantity", "CodeableConcept", "Coding", "Code",
    "Period", "Range", "Ratio", "Reference",
    "Annotation", "Attachment", "Identifier",
    "HumanName", "Address", "ContactPoint",
    "Timing", "Signature", "Age", "Count",
    "Distance", "Duration", "Money", "SimpleQuantity",
    "SampledData", "Uri", "Url", "Canonical", "Oid", "Uuid",
    "Id", "Markdown", "Base64Binary", "UnsignedInt", "PositiveInt",
], key=len, reverse=True)


class ResourceNode:
    """
    *  Constructs a instance for the given node ("data") of a resource.  If the
    *  data is the top-level node of a resouce, the path and type parameters will
    *  be ignored in favor of the resource's resourceType field.
    * @param data the node's data or value (which might be an object with
    *  sub-nodes, an array, or FHIR data type)
    * @param path the node's path in the resource (e.g. Patient.name).  If the
    *  data's type can be determined from data, that will take precedence over
    *  this parameter.
    * @param _data additional data stored in a property named with "_" prepended.
    """

    # FP-12 EXPLORER QA-001 (2026-08-17): field-name -> complex type table
    # mirroring the native evaluator.cpp field_name inference chains used by
    # type()/is()/ofType(). LOCKSTEP RULE: keep aligned with the native
    # structuralFHIRComplexType/field-name chains in evaluator.cpp.
    _FIELD_NAME_COMPLEX_TYPES = {
        "name": "HumanName",
        "address": "Address",
        "identifier": "Identifier",
        "telecom": "ContactPoint",
        "coding": "Coding",
        "code": "CodeableConcept",
        "extension": "Extension",
        "modifierExtension": "Extension",
    }

    # Known FHIR backbone-element fields (curated from
    # models/r4/fhir_path_to_type.json; mirrors the native set in
    # structuralFHIRComplexType).
    _BACKBONE_ELEMENT_FIELDS = frozenset(
        {"communication", "component", "compose", "contact", "expansion", "item", "link"}
    )

    def __init__(self, data, path, _data=None, propName=None, index=None):
        """
        If data is a resource (maybe a contained resource) reset the path
        information to the resource type.
        """
        if isinstance(data, abc.Mapping) and "resourceType" in data:
            path = data["resourceType"]

        self.path = path
        self.data = data
        self._data = _data
        self.propName: Optional[str] = propName
        self.index: Optional[int] = index

    def __eq__(self, value):
        if isinstance(value, ResourceNode):
            return self.data == value.data
        return self.data == value

    def __hash__(self):
        data_hash = hash(json.dumps(self.data, sort_keys=True, default=str))
        path_hash = hash(self.path)
        return hash((data_hash, path_hash))

    def __repr__(self):
        data_preview = str(self.data)
        if len(data_preview) > 60:
            data_preview = data_preview[:57] + "..."
        return f"ResourceNode({self.path!r}, {data_preview})"

    def get_type_info(self):
        namespace = TypeInfo.FHIR

        if self.path is None:
            return None

        match = re.match(r"^System\.(.*)$", self.path)
        if match:
            return TypeInfo(namespace=TypeInfo.System, name=match.group(1))
        elif "." not in self.path:
            return TypeInfo(namespace=namespace, name=self.path)

        # If we have a model with path2Type, try to resolve type from it
        if TypeInfo.model and isinstance(TypeInfo.model, dict):
            path2Type = TypeInfo.model.get("path2Type", {})
            if self.path in path2Type:
                type_name = path2Type[self.path]
                if (
                    type_name == self.path
                    and (
                        TypeInfo.model.get("type2Parent", {}).get(type_name) == "BackboneElement"
                        or "." in type_name
                    )
                ):
                    type_name = "BackboneElement"
                return TypeInfo(namespace=namespace, name=type_name)

        # Try to resolve type from built-in path-to-type mapping
        # First try exact match
        if self.path in TypeInfo.FHIR_PATH_TO_TYPE:
            type_name = TypeInfo.FHIR_PATH_TO_TYPE[self.path]
            if (
                type_name == self.path
                and (
                    TypeInfo.FHIR_TYPE_HIERARCHY.get(type_name) == "BackboneElement"
                    or "." in type_name
                )
            ):
                type_name = "BackboneElement"
            return TypeInfo(namespace=namespace, name=type_name)

        # When model metadata cannot resolve a primitive element path, trust the
        # JSON value shape for numeric/boolean primitives before applying broad
        # suffix fallbacks such as ".value" -> string. This keeps Quantity.value
        # typed as decimal in the Python fallback.
        if isinstance(self.data, bool):
            return TypeInfo(namespace=namespace, name="boolean")
        if isinstance(self.data, int):
            return TypeInfo(namespace=namespace, name="integer")
        if isinstance(self.data, (float, Decimal)):
            return TypeInfo(namespace=namespace, name="decimal")

        # Try suffix match (e.g., "Patient.gender" matches ".gender")
        for suffix, type_name in TypeInfo.FHIR_PATH_TO_TYPE.items():
            if suffix.startswith(".") and self.path.endswith(suffix[1:]):
                # Make sure it's a proper field match (not a partial match)
                field_name = suffix[1:]
                if self.path.endswith("." + field_name) or self.path == field_name:
                    # Guard: if the resolved type is a primitive but the data is a
                    # complex type (dict), the suffix match is wrong (e.g., .code
                    # matching Condition.code which is CodeableConcept, not code).
                    if isinstance(self.data, abc.Mapping) and type_name[0].islower():
                        continue
                    return TypeInfo(namespace=namespace, name=type_name)

        # FHIRPath §5.2.4 ofType parity: when path metadata is absent for a
        # string field whose name is itself a FHIR primitive subtype (e.g.
        # `Patient.id` where the field name `id` is a FHIR primitive distinct
        # from `string`), resolve the type from the field name. Without this,
        # `get_type_info()` falls through to value-based inference and returns
        # `string` for any str value, which causes `ofType(id)` to miss and
        # `ofType(string)` to over-match — both violating the R4 baseline
        # (`testFHIRPathAsFunction16` analogue: primitive subtypes are NOT
        # included by ofType). Only apply this to primitive field names whose
        # type is NOT the generic `string`; otherwise the suffix/choice logic
        # above has already produced the right answer or never will.
        if "." in self.path and isinstance(self.data, str):
            last_segment = self.path.rsplit(".", 1)[1]
            if (
                last_segment in TypeInfo.VALID_FHIR_TYPES
                and last_segment != "string"
                and not last_segment[0].isupper()
            ):
                return TypeInfo(namespace=namespace, name=last_segment)

        # Detect FHIR choice type paths (e.g., "DetectedIssue.identifiedDateTime")
        # by checking if the last path segment ends with a known FHIR type suffix.
        if "." in self.path:
            last_segment = self.path.rsplit(".", 1)[1]
            for suffix in _CHOICE_TYPE_SUFFIXES:
                if last_segment.endswith(suffix) and len(last_segment) > len(suffix):
                    # Verify the prefix part is lowercase (a real choice field)
                    prefix = last_segment[:-len(suffix)]
                    if prefix and prefix[0].islower():
                        # Convert suffix to FHIR type name (lowercase first char)
                        fhir_type = suffix[0].lower() + suffix[1:]
                        return TypeInfo(namespace=namespace, name=fhir_type)

        # FP-12 EXPLORER QA-001 (2026-08-17): mirror the native engine's
        # field-name complex-type inference (evaluator.cpp structuralFHIRComplexType
        # and the type()/is()/ofType() field_name chains) for Mapping nodes whose
        # paths are absent from path metadata — e.g. recursive backbone paths
        # (Questionnaire.item.item) and choice-suffixed nested paths
        # (Observation.component.valueCodeableConcept.coding). Without this,
        # `item.item.type().name` reports 'object' and `coding.ofType(FHIR.Coding)`
        # misses while the native engine types them BackboneElement/Coding.
        if isinstance(self.data, abc.Mapping) and self.path and "." in self.path:
            field_name = self.path.rsplit(".", 1)[1]
            complex_name = self._FIELD_NAME_COMPLEX_TYPES.get(field_name)
            if complex_name is None and field_name in self._BACKBONE_ELEMENT_FIELDS:
                complex_name = "BackboneElement"
            if complex_name is not None:
                return TypeInfo(namespace=namespace, name=complex_name)

        # If we have a model but no path match, fall back to value-based inference
        # (don't just return BackboneElement)
        # Fall back to value-based type inference
        return TypeInfo.create_by_value_in_namespace(namespace=namespace, value=self.data)

    def toJSON(self):
        return json.dumps(self.data)

    @staticmethod
    def create_node(data, path=None, _data=None, propName=None, index=None):
        if isinstance(data, ResourceNode):
            return data
        return ResourceNode(data, path, _data, propName, index)

    def convert_data(self):
        data = self.data
        cls = TypeInfo.type_to_class_with_check_string.get(self.path)
        if cls:
            data = FP_TimeBase.check_string(cls, data) or data
        if isinstance(data, abc.Mapping) and data.get("system") == "http://unitsofmeasure.org":
            value = data.get("value")
            code = data.get("code") or data.get("unit")
            if value is not None and not isinstance(value, bool) and isinstance(code, str) and code:
                try:
                    value = Decimal(str(value))
                except Exception:
                    return data
                if value.is_finite():
                    data = FP_Quantity(
                        value,
                        FP_Quantity.timeUnitsToUCUM.get(code, "'" + code + "'"),
                    )
        return data


class TypeInfo:
    # DEPRECATED: ``model`` is a legacy class-level attribute that was intended as a
    # global hook for FHIR model injection.  It is always ``None`` in the current
    # codebase.  Callers should pass ``model`` explicitly to ``is_type()`` or rely
    # on the built-in ``FHIR_TYPE_HIERARCHY``.  Do NOT mutate this from concurrent
    # threads — it is not thread-safe.  Planned for removal in v2.0.
    model = None
    System = "System"
    FHIR = "FHIR"

    type_to_class_with_check_string = {
        "date": FP_Date,
        "dateTime": FP_DateTime,
        "time": FP_Time,
    }

    # Mapping from System types to equivalent FHIR primitive types
    # System types are capitalized, FHIR types are lowercase
    SYSTEM_TO_FHIR_TYPE = {
        "Boolean": "boolean",
        "Integer": "integer",
        "String": "string",
        "Decimal": "decimal",
        "DateTime": "dateTime",
        "Date": "date",
        "Time": "time",
        "Quantity": "Quantity",
        "Any": "Any",
    }

    # Mapping from FHIR primitive types to System types
    FHIR_TO_SYSTEM_TYPE = {v: k for k, v in SYSTEM_TO_FHIR_TYPE.items()}

    # Loaded from generated R4 model metadata. The legacy valid_fhir_types.json
    # is intentionally widened with the full hierarchy tables so type
    # specifier validation cannot drift from subtype matching.
    VALID_FHIR_TYPES = _VALID_FHIR_TYPES

    @staticmethod
    def get_valid_types():
        """Return the set of valid FHIR and System types."""
        return TypeInfo.VALID_FHIR_TYPES

    # Loaded from models/r4/fhir_path_to_type.json
    FHIR_PATH_TO_TYPE = _load_json("fhir_path_to_type.json")

    # Loaded from models/r4/type2Parent.json as the CANONICAL hierarchy, with
    # deliberate legacy-primitive conventions layered on top. Canonical must
    # win for primitive subtype chains: type2Parent.json carries uuid->uri /
    # oid->uri (official R4; fixture testTypeA4 pins `valueUuid is FHIR.uri`
    # // true), while the legacy fhir_type_hierarchy.json flattens uuid/oid
    # straight to string, erasing the uri ancestor and breaking qualified
    # `is`/`as` subtype checks (FP-15 SKEPTIC QA-001, 2026-08-18). The
    # remaining explicit overrides preserve documented conventions: uri is
    # string-compatible for `is FHIR.string`, and Money/Dosage/Timing keep
    # their legacy FHIRPath parents (Money is a Quantity profile; Dosage and
    # Timing are Element datatypes, not BackboneElements).
    FHIR_TYPE_HIERARCHY = {
        **_load_json("fhir_type_hierarchy.json"),
        **_load_json("type2Parent.json"),
        "uri": "string",
        "Money": "Quantity",
        "Dosage": "Element",
        "Timing": "Element",
    }

    def __init__(self, name, namespace):
        self.name = name
        self.namespace = namespace

    @staticmethod
    def is_type(type_name, super_type, model=None):
        seen = set()
        while type_name:
            if type_name in seen:
                return False
            seen.add(type_name)
            if type_name == super_type:
                return True

            # Use explicitly passed model if available, fall back to class variable
            _model = model if model is not None else TypeInfo.model
            if _model and isinstance(_model, dict):
                type_name = _model.get("type2Parent", {}).get(type_name) or _model.get(
                    "path2Type", {}
                ).get(type_name)
            else:
                # Fall back to built-in FHIR type hierarchy
                type_name = TypeInfo.FHIR_TYPE_HIERARCHY.get(type_name)

        return False

    @staticmethod
    def _normalize_type_name(namespace, name):
        """Normalize a type name for cross-namespace comparison (FHIRPath §5.8)."""
        if namespace == TypeInfo.System:
            return TypeInfo.SYSTEM_TO_FHIR_TYPE.get(name, name)
        if namespace == TypeInfo.FHIR:
            normalized = TypeInfo.FHIR_TO_SYSTEM_TYPE.get(name, name)
            return TypeInfo.SYSTEM_TO_FHIR_TYPE.get(normalized, normalized)
        return name

    def is_(self, other, model=None):
        if not isinstance(other, TypeInfo):
            return False

        self_name = TypeInfo._normalize_type_name(self.namespace, self.name)
        other_name = TypeInfo._normalize_type_name(other.namespace, other.name)

        if other_name == "Any":
            return True

        # Per FHIRPath conformance tests (testType12, testType14):
        # FHIR types and System types are distinct for is() checks.
        # FHIR.boolean is NOT System.Boolean, even though they are
        # interchangeable for operations.
        if (self.namespace and other.namespace
                and self.namespace != other.namespace):
            return False

        return TypeInfo.is_type(self_name, other_name, model=model)

    def is_exact_type(self, other, model=None):
        """Check if this type is exactly the same as other type (no subtype matching).

        Per FHIRPath conformance tests: FHIR types and System types are
        distinct — FHIR.boolean is NOT System.Boolean for as() checks.
        """
        if not isinstance(other, TypeInfo):
            return False

        self_name = TypeInfo._normalize_type_name(self.namespace, self.name)
        other_name = TypeInfo._normalize_type_name(other.namespace, other.name)

        # FHIR and System namespaces are always distinct for type identity.
        if (self.namespace and other.namespace
                and self.namespace != other.namespace):
            return False

        return self_name == other_name

    @staticmethod
    def create_by_value_in_namespace(namespace, value):
        name = type(value).__name__

        if isinstance(value, int) and not isinstance(value, bool):
            name = "integer"
        elif isinstance(value, float) or isinstance(value, Decimal):
            name = "decimal"
        elif isinstance(value, FP_Date):
            name = "date"
        elif isinstance(value, FP_DateTime):
            name = "dateTime"
        elif isinstance(value, FP_Time):
            name = "time"
        elif isinstance(value, FP_Quantity):
            name = "Quantity"
        elif isinstance(value, str):
            name = "string"
        elif isinstance(value, abc.Mapping):
            # Detect common FHIR complex types by structural properties
            if 'coding' in value:
                name = "CodeableConcept"
            elif 'system' in value and 'code' in value and 'value' not in value:
                name = "Coding"
            elif 'value' in value and ('unit' in value or 'code' in value):
                name = "Quantity"
            elif 'reference' in value:
                name = "Reference"
            elif 'contentType' in value:
                name = "Attachment"
            elif 'low' in value or 'high' in value:
                name = "Range"
            elif 'start' in value or 'end' in value:
                name = "Period"
            else:
                name = "object"

        if name == "bool":
            name = "boolean"

        if namespace == TypeInfo.System:
            if name == "dateTime":
                name = "DateTime"
            elif name == "date":
                name = "Date"
            else:
                name = name.capitalize()

        return TypeInfo(name, namespace)

    @staticmethod
    def from_value(value):
        if isinstance(value, ResourceNode):
            type_info = value.get_type_info()
            if (
                type_info
                and type_info.namespace == TypeInfo.FHIR
                and type_info.name
                and "." in type_info.name
            ):
                return TypeInfo(namespace=TypeInfo.FHIR, name="BackboneElement")
            return type_info
        # FHIR resources represented as dicts: detect via resourceType key
        if isinstance(value, abc.Mapping) and 'resourceType' in value:
            return TypeInfo(namespace=TypeInfo.FHIR, name=value['resourceType'])
        return TypeInfo.create_by_value_in_namespace(TypeInfo.System, value)
