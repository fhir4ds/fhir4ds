#pragma once

#include <cstdint>
#include <string>
#include "cql/optional.hpp"

namespace cql {

struct DateTimeValue {
	int32_t year = 0;
	int32_t month = 1;
	int32_t day = 1;
	int32_t hour = 0;
	int32_t minute = 0;
	int32_t second = 0;
	int32_t millisecond = 0;
	bool has_time = false;
	bool has_tz = false;
	int32_t tz_offset_minutes = 0;

	// Precision tracking
	enum class Precision { Year, Month, Day, Hour, Minute, Second, Millisecond };
	Precision precision = Precision::Day;

	bool operator<(const DateTimeValue &other) const;
	bool operator<=(const DateTimeValue &other) const;
	bool operator==(const DateTimeValue &other) const;
	bool operator>(const DateTimeValue &other) const;
	bool operator>=(const DateTimeValue &other) const;
	bool operator!=(const DateTimeValue &other) const;

	std::string to_string() const;
	int64_t to_julian_day() const;
	int64_t to_epoch_millis() const;

	static Optional<DateTimeValue> parse(const std::string &str);

	// Compare at a specific precision
	int compare_at_precision(const DateTimeValue &other, Precision prec) const;
};

} // namespace cql
