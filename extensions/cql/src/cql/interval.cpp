#include "cql/interval.hpp"
#include "yyjson.hpp"

using namespace duckdb_yyjson; // NOLINT
#include <cstdlib>
#include <cmath>
#include <sstream>

namespace cql {

// Escape a string for safe JSON interpolation
static std::string escapeJsonString(const std::string &s) {
	std::string out;
	out.reserve(s.size() + 4);
	for (unsigned char c : s) {
		switch (c) {
		case '"':  out += "\\\""; break;
		case '\\': out += "\\\\"; break;
		case '\b': out += "\\b";  break;
		case '\f': out += "\\f";  break;
		case '\n': out += "\\n";  break;
		case '\r': out += "\\r";  break;
		case '\t': out += "\\t";  break;
		default:
			if (c < 0x20) {
				char buf[8];
				std::snprintf(buf, sizeof(buf), "\\u%04x", static_cast<unsigned>(c));
				out += buf;
			} else {
				out += static_cast<char>(c);
			}
		}
	}
	return out;
}

// =====================================================================
// BoundValue implementation
// =====================================================================

int BoundValue::compare(const BoundValue &other) const {
if (type != other.type) {
return -2; // type mismatch = incomparable
}
switch (type) {
case BoundType::DateTime:
case BoundType::Time:
if (!dt_val || !other.dt_val) {
return -2;
}
return dt_val->compare_at_precision(*other.dt_val, DateTimeValue::Precision::Millisecond);
case BoundType::Integer:
if (!int_val || !other.int_val) {
return -2;
}
return (*int_val < *other.int_val) ? -1 : (*int_val > *other.int_val) ? 1 : 0;
case BoundType::Decimal:
if (!dec_val || !other.dec_val) {
return -2;
}
return (*dec_val < *other.dec_val) ? -1 : (*dec_val > *other.dec_val) ? 1 : 0;
case BoundType::Quantity:
if (!qty_numeric || !other.qty_numeric) {
return -2;
}
return (*qty_numeric < *other.qty_numeric) ? -1 : (*qty_numeric > *other.qty_numeric) ? 1 : 0;
}
return -2;
}

std::string BoundValue::to_string() const {
	// For DateTime/Time, always use canonical DateTimeValue format
	// (normalizes space-separated timestamps to ISO 8601 T-separated)
	if (type == BoundType::DateTime || type == BoundType::Time) {
		return dt_val ? dt_val->to_string() : "";
	}
	// For other types, prefer raw_str for round-trip fidelity
	if (!raw_str.empty()) {
		return raw_str;
	}
	switch (type) {
	case BoundType::Integer:
		if (int_val) {
			std::ostringstream oss;
			oss << *int_val;
			return oss.str();
		}
		return "";
	case BoundType::Decimal:
		if (dec_val) {
			std::ostringstream oss;
			oss << *dec_val;
			return oss.str();
		}
		return "";
	case BoundType::Quantity:
		return "";
	default:
		return "";
	}
}

Optional<BoundValue> BoundValue::from_string(const std::string &str) {
if (str.empty()) {
return NullOpt<BoundValue>();
}

// Quantity JSON: {"value": ..., "unit": ...}
if (str[0] == '{') {
yyjson_doc *doc = yyjson_read(str.c_str(), str.size(), 0);
if (doc) {
yyjson_val *root = yyjson_doc_get_root(doc);
yyjson_val *val_node = yyjson_obj_get(root, "value");
if (val_node && (yyjson_is_real(val_node) || yyjson_is_int(val_node) || yyjson_is_sint(val_node))) {
BoundValue bv;
bv.type = BoundType::Quantity;
bv.qty_numeric = Optional<double>(yyjson_get_num(val_node));
yyjson_val *unit_node = yyjson_obj_get(root, "unit");
if (!unit_node) {
unit_node = yyjson_obj_get(root, "code");
}
if (unit_node && yyjson_is_str(unit_node)) {
bv.qty_unit = yyjson_get_str(unit_node);
}
bv.raw_str = str;
yyjson_doc_free(doc);
return Optional<BoundValue>(bv);
}
yyjson_doc_free(doc);
}
return NullOpt<BoundValue>();
}

// Time string: starts with 'T' or looks like HH:MM:SS (no dashes)
if ((str[0] == 'T' && str.size() >= 3 && str[1] >= '0' && str[1] <= '9') ||
    (str.size() >= 5 && str[2] == ':' && str[0] >= '0' && str[0] <= '9' &&
     str.find('-') == std::string::npos)) {
// Try to parse time as millis-since-midnight
// Not a full time parser — keep as raw string for now
// DateTime parser won't handle these, so fall through
}

// Try numeric FIRST for pure-numeric strings (matches Python _parse_point order).
// This ensures "5" is Integer, not DateTime(year=5). Only strings with
// date-like characters (dash, T, colon) fall through to the datetime parser.
bool has_dash = (str.find('-') != std::string::npos && str[0] != '-')
                || (str[0] == '-' && str.find('-', 1) != std::string::npos);
bool has_colon = str.find(':') != std::string::npos;
bool has_T = str.find('T') != std::string::npos;
bool looks_datelike = has_dash || has_colon || has_T;

if (!looks_datelike) {
const char *s = str.c_str();
char *end = NULL;
double d = std::strtod(s, &end);
if (end != s && *end == '\0' && !std::isinf(d) && !std::isnan(d)) {
BoundValue bv;
bv.raw_str = str;
if (str.find('.') == std::string::npos &&
    d >= -9.22e18 && d <= 9.22e18 &&
    d == static_cast<double>(static_cast<int64_t>(d))) {
bv.type = BoundType::Integer;
bv.int_val = Optional<int64_t>(static_cast<int64_t>(d));
} else {
bv.type = BoundType::Decimal;
bv.dec_val = Optional<double>(d);
}
return Optional<BoundValue>(bv);
}
}

// Try datetime (for strings with date separators like "2024-01-15")
auto dt = DateTimeValue::parse(str);
if (dt) {
BoundValue bv;
bv.type = BoundType::DateTime;
bv.dt_val = dt;
bv.raw_str = str;
return Optional<BoundValue>(bv);
}

// Final fallback: try numeric for any remaining string (e.g. "1.5e10")
if (looks_datelike) {
const char *s = str.c_str();
char *end = NULL;
double d = std::strtod(s, &end);
if (end != s && *end == '\0' && !std::isinf(d) && !std::isnan(d)) {
BoundValue bv;
bv.raw_str = str;
if (str.find('.') == std::string::npos &&
    d >= -9.22e18 && d <= 9.22e18 &&
    d == static_cast<double>(static_cast<int64_t>(d))) {
bv.type = BoundType::Integer;
bv.int_val = Optional<int64_t>(static_cast<int64_t>(d));
} else {
bv.type = BoundType::Decimal;
bv.dec_val = Optional<double>(d);
}
return Optional<BoundValue>(bv);
}
}

return NullOpt<BoundValue>();
}

Optional<BoundValue> BoundValue::from_number(double val, bool is_integer) {
BoundValue bv;
if (is_integer) {
bv.type = BoundType::Integer;
bv.int_val = Optional<int64_t>(static_cast<int64_t>(val));
std::ostringstream oss;
oss << static_cast<int64_t>(val);
bv.raw_str = oss.str();
} else {
bv.type = BoundType::Decimal;
bv.dec_val = Optional<double>(val);
std::ostringstream oss;
oss << val;
bv.raw_str = oss.str();
}
return Optional<BoundValue>(bv);
}

// =====================================================================
// Helper: parse a bound value from a yyjson_val
// =====================================================================
static Optional<BoundValue> parse_bound_from_yyjson(yyjson_val *val) {
if (!val || yyjson_is_null(val)) {
return NullOpt<BoundValue>();
}
if (yyjson_is_str(val)) {
return BoundValue::from_string(yyjson_get_str(val));
}
if (yyjson_is_int(val) || yyjson_is_sint(val)) {
return BoundValue::from_number(static_cast<double>(yyjson_get_sint(val)), true);
}
if (yyjson_is_real(val)) {
return BoundValue::from_number(yyjson_get_real(val), false);
}
if (yyjson_is_obj(val)) {
// Quantity object: {"value": N, "unit": "..."}
yyjson_val *v = yyjson_obj_get(val, "value");
if (v && (yyjson_is_real(v) || yyjson_is_int(v) || yyjson_is_sint(v))) {
BoundValue bv;
bv.type = BoundType::Quantity;
bv.qty_numeric = Optional<double>(yyjson_get_num(v));
yyjson_val *u = yyjson_obj_get(val, "unit");
if (!u) {
u = yyjson_obj_get(val, "code");
}
if (u && yyjson_is_str(u)) {
bv.qty_unit = yyjson_get_str(u);
}
char *json_str = yyjson_val_write(val, 0, NULL);
if (json_str) {
bv.raw_str = json_str;
free(json_str);
}
return Optional<BoundValue>(bv);
}
}
return NullOpt<BoundValue>();
}

// =====================================================================
// Interval implementation
// =====================================================================

bool is_json_interval(const std::string &str) {
if (str.empty() || str[0] != '{') {
return false;
}
// Distinguish interval JSON (has low/high/start/end) from quantity JSON (has value/unit)
return str.find("\"low\"") != std::string::npos
    || str.find("\"high\"") != std::string::npos
    || str.find("\"start\"") != std::string::npos
    || str.find("\"end\"") != std::string::npos;
}

Optional<BoundValue> parse_point_value(const std::string &str) {
return BoundValue::from_string(str);
}

Optional<Interval> Interval::parse(const std::string &json) {
if (json.empty()) {
return NullOpt<Interval>();
}

// Point value (non-JSON string)
if (json[0] != '{') {
auto point = BoundValue::from_string(json);
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

// Try CQL format: low/high
yyjson_val *low_val = yyjson_obj_get(root, "low");
yyjson_val *high_val = yyjson_obj_get(root, "high");
yyjson_val *start_val = yyjson_obj_get(root, "start");
yyjson_val *end_val = yyjson_obj_get(root, "end");

// CQL format
if (low_val && !yyjson_is_null(low_val)) {
iv.low = parse_bound_from_yyjson(low_val);
}
if (high_val && !yyjson_is_null(high_val)) {
iv.high = parse_bound_from_yyjson(high_val);
}

// FHIR Period format (start/end) — fallback if low/high didn't parse
if (!iv.low && start_val && !yyjson_is_null(start_val)) {
iv.low = parse_bound_from_yyjson(start_val);
}
if (!iv.high && end_val && !yyjson_is_null(end_val)) {
iv.high = parse_bound_from_yyjson(end_val);
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

// Set bound_type from whichever bound is present
if (iv.low) {
iv.bound_type = iv.low->type;
} else if (iv.high) {
iv.bound_type = iv.high->type;
}

return Optional<Interval>(iv);
}

Interval Interval::from_point(const BoundValue &point) {
Interval iv;
iv.low = point;
iv.high = point;
iv.low_closed = true;
iv.high_closed = true;
iv.bound_type = point.type;
return iv;
}

Interval Interval::from_datetime_point(const DateTimeValue &point) {
BoundValue bv;
bv.type = BoundType::DateTime;
bv.dt_val = point;
bv.raw_str = point.to_string();
return from_point(bv);
}

// =====================================================================
// Algebra methods — all dispatch through BoundValue::compare()
// =====================================================================

bool Interval::contains_point(const BoundValue &point) const {
if (low) {
int cmp = low->compare(point);
if (cmp == -2) {
return false;
}
if (low_closed) {
if (cmp > 0) {
return false; // low > point
}
} else {
if (cmp >= 0) {
return false; // low >= point
}
}
}
if (high) {
int cmp = point.compare(*high);
if (cmp == -2) {
return false;
}
if (high_closed) {
if (cmp > 0) {
return false; // point > high
}
} else {
if (cmp >= 0) {
return false; // point >= high
}
}
}
return true;
}

bool Interval::contains_interval(const Interval &other) const {
if (!other.low && low) {
return false;
}
if (other.low && !contains_point(*other.low)) {
return false;
}
if (!other.high && high) {
return false;
}
if (other.high && !contains_point(*other.high)) {
return false;
}
return true;
}

bool Interval::properly_contains_point(const BoundValue &point) const {
if (!contains_point(point)) {
return false;
}
if (low && low->compare(point) == 0) {
return false;
}
if (high && high->compare(point) == 0) {
return false;
}
return true;
}

bool Interval::properly_contains_interval(const Interval &other) const {
return contains_interval(other) && !(*this == other);
}

bool operator==(const Interval &a, const Interval &b) {
bool low_eq = false;
if (!a.low && !b.low) {
low_eq = true;
} else if (a.low && b.low) {
low_eq = (a.low->compare(*b.low) == 0);
}
bool high_eq = false;
if (!a.high && !b.high) {
high_eq = true;
} else if (a.high && b.high) {
high_eq = (a.high->compare(*b.high) == 0);
}
return low_eq && high_eq && a.low_closed == b.low_closed && a.high_closed == b.high_closed;
}

bool Interval::overlaps(const Interval &other) const {
if (low && other.high) {
int cmp = other.high->compare(*low);
if (cmp == -2) {
return false;
}
if (cmp < 0) {
return false;
}
if (cmp == 0 && (!other.high_closed || !low_closed)) {
return false;
}
}
if (high && other.low) {
int cmp = high->compare(*other.low);
if (cmp == -2) {
return false;
}
if (cmp < 0) {
return false;
}
if (cmp == 0 && (!high_closed || !other.low_closed)) {
return false;
}
}
return true;
}

bool Interval::before(const Interval &other) const {
if (!high || !other.low) {
return false;
}
int cmp = high->compare(*other.low);
if (cmp == -2) {
return false;
}
if (high_closed && other.low_closed) {
return cmp < 0;
}
return cmp <= 0;
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
return high->compare(*other.low) == 0;
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
int low_cmp = low->compare(*other.low);
if (low_cmp == -2) {
return false;
}
if (!high) {
return low_cmp < 0;
}
int high_cmp = high->compare(*other.low);
if (high_cmp == -2) {
return false;
}
return low_cmp < 0 && high_cmp >= 0;
}

bool Interval::overlaps_after(const Interval &other) const {
return other.overlaps_before(*this);
}

bool Interval::starts_same(const Interval &other) const {
if (!low || !other.low) {
return !low && !other.low;
}
return low->compare(*other.low) == 0;
}

bool Interval::ends_same(const Interval &other) const {
if (!high || !other.high) {
return !high && !other.high;
}
return high->compare(*other.high) == 0;
}

Optional<int64_t> Interval::width_days() const {
if (!low || !high) {
return NullOpt<int64_t>();
}
if (bound_type == BoundType::DateTime) {
if (!low->dt_val || !high->dt_val) {
return NullOpt<int64_t>();
}
return high->dt_val->to_julian_day() - low->dt_val->to_julian_day();
}
if (bound_type == BoundType::Integer && low->int_val && high->int_val) {
return *high->int_val - *low->int_val;
}
return NullOpt<int64_t>();
}

Optional<std::string> Interval::width_string() const {
if (!low || !high) {
return NullOpt<std::string>();
}
switch (bound_type) {
case BoundType::Integer:
if (low->int_val && high->int_val) {
std::ostringstream oss;
oss << (*high->int_val - *low->int_val);
return Optional<std::string>(oss.str());
}
break;
case BoundType::Decimal:
if (low->dec_val && high->dec_val) {
std::ostringstream oss;
oss << (*high->dec_val - *low->dec_val);
return Optional<std::string>(oss.str());
}
break;
case BoundType::Quantity:
if (low->qty_numeric && high->qty_numeric) {
std::ostringstream oss;
double w = *high->qty_numeric - *low->qty_numeric;
oss << "{\"value\":" << w << ",\"unit\":\"" << escapeJsonString(low->qty_unit) << "\",\"code\":\"" << escapeJsonString(low->qty_unit) << "\"}";
return Optional<std::string>(oss.str());
}
break;
case BoundType::DateTime:
if (low->dt_val && high->dt_val) {
std::ostringstream oss;
oss << (high->dt_val->to_julian_day() - low->dt_val->to_julian_day());
return Optional<std::string>(oss.str());
}
break;
case BoundType::Time:
break;
}
return NullOpt<std::string>();
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
std::string s = low->to_string();
if (low->type == BoundType::Quantity && !s.empty() && s[0] == '{') {
oss << "\"low\":" << s;
} else if (low->type == BoundType::Integer && low->int_val) {
oss << "\"low\":" << *low->int_val;
} else if (low->type == BoundType::Decimal && low->dec_val) {
oss << "\"low\":" << *low->dec_val;
} else {
oss << "\"low\":\"" << s << "\"";
}
} else {
oss << "\"low\":null";
}
oss << ",";
if (high) {
std::string s = high->to_string();
if (high->type == BoundType::Quantity && !s.empty() && s[0] == '{') {
oss << "\"high\":" << s;
} else if (high->type == BoundType::Integer && high->int_val) {
oss << "\"high\":" << *high->int_val;
} else if (high->type == BoundType::Decimal && high->dec_val) {
oss << "\"high\":" << *high->dec_val;
} else {
oss << "\"high\":\"" << s << "\"";
}
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
char *elem_json = yyjson_val_write(elem, 0, NULL);
if (elem_json) {
auto iv = Interval::parse(elem_json);
if (iv) {
result.push_back(*iv);
}
free(elem_json);
}
} else if (yyjson_is_str(elem)) {
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

// =====================================================================
// Interval set operations
// =====================================================================

Optional<bool> Interval::on_or_after(const Interval &a, const Interval &b) {
if (!a.low || !b.high) return NullOpt<bool>();
int cmp = a.low->compare(*b.high);
if (cmp == -2) return NullOpt<bool>();
return Optional<bool>(cmp >= 0);
}

Optional<bool> Interval::on_or_before(const Interval &a, const Interval &b) {
if (!a.high || !b.low) return NullOpt<bool>();
int cmp = a.high->compare(*b.low);
if (cmp == -2) return NullOpt<bool>();
return Optional<bool>(cmp <= 0);
}

Optional<Interval> Interval::intersect(const Interval &a, const Interval &b) {
// New low = max(a.low, b.low)
// New high = min(a.high, b.high)
Interval result;
result.bound_type = a.bound_type;

if (!a.low && !b.low) {
// Both unbounded below
result.low_closed = a.low_closed && b.low_closed;
} else if (!a.low) {
result.low = b.low;
result.low_closed = b.low_closed;
} else if (!b.low) {
result.low = a.low;
result.low_closed = a.low_closed;
} else {
int cmp = a.low->compare(*b.low);
if (cmp == -2) return NullOpt<Interval>();
if (cmp > 0) {
result.low = a.low;
result.low_closed = a.low_closed;
} else if (cmp < 0) {
result.low = b.low;
result.low_closed = b.low_closed;
} else {
result.low = a.low;
result.low_closed = a.low_closed && b.low_closed;
}
}

if (!a.high && !b.high) {
result.high_closed = a.high_closed && b.high_closed;
} else if (!a.high) {
result.high = b.high;
result.high_closed = b.high_closed;
} else if (!b.high) {
result.high = a.high;
result.high_closed = a.high_closed;
} else {
int cmp = a.high->compare(*b.high);
if (cmp == -2) return NullOpt<Interval>();
if (cmp < 0) {
result.high = a.high;
result.high_closed = a.high_closed;
} else if (cmp > 0) {
result.high = b.high;
result.high_closed = b.high_closed;
} else {
result.high = a.high;
result.high_closed = a.high_closed && b.high_closed;
}
}

// Check if result is valid (non-empty)
if (result.low && result.high) {
int cmp = result.low->compare(*result.high);
if (cmp > 0) return NullOpt<Interval>();
if (cmp == 0 && !(result.low_closed && result.high_closed)) return NullOpt<Interval>();
}

return Optional<Interval>(result);
}

Optional<Interval> Interval::union_of(const Interval &a, const Interval &b) {
// Intervals must overlap or meet for union to be valid
if (!a.overlaps(b) && !a.meets(b) && !b.meets(a)) {
return NullOpt<Interval>();
}

Interval result;
result.bound_type = a.bound_type;

// Min of lows
if (!a.low) {
result.low_closed = a.low_closed;
} else if (!b.low) {
result.low_closed = b.low_closed;
} else {
int cmp = a.low->compare(*b.low);
if (cmp == -2) return NullOpt<Interval>();
if (cmp < 0) {
result.low = a.low;
result.low_closed = a.low_closed;
} else if (cmp > 0) {
result.low = b.low;
result.low_closed = b.low_closed;
} else {
result.low = a.low;
result.low_closed = a.low_closed || b.low_closed;
}
}

// Max of highs
if (!a.high) {
result.high_closed = a.high_closed;
} else if (!b.high) {
result.high_closed = b.high_closed;
} else {
int cmp = a.high->compare(*b.high);
if (cmp == -2) return NullOpt<Interval>();
if (cmp > 0) {
result.high = a.high;
result.high_closed = a.high_closed;
} else if (cmp < 0) {
result.high = b.high;
result.high_closed = b.high_closed;
} else {
result.high = a.high;
result.high_closed = a.high_closed || b.high_closed;
}
}

return Optional<Interval>(result);
}

Optional<Interval> Interval::except_of(const Interval &a, const Interval &b) {
// If no overlap, return a
if (!a.overlaps(b)) {
return Optional<Interval>(a);
}

// Check if b completely contains a → return null
if (b.contains_interval(a)) {
return NullOpt<Interval>();
}

// Determine which portion of a remains
bool has_left = false;
bool has_right = false;

if (a.low && b.low) {
int cmp = b.low->compare(*a.low);
if (cmp > 0) has_left = true;
} else if (b.low && !a.low) {
has_left = true;
}

if (a.high && b.high) {
int cmp = b.high->compare(*a.high);
if (cmp < 0) has_right = true;
} else if (b.high && !a.high) {
has_right = true;
}

// CQL except returns only one contiguous interval
if (has_left && has_right) {
return NullOpt<Interval>();
}

Interval result;
result.bound_type = a.bound_type;

if (has_left) {
result.low = a.low;
result.low_closed = a.low_closed;
result.high = b.low;
result.high_closed = !b.low_closed;
return Optional<Interval>(result);
}

if (has_right) {
result.low = b.high;
result.low_closed = !b.high_closed;
result.high = a.high;
result.high_closed = a.high_closed;
return Optional<Interval>(result);
}

return NullOpt<Interval>();
}

} // namespace cql
