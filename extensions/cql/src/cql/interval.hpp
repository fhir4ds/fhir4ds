#pragma once

#include "datetime.hpp"
#include <string>
#include <vector>
#include <cstdint>
#include "cql/optional.hpp"

namespace cql {

// Polymorphic bound types for CQL intervals
enum class BoundType { DateTime, Integer, Decimal, Quantity, Time };

struct BoundValue {
	BoundType type;
	Optional<DateTimeValue> dt_val;
	Optional<int64_t> int_val;
	Optional<double> dec_val;
	// For Quantity: store numeric value + unit string for comparison
	Optional<double> qty_numeric;
	std::string qty_unit;
	// Original string representation for serialization
	std::string raw_str;

	BoundValue() : type(BoundType::Integer) {}

	// Compare two BoundValues. Returns -1, 0, 1 for <, ==, >.
	// Returns -2 for type mismatch or incomparable.
	int compare(const BoundValue &other) const;

	// Compare at a specific precision (DateTime only).
	int compare_at_prec(const BoundValue &other, DateTimeValue::Precision prec) const;

	// Serialize to string for JSON output
	std::string to_string() const;

	// Parse from a yyjson value (used during interval JSON parsing)
	// Requires forward-declared yyjson types — implemented in .cpp
	static Optional<BoundValue> from_string(const std::string &str);
	static Optional<BoundValue> from_interval_bound_string(const std::string &str);
	static Optional<BoundValue> from_number(double val, bool is_integer);
};

struct Interval {
	Optional<BoundValue> low;
	Optional<BoundValue> high;
	bool low_closed = true;
	bool high_closed = true;
	BoundType bound_type;

	Interval() : bound_type(BoundType::DateTime) {}

	static Optional<Interval> parse(const std::string &json);
	static Interval from_point(const BoundValue &point);
	static Interval from_datetime_point(const DateTimeValue &point);

	bool contains_point(const BoundValue &point) const;
	bool contains_interval(const Interval &other) const;
	bool properly_contains_point(const BoundValue &point) const;
	bool properly_contains_interval(const Interval &other) const;
	bool overlaps(const Interval &other) const;
	bool before(const Interval &other) const;
	bool after(const Interval &other) const;
	bool meets(const Interval &other) const;
	bool meets_before(const Interval &other) const;
	bool meets_after(const Interval &other) const;
	Optional<bool> properly_contains_point_nullable(const BoundValue &point) const;
	Optional<bool> meets_nullable(const Interval &other) const;
	Optional<bool> meets_before_nullable(const Interval &other) const;
	Optional<bool> meets_after_nullable(const Interval &other) const;
	bool includes(const Interval &other) const;
	bool properly_includes(const Interval &other) const;
	bool overlaps_before(const Interval &other) const;
	bool overlaps_after(const Interval &other) const;
	bool starts_same(const Interval &other) const;
	bool ends_same(const Interval &other) const;

	// Precision-aware interval equality — returns NullOpt when mixed-precision
	// temporal bounds make the equality uncertain (per CQL §Equal).
	Optional<bool> equals_nullable(const Interval &other) const;

	// Precision-aware variants (truncate bounds to precision before comparing)
	bool overlaps(const Interval &other, DateTimeValue::Precision prec) const;
	bool contains_point(const BoundValue &point, DateTimeValue::Precision prec) const;
	bool contains_interval(const Interval &other, DateTimeValue::Precision prec) const;
	bool includes(const Interval &other, DateTimeValue::Precision prec) const;
	bool before(const Interval &other, DateTimeValue::Precision prec) const;
	bool after(const Interval &other, DateTimeValue::Precision prec) const;
	bool overlaps_before(const Interval &other, DateTimeValue::Precision prec) const;
	bool overlaps_after(const Interval &other, DateTimeValue::Precision prec) const;

	Optional<int64_t> width_days() const;
	// Generic width: for numeric intervals returns high-low as string
	Optional<std::string> width_string() const;
	Optional<std::string> size_string() const;
	std::string start_string() const;
	std::string end_string() const;
	std::string to_json() const;

	// Interval set operations
	// Returns the intersection of two intervals, or NullOpt if they don't overlap
	static Optional<Interval> intersect(const Interval &a, const Interval &b);
	// Returns the union of two intervals, or NullOpt if they don't overlap/meet
	static Optional<Interval> union_of(const Interval &a, const Interval &b);
	// Returns the portion of a not in b, or NullOpt
	static Optional<Interval> except_of(const Interval &a, const Interval &b);
	// CQL on or after: start(a) >= end(b)
	static Optional<bool> on_or_after(const Interval &a, const Interval &b);
	// CQL on or before: end(a) <= start(b)
	static Optional<bool> on_or_before(const Interval &a, const Interval &b);
};

bool operator==(const Interval &a, const Interval &b);

// Detect whether a string is a JSON interval or a point value
bool is_json_interval(const std::string &str);

// Parse a point value string into a BoundValue
Optional<BoundValue> parse_point_value(const std::string &str);

// Parse a JSON array of intervals
std::vector<Interval> parse_interval_array(const std::string &json_array);

// Parse precision string ("year","month","day","hour","minute","second","millisecond")
Optional<DateTimeValue::Precision> precision_from_string(const std::string &s);

} // namespace cql
