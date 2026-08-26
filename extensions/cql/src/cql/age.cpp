#include "cql/age.hpp"
#include "yyjson.hpp"

using namespace duckdb_yyjson; // NOLINT
#include <algorithm>
#include <cstdlib>

namespace cql {

namespace {

bool IsLeapYear(int32_t year) {
	return (year % 4 == 0) && (year % 100 != 0 || year % 400 == 0);
}

int32_t DaysInMonth(int32_t year, int32_t month) {
	switch (month) {
	case 2:
		return IsLeapYear(year) ? 29 : 28;
	case 4:
	case 6:
	case 9:
	case 11:
		return 30;
	default:
		return 31;
	}
}

DateTimeValue AddCalendarMonths(const DateTimeValue &value, int64_t months) {
	int64_t month_index = static_cast<int64_t>(value.year) * 12 + (value.month - 1) + months;
	int64_t year = month_index / 12;
	int64_t month_zero = month_index % 12;
	if (month_zero < 0) {
		month_zero += 12;
		year--;
	}

	DateTimeValue result = value;
	result.year = static_cast<int32_t>(year);
	result.month = static_cast<int32_t>(month_zero + 1);
	result.day = std::min(value.day, DaysInMonth(result.year, result.month));
	return result;
}

bool DateAfter(const DateTimeValue &left, const DateTimeValue &right) {
	if (left.year != right.year) {
		return left.year > right.year;
	}
	if (left.month != right.month) {
		return left.month > right.month;
	}
	return left.day > right.day;
}

} // namespace

Optional<DateTimeValue> AgeCalculator::extract_birthdate(const char *json, size_t len) {
	yyjson_doc *doc = yyjson_read(json, len, 0);
	if (!doc) {
		return NullOpt<DateTimeValue>();
	}

	yyjson_val *root = yyjson_doc_get_root(doc);
	yyjson_val *bd = yyjson_obj_get(root, "birthDate");

	Optional<DateTimeValue> result;
	if (bd && yyjson_is_str(bd)) {
		result = DateTimeValue::parse(yyjson_get_str(bd));
	}
	yyjson_doc_free(doc);
	return result;
}

Optional<std::string> AgeCalculator::extract_birthdate_text(const char *json, size_t len) {
	yyjson_doc *doc = yyjson_read(json, len, 0);
	if (!doc) {
		return NullOpt<std::string>();
	}
	yyjson_val *root = yyjson_doc_get_root(doc);
	yyjson_val *bd = yyjson_obj_get(root, "birthDate");
	Optional<std::string> result;
	if (bd && yyjson_is_str(bd)) {
		result = std::string(yyjson_get_str(bd));
	}
	yyjson_doc_free(doc);
	return result;
}

Optional<int64_t> AgeCalculator::age_in_years(const DateTimeValue &birth, const DateTimeValue &as_of) {
	int64_t years = as_of.year - birth.year;
	if (DateAfter(AddCalendarMonths(birth, years * 12), as_of)) {
		years--;
	}
	if (years < 0) {
		return NullOpt<int64_t>(); // Negative age is clinically invalid
	}
	return years;
}

Optional<int64_t> AgeCalculator::age_in_months(const DateTimeValue &birth, const DateTimeValue &as_of) {
	int64_t months = (as_of.year - birth.year) * 12 + (as_of.month - birth.month);
	if (DateAfter(AddCalendarMonths(birth, months), as_of)) {
		months--;
	}
	if (months < 0) {
		return NullOpt<int64_t>(); // Negative age is clinically invalid
	}
	return months;
}

Optional<int64_t> AgeCalculator::age_in_days(const DateTimeValue &birth, const DateTimeValue &as_of) {
	auto days = as_of.to_julian_day() - birth.to_julian_day();
	if (days < 0) {
		return NullOpt<int64_t>(); // Negative age is clinically invalid
	}
	return days;
}

Optional<int64_t> AgeCalculator::age_in_hours(const DateTimeValue &birth, const DateTimeValue &as_of) {
	auto days = age_in_days(birth, as_of);
	if (!days) {
		return NullOpt<int64_t>();
	}
	int64_t hours = *days * 24 + (as_of.hour - birth.hour);
	if (hours < 0) {
		return NullOpt<int64_t>();
	}
	return hours;
}

Optional<int64_t> AgeCalculator::age_in_minutes(const DateTimeValue &birth, const DateTimeValue &as_of) {
	auto hours = age_in_hours(birth, as_of);
	if (!hours) {
		return NullOpt<int64_t>();
	}
	int64_t minutes = *hours * 60 + (as_of.minute - birth.minute);
	if (minutes < 0) {
		return NullOpt<int64_t>();
	}
	return minutes;
}

Optional<int64_t> AgeCalculator::age_in_seconds(const DateTimeValue &birth, const DateTimeValue &as_of) {
	auto minutes = age_in_minutes(birth, as_of);
	if (!minutes) {
		return NullOpt<int64_t>();
	}
	int64_t seconds = *minutes * 60 + (as_of.second - birth.second);
	if (seconds < 0) {
		return NullOpt<int64_t>();
	}
	return seconds;
}

// =====================================================================
// Boundary-crossing difference functions
// These count calendar boundary crossings, not complete units.
// Example: differenceInYears("2020-12-31", "2021-01-01") = 1
// =====================================================================

Optional<int64_t> AgeCalculator::diff_years(const DateTimeValue &start, const DateTimeValue &end) {
	return static_cast<int64_t>(end.year - start.year);
}

Optional<int64_t> AgeCalculator::diff_months(const DateTimeValue &start, const DateTimeValue &end) {
	return static_cast<int64_t>((end.year - start.year) * 12 + (end.month - start.month));
}

Optional<int64_t> AgeCalculator::diff_days(const DateTimeValue &start, const DateTimeValue &end) {
	return end.to_julian_day() - start.to_julian_day();
}

Optional<int64_t> AgeCalculator::diff_hours(const DateTimeValue &start, const DateTimeValue &end) {
	int64_t ms = end.to_epoch_millis() - start.to_epoch_millis();
	return ms / 3600000LL;
}

Optional<int64_t> AgeCalculator::diff_minutes(const DateTimeValue &start, const DateTimeValue &end) {
	int64_t ms = end.to_epoch_millis() - start.to_epoch_millis();
	return ms / 60000LL;
}

Optional<int64_t> AgeCalculator::diff_seconds(const DateTimeValue &start, const DateTimeValue &end) {
	int64_t ms = end.to_epoch_millis() - start.to_epoch_millis();
	return ms / 1000LL;
}

} // namespace cql
