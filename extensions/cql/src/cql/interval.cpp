#include "cql/interval.hpp"
#include "yyjson.hpp"

using namespace duckdb_yyjson; // NOLINT
#include <sstream>

namespace cql {

bool is_json_interval(const std::string &str) {
	return !str.empty() && str[0] == '{';
}

Optional<Interval> Interval::parse(const std::string &json) {
	if (json.empty()) {
		return NullOpt<Interval>();
	}

	// Point value (non-JSON string)
	if (json[0] != '{') {
		auto point = DateTimeValue::parse(json);
		if (!point) {
			return NullOpt<Interval>();
		}
		return Interval::from_point(*point);
	}

	yyjson_doc *doc = yyjson_read(json.c_str(), json.size(), 0);
	if (!doc) {
		return NullOpt<Interval>();
	}

	yyjson_val *root = yyjson_doc_get_root(doc);
	if (!yyjson_is_obj(root)) {
		yyjson_doc_free(doc);
		return NullOpt<Interval>();
	}

	Interval iv;

	// Try CQL format: low/high/lowClosed/highClosed
	yyjson_val *low_val = yyjson_obj_get(root, "low");
	yyjson_val *high_val = yyjson_obj_get(root, "high");
	yyjson_val *start_val = yyjson_obj_get(root, "start");
	yyjson_val *end_val = yyjson_obj_get(root, "end");

	// CQL format
	if (low_val && yyjson_is_str(low_val)) {
		iv.low = DateTimeValue::parse(yyjson_get_str(low_val));
	}
	if (high_val && yyjson_is_str(high_val)) {
		iv.high = DateTimeValue::parse(yyjson_get_str(high_val));
	}

	// FHIR Period format (start/end)
	if (!iv.low && start_val && yyjson_is_str(start_val)) {
		iv.low = DateTimeValue::parse(yyjson_get_str(start_val));
	}
	if (!iv.high && end_val && yyjson_is_str(end_val)) {
		iv.high = DateTimeValue::parse(yyjson_get_str(end_val));
	}

	// Closedness
	yyjson_val *low_closed = yyjson_obj_get(root, "lowClosed");
	yyjson_val *high_closed = yyjson_obj_get(root, "highClosed");
	iv.low_closed = low_closed ? yyjson_get_bool(low_closed) : true;
	iv.high_closed = high_closed ? yyjson_get_bool(high_closed) : true;

	yyjson_doc_free(doc);

	if (!iv.low && !iv.high) {
		return NullOpt<Interval>();
	}
	return iv;
}

Interval Interval::from_point(const DateTimeValue &point) {
	Interval iv;
	iv.low = point;
	iv.high = point;
	iv.low_closed = true;
	iv.high_closed = true;
	return iv;
}

bool Interval::contains_point(const DateTimeValue &point) const {
	if (low) {
		if (low_closed) {
			if (point < *low) {
				return false;
			}
		} else {
			if (point <= *low) {
				return false;
			}
		}
	}
	if (high) {
		if (high_closed) {
			if (point > *high) {
				return false;
			}
		} else {
			if (point >= *high) {
				return false;
			}
		}
	}
	return true;
}

bool Interval::contains_interval(const Interval &other) const {
	// If inner interval has unknown low bound but outer has a finite low,
	// we cannot verify containment — CQL result is null → treat as false
	if (!other.low && low) {
		return false;
	}
	if (other.low && !contains_point(*other.low)) {
		return false;
	}
	// If inner interval has unknown high bound but outer has a finite high,
	// we cannot verify containment — CQL result is null → treat as false
	if (!other.high && high) {
		return false;
	}
	if (other.high && !contains_point(*other.high)) {
		return false;
	}
	return true;
}

bool Interval::properly_contains_point(const DateTimeValue &point) const {
	if (!contains_point(point)) {
		return false;
	}
	if (low && point == *low) {
		return false;
	}
	if (high && point == *high) {
		return false;
	}
	return true;
}

bool Interval::properly_contains_interval(const Interval &other) const {
	return contains_interval(other) && !(*this == other);
}

bool operator==(const Interval &a, const Interval &b) {
	bool low_eq = (!a.low && !b.low) || (a.low && b.low && *a.low == *b.low);
	bool high_eq = (!a.high && !b.high) || (a.high && b.high && *a.high == *b.high);
	return low_eq && high_eq && a.low_closed == b.low_closed && a.high_closed == b.high_closed;
}

bool Interval::overlaps(const Interval &other) const {
	if (low && other.high) {
		if (*other.high < *low) {
			return false;
		}
		// Equal boundary but one is exclusive → no overlap
		if (*other.high == *low && (!other.high_closed || !low_closed)) {
			return false;
		}
	}
	if (high && other.low) {
		if (*high < *other.low) {
			return false;
		}
		// Equal boundary but one is exclusive → no overlap
		if (*high == *other.low && (!high_closed || !other.low_closed)) {
			return false;
		}
	}
	return true;
}

bool Interval::before(const Interval &other) const {
	if (!high || !other.low) {
		return false;
	}
	if (high_closed && other.low_closed) {
		return *high < *other.low;
	}
	return *high <= *other.low;
}

bool Interval::after(const Interval &other) const {
	return other.before(*this);
}

bool Interval::meets(const Interval &other) const {
	return meets_before(other) || meets_after(other);
}

bool Interval::meets_before(const Interval &other) const {
	if (!high || !other.low) {
		return false;
	}
	return *high == *other.low;
}

bool Interval::meets_after(const Interval &other) const {
	return other.meets_before(*this);
}

bool Interval::includes(const Interval &other) const {
	return contains_interval(other);
}

bool Interval::properly_includes(const Interval &other) const {
	return properly_contains_interval(other);
}

bool Interval::overlaps_before(const Interval &other) const {
	if (!low || !other.low) {
		return false;
	}
	// NULL high means unbounded (extends to +infinity) → always >= other.low
	if (!high) {
		return *low < *other.low;
	}
	return *low < *other.low && *high >= *other.low;
}

bool Interval::overlaps_after(const Interval &other) const {
	return other.overlaps_before(*this);
}

bool Interval::starts_same(const Interval &other) const {
	if (!low || !other.low) {
		return !low && !other.low;
	}
	return *low == *other.low;
}

bool Interval::ends_same(const Interval &other) const {
	if (!high || !other.high) {
		return !high && !other.high;
	}
	return *high == *other.high;
}

Optional<int64_t> Interval::width_days() const {
	if (!low || !high) {
		return NullOpt<int64_t>();
	}
	return high->to_julian_day() - low->to_julian_day();
}

std::string Interval::start_string() const {
	return low ? low->to_string() : "";
}

std::string Interval::end_string() const {
	return high ? high->to_string() : "";
}

std::string Interval::to_json() const {
	std::ostringstream oss;
	oss << "{";
	if (low) {
		oss << "\"low\":\"" << low->to_string() << "\"";
	} else {
		oss << "\"low\":null";
	}
	oss << ",";
	if (high) {
		oss << "\"high\":\"" << high->to_string() << "\"";
	} else {
		oss << "\"high\":null";
	}
	oss << ",\"lowClosed\":" << (low_closed ? "true" : "false");
	oss << ",\"highClosed\":" << (high_closed ? "true" : "false");
	oss << "}";
	return oss.str();
}

std::vector<Interval> parse_interval_array(const std::string &json_array) {
	std::vector<Interval> result;
	if (json_array.empty()) {
		return result;
	}

	yyjson_doc *doc = yyjson_read(json_array.c_str(), json_array.size(), 0);
	if (!doc) {
		return result;
	}

	yyjson_val *root = yyjson_doc_get_root(doc);
	if (!yyjson_is_arr(root)) {
		yyjson_doc_free(doc);
		return result;
	}

	size_t arr_idx, arr_max;
	yyjson_val *elem;
	yyjson_arr_foreach(root, arr_idx, arr_max, elem) {
		if (yyjson_is_obj(elem)) {
			char *elem_json = yyjson_val_write(elem, 0, nullptr);
			if (elem_json) {
				auto iv = Interval::parse(elem_json);
				if (iv) {
					result.push_back(*iv);
				}
				free(elem_json);
			}
		} else if (yyjson_is_str(elem)) {
			// JSON-escaped string element (DuckDB to_json encodes VARCHARs as strings)
			const char *str_val = yyjson_get_str(elem);
			if (str_val) {
				auto iv = Interval::parse(str_val);
				if (iv) {
					result.push_back(*iv);
				}
			}
		}
	}
	yyjson_doc_free(doc);
	return result;
}

} // namespace cql
