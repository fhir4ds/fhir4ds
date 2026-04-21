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
#include <chrono>
#include <mutex>
#include <stdexcept>

namespace duckdb {

// =====================================================================
// Named constants for CQL datetime/duration calculations
// =====================================================================
static const std::string CQL_MIN_DATETIME = "0001-01-01T00:00:00.000+00:00";
static const std::string CQL_MAX_DATETIME = "9999-12-31T23:59:59.999+00:00";

// =====================================================================
// Named constants for time unit conversions (replacing magic numbers)
// =====================================================================
static constexpr int64_t MS_PER_SECOND = 1000LL;
static constexpr int64_t MS_PER_MINUTE = 60000LL;
static constexpr int64_t MS_PER_HOUR = 3600000LL;
static constexpr int64_t MS_PER_DAY = 86400000LL;
static constexpr double DAYS_PER_YEAR = 365.25;
static constexpr double DAYS_PER_MONTH = 30.4375;

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
	auto hours = cql::AgeCalculator::diff_hours(*a_dt, *b_dt);
	if (!hours) {
		result_mask.SetInvalid(i);
	} else {
		result_data[i] = *hours;
	}
})

DEFINE_TWO_STR_BIGINT_UDF(DifferenceInMinutesFunc, {
	auto minutes = cql::AgeCalculator::diff_minutes(*a_dt, *b_dt);
	if (!minutes) {
		result_mask.SetInvalid(i);
	} else {
		result_data[i] = *minutes;
	}
})

DEFINE_TWO_STR_BIGINT_UDF(DifferenceInSecondsFunc, {
	auto seconds = cql::AgeCalculator::diff_seconds(*a_dt, *b_dt);
	if (!seconds) {
		result_mask.SetInvalid(i);
	} else {
		result_data[i] = *seconds;
	}
})

DEFINE_TWO_STR_BIGINT_UDF(WeeksBetweenFunc, {
	auto days_diff = cql::AgeCalculator::diff_days(*a_dt, *b_dt);
	if (!days_diff) {
		result_mask.SetInvalid(i);
	} else {
		result_data[i] = *days_diff / 7;
	}
})

DEFINE_TWO_STR_BIGINT_UDF(MillisecondsBetweenFunc, {
	result_data[i] = b_dt->to_epoch_millis() - a_dt->to_epoch_millis();
})

// date_diff equivalents (match Python's DaysBetween/MonthsBetween/etc. macros)
DEFINE_TWO_STR_BIGINT_UDF(YearsBetweenFunc, {
	result_data[i] = b_dt->year - a_dt->year;
})

DEFINE_TWO_STR_BIGINT_UDF(MonthsBetweenFunc, {
	result_data[i] = (b_dt->year - a_dt->year) * 12 + (b_dt->month - a_dt->month);
})

DEFINE_TWO_STR_BIGINT_UDF(DaysBetweenFunc, {
	result_data[i] = b_dt->to_julian_day() - a_dt->to_julian_day();
})

DEFINE_TWO_STR_BIGINT_UDF(HoursBetweenFunc, {
	result_data[i] = (b_dt->to_epoch_millis() - a_dt->to_epoch_millis()) / MS_PER_HOUR;
})

DEFINE_TWO_STR_BIGINT_UDF(MinutesBetweenFunc, {
	result_data[i] = (b_dt->to_epoch_millis() - a_dt->to_epoch_millis()) / MS_PER_MINUTE;
})

DEFINE_TWO_STR_BIGINT_UDF(SecondsBetweenFunc, {
	result_data[i] = (b_dt->to_epoch_millis() - a_dt->to_epoch_millis()) / MS_PER_SECOND;
})

// =====================================================================
// Interval UDFs
// =====================================================================
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
				result_data[i] = StringVector::AddString(result, CQL_MIN_DATETIME);
			} else {
				result_mask.SetInvalid(i);
			}
		} else {
			result_data[i] = StringVector::AddString(result, iv->low->to_string());
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
				result_data[i] = StringVector::AddString(result, CQL_MAX_DATETIME);
			} else {
				result_mask.SetInvalid(i);
			}
		} else {
			result_data[i] = StringVector::AddString(result, iv->high->to_string());
		}
	}
}

