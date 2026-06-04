#include "cql/interval.hpp"
#include "cql/quantity.hpp"
#include "yyjson.hpp"

using namespace duckdb_yyjson; // NOLINT
#include <cstdlib>
#include <algorithm>
#include <cmath>
#include <iomanip>
#include <limits>
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

static bool is_day_precision_datetime_marker(const std::string &s) {
	return s.size() == 11 && s[4] == '-' && s[7] == '-' && s[10] == 'T';
}

static std::string format_day_precision_datetime(const DateTimeValue &dt) {
	char buf[16];
	std::snprintf(buf, sizeof(buf), "%04d-%02d-%02dT", dt.year, dt.month, dt.day);
	return std::string(buf);
}

static std::string format_decimal_value(double value) {
	if (std::fabs(value) < 5e-13) {
		value = 0.0;
	}
	std::ostringstream oss;
	oss << std::fixed << std::setprecision(8) << value;
	std::string out = oss.str();
	auto dot = out.find('.');
	if (dot != std::string::npos) {
		while (out.size() > dot + 2 && out[out.size() - 1] == '0') {
			out.erase(out.size() - 1);
		}
		if (out[out.size() - 1] == '.') {
			out += '0';
		}
	}
	return out;
}

static bool is_four_digit_year(const std::string &s) {
	return s.size() == 4 && s[0] >= '0' && s[0] <= '9' && s[1] >= '0' && s[1] <= '9' &&
	       s[2] >= '0' && s[2] <= '9' && s[3] >= '0' && s[3] <= '9';
}

static bool looks_temporal_interval_bound(const std::string &s) {
	if (s.empty()) {
		return false;
	}
	if (is_four_digit_year(s)) {
		return true;
	}
	if (s[0] == 'T') {
		return true;
	}
	if (s.find('T') != std::string::npos || s.find(':') != std::string::npos) {
		return true;
	}
	return s.find('-') != std::string::npos && s[0] != '-';
}

static std::string quantity_json_for_bound(yyjson_val *value_node, const std::string &unit) {
	std::ostringstream oss;
	oss << "{\"value\":";
	char *value_json = yyjson_val_write(value_node, 0, NULL);
	if (value_json) {
		oss << value_json;
		free(value_json);
	} else {
		oss << "null";
	}
	oss << ",\"unit\":\"" << escapeJsonString(unit) << "\"}";
	return oss.str();
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
{
	auto less = quantity_compare(raw_str, other.raw_str, "<");
	if (less && *less) {
		return -1;
	}
	auto greater = quantity_compare(raw_str, other.raw_str, ">");
	if (greater && *greater) {
		return 1;
	}
	auto equal = quantity_compare(raw_str, other.raw_str, "==");
	if (equal && *equal) {
		return 0;
	}
	return -2;
}
}
return -2;
}

int BoundValue::compare_at_prec(const BoundValue &other, DateTimeValue::Precision prec) const {
if (type != other.type) {
return -2;
}
switch (type) {
case BoundType::DateTime:
case BoundType::Time:
if (!dt_val || !other.dt_val) {
return -2;
}
return dt_val->compare_at_precision(*other.dt_val, prec);
default:
return compare(other);
}
}

std::string BoundValue::to_string() const {
	// For DateTime/Time, always use canonical DateTimeValue format
	// (normalizes space-separated timestamps to ISO 8601 T-separated)
	if (type == BoundType::DateTime || type == BoundType::Time) {
		if (!dt_val) {
			return "";
		}
		if (is_day_precision_datetime_marker(raw_str) && !dt_val->has_time &&
		    dt_val->precision == DateTimeValue::Precision::Day) {
			return format_day_precision_datetime(*dt_val);
		}
		return dt_val->to_string();
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
			return format_decimal_value(*dec_val);
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
bv.raw_str = quantity_json_for_bound(val_node, bv.qty_unit);
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
bv.type = dt->is_time ? BoundType::Time : BoundType::DateTime;
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

Optional<BoundValue> BoundValue::from_interval_bound_string(const std::string &str) {
if (str.empty()) {
return NullOpt<BoundValue>();
}
if (str[0] != '{' && looks_temporal_interval_bound(str)) {
auto dt = DateTimeValue::parse(str);
if (dt) {
BoundValue bv;
bv.type = dt->is_time ? BoundType::Time : BoundType::DateTime;
bv.dt_val = dt;
bv.raw_str = str;
return Optional<BoundValue>(bv);
}
}
return BoundValue::from_string(str);
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
bv.raw_str = format_decimal_value(val);
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
return BoundValue::from_interval_bound_string(yyjson_get_str(val));
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
bv.raw_str = quantity_json_for_bound(v, bv.qty_unit);
return Optional<BoundValue>(bv);
}
}
return NullOpt<BoundValue>();
}

