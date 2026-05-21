#include "cql/quantity.hpp"
#include "yyjson.hpp"

// Shared UCUM conversion table (canonical source in duckdb-fhirpath-cpp)
#include "shared/ucum_units.hpp"

using namespace duckdb_yyjson; // NOLINT

#include <cmath>
#include <cctype>
#include <cstdlib>
#include <unordered_map>

namespace cql {

// Alias the shared table for local use
static const std::unordered_map<std::string, fhir::UnitConversion> &GetUnitTable() {
	return fhir::GetUcumUnitTable();
}

static bool is_cql_calendar_duration_unit(const std::string &unit) {
	return unit == "year" || unit == "years" ||
	       unit == "month" || unit == "months" ||
	       unit == "week" || unit == "weeks" ||
	       unit == "day" || unit == "days" ||
	       unit == "hour" || unit == "hours" ||
	       unit == "minute" || unit == "minutes" ||
	       unit == "second" || unit == "seconds" ||
	       unit == "millisecond" || unit == "milliseconds";
}

bool is_valid_quantity_unit(const std::string &unit) {
	if (unit == "1" || is_cql_calendar_duration_unit(unit)) {
		return true;
	}
	const auto &table = GetUnitTable();
	return table.find(unit) != table.end();
}

// Convert value from source unit to base unit
static Optional<double> to_base(double value, const std::string &unit) {
	const auto &table = GetUnitTable();
	auto it = table.find(unit);
	if (it == table.end()) {
		return NullOpt<double>();
	}

	// Special handling for temperature
	if (unit == "[degF]" || unit == "degF") {
		return (value - 32.0) * 5.0 / 9.0; // Fahrenheit to Celsius
	}

	return value * it->second.factor;
}

// Convert value from base unit to target unit
static Optional<double> from_base(double base_value, const std::string &target_unit) {
	const auto &table = GetUnitTable();
	auto it = table.find(target_unit);
	if (it == table.end()) {
		return NullOpt<double>();
	}

	// Special handling for temperature
	if (target_unit == "[degF]" || target_unit == "degF") {
		return base_value * 9.0 / 5.0 + 32.0; // Celsius to Fahrenheit
	}

	if (it->second.factor == 0.0) {
		return NullOpt<double>();
	}
	return base_value / it->second.factor;
}

// Get the base unit for a given unit code
static Optional<std::string> get_base_unit(const std::string &unit) {
	const auto &table = GetUnitTable();
	auto it = table.find(unit);
	if (it == table.end()) {
		return NullOpt<std::string>();
	}
	return it->second.base_unit;
}

// Check if two units are compatible (same base unit)
static bool units_compatible(const std::string &u1, const std::string &u2) {
	auto b1 = get_base_unit(u1);
	auto b2 = get_base_unit(u2);
	if (!b1.has_value() || !b2.has_value()) {
		return false;
	}
	return b1.value() == b2.value();
}

static Optional<std::string> most_granular_compatible_unit(const std::string &u1, const std::string &u2) {
	if (u1 == u2) {
		return Optional<std::string>(u1);
	}
	const auto &table = GetUnitTable();
	auto it1 = table.find(u1);
	auto it2 = table.find(u2);
	if (it1 == table.end() || it2 == table.end()) {
		return NullOpt<std::string>();
	}
	if (it1->second.base_unit != it2->second.base_unit) {
		return NullOpt<std::string>();
	}
	return Optional<std::string>((std::fabs(it1->second.factor) <= std::fabs(it2->second.factor)) ? u1 : u2);
}

static bool calendar_month_factor(const std::string &unit, double &factor) {
	if (unit == "year" || unit == "years") {
		factor = 12.0;
		return true;
	}
	if (unit == "month" || unit == "months") {
		factor = 1.0;
		return true;
	}
	return false;
}

static bool equivalent_duration_day_factor(const std::string &unit, double &factor) {
	if (unit == "year" || unit == "years" || unit == "a") {
		factor = 365.0;
		return true;
	}
	if (unit == "month" || unit == "months" || unit == "mo") {
		factor = 30.0;
		return true;
	}
	if (unit == "week" || unit == "weeks" || unit == "wk") {
		factor = 7.0;
		return true;
	}
	if (unit == "day" || unit == "days" || unit == "d") {
		factor = 1.0;
		return true;
	}
	if (unit == "hour" || unit == "hours" || unit == "h") {
		factor = 1.0 / 24.0;
		return true;
	}
	if (unit == "minute" || unit == "minutes" || unit == "min") {
		factor = 1.0 / 1440.0;
		return true;
	}
	if (unit == "second" || unit == "seconds" || unit == "s") {
		factor = 1.0 / 86400.0;
		return true;
	}
	if (unit == "millisecond" || unit == "milliseconds" || unit == "ms") {
		factor = 1.0 / 86400000.0;
		return true;
	}
	return false;
}

static bool definite_duration_day_factor(const std::string &unit, double &factor) {
	if (unit == "year" || unit == "years" || unit == "a" || unit == "month" || unit == "months" || unit == "mo") {
		return false;
	}
	return equivalent_duration_day_factor(unit, factor);
}

static Optional<bool> apply_quantity_compare(double v1, double v2, const std::string &op) {
	if (op == ">") return v1 > v2;
	if (op == "<") return v1 < v2;
	if (op == ">=") return v1 >= v2;
	if (op == "<=") return v1 <= v2;
	if (op == "==" || op == "~") return v1 == v2;
	if (op == "!=" || op == "!~") return v1 != v2;
	return NullOpt<bool>();
}

static double round_for_equivalence(double value, int precision) {
	double scale = std::pow(10.0, static_cast<double>(precision));
	if (value >= 0.0) {
		return std::floor(value * scale + 0.5) / scale;
	}
	return std::ceil(value * scale - 0.5) / scale;
}

static Optional<bool> apply_quantity_compare(const ParsedQuantity &q1, double v1,
                                             const ParsedQuantity &q2, double v2,
                                             const std::string &op) {
	if (op == "~" || op == "!~") {
		int precision = q1.precision < q2.precision ? q1.precision : q2.precision;
		bool equivalent = round_for_equivalence(v1, precision) == round_for_equivalence(v2, precision);
		return op == "~" ? equivalent : !equivalent;
	}
	return apply_quantity_compare(v1, v2, op);
}

static Optional<bool> compare_cql_duration_quantities(const ParsedQuantity &q1, const ParsedQuantity &q2,
                                                      const std::string &code1, const std::string &code2,
                                                      const std::string &op, bool &applicable) {
	double f1 = 0.0;
	double f2 = 0.0;
	bool d1 = equivalent_duration_day_factor(code1, f1);
	bool d2 = equivalent_duration_day_factor(code2, f2);
	applicable = d1 || d2;
	if (!applicable) {
		return NullOpt<bool>();
	}
	if (!d1 || !d2) {
		return NullOpt<bool>();
	}

	if (op == "~" || op == "!~") {
		return apply_quantity_compare(q1, q1.value * f1, q2, q2.value * f2, op);
	}

	double m1 = 0.0;
	double m2 = 0.0;
	bool c1 = calendar_month_factor(code1, m1);
	bool c2 = calendar_month_factor(code2, m2);
	if (c1 || c2) {
		if (c1 && c2) {
			return apply_quantity_compare(q1, q1.value * m1, q2, q2.value * m2, op);
		}
		return NullOpt<bool>();
	}

	bool def1 = definite_duration_day_factor(code1, f1);
	bool def2 = definite_duration_day_factor(code2, f2);
	if (def1 && def2) {
		return apply_quantity_compare(q1, q1.value * f1, q2, q2.value * f2, op);
	}
	return NullOpt<bool>();
}

static std::string pint_display_unit(const std::string &unit) {
	if (unit == "m") return "meter";
	if (unit == "s") return "second";
	return unit;
}

// =====================================================================
// JSON parsing
// =====================================================================

static int extract_value_precision(const std::string &json) {
	size_t key = json.find("\"value\"");
	if (key == std::string::npos) {
		return 0;
	}
	size_t colon = json.find(':', key);
	if (colon == std::string::npos) {
		return 0;
	}
	size_t pos = colon + 1;
	while (pos < json.size() && std::isspace(static_cast<unsigned char>(json[pos]))) {
		pos++;
	}
	if (pos < json.size() && (json[pos] == '-' || json[pos] == '+')) {
		pos++;
	}
	while (pos < json.size() && std::isdigit(static_cast<unsigned char>(json[pos]))) {
		pos++;
	}
	if (pos >= json.size() || json[pos] != '.') {
		return 0;
	}
	pos++;
	int precision = 0;
	while (pos < json.size() && std::isdigit(static_cast<unsigned char>(json[pos]))) {
		precision++;
		pos++;
	}
	size_t end = pos;
	while (precision > 0 && end > 0 && json[end - 1] == '0') {
		precision--;
		end--;
	}
	return precision;
}

Optional<ParsedQuantity> parse_quantity_json(const std::string &json) {
	yyjson_doc *doc = yyjson_read(json.c_str(), json.size(), 0);
	if (!doc) {
		return NullOpt<ParsedQuantity>();
	}

	yyjson_val *root = yyjson_doc_get_root(doc);
	if (!root || !yyjson_is_obj(root)) {
		yyjson_doc_free(doc);
		return NullOpt<ParsedQuantity>();
	}

	// Extract value
	yyjson_val *val = yyjson_obj_get(root, "value");
	if (!val) {
		yyjson_doc_free(doc);
		return NullOpt<ParsedQuantity>();
	}

	double value;
	if (yyjson_is_real(val)) {
		value = yyjson_get_real(val);
	} else if (yyjson_is_int(val)) {
		value = static_cast<double>(yyjson_get_int(val));
		} else {
			yyjson_doc_free(doc);
			return NullOpt<ParsedQuantity>();
		}
		if (!std::isfinite(value)) {
			yyjson_doc_free(doc);
			return NullOpt<ParsedQuantity>();
		}

	// Extract code (try "code" then "unit")
	std::string code;
	yyjson_val *code_val = yyjson_obj_get(root, "code");
	if (code_val && yyjson_is_str(code_val)) {
		code = yyjson_get_str(code_val);
	} else {
		yyjson_val *unit_val = yyjson_obj_get(root, "unit");
		if (unit_val && yyjson_is_str(unit_val)) {
			code = yyjson_get_str(unit_val);
		}
	}

	// Extract system
	std::string system = "http://unitsofmeasure.org";
	yyjson_val *sys_val = yyjson_obj_get(root, "system");
	if (sys_val && yyjson_is_str(sys_val)) {
		system = yyjson_get_str(sys_val);
	}

	int precision = extract_value_precision(json);

	yyjson_doc_free(doc);
	return ParsedQuantity{value, code, system, precision};
}

Optional<std::string> format_quantity_json(const ParsedQuantity &q) {
	yyjson_mut_doc *doc = yyjson_mut_doc_new(nullptr);
	if (!doc) {
		return NullOpt<std::string>();
	}
	yyjson_mut_val *root = yyjson_mut_obj(doc);
	if (!root) {
		yyjson_mut_doc_free(doc);
		return NullOpt<std::string>();
	}
	yyjson_mut_doc_set_root(doc, root);

	yyjson_mut_obj_add_real(doc, root, "value", q.value);
	yyjson_mut_obj_add_strcpy(doc, root, "unit", q.code.c_str());
	yyjson_mut_obj_add_strcpy(doc, root, "code", q.code.c_str());
	yyjson_mut_obj_add_strcpy(doc, root, "system", q.system.c_str());

	char *json_str = yyjson_mut_write(doc, 0, nullptr);
	if (!json_str) {
		yyjson_mut_doc_free(doc);
		return NullOpt<std::string>();
	}
	std::string result(json_str);
	free(json_str);
	yyjson_mut_doc_free(doc);
	return result;
}

// =====================================================================
// Public API
// =====================================================================

Optional<double> quantity_value_fn(const std::string &json) {
	auto q = parse_quantity_json(json);
	if (!q.has_value()) {
		return NullOpt<double>();
	}
	return q->value;
}

Optional<std::string> quantity_unit_fn(const std::string &json) {
	auto q = parse_quantity_json(json);
	if (!q.has_value()) {
		return NullOpt<std::string>();
	}
	if (q->code.empty()) {
		return NullOpt<std::string>();
	}
	return q->code;
}

Optional<bool> quantity_compare(const std::string &q1_json, const std::string &q2_json, const std::string &op) {
	auto q1 = parse_quantity_json(q1_json);
	auto q2 = parse_quantity_json(q2_json);
	if (!q1.has_value() || !q2.has_value()) {
		return NullOpt<bool>();
	}

	// Same unit: direct comparison
	double v1, v2;
	// Normalize empty code to "1" (dimensionless) for comparison
	std::string code1 = q1->code.empty() ? "1" : q1->code;
	std::string code2 = q2->code.empty() ? "1" : q2->code;
	bool duration_applicable = false;
	auto duration_result = compare_cql_duration_quantities(*q1, *q2, code1, code2, op, duration_applicable);
	if (duration_applicable) {
		return duration_result;
	}
	if (code1 == code2) {
		v1 = q1->value;
		v2 = q2->value;
	} else {
		// Convert both to base units
		if (!units_compatible(code1, code2)) {
			return NullOpt<bool>();
		}
		auto b1 = to_base(q1->value, code1);
		auto b2 = to_base(q2->value, code2);
		if (!b1.has_value() || !b2.has_value()) {
			return NullOpt<bool>();
		}
		v1 = b1.value();
		v2 = b2.value();
	}

	return apply_quantity_compare(*q1, v1, *q2, v2, op);
}

Optional<std::string> quantity_add(const std::string &q1_json, const std::string &q2_json) {
	auto q1 = parse_quantity_json(q1_json);
	auto q2 = parse_quantity_json(q2_json);
	if (!q1.has_value() || !q2.has_value()) {
		return NullOpt<std::string>();
	}

	std::string code1 = q1->code.empty() ? "1" : q1->code;
	std::string code2 = q2->code.empty() ? "1" : q2->code;
	auto result_code = most_granular_compatible_unit(code1, code2);
	if (!result_code.has_value()) {
		return NullOpt<std::string>();
	}
	if (code1 == code2) {
		return format_quantity_json({q1->value + q2->value, result_code.value(), q1->system});
	}

	auto b1 = to_base(q1->value, code1);
	auto b2 = to_base(q2->value, code2);
	auto v1 = b1.has_value() ? from_base(b1.value(), result_code.value()) : NullOpt<double>();
	auto v2 = b2.has_value() ? from_base(b2.value(), result_code.value()) : NullOpt<double>();
	if (!v1.has_value() || !v2.has_value()) {
		return NullOpt<std::string>();
	}

	return format_quantity_json({v1.value() + v2.value(), result_code.value(), q1->system});
}

Optional<std::string> quantity_subtract(const std::string &q1_json, const std::string &q2_json) {
	auto q1 = parse_quantity_json(q1_json);
	auto q2 = parse_quantity_json(q2_json);
	if (!q1.has_value() || !q2.has_value()) {
		return NullOpt<std::string>();
	}

	// Same unit: simple subtract (normalize empty code to "1")
	std::string code1 = q1->code.empty() ? "1" : q1->code;
	std::string code2 = q2->code.empty() ? "1" : q2->code;
	if (code1 == code2) {
		return format_quantity_json({q1->value - q2->value, code1, q1->system});
	}

	// Convert q2 to q1's units
	if (!units_compatible(code1, code2)) {
		return NullOpt<std::string>();
	}
	auto b2 = to_base(q2->value, code2);
	auto converted = b2.has_value() ? from_base(b2.value(), code1) : NullOpt<double>();
	if (!converted.has_value()) {
		return NullOpt<std::string>();
	}

	return format_quantity_json({q1->value - converted.value(), q1->code, q1->system});
}

Optional<std::string> quantity_convert(const std::string &q_json, const std::string &target_unit) {
	auto q = parse_quantity_json(q_json);
	if (!q.has_value()) {
		return NullOpt<std::string>();
	}

	// Same unit: no conversion needed
	if (q->code == target_unit) {
		return format_quantity_json(q.value());
	}

	if (!units_compatible(q->code, target_unit)) {
		return NullOpt<std::string>();
	}

	auto base_val = to_base(q->value, q->code);
	if (!base_val.has_value()) {
		return NullOpt<std::string>();
	}

	auto converted = from_base(base_val.value(), target_unit);
	if (!converted.has_value()) {
		return NullOpt<std::string>();
	}

	return format_quantity_json({converted.value(), target_unit, q->system});
}

// =====================================================================
// Phase 6: New quantity operations
// =====================================================================

Optional<std::string> quantity_multiply(const std::string &q1_json, const std::string &q2_json) {
	auto q1 = parse_quantity_json(q1_json);
	auto q2 = parse_quantity_json(q2_json);
	if (!q1 || !q2) return NullOpt<std::string>();

	// Normalize empty code to "1" (dimensionless)
	std::string code1 = q1->code.empty() ? "1" : q1->code;
	std::string code2 = q2->code.empty() ? "1" : q2->code;

	ParsedQuantity result;
	result.value = q1->value * q2->value;
	if (code1 == "1") {
		result.code = code2;
	} else if (code2 == "1") {
		result.code = code1;
	} else if (code1 == code2 && code1 == "cm") {
		result.code = "cm2";
	} else {
		result.code = pint_display_unit(code1) + " * " + pint_display_unit(code2);
	}
	result.system = q1->system;
	return format_quantity_json(result);
}

Optional<std::string> quantity_divide(const std::string &q1_json, const std::string &q2_json) {
	auto q1 = parse_quantity_json(q1_json);
	auto q2 = parse_quantity_json(q2_json);
	if (!q1 || !q2) return NullOpt<std::string>();
	if (q2->value == 0) return NullOpt<std::string>();

	// Normalize empty code to "1" (dimensionless)
	std::string code1 = q1->code.empty() ? "1" : q1->code;
	std::string code2 = q2->code.empty() ? "1" : q2->code;

	ParsedQuantity result;
	result.value = q1->value / q2->value;
	if (code2 == "1") {
		result.code = code1;
	} else if (code1 == code2) {
		result.code = "1";
	} else {
		result.code = code1 + "/" + code2;
	}
	result.system = q1->system;
	return format_quantity_json(result);
}

Optional<std::string> quantity_negate(const std::string &q_json) {
	auto q = parse_quantity_json(q_json);
	if (!q) return NullOpt<std::string>();
	q->value = -q->value;
	return format_quantity_json(*q);
}

Optional<std::string> quantity_abs(const std::string &q_json) {
	auto q = parse_quantity_json(q_json);
	if (!q) return NullOpt<std::string>();
	if (q->value < 0) q->value = -q->value;
	return format_quantity_json(*q);
}

Optional<std::string> quantity_modulo(const std::string &q1_json, const std::string &q2_json) {
	auto q1 = parse_quantity_json(q1_json);
	auto q2 = parse_quantity_json(q2_json);
	if (!q1 || !q2) return NullOpt<std::string>();
	std::string code1 = q1->code.empty() ? "1" : q1->code;
	std::string code2 = q2->code.empty() ? "1" : q2->code;
	double q2_value_in_q1_units = q2->value;
	if (code1 != code2) {
		if (!units_compatible(code1, code2)) return NullOpt<std::string>();
		auto b2 = to_base(q2->value, code2);
		auto converted = b2.has_value() ? from_base(b2.value(), code1) : NullOpt<double>();
		if (!converted.has_value()) return NullOpt<std::string>();
		q2_value_in_q1_units = converted.value();
	}
	if (q2_value_in_q1_units == 0) return NullOpt<std::string>();
	// CQL modulo: x - y * trunc(x/y)
	double quotient = q1->value / q2_value_in_q1_units;
	double trunc_q = (quotient >= 0) ? std::floor(quotient) : std::ceil(quotient);
	ParsedQuantity result;
	result.value = q1->value - q2_value_in_q1_units * trunc_q;
	result.code = code1;
	result.system = q1->system;
	return format_quantity_json(result);
}

Optional<std::string> quantity_truncated_divide(const std::string &q1_json, const std::string &q2_json) {
	auto q1 = parse_quantity_json(q1_json);
	auto q2 = parse_quantity_json(q2_json);
	if (!q1 || !q2) return NullOpt<std::string>();
	std::string code1 = q1->code.empty() ? "1" : q1->code;
	std::string code2 = q2->code.empty() ? "1" : q2->code;
	double q2_value_in_q1_units = q2->value;
	if (code1 != code2) {
		if (!units_compatible(code1, code2)) return NullOpt<std::string>();
		auto b2 = to_base(q2->value, code2);
		auto converted = b2.has_value() ? from_base(b2.value(), code1) : NullOpt<double>();
		if (!converted.has_value()) return NullOpt<std::string>();
		q2_value_in_q1_units = converted.value();
	}
	if (q2_value_in_q1_units == 0) return NullOpt<std::string>();
	double quotient = q1->value / q2_value_in_q1_units;
	ParsedQuantity result;
	result.value = (quotient >= 0) ? std::floor(quotient) : std::ceil(quotient);
	result.code = code1;
	result.system = q1->system;
	return format_quantity_json(result);
}

Optional<std::string> to_quantity(const std::string &s) {
	if (s.empty()) return NullOpt<std::string>();
	// Match the CQL ToQuantity string grammar: (+|-)?#0(.0#)?('<unit>')?
	const char *p = s.c_str();
	if (*p == '+' || *p == '-') p++;

	const char *integer_start = p;
	while (std::isdigit(static_cast<unsigned char>(*p))) p++;
	if (p == integer_start) return NullOpt<std::string>();

	if (*p == '.') {
		p++;
		const char *fraction_start = p;
		while (std::isdigit(static_cast<unsigned char>(*p))) p++;
		if (p == fraction_start) return NullOpt<std::string>();
	}

	char *end = NULL;
	double val = std::strtod(s.c_str(), &end);
	if (end != p || !std::isfinite(val)) return NullOpt<std::string>();

	bool had_unit_separator_space = false;
	while (*end == ' ') {
		had_unit_separator_space = true;
		end++;
	}
	std::string unit = "1";
	if (*end == '\'') {
		end++;
		const char *unit_start = end;
		while (*end && *end != '\'') end++;
		if (*end == '\'') {
			unit = std::string(unit_start, end - unit_start);
			end++;
		} else {
			return NullOpt<std::string>();
		}
	} else if (had_unit_separator_space) {
		return NullOpt<std::string>();
	}
	if (*end != '\0') return NullOpt<std::string>();

	ParsedQuantity q;
	q.value = val;
	q.code = unit;
	if (!is_valid_quantity_unit(q.code)) return NullOpt<std::string>();
	q.system = "http://unitsofmeasure.org";
	return format_quantity_json(q);
}

Optional<std::string> to_concept(const std::string &code_json) {
	if (code_json.empty()) return NullOpt<std::string>();
	// Wrap code in a concept: {"codes": [code]}
	yyjson_doc *doc = yyjson_read(code_json.c_str(), code_json.size(), 0);
	if (!doc) return NullOpt<std::string>();

	yyjson_mut_doc *mut_doc = yyjson_mut_doc_new(NULL);
	yyjson_mut_val *root = yyjson_mut_obj(mut_doc);
	yyjson_mut_doc_set_root(mut_doc, root);

	yyjson_mut_val *codes_arr = yyjson_mut_arr(mut_doc);
	yyjson_val *src_root = yyjson_doc_get_root(doc);

	if (yyjson_is_obj(src_root)) {
		yyjson_mut_val *copied = yyjson_val_mut_copy(mut_doc, src_root);
		if (!copied) {
			yyjson_mut_doc_free(mut_doc);
			yyjson_doc_free(doc);
			return NullOpt<std::string>();
		}
		yyjson_mut_arr_append(codes_arr, copied);
	} else if (yyjson_is_arr(src_root)) {
		size_t idx, max;
		yyjson_val *elem;
		yyjson_arr_foreach(src_root, idx, max, elem) {
			if (!yyjson_is_obj(elem)) {
				yyjson_mut_doc_free(mut_doc);
				yyjson_doc_free(doc);
				return NullOpt<std::string>();
			}
			yyjson_mut_val *copied = yyjson_val_mut_copy(mut_doc, elem);
			if (!copied) {
				yyjson_mut_doc_free(mut_doc);
				yyjson_doc_free(doc);
				return NullOpt<std::string>();
			}
			yyjson_mut_arr_append(codes_arr, copied);
		}
	} else {
		yyjson_mut_doc_free(mut_doc);
		yyjson_doc_free(doc);
		return NullOpt<std::string>();
	}
	yyjson_mut_obj_add_val(mut_doc, root, "codes", codes_arr);

	char *json_str = yyjson_mut_write(mut_doc, 0, NULL);
	std::string result;
	if (json_str) {
		result = json_str;
		free(json_str);
	}

	yyjson_mut_doc_free(mut_doc);
	yyjson_doc_free(doc);
	return result.empty() ? NullOpt<std::string>() : Optional<std::string>(result);
}

} // namespace cql
