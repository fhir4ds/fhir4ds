#include "cql/boundary.hpp"
#include "cql/datetime.hpp"
#include <cstdlib>
#include <cmath>
#include <sstream>
#include <algorithm>
#include <cstring>

namespace cql {

// =====================================================================
// Helper: detect value type
// =====================================================================
enum class ValueKind { DateTime, Date, Time, Numeric, Unknown };

static ValueKind detect_kind(const std::string &s) {
	if (s.empty()) return ValueKind::Unknown;
	// Time: starts with T and digit, or HH:MM pattern without dashes
	if ((s[0] == 'T' && s.size() >= 3 && s[1] >= '0' && s[1] <= '9') ||
	    (s.size() >= 5 && s[2] == ':' && s[0] >= '0' && s[0] <= '9' && s.find('-') == std::string::npos)) {
		return ValueKind::Time;
	}
	// Date/DateTime: has dashes in date-like position
	if (s.size() >= 10 && s[4] == '-') {
		if (s.find('T') != std::string::npos || s.find(' ') != std::string::npos) {
			return ValueKind::DateTime;
		}
		return ValueKind::Date;
	}
	// Year-only: 4 digits
	if (s.size() == 4 && s[0] >= '0' && s[0] <= '9' && s[1] >= '0' && s[3] >= '0') {
		return ValueKind::Date;
	}
	// Year-month: YYYY-MM
	if (s.size() == 7 && s[4] == '-') {
		return ValueKind::Date;
	}
	// Numeric
	char *end = NULL;
	std::strtod(s.c_str(), &end);
	if (end != s.c_str() && *end == '\0') {
		return ValueKind::Numeric;
	}
	return ValueKind::Unknown;
}

// =====================================================================
// Helper: parse time string to components
// =====================================================================
struct TimeComponents {
	int h, m, s, ms;
};

static TimeComponents parse_time_components(const std::string &s) {
	TimeComponents tc = {0, 0, 0, 0};
	std::string ts = s;
	if (!ts.empty() && ts[0] == 'T') ts = ts.substr(1);

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

static std::string format_time(int h, int m, int s, int ms) {
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
	return oss.str();
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

// =====================================================================
// Helper: extract date/datetime components from string
// =====================================================================
struct DateTimeComponents {
	std::string year, month, day, hour, minute, second, ms;
	bool has_month, has_day, has_time, has_minute, has_second, has_ms;
};

static DateTimeComponents parse_dt_components(const std::string &s) {
	DateTimeComponents c;
	c.has_month = false; c.has_day = false; c.has_time = false;
	c.has_minute = false; c.has_second = false; c.has_ms = false;

	c.year = s.substr(0, 4);
	if (s.size() > 5 && s[4] == '-') {
		c.month = s.substr(5, 2);
		c.has_month = true;
	}
	if (s.size() > 8 && s[7] == '-') {
		c.day = s.substr(8, 2);
		c.has_day = true;
	}
	size_t t_pos = s.find('T');
	if (t_pos == std::string::npos) t_pos = s.find(' ');
	if (t_pos != std::string::npos && t_pos + 2 < s.size()) {
		c.has_time = true;
		c.hour = s.substr(t_pos + 1, 2);
		if (t_pos + 5 < s.size() && s[t_pos + 3] == ':') {
			c.minute = s.substr(t_pos + 4, 2);
			c.has_minute = true;
		}
		if (t_pos + 8 < s.size() && s[t_pos + 6] == ':') {
			c.second = s.substr(t_pos + 7, 2);
			c.has_second = true;
		}
		size_t dot = s.find('.', t_pos);
		if (dot != std::string::npos && dot + 1 < s.size()) {
			// Extract up to 3 chars for ms, ignoring timezone
			std::string frac;
			for (size_t i = dot + 1; i < s.size() && frac.size() < 3; i++) {
				if (s[i] >= '0' && s[i] <= '9') frac += s[i];
				else break;
			}
			while (frac.size() < 3) frac += "0";
			c.ms = frac;
			c.has_ms = true;
		}
	}
	return c;
}

// =====================================================================
// HighBoundary
// =====================================================================
Optional<std::string> high_boundary(const std::string &value, int precision) {
	if (value.empty()) return NullOpt<std::string>();

	auto kind = detect_kind(value);

	if (kind == ValueKind::Numeric) {
		// Decimal: fill remaining digits with 9s
		std::string d_str = value;
		size_t dot = d_str.find('.');
		int current_dec = (dot != std::string::npos) ? static_cast<int>(d_str.size() - dot - 1) : 0;
		int to_fill = precision - current_dec;
		if (to_fill <= 0) return Optional<std::string>(value);
		if (dot == std::string::npos) d_str += ".";
		for (int i = 0; i < to_fill; i++) d_str += "9";
		return Optional<std::string>(d_str);
	}

	if (kind == ValueKind::Time) {
		auto tc = parse_time_components(value);
		if (precision <= 2) return Optional<std::string>(format_time(tc.h, 59, 59, 999));
		if (precision <= 4) return Optional<std::string>(format_time(tc.h, tc.m, 59, 999));
		if (precision <= 6) return Optional<std::string>(format_time(tc.h, tc.m, tc.s, 999));
		return Optional<std::string>(format_time(tc.h, tc.m, tc.s, tc.ms));
	}

	if (kind == ValueKind::Date || kind == ValueKind::DateTime) {
		auto c = parse_dt_components(value);
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
		if (precision <= 10) return Optional<std::string>(yr + "-" + mo + "-" + dy + "T" + hr);
		if (precision <= 12) return Optional<std::string>(yr + "-" + mo + "-" + dy + "T" + hr + ":" + mn);
		if (precision <= 14) return Optional<std::string>(yr + "-" + mo + "-" + dy + "T" + hr + ":" + mn + ":" + sc);
		return Optional<std::string>(yr + "-" + mo + "-" + dy + "T" + hr + ":" + mn + ":" + sc + "." + ms);
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
		std::string d_str = value;
		size_t dot = d_str.find('.');
		int current_dec = (dot != std::string::npos) ? static_cast<int>(d_str.size() - dot - 1) : 0;
		int to_fill = precision - current_dec;
		if (to_fill <= 0) return Optional<std::string>(value);
		if (dot == std::string::npos) d_str += ".";
		for (int i = 0; i < to_fill; i++) d_str += "0";
		return Optional<std::string>(d_str);
	}

	if (kind == ValueKind::Time) {
		auto tc = parse_time_components(value);
		if (precision <= 2) return Optional<std::string>(format_time(tc.h, 0, 0, 0));
		if (precision <= 4) return Optional<std::string>(format_time(tc.h, tc.m, 0, 0));
		if (precision <= 6) return Optional<std::string>(format_time(tc.h, tc.m, tc.s, 0));
		return Optional<std::string>(format_time(tc.h, tc.m, tc.s, tc.ms));
	}

	if (kind == ValueKind::Date || kind == ValueKind::DateTime) {
		auto c = parse_dt_components(value);
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
		if (precision <= 10) return Optional<std::string>(yr + "-" + mo + "-" + dy + "T" + hr);
		if (precision <= 12) return Optional<std::string>(yr + "-" + mo + "-" + dy + "T" + hr + ":" + mn);
		if (precision <= 14) return Optional<std::string>(yr + "-" + mo + "-" + dy + "T" + hr + ":" + mn + ":" + sc);
		return Optional<std::string>(yr + "-" + mo + "-" + dy + "T" + hr + ":" + mn + ":" + sc + "." + ms);
	}

	return NullOpt<std::string>();
}

// =====================================================================
// cql_precision
// =====================================================================
Optional<int> cql_precision(const std::string &value) {
	if (value.empty()) return NullOpt<int>();

	auto kind = detect_kind(value);

	if (kind == ValueKind::Date || kind == ValueKind::DateTime) {
		// Count digit characters, strip timezone suffix
		std::string s = value;
		// Strip timezone
		for (size_t i = 10; i < s.size(); i++) {
			if (s[i] == '+' || s[i] == 'Z') {
				s = s.substr(0, i);
				break;
			}
		}
		int count = 0;
		for (size_t i = 0; i < s.size(); i++) {
			if (s[i] >= '0' && s[i] <= '9') count++;
		}
		return Optional<int>(count);
	}

	if (kind == ValueKind::Time) {
		std::string s = value;
		if (!s.empty() && s[0] == 'T') s = s.substr(1);
		int count = 0;
		for (size_t i = 0; i < s.size(); i++) {
			if (s[i] >= '0' && s[i] <= '9') count++;
		}
		return Optional<int>(count);
	}

	if (kind == ValueKind::Numeric) {
		size_t dot = value.find('.');
		if (dot == std::string::npos) return Optional<int>(0);
		return Optional<int>(static_cast<int>(value.size() - dot - 1));
	}

	return Optional<int>(static_cast<int>(value.size()));
}

// =====================================================================
// cql_timezone_offset
// =====================================================================
Optional<double> cql_timezone_offset(const std::string &value) {
	if (value.empty()) return NullOpt<double>();

	// Search for +HH:MM or -HH:MM at end
	for (int i = static_cast<int>(value.size()) - 1; i >= 0; i--) {
		if (value[i] == '+' || value[i] == '-') {
			if (i + 5 < static_cast<int>(value.size()) && value[i + 3] == ':') {
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

	if (kind == ValueKind::Time) {
		auto tc = parse_time_components(value);
		int total_ms = ((tc.h * 60 + tc.m) * 60 + tc.s) * 1000 + tc.ms - 1;
		if (total_ms < 0) return NullOpt<std::string>(); // underflow
		int rh = total_ms / 3600000;
		int rem = total_ms % 3600000;
		int rm = rem / 60000;
		rem = rem % 60000;
		int rs = rem / 1000;
		int rms = rem % 1000;
		return Optional<std::string>(format_time(rh, rm, rs, rms));
	}

	if (kind == ValueKind::DateTime) {
		// Subtract 1 millisecond
		auto dt = DateTimeValue::parse(value);
		if (!dt) return NullOpt<std::string>();
		dt->millisecond -= 1;
		if (dt->millisecond < 0) {
			dt->millisecond = 999;
			dt->second -= 1;
			if (dt->second < 0) {
				dt->second = 59;
				dt->minute -= 1;
				if (dt->minute < 0) {
					dt->minute = 59;
					dt->hour -= 1;
					if (dt->hour < 0) {
						dt->hour = 23;
						dt->day -= 1;
						if (dt->day < 1) {
							dt->month -= 1;
							if (dt->month < 1) {
								dt->month = 12;
								dt->year -= 1;
							}
							dt->day = days_in_month(dt->year, dt->month);
						}
					}
				}
			}
		}
		return Optional<std::string>(dt->to_string());
	}

	if (kind == ValueKind::Date) {
		// Subtract 1 day
		auto dt = DateTimeValue::parse(value);
		if (!dt) return NullOpt<std::string>();
		dt->day -= 1;
		if (dt->day < 1) {
			dt->month -= 1;
			if (dt->month < 1) {
				dt->month = 12;
				dt->year -= 1;
			}
			dt->day = days_in_month(dt->year, dt->month);
		}
		// Return in original format
		if (dt->precision == DateTimeValue::Precision::Year) {
			std::ostringstream oss;
			oss << dt->year;
			return Optional<std::string>(oss.str());
		}
		return Optional<std::string>(dt->to_string());
	}

	if (kind == ValueKind::Numeric) {
		// Try integer first
		if (value.find('.') == std::string::npos) {
			char *end = NULL;
			long long v = std::strtoll(value.c_str(), &end, 10);
			if (end != value.c_str() && *end == '\0') {
				std::ostringstream oss;
				oss << (v - 1);
				return Optional<std::string>(oss.str());
			}
		}
		// Decimal: subtract 1e-8
		char *end = NULL;
		double d = std::strtod(value.c_str(), &end);
		if (end != value.c_str() && *end == '\0') {
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

	if (kind == ValueKind::Time) {
		auto tc = parse_time_components(value);
		int total_ms = ((tc.h * 60 + tc.m) * 60 + tc.s) * 1000 + tc.ms + 1;
		if (total_ms > 86399999) return NullOpt<std::string>(); // overflow
		int rh = total_ms / 3600000;
		int rem = total_ms % 3600000;
		int rm = rem / 60000;
		rem = rem % 60000;
		int rs = rem / 1000;
		int rms = rem % 1000;
		return Optional<std::string>(format_time(rh, rm, rs, rms));
	}

	if (kind == ValueKind::DateTime) {
		auto dt = DateTimeValue::parse(value);
		if (!dt) return NullOpt<std::string>();
		dt->millisecond += 1;
		if (dt->millisecond > 999) {
			dt->millisecond = 0;
			dt->second += 1;
			if (dt->second > 59) {
				dt->second = 0;
				dt->minute += 1;
				if (dt->minute > 59) {
					dt->minute = 0;
					dt->hour += 1;
					if (dt->hour > 23) {
						dt->hour = 0;
						dt->day += 1;
						if (dt->day > days_in_month(dt->year, dt->month)) {
							dt->day = 1;
							dt->month += 1;
							if (dt->month > 12) {
								dt->month = 1;
								dt->year += 1;
							}
						}
					}
				}
			}
		}
		return Optional<std::string>(dt->to_string());
	}

	if (kind == ValueKind::Date) {
		auto dt = DateTimeValue::parse(value);
		if (!dt) return NullOpt<std::string>();
		dt->day += 1;
		if (dt->day > days_in_month(dt->year, dt->month)) {
			dt->day = 1;
			dt->month += 1;
			if (dt->month > 12) {
				dt->month = 1;
				dt->year += 1;
			}
		}
		if (dt->precision == DateTimeValue::Precision::Year) {
			std::ostringstream oss;
			oss << dt->year;
			return Optional<std::string>(oss.str());
		}
		return Optional<std::string>(dt->to_string());
	}

	if (kind == ValueKind::Numeric) {
		if (value.find('.') == std::string::npos) {
			char *end = NULL;
			long long v = std::strtoll(value.c_str(), &end, 10);
			if (end != value.c_str() && *end == '\0') {
				std::ostringstream oss;
				oss << (v + 1);
				return Optional<std::string>(oss.str());
			}
		}
		char *end = NULL;
		double d = std::strtod(value.c_str(), &end);
		if (end != value.c_str() && *end == '\0') {
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
