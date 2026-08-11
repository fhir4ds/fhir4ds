#include "cql/boundary.hpp"
#include "cql/datetime.hpp"
#include "cql/quantity.hpp"
#include <cstdlib>
#include <cmath>
#include <sstream>
#include <algorithm>
#include <cstring>
#include <cctype>
#include <iomanip>

namespace cql {

// =====================================================================
// Helper: detect value type
// =====================================================================
enum class ValueKind { DateTime, Date, Time, Numeric, Unknown };

static ValueKind detect_kind(const std::string &s) {
	if (s.empty()) return ValueKind::Unknown;
	// Time: starts with T and digit, or HH:MM pattern without dashes
	if ((s[0] == 'T' && s.size() >= 3 && s[1] >= '0' && s[1] <= '9') ||
	    (s.size() >= 5 && s[2] == ':' && s[0] >= '0' && s[0] <= '9')) {
		return ValueKind::Time;
	}
	if ((s.size() == 5 && s[4] == 'T') || (s.size() == 8 && s[4] == '-' && s[7] == 'T')) {
		return ValueKind::DateTime;
	}
	// Date/DateTime: has dashes in date-like position
	if (s.size() >= 10 && s[4] == '-') {
		if (s.find('T') != std::string::npos || s.find(' ') != std::string::npos) {
			return ValueKind::DateTime;
		}
		return ValueKind::Date;
	}
	// Year-only: 4 digits
	if (s.size() == 4 &&
	    std::isdigit(static_cast<unsigned char>(s[0])) &&
	    std::isdigit(static_cast<unsigned char>(s[1])) &&
	    std::isdigit(static_cast<unsigned char>(s[2])) &&
	    std::isdigit(static_cast<unsigned char>(s[3]))) {
		return ValueKind::Date;
	}
	// Year-month: YYYY-MM
	if (s.size() == 7 && s[4] == '-') {
		return ValueKind::Date;
	}
	// Numeric
	char *end = NULL;
	double parsed = std::strtod(s.c_str(), &end);
	if (end != s.c_str() && *end == '\0' && std::isfinite(parsed)) {
		return ValueKind::Numeric;
	}
	return ValueKind::Unknown;
}

static Optional<bool> quantity_value_uses_decimal_step(const std::string &json) {
	size_t key = json.find("\"value\"");
	if (key == std::string::npos) return NullOpt<bool>();
	size_t colon = json.find(':', key);
	if (colon == std::string::npos) return NullOpt<bool>();
	size_t pos = colon + 1;
	while (pos < json.size() && std::isspace(static_cast<unsigned char>(json[pos]))) {
		pos++;
	}
	if (pos >= json.size()) return NullOpt<bool>();
	if (json[pos] == '"') return NullOpt<bool>();
	if (json[pos] == '-' || json[pos] == '+') {
		pos++;
	}
	bool saw_digit = false;
	while (pos < json.size() && std::isdigit(static_cast<unsigned char>(json[pos]))) {
		saw_digit = true;
		pos++;
	}
	bool decimal_step = false;
	if (pos < json.size() && json[pos] == '.') {
		decimal_step = true;
		pos++;
		while (pos < json.size() && std::isdigit(static_cast<unsigned char>(json[pos]))) {
			saw_digit = true;
			pos++;
		}
	}
	if (!saw_digit) return NullOpt<bool>();
	if (pos < json.size() && (json[pos] == 'e' || json[pos] == 'E')) {
		decimal_step = true;
		pos++;
		if (pos < json.size() && (json[pos] == '-' || json[pos] == '+')) {
			pos++;
		}
		bool saw_exp_digit = false;
		while (pos < json.size() && std::isdigit(static_cast<unsigned char>(json[pos]))) {
			saw_exp_digit = true;
			pos++;
		}
		if (!saw_exp_digit) return NullOpt<bool>();
	}
	return Optional<bool>(decimal_step);
}

static Optional<std::string> step_quantity_json(const std::string &value, int direction) {
	auto decimal_step = quantity_value_uses_decimal_step(value);
	if (!decimal_step) return NullOpt<std::string>();
	auto q = parse_quantity_json(value);
	if (!q) return NullOpt<std::string>();
	q->value += direction * (decimal_step.value() ? 0.00000001 : 1.0);
	if (q->code.empty()) {
		q->code = "1";
	}
	auto formatted = format_quantity_json(*q);
	return formatted ? formatted : NullOpt<std::string>();
}

Optional<int64_t> default_boundary_precision(const std::string &value) {
	if (value.empty()) return NullOpt<int64_t>();
	auto kind = detect_kind(value);
	if (kind == ValueKind::Numeric) return Optional<int64_t>(8);
	if (kind == ValueKind::Time) return Optional<int64_t>(9);
	if (kind == ValueKind::DateTime) return Optional<int64_t>(17);
	if (kind == ValueKind::Date) {
		auto precision = cql_precision(value);
		if (!precision) return NullOpt<int64_t>();
		return precision;
	}
	return NullOpt<int64_t>();
}

// =====================================================================
// Helper: parse time string to components
// =====================================================================
struct TimeComponents {
	int h, m, s, ms;
	std::string suffix;
};

static TimeComponents parse_time_components(const std::string &s) {
	TimeComponents tc = {0, 0, 0, 0, ""};
	std::string ts = s;
	if (!ts.empty() && ts[0] == 'T') ts = ts.substr(1);
	if (!ts.empty() && ts[ts.size() - 1] == 'Z') {
		tc.suffix = "Z";
		ts = ts.substr(0, ts.size() - 1);
	} else {
		size_t tz_pos = std::string::npos;
		for (size_t j = 1; j < ts.size(); j++) {
			if (ts[j] == '+' || ts[j] == '-') {
				tz_pos = j;
				break;
			}
		}
		if (tz_pos != std::string::npos) {
			tc.suffix = ts.substr(tz_pos);
			ts = ts.substr(0, tz_pos);
		}
	}

	// Parse HH
	tc.h = std::atoi(ts.c_str());
	size_t pos = ts.find(':');
	if (pos == std::string::npos) return tc;
	ts = ts.substr(pos + 1);

	// Parse MM
	tc.m = std::atoi(ts.c_str());
	pos = ts.find(':');
	if (pos == std::string::npos) return tc;
	ts = ts.substr(pos + 1);

	// Parse SS.mmm
	size_t dot = ts.find('.');
	if (dot != std::string::npos) {
		tc.s = std::atoi(ts.substr(0, dot).c_str());
		std::string frac = ts.substr(dot + 1);
		while (frac.size() < 3) frac += "0";
		tc.ms = std::atoi(frac.substr(0, 3).c_str());
	} else {
		tc.s = std::atoi(ts.c_str());
	}
	return tc;
}

static std::string format_time(int h, int m, int s, int ms, const std::string &suffix = "") {
	std::ostringstream oss;
	oss << "T";
	if (h < 10) oss << "0";
	oss << h << ":";
	if (m < 10) oss << "0";
	oss << m << ":";
	if (s < 10) oss << "0";
	oss << s << ".";
	if (ms < 10) oss << "00";
	else if (ms < 100) oss << "0";
	oss << ms;
	oss << suffix;
	return oss.str();
}

static std::string strip_time_suffix(std::string ts) {
	if (!ts.empty() && ts[0] == 'T') ts = ts.substr(1);
	if (!ts.empty() && ts[ts.size() - 1] == 'Z') {
		return ts.substr(0, ts.size() - 1);
	}
	for (size_t j = 1; j < ts.size(); j++) {
		if (ts[j] == '+' || ts[j] == '-') {
			return ts.substr(0, j);
		}
	}
	return ts;
}

static std::string strip_datetime_timezone_for_precision(const std::string &value) {
	size_t sep = value.find('T');
	if (sep == std::string::npos) sep = value.find(' ');
	if (sep == std::string::npos) return value;
	if (!value.empty() && value[value.size() - 1] == 'Z') {
		return value.substr(0, value.size() - 1);
	}
	for (size_t j = sep + 1; j < value.size(); j++) {
		if (value[j] == '+' || value[j] == '-') {
			return value.substr(0, j);
		}
	}
	return value;
}

static bool all_digits(const std::string &s) {
	if (s.empty()) return false;
	for (char ch : s) {
		if (!std::isdigit(static_cast<unsigned char>(ch))) return false;
	}
	return true;
}

static std::string normalize_numeric_text(const std::string &value) {
	if (value.find('e') == std::string::npos && value.find('E') == std::string::npos) {
		return value;
	}
	char *end = NULL;
	double parsed = std::strtod(value.c_str(), &end);
	if (end == value.c_str() || *end != '\0' || std::isinf(parsed) || std::isnan(parsed)) {
		return value;
	}
	std::ostringstream oss;
	oss << std::fixed << std::setprecision(12) << parsed;
	std::string out = oss.str();
	while (out.size() > 1 && out.back() == '0') out.pop_back();
	if (!out.empty() && out.back() == '.') out.pop_back();
	if (out == "-0") out = "0";
	return out;
}

static int compare_decimal_abs_to_cql_max(std::string value) {
	if (!value.empty() && (value[0] == '+' || value[0] == '-')) {
		value = value.substr(1);
	}
	if (value.find('e') != std::string::npos || value.find('E') != std::string::npos) {
		char *end = NULL;
		long double parsed = std::strtold(value.c_str(), &end);
		if (end == value.c_str() || *end != '\0') return 1;
		long double max_value = 1.0e20L;
		if (parsed < max_value) return -1;
		if (parsed > max_value) return 1;
		return 0;
	}

	std::string int_part = value;
	std::string frac_part;
	size_t dot = value.find('.');
	if (dot != std::string::npos) {
		int_part = value.substr(0, dot);
		frac_part = value.substr(dot + 1);
	}
	size_t first_non_zero = int_part.find_first_not_of('0');
	if (first_non_zero == std::string::npos) {
		int_part = "0";
	} else {
		int_part = int_part.substr(first_non_zero);
	}
	while (frac_part.size() < 8) frac_part += "0";
	if (frac_part.size() > 8) frac_part = frac_part.substr(0, 8);

	static const std::string max_int = "99999999999999999999";
	static const std::string max_frac = "99999999";
	if (int_part.size() != max_int.size()) {
		return int_part.size() < max_int.size() ? -1 : 1;
	}
	if (int_part != max_int) {
		return int_part < max_int ? -1 : 1;
	}
	if (frac_part == max_frac) return 0;
	return frac_part < max_frac ? -1 : 1;
}

static bool decimal_step_overflows(const std::string &value, int direction) {
	if (value.empty()) return true;
	bool negative = value[0] == '-';
	int cmp = compare_decimal_abs_to_cql_max(value);
	if (cmp > 0) return true;
	if ((value.find('e') != std::string::npos || value.find('E') != std::string::npos) && cmp >= 0) return true;
	if (direction > 0 && !negative && cmp == 0) return true;
	if (direction < 0 && negative && cmp == 0) return true;
	return false;
}

static bool valid_timezone_suffix(const std::string &suffix) {
	if (suffix.empty() || suffix == "Z") return true;
	if (suffix.size() != 6 || suffix[3] != ':') return false;
	if (suffix[0] != '+' && suffix[0] != '-') return false;
	std::string digits;
	for (size_t i = 1; i < suffix.size(); i++) {
		if (suffix[i] == ':') continue;
		if (!std::isdigit(static_cast<unsigned char>(suffix[i]))) return false;
		digits += suffix[i];
	}
	if (digits.size() != 4) return false;
	int hours = std::atoi(digits.substr(0, 2).c_str());
	int minutes = std::atoi(digits.substr(2, 2).c_str());
	return minutes <= 59 && (hours < 14 || (hours == 14 && minutes == 0));
}

static bool parse_int_range(const std::string &text, int min_value, int max_value, int &out) {
	if (!all_digits(text)) return false;
	out = std::atoi(text.c_str());
	return out >= min_value && out <= max_value;
}

static bool validate_time_string(const std::string &value) {
	std::string ts = value;
	if (!ts.empty() && ts[0] == 'T') ts = ts.substr(1);
	std::string suffix;
	if (!ts.empty() && ts[ts.size() - 1] == 'Z') {
		suffix = "Z";
		ts = ts.substr(0, ts.size() - 1);
	} else {
		for (size_t j = 1; j < ts.size(); j++) {
			if (ts[j] == '+' || ts[j] == '-') {
				suffix = ts.substr(j);
				ts = ts.substr(0, j);
				break;
			}
		}
	}
	if (!valid_timezone_suffix(suffix) || ts.empty()) return false;

	size_t first = ts.find(':');
	std::string hour_text = first == std::string::npos ? ts : ts.substr(0, first);
	int component = 0;
	if (!parse_int_range(hour_text, 0, 23, component)) return false;
	if (first == std::string::npos) return true;

	size_t second = ts.find(':', first + 1);
	std::string minute_text = second == std::string::npos
		? ts.substr(first + 1)
		: ts.substr(first + 1, second - first - 1);
	if (!parse_int_range(minute_text, 0, 59, component)) return false;
	if (second == std::string::npos) return true;

	std::string second_text = ts.substr(second + 1);
	size_t dot = second_text.find('.');
	std::string whole_second = dot == std::string::npos ? second_text : second_text.substr(0, dot);
	if (!parse_int_range(whole_second, 0, 59, component)) return false;
	if (dot != std::string::npos) {
		std::string frac = second_text.substr(dot + 1);
		if (frac.empty() || frac.size() > 3 || !all_digits(frac)) return false;
	}
	return true;
}

static bool validate_dt_lexical_shape(const std::string &value) {
	std::string body = value;
	size_t sep = body.find('T');
	if (sep == std::string::npos) sep = body.find(' ');

	std::string suffix;
	if (sep != std::string::npos) {
		if (!body.empty() && body[body.size() - 1] == 'Z') {
			suffix = "Z";
			body = body.substr(0, body.size() - 1);
		} else {
			for (size_t j = sep + 1; j < body.size(); j++) {
				if (body[j] == '+' || body[j] == '-') {
					suffix = body.substr(j);
					body = body.substr(0, j);
					break;
				}
			}
		}
	}
	if (!valid_timezone_suffix(suffix)) return false;

	std::string date_part = sep == std::string::npos ? body : body.substr(0, sep);
	if (!(date_part.size() == 4 || date_part.size() == 7 || date_part.size() == 10)) return false;
	if (!all_digits(date_part.substr(0, 4))) return false;
	if (date_part.size() >= 7 && (date_part[4] != '-' || !all_digits(date_part.substr(5, 2)))) return false;
	if (date_part.size() == 10 && (date_part[7] != '-' || !all_digits(date_part.substr(8, 2)))) return false;
	if (sep == std::string::npos) return true;

	std::string time_part = body.substr(sep + 1);
	if (time_part.empty()) return true;
	if (date_part.size() != 10) return false;
	size_t first = time_part.find(':');
	std::string hour_text = first == std::string::npos ? time_part : time_part.substr(0, first);
	if (hour_text.size() != 2 || !all_digits(hour_text)) return false;
	if (first == std::string::npos) return true;
	size_t second = time_part.find(':', first + 1);
	std::string minute_text = second == std::string::npos
		? time_part.substr(first + 1)
		: time_part.substr(first + 1, second - first - 1);
	if (minute_text.size() != 2 || !all_digits(minute_text)) return false;
	if (second == std::string::npos) return true;
	std::string second_text = time_part.substr(second + 1);
	size_t dot = second_text.find('.');
	std::string whole_second = dot == std::string::npos ? second_text : second_text.substr(0, dot);
	if (whole_second.size() != 2 || !all_digits(whole_second)) return false;
	if (dot != std::string::npos) {
		std::string frac = second_text.substr(dot + 1);
		if (frac.empty() || frac.size() > 3 || !all_digits(frac)) return false;
	}
	return true;
}

// =====================================================================
// Helper: days in month
// =====================================================================
static int days_in_month(int year, int month) {
	static const int days[] = {0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31};
	if (month < 1 || month > 12) return 31;
	int d = days[month];
	if (month == 2 && (year % 4 == 0 && (year % 100 != 0 || year % 400 == 0))) {
		d = 29;
	}
	return d;
}

static bool is_day_precision_datetime_marker(const std::string &s) {
	return s.size() == 11 && s[4] == '-' && s[7] == '-' && s[10] == 'T';
}

static std::string format_day_precision_datetime(const DateTimeValue &dt) {
	std::ostringstream oss;
	oss << std::setfill('0') << std::setw(4) << dt.year
	    << "-" << std::setw(2) << dt.month
	    << "-" << std::setw(2) << dt.day << "T";
	return oss.str();
}

static bool add_days_in_place(DateTimeValue &dt, int direction) {
	if (direction > 0) {
		dt.day += 1;
		if (dt.day > days_in_month(dt.year, dt.month)) {
			dt.day = 1;
			dt.month += 1;
			if (dt.month > 12) {
				dt.month = 1;
				dt.year += 1;
			}
		}
		return dt.year <= 9999;
	}

	dt.day -= 1;
	if (dt.day < 1) {
		dt.month -= 1;
		if (dt.month < 1) {
			dt.month = 12;
			dt.year -= 1;
		}
		dt.day = days_in_month(dt.year, dt.month);
	}
	return dt.year >= 1;
}

static bool add_months_in_place(DateTimeValue &dt, int direction) {
	dt.month += direction;
	if (dt.month < 1) {
		dt.month = 12;
		dt.year -= 1;
	} else if (dt.month > 12) {
		dt.month = 1;
		dt.year += 1;
	}
	return dt.year >= 1 && dt.year <= 9999;
}

static bool add_time_millis_in_place(DateTimeValue &dt, int64_t delta_ms) {
	int64_t total_ms = ((static_cast<int64_t>(dt.hour) * 60 + dt.minute) * 60 + dt.second) * 1000 +
	                   dt.millisecond + delta_ms;
	while (total_ms < 0) {
		if (!add_days_in_place(dt, -1)) return false;
		total_ms += 86400000LL;
	}
	while (total_ms > 86399999LL) {
		if (!add_days_in_place(dt, 1)) return false;
		total_ms -= 86400000LL;
	}
	dt.hour = static_cast<int32_t>(total_ms / 3600000LL);
	int64_t rem = total_ms % 3600000LL;
	dt.minute = static_cast<int32_t>(rem / 60000LL);
	rem %= 60000LL;
	dt.second = static_cast<int32_t>(rem / 1000LL);
	dt.millisecond = static_cast<int32_t>(rem % 1000LL);
	return true;
}

static int64_t time_step_for_precision(const std::string &value) {
	std::string ts = strip_time_suffix(value);
	size_t first = ts.find(':');
	if (first == std::string::npos) return 3600000LL;
	size_t second = ts.find(':', first + 1);
	if (second == std::string::npos) return 60000LL;
	if (ts.find('.', second + 1) == std::string::npos) return 1000LL;
	return 1LL;
}

static std::string format_time_for_precision(int h, int m, int s, int ms, int64_t step_ms, const std::string &suffix) {
	std::ostringstream oss;
	oss << "T" << std::setfill('0') << std::setw(2) << h;
	if (step_ms <= 60000LL) {
		oss << ":" << std::setw(2) << m;
	}
	if (step_ms <= 1000LL) {
		oss << ":" << std::setw(2) << s;
	}
	if (step_ms == 1LL) {
		oss << "." << std::setw(3) << ms;
	}
	oss << suffix;
	return oss.str();
}

// =====================================================================
// Helper: extract date/datetime components from string
// =====================================================================
struct DateTimeComponents {
	std::string year, month, day, hour, minute, second, ms;
	bool has_month, has_day, has_time, has_minute, has_second, has_ms;
	std::string suffix;
};

static DateTimeComponents parse_dt_components(const std::string &s) {
	DateTimeComponents c;
	c.has_month = false; c.has_day = false; c.has_time = false;
	c.has_minute = false; c.has_second = false; c.has_ms = false;
	c.suffix = "";

	std::string body = s;
	size_t original_t_pos = body.find('T');
	if (original_t_pos == std::string::npos) original_t_pos = body.find(' ');
	if (original_t_pos != std::string::npos) {
		if (!body.empty() && body[body.size() - 1] == 'Z') {
			c.suffix = "Z";
			body = body.substr(0, body.size() - 1);
		} else {
			for (size_t j = original_t_pos + 1; j < body.size(); j++) {
				if (body[j] == '+' || body[j] == '-') {
					c.suffix = body.substr(j);
					body = body.substr(0, j);
					break;
				}
			}
		}
	}

	c.year = body.substr(0, 4);
	if (body.size() > 5 && body[4] == '-') {
		c.month = body.substr(5, 2);
		c.has_month = true;
	}
	if (body.size() > 8 && body[7] == '-') {
		c.day = body.substr(8, 2);
		c.has_day = true;
	}
	size_t t_pos = body.find('T');
	if (t_pos == std::string::npos) t_pos = body.find(' ');
	if (t_pos != std::string::npos && t_pos + 2 < body.size()) {
		c.has_time = true;
		c.hour = body.substr(t_pos + 1, 2);
		if (t_pos + 5 < body.size() && body[t_pos + 3] == ':') {
			c.minute = body.substr(t_pos + 4, 2);
			c.has_minute = true;
		}
		if (t_pos + 8 < body.size() && body[t_pos + 6] == ':') {
			c.second = body.substr(t_pos + 7, 2);
			c.has_second = true;
		}
		size_t dot = body.find('.', t_pos);
		if (dot != std::string::npos && dot + 1 < body.size()) {
			// Extract up to 3 chars for ms, ignoring timezone
			std::string frac;
			for (size_t i = dot + 1; i < body.size() && frac.size() < 3; i++) {
				if (body[i] >= '0' && body[i] <= '9') frac += body[i];
				else break;
			}
			while (frac.size() < 3) frac += "0";
			c.ms = frac;
			c.has_ms = true;
		}
	}
	return c;
}

static bool validate_dt_components(const DateTimeComponents &c) {
	if (!valid_timezone_suffix(c.suffix)) return false;
	int year = 0;
	if (!parse_int_range(c.year, 1, 9999, year)) return false;
	int month = 1;
	if (c.has_month && !parse_int_range(c.month, 1, 12, month)) return false;
	if (c.has_day) {
		int day = 0;
		if (!parse_int_range(c.day, 1, days_in_month(year, month), day)) return false;
	}
	int component = 0;
	if (c.has_time && !parse_int_range(c.hour, 0, 23, component)) return false;
	if (c.has_minute && !parse_int_range(c.minute, 0, 59, component)) return false;
	if (c.has_second && !parse_int_range(c.second, 0, 59, component)) return false;
	if (c.has_ms && (c.ms.size() > 3 || !all_digits(c.ms))) return false;
	return true;
}

static std::string format_temporal_for_precision(const DateTimeValue &dt, bool is_datetime,
                                                 const DateTimeComponents &c) {
	std::ostringstream oss;
	oss << std::setfill('0') << std::setw(4) << dt.year;
	if (c.has_month) {
		oss << "-" << std::setw(2) << dt.month;
	}
	if (c.has_day) {
		oss << "-" << std::setw(2) << dt.day;
	}
	if (is_datetime) {
		oss << "T";
		if (c.has_time) {
			oss << std::setw(2) << dt.hour;
			if (c.has_minute) {
				oss << ":" << std::setw(2) << dt.minute;
			}
			if (c.has_second) {
				oss << ":" << std::setw(2) << dt.second;
			}
			if (c.has_ms) {
				oss << "." << std::setw(3) << dt.millisecond;
			}
			oss << c.suffix;
		}
	}
	return oss.str();
}

static Optional<std::string> step_date_or_datetime(const std::string &value, int direction, bool is_datetime) {
	if (!validate_dt_lexical_shape(value)) return NullOpt<std::string>();
	auto c = parse_dt_components(value);
	if (!validate_dt_components(c)) return NullOpt<std::string>();
	DateTimeValue dt;
	dt.year = std::atoi(c.year.c_str());
	dt.month = c.has_month ? std::atoi(c.month.c_str()) : 1;
	dt.day = c.has_day ? std::atoi(c.day.c_str()) : 1;
	dt.has_time = c.has_time;
	dt.hour = c.has_time ? std::atoi(c.hour.c_str()) : 0;
	dt.minute = c.has_minute ? std::atoi(c.minute.c_str()) : 0;
	dt.second = c.has_second ? std::atoi(c.second.c_str()) : 0;
	dt.millisecond = c.has_ms ? std::atoi(c.ms.c_str()) : 0;

	if (!c.has_month) {
		dt.year += direction;
		if (dt.year < 1 || dt.year > 9999) return NullOpt<std::string>();
		return Optional<std::string>(format_temporal_for_precision(dt, is_datetime, c));
	}
	if (!c.has_day) {
		if (!add_months_in_place(dt, direction)) return NullOpt<std::string>();
		return Optional<std::string>(format_temporal_for_precision(dt, is_datetime, c));
	}
	if (!is_datetime || !c.has_time) {
		if (!add_days_in_place(dt, direction)) return NullOpt<std::string>();
		return Optional<std::string>(format_temporal_for_precision(dt, is_datetime, c));
	}

	int64_t delta_ms = 1;
	if (!c.has_minute) delta_ms = 3600000LL;
	else if (!c.has_second) delta_ms = 60000LL;
	else if (!c.has_ms) delta_ms = 1000LL;
	delta_ms *= direction;
	if (!add_time_millis_in_place(dt, delta_ms)) return NullOpt<std::string>();
	return Optional<std::string>(format_temporal_for_precision(dt, is_datetime, c));
}

// =====================================================================
// HighBoundary
// =====================================================================
Optional<std::string> high_boundary(const std::string &value, int precision) {
	if (value.empty()) return NullOpt<std::string>();

	auto kind = detect_kind(value);

	if (kind == ValueKind::Numeric) {
		if (precision > 8) return NullOpt<std::string>();
		// Decimal: fill remaining digits with 9s
		std::string d_str = normalize_numeric_text(value);
		size_t dot = d_str.find('.');
		int current_dec = (dot != std::string::npos) ? static_cast<int>(d_str.size() - dot - 1) : 0;
		int to_fill = precision - current_dec;
		if (to_fill <= 0) return Optional<std::string>(d_str);
		if (dot == std::string::npos) d_str += ".";
		for (int i = 0; i < to_fill; i++) d_str += "9";
		return Optional<std::string>(d_str);
	}

	if (kind == ValueKind::Time) {
		if (precision > 9) return NullOpt<std::string>();
		if (!validate_time_string(value)) return NullOpt<std::string>();
		auto tc = parse_time_components(value);
		int input_precision = 2;
		std::string ts = strip_time_suffix(value);
		if (ts.find(':') != std::string::npos) input_precision = 4;
		size_t second_sep = ts.find(':', ts.find(':') == std::string::npos ? 0 : ts.find(':') + 1);
		if (second_sep != std::string::npos) input_precision = 6;
		if (ts.find('.') != std::string::npos) input_precision = 9;
		if (precision <= 2 || input_precision <= 2) return Optional<std::string>(format_time(tc.h, 59, 59, 999, tc.suffix));
		if (precision <= 4 || input_precision <= 4) return Optional<std::string>(format_time(tc.h, tc.m, 59, 999, tc.suffix));
		if (precision <= 6 || input_precision <= 6) return Optional<std::string>(format_time(tc.h, tc.m, tc.s, 999, tc.suffix));
		return Optional<std::string>(format_time(tc.h, tc.m, tc.s, tc.ms, tc.suffix));
	}

	if (kind == ValueKind::Date || kind == ValueKind::DateTime) {
		if ((kind == ValueKind::Date && precision > 8) ||
		    (kind == ValueKind::DateTime && precision > 17)) {
			return NullOpt<std::string>();
		}
		if (!validate_dt_lexical_shape(value)) return NullOpt<std::string>();
		auto c = parse_dt_components(value);
		if (!validate_dt_components(c)) return NullOpt<std::string>();
		std::string yr = c.year;
		std::string mo = c.has_month ? c.month : "12";
		int yr_i = std::atoi(yr.c_str());
		int mo_i = std::atoi(mo.c_str());
		int dm = days_in_month(yr_i, mo_i);
		std::ostringstream dm_oss;
		if (dm < 10) dm_oss << "0";
		dm_oss << dm;
		std::string dy = c.has_day ? c.day : dm_oss.str();
		// Recalculate if month was defaulted to 12
		if (!c.has_month) dy = "31";
		std::string hr = c.has_time ? c.hour : "23";
		std::string mn = c.has_minute ? c.minute : "59";
		std::string sc = c.has_second ? c.second : "59";
		std::string ms = c.has_ms ? c.ms : "999";

		if (precision <= 4) return Optional<std::string>(yr);
		if (precision <= 6) return Optional<std::string>(yr + "-" + mo);
		if (precision <= 8) return Optional<std::string>(yr + "-" + mo + "-" + dy);
		if (precision <= 10) return Optional<std::string>(yr + "-" + mo + "-" + dy + "T" + hr + c.suffix);
		if (precision <= 12) return Optional<std::string>(yr + "-" + mo + "-" + dy + "T" + hr + ":" + mn + c.suffix);
		if (precision <= 14) return Optional<std::string>(yr + "-" + mo + "-" + dy + "T" + hr + ":" + mn + ":" + sc + c.suffix);
		return Optional<std::string>(yr + "-" + mo + "-" + dy + "T" + hr + ":" + mn + ":" + sc + "." + ms + c.suffix);
	}

	return NullOpt<std::string>();
}

// =====================================================================
// LowBoundary
// =====================================================================
Optional<std::string> low_boundary(const std::string &value, int precision) {
	if (value.empty()) return NullOpt<std::string>();

	auto kind = detect_kind(value);

	if (kind == ValueKind::Numeric) {
		if (precision > 8) return NullOpt<std::string>();
		std::string d_str = normalize_numeric_text(value);
		size_t dot = d_str.find('.');
		int current_dec = (dot != std::string::npos) ? static_cast<int>(d_str.size() - dot - 1) : 0;
		int to_fill = precision - current_dec;
		if (to_fill <= 0) return Optional<std::string>(d_str);
		if (dot == std::string::npos) d_str += ".";
		for (int i = 0; i < to_fill; i++) d_str += "0";
		return Optional<std::string>(d_str);
	}

	if (kind == ValueKind::Time) {
		if (precision > 9) return NullOpt<std::string>();
		if (!validate_time_string(value)) return NullOpt<std::string>();
		auto tc = parse_time_components(value);
		if (precision <= 2) return Optional<std::string>(format_time(tc.h, 0, 0, 0, tc.suffix));
		if (precision <= 4) return Optional<std::string>(format_time(tc.h, tc.m, 0, 0, tc.suffix));
		if (precision <= 6) return Optional<std::string>(format_time(tc.h, tc.m, tc.s, 0, tc.suffix));
		return Optional<std::string>(format_time(tc.h, tc.m, tc.s, tc.ms, tc.suffix));
	}

	if (kind == ValueKind::Date || kind == ValueKind::DateTime) {
		if ((kind == ValueKind::Date && precision > 8) ||
		    (kind == ValueKind::DateTime && precision > 17)) {
			return NullOpt<std::string>();
		}
		if (!validate_dt_lexical_shape(value)) return NullOpt<std::string>();
		auto c = parse_dt_components(value);
		if (!validate_dt_components(c)) return NullOpt<std::string>();
		std::string yr = c.year;
		std::string mo = c.has_month ? c.month : "01";
		std::string dy = c.has_day ? c.day : "01";
		std::string hr = c.has_time ? c.hour : "00";
		std::string mn = c.has_minute ? c.minute : "00";
		std::string sc = c.has_second ? c.second : "00";
		std::string ms = c.has_ms ? c.ms : "000";

		if (precision <= 4) return Optional<std::string>(yr);
		if (precision <= 6) return Optional<std::string>(yr + "-" + mo);
		if (precision <= 8) return Optional<std::string>(yr + "-" + mo + "-" + dy);
		if (precision <= 10) return Optional<std::string>(yr + "-" + mo + "-" + dy + "T" + hr + c.suffix);
		if (precision <= 12) return Optional<std::string>(yr + "-" + mo + "-" + dy + "T" + hr + ":" + mn + c.suffix);
		if (precision <= 14) return Optional<std::string>(yr + "-" + mo + "-" + dy + "T" + hr + ":" + mn + ":" + sc + c.suffix);
		return Optional<std::string>(yr + "-" + mo + "-" + dy + "T" + hr + ":" + mn + ":" + sc + "." + ms + c.suffix);
	}

	return NullOpt<std::string>();
}

// =====================================================================
// cql_precision
// =====================================================================
Optional<int64_t> cql_precision(const std::string &value) {
	if (value.empty()) return NullOpt<int64_t>();

	std::string s = value;
	bool date_like = s.find('T') != std::string::npos ||
	                 (s.size() >= 4 && std::isdigit(static_cast<unsigned char>(s[0])) &&
	                  std::isdigit(static_cast<unsigned char>(s[1])) &&
	                  std::isdigit(static_cast<unsigned char>(s[2])) &&
	                  std::isdigit(static_cast<unsigned char>(s[3])) &&
	                  (s.size() == 4 || s[4] == '-'));
	if (date_like) {
		s = strip_datetime_timezone_for_precision(s);
		int64_t digits = 0;
		for (char c : s) {
			if (std::isdigit(static_cast<unsigned char>(c))) digits++;
		}
		return Optional<int64_t>(digits);
	}

	if ((s.size() >= 1 && s[0] == 'T') || (s.size() >= 2 && s.find(':') != std::string::npos &&
	                                       s.find('-') == std::string::npos)) {
		if (!s.empty() && s[0] == 'T') s = s.substr(1);
		int64_t digits = 0;
		for (char c : s) {
			if (std::isdigit(static_cast<unsigned char>(c))) digits++;
		}
		return Optional<int64_t>(digits);
	}

	char *end = nullptr;
	std::strtod(s.c_str(), &end);
	if (end == s.c_str() || *end != '\0') return NullOpt<int64_t>();

	auto exp_pos = s.find_first_of("eE");
	std::string mantissa = exp_pos == std::string::npos ? s : s.substr(0, exp_pos);
	int64_t exponent = 0;
	if (exp_pos != std::string::npos) {
		try {
			exponent = std::stoll(s.substr(exp_pos + 1));
		} catch (const std::exception &) {
			return NullOpt<int64_t>();
		}
	}

	int64_t fractional_digits = 0;
	auto dot_pos = mantissa.find('.');
	if (dot_pos != std::string::npos) {
		fractional_digits = static_cast<int64_t>(mantissa.size() - dot_pos - 1);
	}
	int64_t precision = fractional_digits - exponent;
	return Optional<int64_t>(precision > 0 ? precision : 0);
}

// =====================================================================
// cql_timezone_offset
// =====================================================================
Optional<double> cql_timezone_offset(const std::string &value) {
	if (value.empty()) return NullOpt<double>();

	// CQL §DateTime ISO-8601 representation: Z is the UTC designator
	// (equivalent to +00:00). Return 0.0 for Z-suffixed values.
	if (value[value.size() - 1] == 'Z') {
		return Optional<double>(0.0);
	}

	// Search for +HH:MM or -HH:MM at end
	for (int i = static_cast<int>(value.size()) - 1; i >= 0; i--) {
		if (value[i] == '+' || value[i] == '-') {
			std::string suffix = value.substr(i);
			if (valid_timezone_suffix(suffix)) {
				int sign = (value[i] == '+') ? 1 : -1;
				int hours = std::atoi(value.substr(i + 1, 2).c_str());
				int mins = std::atoi(value.substr(i + 4, 2).c_str());
				return Optional<double>(sign * (hours + mins / 60.0));
			}
			break;
		}
	}
	return NullOpt<double>();
}

// =====================================================================
// predecessorOf
// =====================================================================
Optional<std::string> predecessor_of(const std::string &value) {
	if (value.empty()) return NullOpt<std::string>();

	auto kind = detect_kind(value);

	if (!value.empty() && value[0] == '{') {
		return step_quantity_json(value, -1);
	}

	if (kind == ValueKind::Time) {
		if (!validate_time_string(value)) return NullOpt<std::string>();
		auto tc = parse_time_components(value);
		int64_t step_ms = time_step_for_precision(value);
		int total_ms = ((tc.h * 60 + tc.m) * 60 + tc.s) * 1000 + tc.ms - static_cast<int>(step_ms);
		if (total_ms < 0) return NullOpt<std::string>(); // underflow
		int rh = total_ms / 3600000;
		int rem = total_ms % 3600000;
		int rm = rem / 60000;
		rem = rem % 60000;
		int rs = rem / 1000;
		int rms = rem % 1000;
		return Optional<std::string>(format_time_for_precision(rh, rm, rs, rms, step_ms, tc.suffix));
	}

	if (kind == ValueKind::DateTime) {
		return step_date_or_datetime(value, -1, true);
	}

	if (kind == ValueKind::Date) {
		return step_date_or_datetime(value, -1, false);
	}

	if (kind == ValueKind::Numeric) {
		// Public VARCHAR numeric helpers are decimal-valued. Typed Integer/Long
		// predecessor uses the BIGINT overload registered in cql_extension.cpp.
		char *end = NULL;
		double d = std::strtod(value.c_str(), &end);
		if (end != value.c_str() && *end == '\0') {
			if (decimal_step_overflows(value, -1)) return NullOpt<std::string>();
			double result = d - 1e-8;
			std::ostringstream oss;
			oss.precision(15);
			oss << result;
			return Optional<std::string>(oss.str());
		}
	}

	return NullOpt<std::string>();
}

// =====================================================================
// successorOf
// =====================================================================
Optional<std::string> successor_of(const std::string &value) {
	if (value.empty()) return NullOpt<std::string>();

	auto kind = detect_kind(value);

	if (!value.empty() && value[0] == '{') {
		return step_quantity_json(value, 1);
	}

	if (kind == ValueKind::Time) {
		if (!validate_time_string(value)) return NullOpt<std::string>();
		auto tc = parse_time_components(value);
		int64_t step_ms = time_step_for_precision(value);
		int total_ms = ((tc.h * 60 + tc.m) * 60 + tc.s) * 1000 + tc.ms + static_cast<int>(step_ms);
		if (total_ms > 86399999) return NullOpt<std::string>(); // overflow
		int rh = total_ms / 3600000;
		int rem = total_ms % 3600000;
		int rm = rem / 60000;
		rem = rem % 60000;
		int rs = rem / 1000;
		int rms = rem % 1000;
		return Optional<std::string>(format_time_for_precision(rh, rm, rs, rms, step_ms, tc.suffix));
	}

	if (kind == ValueKind::DateTime) {
		return step_date_or_datetime(value, 1, true);
	}

	if (kind == ValueKind::Date) {
		return step_date_or_datetime(value, 1, false);
	}

	if (kind == ValueKind::Numeric) {
		// Public VARCHAR numeric helpers are decimal-valued. Typed Integer/Long
		// successor uses the BIGINT overload registered in cql_extension.cpp.
		char *end = NULL;
		double d = std::strtod(value.c_str(), &end);
		if (end != value.c_str() && *end == '\0') {
			if (decimal_step_overflows(value, 1)) return NullOpt<std::string>();
			double result = d + 1e-8;
			std::ostringstream oss;
			oss.precision(15);
			oss << result;
			return Optional<std::string>(oss.str());
		}
	}

	return NullOpt<std::string>();
}

} // namespace cql
