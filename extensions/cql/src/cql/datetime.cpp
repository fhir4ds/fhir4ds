#include "cql/datetime.hpp"
#include <cctype>
#include <cstdlib>
#include <cstdio>
#include <cstring>
#include <sstream>

namespace cql {

static int days_in_month(int year, int month) {
	static const int dim[] = {0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31};
	if (month < 1 || month > 12) {
		return 0;
	}
	if (month == 2 && (year % 4 == 0 && (year % 100 != 0 || year % 400 == 0))) {
		return 29;
	}
	return dim[month];
}

static bool parse_timezone_offset(char *&end, int &offset_minutes) {
	int sign = (*end == '+') ? 1 : -1;
	const char *p = end + 1;
	if (std::strlen(p) < 5) {
		return false;
	}
	if (!std::isdigit(static_cast<unsigned char>(p[0])) ||
	    !std::isdigit(static_cast<unsigned char>(p[1])) ||
	    p[2] != ':' ||
	    !std::isdigit(static_cast<unsigned char>(p[3])) ||
	    !std::isdigit(static_cast<unsigned char>(p[4]))) {
		return false;
	}
	int tz_hour = (p[0] - '0') * 10 + (p[1] - '0');
	int tz_min = (p[3] - '0') * 10 + (p[4] - '0');
	if (tz_hour > 14 || tz_min > 59 || (tz_hour == 14 && tz_min > 0)) {
		return false;
	}
	end = const_cast<char *>(p + 5);
	offset_minutes = sign * (tz_hour * 60 + tz_min);
	return true;
}

static Optional<DateTimeValue> parse_time_value(const std::string &str) {
	DateTimeValue dt;
	dt.year = 1;
	dt.month = 1;
	dt.day = 1;
	dt.has_time = true;
	dt.is_time = true;
	dt.precision = DateTimeValue::Precision::Hour;

	const char *s = str.c_str();
	if (*s == 'T') {
		s++;
	}
	char *end;
	dt.hour = static_cast<int32_t>(std::strtol(s, &end, 10));
	if (end == s || dt.hour < 0 || dt.hour > 23) {
		return NullOpt<DateTimeValue>();
	}

	if (*end == ':') {
		s = end + 1;
		dt.minute = static_cast<int32_t>(std::strtol(s, &end, 10));
		if (end == s || dt.minute < 0 || dt.minute > 59) {
			return NullOpt<DateTimeValue>();
		}
		dt.precision = DateTimeValue::Precision::Minute;
		if (*end == ':') {
			s = end + 1;
			dt.second = static_cast<int32_t>(std::strtol(s, &end, 10));
			if (end == s || dt.second < 0 || dt.second > 59) {
				return NullOpt<DateTimeValue>();
			}
			dt.precision = DateTimeValue::Precision::Second;
			if (*end == '.') {
				s = end + 1;
				dt.millisecond = static_cast<int32_t>(std::strtol(s, &end, 10));
				int digits = static_cast<int>(end - s);
				if (digits <= 0) {
					return NullOpt<DateTimeValue>();
				}
				if (digits == 1) {
					dt.millisecond *= 100;
				} else if (digits == 2) {
					dt.millisecond *= 10;
				} else if (digits > 3) {
					for (int i = 3; i < digits; i++) {
						dt.millisecond /= 10;
					}
				}
				if (dt.millisecond < 0 || dt.millisecond > 999) {
					return NullOpt<DateTimeValue>();
				}
				dt.precision = DateTimeValue::Precision::Millisecond;
			}
		}
	}

	if (*end == 'Z') {
		dt.has_tz = true;
		dt.tz_offset_minutes = 0;
		end++;
	} else if (*end == '+' || *end == '-') {
		dt.has_tz = true;
		int offset = 0;
		if (!parse_timezone_offset(end, offset)) {
			return NullOpt<DateTimeValue>();
		}
		dt.tz_offset_minutes = offset;
	}

	if (*end != '\0') {
		return NullOpt<DateTimeValue>();
	}
	return dt;
}

Optional<DateTimeValue> DateTimeValue::parse(const std::string &str) {
	if (str.empty()) {
		return NullOpt<DateTimeValue>();
	}

	if (str[0] == 'T' || (str.find(':') != std::string::npos && str.find('-') == std::string::npos)) {
		return parse_time_value(str);
	}

	DateTimeValue dt;
	const char *s = str.c_str();
	char *end;

	// Parse year
	dt.year = static_cast<int32_t>(std::strtol(s, &end, 10));
	if (end == s || dt.year < 1 || dt.year > 9999) {
		return NullOpt<DateTimeValue>();
	}
	dt.precision = Precision::Year;

	if (*end == '\0') {
		dt.month = 1;
		dt.day = 1;
		return dt;
	}
	if (*end == 'T' && *(end + 1) == '\0') {
		dt.month = 1;
		dt.day = 1;
		return dt;
	}
	if (*end != '-') {
		return NullOpt<DateTimeValue>();
	}
	s = end + 1;

	// Parse month
	dt.month = static_cast<int32_t>(std::strtol(s, &end, 10));
	if (end == s || dt.month < 1 || dt.month > 12) {
		return NullOpt<DateTimeValue>();
	}
	dt.precision = Precision::Month;

	if (*end == '\0') {
		dt.day = 1;
		return dt;
	}
	if (*end == 'T' && *(end + 1) == '\0') {
		dt.day = 1;
		return dt;
	}
	if (*end != '-') {
		return NullOpt<DateTimeValue>();
	}
	s = end + 1;

	// Parse day
	dt.day = static_cast<int32_t>(std::strtol(s, &end, 10));
	if (end == s || dt.day < 1 || dt.day > days_in_month(dt.year, dt.month)) {
		return NullOpt<DateTimeValue>();
	}
	dt.precision = Precision::Day;

	if (*end == '\0') {
		return dt;
	}
	if (*end == 'T' && *(end + 1) == '\0') {
		return dt;
	}

	// Parse time component
	// Accept both 'T' (ISO 8601) and ' ' (DuckDB CAST(TIMESTAMP AS VARCHAR) output)
	if (*end == 'T' || *end == ' ') {
		dt.has_time = true;
		s = end + 1;

		dt.hour = static_cast<int32_t>(std::strtol(s, &end, 10));
		if (end == s || dt.hour < 0 || dt.hour > 23) {
			return NullOpt<DateTimeValue>();
		}
		dt.precision = Precision::Hour;
		if (*end == ':') {
			s = end + 1;
			dt.minute = static_cast<int32_t>(std::strtol(s, &end, 10));
			if (end == s || dt.minute < 0 || dt.minute > 59) {
				return NullOpt<DateTimeValue>();
			}
			dt.precision = Precision::Minute;
			if (*end == ':') {
				s = end + 1;
				dt.second = static_cast<int32_t>(std::strtol(s, &end, 10));
				if (end == s || dt.second < 0 || dt.second > 59) {
					return NullOpt<DateTimeValue>();
				}
				dt.precision = Precision::Second;
				if (*end == '.') {
					s = end + 1;
					dt.millisecond = static_cast<int32_t>(std::strtol(s, &end, 10));
					dt.precision = Precision::Millisecond;
					// Handle various fractional second lengths
					int digits = static_cast<int>(end - s);
					if (digits <= 0) {
						return NullOpt<DateTimeValue>();
					}
					if (digits == 1) {
						dt.millisecond *= 100;
					} else if (digits == 2) {
						dt.millisecond *= 10;
					} else if (digits > 3) {
						for (int i = 3; i < digits; i++) {
							dt.millisecond /= 10;
						}
					}
					if (dt.millisecond < 0 || dt.millisecond > 999) {
						return NullOpt<DateTimeValue>();
					}
				}
			}
		}

		// Parse timezone
		if (*end == 'Z') {
			dt.has_tz = true;
			dt.tz_offset_minutes = 0;
			end++;
		} else if (*end == '+' || *end == '-') {
			dt.has_tz = true;
			int offset = 0;
			if (!parse_timezone_offset(end, offset)) {
				return NullOpt<DateTimeValue>();
			}
			dt.tz_offset_minutes = offset;
		}
	}

	if (*end != '\0') {
		return NullOpt<DateTimeValue>();
	}

	return dt;
}

std::string DateTimeValue::to_string() const {
	std::ostringstream oss;
	char buf[32];

	if (is_time) {
		snprintf(buf, sizeof(buf), "T%02d", hour);
		oss << buf;
		if (precision >= Precision::Minute) {
			snprintf(buf, sizeof(buf), ":%02d", minute);
			oss << buf;
		}
		if (precision >= Precision::Second) {
			snprintf(buf, sizeof(buf), ":%02d", second);
			oss << buf;
		}
		if (precision >= Precision::Millisecond) {
			snprintf(buf, sizeof(buf), ".%03d", millisecond);
			oss << buf;
		}
		if (has_tz) {
			if (tz_offset_minutes == 0) {
				oss << "Z";
			} else {
				int abs_offset = std::abs(tz_offset_minutes);
				snprintf(buf, sizeof(buf), "%c%02d:%02d", tz_offset_minutes >= 0 ? '+' : '-', abs_offset / 60,
				         abs_offset % 60);
				oss << buf;
			}
		}
		return oss.str();
	}

	snprintf(buf, sizeof(buf), "%04d", year);
	oss << buf;
	if (!has_time && precision == Precision::Year) {
		// CQL §9 Date: "@2014 represents some day in the year 2014" — year-precision
		// dates serialize as the canonical 4-digit year YYYY, not "YYYYT".
		// The "T" is only a date/time separator (e.g. "YYYY-MM-DDTHH:mm:ss").
		// Note: the parser still accepts "YYYYT" for backward compatibility.
		return oss.str();
	}

	if (precision >= Precision::Month) {
		snprintf(buf, sizeof(buf), "-%02d", month);
		oss << buf;
	}
	if (precision >= Precision::Day) {
		snprintf(buf, sizeof(buf), "-%02d", day);
		oss << buf;
	}
	if (has_time) {
		snprintf(buf, sizeof(buf), "T%02d", hour);
		oss << buf;
		if (precision >= Precision::Minute) {
			snprintf(buf, sizeof(buf), ":%02d", minute);
			oss << buf;
		}
		if (precision >= Precision::Second) {
			snprintf(buf, sizeof(buf), ":%02d", second);
			oss << buf;
		}
		if (precision >= Precision::Millisecond) {
			snprintf(buf, sizeof(buf), ".%03d", millisecond);
			oss << buf;
		}
		if (has_tz) {
			if (tz_offset_minutes == 0) {
				oss << "Z";
			} else {
				int abs_offset = std::abs(tz_offset_minutes);
				snprintf(buf, sizeof(buf), "%c%02d:%02d", tz_offset_minutes >= 0 ? '+' : '-', abs_offset / 60,
				         abs_offset % 60);
				oss << buf;
			}
		}
	}
	return oss.str();
}

int64_t DateTimeValue::to_julian_day() const {
	// Julian Day Number calculation
	int64_t a = (14 - month) / 12;
	int64_t y = year + 4800 - a;
	int64_t m = month + 12 * a - 3;
	return day + (153 * m + 2) / 5 + 365 * y + y / 4 - y / 100 + y / 400 - 32045;
}

int64_t DateTimeValue::to_epoch_millis() const {
	int64_t jdn = to_julian_day();
	int64_t unix_jdn = 2440588; // Jan 1, 1970
	int64_t days = jdn - unix_jdn;
	return days * 86400000LL + hour * 3600000LL + minute * 60000LL + second * 1000LL + millisecond;
}

bool DateTimeValue::operator<(const DateTimeValue &other) const {
	return compare_at_precision(other, Precision::Millisecond) < 0;
}

bool DateTimeValue::operator<=(const DateTimeValue &other) const {
	return compare_at_precision(other, Precision::Millisecond) <= 0;
}

bool DateTimeValue::operator==(const DateTimeValue &other) const {
	return compare_at_precision(other, Precision::Millisecond) == 0;
}

bool DateTimeValue::operator>(const DateTimeValue &other) const {
	return compare_at_precision(other, Precision::Millisecond) > 0;
}

bool DateTimeValue::operator>=(const DateTimeValue &other) const {
	return compare_at_precision(other, Precision::Millisecond) >= 0;
}

bool DateTimeValue::operator!=(const DateTimeValue &other) const {
	return compare_at_precision(other, Precision::Millisecond) != 0;
}

int DateTimeValue::compare_at_precision(const DateTimeValue &other, Precision prec) const {
	if (year != other.year) {
		return year < other.year ? -1 : 1;
	}
	if (prec == Precision::Year) {
		return 0;
	}
	if (month != other.month) {
		return month < other.month ? -1 : 1;
	}
	if (prec == Precision::Month) {
		return 0;
	}
	if (day != other.day) {
		return day < other.day ? -1 : 1;
	}
	if (prec == Precision::Day) {
		return 0;
	}
	if (hour != other.hour) {
		return hour < other.hour ? -1 : 1;
	}
	if (prec == Precision::Hour) {
		return 0;
	}
	if (minute != other.minute) {
		return minute < other.minute ? -1 : 1;
	}
	if (prec == Precision::Minute) {
		return 0;
	}
	if (second != other.second) {
		return second < other.second ? -1 : 1;
	}
	if (prec == Precision::Second) {
		return 0;
	}
	if (millisecond != other.millisecond) {
		return millisecond < other.millisecond ? -1 : 1;
	}
	return 0;
}

} // namespace cql
