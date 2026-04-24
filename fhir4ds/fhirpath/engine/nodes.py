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
    _year_month_conversion_factor = {"'a'": 12, "'mo'": 1}
    _m_cm_mm_conversion_factor = {"'m'": Decimal("1"), "'cm'": Decimal("0.01"), "'mm'": Decimal("0.001")}
    _lbs_kg_conversion_factor = {"'kg'": Decimal("1"), "'[lb_av]'": Decimal("0.453592")}
    _g_mg_conversion_factor = {"'g'": Decimal("1"), "'mg'": Decimal("0.001")}

    datetime_multipliers = {
        **{key: Decimal("604800") for key in ["'wk'", "week", "weeks"]},
        **{key: Decimal("86400") for key in ["'d'", "day", "days"]},
        **{key: Decimal("3600") for key in ["'h'", "hour", "hours"]},
        **{key: Decimal("60") for key in ["'min'", "minute", "minutes"]},
        **{key: Decimal("1") for key in ["'s'", "second", "seconds"]},
        **{key: Decimal("0.001") for key in ["'ms'", "millisecond", "milliseconds"]},
    }

    def __init__(self, value, unit):
        super().__init__()
        self.asStr = f"{value} {unit}"
        self.value = value
        self.unit = unit

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
            if self.unit in self._years_and_months and other.unit in self._years_and_months:
                if self.unit == "'a'" or other.unit == "'a'":
                    return False
                return self._compare_years_and_months(other)
            elif self.unit in self._weeks_days_and_time and other.unit in self._weeks_days_and_time:
                self_value_in_seconds = self.value * self.datetime_multipliers[self.unit]
                other_value_in_seconds = other.value * self.datetime_multipliers[other.unit]
                return self_value_in_seconds == other_value_in_seconds
            else:
                if self.unit != other.unit:
                    converted = FP_Quantity.conv_unit_to(self.unit, self.value, other.unit)
                    if converted is not None:
                        return other.value == converted.value and other.unit == converted.unit

                return self.value == other.value and self.unit == other.unit
        else:
            return super().__eq__(other)

    @staticmethod
    def _strip_unit_quotes(unit):
        """Strip surrounding single quotes from UCUM unit strings."""
        if unit.startswith("'") and unit.endswith("'"):
            return unit[1:-1]
        return unit

    def __mul__(self, other):
        """Multiply quantity by a number or another quantity."""
        if isinstance(other, (int, float, Decimal)):
            return FP_Quantity(self.value * other, self.unit)
        if isinstance(other, FP_Quantity):
            # Try to normalize to the same dimension first
            converted = FP_Quantity.conv_unit_to(self.unit, self.value, other.unit)
            if converted is not None:
                # Same dimension: normalize, multiply, produce squared unit
                new_value = converted.value * other.value
                bare = FP_Quantity._strip_unit_quotes(other.unit)
                return FP_Quantity(new_value, f"'{bare}2'")
            # Different dimensions: multiply values, compound unit
            new_value = self.value * other.value
            bare_self = FP_Quantity._strip_unit_quotes(self.unit)
            bare_other = FP_Quantity._strip_unit_quotes(other.unit)
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
            return FP_Quantity(self.value / other, self.unit)
        if isinstance(other, FP_Quantity):
            if other.value == 0:
                return []
            new_value = self.value / other.value
            if self.unit == other.unit:
                return FP_Quantity(new_value, "'1'")
            # Produce proper UCUM compound unit
            bare_self = FP_Quantity._strip_unit_quotes(self.unit)
            bare_other = FP_Quantity._strip_unit_quotes(other.unit)
            return FP_Quantity(new_value, f"'{bare_self}/{bare_other}'")
        return NotImplemented

    def __rtruediv__(self, other):
        """Right division (number / quantity)."""
        if isinstance(other, (int, float, Decimal)):
            if self.value == 0:
                return []
            return FP_Quantity(other / self.value, f"1/{self.unit}")
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
            new_value = value_in_seconds / FP_Quantity.datetime_multipliers.get(toUnit)
            return FP_Quantity(new_value, toUnit)

        from_m_cm_mm_magnitude = FP_Quantity._m_cm_mm_conversion_factor.get(fromUnit)
        to_m_cm_mm_magnitude = FP_Quantity._m_cm_mm_conversion_factor.get(toUnit)
        if from_m_cm_mm_magnitude and to_m_cm_mm_magnitude:
            return FP_Quantity(from_m_cm_mm_magnitude * value / to_m_cm_mm_magnitude, toUnit)

        from_lbs_kg_magnitude = FP_Quantity._lbs_kg_conversion_factor.get(fromUnit)
        to_lbs_kg_magnitude = FP_Quantity._lbs_kg_conversion_factor.get(toUnit)
        if from_lbs_kg_magnitude and to_lbs_kg_magnitude:
            converted_value = (from_lbs_kg_magnitude * value) / to_lbs_kg_magnitude
            rounded_value = converted_value.quantize(Decimal("1."), rounding=ROUND_UP)
            return FP_Quantity(rounded_value, toUnit)

        from_g_mg_magnitude = FP_Quantity._g_mg_conversion_factor.get(fromUnit)
        to_g_mg_magnitude = FP_Quantity._g_mg_conversion_factor.get(toUnit)
        if from_g_mg_magnitude and to_g_mg_magnitude:
            result = (from_g_mg_magnitude * Decimal(str(value)) / to_g_mg_magnitude).quantize(
                Decimal("1."), rounding=ROUND_HALF_UP
            )
            return FP_Quantity(result, toUnit)
        return None

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

        # Try to convert units for comparison
        if self.unit != other.unit:
            converted = FP_Quantity.conv_unit_to(self.unit, self.value, other.unit)
            if converted is not None:
                if converted.value < other.value:
                    return -1
                elif converted.value > other.value:
                    return 1
                return 0

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
            return self._getDateTimeInt() == otherDateTime._getDateTimeInt()

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

        thisDateTimeInt = self._getDateTimeInt()
        otherDateTimeInt = otherDateTime._getDateTimeInt()

        if thisDateTimeInt < otherDateTimeInt:
            return -1
        elif thisDateTimeInt == otherDateTimeInt:
            return 0
        return 1

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
        ("millisecond", "hour"): 3_600_000,
        ("millisecond", "minute"): 60_000,
        ("millisecond", "day"): 86_400_000,
    }

    @staticmethod
    def _truncate_toward_zero(value, divisor):
        """Truncate integer division toward zero (floor for positive, ceil for negative)."""
        return math.floor(value / divisor) if value >= 0 else math.ceil(value / divisor)

    def plus(self, time_quantity):
        value = int(time_quantity.value)
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
            elif precision == 7:
                result = date_obj + timedelta(hours=value)
            else:
                result = date_obj
        elif time_unit in ("minute", "second", "millisecond"):
            target_unit_by_precision = {4: "hour", 5: "minute", 7: None}
            target = target_unit_by_precision.get(precision)
            if target is not None:
                result = date_obj + relativedelta(
                    **{target + "s": trunc(value, divs[(time_unit, target)])}
                )
            elif precision == 7:
                result = date_obj + timedelta(**{time_unit + "s": value})
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
            # Time-based units on Date: convert to days
            result = date_obj + relativedelta(
                days=trunc(value, divs[(time_unit, "day")])
            )
        return self._extractDateByPrecision(result, precision)

    def _plus_time(self, value, time_unit, dt_list, time_quantity):
        precision = self._calculateTimePrecision(dt_list)
        date_obj = self._convertTime(dt_list)

        if precision == 2:
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
        elif precision in (3, 4):
            if time_unit == "hour":
                result = date_obj + relativedelta(minutes=value * 60)
            elif time_unit == "minute":
                result = date_obj + relativedelta(minutes=value)
            elif time_unit == "second":
                milliseconds = float(str(time_quantity).split()[0]) * 1000
                result = date_obj + relativedelta(microseconds=milliseconds * 1000)
            elif time_unit == "millisecond":
                result = date_obj + relativedelta(microseconds=value * 1000)
            else:
                result = date_obj
        else:
            result = date_obj
        return (
            self._extractTimeByPrecision(result, precision if precision < 3 else 4) + (dt_list[4] or "")
        )

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
        month = m.group("month")
        day = m.group("day")
        if month is not None and not (1 <= int(month) <= 12):
            return None
        if day is not None:
            year_int = int(m.group("year"))
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

        if not re.match(timeRE, dateStr):
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
                "%H:%M:%S%z",
                "%H:%M:%S.%f%z",
                "%H:%M:%S",
                "%H:%M:%S.%f",
                "%H:%M%z",
                "%H:%M",
                "%H%z",
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

    def __str__(self):
        if self._pyTimeObject:
            time_str = self._pyTimeObject.isoformat()
            if "." in time_str:
                time_str = time_str[: time_str.index(".") + 4]
            return time_str
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
        format = {1: "T%H", 2: "T%H:%M", 3: "T%H:%M:%S", 4: "T%H:%M:%S.%f"}
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
        month = m.group("month")
        day = m.group("day")
        hour = m.group("hour")
        minute = m.group("minute")
        second = m.group("second")
        if month is not None and not (1 <= int(month) <= 12):
            return None
        if day is not None:
            year_int = int(m.group("year"))
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
        if re.match(r"^\d{4}-\d{2}-\d{2}$", self.asStr):
            return self.asStr
        if self.asStr and len(self.asStr) <= 4:
            return self.asStr
        if self._getDateTimeObject():
            iso_str = self._getDateTimeObject().isoformat()
            if "." in iso_str:
                iso_str = iso_str[: iso_str.index(".") + 4] + iso_str[iso_str.index(".") + 7 :]
            return iso_str
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
            # Use original timezone if provided, otherwise use the date_obj's timezone
            if timezone_str:
                # Normalize Z to +00:00 for consistent output
                tz_output = "+00:00" if timezone_str == "Z" else timezone_str
            else:
                tz_offset = date_obj.strftime("%z")
                tz_output = tz_offset[:3] + ":" + tz_offset[3:] if tz_offset else "+00:00"
            formatted_date = f"{formatted_date}.{milliseconds}{tz_output}"
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
                return TypeInfo(namespace=namespace, name=path2Type[self.path])

        # Try to resolve type from built-in path-to-type mapping
        # First try exact match
        if self.path in TypeInfo.FHIR_PATH_TO_TYPE:
            return TypeInfo(namespace=namespace, name=TypeInfo.FHIR_PATH_TO_TYPE[self.path])

        # Try suffix match (e.g., "Patient.gender" matches ".gender")
        for suffix, type_name in TypeInfo.FHIR_PATH_TO_TYPE.items():
            if suffix.startswith(".") and self.path.endswith(suffix[1:]):
                # Make sure it's a proper field match (not a partial match)
                field_name = suffix[1:]
                if self.path.endswith("." + field_name) or self.path == field_name:
                    return TypeInfo(namespace=namespace, name=type_name)

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
            data = FP_Quantity(
                data["value"],
                FP_Quantity.timeUnitsToUCUM.get(data["code"], "'" + data["code"] + "'"),
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

    # Loaded from models/r4/valid_fhir_types.json
    VALID_FHIR_TYPES = set(_load_json("valid_fhir_types.json"))

    @staticmethod
    def get_valid_types():
        """Return the set of valid FHIR and System types."""
        return TypeInfo.VALID_FHIR_TYPES

    # Loaded from models/r4/fhir_path_to_type.json
    FHIR_PATH_TO_TYPE = _load_json("fhir_path_to_type.json")

    # Loaded from models/r4/fhir_type_hierarchy.json
    FHIR_TYPE_HIERARCHY = _load_json("fhir_type_hierarchy.json")

    def __init__(self, name, namespace):
        self.name = name
        self.namespace = namespace

    @staticmethod
    def is_type(type_name, super_type, model=None):
        while type_name:
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

        # FHIRPath §6.3: Types in different namespaces are distinct.
        # FHIR.boolean is NOT System.Boolean (confirmed by FHIRPath test suite).
        if (self.namespace and other.namespace
                and self.namespace != other.namespace):
            return False

        return TypeInfo.is_type(self_name, other_name, model=model)

    def is_exact_type(self, other, model=None):
        """Check if this type is exactly the same as other type (no subtype matching).

        Per FHIRPath §5.1, FHIR primitive types and their System equivalents
        (e.g., FHIR.string ↔ System.String) are treated as the same type.
        """
        if not isinstance(other, TypeInfo):
            return False

        self_name = TypeInfo._normalize_type_name(self.namespace, self.name)
        other_name = TypeInfo._normalize_type_name(other.namespace, other.name)

        # If both namespaces are known and differ, only allow the comparison
        # when the normalized names match a known primitive-type equivalence.
        if (self.namespace and other.namespace
                and self.namespace != other.namespace):
            return self_name == other_name and self_name in TypeInfo.FHIR_TO_SYSTEM_TYPE

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
            return value.get_type_info()
        # FHIR resources represented as dicts: detect via resourceType key
        if isinstance(value, abc.Mapping) and 'resourceType' in value:
            return TypeInfo(namespace=TypeInfo.FHIR, name=value['resourceType'])
        return TypeInfo.create_by_value_in_namespace(TypeInfo.System, value)
