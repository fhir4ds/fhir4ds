#pragma once

#include "datetime.hpp"
#include <cstdint>
#include <string>
#include "cql/optional.hpp"

namespace cql {

struct AgeCalculator {
	static Optional<DateTimeValue> extract_birthdate(const char *json, size_t len);

	// Age-style (complete units, birthday logic) — for AgeInYears/Months/etc.
	static Optional<int64_t> age_in_years(const DateTimeValue &birth, const DateTimeValue &as_of);
	static Optional<int64_t> age_in_months(const DateTimeValue &birth, const DateTimeValue &as_of);
	static Optional<int64_t> age_in_days(const DateTimeValue &birth, const DateTimeValue &as_of);
	static Optional<int64_t> age_in_hours(const DateTimeValue &birth, const DateTimeValue &as_of);
	static Optional<int64_t> age_in_minutes(const DateTimeValue &birth, const DateTimeValue &as_of);
	static Optional<int64_t> age_in_seconds(const DateTimeValue &birth, const DateTimeValue &as_of);

	// Boundary-crossing (calendar difference) — for differenceInYears/Months/etc.
	static Optional<int64_t> diff_years(const DateTimeValue &start, const DateTimeValue &end);
	static Optional<int64_t> diff_months(const DateTimeValue &start, const DateTimeValue &end);
	static Optional<int64_t> diff_days(const DateTimeValue &start, const DateTimeValue &end);
	static Optional<int64_t> diff_hours(const DateTimeValue &start, const DateTimeValue &end);
	static Optional<int64_t> diff_minutes(const DateTimeValue &start, const DateTimeValue &end);
	static Optional<int64_t> diff_seconds(const DateTimeValue &start, const DateTimeValue &end);
};

} // namespace cql