static int interval_precision_rank(DateTimeValue::Precision precision) {
	switch (precision) {
	case DateTimeValue::Precision::Year:
		return 0;
	case DateTimeValue::Precision::Month:
		return 1;
	case DateTimeValue::Precision::Day:
		return 2;
	case DateTimeValue::Precision::Hour:
		return 3;
	case DateTimeValue::Precision::Minute:
		return 4;
	case DateTimeValue::Precision::Second:
		return 5;
	case DateTimeValue::Precision::Millisecond:
		return 6;
	}
	return 6;
}

static DateTimeValue::Precision interval_precision_from_rank(int rank) {
	switch (rank) {
	case 0:
		return DateTimeValue::Precision::Year;
	case 1:
		return DateTimeValue::Precision::Month;
	case 2:
		return DateTimeValue::Precision::Day;
	case 3:
		return DateTimeValue::Precision::Hour;
	case 4:
		return DateTimeValue::Precision::Minute;
	case 5:
		return DateTimeValue::Precision::Second;
	default:
		return DateTimeValue::Precision::Millisecond;
	}
}

static Optional<int> compare_interval_order_nullable(const BoundValue &left, const BoundValue &right) {
	if ((left.type == BoundType::DateTime || left.type == BoundType::Time) &&
	    left.type == right.type && left.dt_val && right.dt_val) {
		int left_rank = interval_precision_rank(left.dt_val->precision);
		int right_rank = interval_precision_rank(right.dt_val->precision);
		DateTimeValue::Precision coarsest = interval_precision_from_rank(std::min(left_rank, right_rank));
		int cmp = left.dt_val->compare_at_precision(*right.dt_val, coarsest);
		if (cmp != 0) {
			return Optional<int>(cmp);
		}
		if (left_rank != right_rank) {
			return NullOpt<int>();
		}
		return Optional<int>(0);
	}

	int cmp = left.compare(right);
	if (cmp == -2) {
		return NullOpt<int>();
	}
	return Optional<int>(cmp);
}

static cql::DateTimeValue AddDaysForInterval(const cql::DateTimeValue &dt, int64_t days) {
	int64_t jdn = dt.to_julian_day() + days;

	int64_t l = jdn + 68569;
	int64_t n = (4 * l) / 146097;
	l = l - (146097 * n + 3) / 4;
	int64_t i = (4000 * (l + 1)) / 1461001;
	l = l - (1461 * i) / 4 + 31;
	int64_t j = (80 * l) / 2447;
	int32_t day = static_cast<int32_t>(l - (2447 * j) / 80);
	l = j / 11;
	int32_t month = static_cast<int32_t>(j + 2 - 12 * l);
	int32_t year = static_cast<int32_t>(100 * (n - 49) + i + l);

	cql::DateTimeValue result = dt;
	result.year = year;
	result.month = month;
	result.day = day;
	return result;
}

static bool IsLeapYearForInterval(int32_t year) {
	return (year % 4 == 0) && (year % 100 != 0 || year % 400 == 0);
}

static int32_t DaysInMonthForInterval(int32_t year, int32_t month) {
	static const int32_t dim[] = {0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31};
	if (month < 1 || month > 12) {
		return 0;
	}
	if (month == 2 && IsLeapYearForInterval(year)) {
		return 29;
	}
	return dim[month];
}

static cql::DateTimeValue AddMonthsForInterval(const cql::DateTimeValue &dt, int32_t months) {
	cql::DateTimeValue result = dt;
	int32_t m = dt.month - 1 + months;
	if (m >= 0) {
		result.year = dt.year + m / 12;
		result.month = (m % 12) + 1;
	} else {
		int32_t abs_m = -m;
		int32_t years_back = (abs_m + 11) / 12;
		result.year = dt.year - years_back;
		result.month = 12 - ((abs_m - 1) % 12);
	}
	int32_t max_day = DaysInMonthForInterval(result.year, result.month);
	if (max_day > 0 && result.day > max_day) {
		result.day = max_day;
	}
	return result;
}