static void IntervalWidthFunc(DataChunk &args, ExpressionState &state, Vector &result) {
	idx_t count = args.size();
	UnifiedVectorFormat iv_data;
	args.data[0].ToUnifiedFormat(count, iv_data);
	auto intervals = UnifiedVectorFormat::GetData<string_t>(iv_data);

	result.SetVectorType(VectorType::FLAT_VECTOR);
	auto result_data = FlatVector::GetData<int64_t>(result);
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
		auto width = iv->width_days();
		if (!width) {
			result_mask.SetInvalid(i);
		} else {
			result_data[i] = *width;
		}
	}
}

DEFINE_TWO_STR_BOOL_UDF(IntervalContainsFunc, {
	auto iv = cql::Interval::parse(a_str);
	if (!iv) {
		result_data[i] = false;
		continue;
	}
	if (cql::is_json_interval(b_str)) {
		auto other = cql::Interval::parse(b_str);
		result_data[i] = other ? iv->includes(*other) : false;
	} else {
		auto point = cql::parse_point_value(b_str);
		result_data[i] = point ? iv->contains_point(*point) : false;
	}
})

DEFINE_TWO_STR_BOOL_UDF(IntervalProperlyContainsFunc, {
	auto iv = cql::Interval::parse(a_str);
	if (!iv) {
		result_data[i] = false;
		continue;
	}
	if (cql::is_json_interval(b_str)) {
		auto other = cql::Interval::parse(b_str);
		result_data[i] = other ? iv->properly_includes(*other) : false;
	} else {
		auto point = cql::parse_point_value(b_str);
		result_data[i] = point ? iv->properly_contains_point(*point) : false;
	}
})

DEFINE_TWO_STR_BOOL_UDF(IntervalOverlapsFunc, {
	auto iv1 = cql::Interval::parse(a_str);
	auto iv2 = cql::Interval::parse(b_str);
	result_data[i] = (iv1 && iv2) ? iv1->overlaps(*iv2) : false;
})

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
	result_data[i] = (iv1 && iv2) ? iv2->includes(*iv1) : false;
})

DEFINE_TWO_STR_BOOL_UDF(IntervalProperlyIncludesFunc, {
	auto iv1 = cql::Interval::parse(a_str);
	auto iv2 = cql::Interval::parse(b_str);
	result_data[i] = (iv1 && iv2) ? iv1->properly_includes(*iv2) : false;
})

DEFINE_TWO_STR_BOOL_UDF(IntervalProperlyIncludedInFunc, {
	auto iv1 = cql::Interval::parse(a_str);
	auto iv2 = cql::Interval::parse(b_str);
	result_data[i] = (iv1 && iv2) ? iv2->properly_includes(*iv1) : false;
})

DEFINE_TWO_STR_BOOL_UDF(IntervalOverlapsBeforeFunc, {
	auto iv1 = cql::Interval::parse(a_str);
	auto iv2 = cql::Interval::parse(b_str);
	result_data[i] = (iv1 && iv2) ? iv1->overlaps_before(*iv2) : false;
})

DEFINE_TWO_STR_BOOL_UDF(IntervalOverlapsAfterFunc, {
	auto iv1 = cql::Interval::parse(a_str);
	auto iv2 = cql::Interval::parse(b_str);
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
	result_data[i] = (iv1 && iv2) ? iv1->starts_same(*iv2) : false;
})

