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
	bool is_time = false;
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

// Normalize a DateTime to UTC wall-clock components for comparison.
//
// CQL #datetime-2 (cql-tests #88): an offset-less DateTime assumes the timezone
// offset of the evaluation request timestamp, so it normalizes with that offset
// (`assumed_offset_minutes`, normally `evaluation_request_offset_minutes()`)
// instead of keeping its local components. A value that carries its own offset
// uses it. Day-and-coarser comparisons stay on local components and must not be
// routed here (CQL-14 doctrine); callers only reach this for hour-or-finer
// comparisons where at least one operand has an explicit offset.
DateTimeValue normalize_for_temporal_compare(const DateTimeValue &value, int32_t assumed_offset_minutes);

} // namespace cql
