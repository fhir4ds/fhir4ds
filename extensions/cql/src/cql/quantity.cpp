#include "cql/quantity.hpp"
#include "yyjson.hpp"

// Shared UCUM conversion table (canonical source in duckdb-fhirpath-cpp)
#include "shared/ucum_units.hpp"

using namespace duckdb_yyjson; // NOLINT

#include <cmath>
#include <unordered_map>

namespace cql {

// Alias the shared table for local use
static const std::unordered_map<std::string, fhir::UnitConversion> &GetUnitTable() {
	return fhir::GetUcumUnitTable();
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

// =====================================================================
// JSON parsing
// =====================================================================

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

	yyjson_doc_free(doc);
	return ParsedQuantity{value, code, system};
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
	if (q1->code == q2->code || (q1->code.empty() && q2->code.empty())) {
		v1 = q1->value;
		v2 = q2->value;
	} else {
		// Convert both to base units
		if (!units_compatible(q1->code, q2->code)) {
			return NullOpt<bool>();
		}
		auto b1 = to_base(q1->value, q1->code);
		auto b2 = to_base(q2->value, q2->code);
		if (!b1.has_value() || !b2.has_value()) {
			return NullOpt<bool>();
		}
		v1 = b1.value();
		v2 = b2.value();
	}

	if (op == ">") return v1 > v2;
	if (op == "<") return v1 < v2;
	if (op == ">=") return v1 >= v2;
	if (op == "<=") return v1 <= v2;
	if (op == "==") return v1 == v2;
	if (op == "!=") return v1 != v2;
	return NullOpt<bool>();
}

Optional<std::string> quantity_add(const std::string &q1_json, const std::string &q2_json) {
	auto q1 = parse_quantity_json(q1_json);
	auto q2 = parse_quantity_json(q2_json);
	if (!q1.has_value() || !q2.has_value()) {
		return NullOpt<std::string>();
	}

	// Same unit: simple add
	if (q1->code == q2->code) {
		return format_quantity_json({q1->value + q2->value, q1->code, q1->system});
	}

	// Convert q2 to q1's units
	if (!units_compatible(q1->code, q2->code)) {
		return NullOpt<std::string>();
	}
	auto b2 = to_base(q2->value, q2->code);
	auto converted = b2.has_value() ? from_base(b2.value(), q1->code) : NullOpt<double>();
	if (!converted.has_value()) {
		return NullOpt<std::string>();
	}

	return format_quantity_json({q1->value + converted.value(), q1->code, q1->system});
}

Optional<std::string> quantity_subtract(const std::string &q1_json, const std::string &q2_json) {
	auto q1 = parse_quantity_json(q1_json);
	auto q2 = parse_quantity_json(q2_json);
	if (!q1.has_value() || !q2.has_value()) {
		return NullOpt<std::string>();
	}

	// Same unit: simple subtract
	if (q1->code == q2->code) {
		return format_quantity_json({q1->value - q2->value, q1->code, q1->system});
	}

	// Convert q2 to q1's units
	if (!units_compatible(q1->code, q2->code)) {
		return NullOpt<std::string>();
	}
	auto b2 = to_base(q2->value, q2->code);
	auto converted = b2.has_value() ? from_base(b2.value(), q1->code) : NullOpt<double>();
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
	ParsedQuantity result;
	result.value = q1->value * q2->value;
	// Simple unit handling: if one is "1" (dimensionless), take the other
	if (q1->code == "1" || q1->code.empty()) {
		result.code = q2->code;
	} else if (q2->code == "1" || q2->code.empty()) {
		result.code = q1->code;
	} else {
		result.code = q1->code;
	}
	result.system = q1->system;
	return format_quantity_json(result);
}

Optional<std::string> quantity_divide(const std::string &q1_json, const std::string &q2_json) {
	auto q1 = parse_quantity_json(q1_json);
	auto q2 = parse_quantity_json(q2_json);
	if (!q1 || !q2) return NullOpt<std::string>();
	if (q2->value == 0) return NullOpt<std::string>();
	ParsedQuantity result;
	result.value = q1->value / q2->value;
	result.code = q1->code;
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
	if (q2->value == 0) return NullOpt<std::string>();
	// CQL modulo: x - y * trunc(x/y)
	double quotient = q1->value / q2->value;
	double trunc_q = (quotient >= 0) ? std::floor(quotient) : std::ceil(quotient);
	ParsedQuantity result;
	result.value = q1->value - q2->value * trunc_q;
	result.code = q1->code;
	result.system = q1->system;
	return format_quantity_json(result);
}

Optional<std::string> quantity_truncated_divide(const std::string &q1_json, const std::string &q2_json) {
	auto q1 = parse_quantity_json(q1_json);
	auto q2 = parse_quantity_json(q2_json);
	if (!q1 || !q2) return NullOpt<std::string>();
	if (q2->value == 0) return NullOpt<std::string>();
	double quotient = q1->value / q2->value;
	ParsedQuantity result;
	result.value = (quotient >= 0) ? std::floor(quotient) : std::ceil(quotient);
	result.code = q1->code;
	result.system = q1->system;
	return format_quantity_json(result);
}

Optional<std::string> to_quantity(const std::string &s) {
	if (s.empty()) return NullOpt<std::string>();
	// Match: number optionally followed by unit in single quotes
	// E.g. "5.5 'cm'" or just "5.5"
	const char *p = s.c_str();
	while (*p == ' ') p++;

	char *end = NULL;
	double val = std::strtod(p, &end);
	if (end == p) return NullOpt<std::string>();

	while (*end == ' ') end++;
	std::string unit = "1";
	if (*end == '\'') {
		end++;
		const char *unit_start = end;
		while (*end && *end != '\'') end++;
		if (*end == '\'') {
			unit = std::string(unit_start, end - unit_start);
		}
	}

	ParsedQuantity q;
	q.value = val;
	q.code = unit;
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

	// Copy the input as an element in the codes array
	yyjson_mut_val *copied = yyjson_val_mut_copy(mut_doc, src_root);
	yyjson_mut_arr_append(codes_arr, copied);
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