static cql::DateTimeValue AddMillisecondsForInterval(const cql::DateTimeValue &dt, int64_t millis) {
	static const int64_t MS_PER_SECOND = 1000;
	static const int64_t MS_PER_MINUTE = 60 * MS_PER_SECOND;
	static const int64_t MS_PER_HOUR = 60 * MS_PER_MINUTE;
	static const int64_t MS_PER_DAY = 24 * MS_PER_HOUR;

	int64_t epoch_ms = dt.to_epoch_millis() + millis;
	int64_t unix_jdn = 2440588LL;

	int64_t total_days = epoch_ms / MS_PER_DAY;
	int64_t remainder_ms = epoch_ms % MS_PER_DAY;
	if (remainder_ms < 0) {
		total_days -= 1;
		remainder_ms += MS_PER_DAY;
	}

	cql::DateTimeValue result = AddDaysForInterval(dt, total_days + unix_jdn - dt.to_julian_day());
	result.hour = static_cast<int32_t>(remainder_ms / MS_PER_HOUR);
	remainder_ms %= MS_PER_HOUR;
	result.minute = static_cast<int32_t>(remainder_ms / MS_PER_MINUTE);
	remainder_ms %= MS_PER_MINUTE;
	result.second = static_cast<int32_t>(remainder_ms / MS_PER_SECOND);
	result.millisecond = static_cast<int32_t>(remainder_ms % MS_PER_SECOND);
	return result;
}

static cql::DateTimeValue StepDateTimeForIntervalPrecision(const cql::DateTimeValue &dt, int direction) {
	switch (dt.precision) {
	case cql::DateTimeValue::Precision::Year:
		return AddMonthsForInterval(dt, 12 * direction);
	case cql::DateTimeValue::Precision::Month:
		return AddMonthsForInterval(dt, direction);
	case cql::DateTimeValue::Precision::Day:
		return AddDaysForInterval(dt, direction);
	case cql::DateTimeValue::Precision::Hour:
		return AddMillisecondsForInterval(dt, static_cast<int64_t>(direction) * 60 * 60 * 1000);
	case cql::DateTimeValue::Precision::Minute:
		return AddMillisecondsForInterval(dt, static_cast<int64_t>(direction) * 60 * 1000);
	case cql::DateTimeValue::Precision::Second:
		return AddMillisecondsForInterval(dt, static_cast<int64_t>(direction) * 1000);
	case cql::DateTimeValue::Precision::Millisecond:
		return AddMillisecondsForInterval(dt, direction);
	}
	return AddMillisecondsForInterval(dt, direction);
}

static Optional<BoundValue> successor_bound(const BoundValue &value) {
	BoundValue result = value;
	switch (value.type) {
	case BoundType::Integer:
		if (!value.int_val || *value.int_val == std::numeric_limits<int64_t>::max()) {
			return NullOpt<BoundValue>();
		}
		result.int_val = Optional<int64_t>(*value.int_val + 1);
		result.raw_str = std::to_string(*result.int_val);
		return Optional<BoundValue>(result);
	case BoundType::Decimal:
		if (!value.dec_val) {
			return NullOpt<BoundValue>();
		}
		result.dec_val = Optional<double>(*value.dec_val + 1e-8);
		result.raw_str = format_decimal_value(*result.dec_val);
		return Optional<BoundValue>(result);
	case BoundType::Quantity:
		if (!value.qty_numeric) {
			return NullOpt<BoundValue>();
		}
		result.qty_numeric = Optional<double>(*value.qty_numeric + 1e-8);
		{
			std::ostringstream oss;
			oss << "{\"value\":" << format_decimal_value(*result.qty_numeric) << ",\"unit\":\""
			    << escapeJsonString(value.qty_unit) << "\"}";
			result.raw_str = oss.str();
		}
		return Optional<BoundValue>(result);
	case BoundType::DateTime:
	case BoundType::Time:
		if (!value.dt_val) {
			return NullOpt<BoundValue>();
		}
		bool day_precision_datetime = is_day_precision_datetime_marker(value.raw_str);
		result.dt_val = Optional<DateTimeValue>(StepDateTimeForIntervalPrecision(*value.dt_val, 1));
		if (result.dt_val->year > 9999) {
			return NullOpt<BoundValue>();
		}
		result.raw_str = day_precision_datetime ? format_day_precision_datetime(*result.dt_val)
		                                        : result.dt_val->to_string();
		return Optional<BoundValue>(result);
	}
	return NullOpt<BoundValue>();
}

