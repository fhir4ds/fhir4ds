#pragma once

#include "datetime.hpp"
#include <string>
#include <vector>
#include "cql/optional.hpp"

namespace cql {

struct Interval {
	Optional<DateTimeValue> low;
	Optional<DateTimeValue> high;
	bool low_closed = true;
	bool high_closed = true;

	static Optional<Interval> parse(const std::string &json);
	static Interval from_point(const DateTimeValue &point);

	bool contains_point(const DateTimeValue &point) const;
	bool contains_interval(const Interval &other) const;
	bool properly_contains_point(const DateTimeValue &point) const;
	bool properly_contains_interval(const Interval &other) const;
	bool overlaps(const Interval &other) const;
	bool before(const Interval &other) const;
	bool after(const Interval &other) const;
	bool meets(const Interval &other) const;
	bool meets_before(const Interval &other) const;
	bool meets_after(const Interval &other) const;
	bool includes(const Interval &other) const;
	bool properly_includes(const Interval &other) const;
	bool overlaps_before(const Interval &other) const;
	bool overlaps_after(const Interval &other) const;
	bool starts_same(const Interval &other) const;
	bool ends_same(const Interval &other) const;

	Optional<int64_t> width_days() const;
	std::string start_string() const;
	std::string end_string() const;
	std::string to_json() const;
};

bool operator==(const Interval &a, const Interval &b);

// Detect whether a string is a JSON interval or a point value
bool is_json_interval(const std::string &str);

// Parse a JSON array of intervals
std::vector<Interval> parse_interval_array(const std::string &json_array);

} // namespace cql
