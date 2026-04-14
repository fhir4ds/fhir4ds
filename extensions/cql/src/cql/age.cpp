#include "cql/age.hpp"
#include "yyjson.hpp"

using namespace duckdb_yyjson; // NOLINT
#include <cstdlib>

namespace cql {

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

Optional<int64_t> AgeCalculator::age_in_years(const DateTimeValue &birth, const DateTimeValue &as_of) {
	int64_t years = as_of.year - birth.year;
	if (as_of.month < birth.month || (as_of.month == birth.month && as_of.day < birth.day)) {
		years--;
	}
	if (years < 0) {
		return NullOpt<int64_t>(); // Negative age is clinically invalid
	}
	return years;
}

Optional<int64_t> AgeCalculator::age_in_months(const DateTimeValue &birth, const DateTimeValue &as_of) {
	int64_t months = (as_of.year - birth.year) * 12 + (as_of.month - birth.month);
	if (as_of.day < birth.day) {
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