static Optional<BoundValue> predecessor_bound(const BoundValue &value) {
	BoundValue result = value;
	switch (value.type) {
	case BoundType::Integer:
		if (!value.int_val || *value.int_val == std::numeric_limits<int64_t>::min()) {
			return NullOpt<BoundValue>();
		}
		result.int_val = Optional<int64_t>(*value.int_val - 1);
		result.raw_str = std::to_string(*result.int_val);
		return Optional<BoundValue>(result);
	case BoundType::Decimal:
		if (!value.dec_val) {
			return NullOpt<BoundValue>();
		}
		result.dec_val = Optional<double>(*value.dec_val - 1e-8);
		result.raw_str = format_decimal_value(*result.dec_val);
		return Optional<BoundValue>(result);
	case BoundType::Quantity:
		if (!value.qty_numeric) {
			return NullOpt<BoundValue>();
		}
		result.qty_numeric = Optional<double>(*value.qty_numeric - 1e-8);
		{
			std::ostringstream oss;
			oss << "{\"value\":" << format_decimal_value(*result.qty_numeric) << ",\"unit\":\""
			    << escapeJsonString(value.qty_unit) << "\"}";
			result.raw_str = oss.str();
		}
		return Optional<BoundValue>(result);
	case BoundType::DateTime:
	case BoundType::Time:
		if (!value.dt_val) {
			return NullOpt<BoundValue>();
		}
		bool day_precision_datetime = is_day_precision_datetime_marker(value.raw_str);
		result.dt_val = Optional<DateTimeValue>(StepDateTimeForIntervalPrecision(*value.dt_val, -1));
		if (result.dt_val->year < 1 || result.dt_val->year > 9999) {
			return NullOpt<BoundValue>();
		}
		result.raw_str = day_precision_datetime ? format_day_precision_datetime(*result.dt_val)
		                                        : result.dt_val->to_string();
		return Optional<BoundValue>(result);
	}
	return NullOpt<BoundValue>();
}

static Optional<BoundValue> effective_start_bound(const Interval &iv) {
	if (!iv.low) {
		return NullOpt<BoundValue>();
	}
	return iv.low_closed ? iv.low : successor_bound(*iv.low);
}

static Optional<BoundValue> effective_end_bound(const Interval &iv) {
	if (!iv.high) {
		return NullOpt<BoundValue>();
	}
	return iv.high_closed ? iv.high : predecessor_bound(*iv.high);
}

static bool effective_interval_empty(const Interval &iv) {
	auto start = effective_start_bound(iv);
	auto end = effective_end_bound(iv);
	if (start && end) {
		int cmp = start->compare(*end);
		return cmp == -2 || cmp > 0;
	}
	return false;
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
auto this_start = effective_start_bound(*this);
auto this_end = effective_end_bound(*this);
auto other_start = effective_start_bound(other);
auto other_end = effective_end_bound(other);
if (!other_start && this_start) {
return false;
}
if (other_start && this_start) {
int cmp = this_start->compare(*other_start);
if (cmp == -2 || cmp > 0) return false;
}
if (!other_end && this_end) {
return false;
}
if (other_end && this_end) {
int cmp = this_end->compare(*other_end);
if (cmp == -2 || cmp < 0) return false;
}
return !effective_interval_empty(other);
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
auto a_start = effective_start_bound(a);
auto a_end = effective_end_bound(a);
auto b_start = effective_start_bound(b);
auto b_end = effective_end_bound(b);
bool low_eq = false;
if (!a_start && !b_start) {
low_eq = true;
} else if (a_start && b_start) {
low_eq = (a_start->compare(*b_start) == 0);
}
bool high_eq = false;
if (!a_end && !b_end) {
high_eq = true;
} else if (a_end && b_end) {
high_eq = (a_end->compare(*b_end) == 0);
}
return low_eq && high_eq;
}

