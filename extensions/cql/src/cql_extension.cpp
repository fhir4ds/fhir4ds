#define DUCKDB_EXTENSION_MAIN

#include "cql_extension.hpp"
#include "cql/age.hpp"
#include "cql/aggregate.hpp"
#include "cql/boundary.hpp"
#include "cql/clinical.hpp"
#include "cql/datetime.hpp"
#include "cql/interval.hpp"
#include "cql/math.hpp"
#include "cql/logical.hpp"
#include "cql/quantity.hpp"
#include "cql/ratio.hpp"
#include "cql/valueset.hpp"
#include "yyjson.hpp"

#include "duckdb.hpp"
#include "duckdb/common/exception.hpp"
#include "duckdb/common/types/value.hpp"
#include "duckdb/function/scalar_function.hpp"
#include <algorithm>
#include <cctype>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <iomanip>
#include <limits>
#include <mutex>
#include <regex>
#include <sstream>
#include <stdexcept>
#include <unordered_map>
#include <vector>

namespace duckdb {

// =====================================================================
// Named constants for CQL datetime/duration calculations
// =====================================================================
static const std::string CQL_MIN_DATETIME = "0001-01-01T00:00:00.000+00:00";
static const std::string CQL_MAX_DATETIME = "9999-12-31T23:59:59.999+00:00";
static const std::string CQL_MIN_DATE = "0001-01-01";
static const std::string CQL_MAX_DATE = "9999-12-31";
static const std::string CQL_MIN_TIME = "T00:00:00.000";
static const std::string CQL_MAX_TIME = "T23:59:59.999";
static const std::string CQL_MIN_INTEGER = "-2147483648";
static const std::string CQL_MAX_INTEGER = "2147483647";
static const std::string CQL_MIN_DECIMAL = "-99999999999999999999.99999999";
static const std::string CQL_MAX_DECIMAL = "99999999999999999999.99999999";

// =====================================================================
// Named constants for time unit conversions (replacing magic numbers)
// =====================================================================
static constexpr int64_t MS_PER_SECOND = 1000LL;
static constexpr int64_t MS_PER_MINUTE = 60000LL;
static constexpr int64_t MS_PER_HOUR = 3600000LL;
static constexpr int64_t MS_PER_DAY = 86400000LL;
static constexpr double DAYS_PER_YEAR = 365.25;
static constexpr double DAYS_PER_MONTH = 30.4375;

static int CqlDaysInMonth(int year, int month) {
	static const int dim[] = {0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31};
	if (month < 1 || month > 12) {
		return 0;
	}
	if (month == 2 && (year % 4 == 0 && (year % 100 != 0 || year % 400 == 0))) {
		return 29;
	}
	return dim[month];
}

static int64_t FloorDiv(int64_t a, int64_t b) {
	int64_t q = a / b;
	int64_t r = a % b;
	if (r != 0 && ((r > 0) != (b > 0))) {
		--q;
	}
	return q;
}

static cql::DateTimeValue AddCalendarMonths(const cql::DateTimeValue &value, int64_t months) {
	cql::DateTimeValue result = value;
	int64_t month_index = static_cast<int64_t>(value.year) * 12 + (value.month - 1) + months;
	int64_t year = FloorDiv(month_index, 12);
	int64_t month_zero = month_index - year * 12;
	result.year = static_cast<int32_t>(year);
	result.month = static_cast<int32_t>(month_zero + 1);
	result.day = std::min<int32_t>(value.day, CqlDaysInMonth(result.year, result.month));
	return result;
}

static int64_t DurationInCalendarMonths(const cql::DateTimeValue &start, const cql::DateTimeValue &end) {
	if (end < start) {
		return -DurationInCalendarMonths(end, start);
	}
	int64_t months = (static_cast<int64_t>(end.year) - start.year) * 12 + (end.month - start.month);
	if (AddCalendarMonths(start, months) > end) {
		--months;
	}
	return months;
}

static int64_t DurationInCalendarYears(const cql::DateTimeValue &start, const cql::DateTimeValue &end) {
	if (end < start) {
		return -DurationInCalendarYears(end, start);
	}
	int64_t years = static_cast<int64_t>(end.year) - start.year;
	if (AddCalendarMonths(start, years * 12) > end) {
		--years;
	}
	return years;
}

static int64_t ToEpochMillisForElapsed(const cql::DateTimeValue &value) {
	int64_t millis = value.to_epoch_millis();
	if (value.has_tz) {
		millis -= static_cast<int64_t>(value.tz_offset_minutes) * MS_PER_MINUTE;
	}
	return millis;
}

static cql::DateTimeValue AddYears(const cql::DateTimeValue &dt, int32_t years);
static cql::DateTimeValue AddMonths(const cql::DateTimeValue &dt, int32_t months);
static cql::DateTimeValue AddDays(const cql::DateTimeValue &dt, int64_t days);
static cql::DateTimeValue AddMilliseconds(const cql::DateTimeValue &dt, int64_t millis);

// =====================================================================
// CQL regex helpers
// =====================================================================
static bool CqlRegexHasReDoSRisk(const std::string &pattern) {
	for (size_t i = 0; i < pattern.size(); ++i) {
		if (pattern[i] != '(' || (i > 0 && pattern[i - 1] == '\\')) {
			continue;
		}
		bool in_bracket = false;
		bool has_inner_quantifier = false;
		bool has_alternation = false;
		for (size_t j = i + 1; j < pattern.size(); ++j) {
			char c = pattern[j];
			if (c == '\\' && j + 1 < pattern.size()) {
				++j;
				continue;
			}
			if (c == '[') {
				in_bracket = true;
				continue;
			}
			if (c == ']') {
				in_bracket = false;
				continue;
			}
			if (in_bracket) {
				continue;
			}
			if (c == '(') {
				break;
			}
			if (c == ')') {
				if (j + 1 < pattern.size() && (pattern[j + 1] == '+' || pattern[j + 1] == '*')) {
					return has_inner_quantifier || has_alternation;
				}
				break;
			}
			if (c == '+' || c == '*') {
				has_inner_quantifier = true;
			} else if (c == '|') {
				has_alternation = true;
			}
		}
	}
	return false;
}

static bool CqlRegexAllowed(const std::string &pattern) {
	static constexpr size_t MAX_CQL_REGEX_LENGTH = 1000;
	return pattern.size() <= MAX_CQL_REGEX_LENGTH && !CqlRegexHasReDoSRisk(pattern);
}

static std::string NormalizeCqlRegex(const std::string &pattern) {
	static const std::string utf8_codepoint =
	    "(?:[\\x00-\\x7F]|[\\xC2-\\xDF][\\x80-\\xBF]|[\\xE0-\\xEF][\\x80-\\xBF]{2}|[\\xF0-\\xF4][\\x80-\\xBF]{3})";
	std::string normalized;
	bool in_bracket = false;
	for (size_t i = 0; i < pattern.size(); ++i) {
		if (pattern[i] == '\\' && i + 1 < pattern.size()) {
			normalized += pattern[i];
			normalized += pattern[i + 1];
			++i;
		} else if (pattern[i] == '[') {
			in_bracket = true;
			normalized += pattern[i];
		} else if (pattern[i] == ']') {
			in_bracket = false;
			normalized += pattern[i];
		} else if (pattern[i] == '.' && !in_bracket) {
			normalized += utf8_codepoint;
		} else {
			normalized += pattern[i];
		}
	}
	return normalized;
}

static cql::Optional<std::regex> CompileCqlRegex(const std::string &pattern) {
	if (!CqlRegexAllowed(pattern)) {
		return cql::NullOpt<std::regex>();
	}
	try {
		return cql::MakeOptional(std::regex(NormalizeCqlRegex(pattern), std::regex_constants::ECMAScript));
	} catch (const std::exception &) {
		return cql::NullOpt<std::regex>();
	}
}

static size_t NextUtf8Codepoint(const std::string &s, size_t pos) {
	if (pos >= s.size()) {
		return pos;
	}
	unsigned char c = static_cast<unsigned char>(s[pos]);
	if (c < 0x80) {
		return pos + 1;
	}
	if ((c & 0xE0) == 0xC0 && pos + 1 < s.size()) {
		return pos + 2;
	}
	if ((c & 0xF0) == 0xE0 && pos + 2 < s.size()) {
		return pos + 3;
	}
	if ((c & 0xF8) == 0xF0 && pos + 3 < s.size()) {
		return pos + 4;
	}
	return pos + 1;
}

static std::string CqlReplacementToStdRegex(const std::string &replacement) {
	std::string out;
	for (size_t i = 0; i < replacement.size(); ++i) {
		char c = replacement[i];
		if (c == '\\' && i + 1 < replacement.size()) {
			char next = replacement[i + 1];
			if (next == '$') {
				out += "$$";
			} else if (next == '\\') {
				out += "\\";
			} else {
				out += "\\";
				out += next;
			}
			++i;
		} else if (c == '$') {
			if (i + 1 < replacement.size() && std::isdigit(static_cast<unsigned char>(replacement[i + 1]))) {
				out += c;
			} else {
				out += "$$";
			}
		} else {
			out += c;
		}
	}
	return out;
}

static void CqlRegexMatchesFunc(DataChunk &args, ExpressionState &state, Vector &result) {
	idx_t count = args.size();
	UnifiedVectorFormat s_data, pattern_data;
	args.data[0].ToUnifiedFormat(count, s_data);
	args.data[1].ToUnifiedFormat(count, pattern_data);
	auto s_vals = UnifiedVectorFormat::GetData<string_t>(s_data);
	auto pattern_vals = UnifiedVectorFormat::GetData<string_t>(pattern_data);
	result.SetVectorType(VectorType::FLAT_VECTOR);
	auto result_data = FlatVector::GetData<bool>(result);
	auto &result_mask = FlatVector::Validity(result);
	for (idx_t i = 0; i < count; i++) {
		auto s_idx = s_data.sel->get_index(i);
		auto p_idx = pattern_data.sel->get_index(i);
		if (!s_data.validity.RowIsValid(s_idx) || !pattern_data.validity.RowIsValid(p_idx)) {
			result_mask.SetInvalid(i);
			continue;
		}
		auto re = CompileCqlRegex(pattern_vals[p_idx].GetString());
		if (!re) {
			result_mask.SetInvalid(i);
			continue;
		}
		try {
			std::string input = s_vals[s_idx].GetString();
			result_data[i] = std::regex_search(input, *re);
		} catch (const std::exception &) {
			result_mask.SetInvalid(i);
		}
	}
}

static void CqlRegexReplaceMatchesFunc(DataChunk &args, ExpressionState &state, Vector &result) {
	idx_t count = args.size();
	UnifiedVectorFormat s_data, pattern_data, replacement_data;
	args.data[0].ToUnifiedFormat(count, s_data);
	args.data[1].ToUnifiedFormat(count, pattern_data);
	args.data[2].ToUnifiedFormat(count, replacement_data);
	auto s_vals = UnifiedVectorFormat::GetData<string_t>(s_data);
	auto pattern_vals = UnifiedVectorFormat::GetData<string_t>(pattern_data);
	auto replacement_vals = UnifiedVectorFormat::GetData<string_t>(replacement_data);
	result.SetVectorType(VectorType::FLAT_VECTOR);
	auto result_data = FlatVector::GetData<string_t>(result);
	auto &result_mask = FlatVector::Validity(result);
	for (idx_t i = 0; i < count; i++) {
		auto s_idx = s_data.sel->get_index(i);
		auto p_idx = pattern_data.sel->get_index(i);
		auto r_idx = replacement_data.sel->get_index(i);
		if (!s_data.validity.RowIsValid(s_idx) || !pattern_data.validity.RowIsValid(p_idx) ||
		    !replacement_data.validity.RowIsValid(r_idx)) {
			result_mask.SetInvalid(i);
			continue;
		}
		auto re = CompileCqlRegex(pattern_vals[p_idx].GetString());
		if (!re) {
			result_mask.SetInvalid(i);
			continue;
		}
		try {
			std::string input = s_vals[s_idx].GetString();
			auto replacement = CqlReplacementToStdRegex(replacement_vals[r_idx].GetString());
			auto replaced = std::regex_replace(input, *re, replacement);
			result_data[i] = StringVector::AddString(result, replaced);
		} catch (const std::exception &) {
			result_mask.SetInvalid(i);
		}
	}
}

static void CqlRegexSplitOnMatchesFunc(DataChunk &args, ExpressionState &state, Vector &result) {
	idx_t count = args.size();
	UnifiedVectorFormat s_data, pattern_data;
	args.data[0].ToUnifiedFormat(count, s_data);
	args.data[1].ToUnifiedFormat(count, pattern_data);
	auto s_vals = UnifiedVectorFormat::GetData<string_t>(s_data);
	auto pattern_vals = UnifiedVectorFormat::GetData<string_t>(pattern_data);
	auto &result_mask = FlatVector::Validity(result);
	std::vector<idx_t> row_offsets(count);
	std::vector<idx_t> row_counts(count);
	std::vector<bool> row_null(count, false);
	idx_t total_size = 0;
	for (idx_t i = 0; i < count; i++) {
		auto s_idx = s_data.sel->get_index(i);
		auto p_idx = pattern_data.sel->get_index(i);
		if (!s_data.validity.RowIsValid(s_idx) || !pattern_data.validity.RowIsValid(p_idx)) {
			row_offsets[i] = total_size;
			row_counts[i] = 0;
			row_null[i] = true;
			continue;
		}
		std::string s = s_vals[s_idx].GetString();
		std::string pattern = pattern_vals[p_idx].GetString();
		row_offsets[i] = total_size;
		try {
			if (pattern.empty()) {
				size_t pos = 0;
				while (pos < s.size()) {
					size_t next = NextUtf8Codepoint(s, pos);
					ListVector::PushBack(result, Value(s.substr(pos, next - pos)));
					pos = next;
					total_size++;
				}
				row_counts[i] = total_size - row_offsets[i];
				continue;
			}
			auto re = CompileCqlRegex(pattern);
			if (!re) {
				row_counts[i] = 0;
				row_null[i] = true;
				continue;
			}
			size_t last = 0;
			for (std::sregex_iterator it(s.begin(), s.end(), *re), end; it != end; ++it) {
				const auto &match = *it;
				size_t pos = static_cast<size_t>(match.position());
				size_t len = static_cast<size_t>(match.length());
				ListVector::PushBack(result, Value(s.substr(last, pos - last)));
				total_size++;
				last = pos + len;
			}
			ListVector::PushBack(result, Value(s.substr(last)));
			total_size++;
			row_counts[i] = total_size - row_offsets[i];
		} catch (const std::exception &) {
			row_counts[i] = 0;
			row_null[i] = true;
		}
	}
	auto list_entries = ListVector::GetData(result);
	for (idx_t i = 0; i < count; i++) {
		list_entries[i] = {row_offsets[i], row_counts[i]};
		if (row_null[i]) {
			result_mask.SetInvalid(i);
		}
	}
	ListVector::SetListSize(result, total_size);
}

// =====================================================================
// Helper: get current date for age calculations
// =====================================================================
static cql::DateTimeValue GetToday() {
	auto now = std::chrono::system_clock::now();
	auto epoch = now.time_since_epoch();
	auto total_seconds = std::chrono::duration_cast<std::chrono::seconds>(epoch).count();
	// Convert epoch seconds to date components
	int64_t days_since_epoch = total_seconds / 86400;
	// Civil from days algorithm (Howard Hinnant)
	days_since_epoch += 719468;
	int64_t era = (days_since_epoch >= 0 ? days_since_epoch : days_since_epoch - 146096) / 146097;
	int64_t doe = days_since_epoch - era * 146097;
	int64_t yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
	int64_t y = yoe + era * 400;
	int64_t doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
	int64_t mp = (5 * doy + 2) / 153;
	int64_t d = doy - (153 * mp + 2) / 5 + 1;
	int64_t m = mp + (mp < 10 ? 3 : -9);
	y += (m <= 2 ? 1 : 0);

	cql::DateTimeValue today;
	today.year = static_cast<int32_t>(y);
	today.month = static_cast<int32_t>(m);
	today.day = static_cast<int32_t>(d);
	return today;
}

// =====================================================================
// Macro for simple two-string-input → BIGINT functions
// =====================================================================
#define DEFINE_TWO_STR_BIGINT_UDF(FuncName, body)                                                                      \
	static void FuncName(DataChunk &args, ExpressionState &state, Vector &result) {                                    \
		idx_t count = args.size();                                                                                     \
		UnifiedVectorFormat a_data, b_data;                                                                            \
		args.data[0].ToUnifiedFormat(count, a_data);                                                                   \
		args.data[1].ToUnifiedFormat(count, b_data);                                                                   \
		auto a_vals = UnifiedVectorFormat::GetData<string_t>(a_data);                                                  \
		auto b_vals = UnifiedVectorFormat::GetData<string_t>(b_data);                                                  \
		result.SetVectorType(VectorType::FLAT_VECTOR);                                                                 \
		auto result_data = FlatVector::GetData<int64_t>(result);                                                       \
		auto &result_mask = FlatVector::Validity(result);                                                              \
		for (idx_t i = 0; i < count; i++) {                                                                            \
			auto a_idx = a_data.sel->get_index(i);                                                                     \
			auto b_idx = b_data.sel->get_index(i);                                                                     \
			if (!a_data.validity.RowIsValid(a_idx) || !b_data.validity.RowIsValid(b_idx)) {                            \
				result_mask.SetInvalid(i);                                                                             \
				continue;                                                                                              \
			}                                                                                                          \
			auto a_str = a_vals[a_idx].GetString();                                                                    \
			auto b_str = b_vals[b_idx].GetString();                                                                    \
			auto a_dt = cql::DateTimeValue::parse(a_str);                                                              \
			auto b_dt = cql::DateTimeValue::parse(b_str);                                                              \
			if (!a_dt || !b_dt) {                                                                                      \
				result_mask.SetInvalid(i);                                                                             \
				continue;                                                                                              \
			}                                                                                                          \
			body                                                                                                       \
		}                                                                                                              \
	}

// =====================================================================
// Macro for two-string-input → BOOLEAN functions
// =====================================================================
#define DEFINE_TWO_STR_BOOL_UDF(FuncName, body)                                                                        \
	static void FuncName(DataChunk &args, ExpressionState &state, Vector &result) {                                    \
		idx_t count = args.size();                                                                                     \
		UnifiedVectorFormat a_data, b_data;                                                                            \
		args.data[0].ToUnifiedFormat(count, a_data);                                                                   \
		args.data[1].ToUnifiedFormat(count, b_data);                                                                   \
		auto a_vals = UnifiedVectorFormat::GetData<string_t>(a_data);                                                  \
		auto b_vals = UnifiedVectorFormat::GetData<string_t>(b_data);                                                  \
		result.SetVectorType(VectorType::FLAT_VECTOR);                                                                 \
		auto result_data = FlatVector::GetData<bool>(result);                                                          \
		auto &result_mask = FlatVector::Validity(result);                                                              \
		for (idx_t i = 0; i < count; i++) {                                                                            \
			auto a_idx = a_data.sel->get_index(i);                                                                     \
			auto b_idx = b_data.sel->get_index(i);                                                                     \
			if (!a_data.validity.RowIsValid(a_idx) || !b_data.validity.RowIsValid(b_idx)) {                            \
				result_mask.SetInvalid(i);                                                                             \
				continue;                                                                                              \
			}                                                                                                          \
			auto a_str = a_vals[a_idx].GetString();                                                                    \
			auto b_str = b_vals[b_idx].GetString();                                                                    \
			body                                                                                                       \
		}                                                                                                              \
	}

// =====================================================================
// Macro for one-string-input → VARCHAR functions
// =====================================================================
#define DEFINE_ONE_STR_STR_UDF(FuncName, body)                                                                         \
	static void FuncName(DataChunk &args, ExpressionState &state, Vector &result) {                                    \
		idx_t count = args.size();                                                                                     \
		UnifiedVectorFormat a_data;                                                                                    \
		args.data[0].ToUnifiedFormat(count, a_data);                                                                   \
		auto a_vals = UnifiedVectorFormat::GetData<string_t>(a_data);                                                  \
		result.SetVectorType(VectorType::FLAT_VECTOR);                                                                 \
		auto result_data = FlatVector::GetData<string_t>(result);                                                      \
		auto &result_mask = FlatVector::Validity(result);                                                              \
		for (idx_t i = 0; i < count; i++) {                                                                            \
			auto a_idx = a_data.sel->get_index(i);                                                                     \
			if (!a_data.validity.RowIsValid(a_idx)) {                                                                  \
				result_mask.SetInvalid(i);                                                                             \
				continue;                                                                                              \
			}                                                                                                          \
			auto a_str = a_vals[a_idx].GetString();                                                                    \
			body                                                                                                       \
		}                                                                                                              \
	}

// =====================================================================
// Macro for two-string-input → VARCHAR functions
// =====================================================================
#define DEFINE_TWO_STR_STR_UDF(FuncName, body)                                                                         \
	static void FuncName(DataChunk &args, ExpressionState &state, Vector &result) {                                    \
		idx_t count = args.size();                                                                                     \
		UnifiedVectorFormat a_data, b_data;                                                                            \
		args.data[0].ToUnifiedFormat(count, a_data);                                                                   \
		args.data[1].ToUnifiedFormat(count, b_data);                                                                   \
		auto a_vals = UnifiedVectorFormat::GetData<string_t>(a_data);                                                  \
		auto b_vals = UnifiedVectorFormat::GetData<string_t>(b_data);                                                  \
		result.SetVectorType(VectorType::FLAT_VECTOR);                                                                 \
		auto result_data = FlatVector::GetData<string_t>(result);                                                      \
		auto &result_mask = FlatVector::Validity(result);                                                              \
		for (idx_t i = 0; i < count; i++) {                                                                            \
			auto a_idx = a_data.sel->get_index(i);                                                                     \
			auto b_idx = b_data.sel->get_index(i);                                                                     \
			if (!a_data.validity.RowIsValid(a_idx) || !b_data.validity.RowIsValid(b_idx)) {                            \
				result_mask.SetInvalid(i);                                                                             \
				continue;                                                                                              \
			}                                                                                                          \
			auto a_str = a_vals[a_idx].GetString();                                                                    \
			auto b_str = b_vals[b_idx].GetString();                                                                    \
			body                                                                                                       \
		}                                                                                                              \
	}

// =====================================================================
// Age UDFs
// =====================================================================
#define DEFINE_AGE_UDF(FuncName, method_call)                                                                           \
	static void FuncName(DataChunk &args, ExpressionState &state, Vector &result) {                                    \
		idx_t count = args.size();                                                                                     \
		UnifiedVectorFormat res_data;                                                                                   \
		args.data[0].ToUnifiedFormat(count, res_data);                                                                 \
		auto resources = UnifiedVectorFormat::GetData<string_t>(res_data);                                             \
		result.SetVectorType(VectorType::FLAT_VECTOR);                                                                 \
		auto result_data = FlatVector::GetData<int64_t>(result);                                                       \
		auto &result_mask = FlatVector::Validity(result);                                                              \
		auto today = GetToday();                                                                                       \
		for (idx_t i = 0; i < count; i++) {                                                                            \
			auto idx = res_data.sel->get_index(i);                                                                     \
			if (!res_data.validity.RowIsValid(idx)) {                                                                  \
				result_mask.SetInvalid(i);                                                                             \
				continue;                                                                                              \
			}                                                                                                          \
			auto birth = cql::AgeCalculator::extract_birthdate(resources[idx].GetData(), resources[idx].GetSize());    \
			if (!birth) {                                                                                              \
				result_mask.SetInvalid(i);                                                                             \
				continue;                                                                                              \
			}                                                                                                          \
			auto age = method_call(*birth, today);                                                                     \
			if (!age) {                                                                                                \
				result_mask.SetInvalid(i);                                                                             \
			} else {                                                                                                   \
				result_data[i] = *age;                                                                                 \
			}                                                                                                          \
		}                                                                                                              \
	}

#define DEFINE_AGE_AT_UDF(FuncName, method_call)                                                                       \
	static void FuncName(DataChunk &args, ExpressionState &state, Vector &result) {                                    \
		idx_t count = args.size();                                                                                     \
		UnifiedVectorFormat res_data, date_data;                                                                       \
		args.data[0].ToUnifiedFormat(count, res_data);                                                                 \
		args.data[1].ToUnifiedFormat(count, date_data);                                                                \
		auto resources = UnifiedVectorFormat::GetData<string_t>(res_data);                                             \
		auto dates = UnifiedVectorFormat::GetData<string_t>(date_data);                                                \
		result.SetVectorType(VectorType::FLAT_VECTOR);                                                                 \
		auto result_data = FlatVector::GetData<int64_t>(result);                                                       \
		auto &result_mask = FlatVector::Validity(result);                                                              \
		for (idx_t i = 0; i < count; i++) {                                                                            \
			auto r_idx = res_data.sel->get_index(i);                                                                   \
			auto d_idx = date_data.sel->get_index(i);                                                                  \
			if (!res_data.validity.RowIsValid(r_idx) || !date_data.validity.RowIsValid(d_idx)) {                       \
				result_mask.SetInvalid(i);                                                                             \
				continue;                                                                                              \
			}                                                                                                          \
			auto birth = cql::AgeCalculator::extract_birthdate(resources[r_idx].GetData(),                             \
			                                                   resources[r_idx].GetSize());                            \
			auto as_of = cql::DateTimeValue::parse(dates[d_idx].GetString());                                          \
			if (!birth || !as_of) {                                                                                    \
				result_mask.SetInvalid(i);                                                                             \
				continue;                                                                                              \
			}                                                                                                          \
			auto age = method_call(*birth, *as_of);                                                                    \
			if (!age || *age < 0) {                                                                                \
				result_mask.SetInvalid(i);                                                                             \
			} else {                                                                                                   \
				result_data[i] = *age;                                                                                 \
			}                                                                                                          \
		}                                                                                                              \
	}

DEFINE_AGE_UDF(AgeInYearsFunc, cql::AgeCalculator::age_in_years)
DEFINE_AGE_UDF(AgeInMonthsFunc, cql::AgeCalculator::age_in_months)
DEFINE_AGE_UDF(AgeInDaysFunc, cql::AgeCalculator::age_in_days)
DEFINE_AGE_UDF(AgeInHoursFunc, cql::AgeCalculator::age_in_hours)
DEFINE_AGE_UDF(AgeInMinutesFunc, cql::AgeCalculator::age_in_minutes)
DEFINE_AGE_UDF(AgeInSecondsFunc, cql::AgeCalculator::age_in_seconds)
DEFINE_AGE_AT_UDF(AgeInYearsAtFunc, cql::AgeCalculator::age_in_years)
DEFINE_AGE_AT_UDF(AgeInMonthsAtFunc, cql::AgeCalculator::age_in_months)
DEFINE_AGE_AT_UDF(AgeInDaysAtFunc, cql::AgeCalculator::age_in_days)
DEFINE_AGE_AT_UDF(AgeInHoursAtFunc, cql::AgeCalculator::age_in_hours)
DEFINE_AGE_AT_UDF(AgeInMinutesAtFunc, cql::AgeCalculator::age_in_minutes)
DEFINE_AGE_AT_UDF(AgeInSecondsAtFunc, cql::AgeCalculator::age_in_seconds)

static cql::Optional<int64_t> AgeInWeeksValue(const cql::DateTimeValue &birth, const cql::DateTimeValue &as_of) {
	auto days = cql::AgeCalculator::age_in_days(birth, as_of);
	if (!days) {
		return cql::NullOpt<int64_t>();
	}
	return *days / 7;
}

DEFINE_AGE_UDF(AgeInWeeksFunc, AgeInWeeksValue)
DEFINE_AGE_AT_UDF(AgeInWeeksAtFunc, AgeInWeeksValue)

#define DEFINE_CALCULATE_AGE_UDF(FuncName, method_call)                                                                \
	static void FuncName(DataChunk &args, ExpressionState &state, Vector &result) {                                    \
		idx_t count = args.size();                                                                                     \
		UnifiedVectorFormat birth_data;                                                                                \
		args.data[0].ToUnifiedFormat(count, birth_data);                                                               \
		auto births = UnifiedVectorFormat::GetData<string_t>(birth_data);                                              \
		result.SetVectorType(VectorType::FLAT_VECTOR);                                                                 \
		auto result_data = FlatVector::GetData<int64_t>(result);                                                       \
		auto &result_mask = FlatVector::Validity(result);                                                              \
		auto today = GetToday();                                                                                       \
		for (idx_t i = 0; i < count; i++) {                                                                            \
			auto b_idx = birth_data.sel->get_index(i);                                                                 \
			if (!birth_data.validity.RowIsValid(b_idx)) {                                                              \
				result_mask.SetInvalid(i);                                                                             \
				continue;                                                                                              \
			}                                                                                                          \
			auto birth = cql::DateTimeValue::parse(births[b_idx].GetString());                                         \
			if (!birth) {                                                                                              \
				result_mask.SetInvalid(i);                                                                             \
				continue;                                                                                              \
			}                                                                                                          \
			auto age = method_call(*birth, today);                                                                     \
			if (!age || *age < 0) {                                                                                    \
				result_mask.SetInvalid(i);                                                                             \
			} else {                                                                                                   \
				result_data[i] = *age;                                                                                 \
			}                                                                                                          \
		}                                                                                                              \
	}

#define DEFINE_CALCULATE_AGE_AT_UDF(FuncName, method_call)                                                             \
	static void FuncName(DataChunk &args, ExpressionState &state, Vector &result) {                                    \
		idx_t count = args.size();                                                                                     \
		UnifiedVectorFormat birth_data, date_data;                                                                     \
		args.data[0].ToUnifiedFormat(count, birth_data);                                                               \
		args.data[1].ToUnifiedFormat(count, date_data);                                                                \
		auto births = UnifiedVectorFormat::GetData<string_t>(birth_data);                                              \
		auto dates = UnifiedVectorFormat::GetData<string_t>(date_data);                                                \
		result.SetVectorType(VectorType::FLAT_VECTOR);                                                                 \
		auto result_data = FlatVector::GetData<int64_t>(result);                                                       \
		auto &result_mask = FlatVector::Validity(result);                                                              \
		for (idx_t i = 0; i < count; i++) {                                                                            \
			auto b_idx = birth_data.sel->get_index(i);                                                                 \
			auto d_idx = date_data.sel->get_index(i);                                                                  \
			if (!birth_data.validity.RowIsValid(b_idx) || !date_data.validity.RowIsValid(d_idx)) {                     \
				result_mask.SetInvalid(i);                                                                             \
				continue;                                                                                              \
			}                                                                                                          \
			auto birth = cql::DateTimeValue::parse(births[b_idx].GetString());                                         \
			auto as_of = cql::DateTimeValue::parse(dates[d_idx].GetString());                                          \
			if (!birth || !as_of) {                                                                                    \
				result_mask.SetInvalid(i);                                                                             \
				continue;                                                                                              \
			}                                                                                                          \
			auto age = method_call(*birth, *as_of);                                                                    \
			if (!age || *age < 0) {                                                                                    \
				result_mask.SetInvalid(i);                                                                             \
			} else {                                                                                                   \
				result_data[i] = *age;                                                                                 \
			}                                                                                                          \
		}                                                                                                              \
	}

DEFINE_CALCULATE_AGE_UDF(CalculateAgeInYearsFunc, cql::AgeCalculator::age_in_years)
DEFINE_CALCULATE_AGE_UDF(CalculateAgeInMonthsFunc, cql::AgeCalculator::age_in_months)
DEFINE_CALCULATE_AGE_UDF(CalculateAgeInWeeksFunc, AgeInWeeksValue)
DEFINE_CALCULATE_AGE_UDF(CalculateAgeInDaysFunc, cql::AgeCalculator::age_in_days)
DEFINE_CALCULATE_AGE_UDF(CalculateAgeInHoursFunc, cql::AgeCalculator::age_in_hours)
DEFINE_CALCULATE_AGE_UDF(CalculateAgeInMinutesFunc, cql::AgeCalculator::age_in_minutes)
DEFINE_CALCULATE_AGE_UDF(CalculateAgeInSecondsFunc, cql::AgeCalculator::age_in_seconds)
DEFINE_CALCULATE_AGE_AT_UDF(CalculateAgeInYearsAtFunc, cql::AgeCalculator::age_in_years)
DEFINE_CALCULATE_AGE_AT_UDF(CalculateAgeInMonthsAtFunc, cql::AgeCalculator::age_in_months)
DEFINE_CALCULATE_AGE_AT_UDF(CalculateAgeInWeeksAtFunc, AgeInWeeksValue)
DEFINE_CALCULATE_AGE_AT_UDF(CalculateAgeInDaysAtFunc, cql::AgeCalculator::age_in_days)
DEFINE_CALCULATE_AGE_AT_UDF(CalculateAgeInHoursAtFunc, cql::AgeCalculator::age_in_hours)
DEFINE_CALCULATE_AGE_AT_UDF(CalculateAgeInMinutesAtFunc, cql::AgeCalculator::age_in_minutes)
DEFINE_CALCULATE_AGE_AT_UDF(CalculateAgeInSecondsAtFunc, cql::AgeCalculator::age_in_seconds)

// =====================================================================
// Datetime difference UDFs
// =====================================================================
DEFINE_TWO_STR_BIGINT_UDF(DifferenceInYearsFunc, {
	auto years = cql::AgeCalculator::diff_years(*a_dt, *b_dt);
	if (!years) {
		result_mask.SetInvalid(i);
	} else {
		result_data[i] = *years;
	}
})

DEFINE_TWO_STR_BIGINT_UDF(DifferenceInMonthsFunc, {
	auto months = cql::AgeCalculator::diff_months(*a_dt, *b_dt);
	if (!months) {
		result_mask.SetInvalid(i);
	} else {
		result_data[i] = *months;
	}
})

DEFINE_TWO_STR_BIGINT_UDF(DifferenceInDaysFunc, {
	auto days_diff = cql::AgeCalculator::diff_days(*a_dt, *b_dt);
	if (!days_diff) {
		result_mask.SetInvalid(i);
	} else {
		result_data[i] = *days_diff;
	}
})

DEFINE_TWO_STR_BIGINT_UDF(DifferenceInHoursFunc, {
	if (a_dt->has_tz != b_dt->has_tz) {
		result_mask.SetInvalid(i);
	} else {
		result_data[i] = (ToEpochMillisForElapsed(*b_dt) - ToEpochMillisForElapsed(*a_dt)) / MS_PER_HOUR;
	}
})

DEFINE_TWO_STR_BIGINT_UDF(DifferenceInMinutesFunc, {
	if (a_dt->has_tz != b_dt->has_tz) {
		result_mask.SetInvalid(i);
	} else {
		result_data[i] = (ToEpochMillisForElapsed(*b_dt) - ToEpochMillisForElapsed(*a_dt)) / MS_PER_MINUTE;
	}
})

DEFINE_TWO_STR_BIGINT_UDF(DifferenceInSecondsFunc, {
	if (a_dt->has_tz != b_dt->has_tz) {
		result_mask.SetInvalid(i);
	} else {
		result_data[i] = (ToEpochMillisForElapsed(*b_dt) - ToEpochMillisForElapsed(*a_dt)) / MS_PER_SECOND;
	}
})

DEFINE_TWO_STR_BIGINT_UDF(DifferenceInWeeksFunc, {
	auto days = cql::AgeCalculator::diff_days(*a_dt, *b_dt);
	if (!days) {
		result_mask.SetInvalid(i);
	} else {
		result_data[i] = *days / 7;
	}
})

DEFINE_TWO_STR_BIGINT_UDF(DifferenceInMillisecondsFunc, {
	if (a_dt->has_tz != b_dt->has_tz) {
		result_mask.SetInvalid(i);
	} else {
		result_data[i] = ToEpochMillisForElapsed(*b_dt) - ToEpochMillisForElapsed(*a_dt);
	}
})

DEFINE_TWO_STR_BIGINT_UDF(WeeksBetweenFunc, {
	// CQL §16.14: WeeksBetween counts *complete* 7-day periods.
	if (a_dt->has_tz != b_dt->has_tz) {
		result_mask.SetInvalid(i);
	} else {
		int64_t ms_diff = ToEpochMillisForElapsed(*b_dt) - ToEpochMillisForElapsed(*a_dt);
		result_data[i] = ms_diff / (MS_PER_DAY * 7);
	}
})

DEFINE_TWO_STR_BIGINT_UDF(MillisecondsBetweenFunc, {
	if (a_dt->has_tz != b_dt->has_tz) {
		result_mask.SetInvalid(i);
	} else {
		result_data[i] = ToEpochMillisForElapsed(*b_dt) - ToEpochMillisForElapsed(*a_dt);
	}
})

// date_diff equivalents (match Python's DaysBetween/MonthsBetween/etc. macros)
DEFINE_TWO_STR_BIGINT_UDF(YearsBetweenFunc, {
	// CQL §16.14: YearsBetween counts *complete* calendar years, not raw year subtraction.
	result_data[i] = DurationInCalendarYears(*a_dt, *b_dt);
})

DEFINE_TWO_STR_BIGINT_UDF(MonthsBetweenFunc, {
	// CQL §16.14: MonthsBetween counts *complete* months, not calendar boundary crossings.
	result_data[i] = DurationInCalendarMonths(*a_dt, *b_dt);
})

DEFINE_TWO_STR_BIGINT_UDF(DaysBetweenFunc, {
	if (a_dt->has_tz != b_dt->has_tz) {
		result_mask.SetInvalid(i);
	} else {
		int64_t ms_diff = ToEpochMillisForElapsed(*b_dt) - ToEpochMillisForElapsed(*a_dt);
		result_data[i] = ms_diff / MS_PER_DAY;
	}
})

DEFINE_TWO_STR_BIGINT_UDF(HoursBetweenFunc, {
	if (a_dt->has_tz != b_dt->has_tz) {
		result_mask.SetInvalid(i);
	} else {
		result_data[i] = (ToEpochMillisForElapsed(*b_dt) - ToEpochMillisForElapsed(*a_dt)) / MS_PER_HOUR;
	}
})

DEFINE_TWO_STR_BIGINT_UDF(MinutesBetweenFunc, {
	if (a_dt->has_tz != b_dt->has_tz) {
		result_mask.SetInvalid(i);
	} else {
		result_data[i] = (ToEpochMillisForElapsed(*b_dt) - ToEpochMillisForElapsed(*a_dt)) / MS_PER_MINUTE;
	}
})

DEFINE_TWO_STR_BIGINT_UDF(SecondsBetweenFunc, {
	if (a_dt->has_tz != b_dt->has_tz) {
		result_mask.SetInvalid(i);
	} else {
		result_data[i] = (ToEpochMillisForElapsed(*b_dt) - ToEpochMillisForElapsed(*a_dt)) / MS_PER_SECOND;
	}
})

// =====================================================================
// Interval UDFs
// =====================================================================
static bool BoundLooksLikeDateTime(const cql::BoundValue &bound) {
	if (bound.dt_val && bound.dt_val->has_time) {
		return true;
	}
	return bound.raw_str.find('T') != std::string::npos || bound.raw_str.find(' ') != std::string::npos;
}

static std::string MinimumForIntervalPointType(const cql::Interval &iv) {
	switch (iv.bound_type) {
	case cql::BoundType::Integer:
		return CQL_MIN_INTEGER;
	case cql::BoundType::Decimal:
		return CQL_MIN_DECIMAL;
	case cql::BoundType::DateTime:
		if (iv.high && BoundLooksLikeDateTime(*iv.high)) {
			return CQL_MIN_DATETIME;
		}
		if (iv.low && BoundLooksLikeDateTime(*iv.low)) {
			return CQL_MIN_DATETIME;
		}
		return CQL_MIN_DATE;
	case cql::BoundType::Time:
		return CQL_MIN_TIME;
	case cql::BoundType::Quantity:
		return "";
	}
	return "";
}

static std::string MaximumForIntervalPointType(const cql::Interval &iv) {
	switch (iv.bound_type) {
	case cql::BoundType::Integer:
		return CQL_MAX_INTEGER;
	case cql::BoundType::Decimal:
		return CQL_MAX_DECIMAL;
	case cql::BoundType::DateTime:
		if (iv.low && BoundLooksLikeDateTime(*iv.low)) {
			return CQL_MAX_DATETIME;
		}
		if (iv.high && BoundLooksLikeDateTime(*iv.high)) {
			return CQL_MAX_DATETIME;
		}
		return CQL_MAX_DATE;
	case cql::BoundType::Time:
		return CQL_MAX_TIME;
	case cql::BoundType::Quantity:
		return "";
	}
	return "";
}

static void IntervalStartFunc(DataChunk &args, ExpressionState &state, Vector &result) {
	idx_t count = args.size();
	UnifiedVectorFormat iv_data;
	args.data[0].ToUnifiedFormat(count, iv_data);
	auto intervals = UnifiedVectorFormat::GetData<string_t>(iv_data);

	result.SetVectorType(VectorType::FLAT_VECTOR);
	auto result_data = FlatVector::GetData<string_t>(result);
	auto &result_mask = FlatVector::Validity(result);

	for (idx_t i = 0; i < count; i++) {
		auto idx = iv_data.sel->get_index(i);
		if (!iv_data.validity.RowIsValid(idx)) {
			result_mask.SetInvalid(i);
			continue;
		}
		auto iv = cql::Interval::parse(intervals[idx].GetString());
		if (!iv) {
			result_mask.SetInvalid(i);
		} else if (!iv->low) {
			if (iv->low_closed && iv->high) {
				auto minimum = MinimumForIntervalPointType(*iv);
				if (minimum.empty()) {
					result_mask.SetInvalid(i);
				} else {
					result_data[i] = StringVector::AddString(result, minimum);
				}
			} else {
				result_mask.SetInvalid(i);
			}
		} else {
			result_data[i] = StringVector::AddString(result, iv->start_string());
		}
	}
}

static void IntervalEndFunc(DataChunk &args, ExpressionState &state, Vector &result) {
	idx_t count = args.size();
	UnifiedVectorFormat iv_data;
	args.data[0].ToUnifiedFormat(count, iv_data);
	auto intervals = UnifiedVectorFormat::GetData<string_t>(iv_data);

	result.SetVectorType(VectorType::FLAT_VECTOR);
	auto result_data = FlatVector::GetData<string_t>(result);
	auto &result_mask = FlatVector::Validity(result);

	for (idx_t i = 0; i < count; i++) {
		auto idx = iv_data.sel->get_index(i);
		if (!iv_data.validity.RowIsValid(idx)) {
			result_mask.SetInvalid(i);
			continue;
		}
		auto iv = cql::Interval::parse(intervals[idx].GetString());
		if (!iv) {
			result_mask.SetInvalid(i);
		} else if (!iv->high) {
			if (iv->high_closed && iv->low) {
				auto maximum = MaximumForIntervalPointType(*iv);
				if (maximum.empty()) {
					result_mask.SetInvalid(i);
				} else {
					result_data[i] = StringVector::AddString(result, maximum);
				}
			} else {
				result_mask.SetInvalid(i);
			}
		} else {
			result_data[i] = StringVector::AddString(result, iv->end_string());
		}
	}
}

static void IntervalWidthFunc(DataChunk &args, ExpressionState &state, Vector &result) {
	idx_t count = args.size();
	UnifiedVectorFormat iv_data;
	args.data[0].ToUnifiedFormat(count, iv_data);
	auto intervals = UnifiedVectorFormat::GetData<string_t>(iv_data);

	result.SetVectorType(VectorType::FLAT_VECTOR);
	auto result_data = FlatVector::GetData<string_t>(result);
	auto &result_mask = FlatVector::Validity(result);

	for (idx_t i = 0; i < count; i++) {
		auto idx = iv_data.sel->get_index(i);
		if (!iv_data.validity.RowIsValid(idx)) {
			result_mask.SetInvalid(i);
			continue;
		}
		auto iv = cql::Interval::parse(intervals[idx].GetString());
		if (!iv) {
			result_mask.SetInvalid(i);
			continue;
		}
		if (iv->bound_type == cql::BoundType::DateTime || iv->bound_type == cql::BoundType::Time) {
			throw InvalidInputException("Width is not defined for DateTime or Time intervals");
		}
		auto width = iv->width_string();
		if (!width) {
			result_mask.SetInvalid(i);
		} else {
			result_data[i] = StringVector::AddString(result, *width);
		}
	}
}

static bool LooksDateTimeLikeBound(const std::string &value) {
	return value.find('-') != std::string::npos || value.find('T') != std::string::npos ||
	       value.find(':') != std::string::npos;
}

static bool LooksFourDigitYear(const std::string &value) {
	if (value.size() != 4) {
		return false;
	}
	return std::all_of(value.begin(), value.end(), [](unsigned char c) { return std::isdigit(c); });
}

static cql::Optional<cql::BoundValue> DateTimeBoundFromString(const std::string &value) {
	auto dt = cql::DateTimeValue::parse(value);
	if (!dt) {
		return cql::NullOpt<cql::BoundValue>();
	}
	cql::BoundValue bound;
	bound.type = dt->is_time ? cql::BoundType::Time : cql::BoundType::DateTime;
	bound.dt_val = dt;
	bound.raw_str = value;
	return cql::Optional<cql::BoundValue>(bound);
}

static cql::Optional<cql::BoundValue> ParseIntervalBoundWithPeer(const std::string &value, bool peer_is_datetime) {
	if (peer_is_datetime && LooksFourDigitYear(value)) {
		auto dt_bound = DateTimeBoundFromString(value);
		if (dt_bound) {
			return dt_bound;
		}
	}
	return cql::BoundValue::from_string(value);
}

static cql::DateTimeValue DateTimeHighBoundary(cql::DateTimeValue value) {
	switch (value.precision) {
	case cql::DateTimeValue::Precision::Year:
		value.month = 12;
		value.day = 31;
		value.hour = 23;
		value.minute = 59;
		value.second = 59;
		value.millisecond = 999;
		value.has_time = true;
		break;
	case cql::DateTimeValue::Precision::Month:
		value.day = CqlDaysInMonth(value.year, value.month);
		value.hour = 23;
		value.minute = 59;
		value.second = 59;
		value.millisecond = 999;
		value.has_time = true;
		break;
	case cql::DateTimeValue::Precision::Day:
		value.hour = 23;
		value.minute = 59;
		value.second = 59;
		value.millisecond = 999;
		value.has_time = true;
		break;
	case cql::DateTimeValue::Precision::Hour:
		value.minute = 59;
		value.second = 59;
		value.millisecond = 999;
		value.has_time = true;
		break;
	case cql::DateTimeValue::Precision::Minute:
		value.second = 59;
		value.millisecond = 999;
		value.has_time = true;
		break;
	case cql::DateTimeValue::Precision::Second:
		value.millisecond = 999;
		value.has_time = true;
		break;
	case cql::DateTimeValue::Precision::Millisecond:
		break;
	}
	return value;
}

struct DateTimeBoundRange {
	int64_t low_ms;
	int64_t high_ms;
};

static cql::Optional<DateTimeBoundRange> DateTimeRangeForBound(const cql::BoundValue &bound) {
	if (bound.type != cql::BoundType::DateTime || !bound.dt_val) {
		return cql::NullOpt<DateTimeBoundRange>();
	}
	DateTimeBoundRange range;
	range.low_ms = bound.dt_val->to_epoch_millis();
	range.high_ms = DateTimeHighBoundary(*bound.dt_val).to_epoch_millis();
	return cql::Optional<DateTimeBoundRange>(range);
}

enum class CqlTriBool { KnownFalse, KnownTrue, Unknown, NotApplicable };

static CqlTriBool RangeLessOrEqual(const DateTimeBoundRange &left, const DateTimeBoundRange &right) {
	if (left.high_ms <= right.low_ms) {
		return CqlTriBool::KnownTrue;
	}
	if (left.low_ms > right.high_ms) {
		return CqlTriBool::KnownFalse;
	}
	return CqlTriBool::Unknown;
}

static CqlTriBool DateTimeOverlapsTriState(const cql::Interval &left, const cql::Interval &right) {
	if (!left.low || !left.high || !right.low || !right.high) {
		return CqlTriBool::NotApplicable;
	}
	auto left_low = DateTimeRangeForBound(*left.low);
	auto left_high = DateTimeRangeForBound(*left.high);
	auto right_low = DateTimeRangeForBound(*right.low);
	auto right_high = DateTimeRangeForBound(*right.high);
	if (!left_low || !left_high || !right_low || !right_high) {
		return CqlTriBool::NotApplicable;
	}

	auto left_starts_before_right_ends = RangeLessOrEqual(*left_low, *right_high);
	auto right_starts_before_left_ends = RangeLessOrEqual(*right_low, *left_high);
	if (left_starts_before_right_ends == CqlTriBool::KnownFalse ||
	    right_starts_before_left_ends == CqlTriBool::KnownFalse) {
		return CqlTriBool::KnownFalse;
	}
	if (left_starts_before_right_ends == CqlTriBool::KnownTrue &&
	    right_starts_before_left_ends == CqlTriBool::KnownTrue) {
		return CqlTriBool::KnownTrue;
	}
	return CqlTriBool::Unknown;
}

static bool IncomparableQuantityEndpoint(const cql::Optional<cql::BoundValue> &left,
                                         const cql::Optional<cql::BoundValue> &right) {
	if (!left || !right) {
		return false;
	}
	if (left->type != cql::BoundType::Quantity && right->type != cql::BoundType::Quantity) {
		return false;
	}
	return left->compare(*right) == -2;
}

static bool IntervalOverlapsQuantityUnknown(const cql::Interval &left, const cql::Interval &right) {
	return IncomparableQuantityEndpoint(right.high, left.low) ||
	       IncomparableQuantityEndpoint(left.high, right.low);
}

static bool IntervalContainsPointQuantityUnknown(const cql::Interval &interval, const cql::BoundValue &point) {
	cql::Optional<cql::BoundValue> point_value(point);
	return IncomparableQuantityEndpoint(interval.low, point_value) ||
	       IncomparableQuantityEndpoint(interval.high, point_value);
}

static bool IntervalIncludesQuantityUnknown(const cql::Interval &container, const cql::Interval &contained) {
	return IncomparableQuantityEndpoint(container.low, contained.low) ||
	       IncomparableQuantityEndpoint(container.high, contained.high);
}

static void IntervalContainsFunc(DataChunk &args, ExpressionState &state, Vector &result) {
	idx_t count = args.size();
	UnifiedVectorFormat a_data, b_data;
	args.data[0].ToUnifiedFormat(count, a_data);
	args.data[1].ToUnifiedFormat(count, b_data);
	auto a_vals = UnifiedVectorFormat::GetData<string_t>(a_data);
	auto b_vals = UnifiedVectorFormat::GetData<string_t>(b_data);
	result.SetVectorType(VectorType::FLAT_VECTOR);
	auto result_data = FlatVector::GetData<bool>(result);
	auto &result_mask = FlatVector::Validity(result);
	for (idx_t i = 0; i < count; i++) {
		auto a_idx = a_data.sel->get_index(i);
		auto b_idx = b_data.sel->get_index(i);
		if (!a_data.validity.RowIsValid(a_idx)) {
			result_data[i] = false;
			continue;
		}
		if (!b_data.validity.RowIsValid(b_idx)) {
			result_mask.SetInvalid(i);
			continue;
		}
		auto a_str = a_vals[a_idx].GetString();
		auto b_str = b_vals[b_idx].GetString();
		auto iv = cql::Interval::parse(a_str);
		if (!iv) {
			result_data[i] = false;
			continue;
		}
		if (cql::is_json_interval(b_str)) {
			auto other = cql::Interval::parse(b_str);
			if (other && IntervalIncludesQuantityUnknown(*iv, *other)) {
				result_mask.SetInvalid(i);
				continue;
			}
			result_data[i] = other ? iv->includes(*other) : false;
		} else {
			auto point = cql::parse_point_value(b_str);
			if (point && IntervalContainsPointQuantityUnknown(*iv, *point)) {
				result_mask.SetInvalid(i);
				continue;
			}
			result_data[i] = point ? iv->contains_point(*point) : false;
		}
	}
}

DEFINE_TWO_STR_BOOL_UDF(IntervalProperlyContainsFunc, {
	auto iv = cql::Interval::parse(a_str);
	if (!iv) {
		result_data[i] = false;
		continue;
	}
	if (cql::is_json_interval(b_str)) {
		auto other = cql::Interval::parse(b_str);
		if (other && IntervalIncludesQuantityUnknown(*iv, *other)) {
			result_mask.SetInvalid(i);
			continue;
		}
		result_data[i] = other ? iv->properly_includes(*other) : false;
	} else {
		auto point = cql::parse_point_value(b_str);
		if (point && IntervalContainsPointQuantityUnknown(*iv, *point)) {
			result_mask.SetInvalid(i);
			continue;
		}
		result_data[i] = point ? iv->properly_contains_point(*point) : false;
	}
})

static void IntervalOverlapsFunc(DataChunk &args, ExpressionState &state, Vector &result) {
	idx_t count = args.size();
	UnifiedVectorFormat a_data, b_data;
	args.data[0].ToUnifiedFormat(count, a_data);
	args.data[1].ToUnifiedFormat(count, b_data);
	auto a_vals = UnifiedVectorFormat::GetData<string_t>(a_data);
	auto b_vals = UnifiedVectorFormat::GetData<string_t>(b_data);
	result.SetVectorType(VectorType::FLAT_VECTOR);
	auto result_data = FlatVector::GetData<bool>(result);
	auto &result_mask = FlatVector::Validity(result);
	for (idx_t i = 0; i < count; i++) {
		auto a_idx = a_data.sel->get_index(i);
		auto b_idx = b_data.sel->get_index(i);
		if (!a_data.validity.RowIsValid(a_idx) || !b_data.validity.RowIsValid(b_idx)) {
			result_mask.SetInvalid(i);
			continue;
		}
		auto iv1 = cql::Interval::parse(a_vals[a_idx].GetString());
		auto iv2 = cql::Interval::parse(b_vals[b_idx].GetString());
		if (!iv1 || !iv2) {
			result_data[i] = false;
			continue;
		}
		auto tri = DateTimeOverlapsTriState(*iv1, *iv2);
		if (tri == CqlTriBool::Unknown) {
			result_mask.SetInvalid(i);
			continue;
		}
		if (tri == CqlTriBool::NotApplicable && IntervalOverlapsQuantityUnknown(*iv1, *iv2)) {
			result_mask.SetInvalid(i);
			continue;
		}
		result_data[i] = tri == CqlTriBool::NotApplicable ? iv1->overlaps(*iv2) : tri == CqlTriBool::KnownTrue;
	}
}

DEFINE_TWO_STR_BOOL_UDF(IntervalBeforeFunc, {
	auto iv1 = cql::Interval::parse(a_str);
	auto iv2 = cql::Interval::parse(b_str);
	result_data[i] = (iv1 && iv2) ? iv1->before(*iv2) : false;
})

DEFINE_TWO_STR_BOOL_UDF(IntervalAfterFunc, {
	auto iv1 = cql::Interval::parse(a_str);
	auto iv2 = cql::Interval::parse(b_str);
	result_data[i] = (iv1 && iv2) ? iv1->after(*iv2) : false;
})

DEFINE_TWO_STR_BOOL_UDF(IntervalMeetsFunc, {
	auto iv1 = cql::Interval::parse(a_str);
	auto iv2 = cql::Interval::parse(b_str);
	result_data[i] = (iv1 && iv2) ? iv1->meets(*iv2) : false;
})

DEFINE_TWO_STR_BOOL_UDF(IntervalIncludesFunc, {
	auto iv1 = cql::Interval::parse(a_str);
	auto iv2 = cql::Interval::parse(b_str);
	result_data[i] = (iv1 && iv2) ? iv1->includes(*iv2) : false;
})

DEFINE_TWO_STR_BOOL_UDF(IntervalIncludedInFunc, {
	auto iv1 = cql::Interval::parse(a_str);
	auto iv2 = cql::Interval::parse(b_str);
	if (iv1 && iv2 && iv1->low && iv2->low && iv1->low->dt_val && iv2->low->dt_val &&
	    iv1->low->compare(*iv2->low) == 0 && iv1->low->dt_val->precision != iv2->low->dt_val->precision) {
		result_mask.SetInvalid(i);
		continue;
	}
	if (iv1 && iv2 && iv1->high && iv2->high && iv1->high->dt_val && iv2->high->dt_val &&
	    iv1->high->compare(*iv2->high) == 0 && iv1->high->dt_val->precision != iv2->high->dt_val->precision) {
		result_mask.SetInvalid(i);
		continue;
	}
	result_data[i] = (iv1 && iv2) ? iv2->includes(*iv1) : false;
})

DEFINE_TWO_STR_BOOL_UDF(IntervalProperlyIncludesFunc, {
	auto iv1 = cql::Interval::parse(a_str);
	auto iv2 = cql::Interval::parse(b_str);
	result_data[i] = (iv1 && iv2) ? iv1->properly_includes(*iv2) : false;
})

static void IntervalProperlyIncludedInFunc(DataChunk &args, ExpressionState &state, Vector &result) {
	idx_t count = args.size();
	UnifiedVectorFormat a_data, b_data;
	args.data[0].ToUnifiedFormat(count, a_data);
	args.data[1].ToUnifiedFormat(count, b_data);
	auto a_vals = UnifiedVectorFormat::GetData<string_t>(a_data);
	auto b_vals = UnifiedVectorFormat::GetData<string_t>(b_data);
	result.SetVectorType(VectorType::FLAT_VECTOR);
	auto result_data = FlatVector::GetData<bool>(result);
	auto &result_mask = FlatVector::Validity(result);
	for (idx_t i = 0; i < count; i++) {
		auto a_idx = a_data.sel->get_index(i);
		auto b_idx = b_data.sel->get_index(i);
		if (!a_data.validity.RowIsValid(a_idx)) {
			result_mask.SetInvalid(i);
			continue;
		}
		auto iv1 = cql::Interval::parse(a_vals[a_idx].GetString());
		if (!iv1) {
			result_mask.SetInvalid(i);
			continue;
		}
		if (!b_data.validity.RowIsValid(b_idx)) {
			result_mask.SetInvalid(i);
			continue;
		}
		auto iv2 = cql::Interval::parse(b_vals[b_idx].GetString());
		result_data[i] = iv2 ? iv2->properly_includes(*iv1) : false;
	}
}

DEFINE_TWO_STR_BOOL_UDF(IntervalOverlapsBeforeFunc, {
	auto iv1 = cql::Interval::parse(a_str);
	auto iv2 = cql::Interval::parse(b_str);
	if (iv1 && iv2) {
		auto tri = DateTimeOverlapsTriState(*iv1, *iv2);
		if (tri == CqlTriBool::Unknown) {
			result_mask.SetInvalid(i);
			continue;
		}
		if (tri == CqlTriBool::KnownFalse) {
			result_data[i] = false;
			continue;
		}
		if (tri == CqlTriBool::NotApplicable && IntervalOverlapsQuantityUnknown(*iv1, *iv2)) {
			result_mask.SetInvalid(i);
			continue;
		}
	}
	result_data[i] = (iv1 && iv2) ? iv1->overlaps_before(*iv2) : false;
})

DEFINE_TWO_STR_BOOL_UDF(IntervalOverlapsAfterFunc, {
	auto iv1 = cql::Interval::parse(a_str);
	auto iv2 = cql::Interval::parse(b_str);
	if (iv1 && iv2) {
		auto tri = DateTimeOverlapsTriState(*iv1, *iv2);
		if (tri == CqlTriBool::Unknown) {
			result_mask.SetInvalid(i);
			continue;
		}
		if (tri == CqlTriBool::KnownFalse) {
			result_data[i] = false;
			continue;
		}
		if (tri == CqlTriBool::NotApplicable && IntervalOverlapsQuantityUnknown(*iv1, *iv2)) {
			result_mask.SetInvalid(i);
			continue;
		}
	}
	result_data[i] = (iv1 && iv2) ? iv1->overlaps_after(*iv2) : false;
})

DEFINE_TWO_STR_BOOL_UDF(IntervalMeetsBeforeFunc, {
	auto iv1 = cql::Interval::parse(a_str);
	auto iv2 = cql::Interval::parse(b_str);
	result_data[i] = (iv1 && iv2) ? iv1->meets_before(*iv2) : false;
})

DEFINE_TWO_STR_BOOL_UDF(IntervalMeetsAfterFunc, {
	auto iv1 = cql::Interval::parse(a_str);
	auto iv2 = cql::Interval::parse(b_str);
	result_data[i] = (iv1 && iv2) ? iv1->meets_after(*iv2) : false;
})

DEFINE_TWO_STR_BOOL_UDF(IntervalStartsSameFunc, {
	auto iv1 = cql::Interval::parse(a_str);
	auto iv2 = cql::Interval::parse(b_str);
	if (!iv1 || !iv2 || !iv1->low || !iv2->low || !iv1->high || !iv2->high) {
		result_mask.SetInvalid(i);
		continue;
	}
	result_data[i] = iv1->starts_same(*iv2);
})

DEFINE_TWO_STR_BOOL_UDF(IntervalEndsSameFunc, {
	auto iv1 = cql::Interval::parse(a_str);
	auto iv2 = cql::Interval::parse(b_str);
	if (!iv1 || !iv2 || !iv1->low || !iv2->low || !iv1->high || !iv2->high) {
		result_mask.SetInvalid(i);
		continue;
	}
	result_data[i] = iv1->ends_same(*iv2);
})

DEFINE_TWO_STR_BOOL_UDF(IntervalEqualsFunc, {
	auto iv1 = cql::Interval::parse(a_str);
	auto iv2 = cql::Interval::parse(b_str);
	if (!iv1 || !iv2) {
		result_mask.SetInvalid(i);
		continue;
	}
	result_data[i] = (*iv1 == *iv2);
})

static void IntervalEquivalentFunc(DataChunk &args, ExpressionState &state, Vector &result) {
	idx_t count = args.size();
	UnifiedVectorFormat a_data, b_data;
	args.data[0].ToUnifiedFormat(count, a_data);
	args.data[1].ToUnifiedFormat(count, b_data);
	auto a_vals = UnifiedVectorFormat::GetData<string_t>(a_data);
	auto b_vals = UnifiedVectorFormat::GetData<string_t>(b_data);
	result.SetVectorType(VectorType::FLAT_VECTOR);
	auto result_data = FlatVector::GetData<bool>(result);
	for (idx_t i = 0; i < count; i++) {
		auto a_idx = a_data.sel->get_index(i);
		auto b_idx = b_data.sel->get_index(i);
		bool a_null = !a_data.validity.RowIsValid(a_idx);
		bool b_null = !b_data.validity.RowIsValid(b_idx);
		if (a_null || b_null) {
			result_data[i] = a_null && b_null;
			continue;
		}
		auto iv1 = cql::Interval::parse(a_vals[a_idx].GetString());
		auto iv2 = cql::Interval::parse(b_vals[b_idx].GetString());
		result_data[i] = (iv1 && iv2) ? (*iv1 == *iv2) : false;
	}
}

// =====================================================================
// Precision-aware interval UDFs
// (interval, interval, precision) → BOOLEAN
// =====================================================================

static int IntervalPrecisionRank(cql::DateTimeValue::Precision precision) {
	switch (precision) {
	case cql::DateTimeValue::Precision::Year:
		return 0;
	case cql::DateTimeValue::Precision::Month:
		return 1;
	case cql::DateTimeValue::Precision::Day:
		return 2;
	case cql::DateTimeValue::Precision::Hour:
		return 3;
	case cql::DateTimeValue::Precision::Minute:
		return 4;
	case cql::DateTimeValue::Precision::Second:
		return 5;
	case cql::DateTimeValue::Precision::Millisecond:
		return 6;
	}
	return 6;
}

static cql::DateTimeValue::Precision IntervalPrecisionFromRank(int rank) {
	switch (rank) {
	case 0:
		return cql::DateTimeValue::Precision::Year;
	case 1:
		return cql::DateTimeValue::Precision::Month;
	case 2:
		return cql::DateTimeValue::Precision::Day;
	case 3:
		return cql::DateTimeValue::Precision::Hour;
	case 4:
		return cql::DateTimeValue::Precision::Minute;
	case 5:
		return cql::DateTimeValue::Precision::Second;
	default:
		return cql::DateTimeValue::Precision::Millisecond;
	}
}

static bool PrecisionPairUncertain(const cql::Optional<cql::BoundValue> &left,
                                   const cql::Optional<cql::BoundValue> &right,
                                   cql::DateTimeValue::Precision precision) {
	if (!left || !right || !left->dt_val || !right->dt_val) {
		return false;
	}
	if (left->type != cql::BoundType::DateTime && left->type != cql::BoundType::Time) {
		return false;
	}
	if (right->type != cql::BoundType::DateTime && right->type != cql::BoundType::Time) {
		return false;
	}
	int target_rank = IntervalPrecisionRank(precision);
	int left_rank = IntervalPrecisionRank(left->dt_val->precision);
	int right_rank = IntervalPrecisionRank(right->dt_val->precision);
	int min_rank = std::min(left_rank, right_rank);
	if (target_rank <= min_rank) {
		return false;
	}
	return left->dt_val->compare_at_precision(*right->dt_val, IntervalPrecisionFromRank(min_rank)) == 0;
}

static bool IntervalBeforeUncertain(const cql::Interval &left, const cql::Interval &right,
                                    cql::DateTimeValue::Precision precision) {
	return PrecisionPairUncertain(left.high, right.low, precision);
}

static bool IntervalAfterUncertain(const cql::Interval &left, const cql::Interval &right,
                                   cql::DateTimeValue::Precision precision) {
	return PrecisionPairUncertain(right.high, left.low, precision);
}

static bool IntervalIncludesUncertain(const cql::Interval &left, const cql::Interval &right,
                                      cql::DateTimeValue::Precision precision) {
	return PrecisionPairUncertain(left.low, right.low, precision) ||
	       PrecisionPairUncertain(left.high, right.high, precision);
}

static bool IntervalOverlapsUncertain(const cql::Interval &left, const cql::Interval &right,
                                      cql::DateTimeValue::Precision precision) {
	return PrecisionPairUncertain(right.high, left.low, precision) ||
	       PrecisionPairUncertain(left.high, right.low, precision);
}

static bool IntervalOverlapsBeforeUncertain(const cql::Interval &left, const cql::Interval &right,
                                            cql::DateTimeValue::Precision precision) {
	return PrecisionPairUncertain(left.low, right.low, precision) ||
	       PrecisionPairUncertain(left.high, right.low, precision);
}

static bool IntervalOverlapsAfterUncertain(const cql::Interval &left, const cql::Interval &right,
                                           cql::DateTimeValue::Precision precision) {
	return IntervalOverlapsBeforeUncertain(right, left, precision);
}

static bool IntervalContainsUncertain(const cql::Interval &interval, const cql::BoundValue &point,
                                      cql::DateTimeValue::Precision precision) {
	cql::Optional<cql::BoundValue> point_value(point);
	return PrecisionPairUncertain(interval.low, point_value, precision) ||
	       PrecisionPairUncertain(interval.high, point_value, precision);
}

static bool PrecisionIntervalUncertainFor(const char *func_name, const cql::Interval &left,
                                          const cql::Interval &right,
                                          cql::DateTimeValue::Precision precision) {
	std::string name(func_name);
	if (name == "IntervalBeforePreciseFunc") {
		return IntervalBeforeUncertain(left, right, precision);
	}
	if (name == "IntervalAfterPreciseFunc") {
		return IntervalAfterUncertain(left, right, precision);
	}
	if (name == "IntervalIncludesPreciseFunc") {
		return IntervalIncludesUncertain(left, right, precision);
	}
	if (name == "IntervalOverlapsPreciseFunc") {
		return IntervalOverlapsUncertain(left, right, precision);
	}
	if (name == "IntervalOverlapsBeforePreciseFunc") {
		return IntervalOverlapsBeforeUncertain(left, right, precision);
	}
	if (name == "IntervalOverlapsAfterPreciseFunc") {
		return IntervalOverlapsAfterUncertain(left, right, precision);
	}
	return false;
}

#define DEFINE_PREC_INTERVAL_UDF(FuncName, method_call)                                                                  \
	static void FuncName(DataChunk &args, ExpressionState &state, Vector &result) {                                      \
		idx_t count = args.size();                                                                                       \
		UnifiedVectorFormat a_data, b_data, p_data;                                                                      \
		args.data[0].ToUnifiedFormat(count, a_data);                                                                     \
		args.data[1].ToUnifiedFormat(count, b_data);                                                                     \
		args.data[2].ToUnifiedFormat(count, p_data);                                                                     \
		auto a_vals = UnifiedVectorFormat::GetData<string_t>(a_data);                                                    \
		auto b_vals = UnifiedVectorFormat::GetData<string_t>(b_data);                                                    \
		auto p_vals = UnifiedVectorFormat::GetData<string_t>(p_data);                                                    \
		result.SetVectorType(VectorType::FLAT_VECTOR);                                                                   \
		auto result_data = FlatVector::GetData<bool>(result);                                                            \
		auto &result_mask = FlatVector::Validity(result);                                                                \
		for (idx_t i = 0; i < count; i++) {                                                                              \
			auto a_idx = a_data.sel->get_index(i);                                                                       \
			auto b_idx = b_data.sel->get_index(i);                                                                       \
			auto p_idx = p_data.sel->get_index(i);                                                                       \
			if (!a_data.validity.RowIsValid(a_idx) || !b_data.validity.RowIsValid(b_idx) ||                              \
			    !p_data.validity.RowIsValid(p_idx)) {                                                                    \
				result_mask.SetInvalid(i);                                                                               \
				continue;                                                                                                \
			}                                                                                                            \
			auto prec = cql::precision_from_string(p_vals[p_idx].GetString());                                           \
			if (!prec) { result_mask.SetInvalid(i); continue; }                                                          \
			auto iv1 = cql::Interval::parse(a_vals[a_idx].GetString());                                                  \
			auto iv2 = cql::Interval::parse(b_vals[b_idx].GetString());                                                  \
			if (iv1 && iv2 && PrecisionIntervalUncertainFor(#FuncName, *iv1, *iv2, *prec)) {                            \
				result_mask.SetInvalid(i);                                                                               \
				continue;                                                                                                \
			}                                                                                                            \
			result_data[i] = (iv1 && iv2) ? method_call : false;                                                         \
		}                                                                                                                \
	}

DEFINE_PREC_INTERVAL_UDF(IntervalOverlapsPreciseFunc, iv1->overlaps(*iv2, *prec))
DEFINE_PREC_INTERVAL_UDF(IntervalBeforePreciseFunc, iv1->before(*iv2, *prec))
DEFINE_PREC_INTERVAL_UDF(IntervalAfterPreciseFunc, iv1->after(*iv2, *prec))
DEFINE_PREC_INTERVAL_UDF(IntervalIncludesPreciseFunc, iv1->includes(*iv2, *prec))
DEFINE_PREC_INTERVAL_UDF(IntervalOverlapsBeforePreciseFunc, iv1->overlaps_before(*iv2, *prec))
DEFINE_PREC_INTERVAL_UDF(IntervalOverlapsAfterPreciseFunc, iv1->overlaps_after(*iv2, *prec))

static void IntervalIncludedInPreciseFunc(DataChunk &args, ExpressionState &state, Vector &result) {
	idx_t count = args.size();
	UnifiedVectorFormat a_data, b_data, p_data;
	args.data[0].ToUnifiedFormat(count, a_data);
	args.data[1].ToUnifiedFormat(count, b_data);
	args.data[2].ToUnifiedFormat(count, p_data);
	auto a_vals = UnifiedVectorFormat::GetData<string_t>(a_data);
	auto b_vals = UnifiedVectorFormat::GetData<string_t>(b_data);
	auto p_vals = UnifiedVectorFormat::GetData<string_t>(p_data);
	result.SetVectorType(VectorType::FLAT_VECTOR);
	auto result_data = FlatVector::GetData<bool>(result);
	auto &result_mask = FlatVector::Validity(result);
	for (idx_t i = 0; i < count; i++) {
		auto a_idx = a_data.sel->get_index(i);
		auto b_idx = b_data.sel->get_index(i);
		auto p_idx = p_data.sel->get_index(i);
		if (!a_data.validity.RowIsValid(a_idx) || !b_data.validity.RowIsValid(b_idx) ||
		    !p_data.validity.RowIsValid(p_idx)) {
			result_mask.SetInvalid(i);
			continue;
		}
		auto prec = cql::precision_from_string(p_vals[p_idx].GetString());
		auto iv1 = cql::Interval::parse(a_vals[a_idx].GetString());
		auto iv2 = cql::Interval::parse(b_vals[b_idx].GetString());
		if (!prec || !iv1 || !iv2) {
			result_mask.SetInvalid(i);
			continue;
		}
		if (IntervalIncludesUncertain(*iv2, *iv1, *prec)) {
			result_mask.SetInvalid(i);
			continue;
		}
		result_data[i] = iv2->includes(*iv1, *prec);
	}
}

static cql::Optional<cql::BoundValue> ParsePointValueForPrecision(const std::string &str) {
	if (!str.empty() && (str[0] == 'T' || str.find('T') != std::string::npos ||
	                   str.find(':') != std::string::npos ||
	                   (str.size() == 4 && str[0] >= '0' && str[0] <= '9' &&
	                    str[1] >= '0' && str[1] <= '9' && str[2] >= '0' && str[2] <= '9' &&
	                    str[3] >= '0' && str[3] <= '9') ||
	                   (str.find('-') != std::string::npos && str[0] != '-'))) {
		return cql::BoundValue::from_interval_bound_string(str);
	}
	return cql::parse_point_value(str);
}

// Precision-aware contains: (interval, point, precision) → BOOLEAN
static void IntervalContainsPreciseFunc(DataChunk &args, ExpressionState &state, Vector &result) {
	idx_t count = args.size();
	UnifiedVectorFormat iv_data, pt_data, p_data;
	args.data[0].ToUnifiedFormat(count, iv_data);
	args.data[1].ToUnifiedFormat(count, pt_data);
	args.data[2].ToUnifiedFormat(count, p_data);
	auto iv_vals = UnifiedVectorFormat::GetData<string_t>(iv_data);
	auto pt_vals = UnifiedVectorFormat::GetData<string_t>(pt_data);
	auto p_vals = UnifiedVectorFormat::GetData<string_t>(p_data);

	result.SetVectorType(VectorType::FLAT_VECTOR);
	auto result_data = FlatVector::GetData<bool>(result);
	auto &result_mask = FlatVector::Validity(result);

	for (idx_t i = 0; i < count; i++) {
		auto iv_idx = iv_data.sel->get_index(i);
		auto pt_idx = pt_data.sel->get_index(i);
		auto p_idx = p_data.sel->get_index(i);
		if (!iv_data.validity.RowIsValid(iv_idx)) {
			result_data[i] = false;
			continue;
		}
		if (!pt_data.validity.RowIsValid(pt_idx) || !p_data.validity.RowIsValid(p_idx)) {
			result_mask.SetInvalid(i);
			continue;
		}
		auto prec = cql::precision_from_string(p_vals[p_idx].GetString());
		if (!prec) { result_mask.SetInvalid(i); continue; }
		auto iv = cql::Interval::parse(iv_vals[iv_idx].GetString());
		if (!iv) { result_mask.SetInvalid(i); continue; }
		std::string pt_str = pt_vals[pt_idx].GetString();
		if (cql::is_json_interval(pt_str)) {
			auto pt_iv = cql::Interval::parse(pt_str);
			if (pt_iv && IntervalIncludesUncertain(*iv, *pt_iv, *prec)) {
				result_mask.SetInvalid(i);
				continue;
			}
			result_data[i] = pt_iv ? iv->contains_interval(*pt_iv, *prec) : false;
		} else {
			auto pt = ParsePointValueForPrecision(pt_str);
			if (pt && IntervalContainsUncertain(*iv, *pt, *prec)) {
				result_mask.SetInvalid(i);
				continue;
			}
			result_data[i] = pt ? iv->contains_point(*pt, *prec) : false;
		}
	}
}

// truncateInterval(interval, precision) → VARCHAR
// Returns a new interval with bounds truncated to the given precision.
static void TruncateIntervalFunc(DataChunk &args, ExpressionState &state, Vector &result) {
	idx_t count = args.size();
	UnifiedVectorFormat iv_data, p_data;
	args.data[0].ToUnifiedFormat(count, iv_data);
	args.data[1].ToUnifiedFormat(count, p_data);
	auto iv_vals = UnifiedVectorFormat::GetData<string_t>(iv_data);
	auto p_vals = UnifiedVectorFormat::GetData<string_t>(p_data);

	result.SetVectorType(VectorType::FLAT_VECTOR);
	auto result_data = FlatVector::GetData<string_t>(result);
	auto &result_mask = FlatVector::Validity(result);

	for (idx_t i = 0; i < count; i++) {
		auto iv_idx = iv_data.sel->get_index(i);
		auto p_idx = p_data.sel->get_index(i);
		if (!iv_data.validity.RowIsValid(iv_idx) || !p_data.validity.RowIsValid(p_idx)) {
			result_mask.SetInvalid(i);
			continue;
		}
		auto prec = cql::precision_from_string(p_vals[p_idx].GetString());
		if (!prec) { result_mask.SetInvalid(i); continue; }
		auto iv = cql::Interval::parse(iv_vals[iv_idx].GetString());
		if (!iv) { result_mask.SetInvalid(i); continue; }
		result_data[i] = StringVector::AddString(result, iv->to_json());
	}
}

// intervalFromBounds(low, high, lowClosed, highClosed) → VARCHAR
static void IntervalFromBoundsFunc(DataChunk &args, ExpressionState &state, Vector &result) {
	idx_t count = args.size();
	UnifiedVectorFormat low_data, high_data, lc_data, hc_data;
	args.data[0].ToUnifiedFormat(count, low_data);
	args.data[1].ToUnifiedFormat(count, high_data);
	args.data[2].ToUnifiedFormat(count, lc_data);
	args.data[3].ToUnifiedFormat(count, hc_data);

	auto lows = UnifiedVectorFormat::GetData<string_t>(low_data);
	auto highs = UnifiedVectorFormat::GetData<string_t>(high_data);
	auto lcs = UnifiedVectorFormat::GetData<bool>(lc_data);
	auto hcs = UnifiedVectorFormat::GetData<bool>(hc_data);

	result.SetVectorType(VectorType::FLAT_VECTOR);
	auto result_data = FlatVector::GetData<string_t>(result);
	auto &result_mask = FlatVector::Validity(result);

	for (idx_t i = 0; i < count; i++) {
		auto l_idx = low_data.sel->get_index(i);
		auto h_idx = high_data.sel->get_index(i);
		auto lc_idx = lc_data.sel->get_index(i);
		auto hc_idx = hc_data.sel->get_index(i);

		cql::Interval iv;
		bool low_supplied = low_data.validity.RowIsValid(l_idx);
		bool high_supplied = high_data.validity.RowIsValid(h_idx);
		if (!low_supplied && !high_supplied) {
			result_mask.SetInvalid(i);
			continue;
		}

		std::string low_raw = low_supplied ? lows[l_idx].GetString() : "";
		std::string high_raw = high_supplied ? highs[h_idx].GetString() : "";
		bool low_datetime_like = low_supplied && LooksDateTimeLikeBound(low_raw);
		bool high_datetime_like = high_supplied && LooksDateTimeLikeBound(high_raw);
		if (low_supplied) {
			iv.low = ParseIntervalBoundWithPeer(low_raw, high_datetime_like);
		}
		if (high_supplied) {
			iv.high = ParseIntervalBoundWithPeer(high_raw, low_datetime_like);
		}
		iv.low_closed = lc_data.validity.RowIsValid(lc_idx) ? lcs[lc_idx] : true;
		iv.high_closed = hc_data.validity.RowIsValid(hc_idx) ? hcs[hc_idx] : true;
		if (iv.low) {
			iv.bound_type = iv.low->type;
		} else if (iv.high) {
			iv.bound_type = iv.high->type;
		}

		if (!iv.low && !iv.high) {
			result_data[i] = StringVector::AddString(result, iv.to_json());
			continue;
		}
		if (iv.low && iv.high) {
			int cmp = iv.low->compare(*iv.high);
			if (cmp > 0 || (cmp == 0 && !(iv.low_closed && iv.high_closed))) {
				throw InvalidInputException("Invalid CQL interval: low bound is after high bound");
			}
		}
		result_data[i] = StringVector::AddString(result, iv.to_json());
	}
}

DEFINE_ONE_STR_STR_UDF(IntervalSizeFunc, {
	auto iv = cql::Interval::parse(a_str);
	if (!iv || !iv->low || !iv->high) { result_mask.SetInvalid(i); continue; }
	auto size = iv->size_string();
	if (!size) { result_mask.SetInvalid(i); continue; }
	result_data[i] = StringVector::AddString(result, *size);
})

struct ExpandStep {
	double value = 1.0;
	std::string unit;
	bool supplied = false;
	bool valid = true;
};

struct ExpandedInterval {
	std::string low;
	std::string high;
	bool quote_values = false;

	ExpandedInterval() {
	}
	ExpandedInterval(std::string low_value, std::string high_value, bool quote)
	    : low(std::move(low_value)), high(std::move(high_value)), quote_values(quote) {
	}
};

static const size_t MAX_EXPAND_POINTS = 10000;

static std::string LowerAscii(std::string value) {
	std::transform(value.begin(), value.end(), value.begin(),
	               [](unsigned char ch) { return static_cast<char>(std::tolower(ch)); });
	return value;
}

static bool IsTemporalExpandUnit(const std::string &unit) {
	std::string u = LowerAscii(unit);
	return u == "year" || u == "years" || u == "a" || u == "month" || u == "months" || u == "mo" ||
	       u == "week" || u == "weeks" || u == "wk" || u == "day" || u == "days" || u == "d" ||
	       u == "hour" || u == "hours" || u == "h" || u == "minute" || u == "minutes" || u == "min" ||
	       u == "second" || u == "seconds" || u == "s" || u == "millisecond" || u == "milliseconds" ||
	       u == "ms";
}

static bool IsDefaultExpandUnit(const std::string &unit) {
	std::string u = LowerAscii(unit);
	return u.empty() || u == "1";
}

static ExpandStep ParseExpandStep(const std::string &per) {
	ExpandStep step;
	step.supplied = true;
	auto quantity = cql::parse_quantity_json(per);
	if (!quantity) {
		step.valid = false;
		return step;
	}
	step.value = quantity->value;
	step.unit = quantity->code;
	return step;
}

static void AppendJsonQuoted(std::ostringstream &oss, const std::string &value) {
	oss << "\"";
	for (char ch : value) {
		switch (ch) {
		case '\\':
			oss << "\\\\";
			break;
		case '"':
			oss << "\\\"";
			break;
		case '\n':
			oss << "\\n";
			break;
		case '\r':
			oss << "\\r";
			break;
		case '\t':
			oss << "\\t";
			break;
		default:
			oss << ch;
			break;
		}
	}
	oss << "\"";
}

static void AppendJsonScalar(std::ostringstream &oss, const std::string &value, bool quote) {
	if (quote) {
		AppendJsonQuoted(oss, value);
	} else {
		oss << value;
	}
}

static std::string FormatDecimalForJson(double value) {
	std::ostringstream oss;
	oss << std::fixed << std::setprecision(8) << value;
	std::string out = oss.str();
	while (out.size() > 2 && out.back() == '0' && out[out.size() - 2] != '.') {
		out.pop_back();
	}
	if (out.find('.') == std::string::npos) {
		out += ".0";
	}
	return out;
}

static std::string SerializeExpandedPoints(const std::vector<ExpandedInterval> &items) {
	std::ostringstream oss;
	oss << "[";
	for (size_t idx = 0; idx < items.size(); idx++) {
		if (idx > 0) {
			oss << ",";
		}
		AppendJsonScalar(oss, items[idx].low, items[idx].quote_values);
	}
	oss << "]";
	return oss.str();
}

static std::string SerializeExpandedIntervals(const std::vector<ExpandedInterval> &items) {
	std::ostringstream oss;
	oss << "[";
	for (size_t idx = 0; idx < items.size(); idx++) {
		if (idx > 0) {
			oss << ",";
		}
		oss << "{\"low\":";
		AppendJsonScalar(oss, items[idx].low, items[idx].quote_values);
		oss << ",\"high\":";
		AppendJsonScalar(oss, items[idx].high, items[idx].quote_values);
		oss << ",\"lowClosed\":true,\"highClosed\":true}";
	}
	oss << "]";
	return oss.str();
}

static cql::Optional<std::vector<ExpandedInterval>>
ExpandNumericInterval(double low, double high, bool low_closed, bool high_closed, double step_value, bool integer_mode) {
	if (step_value <= 0 || std::isnan(step_value) || std::isinf(step_value)) {
		return cql::NullOpt<std::vector<ExpandedInterval>>();
	}

	double start = low + (low_closed ? 0.0 : (integer_mode ? 1.0 : 1e-8));
	double end = high - (high_closed ? 0.0 : (integer_mode ? 1.0 : 1e-8));
	std::vector<ExpandedInterval> result;
	if (end + 1e-12 < start) {
		return result;
	}

	if (integer_mode) {
		int64_t current = static_cast<int64_t>(start);
		int64_t last = static_cast<int64_t>(end);
		int64_t step = static_cast<int64_t>(step_value);
		if (step <= 0 || static_cast<double>(step) != step_value) {
			return cql::NullOpt<std::vector<ExpandedInterval>>();
		}
		while (current <= last && result.size() < MAX_EXPAND_POINTS) {
			int64_t interval_end = current + step - 1;
			if (interval_end > last) {
				break;
			}
			result.push_back({std::to_string(current), std::to_string(interval_end), false});
			current += step;
		}
		return result;
	}

	double current = start;
	while (current <= end + 1e-10 && result.size() < MAX_EXPAND_POINTS) {
		std::string point = FormatDecimalForJson(current);
		result.push_back({point, point, false});
		current += step_value;
	}
	return result;
}

static cql::Optional<double> QuantityValueInUnit(const std::string &quantity_json, const std::string &target_unit) {
	auto converted = cql::quantity_convert(quantity_json, target_unit);
	if (!converted) {
		return cql::NullOpt<double>();
	}
	auto parsed = cql::parse_quantity_json(*converted);
	if (!parsed) {
		return cql::NullOpt<double>();
	}
	return cql::Optional<double>(parsed->value);
}

static cql::Optional<std::string> FormatExpandQuantity(double value, const std::string &unit) {
	cql::ParsedQuantity quantity;
	quantity.value = value;
	quantity.code = unit;
	quantity.system = "http://unitsofmeasure.org";
	quantity.precision = 8;
	return cql::format_quantity_json(quantity);
}

static cql::Optional<std::vector<ExpandedInterval>>
ExpandQuantityInterval(const cql::Interval &iv, const ExpandStep &step) {
	if (!iv.low || !iv.high || !iv.low->qty_numeric || !iv.high->qty_numeric) {
		return cql::NullOpt<std::vector<ExpandedInterval>>();
	}
	std::string unit = iv.low->qty_unit.empty() ? "1" : iv.low->qty_unit;
	auto low_value = QuantityValueInUnit(iv.low->raw_str, unit);
	auto high_value = QuantityValueInUnit(iv.high->raw_str, unit);
	if (!low_value || !high_value) {
		return std::vector<ExpandedInterval>();
	}

	double step_value = step.supplied ? step.value : 1e-8;
	if (step.supplied && !step.unit.empty()) {
		auto step_json = FormatExpandQuantity(step.value, step.unit);
		auto step_converted = step_json ? QuantityValueInUnit(*step_json, unit) : cql::NullOpt<double>();
		if (!step_converted) {
			return std::vector<ExpandedInterval>();
		}
		step_value = *step_converted;
	}
	if (step_value <= 0 || std::isnan(step_value) || std::isinf(step_value)) {
		return cql::NullOpt<std::vector<ExpandedInterval>>();
	}

	double start = *low_value + (iv.low_closed ? 0.0 : 1e-8);
	double end = *high_value - (iv.high_closed ? 0.0 : 1e-8);
	std::vector<ExpandedInterval> result;
	if (end + 1e-12 < start) {
		return result;
	}
	double current = start;
	while (current <= end + 1e-10 && result.size() < MAX_EXPAND_POINTS) {
		auto quantity = FormatExpandQuantity(current, unit);
		if (!quantity) {
			return cql::NullOpt<std::vector<ExpandedInterval>>();
		}
		result.push_back({*quantity, *quantity, false});
		current += step_value;
	}
	return result;
}

static cql::DateTimeValue::Precision PrecisionForExpandUnit(const std::string &unit,
                                                            cql::DateTimeValue::Precision fallback) {
	std::string u = LowerAscii(unit);
	if (u == "year" || u == "years" || u == "a") {
		return cql::DateTimeValue::Precision::Year;
	}
	if (u == "month" || u == "months" || u == "mo") {
		return cql::DateTimeValue::Precision::Month;
	}
	if (u == "week" || u == "weeks" || u == "wk" || u == "day" || u == "days" || u == "d") {
		return cql::DateTimeValue::Precision::Day;
	}
	if (u == "hour" || u == "hours" || u == "h") {
		return cql::DateTimeValue::Precision::Hour;
	}
	if (u == "minute" || u == "minutes" || u == "min") {
		return cql::DateTimeValue::Precision::Minute;
	}
	if (u == "second" || u == "seconds" || u == "s") {
		return cql::DateTimeValue::Precision::Second;
	}
	if (u == "millisecond" || u == "milliseconds" || u == "ms") {
		return cql::DateTimeValue::Precision::Millisecond;
	}
	return fallback;
}

static int ExpandPrecisionRank(cql::DateTimeValue::Precision precision) {
	switch (precision) {
	case cql::DateTimeValue::Precision::Year:
		return 0;
	case cql::DateTimeValue::Precision::Month:
		return 1;
	case cql::DateTimeValue::Precision::Day:
		return 2;
	case cql::DateTimeValue::Precision::Hour:
		return 3;
	case cql::DateTimeValue::Precision::Minute:
		return 4;
	case cql::DateTimeValue::Precision::Second:
		return 5;
	case cql::DateTimeValue::Precision::Millisecond:
		return 6;
	}
	return 2;
}

static cql::DateTimeValue AddExpandStep(const cql::DateTimeValue &dt, double value, const std::string &unit) {
	std::string u = LowerAscii(unit);
	int64_t count = static_cast<int64_t>(value);
	cql::DateTimeValue result;
	if (u == "year" || u == "years" || u == "a") {
		result = AddYears(dt, static_cast<int32_t>(count));
	} else if (u == "month" || u == "months" || u == "mo") {
		result = AddMonths(dt, static_cast<int32_t>(count));
	} else if (u == "week" || u == "weeks" || u == "wk") {
		result = AddDays(dt, count * 7);
	} else if (u == "day" || u == "days" || u == "d") {
		result = AddDays(dt, count);
	} else {
		int64_t millis = 0;
		if (u == "hour" || u == "hours" || u == "h") {
			millis = static_cast<int64_t>(value * static_cast<double>(MS_PER_HOUR));
		} else if (u == "minute" || u == "minutes" || u == "min") {
			millis = static_cast<int64_t>(value * static_cast<double>(MS_PER_MINUTE));
		} else if (u == "second" || u == "seconds" || u == "s") {
			millis = static_cast<int64_t>(value * static_cast<double>(MS_PER_SECOND));
		} else {
			millis = static_cast<int64_t>(value);
		}
		result = AddMilliseconds(dt, millis);
		result.has_time = true;
	}
	result.is_time = dt.is_time;
	result.precision = PrecisionForExpandUnit(unit, dt.precision);
	if (ExpandPrecisionRank(result.precision) >= ExpandPrecisionRank(cql::DateTimeValue::Precision::Hour)) {
		result.has_time = true;
	}
	return result;
}

static cql::DateTimeValue SubtractExpandStep(const cql::DateTimeValue &dt, double value, const std::string &unit) {
	return AddExpandStep(dt, -value, unit);
}

static cql::DateTimeValue ExpandIntervalEndPredecessor(const cql::DateTimeValue &next,
                                                       const cql::DateTimeValue &current,
                                                       const std::string &unit) {
	std::string u = LowerAscii(unit);
	if (current.is_time || current.has_time || u == "hour" || u == "hours" || u == "h" || u == "minute" ||
	    u == "minutes" || u == "min" || u == "second" || u == "seconds" || u == "s" ||
	    u == "millisecond" || u == "milliseconds" || u == "ms") {
		auto result = AddMilliseconds(next, -1);
		result.is_time = current.is_time;
		result.has_time = true;
		result.precision = PrecisionForExpandUnit(unit, current.precision);
		return result;
	}
	auto result = AddDays(next, -1);
	result.precision = PrecisionForExpandUnit(unit, current.precision);
	return result;
}

static cql::Optional<std::vector<ExpandedInterval>>
ExpandTemporalInterval(const cql::Interval &iv, const ExpandStep &step) {
	if (!iv.low || !iv.high || !iv.low->dt_val || !iv.high->dt_val) {
		return cql::NullOpt<std::vector<ExpandedInterval>>();
	}

	std::string unit = step.supplied && !step.unit.empty() ? step.unit : (iv.bound_type == cql::BoundType::Time ? "hour" : "day");
	double step_value = step.supplied ? step.value : 1.0;
	if (step_value <= 0 || std::isnan(step_value) || std::isinf(step_value)) {
		return cql::NullOpt<std::vector<ExpandedInterval>>();
	}

	cql::DateTimeValue start = *iv.low->dt_val;
	cql::DateTimeValue end = *iv.high->dt_val;
	if (!iv.low_closed) {
		start = AddExpandStep(start, step_value, unit);
	}
	if (!iv.high_closed) {
		end = SubtractExpandStep(end, step_value, unit);
	}
	start.precision = PrecisionForExpandUnit(unit, start.precision);
	end.precision = PrecisionForExpandUnit(unit, end.precision);
	if (ExpandPrecisionRank(start.precision) >= ExpandPrecisionRank(cql::DateTimeValue::Precision::Hour)) {
		start.has_time = true;
	}
	if (ExpandPrecisionRank(end.precision) >= ExpandPrecisionRank(cql::DateTimeValue::Precision::Hour)) {
		end.has_time = true;
	}

	std::vector<ExpandedInterval> result;
	if (start > end) {
		return result;
	}

	cql::DateTimeValue current = start;
	while (current <= end && result.size() < MAX_EXPAND_POINTS) {
		cql::DateTimeValue next = AddExpandStep(current, step_value, unit);
		cql::DateTimeValue interval_end = ExpandIntervalEndPredecessor(next, current, unit);
		if (interval_end > end) {
			interval_end = end;
		}
		result.push_back({current.to_string(), interval_end.to_string(), true});
		current = next;
	}
	return result;
}

static int64_t TimeMillisOfDay(const cql::DateTimeValue &value) {
	return static_cast<int64_t>(value.hour) * MS_PER_HOUR + static_cast<int64_t>(value.minute) * MS_PER_MINUTE +
	       static_cast<int64_t>(value.second) * MS_PER_SECOND + value.millisecond;
}

static int64_t TimeStepMillis(double value, const std::string &unit) {
	std::string u = LowerAscii(unit);
	if (u == "hour" || u == "hours" || u == "h") {
		return static_cast<int64_t>(value * static_cast<double>(MS_PER_HOUR));
	}
	if (u == "minute" || u == "minutes" || u == "min") {
		return static_cast<int64_t>(value * static_cast<double>(MS_PER_MINUTE));
	}
	if (u == "second" || u == "seconds" || u == "s") {
		return static_cast<int64_t>(value * static_cast<double>(MS_PER_SECOND));
	}
	return static_cast<int64_t>(value);
}

static std::string FormatTimeMillisForRank(int64_t millis, int rank) {
	if (millis < 0) {
		millis = 0;
	}
	int64_t hour = millis / MS_PER_HOUR;
	int64_t rem = millis % MS_PER_HOUR;
	int64_t minute = rem / MS_PER_MINUTE;
	rem %= MS_PER_MINUTE;
	int64_t second = rem / MS_PER_SECOND;
	int64_t ms = rem % MS_PER_SECOND;
	std::ostringstream oss;
	oss << "T" << std::setw(2) << std::setfill('0') << hour;
	if (rank >= ExpandPrecisionRank(cql::DateTimeValue::Precision::Minute)) {
		oss << ":" << std::setw(2) << std::setfill('0') << minute;
	}
	if (rank >= ExpandPrecisionRank(cql::DateTimeValue::Precision::Second)) {
		oss << ":" << std::setw(2) << std::setfill('0') << second;
	}
	if (rank >= ExpandPrecisionRank(cql::DateTimeValue::Precision::Millisecond)) {
		oss << "." << std::setw(3) << std::setfill('0') << ms;
	}
	return oss.str();
}

static cql::Optional<std::vector<ExpandedInterval>>
ExpandTimeInterval(const cql::Interval &iv, const ExpandStep &step) {
	if (!iv.low || !iv.high || !iv.low->dt_val || !iv.high->dt_val) {
		return cql::NullOpt<std::vector<ExpandedInterval>>();
	}
	std::string unit = step.supplied && !step.unit.empty() ? step.unit : "hour";
	double step_value = step.supplied ? step.value : 1.0;
	if (step_value <= 0 || std::isnan(step_value) || std::isinf(step_value)) {
		return cql::NullOpt<std::vector<ExpandedInterval>>();
	}

	int input_rank = ExpandPrecisionRank(iv.low->dt_val->precision);
	int per_rank = ExpandPrecisionRank(PrecisionForExpandUnit(unit, cql::DateTimeValue::Precision::Hour));
	if (per_rank > input_rank) {
		return std::vector<ExpandedInterval>();
	}

	int64_t step_ms = TimeStepMillis(step_value, unit);
	if (step_ms <= 0) {
		return cql::NullOpt<std::vector<ExpandedInterval>>();
	}
	int64_t start = TimeMillisOfDay(*iv.low->dt_val);
	int64_t end = TimeMillisOfDay(*iv.high->dt_val);
	if (!iv.low_closed) {
		start += 1;
		int64_t remainder = start % step_ms;
		if (remainder != 0) {
			start += step_ms - remainder;
		}
	}
	if (!iv.high_closed) {
		end -= 1;
	}

	std::vector<ExpandedInterval> result;
	if (end < start) {
		return result;
	}
	while (start <= end && result.size() < MAX_EXPAND_POINTS) {
		std::string point = FormatTimeMillisForRank(start, per_rank);
		result.push_back({point, point, true});
		start += step_ms;
	}
	return result;
}

static cql::Optional<std::vector<ExpandedInterval>>
ExpandIntervalUnits(const cql::Interval &iv, const ExpandStep &step) {
	if (!step.valid) {
		return cql::NullOpt<std::vector<ExpandedInterval>>();
	}
	if (!iv.low || !iv.high) {
		return cql::NullOpt<std::vector<ExpandedInterval>>();
	}

	if (iv.bound_type == cql::BoundType::Integer && iv.low->int_val && iv.high->int_val) {
		if (step.supplied && !IsDefaultExpandUnit(step.unit)) {
			return std::vector<ExpandedInterval>();
		}
		double step_value = step.supplied ? step.value : 1.0;
		if (std::fabs(step_value - std::floor(step_value)) > 1e-12) {
			double low = static_cast<double>(*iv.low->int_val) + (iv.low_closed ? 0.0 : 1.0);
			double high = static_cast<double>(*iv.high->int_val) + (iv.high_closed ? 1.0 : 0.0) - 1e-8;
			return ExpandNumericInterval(low, high, true, true, step_value, false);
		}
		return ExpandNumericInterval(static_cast<double>(*iv.low->int_val), static_cast<double>(*iv.high->int_val),
		                             iv.low_closed, iv.high_closed, step_value, true);
	}

	if (iv.bound_type == cql::BoundType::Decimal && iv.low->dec_val && iv.high->dec_val) {
		if (step.supplied && !IsDefaultExpandUnit(step.unit)) {
			return std::vector<ExpandedInterval>();
		}
		double step_value = step.supplied ? step.value : 1e-8;
		return ExpandNumericInterval(*iv.low->dec_val, *iv.high->dec_val, iv.low_closed, iv.high_closed, step_value,
		                             false);
	}

	if (iv.bound_type == cql::BoundType::Quantity && iv.low->qty_numeric && iv.high->qty_numeric) {
		if (step.supplied && IsTemporalExpandUnit(step.unit)) {
			return std::vector<ExpandedInterval>();
		}
		return ExpandQuantityInterval(iv, step);
	}

	if (iv.bound_type == cql::BoundType::Time) {
		if (step.supplied && !IsTemporalExpandUnit(step.unit)) {
			return std::vector<ExpandedInterval>();
		}
		return ExpandTimeInterval(iv, step);
	}

	if (iv.bound_type == cql::BoundType::DateTime) {
		if (step.supplied && !IsTemporalExpandUnit(step.unit)) {
			return std::vector<ExpandedInterval>();
		}
		return ExpandTemporalInterval(iv, step);
	}

	return cql::NullOpt<std::vector<ExpandedInterval>>();
}

static cql::Optional<std::string> ExpandIntervalPointsJson(const cql::Interval &iv, const ExpandStep &step) {
	auto expanded = ExpandIntervalUnits(iv, step);
	if (!expanded) {
		return cql::NullOpt<std::string>();
	}
	return SerializeExpandedPoints(*expanded);
}

static cql::Optional<std::string> ExpandIntervalListJson(const std::vector<std::string> &intervals,
                                                         const ExpandStep &step) {
	if (!step.valid) {
		return cql::NullOpt<std::string>();
	}
	std::vector<ExpandedInterval> all;
	for (const auto &item : intervals) {
		auto iv = cql::Interval::parse(item);
		if (!iv) {
			continue;
		}
		auto expanded = ExpandIntervalUnits(*iv, step);
		if (!expanded) {
			continue;
		}
		all.insert(all.end(), expanded->begin(), expanded->end());
		if (all.size() > MAX_EXPAND_POINTS) {
			return cql::NullOpt<std::string>();
		}
	}
	return SerializeExpandedIntervals(all);
}

DEFINE_ONE_STR_STR_UDF(ExpandPoints1Func, {
	auto iv = cql::Interval::parse(a_str);
	if (!iv) { result_mask.SetInvalid(i); continue; }
	ExpandStep step;
	auto expanded = ExpandIntervalPointsJson(*iv, step);
	if (!expanded) { result_mask.SetInvalid(i); continue; }
	result_data[i] = StringVector::AddString(result, *expanded);
})

static void ExpandPointsFunc(DataChunk &args, ExpressionState &state, Vector &result) {
	idx_t count = args.size();
	UnifiedVectorFormat interval_data, per_data;
	args.data[0].ToUnifiedFormat(count, interval_data);
	args.data[1].ToUnifiedFormat(count, per_data);
	auto intervals = UnifiedVectorFormat::GetData<string_t>(interval_data);
	auto pers = UnifiedVectorFormat::GetData<string_t>(per_data);

	result.SetVectorType(VectorType::FLAT_VECTOR);
	auto result_data = FlatVector::GetData<string_t>(result);
	auto &result_mask = FlatVector::Validity(result);

	for (idx_t i = 0; i < count; i++) {
		auto interval_idx = interval_data.sel->get_index(i);
		auto per_idx = per_data.sel->get_index(i);
		if (!interval_data.validity.RowIsValid(interval_idx)) {
			result_mask.SetInvalid(i);
			continue;
		}
		auto iv = cql::Interval::parse(intervals[interval_idx].GetString());
		if (!iv) {
			result_mask.SetInvalid(i);
			continue;
		}
		ExpandStep step;
		if (per_data.validity.RowIsValid(per_idx)) {
			step = ParseExpandStep(pers[per_idx].GetString());
		}
		auto expanded = ExpandIntervalPointsJson(*iv, step);
		if (!expanded) {
			result_mask.SetInvalid(i);
			continue;
		}
		result_data[i] = StringVector::AddString(result, *expanded);
	}
}

static void ExpandListInternal(DataChunk &args, Vector &result, bool has_per) {
	idx_t count = args.size();
	auto &list_vec = args.data[0];
	UnifiedVectorFormat list_data;
	list_vec.ToUnifiedFormat(count, list_data);
	auto list_entries = UnifiedVectorFormat::GetData<list_entry_t>(list_data);
	auto &child_vec = ListVector::GetEntry(list_vec);
	UnifiedVectorFormat child_data;
	child_vec.ToUnifiedFormat(ListVector::GetListSize(list_vec), child_data);
	auto child_vals = UnifiedVectorFormat::GetData<string_t>(child_data);

	UnifiedVectorFormat per_data;
	const string_t *pers = nullptr;
	if (has_per) {
		args.data[1].ToUnifiedFormat(count, per_data);
		pers = UnifiedVectorFormat::GetData<string_t>(per_data);
	}

	result.SetVectorType(VectorType::FLAT_VECTOR);
	auto result_data = FlatVector::GetData<string_t>(result);
	auto &result_mask = FlatVector::Validity(result);

	for (idx_t i = 0; i < count; i++) {
		auto list_idx = list_data.sel->get_index(i);
		if (!list_data.validity.RowIsValid(list_idx)) {
			result_mask.SetInvalid(i);
			continue;
		}
		ExpandStep step;
		if (has_per) {
			auto per_idx = per_data.sel->get_index(i);
			if (per_data.validity.RowIsValid(per_idx)) {
				step = ParseExpandStep(pers[per_idx].GetString());
			}
		}
		std::vector<std::string> intervals;
		auto &entry = list_entries[list_idx];
		for (idx_t offset = 0; offset < entry.length; offset++) {
			auto child_idx = child_data.sel->get_index(entry.offset + offset);
			if (child_data.validity.RowIsValid(child_idx)) {
				intervals.push_back(child_vals[child_idx].GetString());
			}
		}
		auto expanded = ExpandIntervalListJson(intervals, step);
		if (!expanded) {
			result_mask.SetInvalid(i);
			continue;
		}
		result_data[i] = StringVector::AddString(result, *expanded);
	}
}

static void Expand1Func(DataChunk &args, ExpressionState &state, Vector &result) {
	ExpandListInternal(args, result, false);
}

static void ExpandFunc(DataChunk &args, ExpressionState &state, Vector &result) {
	ExpandListInternal(args, result, true);
}

// dateTimeNow() → VARCHAR
static void DateTimeNowFunc(DataChunk &args, ExpressionState &state, Vector &result) {
	idx_t count = args.size();
	auto now = std::chrono::system_clock::now();
	auto time_t_now = std::chrono::system_clock::to_time_t(now);
	std::tm tm_buf;
#ifdef _WIN32
	gmtime_s(&tm_buf, &time_t_now);
#else
	gmtime_r(&time_t_now, &tm_buf);
#endif
	char buf[32];
	snprintf(buf, sizeof(buf), "%04d-%02d-%02dT%02d:%02d:%02dZ", tm_buf.tm_year + 1900, tm_buf.tm_mon + 1,
	         tm_buf.tm_mday, tm_buf.tm_hour, tm_buf.tm_min, tm_buf.tm_sec);
	std::string now_str(buf);

	result.SetVectorType(VectorType::CONSTANT_VECTOR);
	ConstantVector::GetData<string_t>(result)[0] = StringVector::AddString(result, now_str);
}

// dateTimeToday() → VARCHAR
static void DateTimeTodayFunc(DataChunk &args, ExpressionState &state, Vector &result) {
	auto today = GetToday();
	std::string today_str = today.to_string();

	result.SetVectorType(VectorType::CONSTANT_VECTOR);
	ConstantVector::GetData<string_t>(result)[0] = StringVector::AddString(result, today_str);
}

// dateTimeSameAs(a, b, precision) → BOOLEAN
static void DateTimeSameAsFunc(DataChunk &args, ExpressionState &state, Vector &result) {
	idx_t count = args.size();
	UnifiedVectorFormat a_data, b_data, p_data;
	args.data[0].ToUnifiedFormat(count, a_data);
	args.data[1].ToUnifiedFormat(count, b_data);
	args.data[2].ToUnifiedFormat(count, p_data);

	auto a_vals = UnifiedVectorFormat::GetData<string_t>(a_data);
	auto b_vals = UnifiedVectorFormat::GetData<string_t>(b_data);
	auto p_vals = UnifiedVectorFormat::GetData<string_t>(p_data);

	result.SetVectorType(VectorType::FLAT_VECTOR);
	auto result_data = FlatVector::GetData<bool>(result);
	auto &result_mask = FlatVector::Validity(result);

	for (idx_t i = 0; i < count; i++) {
		auto a_idx = a_data.sel->get_index(i);
		auto b_idx = b_data.sel->get_index(i);
		auto p_idx = p_data.sel->get_index(i);

		if (!a_data.validity.RowIsValid(a_idx) || !b_data.validity.RowIsValid(b_idx)) {
			result_mask.SetInvalid(i);
			continue;
		}

		auto a_dt = cql::DateTimeValue::parse(a_vals[a_idx].GetString());
		auto b_dt = cql::DateTimeValue::parse(b_vals[b_idx].GetString());
		if (!a_dt || !b_dt) {
			result_mask.SetInvalid(i);
			continue;
		}

		auto prec = cql::DateTimeValue::Precision::Millisecond;
		if (p_data.validity.RowIsValid(p_idx)) {
			std::string p_str = p_vals[p_idx].GetString();
			if (p_str == "year") {
				prec = cql::DateTimeValue::Precision::Year;
			} else if (p_str == "month") {
				prec = cql::DateTimeValue::Precision::Month;
			} else if (p_str == "day") {
				prec = cql::DateTimeValue::Precision::Day;
			} else if (p_str == "hour") {
				prec = cql::DateTimeValue::Precision::Hour;
			} else if (p_str == "minute") {
				prec = cql::DateTimeValue::Precision::Minute;
			} else if (p_str == "second") {
				prec = cql::DateTimeValue::Precision::Second;
			} else if (p_str == "millisecond") {
				prec = cql::DateTimeValue::Precision::Millisecond;
			}
		}
		result_data[i] = a_dt->compare_at_precision(*b_dt, prec) == 0;
	}
}

// dateTimeSameOrBefore/After follow same pattern — registering with SameAs structure
static void DateTimeSameOrBeforeFunc(DataChunk &args, ExpressionState &state, Vector &result) {
	idx_t count = args.size();
	UnifiedVectorFormat a_data, b_data, p_data;
	args.data[0].ToUnifiedFormat(count, a_data);
	args.data[1].ToUnifiedFormat(count, b_data);
	args.data[2].ToUnifiedFormat(count, p_data);

	auto a_vals = UnifiedVectorFormat::GetData<string_t>(a_data);
	auto b_vals = UnifiedVectorFormat::GetData<string_t>(b_data);
	auto p_vals = UnifiedVectorFormat::GetData<string_t>(p_data);

	result.SetVectorType(VectorType::FLAT_VECTOR);
	auto result_data = FlatVector::GetData<bool>(result);
	auto &result_mask = FlatVector::Validity(result);

	for (idx_t i = 0; i < count; i++) {
		auto a_idx = a_data.sel->get_index(i);
		auto b_idx = b_data.sel->get_index(i);
		auto p_idx = p_data.sel->get_index(i);

		if (!a_data.validity.RowIsValid(a_idx) || !b_data.validity.RowIsValid(b_idx)) {
			result_mask.SetInvalid(i);
			continue;
		}

		auto a_dt = cql::DateTimeValue::parse(a_vals[a_idx].GetString());
		auto b_dt = cql::DateTimeValue::parse(b_vals[b_idx].GetString());
		if (!a_dt || !b_dt) {
			result_mask.SetInvalid(i);
			continue;
		}

		auto prec = cql::DateTimeValue::Precision::Millisecond;
		if (p_data.validity.RowIsValid(p_idx)) {
			std::string p_str = p_vals[p_idx].GetString();
			if (p_str == "year") {
				prec = cql::DateTimeValue::Precision::Year;
			} else if (p_str == "month") {
				prec = cql::DateTimeValue::Precision::Month;
			} else if (p_str == "day") {
				prec = cql::DateTimeValue::Precision::Day;
			} else if (p_str == "hour") {
				prec = cql::DateTimeValue::Precision::Hour;
			} else if (p_str == "minute") {
				prec = cql::DateTimeValue::Precision::Minute;
			} else if (p_str == "second") {
				prec = cql::DateTimeValue::Precision::Second;
			} else if (p_str == "millisecond") {
				prec = cql::DateTimeValue::Precision::Millisecond;
			}
		}
		result_data[i] = a_dt->compare_at_precision(*b_dt, prec) <= 0;
	}
}

static void DateTimeSameOrAfterFunc(DataChunk &args, ExpressionState &state, Vector &result) {
	idx_t count = args.size();
	UnifiedVectorFormat a_data, b_data, p_data;
	args.data[0].ToUnifiedFormat(count, a_data);
	args.data[1].ToUnifiedFormat(count, b_data);
	args.data[2].ToUnifiedFormat(count, p_data);

	auto a_vals = UnifiedVectorFormat::GetData<string_t>(a_data);
	auto b_vals = UnifiedVectorFormat::GetData<string_t>(b_data);
	auto p_vals = UnifiedVectorFormat::GetData<string_t>(p_data);

	result.SetVectorType(VectorType::FLAT_VECTOR);
	auto result_data = FlatVector::GetData<bool>(result);
	auto &result_mask = FlatVector::Validity(result);

	for (idx_t i = 0; i < count; i++) {
		auto a_idx = a_data.sel->get_index(i);
		auto b_idx = b_data.sel->get_index(i);
		auto p_idx = p_data.sel->get_index(i);

		if (!a_data.validity.RowIsValid(a_idx) || !b_data.validity.RowIsValid(b_idx)) {
			result_mask.SetInvalid(i);
			continue;
		}

		auto a_dt = cql::DateTimeValue::parse(a_vals[a_idx].GetString());
		auto b_dt = cql::DateTimeValue::parse(b_vals[b_idx].GetString());
		if (!a_dt || !b_dt) {
			result_mask.SetInvalid(i);
			continue;
		}

		auto prec = cql::DateTimeValue::Precision::Millisecond;
		if (p_data.validity.RowIsValid(p_idx)) {
			std::string p_str = p_vals[p_idx].GetString();
			if (p_str == "year") {
				prec = cql::DateTimeValue::Precision::Year;
			} else if (p_str == "month") {
				prec = cql::DateTimeValue::Precision::Month;
			} else if (p_str == "day") {
				prec = cql::DateTimeValue::Precision::Day;
			} else if (p_str == "hour") {
				prec = cql::DateTimeValue::Precision::Hour;
			} else if (p_str == "minute") {
				prec = cql::DateTimeValue::Precision::Minute;
			} else if (p_str == "second") {
				prec = cql::DateTimeValue::Precision::Second;
			} else if (p_str == "millisecond") {
				prec = cql::DateTimeValue::Precision::Millisecond;
			}
		}
		result_data[i] = a_dt->compare_at_precision(*b_dt, prec) >= 0;
	}
}

struct TemporalCompareResult {
	int cmp;
	bool certain;
};

static cql::Optional<cql::DateTimeValue::Precision> PrecisionFromName(const std::string &name) {
	if (name == "year") {
		return cql::DateTimeValue::Precision::Year;
	}
	if (name == "month") {
		return cql::DateTimeValue::Precision::Month;
	}
	if (name == "day") {
		return cql::DateTimeValue::Precision::Day;
	}
	if (name == "hour") {
		return cql::DateTimeValue::Precision::Hour;
	}
	if (name == "minute") {
		return cql::DateTimeValue::Precision::Minute;
	}
	if (name == "second") {
		return cql::DateTimeValue::Precision::Second;
	}
	if (name == "millisecond") {
		return cql::DateTimeValue::Precision::Millisecond;
	}
	return cql::NullOpt<cql::DateTimeValue::Precision>();
}

static int PrecisionRank(cql::DateTimeValue::Precision precision) {
	switch (precision) {
	case cql::DateTimeValue::Precision::Year:
		return 0;
	case cql::DateTimeValue::Precision::Month:
		return 1;
	case cql::DateTimeValue::Precision::Day:
		return 2;
	case cql::DateTimeValue::Precision::Hour:
		return 3;
	case cql::DateTimeValue::Precision::Minute:
		return 4;
	case cql::DateTimeValue::Precision::Second:
		return 5;
	case cql::DateTimeValue::Precision::Millisecond:
		return 6;
	}
	return 6;
}

static cql::DateTimeValue::Precision PrecisionByRank(int rank) {
	switch (rank) {
	case 0:
		return cql::DateTimeValue::Precision::Year;
	case 1:
		return cql::DateTimeValue::Precision::Month;
	case 2:
		return cql::DateTimeValue::Precision::Day;
	case 3:
		return cql::DateTimeValue::Precision::Hour;
	case 4:
		return cql::DateTimeValue::Precision::Minute;
	case 5:
		return cql::DateTimeValue::Precision::Second;
	default:
		return cql::DateTimeValue::Precision::Millisecond;
	}
}

static cql::DateTimeValue DateTimeFromEpochMillis(int64_t millis, const cql::DateTimeValue &source) {
	int64_t days = FloorDiv(millis, MS_PER_DAY);
	int64_t ms_of_day = millis - days * MS_PER_DAY;
	if (ms_of_day < 0) {
		ms_of_day += MS_PER_DAY;
		days--;
	}

	// Howard Hinnant civil_from_days algorithm, with days relative to 1970-01-01.
	int64_t z = days + 719468;
	int64_t era = (z >= 0 ? z : z - 146096) / 146097;
	uint64_t doe = static_cast<uint64_t>(z - era * 146097);
	uint64_t yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
	int64_t y = static_cast<int64_t>(yoe) + era * 400;
	uint64_t doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
	uint64_t mp = (5 * doy + 2) / 153;
	uint64_t d = doy - (153 * mp + 2) / 5 + 1;
	int64_t m = static_cast<int64_t>(mp) + (mp < 10 ? 3 : -9);
	y += (m <= 2);

	cql::DateTimeValue out = source;
	out.year = static_cast<int32_t>(y);
	out.month = static_cast<int32_t>(m);
	out.day = static_cast<int32_t>(d);
	out.hour = static_cast<int32_t>(ms_of_day / MS_PER_HOUR);
	ms_of_day %= MS_PER_HOUR;
	out.minute = static_cast<int32_t>(ms_of_day / MS_PER_MINUTE);
	ms_of_day %= MS_PER_MINUTE;
	out.second = static_cast<int32_t>(ms_of_day / MS_PER_SECOND);
	out.millisecond = static_cast<int32_t>(ms_of_day % MS_PER_SECOND);
	out.has_tz = false;
	out.tz_offset_minutes = 0;
	return out;
}

static cql::DateTimeValue NormalizeForTemporalCompare(const cql::DateTimeValue &value) {
	if (!value.has_tz) {
		return value;
	}
	return DateTimeFromEpochMillis(ToEpochMillisForElapsed(value), value);
}

static int CompareTemporalComponents(const cql::DateTimeValue &left, const cql::DateTimeValue &right,
                                     cql::DateTimeValue::Precision precision) {
	if (left.year != right.year) {
		return left.year < right.year ? -1 : 1;
	}
	if (precision == cql::DateTimeValue::Precision::Year) {
		return 0;
	}
	if (left.month != right.month) {
		return left.month < right.month ? -1 : 1;
	}
	if (precision == cql::DateTimeValue::Precision::Month) {
		return 0;
	}
	if (left.day != right.day) {
		return left.day < right.day ? -1 : 1;
	}
	if (precision == cql::DateTimeValue::Precision::Day) {
		return 0;
	}
	if (left.hour != right.hour) {
		return left.hour < right.hour ? -1 : 1;
	}
	if (precision == cql::DateTimeValue::Precision::Hour) {
		return 0;
	}
	if (left.minute != right.minute) {
		return left.minute < right.minute ? -1 : 1;
	}
	if (precision == cql::DateTimeValue::Precision::Minute) {
		return 0;
	}
	if (left.second != right.second) {
		return left.second < right.second ? -1 : 1;
	}
	if (precision == cql::DateTimeValue::Precision::Second) {
		return 0;
	}
	if (left.millisecond != right.millisecond) {
		return left.millisecond < right.millisecond ? -1 : 1;
	}
	return 0;
}

static std::string ExtractTemporalOperand(const std::string &value) {
	if (!value.empty() && value[0] == '{') {
		auto iv = cql::Interval::parse(value);
		if (iv && iv->low) {
			return iv->low->to_string();
		}
	}
	return value;
}

static cql::Optional<TemporalCompareResult>
CompareTemporal(const std::string &left, const std::string &right,
                const cql::Optional<cql::DateTimeValue::Precision> &specified_precision) {
	auto a_dt = cql::DateTimeValue::parse(ExtractTemporalOperand(left));
	auto b_dt = cql::DateTimeValue::parse(ExtractTemporalOperand(right));
	if (!a_dt || !b_dt) {
		return cql::NullOpt<TemporalCompareResult>();
	}

	cql::DateTimeValue::Precision target;
	bool specified = static_cast<bool>(specified_precision);
	if (specified) {
		target = *specified_precision;
	} else {
		target = PrecisionByRank(std::min(PrecisionRank((*a_dt).precision), PrecisionRank((*b_dt).precision)));
	}

	cql::DateTimeValue left_dt = *a_dt;
	cql::DateTimeValue right_dt = *b_dt;
	bool normalize_timezone = ((*a_dt).has_tz || (*b_dt).has_tz) &&
	                          !(*a_dt).is_time && !(*b_dt).is_time &&
	                          PrecisionRank(target) >= PrecisionRank(cql::DateTimeValue::Precision::Hour);
	if (normalize_timezone) {
		left_dt = NormalizeForTemporalCompare(*a_dt);
		right_dt = NormalizeForTemporalCompare(*b_dt);
	}

	int target_rank = PrecisionRank(target);
	if (specified && (PrecisionRank(left_dt.precision) < target_rank || PrecisionRank(right_dt.precision) < target_rank)) {
		auto usable = PrecisionByRank(std::min(std::min(PrecisionRank(left_dt.precision), PrecisionRank(right_dt.precision)),
		                                       target_rank));
		int cmp = CompareTemporalComponents(left_dt, right_dt, usable);
		TemporalCompareResult res;
		res.cmp = cmp;
		res.certain = cmp != 0;
		return res;
	}

	int cmp = CompareTemporalComponents(left_dt, right_dt, target);
	bool certain = true;
	if (!specified && cmp == 0 && PrecisionRank(left_dt.precision) != PrecisionRank(right_dt.precision)) {
		certain = false;
	}

	TemporalCompareResult res;
	res.cmp = cmp;
	res.certain = certain;
	return res;
}

enum class TemporalPredicate { SameOrBefore, SameOrAfter, Before, After, SameAs };

static cql::Optional<bool> EvalTemporalPredicate(const TemporalCompareResult &cmp, TemporalPredicate predicate) {
	switch (predicate) {
	case TemporalPredicate::SameOrBefore:
		if (cmp.cmp < 0) {
			return true;
		}
		if (cmp.cmp > 0) {
			return false;
		}
		return cmp.certain ? cql::Optional<bool>(true) : cql::NullOpt<bool>();
	case TemporalPredicate::SameOrAfter:
		if (cmp.cmp > 0) {
			return true;
		}
		if (cmp.cmp < 0) {
			return false;
		}
		return cmp.certain ? cql::Optional<bool>(true) : cql::NullOpt<bool>();
	case TemporalPredicate::Before:
		if (cmp.cmp < 0) {
			return true;
		}
		if (cmp.cmp > 0) {
			return false;
		}
		return cmp.certain ? cql::Optional<bool>(false) : cql::NullOpt<bool>();
	case TemporalPredicate::After:
		if (cmp.cmp > 0) {
			return true;
		}
		if (cmp.cmp < 0) {
			return false;
		}
		return cmp.certain ? cql::Optional<bool>(false) : cql::NullOpt<bool>();
	case TemporalPredicate::SameAs:
		if (cmp.cmp != 0) {
			return false;
		}
		return cmp.certain ? cql::Optional<bool>(true) : cql::NullOpt<bool>();
	}
	return cql::NullOpt<bool>();
}

#define DEFINE_CQL_TEMPORAL_TWO_UDF(FuncName, predicate)                                                               \
	static void FuncName(DataChunk &args, ExpressionState &state, Vector &result) {                                    \
		idx_t count = args.size();                                                                                     \
		UnifiedVectorFormat a_data, b_data;                                                                            \
		args.data[0].ToUnifiedFormat(count, a_data);                                                                   \
		args.data[1].ToUnifiedFormat(count, b_data);                                                                   \
		auto a_vals = UnifiedVectorFormat::GetData<string_t>(a_data);                                                  \
		auto b_vals = UnifiedVectorFormat::GetData<string_t>(b_data);                                                  \
		result.SetVectorType(VectorType::FLAT_VECTOR);                                                                 \
		auto result_data = FlatVector::GetData<bool>(result);                                                          \
		auto &result_mask = FlatVector::Validity(result);                                                              \
		for (idx_t i = 0; i < count; i++) {                                                                            \
			auto a_idx = a_data.sel->get_index(i);                                                                     \
			auto b_idx = b_data.sel->get_index(i);                                                                     \
			if (!a_data.validity.RowIsValid(a_idx) || !b_data.validity.RowIsValid(b_idx)) {                            \
				result_mask.SetInvalid(i);                                                                             \
				continue;                                                                                              \
			}                                                                                                          \
			auto cmp = CompareTemporal(a_vals[a_idx].GetString(), b_vals[b_idx].GetString(),                           \
			                           cql::NullOpt<cql::DateTimeValue::Precision>());                                \
			if (!cmp) {                                                                                                \
				result_mask.SetInvalid(i);                                                                             \
				continue;                                                                                              \
			}                                                                                                          \
			auto out = EvalTemporalPredicate(*cmp, predicate);                                                         \
			if (!out) {                                                                                                \
				result_mask.SetInvalid(i);                                                                             \
			} else {                                                                                                   \
				result_data[i] = *out;                                                                                 \
			}                                                                                                          \
		}                                                                                                              \
	}

#define DEFINE_CQL_TEMPORAL_THREE_UDF(FuncName, predicate)                                                             \
	static void FuncName(DataChunk &args, ExpressionState &state, Vector &result) {                                    \
		idx_t count = args.size();                                                                                     \
		UnifiedVectorFormat a_data, b_data, p_data;                                                                    \
		args.data[0].ToUnifiedFormat(count, a_data);                                                                   \
		args.data[1].ToUnifiedFormat(count, b_data);                                                                   \
		args.data[2].ToUnifiedFormat(count, p_data);                                                                   \
		auto a_vals = UnifiedVectorFormat::GetData<string_t>(a_data);                                                  \
		auto b_vals = UnifiedVectorFormat::GetData<string_t>(b_data);                                                  \
		auto p_vals = UnifiedVectorFormat::GetData<string_t>(p_data);                                                  \
		result.SetVectorType(VectorType::FLAT_VECTOR);                                                                 \
		auto result_data = FlatVector::GetData<bool>(result);                                                          \
		auto &result_mask = FlatVector::Validity(result);                                                              \
		for (idx_t i = 0; i < count; i++) {                                                                            \
			auto a_idx = a_data.sel->get_index(i);                                                                     \
			auto b_idx = b_data.sel->get_index(i);                                                                     \
			auto p_idx = p_data.sel->get_index(i);                                                                     \
			if (!a_data.validity.RowIsValid(a_idx) || !b_data.validity.RowIsValid(b_idx) ||                            \
			    !p_data.validity.RowIsValid(p_idx)) {                                                                  \
				result_mask.SetInvalid(i);                                                                             \
				continue;                                                                                              \
			}                                                                                                          \
			auto precision = PrecisionFromName(p_vals[p_idx].GetString());                                             \
			if (!precision) {                                                                                          \
				result_mask.SetInvalid(i);                                                                             \
				continue;                                                                                              \
			}                                                                                                          \
			auto cmp = CompareTemporal(a_vals[a_idx].GetString(), b_vals[b_idx].GetString(), precision);               \
			if (!cmp) {                                                                                                \
				result_mask.SetInvalid(i);                                                                             \
				continue;                                                                                              \
			}                                                                                                          \
			auto out = EvalTemporalPredicate(*cmp, predicate);                                                         \
			if (!out) {                                                                                                \
				result_mask.SetInvalid(i);                                                                             \
			} else {                                                                                                   \
				result_data[i] = *out;                                                                                 \
			}                                                                                                          \
		}                                                                                                              \
	}

DEFINE_CQL_TEMPORAL_TWO_UDF(CqlSameOrBeforeFunc, TemporalPredicate::SameOrBefore)
DEFINE_CQL_TEMPORAL_TWO_UDF(CqlSameOrAfterFunc, TemporalPredicate::SameOrAfter)
DEFINE_CQL_TEMPORAL_TWO_UDF(CqlBeforeFunc, TemporalPredicate::Before)
DEFINE_CQL_TEMPORAL_TWO_UDF(CqlAfterFunc, TemporalPredicate::After)
DEFINE_CQL_TEMPORAL_TWO_UDF(CqlDateTimeEqualFunc, TemporalPredicate::SameAs)
DEFINE_CQL_TEMPORAL_THREE_UDF(CqlSameOrBeforePFunc, TemporalPredicate::SameOrBefore)
DEFINE_CQL_TEMPORAL_THREE_UDF(CqlSameOrAfterPFunc, TemporalPredicate::SameOrAfter)
DEFINE_CQL_TEMPORAL_THREE_UDF(CqlBeforePFunc, TemporalPredicate::Before)
DEFINE_CQL_TEMPORAL_THREE_UDF(CqlAfterPFunc, TemporalPredicate::After)
DEFINE_CQL_TEMPORAL_THREE_UDF(CqlSameAsPFunc, TemporalPredicate::SameAs)

struct UncertainRange {
	int64_t low;
	int64_t high;
	bool is_interval;
};

static std::string NormalizeUnitName(const std::string &unit) {
	std::string u = LowerAscii(unit);
	if (!u.empty() && u.back() == 's') {
		u.pop_back();
	}
	if (u == "a") {
		return "year";
	}
	if (u == "mo") {
		return "month";
	}
	if (u == "wk") {
		return "week";
	}
	if (u == "d") {
		return "day";
	}
	if (u == "h") {
		return "hour";
	}
	if (u == "min") {
		return "minute";
	}
	if (u == "s") {
		return "second";
	}
	if (u == "ms") {
		return "millisecond";
	}
	return u;
}

static cql::DateTimeValue::Precision InferPrecisionFromText(const std::string &value) {
	std::string s = value;
	for (char tz : {'+', 'Z'}) {
		auto idx = s.find(tz, 10);
		if (idx != std::string::npos) {
			s = s.substr(0, idx);
			break;
		}
	}
	if (s.size() > 10) {
		for (size_t pos = s.size(); pos-- > 10;) {
			if (s[pos] == '-') {
				s = s.substr(0, pos);
				break;
			}
		}
	}
	if (!s.empty() && (s[0] == 'T' || (s.find(':') != std::string::npos && s.find('-') == std::string::npos))) {
		if (s.find('.') != std::string::npos) return cql::DateTimeValue::Precision::Millisecond;
		size_t colons = std::count(s.begin(), s.end(), ':');
		if (colons >= 2) return cql::DateTimeValue::Precision::Second;
		if (colons >= 1) return cql::DateTimeValue::Precision::Minute;
		return cql::DateTimeValue::Precision::Hour;
	}
	auto t_pos = s.find('T');
	if (t_pos == std::string::npos) {
		t_pos = s.find(' ');
	}
	if (t_pos != std::string::npos) {
		std::string time_part = s.substr(t_pos + 1);
		if (time_part.empty()) {
			std::string date_part = s.substr(0, t_pos);
			size_t dashes = std::count(date_part.begin(), date_part.end(), '-');
			if (dashes >= 2) return cql::DateTimeValue::Precision::Day;
			if (dashes == 1) return cql::DateTimeValue::Precision::Month;
			return cql::DateTimeValue::Precision::Year;
		}
		if (time_part.find('.') != std::string::npos) return cql::DateTimeValue::Precision::Millisecond;
		size_t colons = std::count(time_part.begin(), time_part.end(), ':');
		if (colons >= 2) return cql::DateTimeValue::Precision::Second;
		if (colons >= 1) return cql::DateTimeValue::Precision::Minute;
		return cql::DateTimeValue::Precision::Hour;
	}
	size_t dashes = std::count(s.begin(), s.end(), '-');
	if (dashes >= 2) return cql::DateTimeValue::Precision::Day;
	if (dashes == 1) return cql::DateTimeValue::Precision::Month;
	return cql::DateTimeValue::Precision::Year;
}

static cql::DateTimeValue HighBoundaryValue(const std::string &value) {
	auto parsed = cql::DateTimeValue::parse(value);
	cql::DateTimeValue out = parsed ? *parsed : cql::DateTimeValue();
	out.precision = InferPrecisionFromText(value);
	int rank = PrecisionRank(out.precision);
	if (rank < PrecisionRank(cql::DateTimeValue::Precision::Millisecond)) out.millisecond = 999;
	if (rank < PrecisionRank(cql::DateTimeValue::Precision::Second)) out.second = 59;
	if (rank < PrecisionRank(cql::DateTimeValue::Precision::Minute)) out.minute = 59;
	if (rank < PrecisionRank(cql::DateTimeValue::Precision::Hour)) out.hour = 23;
	if (!out.is_time && rank < PrecisionRank(cql::DateTimeValue::Precision::Day)) {
		out.day = CqlDaysInMonth(out.year, out.month);
	}
	if (!out.is_time && rank < PrecisionRank(cql::DateTimeValue::Precision::Month)) {
		out.month = 12;
		out.day = 31;
	}
	return out;
}

static cql::DateTimeValue DurationHighBoundaryValue(const std::string &value,
                                                    cql::DateTimeValue::Precision unit_precision) {
	auto parsed = cql::DateTimeValue::parse(value);
	cql::DateTimeValue out = parsed ? *parsed : cql::DateTimeValue();
	out.precision = InferPrecisionFromText(value);
	int current_rank = PrecisionRank(out.precision);
	int target_rank = PrecisionRank(unit_precision);

	if (!out.is_time && current_rank < PrecisionRank(cql::DateTimeValue::Precision::Month) &&
	    target_rank >= PrecisionRank(cql::DateTimeValue::Precision::Month)) {
		out.month = 12;
		out.day = 1;
		out.hour = 0;
		out.minute = 0;
		out.second = 0;
		out.millisecond = 0;
	}
	if (!out.is_time && current_rank < PrecisionRank(cql::DateTimeValue::Precision::Day) &&
	    target_rank >= PrecisionRank(cql::DateTimeValue::Precision::Day)) {
		out.day = CqlDaysInMonth(out.year, out.month);
		out.hour = 0;
		out.minute = 0;
		out.second = 0;
		out.millisecond = 0;
	}
	if (current_rank < PrecisionRank(cql::DateTimeValue::Precision::Hour) &&
	    target_rank >= PrecisionRank(cql::DateTimeValue::Precision::Hour)) {
		out.hour = 23;
		out.minute = 0;
		out.second = 0;
		out.millisecond = 0;
	}
	if (current_rank < PrecisionRank(cql::DateTimeValue::Precision::Minute) &&
	    target_rank >= PrecisionRank(cql::DateTimeValue::Precision::Minute)) {
		out.minute = 59;
		out.second = 0;
		out.millisecond = 0;
	}
	if (current_rank < PrecisionRank(cql::DateTimeValue::Precision::Second) &&
	    target_rank >= PrecisionRank(cql::DateTimeValue::Precision::Second)) {
		out.second = 59;
		out.millisecond = 0;
	}
	if (current_rank < PrecisionRank(cql::DateTimeValue::Precision::Millisecond) &&
	    target_rank >= PrecisionRank(cql::DateTimeValue::Precision::Millisecond)) {
		out.millisecond = 999;
	}
	return out;
}

static cql::Optional<int64_t> ComputeDurationBetweenValue(const cql::DateTimeValue &start,
                                                          const cql::DateTimeValue &end,
                                                          const std::string &unit,
                                                          bool is_week) {
	std::string u = NormalizeUnitName(unit);
	if (u == "year") {
		return DurationInCalendarYears(start, end);
	}
	if (u == "month") {
		return DurationInCalendarMonths(start, end);
	}
	if (start.has_tz != end.has_tz) {
		return cql::NullOpt<int64_t>();
	}
	int64_t delta = ToEpochMillisForElapsed(end) - ToEpochMillisForElapsed(start);
	if (is_week || u == "week") {
		return static_cast<int64_t>(static_cast<double>(delta) / static_cast<double>(MS_PER_DAY * 7));
	}
	if (u == "day") {
		return static_cast<int64_t>(static_cast<double>(delta) / static_cast<double>(MS_PER_DAY));
	}
	if (u == "hour") {
		return static_cast<int64_t>(static_cast<double>(delta) / static_cast<double>(MS_PER_HOUR));
	}
	if (u == "minute") {
		return static_cast<int64_t>(static_cast<double>(delta) / static_cast<double>(MS_PER_MINUTE));
	}
	if (u == "second") {
		return static_cast<int64_t>(static_cast<double>(delta) / static_cast<double>(MS_PER_SECOND));
	}
	if (u == "millisecond") {
		return delta;
	}
	return cql::NullOpt<int64_t>();
}

static cql::Optional<int64_t> ComputeDifferenceBetweenValue(const cql::DateTimeValue &start,
                                                            const cql::DateTimeValue &end,
                                                            const std::string &unit,
                                                            bool is_week) {
	std::string u = NormalizeUnitName(unit);
	if (u == "year") {
		return cql::AgeCalculator::diff_years(start, end);
	}
	if (u == "month") {
		return cql::AgeCalculator::diff_months(start, end);
	}
	if (is_week || u == "week") {
		auto days = cql::AgeCalculator::diff_days(start, end);
		if (!days) {
			return cql::NullOpt<int64_t>();
		}
		return *days / 7;
	}
	if (u == "day") {
		return cql::AgeCalculator::diff_days(start, end);
	}
	if (start.has_tz != end.has_tz) {
		return cql::NullOpt<int64_t>();
	}
	int64_t delta = ToEpochMillisForElapsed(end) - ToEpochMillisForElapsed(start);
	if (u == "hour") {
		return delta / MS_PER_HOUR;
	}
	if (u == "minute") {
		return delta / MS_PER_MINUTE;
	}
	if (u == "second") {
		return delta / MS_PER_SECOND;
	}
	if (u == "millisecond") {
		return delta;
	}
	return cql::NullOpt<int64_t>();
}

static cql::Optional<std::string> CqlDurationBetweenString(const std::string &start_text,
                                                           const std::string &end_text,
                                                           const std::string &unit_text) {
	auto start = cql::DateTimeValue::parse(start_text);
	auto end = cql::DateTimeValue::parse(end_text);
	if (!start || !end) {
		return cql::NullOpt<std::string>();
	}
	std::string unit = NormalizeUnitName(unit_text);
	bool is_week = unit == "week";
	std::string duration_unit = is_week ? "day" : unit;
	auto unit_precision = PrecisionFromName(duration_unit);
	if (!unit_precision) {
		return cql::NullOpt<std::string>();
	}
	int unit_rank = PrecisionRank(*unit_precision);
	int start_rank = PrecisionRank(InferPrecisionFromText(start_text));
	int end_rank = PrecisionRank(InferPrecisionFromText(end_text));
	bool date_only = start_text.find('T') == std::string::npos && end_text.find('T') == std::string::npos &&
	                 !start->is_time && !end->is_time;
	bool date_unit = duration_unit == "year" || duration_unit == "month" || duration_unit == "day";
	bool date_fully_specified = date_only && date_unit &&
	                            start_rank == PrecisionRank(cql::DateTimeValue::Precision::Day) &&
	                            end_rank == PrecisionRank(cql::DateTimeValue::Precision::Day);
	bool both_sufficient_precision = date_unit && !date_fully_specified ?
	                                  start_rank > unit_rank && end_rank > unit_rank :
	                                  start_rank >= unit_rank && end_rank >= unit_rank;
	if (both_sufficient_precision || date_fully_specified) {
		auto duration = ComputeDurationBetweenValue(*start, *end, unit_text, is_week);
		if (!duration) return cql::NullOpt<std::string>();
		return std::to_string(*duration);
	}

	auto start_high = HighBoundaryValue(start_text);
	auto end_high = DurationHighBoundaryValue(end_text, *unit_precision);
	auto min_val = ComputeDurationBetweenValue(start_high, *end, unit_text, is_week);
	auto max_val = ComputeDurationBetweenValue(*start, end_high, unit_text, is_week);
	if (!min_val || !max_val) return cql::NullOpt<std::string>();
	if (*min_val == *max_val) {
		return std::to_string(*min_val);
	}
	std::ostringstream oss;
	oss << "{\"start\":" << *min_val << ",\"end\":" << *max_val
	    << ",\"lowClosed\":true,\"highClosed\":true}";
	return oss.str();
}

static cql::Optional<std::string> CqlDifferenceBetweenString(const std::string &start_text,
                                                             const std::string &end_text,
                                                             const std::string &unit_text) {
	auto start = cql::DateTimeValue::parse(start_text);
	auto end = cql::DateTimeValue::parse(end_text);
	if (!start || !end) {
		return cql::NullOpt<std::string>();
	}
	std::string unit = NormalizeUnitName(unit_text);
	bool is_week = unit == "week";
	std::string difference_unit = is_week ? "day" : unit;
	auto unit_precision = PrecisionFromName(difference_unit);
	if (!unit_precision) {
		return cql::NullOpt<std::string>();
	}
	int unit_rank = PrecisionRank(*unit_precision);
	int start_rank = PrecisionRank(InferPrecisionFromText(start_text));
	int end_rank = PrecisionRank(InferPrecisionFromText(end_text));
	bool date_only = start_text.find('T') == std::string::npos && end_text.find('T') == std::string::npos &&
	                 !start->is_time && !end->is_time;
	bool date_unit = difference_unit == "year" || difference_unit == "month" || difference_unit == "day";
	bool both_sufficient_precision = start_rank >= unit_rank && end_rank >= unit_rank;
	bool date_fully_specified = date_only && date_unit &&
	                            start_rank == PrecisionRank(cql::DateTimeValue::Precision::Day) &&
	                            end_rank == PrecisionRank(cql::DateTimeValue::Precision::Day);
	if (both_sufficient_precision || date_fully_specified) {
		auto difference = ComputeDifferenceBetweenValue(*start, *end, unit_text, is_week);
		if (!difference) return cql::NullOpt<std::string>();
		return std::to_string(*difference);
	}

	auto start_high = HighBoundaryValue(start_text);
	auto end_high = HighBoundaryValue(end_text);
	auto min_val = ComputeDifferenceBetweenValue(start_high, *end, unit_text, is_week);
	auto max_val = ComputeDifferenceBetweenValue(*start, end_high, unit_text, is_week);
	if (!min_val || !max_val) return cql::NullOpt<std::string>();
	int64_t low = *min_val;
	int64_t high = *max_val;
	if (low > high) {
		std::swap(low, high);
	}
	if (low == high) {
		return std::to_string(low);
	}
	std::ostringstream oss;
	oss << "{\"start\":" << low << ",\"end\":" << high
	    << ",\"lowClosed\":true,\"highClosed\":true}";
	return oss.str();
}

static cql::Optional<UncertainRange> ParseUncertainRange(const std::string &value) {
	using namespace duckdb_yyjson; // NOLINT
	try {
		size_t pos = 0;
		int64_t scalar = std::stoll(value, &pos);
		if (pos == value.size()) {
			return UncertainRange{scalar, scalar, false};
		}
	} catch (const std::exception &) {
	}
	yyjson_doc *doc = yyjson_read(value.c_str(), value.size(), 0);
	if (!doc) return cql::NullOpt<UncertainRange>();
	yyjson_val *root = yyjson_doc_get_root(doc);
	if (!root || !yyjson_is_obj(root)) {
		yyjson_doc_free(doc);
		return cql::NullOpt<UncertainRange>();
	}
	yyjson_val *low = yyjson_obj_get(root, "start");
	if (!low) low = yyjson_obj_get(root, "low");
	yyjson_val *high = yyjson_obj_get(root, "end");
	if (!high) high = yyjson_obj_get(root, "high");
	if (!low || !high || !yyjson_is_num(low) || !yyjson_is_num(high)) {
		yyjson_doc_free(doc);
		return cql::NullOpt<UncertainRange>();
	}
	UncertainRange range{static_cast<int64_t>(yyjson_get_num(low)), static_cast<int64_t>(yyjson_get_num(high)), true};
	yyjson_doc_free(doc);
	return range;
}

static std::string FormatUncertainRange(int64_t low, int64_t high) {
	if (low == high) {
		return std::to_string(low);
	}
	std::ostringstream oss;
	oss << "{\"start\":" << low << ",\"end\":" << high
	    << ",\"lowClosed\":true,\"highClosed\":true}";
	return oss.str();
}

static void CqlDurationBetweenFunc(DataChunk &args, ExpressionState &state, Vector &result) {
	idx_t count = args.size();
	UnifiedVectorFormat a_data, b_data, u_data;
	args.data[0].ToUnifiedFormat(count, a_data);
	args.data[1].ToUnifiedFormat(count, b_data);
	args.data[2].ToUnifiedFormat(count, u_data);
	auto a_vals = UnifiedVectorFormat::GetData<string_t>(a_data);
	auto b_vals = UnifiedVectorFormat::GetData<string_t>(b_data);
	auto u_vals = UnifiedVectorFormat::GetData<string_t>(u_data);
	result.SetVectorType(VectorType::FLAT_VECTOR);
	auto result_data = FlatVector::GetData<string_t>(result);
	auto &result_mask = FlatVector::Validity(result);
	for (idx_t i = 0; i < count; i++) {
		auto ai = a_data.sel->get_index(i);
		auto bi = b_data.sel->get_index(i);
		auto ui = u_data.sel->get_index(i);
		if (!a_data.validity.RowIsValid(ai) || !b_data.validity.RowIsValid(bi) || !u_data.validity.RowIsValid(ui)) {
			result_mask.SetInvalid(i);
			continue;
		}
		auto out = CqlDurationBetweenString(a_vals[ai].GetString(), b_vals[bi].GetString(), u_vals[ui].GetString());
		if (!out) {
			result_mask.SetInvalid(i);
		} else {
			result_data[i] = StringVector::AddString(result, *out);
		}
	}
}

static void CqlDifferenceBetweenFunc(DataChunk &args, ExpressionState &state, Vector &result) {
	idx_t count = args.size();
	UnifiedVectorFormat a_data, b_data, u_data;
	args.data[0].ToUnifiedFormat(count, a_data);
	args.data[1].ToUnifiedFormat(count, b_data);
	args.data[2].ToUnifiedFormat(count, u_data);
	auto a_vals = UnifiedVectorFormat::GetData<string_t>(a_data);
	auto b_vals = UnifiedVectorFormat::GetData<string_t>(b_data);
	auto u_vals = UnifiedVectorFormat::GetData<string_t>(u_data);
	result.SetVectorType(VectorType::FLAT_VECTOR);
	auto result_data = FlatVector::GetData<string_t>(result);
	auto &result_mask = FlatVector::Validity(result);
	for (idx_t i = 0; i < count; i++) {
		auto ai = a_data.sel->get_index(i);
		auto bi = b_data.sel->get_index(i);
		auto ui = u_data.sel->get_index(i);
		if (!a_data.validity.RowIsValid(ai) || !b_data.validity.RowIsValid(bi) || !u_data.validity.RowIsValid(ui)) {
			result_mask.SetInvalid(i);
			continue;
		}
		auto out = CqlDifferenceBetweenString(a_vals[ai].GetString(), b_vals[bi].GetString(), u_vals[ui].GetString());
		if (!out) {
			result_mask.SetInvalid(i);
		} else {
			result_data[i] = StringVector::AddString(result, *out);
		}
	}
}

#define DEFINE_UNCERTAIN_ARITH(FuncName, expression_low, expression_high)                                             \
	static void FuncName(DataChunk &args, ExpressionState &state, Vector &result) {                                   \
		idx_t count = args.size();                                                                                    \
		UnifiedVectorFormat a_data, b_data;                                                                           \
		args.data[0].ToUnifiedFormat(count, a_data);                                                                  \
		args.data[1].ToUnifiedFormat(count, b_data);                                                                  \
		auto a_vals = UnifiedVectorFormat::GetData<string_t>(a_data);                                                 \
		auto b_vals = UnifiedVectorFormat::GetData<string_t>(b_data);                                                 \
		result.SetVectorType(VectorType::FLAT_VECTOR);                                                                \
		auto result_data = FlatVector::GetData<string_t>(result);                                                     \
		auto &result_mask = FlatVector::Validity(result);                                                             \
		for (idx_t i = 0; i < count; i++) {                                                                           \
			auto ai = a_data.sel->get_index(i);                                                                       \
			auto bi = b_data.sel->get_index(i);                                                                       \
			if (!a_data.validity.RowIsValid(ai) || !b_data.validity.RowIsValid(bi)) {                                  \
				result_mask.SetInvalid(i);                                                                            \
				continue;                                                                                             \
			}                                                                                                         \
			auto a = ParseUncertainRange(a_vals[ai].GetString());                                                     \
			auto b = ParseUncertainRange(b_vals[bi].GetString());                                                     \
			if (!a || !b) { result_mask.SetInvalid(i); continue; }                                                     \
			int64_t low = (expression_low);                                                                           \
			int64_t high = (expression_high);                                                                         \
			result_data[i] = StringVector::AddString(result, FormatUncertainRange(low, high));                        \
		}                                                                                                             \
	}

DEFINE_UNCERTAIN_ARITH(CqlUncertainAddFunc, a->low + b->low, a->high + b->high)
DEFINE_UNCERTAIN_ARITH(CqlUncertainSubtractFunc, a->low - b->high, a->high - b->low)

static void CqlUncertainMultiplyFunc(DataChunk &args, ExpressionState &state, Vector &result) {
	idx_t count = args.size();
	UnifiedVectorFormat a_data, b_data;
	args.data[0].ToUnifiedFormat(count, a_data);
	args.data[1].ToUnifiedFormat(count, b_data);
	auto a_vals = UnifiedVectorFormat::GetData<string_t>(a_data);
	auto b_vals = UnifiedVectorFormat::GetData<string_t>(b_data);
	result.SetVectorType(VectorType::FLAT_VECTOR);
	auto result_data = FlatVector::GetData<string_t>(result);
	auto &result_mask = FlatVector::Validity(result);
	for (idx_t i = 0; i < count; i++) {
		auto ai = a_data.sel->get_index(i);
		auto bi = b_data.sel->get_index(i);
		if (!a_data.validity.RowIsValid(ai) || !b_data.validity.RowIsValid(bi)) {
			result_mask.SetInvalid(i);
			continue;
		}
		auto a = ParseUncertainRange(a_vals[ai].GetString());
		auto b = ParseUncertainRange(b_vals[bi].GetString());
		if (!a || !b) { result_mask.SetInvalid(i); continue; }
		std::vector<int64_t> products = {a->low * b->low, a->low * b->high, a->high * b->low, a->high * b->high};
		auto mm = std::minmax_element(products.begin(), products.end());
		result_data[i] = StringVector::AddString(result, FormatUncertainRange(*mm.first, *mm.second));
	}
}

static void CqlUncertainCompareFunc(DataChunk &args, ExpressionState &state, Vector &result) {
	idx_t count = args.size();
	UnifiedVectorFormat a_data, b_data, op_data;
	args.data[0].ToUnifiedFormat(count, a_data);
	args.data[1].ToUnifiedFormat(count, b_data);
	args.data[2].ToUnifiedFormat(count, op_data);
	auto a_vals = UnifiedVectorFormat::GetData<string_t>(a_data);
	auto b_vals = UnifiedVectorFormat::GetData<string_t>(b_data);
	auto op_vals = UnifiedVectorFormat::GetData<string_t>(op_data);
	result.SetVectorType(VectorType::FLAT_VECTOR);
	auto result_data = FlatVector::GetData<bool>(result);
	auto &result_mask = FlatVector::Validity(result);
	for (idx_t i = 0; i < count; i++) {
		auto ai = a_data.sel->get_index(i);
		auto bi = b_data.sel->get_index(i);
		auto oi = op_data.sel->get_index(i);
		if (!a_data.validity.RowIsValid(ai) || !b_data.validity.RowIsValid(bi) || !op_data.validity.RowIsValid(oi)) {
			result_mask.SetInvalid(i);
			continue;
		}
		auto a = ParseUncertainRange(a_vals[ai].GetString());
		auto b = ParseUncertainRange(b_vals[bi].GetString());
		if (!a || !b) { result_mask.SetInvalid(i); continue; }
		std::string op = op_vals[oi].GetString();
		cql::Optional<bool> out = cql::NullOpt<bool>();
		if (op == ">") {
			if (a->low > b->high) out = true;
			else if (a->high <= b->low) out = false;
		} else if (op == ">=") {
			if (a->low >= b->high) out = true;
			else if (a->high < b->low) out = false;
		} else if (op == "<") {
			if (a->high < b->low) out = true;
			else if (a->low >= b->high) out = false;
		} else if (op == "<=") {
			if (a->high <= b->low) out = true;
			else if (a->low > b->high) out = false;
		} else if (op == "=" || op == "==") {
			if (a->low == a->high && a->low == b->low && b->low == b->high) out = true;
			else if (a->high < b->low || a->low > b->high) out = false;
		}
		if (!out) {
			result_mask.SetInvalid(i);
		} else {
			result_data[i] = *out;
		}
	}
}

// =====================================================================
// Clinical UDFs — Latest, Earliest, claim_principal_diagnosis/procedure
// =====================================================================

// Latest(resources LIST(VARCHAR), date_path VARCHAR) → VARCHAR
static void LatestFunc(DataChunk &args, ExpressionState &state, Vector &result) {
	idx_t count = args.size();

	result.SetVectorType(VectorType::FLAT_VECTOR);
	auto result_data = FlatVector::GetData<string_t>(result);
	auto &result_mask = FlatVector::Validity(result);

	for (idx_t i = 0; i < count; i++) {
		auto list_val = args.data[0].GetValue(i);
		auto path_val = args.data[1].GetValue(i);

		if (list_val.IsNull() || path_val.IsNull()) {
			result_mask.SetInvalid(i);
			continue;
		}

		auto &list_children = ListValue::GetChildren(list_val);
		auto date_path = path_val.GetValue<std::string>();

		std::vector<std::string> resources;
		for (const auto &child : list_children) {
			if (!child.IsNull()) {
				resources.push_back(child.GetValue<std::string>());
			}
		}

		auto latest = cql::find_latest(resources, date_path);
		if (latest) {
			result_data[i] = StringVector::AddString(result, *latest);
		} else {
			result_mask.SetInvalid(i);
		}
	}
}

// Earliest(resources LIST(VARCHAR), date_path VARCHAR) → VARCHAR
static void EarliestFunc(DataChunk &args, ExpressionState &state, Vector &result) {
	idx_t count = args.size();

	result.SetVectorType(VectorType::FLAT_VECTOR);
	auto result_data = FlatVector::GetData<string_t>(result);
	auto &result_mask = FlatVector::Validity(result);

	for (idx_t i = 0; i < count; i++) {
		auto list_val = args.data[0].GetValue(i);
		auto path_val = args.data[1].GetValue(i);

		if (list_val.IsNull() || path_val.IsNull()) {
			result_mask.SetInvalid(i);
			continue;
		}

		auto &list_children = ListValue::GetChildren(list_val);
		auto date_path = path_val.GetValue<std::string>();

		std::vector<std::string> resources;
		for (const auto &child : list_children) {
			if (!child.IsNull()) {
				resources.push_back(child.GetValue<std::string>());
			}
		}

		auto earliest = cql::find_earliest(resources, date_path);
		if (earliest) {
			result_data[i] = StringVector::AddString(result, *earliest);
		} else {
			result_mask.SetInvalid(i);
		}
	}
}

// claim_principal_diagnosis(claim VARCHAR, encounter_id VARCHAR) → VARCHAR
static void ClaimPrincipalDiagnosisFunc(DataChunk &args, ExpressionState &state, Vector &result) {
	idx_t count = args.size();
	UnifiedVectorFormat claim_data, enc_data;
	args.data[0].ToUnifiedFormat(count, claim_data);
	args.data[1].ToUnifiedFormat(count, enc_data);

	auto claims = UnifiedVectorFormat::GetData<string_t>(claim_data);
	auto encounters = UnifiedVectorFormat::GetData<string_t>(enc_data);

	result.SetVectorType(VectorType::FLAT_VECTOR);
	auto result_data = FlatVector::GetData<string_t>(result);
	auto &result_mask = FlatVector::Validity(result);

	for (idx_t i = 0; i < count; i++) {
		auto c_idx = claim_data.sel->get_index(i);
		auto e_idx = enc_data.sel->get_index(i);

		if (!claim_data.validity.RowIsValid(c_idx) || !enc_data.validity.RowIsValid(e_idx)) {
			result_mask.SetInvalid(i);
			continue;
		}

		auto diag = cql::claim_principal_diagnosis(claims[c_idx].GetString(), encounters[e_idx].GetString());
		if (diag) {
			result_data[i] = StringVector::AddString(result, *diag);
		} else {
			result_mask.SetInvalid(i);
		}
	}
}

// claim_principal_procedure(claim VARCHAR, encounter_id VARCHAR) → VARCHAR
static void ClaimPrincipalProcedureFunc(DataChunk &args, ExpressionState &state, Vector &result) {
	idx_t count = args.size();
	UnifiedVectorFormat claim_data, enc_data;
	args.data[0].ToUnifiedFormat(count, claim_data);
	args.data[1].ToUnifiedFormat(count, enc_data);

	auto claims = UnifiedVectorFormat::GetData<string_t>(claim_data);
	auto encounters = UnifiedVectorFormat::GetData<string_t>(enc_data);

	result.SetVectorType(VectorType::FLAT_VECTOR);
	auto result_data = FlatVector::GetData<string_t>(result);
	auto &result_mask = FlatVector::Validity(result);

	for (idx_t i = 0; i < count; i++) {
		auto c_idx = claim_data.sel->get_index(i);
		auto e_idx = enc_data.sel->get_index(i);

		if (!claim_data.validity.RowIsValid(c_idx) || !enc_data.validity.RowIsValid(e_idx)) {
			result_mask.SetInvalid(i);
			continue;
		}

		auto proc = cql::claim_principal_procedure(claims[c_idx].GetString(), encounters[e_idx].GetString());
		if (proc) {
			result_data[i] = StringVector::AddString(result, *proc);
		} else {
			result_mask.SetInvalid(i);
		}
	}
}

// =====================================================================
// Aggregate UDFs — statisticalMedian, Mode, StdDev, Variance
// =====================================================================

// Helper: extract double values from a LIST(DOUBLE) or LIST(VARCHAR) argument
static std::vector<double> ExtractDoubleList(const Value &list_val) {
	std::vector<double> values;
	if (list_val.IsNull()) {
		return values;
	}
	auto &list_children = ListValue::GetChildren(list_val);
	for (const auto &child : list_children) {
		if (!child.IsNull()) {
			try {
				values.push_back(child.GetValue<double>());
			} catch (const std::exception &) {
				// Skip non-numeric values
			}
		}
	}
	return values;
}

// statisticalMedian(values LIST(DOUBLE)) → DOUBLE
static void StatisticalMedianFunc(DataChunk &args, ExpressionState &state, Vector &result) {
	idx_t count = args.size();
	result.SetVectorType(VectorType::FLAT_VECTOR);
	auto result_data = FlatVector::GetData<double>(result);
	auto &result_mask = FlatVector::Validity(result);

	for (idx_t i = 0; i < count; i++) {
		auto list_val = args.data[0].GetValue(i);
		auto values = ExtractDoubleList(list_val);
		auto median = cql::statistical_median(values);
		if (median) {
			result_data[i] = *median;
		} else {
			result_mask.SetInvalid(i);
		}
	}
}

// statisticalMode(values LIST(DOUBLE)) → DOUBLE
static void StatisticalModeFunc(DataChunk &args, ExpressionState &state, Vector &result) {
	idx_t count = args.size();
	result.SetVectorType(VectorType::FLAT_VECTOR);
	auto result_data = FlatVector::GetData<double>(result);
	auto &result_mask = FlatVector::Validity(result);

	for (idx_t i = 0; i < count; i++) {
		auto list_val = args.data[0].GetValue(i);
		auto values = ExtractDoubleList(list_val);
		auto mode = cql::statistical_mode(values);
		if (mode) {
			result_data[i] = *mode;
		} else {
			result_mask.SetInvalid(i);
		}
	}
}

// statisticalStdDev(values LIST(DOUBLE)) → DOUBLE
static void StatisticalStdDevFunc(DataChunk &args, ExpressionState &state, Vector &result) {
	idx_t count = args.size();
	result.SetVectorType(VectorType::FLAT_VECTOR);
	auto result_data = FlatVector::GetData<double>(result);
	auto &result_mask = FlatVector::Validity(result);

	for (idx_t i = 0; i < count; i++) {
		auto list_val = args.data[0].GetValue(i);
		auto values = ExtractDoubleList(list_val);
		auto sd = cql::statistical_stddev(values);
		if (sd) {
			result_data[i] = *sd;
		} else {
			result_mask.SetInvalid(i);
		}
	}
}

// statisticalVariance(values LIST(DOUBLE)) → DOUBLE
static void StatisticalVarianceFunc(DataChunk &args, ExpressionState &state, Vector &result) {
	idx_t count = args.size();
	result.SetVectorType(VectorType::FLAT_VECTOR);
	auto result_data = FlatVector::GetData<double>(result);
	auto &result_mask = FlatVector::Validity(result);

	for (idx_t i = 0; i < count; i++) {
		auto list_val = args.data[0].GetValue(i);
		auto values = ExtractDoubleList(list_val);
		auto var = cql::statistical_variance(values);
		if (var) {
			result_data[i] = *var;
		} else {
			result_mask.SetInvalid(i);
		}
	}
}

// =====================================================================
// Valueset UDFs — extractCodes, extractFirst*, resolveProfileUrl, in_valueset
// =====================================================================

// extractCodes(resource VARCHAR, path VARCHAR) → VARCHAR[]
static void ExtractCodesFunc(DataChunk &args, ExpressionState &state, Vector &result) {
	idx_t count = args.size();
	UnifiedVectorFormat res_data, path_data;
	args.data[0].ToUnifiedFormat(count, res_data);
	args.data[1].ToUnifiedFormat(count, path_data);

	auto resources = UnifiedVectorFormat::GetData<string_t>(res_data);
	auto paths = UnifiedVectorFormat::GetData<string_t>(path_data);

	// Collect offsets first, push all values, then write list_entries
	// to avoid stale pointer after ListVector::PushBack reallocation
	std::vector<idx_t> row_offsets(count);
	std::vector<idx_t> row_counts(count);
	idx_t total_size = 0;

	for (idx_t i = 0; i < count; i++) {
		auto r_idx = res_data.sel->get_index(i);
		auto p_idx = path_data.sel->get_index(i);

		if (!res_data.validity.RowIsValid(r_idx) || !path_data.validity.RowIsValid(p_idx)) {
			row_offsets[i] = total_size;
			row_counts[i] = 0;
			continue;
		}

		auto codes = cql::extract_codes(resources[r_idx].GetString(), paths[p_idx].GetString());
		row_offsets[i] = total_size;
		row_counts[i] = codes.size();
		for (const auto &code : codes) {
			auto code_str = code.system + "|" + code.code;
			ListVector::PushBack(result, Value(code_str));
		}
		total_size += codes.size();
	}

	auto list_entries = ListVector::GetData(result);
	for (idx_t i = 0; i < count; i++) {
		list_entries[i] = {row_offsets[i], row_counts[i]};
	}
	ListVector::SetListSize(result, total_size);
}

// extractFirstCode(resource VARCHAR, path VARCHAR) → VARCHAR
static void ExtractFirstCodeFunc(DataChunk &args, ExpressionState &state, Vector &result) {
	idx_t count = args.size();
	UnifiedVectorFormat res_data, path_data;
	args.data[0].ToUnifiedFormat(count, res_data);
	args.data[1].ToUnifiedFormat(count, path_data);

	auto resources = UnifiedVectorFormat::GetData<string_t>(res_data);
	auto paths = UnifiedVectorFormat::GetData<string_t>(path_data);

	result.SetVectorType(VectorType::FLAT_VECTOR);
	auto result_data = FlatVector::GetData<string_t>(result);
	auto &result_mask = FlatVector::Validity(result);

	for (idx_t i = 0; i < count; i++) {
		auto r_idx = res_data.sel->get_index(i);
		auto p_idx = path_data.sel->get_index(i);

		if (!res_data.validity.RowIsValid(r_idx) || !path_data.validity.RowIsValid(p_idx)) {
			result_mask.SetInvalid(i);
			continue;
		}

		auto code = cql::extract_first_code(resources[r_idx].GetString(), paths[p_idx].GetString());
		if (code.empty()) {
			result_mask.SetInvalid(i);
		} else {
			result_data[i] = StringVector::AddString(result, code);
		}
	}
}

// extractFirstCodeSystem(resource VARCHAR, path VARCHAR) → VARCHAR
static void ExtractFirstCodeSystemFunc(DataChunk &args, ExpressionState &state, Vector &result) {
	idx_t count = args.size();
	UnifiedVectorFormat res_data, path_data;
	args.data[0].ToUnifiedFormat(count, res_data);
	args.data[1].ToUnifiedFormat(count, path_data);

	auto resources = UnifiedVectorFormat::GetData<string_t>(res_data);
	auto paths = UnifiedVectorFormat::GetData<string_t>(path_data);

	result.SetVectorType(VectorType::FLAT_VECTOR);
	auto result_data = FlatVector::GetData<string_t>(result);
	auto &result_mask = FlatVector::Validity(result);

	for (idx_t i = 0; i < count; i++) {
		auto r_idx = res_data.sel->get_index(i);
		auto p_idx = path_data.sel->get_index(i);

		if (!res_data.validity.RowIsValid(r_idx) || !path_data.validity.RowIsValid(p_idx)) {
			result_mask.SetInvalid(i);
			continue;
		}

		auto system = cql::extract_first_code_system(resources[r_idx].GetString(), paths[p_idx].GetString());
		if (system.empty()) {
			result_mask.SetInvalid(i);
		} else {
			result_data[i] = StringVector::AddString(result, system);
		}
	}
}

// extractFirstCodeValue(resource VARCHAR, path VARCHAR) → VARCHAR
static void ExtractFirstCodeValueFunc(DataChunk &args, ExpressionState &state, Vector &result) {
	idx_t count = args.size();
	UnifiedVectorFormat res_data, path_data;
	args.data[0].ToUnifiedFormat(count, res_data);
	args.data[1].ToUnifiedFormat(count, path_data);

	auto resources = UnifiedVectorFormat::GetData<string_t>(res_data);
	auto paths = UnifiedVectorFormat::GetData<string_t>(path_data);

	result.SetVectorType(VectorType::FLAT_VECTOR);
	auto result_data = FlatVector::GetData<string_t>(result);
	auto &result_mask = FlatVector::Validity(result);

	for (idx_t i = 0; i < count; i++) {
		auto r_idx = res_data.sel->get_index(i);
		auto p_idx = path_data.sel->get_index(i);

		if (!res_data.validity.RowIsValid(r_idx) || !path_data.validity.RowIsValid(p_idx)) {
			result_mask.SetInvalid(i);
			continue;
		}

		auto code_val = cql::extract_first_code_value(resources[r_idx].GetString(), paths[p_idx].GetString());
		if (code_val.empty()) {
			result_mask.SetInvalid(i);
		} else {
			result_data[i] = StringVector::AddString(result, code_val);
		}
	}
}

// resolveProfileUrl(profile_url VARCHAR) → VARCHAR
// Maps a FHIR profile URL to its resource type name (e.g., "Patient", "Condition")
static void ResolveProfileUrlFunc(DataChunk &args, ExpressionState &state, Vector &result) {
	idx_t count = args.size();
	UnifiedVectorFormat url_data;
	args.data[0].ToUnifiedFormat(count, url_data);
	auto urls = UnifiedVectorFormat::GetData<string_t>(url_data);

	result.SetVectorType(VectorType::FLAT_VECTOR);
	auto result_data = FlatVector::GetData<string_t>(result);
	auto &result_mask = FlatVector::Validity(result);

	for (idx_t i = 0; i < count; i++) {
		auto u_idx = url_data.sel->get_index(i);
		if (!url_data.validity.RowIsValid(u_idx)) {
			result_mask.SetInvalid(i);
			continue;
		}

		auto resolved = cql::resolve_profile_url(urls[u_idx].GetString());
		if (resolved.empty()) {
			result_mask.SetInvalid(i);
		} else {
			result_data[i] = StringVector::AddString(result, resolved);
		}
	}
}

// Global valueset cache with thread-safe access
// Note: Using std::mutex since DuckDB extensions build with C++14.
// Upgrade to std::shared_mutex (C++17) for concurrent read access when available.
static cql::ValuesetCache g_valueset_cache;
static std::mutex g_valueset_cache_mutex;

struct ValuesetProfileEntry {
	int64_t calls = 0;
	int64_t null_inputs = 0;
	int64_t unloaded_valueset = 0;
	int64_t empty_codes = 0;
	int64_t not_done_matches = 0;
	int64_t code_matches = 0;
	int64_t misses = 0;
	int64_t extracted_codes = 0;
};

static std::unordered_map<std::string, ValuesetProfileEntry> g_valueset_profile;
static std::mutex g_valueset_profile_mutex;

static bool ValuesetProfilingEnabled() {
	const char *value = std::getenv("FHIR4DS_PROFILE_CPP_VALUESET");
	return value && (std::string(value) == "1" || std::string(value) == "true" || std::string(value) == "yes");
}

static std::string ValuesetProfileKey(const std::string &path, const std::string &url) {
	return path + "\t" + url;
}

static std::string EscapeJsonString(const std::string &value) {
	std::ostringstream out;
	for (char ch : value) {
		switch (ch) {
		case '\\':
			out << "\\\\";
			break;
		case '"':
			out << "\\\"";
			break;
		case '\n':
			out << "\\n";
			break;
		case '\r':
			out << "\\r";
			break;
		case '\t':
			out << "\\t";
			break;
		default:
			out << ch;
			break;
		}
	}
	return out.str();
}

static void UpdateValuesetProfile(bool enabled, const std::string &path, const std::string &url, int64_t calls = 0,
                                  int64_t null_inputs = 0, int64_t unloaded_valueset = 0, int64_t empty_codes = 0,
                                  int64_t not_done_matches = 0, int64_t code_matches = 0, int64_t misses = 0,
                                  int64_t extracted_codes = 0) {
	if (!enabled) {
		return;
	}
	std::lock_guard<std::mutex> lock(g_valueset_profile_mutex);
	auto &entry = g_valueset_profile[ValuesetProfileKey(path, url)];
	entry.calls += calls;
	entry.null_inputs += null_inputs;
	entry.unloaded_valueset += unloaded_valueset;
	entry.empty_codes += empty_codes;
	entry.not_done_matches += not_done_matches;
	entry.code_matches += code_matches;
	entry.misses += misses;
	entry.extracted_codes += extracted_codes;
}

// in_valueset(resource VARCHAR, path VARCHAR, valueset_url VARCHAR) → BOOLEAN
static void InValuesetFunc(DataChunk &args, ExpressionState &state, Vector &result) {
	idx_t count = args.size();
	UnifiedVectorFormat res_data, path_data, url_data;
	args.data[0].ToUnifiedFormat(count, res_data);
	args.data[1].ToUnifiedFormat(count, path_data);
	args.data[2].ToUnifiedFormat(count, url_data);

	auto resources = UnifiedVectorFormat::GetData<string_t>(res_data);
	auto paths = UnifiedVectorFormat::GetData<string_t>(path_data);
	auto urls = UnifiedVectorFormat::GetData<string_t>(url_data);

	result.SetVectorType(VectorType::FLAT_VECTOR);
	auto result_data = FlatVector::GetData<bool>(result);
	auto &result_mask = FlatVector::Validity(result);
	bool profile_enabled = ValuesetProfilingEnabled();

	for (idx_t i = 0; i < count; i++) {
		auto r_idx = res_data.sel->get_index(i);
		auto p_idx = path_data.sel->get_index(i);
		auto u_idx = url_data.sel->get_index(i);

		if (!res_data.validity.RowIsValid(r_idx) || !path_data.validity.RowIsValid(p_idx) ||
		    !url_data.validity.RowIsValid(u_idx)) {
			UpdateValuesetProfile(profile_enabled, "<null>", "<null>", 1, 1);
			result_mask.SetInvalid(i);
			continue;
		}

		auto resource_str = resources[r_idx].GetString();
		auto path_str = paths[p_idx].GetString();
		auto url_str = urls[u_idx].GetString();
		UpdateValuesetProfile(profile_enabled, path_str, url_str, 1);

		bool valueset_loaded = false;
		{
			std::lock_guard<std::mutex> lock(g_valueset_cache_mutex);
			valueset_loaded = g_valueset_cache.find(url_str) != g_valueset_cache.end();
		}
		if (!valueset_loaded) {
			UpdateValuesetProfile(profile_enabled, path_str, url_str, 0, 0, 1);
			result_mask.SetInvalid(i);
			continue;
		}

		auto extraction = cql::extract_codes_with_not_done_valueset(resource_str, path_str, url_str);
		const auto &codes = extraction.codes;
		UpdateValuesetProfile(profile_enabled, path_str, url_str, 0, 0, 0, 0, 0, 0, 0,
		                      static_cast<int64_t>(codes.size()));
		if (codes.empty()) {
			if (extraction.has_not_done_valueset) {
				result_data[i] = true;
				UpdateValuesetProfile(profile_enabled, path_str, url_str, 0, 0, 0, 1, 1);
			} else {
				result_data[i] = false;
				UpdateValuesetProfile(profile_enabled, path_str, url_str, 0, 0, 0, 1, 0, 0, 1);
			}
			continue;
		}
		bool found = false;
		{
			std::lock_guard<std::mutex> lock(g_valueset_cache_mutex);
			for (const auto &code : codes) {
				auto norm_system = cql::normalize_system(code.system);
				if (cql::in_valueset(code.code, norm_system, url_str, g_valueset_cache)) {
					found = true;
					break;
				}
				if (norm_system != code.system && cql::in_valueset(code.code, code.system, url_str, g_valueset_cache)) {
					found = true;
					break;
				}
				// Also check code-only match (empty system)
				if (cql::in_valueset(code.code, "", url_str, g_valueset_cache)) {
					found = true;
					break;
				}
			}
		}
		result_data[i] = found;
		UpdateValuesetProfile(profile_enabled, path_str, url_str, 0, 0, 0, 0, 0, found ? 1 : 0, found ? 0 : 1);
	}
}

static void ValuesetCacheClearFunc(DataChunk &args, ExpressionState &state, Vector &result) {
	std::lock_guard<std::mutex> lock(g_valueset_cache_mutex);
	g_valueset_cache.clear();
	result.SetVectorType(VectorType::CONSTANT_VECTOR);
	ConstantVector::GetData<bool>(result)[0] = true;
}

static void ValuesetCacheAddFunc(DataChunk &args, ExpressionState &state, Vector &result) {
	idx_t count = args.size();
	UnifiedVectorFormat url_data, system_data, code_data;
	args.data[0].ToUnifiedFormat(count, url_data);
	args.data[1].ToUnifiedFormat(count, system_data);
	args.data[2].ToUnifiedFormat(count, code_data);

	auto urls = UnifiedVectorFormat::GetData<string_t>(url_data);
	auto systems = UnifiedVectorFormat::GetData<string_t>(system_data);
	auto codes = UnifiedVectorFormat::GetData<string_t>(code_data);

	result.SetVectorType(VectorType::FLAT_VECTOR);
	auto result_data = FlatVector::GetData<bool>(result);
	auto &result_mask = FlatVector::Validity(result);

	std::lock_guard<std::mutex> lock(g_valueset_cache_mutex);
	for (idx_t i = 0; i < count; i++) {
		auto u_idx = url_data.sel->get_index(i);
		auto c_idx = code_data.sel->get_index(i);
		if (!url_data.validity.RowIsValid(u_idx) || !code_data.validity.RowIsValid(c_idx)) {
			result_mask.SetInvalid(i);
			continue;
		}
		std::string url = urls[u_idx].GetString();
		std::string code = codes[c_idx].GetString();
		std::string system;
		auto s_idx = system_data.sel->get_index(i);
		if (system_data.validity.RowIsValid(s_idx)) {
			system = systems[s_idx].GetString();
		}
		auto normalized_system = cql::normalize_system(system);
		g_valueset_cache[url].insert(normalized_system + "|" + code);
		if (normalized_system != system) {
			g_valueset_cache[url].insert(system + "|" + code);
		}
		result_data[i] = true;
	}
}

static void ValuesetCacheSizeFunc(DataChunk &args, ExpressionState &state, Vector &result) {
	int64_t total = 0;
	{
		std::lock_guard<std::mutex> lock(g_valueset_cache_mutex);
		for (const auto &entry : g_valueset_cache) {
			total += static_cast<int64_t>(entry.second.size());
		}
	}
	result.SetVectorType(VectorType::CONSTANT_VECTOR);
	ConstantVector::GetData<int64_t>(result)[0] = total;
}

static void ValuesetProfileClearFunc(DataChunk &args, ExpressionState &state, Vector &result) {
	std::lock_guard<std::mutex> lock(g_valueset_profile_mutex);
	g_valueset_profile.clear();
	result.SetVectorType(VectorType::CONSTANT_VECTOR);
	ConstantVector::GetData<bool>(result)[0] = true;
}

static void ValuesetProfileJsonFunc(DataChunk &args, ExpressionState &state, Vector &result) {
	std::vector<std::pair<std::string, ValuesetProfileEntry>> entries;
	{
		std::lock_guard<std::mutex> lock(g_valueset_profile_mutex);
		entries.reserve(g_valueset_profile.size());
		for (const auto &entry : g_valueset_profile) {
			entries.push_back(entry);
		}
	}
	typedef std::pair<std::string, ValuesetProfileEntry> ProfilePair;
	std::sort(entries.begin(), entries.end(), [](const ProfilePair &left, const ProfilePair &right) {
		return left.second.calls > right.second.calls;
	});

	std::ostringstream out;
	out << "[";
	bool first = true;
	for (const auto &entry : entries) {
		auto sep = entry.first.find('\t');
		auto path = sep == std::string::npos ? entry.first : entry.first.substr(0, sep);
		auto url = sep == std::string::npos ? "" : entry.first.substr(sep + 1);
		if (!first) {
			out << ",";
		}
		first = false;
		out << "{\"path\":\"" << EscapeJsonString(path) << "\",";
		out << "\"valueset_url\":\"" << EscapeJsonString(url) << "\",";
		out << "\"calls\":" << entry.second.calls << ",";
		out << "\"null_inputs\":" << entry.second.null_inputs << ",";
		out << "\"unloaded_valueset\":" << entry.second.unloaded_valueset << ",";
		out << "\"empty_codes\":" << entry.second.empty_codes << ",";
		out << "\"not_done_matches\":" << entry.second.not_done_matches << ",";
		out << "\"code_matches\":" << entry.second.code_matches << ",";
		out << "\"misses\":" << entry.second.misses << ",";
		out << "\"extracted_codes\":" << entry.second.extracted_codes << "}";
	}
	out << "]";

	result.SetVectorType(VectorType::CONSTANT_VECTOR);
	ConstantVector::GetData<string_t>(result)[0] = StringVector::AddString(result, out.str());
}

// =====================================================================
// Missing datetime UDFs — dateComponent, dateTimeTimeOfDay,
// quantityToInterval, dateAddQuantity, dateSubtractQuantity
// =====================================================================

// dateComponent(date VARCHAR, component VARCHAR) → BIGINT
static void DateComponentFunc(DataChunk &args, ExpressionState &state, Vector &result) {
	idx_t count = args.size();
	UnifiedVectorFormat date_data, comp_data;
	args.data[0].ToUnifiedFormat(count, date_data);
	args.data[1].ToUnifiedFormat(count, comp_data);

	auto dates = UnifiedVectorFormat::GetData<string_t>(date_data);
	auto comps = UnifiedVectorFormat::GetData<string_t>(comp_data);

	result.SetVectorType(VectorType::FLAT_VECTOR);
	auto result_data = FlatVector::GetData<int64_t>(result);
	auto &result_mask = FlatVector::Validity(result);

	for (idx_t i = 0; i < count; i++) {
		auto d_idx = date_data.sel->get_index(i);
		auto c_idx = comp_data.sel->get_index(i);

		if (!date_data.validity.RowIsValid(d_idx) || !comp_data.validity.RowIsValid(c_idx)) {
			result_mask.SetInvalid(i);
			continue;
		}

		std::string input = dates[d_idx].GetString();
		auto dt = cql::DateTimeValue::parse(input);
		if (!dt) {
			result_mask.SetInvalid(i);
			continue;
		}

		std::string component = comps[c_idx].GetString();
		int value_rank = PrecisionRank(dt->precision);
		if (component == "year" && !dt->is_time) {
			result_data[i] = dt->year;
		} else if (component == "month" && !dt->is_time && value_rank >= PrecisionRank(cql::DateTimeValue::Precision::Month)) {
			result_data[i] = dt->month;
		} else if (component == "day" && !dt->is_time && value_rank >= PrecisionRank(cql::DateTimeValue::Precision::Day)) {
			result_data[i] = dt->day;
		} else if (component == "hour" && dt->has_time && value_rank >= PrecisionRank(cql::DateTimeValue::Precision::Hour)) {
			result_data[i] = dt->hour;
		} else if (component == "minute" && dt->has_time && value_rank >= PrecisionRank(cql::DateTimeValue::Precision::Minute)) {
			result_data[i] = dt->minute;
		} else if (component == "second" && dt->has_time && value_rank >= PrecisionRank(cql::DateTimeValue::Precision::Second)) {
			result_data[i] = dt->second;
		} else if (component == "millisecond" && dt->has_time && value_rank >= PrecisionRank(cql::DateTimeValue::Precision::Millisecond)) {
			result_data[i] = dt->millisecond;
		} else {
			result_mask.SetInvalid(i);
		}
	}
}

// dateTimeTimeOfDay() → VARCHAR
static void DateTimeTimeOfDayFunc(DataChunk &args, ExpressionState &state, Vector &result) {
	auto now = std::chrono::system_clock::now();
	auto time_t_now = std::chrono::system_clock::to_time_t(now);
	std::tm tm_buf;
#ifdef _WIN32
	gmtime_s(&tm_buf, &time_t_now);
#else
	gmtime_r(&time_t_now, &tm_buf);
#endif
	char buf[16];
	snprintf(buf, sizeof(buf), "T%02d:%02d:%02d", tm_buf.tm_hour, tm_buf.tm_min, tm_buf.tm_sec);
	std::string time_str(buf);

	result.SetVectorType(VectorType::CONSTANT_VECTOR);
	ConstantVector::GetData<string_t>(result)[0] = StringVector::AddString(result, time_str);
}

// UCUM time unit mapping for quantity operations
static int64_t QuantityToDays(double value, const std::string &unit) {
	if (unit == "a" || unit == "year" || unit == "years") {
		return static_cast<int64_t>(value * DAYS_PER_YEAR);
	} else if (unit == "mo" || unit == "month" || unit == "months") {
		return static_cast<int64_t>(value * DAYS_PER_MONTH);
	} else if (unit == "wk" || unit == "week" || unit == "weeks") {
		return static_cast<int64_t>(value * 7);
	} else if (unit == "d" || unit == "day" || unit == "days") {
		return static_cast<int64_t>(value);
	} else if (unit == "h" || unit == "hour" || unit == "hours") {
		return static_cast<int64_t>(value / 24.0);
	}
	return static_cast<int64_t>(value);
}

static bool IsSupportedDateQuantityUnit(const std::string &unit) {
	std::string normalized = NormalizeUnitName(unit);
	return normalized == "year" || normalized == "month" || normalized == "week" ||
	       normalized == "day" || normalized == "hour" || normalized == "minute" ||
	       normalized == "second" || normalized == "millisecond";
}

static bool IsSupportedDateQuantityValue(double value, const std::string &unit) {
	if (!std::isfinite(value)) return false;
	double abs_value = std::fabs(value);
	std::string normalized = NormalizeUnitName(unit);
	if (normalized == "year") return abs_value <= 10000.0;
	if (normalized == "month") return abs_value <= 120000.0;
	if (normalized == "week") return abs_value <= 600000.0;
	if (normalized == "day") return abs_value <= 4000000.0;
	if (normalized == "hour") return abs_value <= 100000000.0;
	if (normalized == "minute") return abs_value <= 6000000000.0;
	if (normalized == "second") return abs_value <= 4000000.0 * 86400.0;
	if (normalized == "millisecond") return abs_value <= 4000000.0 * static_cast<double>(MS_PER_DAY);
	return false;
}

// quantityToInterval(quantity VARCHAR) → VARCHAR
static void QuantityToIntervalFunc(DataChunk &args, ExpressionState &state, Vector &result) {
	idx_t count = args.size();
	UnifiedVectorFormat q_data;
	args.data[0].ToUnifiedFormat(count, q_data);
	auto quantities = UnifiedVectorFormat::GetData<string_t>(q_data);

	result.SetVectorType(VectorType::FLAT_VECTOR);
	auto result_data = FlatVector::GetData<string_t>(result);
	auto &result_mask = FlatVector::Validity(result);

	for (idx_t i = 0; i < count; i++) {
		auto q_idx = q_data.sel->get_index(i);
		if (!q_data.validity.RowIsValid(q_idx)) {
			result_mask.SetInvalid(i);
			continue;
		}

		std::string q_str = quantities[q_idx].GetString();
		auto parsed = cql::parse_quantity_json(q_str);
			if (!parsed.has_value() || parsed->code.empty() ||
			    !IsSupportedDateQuantityUnit(parsed->code) ||
			    !IsSupportedDateQuantityValue(parsed->value, parsed->code)) {
				result_mask.SetInvalid(i);
				continue;
			}
			double value = parsed->value;
			std::string unit = parsed->code;

		int64_t days = QuantityToDays(value, unit);
		std::string interval_str = std::to_string(days) + " days";
		result_data[i] = StringVector::AddString(result, interval_str);
	}
}

// Calendar-aware helpers for year/month arithmetic
static bool IsLeapYear(int32_t year) {
	return (year % 4 == 0 && (year % 100 != 0 || year % 400 == 0));
}

static int32_t CalendarDaysInMonth(int32_t year, int32_t month) {
	static const int32_t dim[] = {0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31};
	if (month == 2 && IsLeapYear(year)) {
		return 29;
	}
	return dim[month];
}

static cql::DateTimeValue AddYears(const cql::DateTimeValue &dt, int32_t years) {
	cql::DateTimeValue result = dt;
	result.year = dt.year + years;
	int32_t max_day = CalendarDaysInMonth(result.year, result.month);
	if (result.day > max_day) {
		result.day = max_day;
	}
	return result;
}

static cql::DateTimeValue AddMonths(const cql::DateTimeValue &dt, int32_t months) {
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

	int32_t max_day = CalendarDaysInMonth(result.year, result.month);
	if (result.day > max_day) {
		result.day = max_day;
	}
	return result;
}

// Helper: add days to a DateTimeValue
static cql::DateTimeValue AddDays(const cql::DateTimeValue &dt, int64_t days) {
	// Convert to Julian day, add, convert back
	int64_t jdn = dt.to_julian_day() + days;

	// Inverse Julian day calculation
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

// Helper: add milliseconds to a DateTimeValue (for sub-day units: hours, minutes, seconds, ms)
static cql::DateTimeValue AddMilliseconds(const cql::DateTimeValue &dt, int64_t millis) {
	if (dt.is_time) {
		int64_t current_ms = static_cast<int64_t>(dt.hour) * MS_PER_HOUR +
		                     static_cast<int64_t>(dt.minute) * MS_PER_MINUTE +
		                     static_cast<int64_t>(dt.second) * MS_PER_SECOND +
		                     static_cast<int64_t>(dt.millisecond);
		int64_t wrapped_ms = (current_ms + millis) % MS_PER_DAY;
		if (wrapped_ms < 0) {
			wrapped_ms += MS_PER_DAY;
		}

		cql::DateTimeValue result = dt;
		result.hour = static_cast<int32_t>(wrapped_ms / MS_PER_HOUR);
		wrapped_ms %= MS_PER_HOUR;
		result.minute = static_cast<int32_t>(wrapped_ms / MS_PER_MINUTE);
		wrapped_ms %= MS_PER_MINUTE;
		result.second = static_cast<int32_t>(wrapped_ms / MS_PER_SECOND);
		result.millisecond = static_cast<int32_t>(wrapped_ms % MS_PER_SECOND);
		return result;
	}

	int64_t epoch_ms = dt.to_epoch_millis() + millis;

	// Convert epoch_ms back to DateTimeValue
	int64_t unix_jdn = 2440588LL; // Jan 1, 1970
	int64_t day_ms = MS_PER_DAY;

	// Handle negative epoch_ms (dates before 1970)
	int64_t total_days = epoch_ms / day_ms;
	int64_t remainder_ms = epoch_ms % day_ms;
	if (remainder_ms < 0) {
		total_days -= 1;
		remainder_ms += day_ms;
	}

	int64_t jdn = total_days + unix_jdn;

	// Inverse Julian day calculation
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
	result.hour = static_cast<int32_t>(remainder_ms / MS_PER_HOUR);
	remainder_ms %= MS_PER_HOUR;
	result.minute = static_cast<int32_t>(remainder_ms / MS_PER_MINUTE);
	remainder_ms %= MS_PER_MINUTE;
	result.second = static_cast<int32_t>(remainder_ms / MS_PER_SECOND);
	result.millisecond = static_cast<int32_t>(remainder_ms % MS_PER_SECOND);
	return result;
}

// Convert quantity value+unit to milliseconds for sub-day units; returns 0 for day+ units
static int64_t QuantityToMillis(double value, const std::string &unit) {
	if (unit == "h" || unit == "hour" || unit == "hours") {
		return static_cast<int64_t>(value * static_cast<double>(MS_PER_HOUR));
	} else if (unit == "min" || unit == "minute" || unit == "minutes") {
		return static_cast<int64_t>(value * static_cast<double>(MS_PER_MINUTE));
	} else if (unit == "s" || unit == "second" || unit == "seconds") {
		return static_cast<int64_t>(value * static_cast<double>(MS_PER_SECOND));
	} else if (unit == "ms" || unit == "millisecond" || unit == "milliseconds") {
		return static_cast<int64_t>(value);
	}
	return 0;
}

static bool IsSubDayUnit(const std::string &unit) {
	return unit == "h" || unit == "hour" || unit == "hours" ||
	       unit == "min" || unit == "minute" || unit == "minutes" ||
	       unit == "s" || unit == "second" || unit == "seconds" ||
	       unit == "ms" || unit == "millisecond" || unit == "milliseconds";
}

static int UnitPrecisionRank(const std::string &unit) {
	std::string u = NormalizeUnitName(unit);
	if (u == "year") return 0;
	if (u == "month") return 1;
	if (u == "week" || u == "day") return 2;
	if (u == "hour") return 3;
	if (u == "minute") return 4;
	if (u == "second") return 5;
	if (u == "millisecond") return 6;
	return 6;
}

static int64_t PrecisionConversionDivisor(int from_rank, int to_rank) {
	static const int64_t conversion[] = {12, 30, 24, 60, 60, 1000};
	int64_t divisor = 1;
	for (int rank = from_rank; rank < to_rank && rank < 6; rank++) {
		divisor *= conversion[rank];
	}
	return divisor;
}

static std::string UnitForPrecisionRank(int rank) {
	switch (rank) {
	case 0:
		return "years";
	case 1:
		return "months";
	case 2:
		return "days";
	case 3:
		return "hours";
	case 4:
		return "minutes";
	case 5:
		return "seconds";
	default:
		return "milliseconds";
	}
}

static void ValidateCqlDateTimeRange(const cql::DateTimeValue &dt) {
	if (dt.year < 1 || dt.year > 9999) {
		throw InvalidInputException("DateTime arithmetic overflow");
	}
}

static bool IsDayPrecisionDateTimeMarker(const std::string &value) {
	return value.size() == 11 && value[4] == '-' && value[7] == '-' && value[10] == 'T';
}

static bool IsYearPrecisionDateTimeMarker(const std::string &value) {
	return value.size() == 5 && value[4] == 'T';
}

static bool IsMonthPrecisionDateTimeMarker(const std::string &value) {
	return value.size() == 8 && value[4] == '-' && value[7] == 'T';
}

static std::string FormatYearPrecisionDateTimeMarker(const cql::DateTimeValue &dt) {
	char buf[8];
	std::snprintf(buf, sizeof(buf), "%04dT", dt.year);
	return std::string(buf);
}

static std::string FormatMonthPrecisionDateTimeMarker(const cql::DateTimeValue &dt) {
	char buf[12];
	std::snprintf(buf, sizeof(buf), "%04d-%02dT", dt.year, dt.month);
	return std::string(buf);
}

static std::string FormatDayPrecisionDateTimeMarker(const cql::DateTimeValue &dt) {
	char buf[16];
	std::snprintf(buf, sizeof(buf), "%04d-%02d-%02dT", dt.year, dt.month, dt.day);
	return std::string(buf);
}

static std::string FormatQuantityDateTimeResult(const cql::DateTimeValue &dt, const std::string &input) {
	if (input.find('T') == std::string::npos && input.find(' ') == std::string::npos) {
		char buf[16];
		if (dt.precision == cql::DateTimeValue::Precision::Year) {
			std::snprintf(buf, sizeof(buf), "%04d", dt.year);
			return std::string(buf);
		}
		if (dt.precision == cql::DateTimeValue::Precision::Month) {
			std::snprintf(buf, sizeof(buf), "%04d-%02d", dt.year, dt.month);
			return std::string(buf);
		}
		if (dt.precision == cql::DateTimeValue::Precision::Day) {
			std::snprintf(buf, sizeof(buf), "%04d-%02d-%02d", dt.year, dt.month, dt.day);
			return std::string(buf);
		}
	}
	if (IsYearPrecisionDateTimeMarker(input) && !dt.has_time &&
	    dt.precision == cql::DateTimeValue::Precision::Year) {
		return FormatYearPrecisionDateTimeMarker(dt);
	}
	if (IsMonthPrecisionDateTimeMarker(input) && !dt.has_time &&
	    dt.precision == cql::DateTimeValue::Precision::Month) {
		return FormatMonthPrecisionDateTimeMarker(dt);
	}
	if (IsDayPrecisionDateTimeMarker(input) && !dt.has_time &&
	    dt.precision == cql::DateTimeValue::Precision::Day) {
		return FormatDayPrecisionDateTimeMarker(dt);
	}
	return dt.to_string();
}

static cql::DateTimeValue ApplyQuantityAtInputPrecision(const cql::DateTimeValue &dt, double value,
                                                        std::string unit) {
	int input_rank = PrecisionRank(dt.precision);
	int unit_rank = UnitPrecisionRank(unit);
	double effective_value = value;
	std::string effective_unit = LowerAscii(unit);
	if (unit_rank > input_rank) {
		int64_t divisor = PrecisionConversionDivisor(input_rank, unit_rank);
		effective_value = divisor > 0 ? static_cast<int64_t>(value) / divisor : static_cast<int64_t>(value);
		effective_unit = UnitForPrecisionRank(input_rank);
	}
	std::string normalized = NormalizeUnitName(effective_unit);
	cql::DateTimeValue out;
	int32_t int_value = static_cast<int32_t>(effective_value);
	if (normalized == "year") {
		out = AddYears(dt, int_value);
	} else if (normalized == "month") {
		out = AddMonths(dt, int_value);
	} else if (normalized == "week") {
		out = AddDays(dt, int_value * 7);
	} else if (normalized == "day") {
		out = AddMilliseconds(dt, static_cast<int64_t>(effective_value * static_cast<double>(MS_PER_DAY)));
	} else if (IsSubDayUnit(effective_unit)) {
		out = AddMilliseconds(dt, QuantityToMillis(effective_value, effective_unit));
	} else {
		out = AddDays(dt, QuantityToDays(effective_value, effective_unit));
	}
	out.precision = dt.precision;
	out.is_time = dt.is_time;
	if (PrecisionRank(out.precision) >= PrecisionRank(cql::DateTimeValue::Precision::Hour)) {
		out.has_time = true;
	} else {
		out.has_time = dt.has_time && dt.precision == cql::DateTimeValue::Precision::Day;
	}
	ValidateCqlDateTimeRange(out);
	return out;
}

// dateAddQuantity(date VARCHAR, quantity VARCHAR) → VARCHAR
static void DateAddQuantityFunc(DataChunk &args, ExpressionState &state, Vector &result) {
	idx_t count = args.size();
	UnifiedVectorFormat date_data, q_data;
	args.data[0].ToUnifiedFormat(count, date_data);
	args.data[1].ToUnifiedFormat(count, q_data);

	auto dates = UnifiedVectorFormat::GetData<string_t>(date_data);
	auto quantities = UnifiedVectorFormat::GetData<string_t>(q_data);

	result.SetVectorType(VectorType::FLAT_VECTOR);
	auto result_data = FlatVector::GetData<string_t>(result);
	auto &result_mask = FlatVector::Validity(result);

	for (idx_t i = 0; i < count; i++) {
		auto d_idx = date_data.sel->get_index(i);
		auto q_idx = q_data.sel->get_index(i);

		if (!date_data.validity.RowIsValid(d_idx) || !q_data.validity.RowIsValid(q_idx)) {
			result_mask.SetInvalid(i);
			continue;
		}

		std::string input = dates[d_idx].GetString();
		auto dt = cql::DateTimeValue::parse(input);
		if (!dt) {
			result_mask.SetInvalid(i);
			continue;
		}

		std::string q_str = quantities[q_idx].GetString();
		auto parsed = cql::parse_quantity_json(q_str);
		if (!parsed.has_value() || parsed->code.empty() ||
		    !IsSupportedDateQuantityUnit(parsed->code) ||
		    !IsSupportedDateQuantityValue(parsed->value, parsed->code)) {
			result_mask.SetInvalid(i);
			continue;
		}
		double value = parsed->value;
		std::string unit = parsed->code;

		cql::DateTimeValue new_dt = ApplyQuantityAtInputPrecision(*dt, value, unit);
		result_data[i] = StringVector::AddString(result, FormatQuantityDateTimeResult(new_dt, input));
	}
}

// dateSubtractQuantity(date VARCHAR, quantity VARCHAR) → VARCHAR
static void DateSubtractQuantityFunc(DataChunk &args, ExpressionState &state, Vector &result) {
	idx_t count = args.size();
	UnifiedVectorFormat date_data, q_data;
	args.data[0].ToUnifiedFormat(count, date_data);
	args.data[1].ToUnifiedFormat(count, q_data);

	auto dates = UnifiedVectorFormat::GetData<string_t>(date_data);
	auto quantities = UnifiedVectorFormat::GetData<string_t>(q_data);

	result.SetVectorType(VectorType::FLAT_VECTOR);
	auto result_data = FlatVector::GetData<string_t>(result);
	auto &result_mask = FlatVector::Validity(result);

	for (idx_t i = 0; i < count; i++) {
		auto d_idx = date_data.sel->get_index(i);
		auto q_idx = q_data.sel->get_index(i);

		if (!date_data.validity.RowIsValid(d_idx) || !q_data.validity.RowIsValid(q_idx)) {
			result_mask.SetInvalid(i);
			continue;
		}

		std::string input = dates[d_idx].GetString();
		auto dt = cql::DateTimeValue::parse(input);
		if (!dt) {
			result_mask.SetInvalid(i);
			continue;
		}

		std::string q_str = quantities[q_idx].GetString();
		auto parsed = cql::parse_quantity_json(q_str);
		if (!parsed.has_value() || parsed->code.empty() ||
		    !IsSupportedDateQuantityUnit(parsed->code) ||
		    !IsSupportedDateQuantityValue(parsed->value, parsed->code)) {
			result_mask.SetInvalid(i);
			continue;
		}
		double value = parsed->value;
		std::string unit = parsed->code;

		cql::DateTimeValue new_dt = ApplyQuantityAtInputPrecision(*dt, -value, unit);
		result_data[i] = StringVector::AddString(result, FormatQuantityDateTimeResult(new_dt, input));
	}
}

// =====================================================================
// collapse_intervals(intervals_json VARCHAR) → VARCHAR
// =====================================================================
static void CollapseIntervalsFunc(DataChunk &args, ExpressionState &state, Vector &result) {
	idx_t count = args.size();
	UnifiedVectorFormat iv_data;
	args.data[0].ToUnifiedFormat(count, iv_data);
	auto intervals = UnifiedVectorFormat::GetData<string_t>(iv_data);

	result.SetVectorType(VectorType::FLAT_VECTOR);
	auto result_data = FlatVector::GetData<string_t>(result);
	auto &result_mask = FlatVector::Validity(result);

	for (idx_t i = 0; i < count; i++) {
		auto idx = iv_data.sel->get_index(i);
		if (!iv_data.validity.RowIsValid(idx)) {
			result_mask.SetInvalid(i);
			continue;
		}

		std::string json_str = intervals[idx].GetString();
		auto parsed = cql::parse_interval_array(json_str);

		if (parsed.empty()) {
			result_data[i] = StringVector::AddString(result, "[]");
			continue;
		}

		// Sort by low bound
		std::sort(parsed.begin(), parsed.end(), [](const cql::Interval &a, const cql::Interval &b) {
			if (!a.low && !b.low) {
				return false;
			}
			if (!a.low) {
				return true;
			}
			if (!b.low) {
				return false;
			}
			return a.low->compare(*b.low) < 0;
		});

		// Merge overlapping/adjacent intervals
		std::vector<cql::Interval> merged;
		merged.push_back(parsed[0]);

		for (size_t j = 1; j < parsed.size(); j++) {
			auto &current = merged.back();
			auto &next = parsed[j];

			bool can_merge = current.overlaps(next) || current.meets(next) || next.meets(current);

			if (can_merge) {
				// Extend current interval
				if (!next.high) {
					current.high = cql::NullOpt<cql::BoundValue>();
				} else if (!current.high || next.high->compare(*current.high) > 0) {
					current.high = next.high;
					current.high_closed = next.high_closed;
				} else if (current.high && next.high->compare(*current.high) == 0) {
					current.high_closed = current.high_closed || next.high_closed;
				}
			} else {
				merged.push_back(next);
			}
		}

		// Serialize to JSON array
		std::string output = "[";
		for (size_t j = 0; j < merged.size(); j++) {
			if (j > 0) {
				output += ",";
			}
			output += merged[j].to_json();
		}
		output += "]";
		result_data[i] = StringVector::AddString(result, output);
	}
}

// =====================================================================
// Ratio UDFs (5)
// =====================================================================

// Helper macro for ratio functions returning DOUBLE
#define DEFINE_RATIO_DOUBLE_UDF(FuncName, cql_fn)                                                                      \
	static void FuncName(DataChunk &args, ExpressionState &state, Vector &result) {                                    \
		idx_t count = args.size();                                                                                     \
		UnifiedVectorFormat r_data;                                                                                    \
		args.data[0].ToUnifiedFormat(count, r_data);                                                                   \
		auto r_vals = UnifiedVectorFormat::GetData<string_t>(r_data);                                                  \
		result.SetVectorType(VectorType::FLAT_VECTOR);                                                                 \
		auto result_data = FlatVector::GetData<double>(result);                                                        \
		auto &result_mask = FlatVector::Validity(result);                                                              \
		for (idx_t i = 0; i < count; i++) {                                                                            \
			auto idx = r_data.sel->get_index(i);                                                                       \
			if (!r_data.validity.RowIsValid(idx)) {                                                                    \
				result_mask.SetInvalid(i);                                                                             \
				continue;                                                                                              \
			}                                                                                                          \
			auto val = cql_fn(r_vals[idx].GetString());                                                                \
			if (val.has_value()) {                                                                                     \
				result_data[i] = val.value();                                                                          \
			} else {                                                                                                   \
				result_mask.SetInvalid(i);                                                                             \
			}                                                                                                          \
		}                                                                                                              \
	}

// Helper macro for ratio functions returning VARCHAR
#define DEFINE_RATIO_STR_UDF(FuncName, cql_fn)                                                                         \
	static void FuncName(DataChunk &args, ExpressionState &state, Vector &result) {                                    \
		idx_t count = args.size();                                                                                     \
		UnifiedVectorFormat r_data;                                                                                    \
		args.data[0].ToUnifiedFormat(count, r_data);                                                                   \
		auto r_vals = UnifiedVectorFormat::GetData<string_t>(r_data);                                                  \
		result.SetVectorType(VectorType::FLAT_VECTOR);                                                                 \
		auto result_data = FlatVector::GetData<string_t>(result);                                                      \
		auto &result_mask = FlatVector::Validity(result);                                                              \
		for (idx_t i = 0; i < count; i++) {                                                                            \
			auto idx = r_data.sel->get_index(i);                                                                       \
			if (!r_data.validity.RowIsValid(idx)) {                                                                    \
				result_mask.SetInvalid(i);                                                                             \
				continue;                                                                                              \
			}                                                                                                          \
			auto val = cql_fn(r_vals[idx].GetString());                                                                \
			if (val.has_value()) {                                                                                     \
				result_data[i] = StringVector::AddString(result, val.value());                                         \
			} else {                                                                                                   \
				result_mask.SetInvalid(i);                                                                             \
			}                                                                                                          \
		}                                                                                                              \
	}

DEFINE_RATIO_DOUBLE_UDF(RatioNumeratorValueFunc, cql::ratio_numerator_value)
DEFINE_RATIO_DOUBLE_UDF(RatioDenominatorValueFunc, cql::ratio_denominator_value)
DEFINE_RATIO_DOUBLE_UDF(RatioValueFunc, cql::ratio_value)
DEFINE_RATIO_STR_UDF(RatioNumeratorUnitFunc, cql::ratio_numerator_unit)
DEFINE_RATIO_STR_UDF(RatioDenominatorUnitFunc, cql::ratio_denominator_unit)
DEFINE_RATIO_STR_UDF(RatioToStringFunc, cql::ratio_to_string)

// =====================================================================
// Quantity UDFs (7)
// =====================================================================

// parseQuantity(VARCHAR) → VARCHAR
static void ParseQuantityFunc(DataChunk &args, ExpressionState &state, Vector &result) {
	using namespace duckdb_yyjson; // NOLINT
	idx_t count = args.size();
	UnifiedVectorFormat q_data;
	args.data[0].ToUnifiedFormat(count, q_data);
	auto q_vals = UnifiedVectorFormat::GetData<string_t>(q_data);

	result.SetVectorType(VectorType::FLAT_VECTOR);
	auto result_data = FlatVector::GetData<string_t>(result);
	auto &result_mask = FlatVector::Validity(result);

	for (idx_t i = 0; i < count; i++) {
		auto idx = q_data.sel->get_index(i);
		if (!q_data.validity.RowIsValid(idx)) {
			result_mask.SetInvalid(i);
			continue;
		}
		std::string q_str = q_vals[idx].GetString();
		if (q_str.empty()) {
			result_mask.SetInvalid(i);
			continue;
		}
		// Lenient parse: accept even if "value" is missing (match Python behavior)
		yyjson_doc *doc = yyjson_read(q_str.c_str(), q_str.size(), 0);
		if (!doc) {
			result_mask.SetInvalid(i);
			continue;
		}
		yyjson_val *root = yyjson_doc_get_root(doc);
		if (!root || !yyjson_is_obj(root)) {
			yyjson_doc_free(doc);
			result_mask.SetInvalid(i);
			continue;
		}
		// Build normalized JSON output
		yyjson_mut_doc *out_doc = yyjson_mut_doc_new(NULL);
		if (!out_doc) {
			result_mask.SetInvalid(i);
			yyjson_doc_free(doc);
			continue;
		}
		yyjson_mut_val *out_root = yyjson_mut_obj(out_doc);
		if (!out_root) {
			yyjson_mut_doc_free(out_doc);
			result_mask.SetInvalid(i);
			yyjson_doc_free(doc);
			continue;
		}
		yyjson_mut_doc_set_root(out_doc, out_root);

		yyjson_val *val = yyjson_obj_get(root, "value");
		if (val && yyjson_is_num(val)) {
			yyjson_mut_obj_add_real(out_doc, out_root, "value", yyjson_get_num(val));
		} else {
			yyjson_mut_obj_add_null(out_doc, out_root, "value");
		}

		// code: try "code" then "unit"
		yyjson_val *code_val = yyjson_obj_get(root, "code");
		yyjson_val *unit_val = yyjson_obj_get(root, "unit");
		if (code_val && yyjson_is_str(code_val)) {
			yyjson_mut_obj_add_strcpy(out_doc, out_root, "code", yyjson_get_str(code_val));
		} else if (unit_val && yyjson_is_str(unit_val)) {
			yyjson_mut_obj_add_strcpy(out_doc, out_root, "code", yyjson_get_str(unit_val));
		}

		// system
		yyjson_val *sys_val = yyjson_obj_get(root, "system");
		if (sys_val && yyjson_is_str(sys_val)) {
			yyjson_mut_obj_add_strcpy(out_doc, out_root, "system", yyjson_get_str(sys_val));
		} else {
			yyjson_mut_obj_add_str(out_doc, out_root, "system", "http://unitsofmeasure.org");
		}

		// Preserve "unit" field in output (Python compat: CQL SQL checks fhirpath_text(parse_quantity(...), 'unit'))
		if (unit_val && yyjson_is_str(unit_val)) {
			yyjson_mut_obj_add_strcpy(out_doc, out_root, "unit", yyjson_get_str(unit_val));
		} else if (code_val && yyjson_is_str(code_val)) {
			yyjson_mut_obj_add_strcpy(out_doc, out_root, "unit", yyjson_get_str(code_val));
		}

		char *json_out = yyjson_mut_write(out_doc, 0, NULL);
		if (json_out) {
			result_data[i] = StringVector::AddString(result, json_out);
			free(json_out);
		} else {
			result_mask.SetInvalid(i);
		}
		yyjson_mut_doc_free(out_doc);
		yyjson_doc_free(doc);
	}
}

// quantityValue(VARCHAR) → DOUBLE
static void QuantityValueFunc(DataChunk &args, ExpressionState &state, Vector &result) {
	idx_t count = args.size();
	UnifiedVectorFormat q_data;
	args.data[0].ToUnifiedFormat(count, q_data);
	auto q_vals = UnifiedVectorFormat::GetData<string_t>(q_data);

	result.SetVectorType(VectorType::FLAT_VECTOR);
	auto result_data = FlatVector::GetData<double>(result);
	auto &result_mask = FlatVector::Validity(result);

	for (idx_t i = 0; i < count; i++) {
		auto idx = q_data.sel->get_index(i);
		if (!q_data.validity.RowIsValid(idx)) {
			result_mask.SetInvalid(i);
			continue;
		}
		auto val = cql::quantity_value_fn(q_vals[idx].GetString());
		if (val.has_value()) {
			result_data[i] = val.value();
		} else {
			result_mask.SetInvalid(i);
		}
	}
}

// quantityUnit(VARCHAR) → VARCHAR
static void QuantityUnitFunc(DataChunk &args, ExpressionState &state, Vector &result) {
	idx_t count = args.size();
	UnifiedVectorFormat q_data;
	args.data[0].ToUnifiedFormat(count, q_data);
	auto q_vals = UnifiedVectorFormat::GetData<string_t>(q_data);

	result.SetVectorType(VectorType::FLAT_VECTOR);
	auto result_data = FlatVector::GetData<string_t>(result);
	auto &result_mask = FlatVector::Validity(result);

	for (idx_t i = 0; i < count; i++) {
		auto idx = q_data.sel->get_index(i);
		if (!q_data.validity.RowIsValid(idx)) {
			result_mask.SetInvalid(i);
			continue;
		}
		auto val = cql::quantity_unit_fn(q_vals[idx].GetString());
		if (val.has_value()) {
			result_data[i] = StringVector::AddString(result, val.value());
		} else {
			result_mask.SetInvalid(i);
		}
	}
}

// quantityCompare(VARCHAR, VARCHAR, VARCHAR) → BOOLEAN
static void QuantityCompareFunc(DataChunk &args, ExpressionState &state, Vector &result) {
	idx_t count = args.size();
	UnifiedVectorFormat q1_data, q2_data, op_data;
	args.data[0].ToUnifiedFormat(count, q1_data);
	args.data[1].ToUnifiedFormat(count, q2_data);
	args.data[2].ToUnifiedFormat(count, op_data);
	auto q1_vals = UnifiedVectorFormat::GetData<string_t>(q1_data);
	auto q2_vals = UnifiedVectorFormat::GetData<string_t>(q2_data);
	auto op_vals = UnifiedVectorFormat::GetData<string_t>(op_data);

	result.SetVectorType(VectorType::FLAT_VECTOR);
	auto result_data = FlatVector::GetData<bool>(result);
	auto &result_mask = FlatVector::Validity(result);

	for (idx_t i = 0; i < count; i++) {
		auto i1 = q1_data.sel->get_index(i);
		auto i2 = q2_data.sel->get_index(i);
		auto i3 = op_data.sel->get_index(i);
		if (!q1_data.validity.RowIsValid(i1) || !q2_data.validity.RowIsValid(i2) ||
		    !op_data.validity.RowIsValid(i3)) {
			result_mask.SetInvalid(i);
			continue;
		}
		auto val = cql::quantity_compare(q1_vals[i1].GetString(), q2_vals[i2].GetString(), op_vals[i3].GetString());
		if (val.has_value()) {
			result_data[i] = val.value();
		} else {
			result_mask.SetInvalid(i);
		}
	}
}

// quantityAdd(VARCHAR, VARCHAR) → VARCHAR
static void QuantityAddFunc(DataChunk &args, ExpressionState &state, Vector &result) {
	idx_t count = args.size();
	UnifiedVectorFormat q1_data, q2_data;
	args.data[0].ToUnifiedFormat(count, q1_data);
	args.data[1].ToUnifiedFormat(count, q2_data);
	auto q1_vals = UnifiedVectorFormat::GetData<string_t>(q1_data);
	auto q2_vals = UnifiedVectorFormat::GetData<string_t>(q2_data);

	result.SetVectorType(VectorType::FLAT_VECTOR);
	auto result_data = FlatVector::GetData<string_t>(result);
	auto &result_mask = FlatVector::Validity(result);

	for (idx_t i = 0; i < count; i++) {
		auto i1 = q1_data.sel->get_index(i);
		auto i2 = q2_data.sel->get_index(i);
		if (!q1_data.validity.RowIsValid(i1) || !q2_data.validity.RowIsValid(i2)) {
			result_mask.SetInvalid(i);
			continue;
		}
		auto val = cql::quantity_add(q1_vals[i1].GetString(), q2_vals[i2].GetString());
		if (val.has_value()) {
			result_data[i] = StringVector::AddString(result, val.value());
		} else {
			result_mask.SetInvalid(i);
		}
	}
}

// quantitySubtract(VARCHAR, VARCHAR) → VARCHAR
static void QuantitySubtractFunc(DataChunk &args, ExpressionState &state, Vector &result) {
	idx_t count = args.size();
	UnifiedVectorFormat q1_data, q2_data;
	args.data[0].ToUnifiedFormat(count, q1_data);
	args.data[1].ToUnifiedFormat(count, q2_data);
	auto q1_vals = UnifiedVectorFormat::GetData<string_t>(q1_data);
	auto q2_vals = UnifiedVectorFormat::GetData<string_t>(q2_data);

	result.SetVectorType(VectorType::FLAT_VECTOR);
	auto result_data = FlatVector::GetData<string_t>(result);
	auto &result_mask = FlatVector::Validity(result);

	for (idx_t i = 0; i < count; i++) {
		auto i1 = q1_data.sel->get_index(i);
		auto i2 = q2_data.sel->get_index(i);
		if (!q1_data.validity.RowIsValid(i1) || !q2_data.validity.RowIsValid(i2)) {
			result_mask.SetInvalid(i);
			continue;
		}
		auto val = cql::quantity_subtract(q1_vals[i1].GetString(), q2_vals[i2].GetString());
		if (val.has_value()) {
			result_data[i] = StringVector::AddString(result, val.value());
		} else {
			result_mask.SetInvalid(i);
		}
	}
}

// quantityConvert(VARCHAR, VARCHAR) → VARCHAR
static void QuantityConvertFunc(DataChunk &args, ExpressionState &state, Vector &result) {
	idx_t count = args.size();
	UnifiedVectorFormat q_data, unit_data;
	args.data[0].ToUnifiedFormat(count, q_data);
	args.data[1].ToUnifiedFormat(count, unit_data);
	auto q_vals = UnifiedVectorFormat::GetData<string_t>(q_data);
	auto unit_vals = UnifiedVectorFormat::GetData<string_t>(unit_data);

	result.SetVectorType(VectorType::FLAT_VECTOR);
	auto result_data = FlatVector::GetData<string_t>(result);
	auto &result_mask = FlatVector::Validity(result);

	for (idx_t i = 0; i < count; i++) {
		auto i1 = q_data.sel->get_index(i);
		auto i2 = unit_data.sel->get_index(i);
		if (!q_data.validity.RowIsValid(i1) || !unit_data.validity.RowIsValid(i2)) {
			result_mask.SetInvalid(i);
			continue;
		}
		auto val = cql::quantity_convert(q_vals[i1].GetString(), unit_vals[i2].GetString());
		if (val.has_value()) {
			result_data[i] = StringVector::AddString(result, val.value());
		} else {
			result_mask.SetInvalid(i);
		}
	}
}

// =====================================================================
// List UDFs (3)
// =====================================================================

static std::string ValueToPublicVarchar(const Value &value) {
	if (value.IsNull()) {
		return "";
	}
	switch (value.type().id()) {
	case LogicalTypeId::BOOLEAN:
		return value.GetValue<bool>() ? "true" : "false";
	case LogicalTypeId::VARCHAR:
		return value.GetValue<std::string>();
	default:
		return value.ToString();
	}
}

// SingletonFrom(VARCHAR[]) → VARCHAR
static void SingletonFromFunc(DataChunk &args, ExpressionState &state, Vector &result) {
	idx_t count = args.size();
	auto &list_vec = args.data[0];
	UnifiedVectorFormat list_data;
	list_vec.ToUnifiedFormat(count, list_data);

	result.SetVectorType(VectorType::FLAT_VECTOR);
	auto result_data = FlatVector::GetData<string_t>(result);
	auto &result_mask = FlatVector::Validity(result);

	auto list_entries = UnifiedVectorFormat::GetData<list_entry_t>(list_data);
	auto &child_vec = ListVector::GetEntry(list_vec);
	UnifiedVectorFormat child_data;
	child_vec.ToUnifiedFormat(ListVector::GetListSize(list_vec), child_data);
	auto child_vals = UnifiedVectorFormat::GetData<string_t>(child_data);

	for (idx_t i = 0; i < count; i++) {
		auto idx = list_data.sel->get_index(i);
		if (!list_data.validity.RowIsValid(idx)) {
			result_mask.SetInvalid(i);
			continue;
		}

		auto &entry = list_entries[idx];
		if (entry.length == 0) {
			result_mask.SetInvalid(i);
			continue;
		}
		if (entry.length != 1) {
			throw InvalidInputException("SingletonFrom: Expected a list with at most one element");
		}

		auto child_idx = child_data.sel->get_index(entry.offset);
		if (!child_data.validity.RowIsValid(child_idx)) {
			result_mask.SetInvalid(i);
			continue;
		}
		result_data[i] = StringVector::AddString(result, child_vals[child_idx]);
	}
}

// SingletonFrom(LIST<ANY>) → VARCHAR
static void SingletonFromAnyListFunc(DataChunk &args, ExpressionState &state, Vector &result) {
	idx_t count = args.size();

	result.SetVectorType(VectorType::FLAT_VECTOR);
	auto result_data = FlatVector::GetData<string_t>(result);
	auto &result_mask = FlatVector::Validity(result);

	for (idx_t i = 0; i < count; i++) {
		auto list_val = args.data[0].GetValue(i);
		if (list_val.IsNull()) {
			result_mask.SetInvalid(i);
			continue;
		}

		auto &children = ListValue::GetChildren(list_val);
		if (children.empty()) {
			result_mask.SetInvalid(i);
			continue;
		}
		if (children.size() != 1) {
			throw InvalidInputException("SingletonFrom: Expected a list with at most one element");
		}
		if (children[0].IsNull()) {
			result_mask.SetInvalid(i);
			continue;
		}
		result_data[i] = StringVector::AddString(result, ValueToPublicVarchar(children[0]));
	}
}

// ElementAt(VARCHAR[], BIGINT) → VARCHAR
static void ElementAtFunc(DataChunk &args, ExpressionState &state, Vector &result) {
	idx_t count = args.size();
	auto &list_vec = args.data[0];
	UnifiedVectorFormat list_data, idx_data;
	list_vec.ToUnifiedFormat(count, list_data);
	args.data[1].ToUnifiedFormat(count, idx_data);

	result.SetVectorType(VectorType::FLAT_VECTOR);
	auto result_data = FlatVector::GetData<string_t>(result);
	auto &result_mask = FlatVector::Validity(result);

	auto list_entries = UnifiedVectorFormat::GetData<list_entry_t>(list_data);
	auto idx_vals = UnifiedVectorFormat::GetData<int64_t>(idx_data);
	auto &child_vec = ListVector::GetEntry(list_vec);
	UnifiedVectorFormat child_data;
	child_vec.ToUnifiedFormat(ListVector::GetListSize(list_vec), child_data);
	auto child_vals = UnifiedVectorFormat::GetData<string_t>(child_data);

	for (idx_t i = 0; i < count; i++) {
		auto li = list_data.sel->get_index(i);
		auto ii = idx_data.sel->get_index(i);
		if (!list_data.validity.RowIsValid(li) || !idx_data.validity.RowIsValid(ii)) {
			result_mask.SetInvalid(i);
			continue;
		}

		auto &entry = list_entries[li];
		int64_t index = idx_vals[ii];

		// CQL uses 0-based indexing; handle negative indices
		if (index < 0) {
			index = static_cast<int64_t>(entry.length) + index;
		}

		if (index < 0 || static_cast<uint64_t>(index) >= entry.length) {
			result_mask.SetInvalid(i);
			continue;
		}

		auto child_idx = child_data.sel->get_index(entry.offset + static_cast<idx_t>(index));
		if (!child_data.validity.RowIsValid(child_idx)) {
			result_mask.SetInvalid(i);
			continue;
		}
		result_data[i] = StringVector::AddString(result, child_vals[child_idx]);
	}
}

// ElementAt(LIST<ANY>, BIGINT) → VARCHAR
static void ElementAtAnyListFunc(DataChunk &args, ExpressionState &state, Vector &result) {
	idx_t count = args.size();

	result.SetVectorType(VectorType::FLAT_VECTOR);
	auto result_data = FlatVector::GetData<string_t>(result);
	auto &result_mask = FlatVector::Validity(result);

	for (idx_t i = 0; i < count; i++) {
		auto list_val = args.data[0].GetValue(i);
		auto index_val = args.data[1].GetValue(i);
		if (list_val.IsNull() || index_val.IsNull()) {
			result_mask.SetInvalid(i);
			continue;
		}

		auto &children = ListValue::GetChildren(list_val);
		int64_t index = index_val.GetValue<int64_t>();
		if (index < 0) {
			index = static_cast<int64_t>(children.size()) + index;
		}
		if (index < 0 || static_cast<uint64_t>(index) >= children.size()) {
			result_mask.SetInvalid(i);
			continue;
		}

		const auto &child = children[static_cast<idx_t>(index)];
		if (child.IsNull()) {
			result_mask.SetInvalid(i);
			continue;
		}
		result_data[i] = StringVector::AddString(result, ValueToPublicVarchar(child));
	}
}

// jsonConcat(VARCHAR, VARCHAR) → VARCHAR[]
static void JsonConcatFunc(DataChunk &args, ExpressionState &state, Vector &result) {
	idx_t count = args.size();
	UnifiedVectorFormat a_data, b_data;
	args.data[0].ToUnifiedFormat(count, a_data);
	args.data[1].ToUnifiedFormat(count, b_data);
	auto a_vals = UnifiedVectorFormat::GetData<string_t>(a_data);
	auto b_vals = UnifiedVectorFormat::GetData<string_t>(b_data);

	auto &result_mask = FlatVector::Validity(result);

	// Collect offsets and push values first, then write list_entries
	// to avoid stale pointer after ListVector::PushBack reallocation
	std::vector<idx_t> row_offsets(count);
	std::vector<idx_t> row_counts(count);
	std::vector<bool> row_null(count, false);
	idx_t total_size = 0;

	for (idx_t i = 0; i < count; i++) {
		auto ai = a_data.sel->get_index(i);
		auto bi = b_data.sel->get_index(i);
		bool a_valid = a_data.validity.RowIsValid(ai);
		bool b_valid = b_data.validity.RowIsValid(bi);

		if (!a_valid && !b_valid) {
			row_offsets[i] = total_size;
			row_counts[i] = 0;
			row_null[i] = true;
			continue;
		}

		row_offsets[i] = total_size;
		idx_t entry_count = 0;
		if (a_valid) {
			ListVector::PushBack(result, Value(a_vals[ai].GetString()));
			entry_count++;
		}
		if (b_valid) {
			ListVector::PushBack(result, Value(b_vals[bi].GetString()));
			entry_count++;
		}

		row_counts[i] = entry_count;
		total_size += entry_count;
	}

	auto list_entries = ListVector::GetData(result);
	for (idx_t i = 0; i < count; i++) {
		list_entries[i] = {row_offsets[i], row_counts[i]};
		if (row_null[i]) {
			result_mask.SetInvalid(i);
		}
	}
	ListVector::SetListSize(result, total_size);
}

static idx_t AppendAnyValueAsStringList(Vector &result, const Value &value) {
	if (value.IsNull()) {
		return 0;
	}
	if (value.type().id() == LogicalTypeId::LIST) {
		idx_t appended = 0;
		auto &children = ListValue::GetChildren(value);
		for (const auto &child : children) {
			if (child.IsNull()) {
				ListVector::PushBack(result, Value(LogicalType::VARCHAR));
			} else {
				ListVector::PushBack(result, Value(ValueToPublicVarchar(child)));
			}
			appended++;
		}
		return appended;
	}
	ListVector::PushBack(result, Value(ValueToPublicVarchar(value)));
	return 1;
}

// jsonConcat(ANY, ANY) → VARCHAR[]
static void JsonConcatAnyFunc(DataChunk &args, ExpressionState &state, Vector &result) {
	idx_t count = args.size();

	std::vector<idx_t> row_offsets(count);
	std::vector<idx_t> row_counts(count);
	std::vector<bool> row_null(count, false);
	idx_t total_size = 0;

	for (idx_t i = 0; i < count; i++) {
		auto left = args.data[0].GetValue(i);
		auto right = args.data[1].GetValue(i);

		row_offsets[i] = total_size;
		if (left.IsNull() && right.IsNull()) {
			row_counts[i] = 0;
			row_null[i] = true;
			continue;
		}
		idx_t entry_count = 0;
		entry_count += AppendAnyValueAsStringList(result, left);
		entry_count += AppendAnyValueAsStringList(result, right);
		row_counts[i] = entry_count;
		total_size += entry_count;
	}

	auto &result_mask = FlatVector::Validity(result);
	auto list_entries = ListVector::GetData(result);
	for (idx_t i = 0; i < count; i++) {
		list_entries[i] = {row_offsets[i], row_counts[i]};
		if (row_null[i]) {
			result_mask.SetInvalid(i);
		}
	}
	ListVector::SetListSize(result, total_size);
}

static idx_t AppendStringList(Vector &result, UnifiedVectorFormat &list_data, UnifiedVectorFormat &child_data,
                              const list_entry_t *list_entries, const string_t *child_vals, idx_t list_index) {
	auto &entry = list_entries[list_index];
	idx_t appended = 0;
	for (idx_t j = 0; j < entry.length; j++) {
		auto child_idx = child_data.sel->get_index(entry.offset + j);
		if (child_data.validity.RowIsValid(child_idx)) {
			ListVector::PushBack(result, Value(child_vals[child_idx].GetString()));
			appended++;
		}
	}
	return appended;
}

// jsonConcat(VARCHAR[], VARCHAR[]) → VARCHAR[]
static void JsonConcatListListFunc(DataChunk &args, ExpressionState &state, Vector &result) {
	idx_t count = args.size();
	auto &a_vec = args.data[0];
	auto &b_vec = args.data[1];
	UnifiedVectorFormat a_data, b_data;
	a_vec.ToUnifiedFormat(count, a_data);
	b_vec.ToUnifiedFormat(count, b_data);
	auto a_entries = UnifiedVectorFormat::GetData<list_entry_t>(a_data);
	auto b_entries = UnifiedVectorFormat::GetData<list_entry_t>(b_data);

	auto &a_child_vec = ListVector::GetEntry(a_vec);
	auto &b_child_vec = ListVector::GetEntry(b_vec);
	UnifiedVectorFormat a_child_data, b_child_data;
	a_child_vec.ToUnifiedFormat(ListVector::GetListSize(a_vec), a_child_data);
	b_child_vec.ToUnifiedFormat(ListVector::GetListSize(b_vec), b_child_data);
	auto a_child_vals = UnifiedVectorFormat::GetData<string_t>(a_child_data);
	auto b_child_vals = UnifiedVectorFormat::GetData<string_t>(b_child_data);

	auto &result_mask = FlatVector::Validity(result);
	std::vector<idx_t> row_offsets(count);
	std::vector<idx_t> row_counts(count);
	std::vector<bool> row_null(count, false);
	idx_t total_size = 0;

	for (idx_t i = 0; i < count; i++) {
		auto ai = a_data.sel->get_index(i);
		auto bi = b_data.sel->get_index(i);
		bool a_valid = a_data.validity.RowIsValid(ai);
		bool b_valid = b_data.validity.RowIsValid(bi);
		row_offsets[i] = total_size;
		if (!a_valid && !b_valid) {
			row_counts[i] = 0;
			row_null[i] = true;
			continue;
		}
		idx_t entry_count = 0;
		if (a_valid) {
			entry_count += AppendStringList(result, a_data, a_child_data, a_entries, a_child_vals, ai);
		}
		if (b_valid) {
			entry_count += AppendStringList(result, b_data, b_child_data, b_entries, b_child_vals, bi);
		}
		row_counts[i] = entry_count;
		total_size += entry_count;
	}

	auto list_entries = ListVector::GetData(result);
	for (idx_t i = 0; i < count; i++) {
		list_entries[i] = {row_offsets[i], row_counts[i]};
		if (row_null[i]) {
			result_mask.SetInvalid(i);
		}
	}
	ListVector::SetListSize(result, total_size);
}

// jsonConcat(VARCHAR[], VARCHAR) → VARCHAR[]
static void JsonConcatListScalarFunc(DataChunk &args, ExpressionState &state, Vector &result) {
	idx_t count = args.size();
	auto &list_vec = args.data[0];
	UnifiedVectorFormat list_data, scalar_data;
	list_vec.ToUnifiedFormat(count, list_data);
	args.data[1].ToUnifiedFormat(count, scalar_data);
	auto list_entries = UnifiedVectorFormat::GetData<list_entry_t>(list_data);
	auto scalar_vals = UnifiedVectorFormat::GetData<string_t>(scalar_data);
	auto &child_vec = ListVector::GetEntry(list_vec);
	UnifiedVectorFormat child_data;
	child_vec.ToUnifiedFormat(ListVector::GetListSize(list_vec), child_data);
	auto child_vals = UnifiedVectorFormat::GetData<string_t>(child_data);

	auto &result_mask = FlatVector::Validity(result);
	std::vector<idx_t> row_offsets(count);
	std::vector<idx_t> row_counts(count);
	std::vector<bool> row_null(count, false);
	idx_t total_size = 0;

	for (idx_t i = 0; i < count; i++) {
		auto li = list_data.sel->get_index(i);
		auto si = scalar_data.sel->get_index(i);
		bool list_valid = list_data.validity.RowIsValid(li);
		bool scalar_valid = scalar_data.validity.RowIsValid(si);
		row_offsets[i] = total_size;
		if (!list_valid && !scalar_valid) {
			row_counts[i] = 0;
			row_null[i] = true;
			continue;
		}
		idx_t entry_count = 0;
		if (list_valid) {
			entry_count += AppendStringList(result, list_data, child_data, list_entries, child_vals, li);
		}
		if (scalar_valid) {
			ListVector::PushBack(result, Value(scalar_vals[si].GetString()));
			entry_count++;
		}
		row_counts[i] = entry_count;
		total_size += entry_count;
	}

	auto result_entries = ListVector::GetData(result);
	for (idx_t i = 0; i < count; i++) {
		result_entries[i] = {row_offsets[i], row_counts[i]};
		if (row_null[i]) {
			result_mask.SetInvalid(i);
		}
	}
	ListVector::SetListSize(result, total_size);
}

// jsonConcat(VARCHAR, VARCHAR[]) → VARCHAR[]
static void JsonConcatScalarListFunc(DataChunk &args, ExpressionState &state, Vector &result) {
	idx_t count = args.size();
	UnifiedVectorFormat scalar_data, list_data;
	args.data[0].ToUnifiedFormat(count, scalar_data);
	auto &list_vec = args.data[1];
	list_vec.ToUnifiedFormat(count, list_data);
	auto scalar_vals = UnifiedVectorFormat::GetData<string_t>(scalar_data);
	auto list_entries = UnifiedVectorFormat::GetData<list_entry_t>(list_data);
	auto &child_vec = ListVector::GetEntry(list_vec);
	UnifiedVectorFormat child_data;
	child_vec.ToUnifiedFormat(ListVector::GetListSize(list_vec), child_data);
	auto child_vals = UnifiedVectorFormat::GetData<string_t>(child_data);

	auto &result_mask = FlatVector::Validity(result);
	std::vector<idx_t> row_offsets(count);
	std::vector<idx_t> row_counts(count);
	std::vector<bool> row_null(count, false);
	idx_t total_size = 0;

	for (idx_t i = 0; i < count; i++) {
		auto si = scalar_data.sel->get_index(i);
		auto li = list_data.sel->get_index(i);
		bool scalar_valid = scalar_data.validity.RowIsValid(si);
		bool list_valid = list_data.validity.RowIsValid(li);
		row_offsets[i] = total_size;
		if (!scalar_valid && !list_valid) {
			row_counts[i] = 0;
			row_null[i] = true;
			continue;
		}
		idx_t entry_count = 0;
		if (scalar_valid) {
			ListVector::PushBack(result, Value(scalar_vals[si].GetString()));
			entry_count++;
		}
		if (list_valid) {
			entry_count += AppendStringList(result, list_data, child_data, list_entries, child_vals, li);
		}
		row_counts[i] = entry_count;
		total_size += entry_count;
	}

	auto result_entries = ListVector::GetData(result);
	for (idx_t i = 0; i < count; i++) {
		result_entries[i] = {row_offsets[i], row_counts[i]};
		if (row_null[i]) {
			result_mask.SetInvalid(i);
		}
	}
	ListVector::SetListSize(result, total_size);
}

// =====================================================================
// Registration helper
// =====================================================================
static void RegisterSpecialScalar(ExtensionLoader &loader, const std::string &name,
                                  const vector<LogicalType> &args, const LogicalType &ret,
                                  scalar_function_t func) {
	auto sf = ScalarFunction(name, args, ret, func);
	sf.null_handling = FunctionNullHandling::SPECIAL_HANDLING;
	loader.RegisterFunction(sf);
}

// =====================================================================
// Boundary UDFs — HighBoundary, LowBoundary, CQLPrecision,
// cqlTimezoneOffset, predecessorOf, successorOf
// =====================================================================

DEFINE_ONE_STR_STR_UDF(HighBoundaryFunc1, {
	auto prec = cql::default_boundary_precision(a_str);
	if (!prec) { result_mask.SetInvalid(i); continue; }
	auto res = cql::high_boundary(a_str, static_cast<int>(*prec));
	if (!res) { result_mask.SetInvalid(i); continue; }
	result_data[i] = StringVector::AddString(result, *res);
})

static void HighBoundaryFunc2(DataChunk &args, ExpressionState &state, Vector &result) {
	idx_t count = args.size();
	UnifiedVectorFormat a_data, p_data;
	args.data[0].ToUnifiedFormat(count, a_data);
	args.data[1].ToUnifiedFormat(count, p_data);

	auto a_vals = UnifiedVectorFormat::GetData<string_t>(a_data);
	auto p_vals = UnifiedVectorFormat::GetData<int64_t>(p_data);

	result.SetVectorType(VectorType::FLAT_VECTOR);
	auto result_data = FlatVector::GetData<string_t>(result);
	auto &result_mask = FlatVector::Validity(result);

	for (idx_t i = 0; i < count; i++) {
		auto a_idx = a_data.sel->get_index(i);
		auto p_idx = p_data.sel->get_index(i);

		if (!a_data.validity.RowIsValid(a_idx) || !p_data.validity.RowIsValid(p_idx)) {
			result_mask.SetInvalid(i);
			continue;
		}

		std::string val = a_vals[a_idx].GetString();
		int prec = static_cast<int>(p_vals[p_idx]);
		auto res = cql::high_boundary(val, prec);
		if (!res) { result_mask.SetInvalid(i); continue; }
		result_data[i] = StringVector::AddString(result, *res);
	}
}

DEFINE_ONE_STR_STR_UDF(LowBoundaryFunc1, {
	auto prec = cql::default_boundary_precision(a_str);
	if (!prec) { result_mask.SetInvalid(i); continue; }
	auto res = cql::low_boundary(a_str, static_cast<int>(*prec));
	if (!res) { result_mask.SetInvalid(i); continue; }
	result_data[i] = StringVector::AddString(result, *res);
})

static void LowBoundaryFunc2(DataChunk &args, ExpressionState &state, Vector &result) {
	idx_t count = args.size();
	UnifiedVectorFormat a_data, p_data;
	args.data[0].ToUnifiedFormat(count, a_data);
	args.data[1].ToUnifiedFormat(count, p_data);

	auto a_vals = UnifiedVectorFormat::GetData<string_t>(a_data);
	auto p_vals = UnifiedVectorFormat::GetData<int64_t>(p_data);

	result.SetVectorType(VectorType::FLAT_VECTOR);
	auto result_data = FlatVector::GetData<string_t>(result);
	auto &result_mask = FlatVector::Validity(result);

	for (idx_t i = 0; i < count; i++) {
		auto a_idx = a_data.sel->get_index(i);
		auto p_idx = p_data.sel->get_index(i);

		if (!a_data.validity.RowIsValid(a_idx) || !p_data.validity.RowIsValid(p_idx)) {
			result_mask.SetInvalid(i);
			continue;
		}

		std::string val = a_vals[a_idx].GetString();
		int prec = static_cast<int>(p_vals[p_idx]);
		auto res = cql::low_boundary(val, prec);
		if (!res) { result_mask.SetInvalid(i); continue; }
		result_data[i] = StringVector::AddString(result, *res);
	}
}

static void HighBoundaryDoubleFunc(DataChunk &args, ExpressionState &state, Vector &result) {
	idx_t count = args.size();
	UnifiedVectorFormat a_data, p_data;
	args.data[0].ToUnifiedFormat(count, a_data);
	args.data[1].ToUnifiedFormat(count, p_data);
	auto a_vals = UnifiedVectorFormat::GetData<double>(a_data);
	auto p_vals = UnifiedVectorFormat::GetData<int64_t>(p_data);
	result.SetVectorType(VectorType::FLAT_VECTOR);
	auto result_data = FlatVector::GetData<double>(result);
	auto &result_mask = FlatVector::Validity(result);
	for (idx_t i = 0; i < count; i++) {
		auto ai = a_data.sel->get_index(i);
		auto pi = p_data.sel->get_index(i);
		if (!a_data.validity.RowIsValid(ai) || !p_data.validity.RowIsValid(pi)) {
			result_mask.SetInvalid(i);
			continue;
		}
		std::ostringstream oss;
		oss << std::setprecision(17) << a_vals[ai];
		auto out = cql::high_boundary(oss.str(), static_cast<int>(p_vals[pi]));
		if (!out) { result_mask.SetInvalid(i); continue; }
		result_data[i] = std::stod(*out);
	}
}

static void HighBoundaryDoubleFunc1(DataChunk &args, ExpressionState &state, Vector &result) {
	idx_t count = args.size();
	UnifiedVectorFormat a_data;
	args.data[0].ToUnifiedFormat(count, a_data);
	auto a_vals = UnifiedVectorFormat::GetData<double>(a_data);
	result.SetVectorType(VectorType::FLAT_VECTOR);
	auto result_data = FlatVector::GetData<double>(result);
	auto &result_mask = FlatVector::Validity(result);
	for (idx_t i = 0; i < count; i++) {
		auto ai = a_data.sel->get_index(i);
		if (!a_data.validity.RowIsValid(ai)) {
			result_mask.SetInvalid(i);
			continue;
		}
		std::ostringstream oss;
		oss << std::setprecision(17) << a_vals[ai];
		auto out = cql::high_boundary(oss.str(), 8);
		if (!out) { result_mask.SetInvalid(i); continue; }
		result_data[i] = std::stod(*out);
	}
}

static void LowBoundaryDoubleFunc(DataChunk &args, ExpressionState &state, Vector &result) {
	idx_t count = args.size();
	UnifiedVectorFormat a_data, p_data;
	args.data[0].ToUnifiedFormat(count, a_data);
	args.data[1].ToUnifiedFormat(count, p_data);
	auto a_vals = UnifiedVectorFormat::GetData<double>(a_data);
	auto p_vals = UnifiedVectorFormat::GetData<int64_t>(p_data);
	result.SetVectorType(VectorType::FLAT_VECTOR);
	auto result_data = FlatVector::GetData<double>(result);
	auto &result_mask = FlatVector::Validity(result);
	for (idx_t i = 0; i < count; i++) {
		auto ai = a_data.sel->get_index(i);
		auto pi = p_data.sel->get_index(i);
		if (!a_data.validity.RowIsValid(ai) || !p_data.validity.RowIsValid(pi)) {
			result_mask.SetInvalid(i);
			continue;
		}
		std::ostringstream oss;
		oss << std::setprecision(17) << a_vals[ai];
		auto out = cql::low_boundary(oss.str(), static_cast<int>(p_vals[pi]));
		if (!out) { result_mask.SetInvalid(i); continue; }
		result_data[i] = std::stod(*out);
	}
}

static void LowBoundaryDoubleFunc1(DataChunk &args, ExpressionState &state, Vector &result) {
	idx_t count = args.size();
	UnifiedVectorFormat a_data;
	args.data[0].ToUnifiedFormat(count, a_data);
	auto a_vals = UnifiedVectorFormat::GetData<double>(a_data);
	result.SetVectorType(VectorType::FLAT_VECTOR);
	auto result_data = FlatVector::GetData<double>(result);
	auto &result_mask = FlatVector::Validity(result);
	for (idx_t i = 0; i < count; i++) {
		auto ai = a_data.sel->get_index(i);
		if (!a_data.validity.RowIsValid(ai)) {
			result_mask.SetInvalid(i);
			continue;
		}
		std::ostringstream oss;
		oss << std::setprecision(17) << a_vals[ai];
		auto out = cql::low_boundary(oss.str(), 8);
		if (!out) { result_mask.SetInvalid(i); continue; }
		result_data[i] = std::stod(*out);
	}
}

DEFINE_ONE_STR_STR_UDF(PredecessorOfFunc, {
	auto res = cql::predecessor_of(a_str);
	if (!res) { result_mask.SetInvalid(i); continue; }
	result_data[i] = StringVector::AddString(result, *res);
})

DEFINE_ONE_STR_STR_UDF(SuccessorOfFunc, {
	auto res = cql::successor_of(a_str);
	if (!res) { result_mask.SetInvalid(i); continue; }
	result_data[i] = StringVector::AddString(result, *res);
})

static void PredecessorOfBigIntFunc(DataChunk &args, ExpressionState &state, Vector &result) {
	idx_t count = args.size();
	UnifiedVectorFormat a_data;
	args.data[0].ToUnifiedFormat(count, a_data);
	auto a_vals = UnifiedVectorFormat::GetData<int64_t>(a_data);
	result.SetVectorType(VectorType::FLAT_VECTOR);
	auto result_data = FlatVector::GetData<int64_t>(result);
	auto &result_mask = FlatVector::Validity(result);
	for (idx_t i = 0; i < count; i++) {
		auto ai = a_data.sel->get_index(i);
		if (!a_data.validity.RowIsValid(ai)) { result_mask.SetInvalid(i); continue; }
		if (a_vals[ai] == std::numeric_limits<int64_t>::min()) {
			result_mask.SetInvalid(i);
			continue;
		}
		result_data[i] = a_vals[ai] - 1;
	}
}

static void SuccessorOfBigIntFunc(DataChunk &args, ExpressionState &state, Vector &result) {
	idx_t count = args.size();
	UnifiedVectorFormat a_data;
	args.data[0].ToUnifiedFormat(count, a_data);
	auto a_vals = UnifiedVectorFormat::GetData<int64_t>(a_data);
	result.SetVectorType(VectorType::FLAT_VECTOR);
	auto result_data = FlatVector::GetData<int64_t>(result);
	auto &result_mask = FlatVector::Validity(result);
	for (idx_t i = 0; i < count; i++) {
		auto ai = a_data.sel->get_index(i);
		if (!a_data.validity.RowIsValid(ai)) { result_mask.SetInvalid(i); continue; }
		if (a_vals[ai] == std::numeric_limits<int64_t>::max()) {
			result_mask.SetInvalid(i);
			continue;
		}
		result_data[i] = a_vals[ai] + 1;
	}
}

static void PredecessorOfDoubleFunc(DataChunk &args, ExpressionState &state, Vector &result) {
	idx_t count = args.size();
	UnifiedVectorFormat a_data;
	args.data[0].ToUnifiedFormat(count, a_data);
	auto a_vals = UnifiedVectorFormat::GetData<double>(a_data);
	result.SetVectorType(VectorType::FLAT_VECTOR);
	auto result_data = FlatVector::GetData<double>(result);
	auto &result_mask = FlatVector::Validity(result);
	for (idx_t i = 0; i < count; i++) {
		auto ai = a_data.sel->get_index(i);
		if (!a_data.validity.RowIsValid(ai)) { result_mask.SetInvalid(i); continue; }
		result_data[i] = a_vals[ai] - 1e-8;
	}
}

static void SuccessorOfDoubleFunc(DataChunk &args, ExpressionState &state, Vector &result) {
	idx_t count = args.size();
	UnifiedVectorFormat a_data;
	args.data[0].ToUnifiedFormat(count, a_data);
	auto a_vals = UnifiedVectorFormat::GetData<double>(a_data);
	result.SetVectorType(VectorType::FLAT_VECTOR);
	auto result_data = FlatVector::GetData<double>(result);
	auto &result_mask = FlatVector::Validity(result);
	for (idx_t i = 0; i < count; i++) {
		auto ai = a_data.sel->get_index(i);
		if (!a_data.validity.RowIsValid(ai)) { result_mask.SetInvalid(i); continue; }
		result_data[i] = a_vals[ai] + 1e-8;
	}
}

static void CQLPrecisionFunc(DataChunk &args, ExpressionState &state, Vector &result) {
	idx_t count = args.size();
	UnifiedVectorFormat a_data;
	args.data[0].ToUnifiedFormat(count, a_data);
	auto a_vals = UnifiedVectorFormat::GetData<string_t>(a_data);

	result.SetVectorType(VectorType::FLAT_VECTOR);
	auto result_data = FlatVector::GetData<int64_t>(result);
	auto &result_mask = FlatVector::Validity(result);

	for (idx_t i = 0; i < count; i++) {
		auto a_idx = a_data.sel->get_index(i);
		if (!a_data.validity.RowIsValid(a_idx)) {
			result_mask.SetInvalid(i);
			continue;
		}
		std::string val = a_vals[a_idx].GetString();
		auto res = cql::cql_precision(val);
		if (!res) { result_mask.SetInvalid(i); continue; }
		result_data[i] = *res;
	}
}

static void CQLTimezoneOffsetFunc(DataChunk &args, ExpressionState &state, Vector &result) {
	idx_t count = args.size();
	UnifiedVectorFormat a_data;
	args.data[0].ToUnifiedFormat(count, a_data);
	auto a_vals = UnifiedVectorFormat::GetData<string_t>(a_data);

	result.SetVectorType(VectorType::FLAT_VECTOR);
	auto result_data = FlatVector::GetData<double>(result);
	auto &result_mask = FlatVector::Validity(result);

	for (idx_t i = 0; i < count; i++) {
		auto a_idx = a_data.sel->get_index(i);
		if (!a_data.validity.RowIsValid(a_idx)) {
			result_mask.SetInvalid(i);
			continue;
		}
		std::string val = a_vals[a_idx].GetString();
		auto res = cql::cql_timezone_offset(val);
		if (!res) { result_mask.SetInvalid(i); continue; }
		result_data[i] = *res;
	}
}

// =====================================================================
// Interval set operation UDFs
// =====================================================================
DEFINE_TWO_STR_STR_UDF(IntervalIntersectFunc, {
	auto iv1 = cql::Interval::parse(a_str);
	auto iv2 = cql::Interval::parse(b_str);
	if (!iv1 || !iv2) { result_mask.SetInvalid(i); continue; }
	auto res = cql::Interval::intersect(*iv1, *iv2);
	if (!res) { result_mask.SetInvalid(i); continue; }
	result_data[i] = StringVector::AddString(result, res->to_json());
})

DEFINE_TWO_STR_STR_UDF(IntervalUnionFunc, {
	auto iv1 = cql::Interval::parse(a_str);
	auto iv2 = cql::Interval::parse(b_str);
	if (!iv1 || !iv2) { result_mask.SetInvalid(i); continue; }
	auto res = cql::Interval::union_of(*iv1, *iv2);
	if (!res) { result_mask.SetInvalid(i); continue; }
	result_data[i] = StringVector::AddString(result, res->to_json());
})

DEFINE_TWO_STR_STR_UDF(IntervalExceptFunc, {
	auto iv1 = cql::Interval::parse(a_str);
	auto iv2 = cql::Interval::parse(b_str);
	if (!iv1 || !iv2) { result_mask.SetInvalid(i); continue; }
	auto res = cql::Interval::except_of(*iv1, *iv2);
	if (!res) { result_mask.SetInvalid(i); continue; }
	result_data[i] = StringVector::AddString(result, res->to_json());
})

DEFINE_TWO_STR_BOOL_UDF(IntervalOnOrAfterFunc, {
	auto iv1 = cql::Interval::parse(a_str);
	auto iv2 = cql::Interval::parse(b_str);
	if (!iv1 || !iv2) { result_mask.SetInvalid(i); continue; }
	auto res = cql::Interval::on_or_after(*iv1, *iv2);
	if (!res) { result_mask.SetInvalid(i); continue; }
	result_data[i] = *res;
})

DEFINE_TWO_STR_BOOL_UDF(IntervalOnOrBeforeFunc, {
	auto iv1 = cql::Interval::parse(a_str);
	auto iv2 = cql::Interval::parse(b_str);
	if (!iv1 || !iv2) { result_mask.SetInvalid(i); continue; }
	auto res = cql::Interval::on_or_before(*iv1, *iv2);
	if (!res) { result_mask.SetInvalid(i); continue; }
	result_data[i] = *res;
})

// =====================================================================
// pointFrom UDF — extract single point from unit interval
// =====================================================================
DEFINE_ONE_STR_STR_UDF(PointFromFunc, {
	auto iv = cql::Interval::parse(a_str);
	if (!iv) { result_mask.SetInvalid(i); continue; }
	auto start = iv->start_string();
	auto end = iv->end_string();
	if (start.empty() || end.empty()) { result_mask.SetInvalid(i); continue; }
	auto start_bound = cql::parse_point_value(start);
	auto end_bound = cql::parse_point_value(end);
	if (!start_bound || !end_bound) { result_mask.SetInvalid(i); continue; }
	int cmp = start_bound->compare(*end_bound);
	if (cmp != 0) { result_mask.SetInvalid(i); continue; }
	result_data[i] = StringVector::AddString(result, start);
})

// =====================================================================
// Math UDFs
// =====================================================================
static void MathRoundFunc(DataChunk &args, ExpressionState &state, Vector &result) {
	idx_t count = args.size();
	UnifiedVectorFormat a_data, b_data;
	args.data[0].ToUnifiedFormat(count, a_data);
	args.data[1].ToUnifiedFormat(count, b_data);
	auto a_vals = UnifiedVectorFormat::GetData<string_t>(a_data);
	auto b_vals = UnifiedVectorFormat::GetData<string_t>(b_data);
	result.SetVectorType(VectorType::FLAT_VECTOR);
	auto result_data = FlatVector::GetData<string_t>(result);
	auto &result_mask = FlatVector::Validity(result);

	for (idx_t i = 0; i < count; i++) {
		auto a_idx = a_data.sel->get_index(i);
		auto b_idx = b_data.sel->get_index(i);
		if (!a_data.validity.RowIsValid(a_idx)) {
			result_mask.SetInvalid(i);
			continue;
		}
		auto a_str = a_vals[a_idx].GetString();
		std::string b_str = b_data.validity.RowIsValid(b_idx) ? b_vals[b_idx].GetString() : "0";
		auto res = cql::math_round(a_str, b_str);
		if (!res) {
			result_mask.SetInvalid(i);
			continue;
		}
		result_data[i] = StringVector::AddString(result, *res);
	}
}

DEFINE_TWO_STR_STR_UDF(MathLogFunc, {
	auto res = cql::math_log(a_str, b_str);
	if (!res) { result_mask.SetInvalid(i); continue; }
	result_data[i] = StringVector::AddString(result, *res);
})

DEFINE_TWO_STR_STR_UDF(MathPowerFunc, {
	auto res = cql::math_power(a_str, b_str);
	if (!res) { result_mask.SetInvalid(i); continue; }
	result_data[i] = StringVector::AddString(result, *res);
})

DEFINE_ONE_STR_STR_UDF(MathAbsFunc, {
	auto res = cql::math_abs(a_str);
	if (!res) { result_mask.SetInvalid(i); continue; }
	result_data[i] = StringVector::AddString(result, *res);
})

DEFINE_ONE_STR_STR_UDF(MathCeilingFunc, {
	auto res = cql::math_ceiling(a_str);
	if (!res) { result_mask.SetInvalid(i); continue; }
	result_data[i] = StringVector::AddString(result, *res);
})

DEFINE_ONE_STR_STR_UDF(MathFloorFunc, {
	auto res = cql::math_floor(a_str);
	if (!res) { result_mask.SetInvalid(i); continue; }
	result_data[i] = StringVector::AddString(result, *res);
})

DEFINE_ONE_STR_STR_UDF(MathExpFunc, {
	auto res = cql::math_exp(a_str);
	if (!res) { result_mask.SetInvalid(i); continue; }
	result_data[i] = StringVector::AddString(result, *res);
})

DEFINE_ONE_STR_STR_UDF(MathLnFunc, {
	auto res = cql::math_ln(a_str);
	if (!res) { result_mask.SetInvalid(i); continue; }
	result_data[i] = StringVector::AddString(result, *res);
})

DEFINE_ONE_STR_STR_UDF(MathSqrtFunc, {
	auto res = cql::math_sqrt(a_str);
	if (!res) { result_mask.SetInvalid(i); continue; }
	result_data[i] = StringVector::AddString(result, *res);
})

DEFINE_ONE_STR_STR_UDF(MathTruncateFunc, {
	auto res = cql::math_truncate(a_str);
	if (!res) { result_mask.SetInvalid(i); continue; }
	result_data[i] = StringVector::AddString(result, *res);
})

// =====================================================================
// Phase 6: Quantity arithmetic UDFs
// =====================================================================
DEFINE_TWO_STR_STR_UDF(QuantityMultiplyFunc, {
	auto res = cql::quantity_multiply(a_str, b_str);
	if (!res) { result_mask.SetInvalid(i); continue; }
	result_data[i] = StringVector::AddString(result, *res);
})

DEFINE_TWO_STR_STR_UDF(QuantityDivideFunc, {
	auto res = cql::quantity_divide(a_str, b_str);
	if (!res) { result_mask.SetInvalid(i); continue; }
	result_data[i] = StringVector::AddString(result, *res);
})

DEFINE_ONE_STR_STR_UDF(QuantityNegateFunc, {
	auto res = cql::quantity_negate(a_str);
	if (!res) { result_mask.SetInvalid(i); continue; }
	result_data[i] = StringVector::AddString(result, *res);
})

DEFINE_ONE_STR_STR_UDF(QuantityAbsFunc, {
	auto res = cql::quantity_abs(a_str);
	if (!res) { result_mask.SetInvalid(i); continue; }
	result_data[i] = StringVector::AddString(result, *res);
})

DEFINE_TWO_STR_STR_UDF(QuantityModuloFunc, {
	auto res = cql::quantity_modulo(a_str, b_str);
	if (!res) { result_mask.SetInvalid(i); continue; }
	result_data[i] = StringVector::AddString(result, *res);
})

DEFINE_TWO_STR_STR_UDF(QuantityTruncatedDivideFunc, {
	auto res = cql::quantity_truncated_divide(a_str, b_str);
	if (!res) { result_mask.SetInvalid(i); continue; }
	result_data[i] = StringVector::AddString(result, *res);
})

DEFINE_ONE_STR_STR_UDF(ToQuantityFunc, {
	auto res = cql::to_quantity(a_str);
	if (!res) { result_mask.SetInvalid(i); continue; }
	result_data[i] = StringVector::AddString(result, *res);
})

static void ToQuantityDoubleFunc(DataChunk &args, ExpressionState &state, Vector &result) {
	idx_t count = args.size();
	UnifiedVectorFormat a_data;
	args.data[0].ToUnifiedFormat(count, a_data);
	auto a_vals = UnifiedVectorFormat::GetData<double>(a_data);

	result.SetVectorType(VectorType::FLAT_VECTOR);
	auto result_data = FlatVector::GetData<string_t>(result);
	auto &result_mask = FlatVector::Validity(result);

	for (idx_t i = 0; i < count; i++) {
		auto a_idx = a_data.sel->get_index(i);
		if (!a_data.validity.RowIsValid(a_idx) || !std::isfinite(a_vals[a_idx])) {
			result_mask.SetInvalid(i);
			continue;
		}
		cql::ParsedQuantity q{a_vals[a_idx], "1", "http://unitsofmeasure.org", 0};
		auto res = cql::format_quantity_json(q);
		if (!res) {
			result_mask.SetInvalid(i);
			continue;
		}
		result_data[i] = StringVector::AddString(result, *res);
	}
}

static void ToQuantityBoolFunc(DataChunk &args, ExpressionState &state, Vector &result) {
	idx_t count = args.size();
	result.SetVectorType(VectorType::FLAT_VECTOR);
	auto &result_mask = FlatVector::Validity(result);
	for (idx_t i = 0; i < count; i++) {
		result_mask.SetInvalid(i);
	}
}

DEFINE_ONE_STR_STR_UDF(ToConceptFunc, {
	auto res = cql::to_concept(a_str);
	if (!res) { result_mask.SetInvalid(i); continue; }
	result_data[i] = StringVector::AddString(result, *res);
})

static void ToConceptListFunc(DataChunk &args, ExpressionState &state, Vector &result) {
	idx_t count = args.size();
	auto &list_vec = args.data[0];
	UnifiedVectorFormat list_data;
	list_vec.ToUnifiedFormat(count, list_data);
	auto list_entries = UnifiedVectorFormat::GetData<list_entry_t>(list_data);
	auto &child_vec = ListVector::GetEntry(list_vec);
	UnifiedVectorFormat child_data;
	child_vec.ToUnifiedFormat(ListVector::GetListSize(list_vec), child_data);
	auto child_vals = UnifiedVectorFormat::GetData<string_t>(child_data);

	result.SetVectorType(VectorType::FLAT_VECTOR);
	auto result_data = FlatVector::GetData<string_t>(result);
	auto &result_mask = FlatVector::Validity(result);

	for (idx_t i = 0; i < count; i++) {
		auto idx = list_data.sel->get_index(i);
		if (!list_data.validity.RowIsValid(idx)) {
			result_mask.SetInvalid(i);
			continue;
		}
		auto &entry = list_entries[idx];
		std::string json_array = "[";
		bool valid = true;
		for (idx_t j = 0; j < entry.length; j++) {
			auto child_idx = child_data.sel->get_index(entry.offset + j);
			if (!child_data.validity.RowIsValid(child_idx)) {
				valid = false;
				break;
			}
			if (j > 0) json_array += ",";
			json_array += child_vals[child_idx].GetString();
		}
		json_array += "]";
		if (!valid) {
			result_mask.SetInvalid(i);
			continue;
		}
		auto res = cql::to_concept(json_array);
		if (!res) {
			result_mask.SetInvalid(i);
			continue;
		}
		result_data[i] = StringVector::AddString(result, *res);
	}
}

// =====================================================================
// Phase 7: Logical aggregate UDFs
// =====================================================================

// AllTrue/AnyTrue/AllFalse/AnyFalse: VARCHAR (JSON array) → BOOLEAN
// Must handle NULL inputs manually (NULL → default per CQL spec)
static void LogicalAllTrueFunc(DataChunk &args, ExpressionState &state, Vector &result) {
	auto count = args.size();
	auto &input = args.data[0];
	UnifiedVectorFormat input_data;
	input.ToUnifiedFormat(count, input_data);
	auto input_strings = UnifiedVectorFormat::GetData<string_t>(input_data);

	result.SetVectorType(VectorType::FLAT_VECTOR);
	auto result_data = FlatVector::GetData<bool>(result);
	auto &result_mask = FlatVector::Validity(result);

	for (idx_t i = 0; i < count; i++) {
		auto idx = input_data.sel->get_index(i);
		if (!input_data.validity.RowIsValid(idx)) {
			result_data[i] = true; // NULL → empty list → true
			continue;
		}
		auto res = cql::logical_all_true(input_strings[idx].GetString());
		if (!res) { result_mask.SetInvalid(i); } else { result_data[i] = res.value(); }
	}
}

static void LogicalAnyTrueFunc(DataChunk &args, ExpressionState &state, Vector &result) {
	auto count = args.size();
	auto &input = args.data[0];
	UnifiedVectorFormat input_data;
	input.ToUnifiedFormat(count, input_data);
	auto input_strings = UnifiedVectorFormat::GetData<string_t>(input_data);

	result.SetVectorType(VectorType::FLAT_VECTOR);
	auto result_data = FlatVector::GetData<bool>(result);
	auto &result_mask = FlatVector::Validity(result);

	for (idx_t i = 0; i < count; i++) {
		auto idx = input_data.sel->get_index(i);
		if (!input_data.validity.RowIsValid(idx)) {
			result_data[i] = false; // NULL → empty list → false
			continue;
		}
		auto res = cql::logical_any_true(input_strings[idx].GetString());
		if (!res) { result_mask.SetInvalid(i); } else { result_data[i] = res.value(); }
	}
}

static void LogicalAllFalseFunc(DataChunk &args, ExpressionState &state, Vector &result) {
	auto count = args.size();
	auto &input = args.data[0];
	UnifiedVectorFormat input_data;
	input.ToUnifiedFormat(count, input_data);
	auto input_strings = UnifiedVectorFormat::GetData<string_t>(input_data);

	result.SetVectorType(VectorType::FLAT_VECTOR);
	auto result_data = FlatVector::GetData<bool>(result);
	auto &result_mask = FlatVector::Validity(result);

	for (idx_t i = 0; i < count; i++) {
		auto idx = input_data.sel->get_index(i);
		if (!input_data.validity.RowIsValid(idx)) {
			result_data[i] = true; // NULL → empty list → true
			continue;
		}
		auto res = cql::logical_all_false(input_strings[idx].GetString());
		if (!res) { result_mask.SetInvalid(i); } else { result_data[i] = res.value(); }
	}
}

static void LogicalAnyFalseFunc(DataChunk &args, ExpressionState &state, Vector &result) {
	auto count = args.size();
	auto &input = args.data[0];
	UnifiedVectorFormat input_data;
	input.ToUnifiedFormat(count, input_data);
	auto input_strings = UnifiedVectorFormat::GetData<string_t>(input_data);

	result.SetVectorType(VectorType::FLAT_VECTOR);
	auto result_data = FlatVector::GetData<bool>(result);
	auto &result_mask = FlatVector::Validity(result);

	for (idx_t i = 0; i < count; i++) {
		auto idx = input_data.sel->get_index(i);
		if (!input_data.validity.RowIsValid(idx)) {
			result_data[i] = false; // NULL → empty list → false
			continue;
		}
		auto res = cql::logical_any_false(input_strings[idx].GetString());
		if (!res) { result_mask.SetInvalid(i); } else { result_data[i] = res.value(); }
	}
}

static void LogicalAllTrueBoolListFunc(DataChunk &args, ExpressionState &state, Vector &result) {
	auto count = args.size();
	auto &list_vec = args.data[0];
	UnifiedVectorFormat list_data;
	list_vec.ToUnifiedFormat(count, list_data);
	auto list_entries = UnifiedVectorFormat::GetData<list_entry_t>(list_data);
	auto &child_vec = ListVector::GetEntry(list_vec);
	UnifiedVectorFormat child_data;
	child_vec.ToUnifiedFormat(ListVector::GetListSize(list_vec), child_data);
	auto child_vals = UnifiedVectorFormat::GetData<bool>(child_data);

	result.SetVectorType(VectorType::FLAT_VECTOR);
	auto result_data = FlatVector::GetData<bool>(result);

	for (idx_t i = 0; i < count; i++) {
		auto idx = list_data.sel->get_index(i);
		if (!list_data.validity.RowIsValid(idx)) {
			result_data[i] = true;
			continue;
		}
		auto &entry = list_entries[idx];
		bool all_true = true;
		for (idx_t j = 0; j < entry.length; j++) {
			auto child_idx = child_data.sel->get_index(entry.offset + j);
			if (child_data.validity.RowIsValid(child_idx) && !child_vals[child_idx]) {
				all_true = false;
				break;
			}
		}
		result_data[i] = all_true;
	}
}

static void LogicalAnyTrueBoolListFunc(DataChunk &args, ExpressionState &state, Vector &result) {
	auto count = args.size();
	auto &list_vec = args.data[0];
	UnifiedVectorFormat list_data;
	list_vec.ToUnifiedFormat(count, list_data);
	auto list_entries = UnifiedVectorFormat::GetData<list_entry_t>(list_data);
	auto &child_vec = ListVector::GetEntry(list_vec);
	UnifiedVectorFormat child_data;
	child_vec.ToUnifiedFormat(ListVector::GetListSize(list_vec), child_data);
	auto child_vals = UnifiedVectorFormat::GetData<bool>(child_data);

	result.SetVectorType(VectorType::FLAT_VECTOR);
	auto result_data = FlatVector::GetData<bool>(result);

	for (idx_t i = 0; i < count; i++) {
		auto idx = list_data.sel->get_index(i);
		if (!list_data.validity.RowIsValid(idx)) {
			result_data[i] = false;
			continue;
		}
		auto &entry = list_entries[idx];
		bool any_true = false;
		for (idx_t j = 0; j < entry.length; j++) {
			auto child_idx = child_data.sel->get_index(entry.offset + j);
			if (child_data.validity.RowIsValid(child_idx) && child_vals[child_idx]) {
				any_true = true;
				break;
			}
		}
		result_data[i] = any_true;
	}
}

static void LogicalAllFalseBoolListFunc(DataChunk &args, ExpressionState &state, Vector &result) {
	auto count = args.size();
	auto &list_vec = args.data[0];
	UnifiedVectorFormat list_data;
	list_vec.ToUnifiedFormat(count, list_data);
	auto list_entries = UnifiedVectorFormat::GetData<list_entry_t>(list_data);
	auto &child_vec = ListVector::GetEntry(list_vec);
	UnifiedVectorFormat child_data;
	child_vec.ToUnifiedFormat(ListVector::GetListSize(list_vec), child_data);
	auto child_vals = UnifiedVectorFormat::GetData<bool>(child_data);

	result.SetVectorType(VectorType::FLAT_VECTOR);
	auto result_data = FlatVector::GetData<bool>(result);

	for (idx_t i = 0; i < count; i++) {
		auto idx = list_data.sel->get_index(i);
		if (!list_data.validity.RowIsValid(idx)) {
			result_data[i] = true;
			continue;
		}
		auto &entry = list_entries[idx];
		bool all_false = true;
		for (idx_t j = 0; j < entry.length; j++) {
			auto child_idx = child_data.sel->get_index(entry.offset + j);
			if (child_data.validity.RowIsValid(child_idx) && child_vals[child_idx]) {
				all_false = false;
				break;
			}
		}
		result_data[i] = all_false;
	}
}

static void LogicalAnyFalseBoolListFunc(DataChunk &args, ExpressionState &state, Vector &result) {
	auto count = args.size();
	auto &list_vec = args.data[0];
	UnifiedVectorFormat list_data;
	list_vec.ToUnifiedFormat(count, list_data);
	auto list_entries = UnifiedVectorFormat::GetData<list_entry_t>(list_data);
	auto &child_vec = ListVector::GetEntry(list_vec);
	UnifiedVectorFormat child_data;
	child_vec.ToUnifiedFormat(ListVector::GetListSize(list_vec), child_data);
	auto child_vals = UnifiedVectorFormat::GetData<bool>(child_data);

	result.SetVectorType(VectorType::FLAT_VECTOR);
	auto result_data = FlatVector::GetData<bool>(result);

	for (idx_t i = 0; i < count; i++) {
		auto idx = list_data.sel->get_index(i);
		if (!list_data.validity.RowIsValid(idx)) {
			result_data[i] = false;
			continue;
		}
		auto &entry = list_entries[idx];
		bool any_false = false;
		for (idx_t j = 0; j < entry.length; j++) {
			auto child_idx = child_data.sel->get_index(entry.offset + j);
			if (child_data.validity.RowIsValid(child_idx) && !child_vals[child_idx]) {
				any_false = true;
				break;
			}
		}
		result_data[i] = any_false;
	}
}

static cql::Optional<bool> ParseLogicalBoolText(const std::string &text) {
	std::string normalized = text;
	std::transform(normalized.begin(), normalized.end(), normalized.begin(),
	               [](unsigned char ch) { return static_cast<char>(std::tolower(ch)); });
	if (normalized == "true") {
		return cql::Optional<bool>(true);
	}
	if (normalized == "false") {
		return cql::Optional<bool>(false);
	}
	return cql::NullOpt<bool>();
}

// LogicalImplies: two nullable VARCHAR → BOOLEAN (3-valued logic)
static void LogicalImpliesFunc(DataChunk &args, ExpressionState &state, Vector &result) {
	auto count = args.size();
	auto &a_vec = args.data[0];
	auto &b_vec = args.data[1];

	UnifiedVectorFormat a_data, b_data;
	a_vec.ToUnifiedFormat(count, a_data);
	b_vec.ToUnifiedFormat(count, b_data);

	auto a_strings = UnifiedVectorFormat::GetData<string_t>(a_data);
	auto b_strings = UnifiedVectorFormat::GetData<string_t>(b_data);

	result.SetVectorType(VectorType::FLAT_VECTOR);
	auto result_data = FlatVector::GetData<bool>(result);
	auto &result_mask = FlatVector::Validity(result);

	for (idx_t i = 0; i < count; i++) {
		auto a_idx = a_data.sel->get_index(i);
		auto b_idx = b_data.sel->get_index(i);

		bool a_null = !a_data.validity.RowIsValid(a_idx);
		bool b_null = !b_data.validity.RowIsValid(b_idx);

		bool a_val = false;
		bool b_val = false;
		if (!a_null) {
			auto parsed = ParseLogicalBoolText(a_strings[a_idx].GetString());
			if (!parsed) {
				result_mask.SetInvalid(i);
				continue;
			}
			a_val = parsed.value();
		}
		if (!b_null) {
			auto parsed = ParseLogicalBoolText(b_strings[b_idx].GetString());
			if (!parsed) {
				result_mask.SetInvalid(i);
				continue;
			}
			b_val = parsed.value();
		}

		auto res = cql::logical_implies(a_null, a_val, b_null, b_val);
		if (!res) {
			result_mask.SetInvalid(i);
		} else {
			result_data[i] = res.value();
		}
	}
}

// LogicalImplies: two nullable BOOLEAN → BOOLEAN (3-valued logic)
static void LogicalImpliesBoolFunc(DataChunk &args, ExpressionState &state, Vector &result) {
	auto count = args.size();
	UnifiedVectorFormat a_data, b_data;
	args.data[0].ToUnifiedFormat(count, a_data);
	args.data[1].ToUnifiedFormat(count, b_data);
	auto a_vals = UnifiedVectorFormat::GetData<bool>(a_data);
	auto b_vals = UnifiedVectorFormat::GetData<bool>(b_data);

	result.SetVectorType(VectorType::FLAT_VECTOR);
	auto result_data = FlatVector::GetData<bool>(result);
	auto &result_mask = FlatVector::Validity(result);

	for (idx_t i = 0; i < count; i++) {
		auto a_idx = a_data.sel->get_index(i);
		auto b_idx = b_data.sel->get_index(i);
		bool a_null = !a_data.validity.RowIsValid(a_idx);
		bool b_null = !b_data.validity.RowIsValid(b_idx);
		bool a_val = a_null ? false : a_vals[a_idx];
		bool b_val = b_null ? false : b_vals[b_idx];

		auto res = cql::logical_implies(a_null, a_val, b_null, b_val);
		if (!res) {
			result_mask.SetInvalid(i);
		} else {
			result_data[i] = res.value();
		}
	}
}

// LogicalCoalesce: VARCHAR (JSON array) → VARCHAR
DEFINE_ONE_STR_STR_UDF(LogicalCoalesceFunc, {
	auto res = cql::logical_coalesce(a_str);
	if (!res) { result_mask.SetInvalid(i); continue; }
	result_data[i] = StringVector::AddString(result, *res);
})

// =====================================================================
// Main registration
// =====================================================================
static void LoadInternal(ExtensionLoader &loader) {
	// Age UDFs
	RegisterSpecialScalar(loader, "AgeInYears", {LogicalType::VARCHAR}, LogicalType::BIGINT, AgeInYearsFunc);
	RegisterSpecialScalar(loader, "AgeInMonths", {LogicalType::VARCHAR}, LogicalType::BIGINT, AgeInMonthsFunc);
	RegisterSpecialScalar(loader, "AgeInWeeks", {LogicalType::VARCHAR}, LogicalType::BIGINT, AgeInWeeksFunc);
	RegisterSpecialScalar(loader, "AgeInDays", {LogicalType::VARCHAR}, LogicalType::BIGINT, AgeInDaysFunc);
	RegisterSpecialScalar(loader, "AgeInHours", {LogicalType::VARCHAR}, LogicalType::BIGINT, AgeInHoursFunc);
	RegisterSpecialScalar(loader, "AgeInMinutes", {LogicalType::VARCHAR}, LogicalType::BIGINT, AgeInMinutesFunc);
	RegisterSpecialScalar(loader, "AgeInSeconds", {LogicalType::VARCHAR}, LogicalType::BIGINT, AgeInSecondsFunc);
	RegisterSpecialScalar(loader, "AgeInYearsAt", {LogicalType::VARCHAR, LogicalType::VARCHAR}, LogicalType::BIGINT,
	                      AgeInYearsAtFunc);
	RegisterSpecialScalar(loader, "AgeInMonthsAt", {LogicalType::VARCHAR, LogicalType::VARCHAR}, LogicalType::BIGINT,
	                      AgeInMonthsAtFunc);
	RegisterSpecialScalar(loader, "AgeInWeeksAt", {LogicalType::VARCHAR, LogicalType::VARCHAR}, LogicalType::BIGINT,
	                      AgeInWeeksAtFunc);
	RegisterSpecialScalar(loader, "AgeInDaysAt", {LogicalType::VARCHAR, LogicalType::VARCHAR}, LogicalType::BIGINT,
	                      AgeInDaysAtFunc);
	RegisterSpecialScalar(loader, "AgeInHoursAt", {LogicalType::VARCHAR, LogicalType::VARCHAR}, LogicalType::BIGINT,
	                      AgeInHoursAtFunc);
	RegisterSpecialScalar(loader, "AgeInMinutesAt", {LogicalType::VARCHAR, LogicalType::VARCHAR}, LogicalType::BIGINT,
	                      AgeInMinutesAtFunc);
	RegisterSpecialScalar(loader, "AgeInSecondsAt", {LogicalType::VARCHAR, LogicalType::VARCHAR}, LogicalType::BIGINT,
	                      AgeInSecondsAtFunc);
	RegisterSpecialScalar(loader, "CalculateAgeInYears", {LogicalType::VARCHAR}, LogicalType::BIGINT,
	                      CalculateAgeInYearsFunc);
	RegisterSpecialScalar(loader, "CalculateAgeInMonths", {LogicalType::VARCHAR}, LogicalType::BIGINT,
	                      CalculateAgeInMonthsFunc);
	RegisterSpecialScalar(loader, "CalculateAgeInWeeks", {LogicalType::VARCHAR}, LogicalType::BIGINT,
	                      CalculateAgeInWeeksFunc);
	RegisterSpecialScalar(loader, "CalculateAgeInDays", {LogicalType::VARCHAR}, LogicalType::BIGINT,
	                      CalculateAgeInDaysFunc);
	RegisterSpecialScalar(loader, "CalculateAgeInHours", {LogicalType::VARCHAR}, LogicalType::BIGINT,
	                      CalculateAgeInHoursFunc);
	RegisterSpecialScalar(loader, "CalculateAgeInMinutes", {LogicalType::VARCHAR}, LogicalType::BIGINT,
	                      CalculateAgeInMinutesFunc);
	RegisterSpecialScalar(loader, "CalculateAgeInSeconds", {LogicalType::VARCHAR}, LogicalType::BIGINT,
	                      CalculateAgeInSecondsFunc);
	RegisterSpecialScalar(loader, "CalculateAgeInYearsAt", {LogicalType::VARCHAR, LogicalType::VARCHAR},
	                      LogicalType::BIGINT, CalculateAgeInYearsAtFunc);
	RegisterSpecialScalar(loader, "CalculateAgeInMonthsAt", {LogicalType::VARCHAR, LogicalType::VARCHAR},
	                      LogicalType::BIGINT, CalculateAgeInMonthsAtFunc);
	RegisterSpecialScalar(loader, "CalculateAgeInWeeksAt", {LogicalType::VARCHAR, LogicalType::VARCHAR},
	                      LogicalType::BIGINT, CalculateAgeInWeeksAtFunc);
	RegisterSpecialScalar(loader, "CalculateAgeInDaysAt", {LogicalType::VARCHAR, LogicalType::VARCHAR},
	                      LogicalType::BIGINT, CalculateAgeInDaysAtFunc);
	RegisterSpecialScalar(loader, "CalculateAgeInHoursAt", {LogicalType::VARCHAR, LogicalType::VARCHAR},
	                      LogicalType::BIGINT, CalculateAgeInHoursAtFunc);
	RegisterSpecialScalar(loader, "CalculateAgeInMinutesAt", {LogicalType::VARCHAR, LogicalType::VARCHAR},
	                      LogicalType::BIGINT, CalculateAgeInMinutesAtFunc);
	RegisterSpecialScalar(loader, "CalculateAgeInSecondsAt", {LogicalType::VARCHAR, LogicalType::VARCHAR},
	                      LogicalType::BIGINT, CalculateAgeInSecondsAtFunc);

	// CQL string regex helpers used by Python-side SQL macros and WASM/no-Python execution.
	RegisterSpecialScalar(loader, "cqlRegexMatches", {LogicalType::VARCHAR, LogicalType::VARCHAR},
	                      LogicalType::BOOLEAN, CqlRegexMatchesFunc);
	RegisterSpecialScalar(loader, "cqlRegexReplaceMatches",
	                      {LogicalType::VARCHAR, LogicalType::VARCHAR, LogicalType::VARCHAR},
	                      LogicalType::VARCHAR, CqlRegexReplaceMatchesFunc);
	RegisterSpecialScalar(loader, "cqlRegexSplitOnMatches", {LogicalType::VARCHAR, LogicalType::VARCHAR},
	                      LogicalType::LIST(LogicalType::VARCHAR), CqlRegexSplitOnMatchesFunc);

	// Interval UDFs (22 — includes collapse_intervals). These are registered
	// for native and WASM builds so browser-required functions are exercised by
	// the native C++ test path instead of being hidden by Python fallback UDFs.
	RegisterSpecialScalar(loader, "intervalStart", {LogicalType::VARCHAR}, LogicalType::VARCHAR, IntervalStartFunc);
	RegisterSpecialScalar(loader, "intervalEnd", {LogicalType::VARCHAR}, LogicalType::VARCHAR, IntervalEndFunc);
	RegisterSpecialScalar(loader, "intervalWidth", {LogicalType::VARCHAR}, LogicalType::VARCHAR, IntervalWidthFunc);
	RegisterSpecialScalar(loader, "intervalContains", {LogicalType::VARCHAR, LogicalType::VARCHAR},
	                      LogicalType::BOOLEAN, IntervalContainsFunc);
	RegisterSpecialScalar(loader, "intervalProperlyContains", {LogicalType::VARCHAR, LogicalType::VARCHAR},
	                      LogicalType::BOOLEAN, IntervalProperlyContainsFunc);
	RegisterSpecialScalar(loader, "intervalOverlaps", {LogicalType::VARCHAR, LogicalType::VARCHAR},
	                      LogicalType::BOOLEAN, IntervalOverlapsFunc);
	RegisterSpecialScalar(loader, "intervalBefore", {LogicalType::VARCHAR, LogicalType::VARCHAR}, LogicalType::BOOLEAN,
	                      IntervalBeforeFunc);
	RegisterSpecialScalar(loader, "intervalAfter", {LogicalType::VARCHAR, LogicalType::VARCHAR}, LogicalType::BOOLEAN,
	                      IntervalAfterFunc);
	RegisterSpecialScalar(loader, "intervalMeets", {LogicalType::VARCHAR, LogicalType::VARCHAR}, LogicalType::BOOLEAN,
	                      IntervalMeetsFunc);
	RegisterSpecialScalar(loader, "intervalIncludes", {LogicalType::VARCHAR, LogicalType::VARCHAR},
	                      LogicalType::BOOLEAN, IntervalIncludesFunc);
	RegisterSpecialScalar(loader, "intervalIncludedIn", {LogicalType::VARCHAR, LogicalType::VARCHAR},
	                      LogicalType::BOOLEAN, IntervalIncludedInFunc);
	RegisterSpecialScalar(loader, "intervalProperlyIncludes", {LogicalType::VARCHAR, LogicalType::VARCHAR},
	                      LogicalType::BOOLEAN, IntervalProperlyIncludesFunc);
	RegisterSpecialScalar(loader, "intervalProperlyIncludedIn", {LogicalType::VARCHAR, LogicalType::VARCHAR},
	                      LogicalType::BOOLEAN, IntervalProperlyIncludedInFunc);
	RegisterSpecialScalar(loader, "intervalOverlapsBefore", {LogicalType::VARCHAR, LogicalType::VARCHAR},
	                      LogicalType::BOOLEAN, IntervalOverlapsBeforeFunc);
	RegisterSpecialScalar(loader, "intervalOverlapsAfter", {LogicalType::VARCHAR, LogicalType::VARCHAR},
	                      LogicalType::BOOLEAN, IntervalOverlapsAfterFunc);
	RegisterSpecialScalar(loader, "intervalMeetsBefore", {LogicalType::VARCHAR, LogicalType::VARCHAR},
	                      LogicalType::BOOLEAN, IntervalMeetsBeforeFunc);
	RegisterSpecialScalar(loader, "intervalMeetsAfter", {LogicalType::VARCHAR, LogicalType::VARCHAR},
	                      LogicalType::BOOLEAN, IntervalMeetsAfterFunc);
	RegisterSpecialScalar(loader, "intervalStartsSame", {LogicalType::VARCHAR, LogicalType::VARCHAR},
	                      LogicalType::BOOLEAN, IntervalStartsSameFunc);
	RegisterSpecialScalar(loader, "intervalEndsSame", {LogicalType::VARCHAR, LogicalType::VARCHAR},
	                      LogicalType::BOOLEAN, IntervalEndsSameFunc);
	RegisterSpecialScalar(loader, "intervalEquals", {LogicalType::VARCHAR, LogicalType::VARCHAR},
	                      LogicalType::BOOLEAN, IntervalEqualsFunc);
	RegisterSpecialScalar(loader, "intervalEquivalent", {LogicalType::VARCHAR, LogicalType::VARCHAR},
	                      LogicalType::BOOLEAN, IntervalEquivalentFunc);
	RegisterSpecialScalar(loader, "intervalFromBounds",
	                      {LogicalType::VARCHAR, LogicalType::VARCHAR, LogicalType::BOOLEAN, LogicalType::BOOLEAN},
	                      LogicalType::VARCHAR, IntervalFromBoundsFunc);
	RegisterSpecialScalar(loader, "interval_size", {LogicalType::VARCHAR}, LogicalType::VARCHAR, IntervalSizeFunc);
	RegisterSpecialScalar(loader, "expand_points1", {LogicalType::VARCHAR}, LogicalType::VARCHAR, ExpandPoints1Func);
	RegisterSpecialScalar(loader, "expand_points", {LogicalType::VARCHAR, LogicalType::VARCHAR}, LogicalType::VARCHAR,
	                      ExpandPointsFunc);
	RegisterSpecialScalar(loader, "expand1", {LogicalType::LIST(LogicalType::VARCHAR)}, LogicalType::VARCHAR,
	                      Expand1Func);
	RegisterSpecialScalar(loader, "expand", {LogicalType::LIST(LogicalType::VARCHAR), LogicalType::VARCHAR},
	                      LogicalType::VARCHAR, ExpandFunc);
	RegisterSpecialScalar(loader, "collapse_intervals", {LogicalType::VARCHAR}, LogicalType::VARCHAR,
	                      CollapseIntervalsFunc);

	// Precision-aware interval UDFs (3-arg: interval, interval/point, precision → BOOLEAN)
	RegisterSpecialScalar(loader, "intervalOverlapsPrecise",
	                      {LogicalType::VARCHAR, LogicalType::VARCHAR, LogicalType::VARCHAR},
	                      LogicalType::BOOLEAN, IntervalOverlapsPreciseFunc);
	RegisterSpecialScalar(loader, "intervalContainsPrecise",
	                      {LogicalType::VARCHAR, LogicalType::VARCHAR, LogicalType::VARCHAR},
	                      LogicalType::BOOLEAN, IntervalContainsPreciseFunc);
	RegisterSpecialScalar(loader, "intervalIncludesPrecise",
	                      {LogicalType::VARCHAR, LogicalType::VARCHAR, LogicalType::VARCHAR},
	                      LogicalType::BOOLEAN, IntervalIncludesPreciseFunc);
	RegisterSpecialScalar(loader, "intervalIncludedInPrecise",
	                      {LogicalType::VARCHAR, LogicalType::VARCHAR, LogicalType::VARCHAR},
	                      LogicalType::BOOLEAN, IntervalIncludedInPreciseFunc);
	RegisterSpecialScalar(loader, "intervalBeforePrecise",
	                      {LogicalType::VARCHAR, LogicalType::VARCHAR, LogicalType::VARCHAR},
	                      LogicalType::BOOLEAN, IntervalBeforePreciseFunc);
	RegisterSpecialScalar(loader, "intervalAfterPrecise",
	                      {LogicalType::VARCHAR, LogicalType::VARCHAR, LogicalType::VARCHAR},
	                      LogicalType::BOOLEAN, IntervalAfterPreciseFunc);
	RegisterSpecialScalar(loader, "intervalOverlapsBeforePrecise",
	                      {LogicalType::VARCHAR, LogicalType::VARCHAR, LogicalType::VARCHAR},
	                      LogicalType::BOOLEAN, IntervalOverlapsBeforePreciseFunc);
	RegisterSpecialScalar(loader, "intervalOverlapsAfterPrecise",
	                      {LogicalType::VARCHAR, LogicalType::VARCHAR, LogicalType::VARCHAR},
	                      LogicalType::BOOLEAN, IntervalOverlapsAfterPreciseFunc);
	RegisterSpecialScalar(loader, "truncateInterval",
	                      {LogicalType::VARCHAR, LogicalType::VARCHAR},
	                      LogicalType::VARCHAR, TruncateIntervalFunc);

	// Datetime difference and duration UDFs.
	RegisterSpecialScalar(loader, "differenceInYears", {LogicalType::VARCHAR, LogicalType::VARCHAR},
	                      LogicalType::BIGINT, DifferenceInYearsFunc);
	RegisterSpecialScalar(loader, "differenceInMonths", {LogicalType::VARCHAR, LogicalType::VARCHAR},
	                      LogicalType::BIGINT, DifferenceInMonthsFunc);
	RegisterSpecialScalar(loader, "differenceInWeeks", {LogicalType::VARCHAR, LogicalType::VARCHAR},
	                      LogicalType::BIGINT, DifferenceInWeeksFunc);
	RegisterSpecialScalar(loader, "differenceInDays", {LogicalType::VARCHAR, LogicalType::VARCHAR},
	                      LogicalType::BIGINT, DifferenceInDaysFunc);
	RegisterSpecialScalar(loader, "differenceInHours", {LogicalType::VARCHAR, LogicalType::VARCHAR},
	                      LogicalType::BIGINT, DifferenceInHoursFunc);
	RegisterSpecialScalar(loader, "differenceInMinutes", {LogicalType::VARCHAR, LogicalType::VARCHAR},
	                      LogicalType::BIGINT, DifferenceInMinutesFunc);
	RegisterSpecialScalar(loader, "differenceInSeconds", {LogicalType::VARCHAR, LogicalType::VARCHAR},
	                      LogicalType::BIGINT, DifferenceInSecondsFunc);
	RegisterSpecialScalar(loader, "differenceInMilliseconds", {LogicalType::VARCHAR, LogicalType::VARCHAR},
	                      LogicalType::BIGINT, DifferenceInMillisecondsFunc);
	RegisterSpecialScalar(loader, "weeksBetween", {LogicalType::VARCHAR, LogicalType::VARCHAR}, LogicalType::BIGINT,
	                      WeeksBetweenFunc);
	RegisterSpecialScalar(loader, "millisecondsBetween", {LogicalType::VARCHAR, LogicalType::VARCHAR},
	                      LogicalType::BIGINT, MillisecondsBetweenFunc);
	RegisterSpecialScalar(loader, "YearsBetween", {LogicalType::VARCHAR, LogicalType::VARCHAR}, LogicalType::BIGINT,
	                      YearsBetweenFunc);
	RegisterSpecialScalar(loader, "MonthsBetween", {LogicalType::VARCHAR, LogicalType::VARCHAR}, LogicalType::BIGINT,
	                      MonthsBetweenFunc);
	RegisterSpecialScalar(loader, "DaysBetween", {LogicalType::VARCHAR, LogicalType::VARCHAR}, LogicalType::BIGINT,
	                      DaysBetweenFunc);
	RegisterSpecialScalar(loader, "HoursBetween", {LogicalType::VARCHAR, LogicalType::VARCHAR}, LogicalType::BIGINT,
	                      HoursBetweenFunc);
	RegisterSpecialScalar(loader, "MinutesBetween", {LogicalType::VARCHAR, LogicalType::VARCHAR}, LogicalType::BIGINT,
	                      MinutesBetweenFunc);
	RegisterSpecialScalar(loader, "SecondsBetween", {LogicalType::VARCHAR, LogicalType::VARCHAR}, LogicalType::BIGINT,
	                      SecondsBetweenFunc);
	loader.RegisterFunction(ScalarFunction("dateTimeNow", {}, LogicalType::VARCHAR, DateTimeNowFunc));
	loader.RegisterFunction(ScalarFunction("dateTimeToday", {}, LogicalType::VARCHAR, DateTimeTodayFunc));
	loader.RegisterFunction(ScalarFunction("dateTimeTimeOfDay", {}, LogicalType::VARCHAR, DateTimeTimeOfDayFunc));
	RegisterSpecialScalar(loader, "dateTimeSameAs",
	                      {LogicalType::VARCHAR, LogicalType::VARCHAR, LogicalType::VARCHAR}, LogicalType::BOOLEAN,
	                      CqlSameAsPFunc);
	RegisterSpecialScalar(loader, "dateTimeSameOrBefore",
	                      {LogicalType::VARCHAR, LogicalType::VARCHAR, LogicalType::VARCHAR}, LogicalType::BOOLEAN,
	                      CqlSameOrBeforePFunc);
	RegisterSpecialScalar(loader, "dateTimeSameOrAfter",
	                      {LogicalType::VARCHAR, LogicalType::VARCHAR, LogicalType::VARCHAR}, LogicalType::BOOLEAN,
	                      CqlSameOrAfterPFunc);
	RegisterSpecialScalar(loader, "cqlSameOrBefore", {LogicalType::VARCHAR, LogicalType::VARCHAR},
	                      LogicalType::BOOLEAN, CqlSameOrBeforeFunc);
	RegisterSpecialScalar(loader, "cqlSameOrAfter", {LogicalType::VARCHAR, LogicalType::VARCHAR},
	                      LogicalType::BOOLEAN, CqlSameOrAfterFunc);
	RegisterSpecialScalar(loader, "cqlBefore", {LogicalType::VARCHAR, LogicalType::VARCHAR},
	                      LogicalType::BOOLEAN, CqlBeforeFunc);
	RegisterSpecialScalar(loader, "cqlAfter", {LogicalType::VARCHAR, LogicalType::VARCHAR},
	                      LogicalType::BOOLEAN, CqlAfterFunc);
	RegisterSpecialScalar(loader, "cqlDateTimeEqual", {LogicalType::VARCHAR, LogicalType::VARCHAR},
	                      LogicalType::BOOLEAN, CqlDateTimeEqualFunc);
	RegisterSpecialScalar(loader, "cqlSameOrBeforeP",
	                      {LogicalType::VARCHAR, LogicalType::VARCHAR, LogicalType::VARCHAR}, LogicalType::BOOLEAN,
	                      CqlSameOrBeforePFunc);
	RegisterSpecialScalar(loader, "cqlSameOrAfterP",
	                      {LogicalType::VARCHAR, LogicalType::VARCHAR, LogicalType::VARCHAR}, LogicalType::BOOLEAN,
	                      CqlSameOrAfterPFunc);
	RegisterSpecialScalar(loader, "cqlBeforeP",
	                      {LogicalType::VARCHAR, LogicalType::VARCHAR, LogicalType::VARCHAR}, LogicalType::BOOLEAN,
	                      CqlBeforePFunc);
	RegisterSpecialScalar(loader, "cqlAfterP",
	                      {LogicalType::VARCHAR, LogicalType::VARCHAR, LogicalType::VARCHAR}, LogicalType::BOOLEAN,
	                      CqlAfterPFunc);
	RegisterSpecialScalar(loader, "cqlSameAsP",
	                      {LogicalType::VARCHAR, LogicalType::VARCHAR, LogicalType::VARCHAR}, LogicalType::BOOLEAN,
	                      CqlSameAsPFunc);
	RegisterSpecialScalar(loader, "cqlDurationBetween",
	                      {LogicalType::VARCHAR, LogicalType::VARCHAR, LogicalType::VARCHAR}, LogicalType::VARCHAR,
	                      CqlDurationBetweenFunc);
	RegisterSpecialScalar(loader, "cqlDifferenceBetween",
	                      {LogicalType::VARCHAR, LogicalType::VARCHAR, LogicalType::VARCHAR}, LogicalType::VARCHAR,
	                      CqlDifferenceBetweenFunc);
	RegisterSpecialScalar(loader, "cqlUncertainAdd",
	                      {LogicalType::VARCHAR, LogicalType::VARCHAR}, LogicalType::VARCHAR,
	                      CqlUncertainAddFunc);
	RegisterSpecialScalar(loader, "cqlUncertainSubtract",
	                      {LogicalType::VARCHAR, LogicalType::VARCHAR}, LogicalType::VARCHAR,
	                      CqlUncertainSubtractFunc);
	RegisterSpecialScalar(loader, "cqlUncertainMultiply",
	                      {LogicalType::VARCHAR, LogicalType::VARCHAR}, LogicalType::VARCHAR,
	                      CqlUncertainMultiplyFunc);
	RegisterSpecialScalar(loader, "cqlUncertainCompare",
	                      {LogicalType::VARCHAR, LogicalType::VARCHAR, LogicalType::VARCHAR}, LogicalType::BOOLEAN,
	                      CqlUncertainCompareFunc);
	RegisterSpecialScalar(loader, "dateComponent", {LogicalType::VARCHAR, LogicalType::VARCHAR}, LogicalType::BIGINT,
	                      DateComponentFunc);
	RegisterSpecialScalar(loader, "quantityToInterval", {LogicalType::VARCHAR}, LogicalType::VARCHAR,
	                      QuantityToIntervalFunc);
	RegisterSpecialScalar(loader, "dateAddQuantity", {LogicalType::VARCHAR, LogicalType::VARCHAR},
	                      LogicalType::VARCHAR, DateAddQuantityFunc);
	RegisterSpecialScalar(loader, "dateSubtractQuantity", {LogicalType::VARCHAR, LogicalType::VARCHAR},
	                      LogicalType::VARCHAR, DateSubtractQuantityFunc);

	// Clinical UDFs (4)
	RegisterSpecialScalar(loader, "Latest",
	                      {LogicalType::LIST(LogicalType::VARCHAR), LogicalType::VARCHAR}, LogicalType::VARCHAR,
	                      LatestFunc);
	RegisterSpecialScalar(loader, "Earliest",
	                      {LogicalType::LIST(LogicalType::VARCHAR), LogicalType::VARCHAR}, LogicalType::VARCHAR,
	                      EarliestFunc);
	RegisterSpecialScalar(loader, "claim_principal_diagnosis", {LogicalType::VARCHAR, LogicalType::VARCHAR},
	                      LogicalType::VARCHAR, ClaimPrincipalDiagnosisFunc);
	RegisterSpecialScalar(loader, "claim_principal_procedure", {LogicalType::VARCHAR, LogicalType::VARCHAR},
	                      LogicalType::VARCHAR, ClaimPrincipalProcedureFunc);

	// Aggregate UDFs (4)
	RegisterSpecialScalar(loader, "statisticalMedian", {LogicalType::LIST(LogicalType::DOUBLE)}, LogicalType::DOUBLE,
	                      StatisticalMedianFunc);
	RegisterSpecialScalar(loader, "statisticalMode", {LogicalType::LIST(LogicalType::DOUBLE)}, LogicalType::DOUBLE,
	                      StatisticalModeFunc);
	RegisterSpecialScalar(loader, "statisticalStdDev", {LogicalType::LIST(LogicalType::DOUBLE)}, LogicalType::DOUBLE,
	                      StatisticalStdDevFunc);
	RegisterSpecialScalar(loader, "statisticalVariance", {LogicalType::LIST(LogicalType::DOUBLE)}, LogicalType::DOUBLE,
	                      StatisticalVarianceFunc);

	// Valueset UDFs (6)
	RegisterSpecialScalar(loader, "extractCodes", {LogicalType::VARCHAR, LogicalType::VARCHAR},
	                      LogicalType::LIST(LogicalType::VARCHAR), ExtractCodesFunc);
	RegisterSpecialScalar(loader, "extractFirstCode", {LogicalType::VARCHAR, LogicalType::VARCHAR},
	                      LogicalType::VARCHAR, ExtractFirstCodeFunc);
	RegisterSpecialScalar(loader, "extractFirstCodeSystem", {LogicalType::VARCHAR, LogicalType::VARCHAR},
	                      LogicalType::VARCHAR, ExtractFirstCodeSystemFunc);
	RegisterSpecialScalar(loader, "extractFirstCodeValue", {LogicalType::VARCHAR, LogicalType::VARCHAR},
	                      LogicalType::VARCHAR, ExtractFirstCodeValueFunc);
	RegisterSpecialScalar(loader, "resolveProfileUrl", {LogicalType::VARCHAR}, LogicalType::VARCHAR,
	                      ResolveProfileUrlFunc);

	// in_valueset (stub — cache not yet populated)
	RegisterSpecialScalar(loader, "in_valueset", {LogicalType::VARCHAR, LogicalType::VARCHAR, LogicalType::VARCHAR},
	                      LogicalType::BOOLEAN, InValuesetFunc);
	RegisterSpecialScalar(loader, "cql_valueset_cache_clear", {}, LogicalType::BOOLEAN, ValuesetCacheClearFunc);
	RegisterSpecialScalar(loader, "cql_valueset_cache_add",
	                      {LogicalType::VARCHAR, LogicalType::VARCHAR, LogicalType::VARCHAR},
	                      LogicalType::BOOLEAN, ValuesetCacheAddFunc);
	RegisterSpecialScalar(loader, "cql_valueset_cache_size", {}, LogicalType::BIGINT, ValuesetCacheSizeFunc);
	RegisterSpecialScalar(loader, "cql_valueset_profile_clear", {}, LogicalType::BOOLEAN, ValuesetProfileClearFunc);
	RegisterSpecialScalar(loader, "cql_valueset_profile_json", {}, LogicalType::VARCHAR, ValuesetProfileJsonFunc);

	// Ratio UDFs (6)
	RegisterSpecialScalar(loader, "ratioNumeratorValue", {LogicalType::VARCHAR}, LogicalType::DOUBLE,
	                      RatioNumeratorValueFunc);
	RegisterSpecialScalar(loader, "ratioDenominatorValue", {LogicalType::VARCHAR}, LogicalType::DOUBLE,
	                      RatioDenominatorValueFunc);
	RegisterSpecialScalar(loader, "ratioValue", {LogicalType::VARCHAR}, LogicalType::DOUBLE, RatioValueFunc);
	RegisterSpecialScalar(loader, "ratioNumeratorUnit", {LogicalType::VARCHAR}, LogicalType::VARCHAR,
	                      RatioNumeratorUnitFunc);
	RegisterSpecialScalar(loader, "ratioDenominatorUnit", {LogicalType::VARCHAR}, LogicalType::VARCHAR,
	                      RatioDenominatorUnitFunc);
	RegisterSpecialScalar(loader, "RatioToString", {LogicalType::VARCHAR}, LogicalType::VARCHAR,
	                      RatioToStringFunc);

	// Quantity UDFs (7 + 7 snake_case aliases = 14)
	RegisterSpecialScalar(loader, "parseQuantity", {LogicalType::VARCHAR}, LogicalType::VARCHAR, ParseQuantityFunc);
	RegisterSpecialScalar(loader, "parse_quantity", {LogicalType::VARCHAR}, LogicalType::VARCHAR, ParseQuantityFunc);
	RegisterSpecialScalar(loader, "quantityValue", {LogicalType::VARCHAR}, LogicalType::DOUBLE, QuantityValueFunc);
	RegisterSpecialScalar(loader, "quantity_value", {LogicalType::VARCHAR}, LogicalType::DOUBLE, QuantityValueFunc);
	RegisterSpecialScalar(loader, "quantityUnit", {LogicalType::VARCHAR}, LogicalType::VARCHAR, QuantityUnitFunc);
	RegisterSpecialScalar(loader, "quantity_unit", {LogicalType::VARCHAR}, LogicalType::VARCHAR, QuantityUnitFunc);
	RegisterSpecialScalar(loader, "quantityCompare",
	                      {LogicalType::VARCHAR, LogicalType::VARCHAR, LogicalType::VARCHAR}, LogicalType::BOOLEAN,
	                      QuantityCompareFunc);
	RegisterSpecialScalar(loader, "quantity_compare",
	                      {LogicalType::VARCHAR, LogicalType::VARCHAR, LogicalType::VARCHAR}, LogicalType::BOOLEAN,
	                      QuantityCompareFunc);
	RegisterSpecialScalar(loader, "quantityAdd", {LogicalType::VARCHAR, LogicalType::VARCHAR}, LogicalType::VARCHAR,
	                      QuantityAddFunc);
	RegisterSpecialScalar(loader, "quantity_add", {LogicalType::VARCHAR, LogicalType::VARCHAR}, LogicalType::VARCHAR,
	                      QuantityAddFunc);
	RegisterSpecialScalar(loader, "quantitySubtract", {LogicalType::VARCHAR, LogicalType::VARCHAR},
	                      LogicalType::VARCHAR, QuantitySubtractFunc);
	RegisterSpecialScalar(loader, "quantity_subtract", {LogicalType::VARCHAR, LogicalType::VARCHAR},
	                      LogicalType::VARCHAR, QuantitySubtractFunc);
	RegisterSpecialScalar(loader, "quantityConvert", {LogicalType::VARCHAR, LogicalType::VARCHAR},
	                      LogicalType::VARCHAR, QuantityConvertFunc);
	RegisterSpecialScalar(loader, "quantity_convert", {LogicalType::VARCHAR, LogicalType::VARCHAR},
	                      LogicalType::VARCHAR, QuantityConvertFunc);

	// List UDFs (3)
	RegisterSpecialScalar(loader, "SingletonFrom", {LogicalType::LIST(LogicalType::VARCHAR)}, LogicalType::VARCHAR,
	                      SingletonFromFunc);
	RegisterSpecialScalar(loader, "SingletonFrom", {LogicalType::LIST(LogicalType::ANY)}, LogicalType::VARCHAR,
	                      SingletonFromAnyListFunc);
	RegisterSpecialScalar(loader, "ElementAt", {LogicalType::LIST(LogicalType::VARCHAR), LogicalType::BIGINT},
	                      LogicalType::VARCHAR, ElementAtFunc);
	RegisterSpecialScalar(loader, "ElementAt", {LogicalType::LIST(LogicalType::ANY), LogicalType::BIGINT},
	                      LogicalType::VARCHAR, ElementAtAnyListFunc);
	RegisterSpecialScalar(loader, "jsonConcat", {LogicalType::VARCHAR, LogicalType::VARCHAR},
	                      LogicalType::LIST(LogicalType::VARCHAR), JsonConcatFunc);
	RegisterSpecialScalar(loader, "jsonConcat",
	                      {LogicalType::LIST(LogicalType::VARCHAR), LogicalType::LIST(LogicalType::VARCHAR)},
	                      LogicalType::LIST(LogicalType::VARCHAR), JsonConcatListListFunc);
	RegisterSpecialScalar(loader, "jsonConcat", {LogicalType::LIST(LogicalType::VARCHAR), LogicalType::VARCHAR},
	                      LogicalType::LIST(LogicalType::VARCHAR), JsonConcatListScalarFunc);
	RegisterSpecialScalar(loader, "jsonConcat", {LogicalType::VARCHAR, LogicalType::LIST(LogicalType::VARCHAR)},
	                      LogicalType::LIST(LogicalType::VARCHAR), JsonConcatScalarListFunc);
	RegisterSpecialScalar(loader, "jsonConcat", {LogicalType::ANY, LogicalType::ANY},
	                      LogicalType::LIST(LogicalType::VARCHAR), JsonConcatAnyFunc);

	// Boundary UDFs. Browser-required functions are registered in native builds
	// too so parity regressions are visible outside browser-only tests.
	RegisterSpecialScalar(loader, "HighBoundary", {LogicalType::VARCHAR},
	                      LogicalType::VARCHAR, HighBoundaryFunc1);
	RegisterSpecialScalar(loader, "HighBoundary", {LogicalType::VARCHAR, LogicalType::BIGINT},
	                      LogicalType::VARCHAR, HighBoundaryFunc2);
	RegisterSpecialScalar(loader, "HighBoundary", {LogicalType::DOUBLE},
	                      LogicalType::DOUBLE, HighBoundaryDoubleFunc1);
	RegisterSpecialScalar(loader, "HighBoundary", {LogicalType::DOUBLE, LogicalType::BIGINT},
	                      LogicalType::DOUBLE, HighBoundaryDoubleFunc);
	RegisterSpecialScalar(loader, "LowBoundary", {LogicalType::VARCHAR},
	                      LogicalType::VARCHAR, LowBoundaryFunc1);
	RegisterSpecialScalar(loader, "LowBoundary", {LogicalType::VARCHAR, LogicalType::BIGINT},
	                      LogicalType::VARCHAR, LowBoundaryFunc2);
	RegisterSpecialScalar(loader, "LowBoundary", {LogicalType::DOUBLE},
	                      LogicalType::DOUBLE, LowBoundaryDoubleFunc1);
	RegisterSpecialScalar(loader, "LowBoundary", {LogicalType::DOUBLE, LogicalType::BIGINT},
	                      LogicalType::DOUBLE, LowBoundaryDoubleFunc);
	RegisterSpecialScalar(loader, "predecessorOf", {LogicalType::VARCHAR},
	                      LogicalType::VARCHAR, PredecessorOfFunc);
	RegisterSpecialScalar(loader, "predecessorOf", {LogicalType::BIGINT},
	                      LogicalType::BIGINT, PredecessorOfBigIntFunc);
	RegisterSpecialScalar(loader, "predecessorOf", {LogicalType::DOUBLE},
	                      LogicalType::DOUBLE, PredecessorOfDoubleFunc);
	RegisterSpecialScalar(loader, "successorOf", {LogicalType::VARCHAR},
	                      LogicalType::VARCHAR, SuccessorOfFunc);
	RegisterSpecialScalar(loader, "successorOf", {LogicalType::BIGINT},
	                      LogicalType::BIGINT, SuccessorOfBigIntFunc);
	RegisterSpecialScalar(loader, "successorOf", {LogicalType::DOUBLE},
	                      LogicalType::DOUBLE, SuccessorOfDoubleFunc);
	RegisterSpecialScalar(loader, "CQLPrecision", {LogicalType::VARCHAR},
	                      LogicalType::BIGINT, CQLPrecisionFunc);
	RegisterSpecialScalar(loader, "cqlTimezoneOffset", {LogicalType::VARCHAR},
	                      LogicalType::DOUBLE, CQLTimezoneOffsetFunc);

	// Interval set operations.
	RegisterSpecialScalar(loader, "intervalIntersect", {LogicalType::VARCHAR, LogicalType::VARCHAR},
	                      LogicalType::VARCHAR, IntervalIntersectFunc);
	RegisterSpecialScalar(loader, "intervalUnion", {LogicalType::VARCHAR, LogicalType::VARCHAR},
	                      LogicalType::VARCHAR, IntervalUnionFunc);
	RegisterSpecialScalar(loader, "intervalExcept", {LogicalType::VARCHAR, LogicalType::VARCHAR},
	                      LogicalType::VARCHAR, IntervalExceptFunc);
	RegisterSpecialScalar(loader, "intervalOnOrAfter", {LogicalType::VARCHAR, LogicalType::VARCHAR},
	                      LogicalType::BOOLEAN, IntervalOnOrAfterFunc);
	RegisterSpecialScalar(loader, "intervalOnOrBefore", {LogicalType::VARCHAR, LogicalType::VARCHAR},
	                      LogicalType::BOOLEAN, IntervalOnOrBeforeFunc);

	// Phase 4: pointFrom
	RegisterSpecialScalar(loader, "pointFrom", {LogicalType::VARCHAR},
	                      LogicalType::VARCHAR, PointFromFunc);

	// Phase 5: Math functions (10)
	RegisterSpecialScalar(loader, "mathAbs", {LogicalType::VARCHAR},
	                      LogicalType::VARCHAR, MathAbsFunc);
	RegisterSpecialScalar(loader, "mathCeiling", {LogicalType::VARCHAR},
	                      LogicalType::VARCHAR, MathCeilingFunc);
	RegisterSpecialScalar(loader, "mathFloor", {LogicalType::VARCHAR},
	                      LogicalType::VARCHAR, MathFloorFunc);
	RegisterSpecialScalar(loader, "mathExp", {LogicalType::VARCHAR},
	                      LogicalType::VARCHAR, MathExpFunc);
	RegisterSpecialScalar(loader, "mathLn", {LogicalType::VARCHAR},
	                      LogicalType::VARCHAR, MathLnFunc);
	RegisterSpecialScalar(loader, "mathLog", {LogicalType::VARCHAR, LogicalType::VARCHAR},
	                      LogicalType::VARCHAR, MathLogFunc);
	RegisterSpecialScalar(loader, "mathPower", {LogicalType::VARCHAR, LogicalType::VARCHAR},
	                      LogicalType::VARCHAR, MathPowerFunc);
	RegisterSpecialScalar(loader, "mathRound", {LogicalType::VARCHAR, LogicalType::VARCHAR},
	                      LogicalType::VARCHAR, MathRoundFunc);
	RegisterSpecialScalar(loader, "mathSqrt", {LogicalType::VARCHAR},
	                      LogicalType::VARCHAR, MathSqrtFunc);
	RegisterSpecialScalar(loader, "mathTruncate", {LogicalType::VARCHAR},
	                      LogicalType::VARCHAR, MathTruncateFunc);

	// Phase 6: Quantity arithmetic UDFs
	RegisterSpecialScalar(loader, "quantityMultiply", {LogicalType::VARCHAR, LogicalType::VARCHAR},
	                      LogicalType::VARCHAR, QuantityMultiplyFunc);
	RegisterSpecialScalar(loader, "quantityDivide", {LogicalType::VARCHAR, LogicalType::VARCHAR},
	                      LogicalType::VARCHAR, QuantityDivideFunc);
	RegisterSpecialScalar(loader, "quantityNegate", {LogicalType::VARCHAR},
	                      LogicalType::VARCHAR, QuantityNegateFunc);
	RegisterSpecialScalar(loader, "quantityAbs", {LogicalType::VARCHAR},
	                      LogicalType::VARCHAR, QuantityAbsFunc);
	RegisterSpecialScalar(loader, "quantityModulo", {LogicalType::VARCHAR, LogicalType::VARCHAR},
	                      LogicalType::VARCHAR, QuantityModuloFunc);
	RegisterSpecialScalar(loader, "quantityTruncatedDivide", {LogicalType::VARCHAR, LogicalType::VARCHAR},
	                      LogicalType::VARCHAR, QuantityTruncatedDivideFunc);
	RegisterSpecialScalar(loader, "ToQuantity", {LogicalType::VARCHAR},
	                      LogicalType::VARCHAR, ToQuantityFunc);
	RegisterSpecialScalar(loader, "ToQuantity", {LogicalType::DOUBLE},
	                      LogicalType::VARCHAR, ToQuantityDoubleFunc);
	RegisterSpecialScalar(loader, "ToQuantity", {LogicalType::BOOLEAN},
	                      LogicalType::VARCHAR, ToQuantityBoolFunc);
	RegisterSpecialScalar(loader, "ToConcept", {LogicalType::VARCHAR},
	                      LogicalType::VARCHAR, ToConceptFunc);
	RegisterSpecialScalar(loader, "ToConcept", {LogicalType::LIST(LogicalType::VARCHAR)},
	                      LogicalType::VARCHAR, ToConceptListFunc);
	RegisterSpecialScalar(loader, "ToConceptFromList", {LogicalType::LIST(LogicalType::VARCHAR)},
	                      LogicalType::VARCHAR, ToConceptListFunc);

	// Phase 7: Logical aggregate UDFs (6)
	RegisterSpecialScalar(loader, "logicalAllTrue", {LogicalType::VARCHAR},
	                      LogicalType::BOOLEAN, LogicalAllTrueFunc);
	RegisterSpecialScalar(loader, "logicalAllTrue", {LogicalType::LIST(LogicalType::BOOLEAN)},
	                      LogicalType::BOOLEAN, LogicalAllTrueBoolListFunc);
	RegisterSpecialScalar(loader, "logicalAnyTrue", {LogicalType::VARCHAR},
	                      LogicalType::BOOLEAN, LogicalAnyTrueFunc);
	RegisterSpecialScalar(loader, "logicalAnyTrue", {LogicalType::LIST(LogicalType::BOOLEAN)},
	                      LogicalType::BOOLEAN, LogicalAnyTrueBoolListFunc);
	RegisterSpecialScalar(loader, "logicalAllFalse", {LogicalType::VARCHAR},
	                      LogicalType::BOOLEAN, LogicalAllFalseFunc);
	RegisterSpecialScalar(loader, "logicalAllFalse", {LogicalType::LIST(LogicalType::BOOLEAN)},
	                      LogicalType::BOOLEAN, LogicalAllFalseBoolListFunc);
	RegisterSpecialScalar(loader, "logicalAnyFalse", {LogicalType::VARCHAR},
	                      LogicalType::BOOLEAN, LogicalAnyFalseFunc);
	RegisterSpecialScalar(loader, "logicalAnyFalse", {LogicalType::LIST(LogicalType::BOOLEAN)},
	                      LogicalType::BOOLEAN, LogicalAnyFalseBoolListFunc);
	RegisterSpecialScalar(loader, "logicalImplies", {LogicalType::VARCHAR, LogicalType::VARCHAR},
	                      LogicalType::BOOLEAN, LogicalImpliesFunc);
	RegisterSpecialScalar(loader, "logicalImplies", {LogicalType::BOOLEAN, LogicalType::BOOLEAN},
	                      LogicalType::BOOLEAN, LogicalImpliesBoolFunc);
	RegisterSpecialScalar(loader, "logicalCoalesce", {LogicalType::VARCHAR},
	                      LogicalType::VARCHAR, LogicalCoalesceFunc);
}

void CqlExtension::Load(ExtensionLoader &loader) {
	LoadInternal(loader);
}

std::string CqlExtension::Name() {
	return "cql";
}

std::string CqlExtension::Version() const {
#ifdef EXT_VERSION_CQL
	return EXT_VERSION_CQL;
#else
	return "0.1.0";
#endif
}

} // namespace duckdb

extern "C" {

DUCKDB_CPP_EXTENSION_ENTRY(cql, loader) {
	duckdb::LoadInternal(loader);
}
}
