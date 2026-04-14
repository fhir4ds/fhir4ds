#include "cql/datetime.hpp"
#include <cstdlib>
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

Optional<DateTimeValue> DateTimeValue::parse(const std::string &str) {
	if (str.empty()) {
		return NullOpt<DateTimeValue>();
	}

	DateTimeValue dt;
	const char *s = str.c_str();
	char *end;

	// Parse year
	dt.year = static_cast<int32_t>(std::strtol(s, &end, 10));
	if (end == s || dt.year < 0) {
		return NullOpt<DateTimeValue>();
	}
	dt.precision = Precision::Year;

	if (*end == '\0') {
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
	if (*end != '-') {
		return NullOpt<DateTimeValue>();
	}
	s = end + 1;

	// Parse day
	dt.day = static_cast<int32_t>(std::strtol(s, &end, 10));
	if (end == s || dt.day < 1 || dt.day > 31) {
		return NullOpt<DateTimeValue>();
	}
	dt.precision = Precision::Day;

	if (*end == '\0') {
		return dt;
	}

	// Parse time component
	// Accept both 'T' (ISO 8601) and ' ' (DuckDB CAST(TIMESTAMP AS VARCHAR) output)
	if (*end == 'T' || *end == ' ') {
		dt.has_time = true;
		s = end + 1;

		dt.hour = static_cast<int32_t>(std::strtol(s, &end, 10));
		dt.precision = Precision::Hour;
		if (*end == ':') {
			s = end + 1;
			dt.minute = static_cast<int32_t>(std::strtol(s, &end, 10));
			dt.precision = Precision::Minute;
			if (*end == ':') {
				s = end + 1;
				dt.second = static_cast<int32_t>(std::strtol(s, &end, 10));
				dt.precision = Precision::Second;
				if (*end == '.') {
					s = end + 1;
					dt.millisecond = static_cast<int32_t>(std::strtol(s, &end, 10));
					dt.precision = Precision::Millisecond;
					// Handle various fractional second lengths
					int digits = static_cast<int>(end - s);
					if (digits == 1) {
						dt.millisecond *= 100;
					} else if (digits == 2) {
						dt.millisecond *= 10;
					}
				}
			}
		}

		// Parse timezone
		if (*end == 'Z') {
			dt.has_tz = true;
			dt.tz_offset_minutes = 0;
		} else if (*end == '+' || *end == '-') {
			dt.has_tz = true;
			int sign = (*end == '+') ? 1 : -1;
			s = end + 1;
			int tz_hour = static_cast<int>(std::strtol(s, &end, 10));
			int tz_min = 0;
			if (*end == ':') {
				s = end + 1;
				tz_min = static_cast<int>(std::strtol(s, &end, 10));
			}
			dt.tz_offset_minutes = sign * (tz_hour * 60 + tz_min);
		}
	}

	return dt;
}

std::string DateTimeValue::to_string() const {
	std::ostringstream oss;
	char buf[32];
	snprintf(buf, sizeof(buf), "%04d", year);
	oss << buf;

	if (precision >= Precision::Month) {
		snprintf(buf, sizeof(buf), "-%02d", month);
		oss << buf;
	}
	if (precision >= Precision::Day) {
		snprintf(buf, sizeof(buf), "-%02d", day);
		oss << buf;
	}
	if (has_time) {
		snprintf(buf, sizeof(buf), "T%02d:%02d:%02d", hour, minute, second);
		oss << buf;
		if (millisecond > 0) {
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
	int a = (14 - month) / 12;
	int y = year + 4800 - a;
	int m = month + 12 * a - 3;
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