bool Interval::overlaps(const Interval &other) const {
if (effective_interval_empty(*this) || effective_interval_empty(other)) {
return false;
}
auto this_start = effective_start_bound(*this);
auto this_end = effective_end_bound(*this);
auto other_start = effective_start_bound(other);
auto other_end = effective_end_bound(other);
if (this_start && other_end) {
int cmp = other_end->compare(*this_start);
if (cmp == -2 || cmp < 0) return false;
}
if (this_end && other_start) {
int cmp = this_end->compare(*other_start);
if (cmp == -2 || cmp < 0) return false;
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
	auto this_end = effective_end_bound(*this);
	auto other_start = effective_start_bound(other);
	if (!this_end || !other_start) {
	return false;
	}
	auto successor = successor_bound(*this_end);
	return successor && successor->compare(*other_start) == 0;
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
if (!overlaps(other)) {
return false;
}
auto this_start = effective_start_bound(*this);
auto other_start = effective_start_bound(other);
if (!this_start && other_start) return true;
if (this_start && !other_start) return false;
if (!this_start && !other_start) return false;
int cmp = this_start->compare(*other_start);
return cmp != -2 && cmp < 0;
}

bool Interval::overlaps_after(const Interval &other) const {
if (!overlaps(other)) {
return false;
}
auto this_end = effective_end_bound(*this);
auto other_end = effective_end_bound(other);
if (!this_end && other_end) return true;
if (this_end && !other_end) return false;
if (!this_end && !other_end) return false;
int cmp = this_end->compare(*other_end);
return cmp != -2 && cmp > 0;
}

bool Interval::starts_same(const Interval &other) const {
auto this_start = effective_start_bound(*this);
auto other_start = effective_start_bound(other);
if (!this_start || !other_start) {
return false;
}
if (this_start->compare(*other_start) != 0) {
return false;
}
auto this_end = effective_end_bound(*this);
auto other_end = effective_end_bound(other);
if (!this_end || !other_end) {
return false;
}
int cmp = this_end->compare(*other_end);
return cmp != -2 && cmp <= 0;
}

bool Interval::ends_same(const Interval &other) const {
auto this_end = effective_end_bound(*this);
auto other_end = effective_end_bound(other);
if (!this_end || !other_end) {
return false;
}
if (this_end->compare(*other_end) != 0) {
return false;
}
auto this_start = effective_start_bound(*this);
auto other_start = effective_start_bound(other);
if (!this_start || !other_start) {
return false;
}
int cmp = this_start->compare(*other_start);
return cmp != -2 && cmp >= 0;
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
auto start = effective_start_bound(*this);
auto end = effective_end_bound(*this);
if (!start || !end) {
return NullOpt<std::string>();
}
switch (bound_type) {
case BoundType::Integer:
if (start->int_val && end->int_val) {
std::ostringstream oss;
oss << (*end->int_val - *start->int_val);
return Optional<std::string>(oss.str());
}
break;
case BoundType::Decimal:
if (start->dec_val && end->dec_val) {
return Optional<std::string>(format_decimal_value(*end->dec_val - *start->dec_val));
}
break;
case BoundType::Quantity:
{
auto start_q = parse_quantity_json(start->raw_str);
auto end_converted = quantity_convert(end->raw_str, start->qty_unit);
auto end_q = end_converted ? parse_quantity_json(*end_converted) : NullOpt<ParsedQuantity>();
if (start_q && end_q) {
	return format_quantity_json({end_q->value - start_q->value, start->qty_unit, start_q->system});
}
}
break;
case BoundType::DateTime:
if (start->dt_val && end->dt_val) {
std::ostringstream oss;
oss << (end->dt_val->to_julian_day() - start->dt_val->to_julian_day());
return Optional<std::string>(oss.str());
}
break;
case BoundType::Time:
break;
}
return NullOpt<std::string>();
}

Optional<std::string> Interval::size_string() const {
auto start = effective_start_bound(*this);
auto end = effective_end_bound(*this);
if (!start || !end) {
return NullOpt<std::string>();
}
switch (bound_type) {
case BoundType::Integer:
if (start->int_val && end->int_val) {
	int64_t size = *end->int_val - *start->int_val + 1;
	return Optional<std::string>(std::to_string(size < 0 ? 0 : size));
}
break;
case BoundType::Decimal:
if (start->dec_val && end->dec_val) {
	return Optional<std::string>(format_decimal_value(*end->dec_val - *start->dec_val + 1e-8));
}
break;
case BoundType::Quantity:
{
auto start_q = parse_quantity_json(start->raw_str);
auto end_converted = quantity_convert(end->raw_str, start->qty_unit);
auto end_q = end_converted ? parse_quantity_json(*end_converted) : NullOpt<ParsedQuantity>();
if (start_q && end_q) {
	return format_quantity_json({end_q->value - start_q->value + 1e-8, start->qty_unit, start_q->system});
}
}
break;
case BoundType::DateTime:
case BoundType::Time:
break;
}
return NullOpt<std::string>();
}

std::string Interval::start_string() const {
auto start = effective_start_bound(*this);
return start ? start->to_string() : "";
}

std::string Interval::end_string() const {
auto end = effective_end_bound(*this);
return end ? end->to_string() : "";
}

static void append_bound_json(std::ostringstream &oss, const char *key, const Optional<BoundValue> &bound) {
oss << "\"" << key << "\": ";
if (!bound) {
oss << "null";
return;
}
std::string s = bound->to_string();
if (bound->type == BoundType::Quantity && !s.empty() && s[0] == '{') {
oss << s;
} else {
oss << "\"" << escapeJsonString(s) << "\"";
}
}

std::string Interval::to_json() const {
std::ostringstream oss;
oss << "{";
append_bound_json(oss, "low", low);
oss << ", ";
append_bound_json(oss, "high", high);
oss << ", \"lowClosed\": " << (low_closed ? "true" : "false");
oss << ", \"highClosed\": " << (high_closed ? "true" : "false");
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
	auto a_start = effective_start_bound(a);
	auto b_end = effective_end_bound(b);
	if (!a_start || !b_end) return NullOpt<bool>();
	auto cmp = compare_interval_order_nullable(*a_start, *b_end);
	if (!cmp) return NullOpt<bool>();
	return Optional<bool>(*cmp >= 0);
}

Optional<bool> Interval::on_or_before(const Interval &a, const Interval &b) {
	auto a_end = effective_end_bound(a);
	auto b_start = effective_start_bound(b);
	if (!a_end || !b_start) return NullOpt<bool>();
	auto cmp = compare_interval_order_nullable(*a_end, *b_start);
	if (!cmp) return NullOpt<bool>();
	return Optional<bool>(*cmp <= 0);
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
if (a.low_closed) {
result.low = b.low;
result.low_closed = b.low_closed;
} else {
result.low = NullOpt<BoundValue>();
result.low_closed = a.low_closed;
}
} else if (!b.low) {
if (b.low_closed) {
result.low = a.low;
result.low_closed = a.low_closed;
} else {
result.low = NullOpt<BoundValue>();
result.low_closed = b.low_closed;
}
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
	result.high = NullOpt<BoundValue>();
	result.high_closed = a.high_closed && b.high_closed;
	} else if (!a.high) {
	if (a.high_closed) {
	result.high = b.high;
	result.high_closed = b.high_closed;
	} else {
	result.high = NullOpt<BoundValue>();
	result.high_closed = a.high_closed;
	}
	} else if (!b.high) {
	if (b.high_closed) {
	result.high = a.high;
	result.high_closed = a.high_closed;
	} else {
	result.high = NullOpt<BoundValue>();
	result.high_closed = b.high_closed;
	}
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
auto a_start = effective_start_bound(a);
auto b_start = effective_start_bound(b);
auto a_end = effective_end_bound(a);
auto b_end = effective_end_bound(b);

// Min of effective starts
if (!a_start) {
result.low_closed = a.low_closed;
} else if (!b_start) {
result.low_closed = b.low_closed;
} else {
int cmp = a_start->compare(*b_start);
if (cmp == -2) return NullOpt<Interval>();
if (cmp < 0) {
result.low = a_start;
result.low_closed = true;
} else if (cmp > 0) {
result.low = b_start;
result.low_closed = true;
} else {
result.low = a_start;
result.low_closed = true;
}
}

// Max of effective ends
if (!a_end) {
result.high_closed = a.high_closed;
} else if (!b_end) {
result.high_closed = b.high_closed;
} else {
int cmp = a_end->compare(*b_end);
if (cmp == -2) return NullOpt<Interval>();
if (cmp > 0) {
result.high = a_end;
result.high_closed = true;
} else if (cmp < 0) {
result.high = b_end;
result.high_closed = true;
} else {
result.high = a_end;
result.high_closed = true;
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
if (b.low_closed && b.low) {
auto pred = predecessor_bound(*b.low);
if (!pred) return NullOpt<Interval>();
result.high = pred;
} else {
result.high = b.low;
}
result.high_closed = true;
return Optional<Interval>(result);
}

if (has_right) {
if (b.high_closed && b.high) {
auto succ = successor_bound(*b.high);
if (!succ) return NullOpt<Interval>();
result.low = succ;
} else {
result.low = b.high;
}
result.low_closed = true;
result.high = a.high;
result.high_closed = a.high_closed;
return Optional<Interval>(result);
}

return NullOpt<Interval>();
}

// =====================================================================
// Precision-aware interval comparisons
// =====================================================================

Optional<DateTimeValue::Precision> precision_from_string(const std::string &s) {
if (s == "year") return DateTimeValue::Precision::Year;
if (s == "month") return DateTimeValue::Precision::Month;
if (s == "day") return DateTimeValue::Precision::Day;
if (s == "hour") return DateTimeValue::Precision::Hour;
if (s == "minute") return DateTimeValue::Precision::Minute;
if (s == "second") return DateTimeValue::Precision::Second;
if (s == "millisecond") return DateTimeValue::Precision::Millisecond;
return NullOpt<DateTimeValue::Precision>();
}

bool Interval::overlaps(const Interval &other, DateTimeValue::Precision prec) const {
if (low && other.high) {
int cmp = other.high->compare_at_prec(*low, prec);
if (cmp == -2) return false;
if (cmp < 0) return false;
if (cmp == 0 && (!other.high_closed || !low_closed)) return false;
}
if (high && other.low) {
int cmp = high->compare_at_prec(*other.low, prec);
if (cmp == -2) return false;
if (cmp < 0) return false;
if (cmp == 0 && (!high_closed || !other.low_closed)) return false;
}
return true;
}

bool Interval::contains_point(const BoundValue &point, DateTimeValue::Precision prec) const {
if (low) {
int cmp = low->compare_at_prec(point, prec);
if (cmp == -2) return false;
if (cmp > 0) return false;
if (cmp == 0 && !low_closed) return false;
}
if (high) {
int cmp = high->compare_at_prec(point, prec);
if (cmp == -2) return false;
if (cmp < 0) return false;
if (cmp == 0 && !high_closed) return false;
}
return true;
}

bool Interval::contains_interval(const Interval &other, DateTimeValue::Precision prec) const {
if (!other.low && low) return false;
if (other.low && !contains_point(*other.low, prec)) return false;
if (!other.high && high) return false;
if (other.high && !contains_point(*other.high, prec)) return false;
return true;
}

bool Interval::includes(const Interval &other, DateTimeValue::Precision prec) const {
return contains_interval(other, prec);
}

bool Interval::before(const Interval &other, DateTimeValue::Precision prec) const {
if (!high || !other.low) return false;
int cmp = high->compare_at_prec(*other.low, prec);
if (cmp == -2) return false;
if (high_closed && other.low_closed) return cmp < 0;
return cmp <= 0;
}

bool Interval::after(const Interval &other, DateTimeValue::Precision prec) const {
return other.before(*this, prec);
}

bool Interval::overlaps_before(const Interval &other, DateTimeValue::Precision prec) const {
if (!low || !other.low) return false;
int low_cmp = low->compare_at_prec(*other.low, prec);
if (low_cmp == -2) return false;
if (!high) return low_cmp < 0;
int high_cmp = high->compare_at_prec(*other.low, prec);
if (high_cmp == -2) return false;
if (high_cmp == 0) return low_cmp < 0 && high_closed && other.low_closed;
return low_cmp < 0 && high_cmp > 0;
}

bool Interval::overlaps_after(const Interval &other, DateTimeValue::Precision prec) const {
return other.overlaps_before(*this, prec);
}

} // namespace cql