DEFINE_TWO_STR_BOOL_UDF(IntervalEndsSameFunc, {
	auto iv1 = cql::Interval::parse(a_str);
	auto iv2 = cql::Interval::parse(b_str);
	result_data[i] = (iv1 && iv2) ? iv1->ends_same(*iv2) : false;
})

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
		if (low_data.validity.RowIsValid(l_idx)) {
			iv.low = cql::BoundValue::from_string(lows[l_idx].GetString());
		}
		if (high_data.validity.RowIsValid(h_idx)) {
			iv.high = cql::BoundValue::from_string(highs[h_idx].GetString());
		}
		iv.low_closed = lc_data.validity.RowIsValid(lc_idx) ? lcs[lc_idx] : true;
		iv.high_closed = hc_data.validity.RowIsValid(hc_idx) ? hcs[hc_idx] : true;
		if (iv.low) {
			iv.bound_type = iv.low->type;
		} else if (iv.high) {
			iv.bound_type = iv.high->type;
		}

		if (!iv.low && !iv.high) {
			result_mask.SetInvalid(i);
		} else {
			result_data[i] = StringVector::AddString(result, iv.to_json());
		}
	}
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

	for (idx_t i = 0; i < count; i++) {
		auto r_idx = res_data.sel->get_index(i);
		auto p_idx = path_data.sel->get_index(i);
		auto u_idx = url_data.sel->get_index(i);

		if (!res_data.validity.RowIsValid(r_idx) || !path_data.validity.RowIsValid(p_idx) ||
		    !url_data.validity.RowIsValid(u_idx)) {
			result_mask.SetInvalid(i);
			continue;
		}

		auto resource_str = resources[r_idx].GetString();
		auto path_str = paths[p_idx].GetString();
		auto url_str = urls[u_idx].GetString();

		auto codes = cql::extract_codes(resource_str, path_str);
		if (codes.empty()) {
			// No code found in resource → NULL (not false)
			result_mask.SetInvalid(i);
			continue;
		}
		bool found = false;
		{
			std::lock_guard<std::mutex> lock(g_valueset_cache_mutex);
			for (const auto &code : codes) {
				if (cql::in_valueset(code.code, code.system, url_str, g_valueset_cache)) {
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
	}
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

		auto dt = cql::DateTimeValue::parse(dates[d_idx].GetString());
		if (!dt) {
			result_mask.SetInvalid(i);
			continue;
		}

		std::string component = comps[c_idx].GetString();
		if (component == "year") {
			result_data[i] = dt->year;
		} else if (component == "month") {
			result_data[i] = dt->month;
		} else if (component == "day") {
			result_data[i] = dt->day;
		} else if (component == "hour") {
			result_data[i] = dt->has_time ? dt->hour : 0;
		} else if (component == "minute") {
			result_data[i] = dt->has_time ? dt->minute : 0;
		} else if (component == "second") {
			result_data[i] = dt->has_time ? dt->second : 0;
		} else if (component == "millisecond") {
			result_data[i] = dt->has_time ? dt->millisecond : 0;
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
	snprintf(buf, sizeof(buf), "%02d:%02d:%02d", tm_buf.tm_hour, tm_buf.tm_min, tm_buf.tm_sec);
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
		double value = parsed.has_value() ? parsed->value : 0;
		std::string unit = parsed.has_value() ? parsed->code : "";

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

		auto dt = cql::DateTimeValue::parse(dates[d_idx].GetString());
		if (!dt) {
			result_mask.SetInvalid(i);
			continue;
		}

		std::string q_str = quantities[q_idx].GetString();
		auto parsed = cql::parse_quantity_json(q_str);
		double value = parsed.has_value() ? parsed->value : 0;
		std::string unit = parsed.has_value() ? parsed->code : "";

		cql::DateTimeValue new_dt;
		int32_t int_value = static_cast<int32_t>(value);
		if (unit == "a" || unit == "year" || unit == "years") {
			new_dt = AddYears(*dt, int_value);
		} else if (unit == "mo" || unit == "month" || unit == "months") {
			new_dt = AddMonths(*dt, int_value);
		} else if (IsSubDayUnit(unit)) {
			int64_t millis = QuantityToMillis(value, unit);
			new_dt = AddMilliseconds(*dt, millis);
		} else {
			int64_t days = QuantityToDays(value, unit);
			new_dt = AddDays(*dt, days);
		}
		result_data[i] = StringVector::AddString(result, new_dt.to_string());
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

		auto dt = cql::DateTimeValue::parse(dates[d_idx].GetString());
		if (!dt) {
			result_mask.SetInvalid(i);
			continue;
		}

		std::string q_str = quantities[q_idx].GetString();
		auto parsed = cql::parse_quantity_json(q_str);
		double value = parsed.has_value() ? parsed->value : 0;
		std::string unit = parsed.has_value() ? parsed->code : "";

		cql::DateTimeValue new_dt;
		int32_t int_value = static_cast<int32_t>(value);
		if (unit == "a" || unit == "year" || unit == "years") {
			new_dt = AddYears(*dt, -int_value);
		} else if (unit == "mo" || unit == "month" || unit == "months") {
			new_dt = AddMonths(*dt, -int_value);
		} else if (IsSubDayUnit(unit)) {
			int64_t millis = QuantityToMillis(value, unit);
			new_dt = AddMilliseconds(*dt, -millis);
		} else {
			int64_t days = QuantityToDays(value, unit);
			new_dt = AddDays(*dt, -days);
		}
		result_data[i] = StringVector::AddString(result, new_dt.to_string());
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

			bool can_merge = false;
			if (current.high && next.low) {
				int cmp = current.high->compare(*next.low);
				if (cmp >= 0) {
					can_merge = true;
				} else if (cmp == 0 && (current.high_closed || next.low_closed)) {
					can_merge = true;
				}
			} else if (!current.high) {
				can_merge = true;
			}

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
			// >1 element: return NULL per CQL spec
			result_mask.SetInvalid(i);
			continue;
		}

		auto child_idx = child_data.sel->get_index(entry.offset);
		if (!child_data.validity.RowIsValid(child_idx)) {
			result_mask.SetInvalid(i);
			continue;
		}
		result_data[i] = StringVector::AddString(result, child_vals[child_idx]);
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
	auto res = cql::high_boundary(a_str, 17);
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
	auto res = cql::low_boundary(a_str, 17);
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
		result_data[i] = static_cast<int64_t>(*res);
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
	if (!iv->low || !iv->high) { result_mask.SetInvalid(i); continue; }
	if (!iv->low_closed || !iv->high_closed) { result_mask.SetInvalid(i); continue; }
	int cmp = iv->low->compare(*iv->high);
	if (cmp != 0) { result_mask.SetInvalid(i); continue; }
	result_data[i] = StringVector::AddString(result, iv->low->to_string());
})

// =====================================================================
// Math UDFs
// =====================================================================
DEFINE_TWO_STR_STR_UDF(MathRoundFunc, {
	auto res = cql::math_round(a_str, b_str);
	if (!res) { result_mask.SetInvalid(i); continue; }
	result_data[i] = StringVector::AddString(result, *res);
})

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

DEFINE_ONE_STR_STR_UDF(ToConceptFunc, {
	auto res = cql::to_concept(a_str);
	if (!res) { result_mask.SetInvalid(i); continue; }
	result_data[i] = StringVector::AddString(result, *res);
})

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
			std::string s = a_strings[a_idx].GetString();
			a_val = (s == "true");
		}
		if (!b_null) {
			std::string s = b_strings[b_idx].GetString();
			b_val = (s == "true");
		}

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
	// Age UDFs (9)
	RegisterSpecialScalar(loader, "AgeInYears", {LogicalType::VARCHAR}, LogicalType::BIGINT, AgeInYearsFunc);
	RegisterSpecialScalar(loader, "AgeInMonths", {LogicalType::VARCHAR}, LogicalType::BIGINT, AgeInMonthsFunc);
	RegisterSpecialScalar(loader, "AgeInDays", {LogicalType::VARCHAR}, LogicalType::BIGINT, AgeInDaysFunc);
	RegisterSpecialScalar(loader, "AgeInHours", {LogicalType::VARCHAR}, LogicalType::BIGINT, AgeInHoursFunc);
	RegisterSpecialScalar(loader, "AgeInMinutes", {LogicalType::VARCHAR}, LogicalType::BIGINT, AgeInMinutesFunc);
	RegisterSpecialScalar(loader, "AgeInSeconds", {LogicalType::VARCHAR}, LogicalType::BIGINT, AgeInSecondsFunc);
	RegisterSpecialScalar(loader, "AgeInYearsAt", {LogicalType::VARCHAR, LogicalType::VARCHAR}, LogicalType::BIGINT,
	                      AgeInYearsAtFunc);
	RegisterSpecialScalar(loader, "AgeInMonthsAt", {LogicalType::VARCHAR, LogicalType::VARCHAR}, LogicalType::BIGINT,
	                      AgeInMonthsAtFunc);
	RegisterSpecialScalar(loader, "AgeInDaysAt", {LogicalType::VARCHAR, LogicalType::VARCHAR}, LogicalType::BIGINT,
	                      AgeInDaysAtFunc);

	// Interval UDFs (22 — includes collapse_intervals)
	RegisterSpecialScalar(loader, "intervalStart", {LogicalType::VARCHAR}, LogicalType::VARCHAR, IntervalStartFunc);
	RegisterSpecialScalar(loader, "intervalEnd", {LogicalType::VARCHAR}, LogicalType::VARCHAR, IntervalEndFunc);
	RegisterSpecialScalar(loader, "intervalWidth", {LogicalType::VARCHAR}, LogicalType::BIGINT, IntervalWidthFunc);
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
	RegisterSpecialScalar(loader, "intervalFromBounds",
	                      {LogicalType::VARCHAR, LogicalType::VARCHAR, LogicalType::BOOLEAN, LogicalType::BOOLEAN},
	                      LogicalType::VARCHAR, IntervalFromBoundsFunc);
	RegisterSpecialScalar(loader, "collapse_intervals", {LogicalType::VARCHAR}, LogicalType::VARCHAR,
	                      CollapseIntervalsFunc);

	// Datetime UDFs (24)
	RegisterSpecialScalar(loader, "differenceInYears", {LogicalType::VARCHAR, LogicalType::VARCHAR},
	                      LogicalType::BIGINT, DifferenceInYearsFunc);
	RegisterSpecialScalar(loader, "differenceInMonths", {LogicalType::VARCHAR, LogicalType::VARCHAR},
	                      LogicalType::BIGINT, DifferenceInMonthsFunc);
	RegisterSpecialScalar(loader, "differenceInDays", {LogicalType::VARCHAR, LogicalType::VARCHAR},
	                      LogicalType::BIGINT, DifferenceInDaysFunc);
	RegisterSpecialScalar(loader, "differenceInHours", {LogicalType::VARCHAR, LogicalType::VARCHAR},
	                      LogicalType::BIGINT, DifferenceInHoursFunc);
	RegisterSpecialScalar(loader, "differenceInMinutes", {LogicalType::VARCHAR, LogicalType::VARCHAR},
	                      LogicalType::BIGINT, DifferenceInMinutesFunc);
	RegisterSpecialScalar(loader, "differenceInSeconds", {LogicalType::VARCHAR, LogicalType::VARCHAR},
	                      LogicalType::BIGINT, DifferenceInSecondsFunc);
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
	                      DateTimeSameAsFunc);
	RegisterSpecialScalar(loader, "dateTimeSameOrBefore",
	                      {LogicalType::VARCHAR, LogicalType::VARCHAR, LogicalType::VARCHAR}, LogicalType::BOOLEAN,
	                      DateTimeSameOrBeforeFunc);
	RegisterSpecialScalar(loader, "dateTimeSameOrAfter",
	                      {LogicalType::VARCHAR, LogicalType::VARCHAR, LogicalType::VARCHAR}, LogicalType::BOOLEAN,
	                      DateTimeSameOrAfterFunc);
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

	// Ratio UDFs (5)
	RegisterSpecialScalar(loader, "ratioNumeratorValue", {LogicalType::VARCHAR}, LogicalType::DOUBLE,
	                      RatioNumeratorValueFunc);
	RegisterSpecialScalar(loader, "ratioDenominatorValue", {LogicalType::VARCHAR}, LogicalType::DOUBLE,
	                      RatioDenominatorValueFunc);
	RegisterSpecialScalar(loader, "ratioValue", {LogicalType::VARCHAR}, LogicalType::DOUBLE, RatioValueFunc);
	RegisterSpecialScalar(loader, "ratioNumeratorUnit", {LogicalType::VARCHAR}, LogicalType::VARCHAR,
	                      RatioNumeratorUnitFunc);
	RegisterSpecialScalar(loader, "ratioDenominatorUnit", {LogicalType::VARCHAR}, LogicalType::VARCHAR,
	                      RatioDenominatorUnitFunc);

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
	RegisterSpecialScalar(loader, "ElementAt", {LogicalType::LIST(LogicalType::VARCHAR), LogicalType::BIGINT},
	                      LogicalType::VARCHAR, ElementAtFunc);
	RegisterSpecialScalar(loader, "jsonConcat", {LogicalType::VARCHAR, LogicalType::VARCHAR},
	                      LogicalType::LIST(LogicalType::VARCHAR), JsonConcatFunc);

	// Boundary UDFs (6 new)
	RegisterSpecialScalar(loader, "HighBoundary", {LogicalType::VARCHAR, LogicalType::BIGINT},
	                      LogicalType::VARCHAR, HighBoundaryFunc2);
	RegisterSpecialScalar(loader, "LowBoundary", {LogicalType::VARCHAR, LogicalType::BIGINT},
	                      LogicalType::VARCHAR, LowBoundaryFunc2);
	RegisterSpecialScalar(loader, "predecessorOf", {LogicalType::VARCHAR},
	                      LogicalType::VARCHAR, PredecessorOfFunc);
	RegisterSpecialScalar(loader, "successorOf", {LogicalType::VARCHAR},
	                      LogicalType::VARCHAR, SuccessorOfFunc);
	RegisterSpecialScalar(loader, "CQLPrecision", {LogicalType::VARCHAR},
	                      LogicalType::BIGINT, CQLPrecisionFunc);
	RegisterSpecialScalar(loader, "cqlTimezoneOffset", {LogicalType::VARCHAR},
	                      LogicalType::DOUBLE, CQLTimezoneOffsetFunc);

	// Interval set operations (5 new)
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

	// Phase 4: pointFrom + diff aliases
	RegisterSpecialScalar(loader, "pointFrom", {LogicalType::VARCHAR},
	                      LogicalType::VARCHAR, PointFromFunc);
	RegisterSpecialScalar(loader, "differenceInWeeks", {LogicalType::VARCHAR, LogicalType::VARCHAR},
	                      LogicalType::BIGINT, WeeksBetweenFunc);
	RegisterSpecialScalar(loader, "differenceInMilliseconds", {LogicalType::VARCHAR, LogicalType::VARCHAR},
	                      LogicalType::BIGINT, MillisecondsBetweenFunc);

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

	// Phase 6: Quantity arithmetic UDFs (8)
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
	RegisterSpecialScalar(loader, "ToConcept", {LogicalType::VARCHAR},
	                      LogicalType::VARCHAR, ToConceptFunc);

	// Phase 7: Logical aggregate UDFs (6)
	RegisterSpecialScalar(loader, "logicalAllTrue", {LogicalType::VARCHAR},
	                      LogicalType::BOOLEAN, LogicalAllTrueFunc);
	RegisterSpecialScalar(loader, "logicalAnyTrue", {LogicalType::VARCHAR},
	                      LogicalType::BOOLEAN, LogicalAnyTrueFunc);
	RegisterSpecialScalar(loader, "logicalAllFalse", {LogicalType::VARCHAR},
	                      LogicalType::BOOLEAN, LogicalAllFalseFunc);
	RegisterSpecialScalar(loader, "logicalAnyFalse", {LogicalType::VARCHAR},
	                      LogicalType::BOOLEAN, LogicalAnyFalseFunc);
	RegisterSpecialScalar(loader, "logicalImplies", {LogicalType::VARCHAR, LogicalType::VARCHAR},
	                      LogicalType::BOOLEAN, LogicalImpliesFunc);
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
