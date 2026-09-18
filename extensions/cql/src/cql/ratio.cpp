#include "cql/ratio.hpp"
#include "cql/quantity.hpp"
#include "yyjson.hpp"

using namespace duckdb_yyjson; // NOLINT

#include <cmath>
#include <iomanip>
#include <sstream>

namespace cql {

// Helper: parse ratio JSON and get numerator or denominator object
static yyjson_val *get_ratio_component(yyjson_doc *doc, const char *component) {
	if (!doc) {
		return nullptr;
	}
	yyjson_val *root = yyjson_doc_get_root(doc);
	if (!root || !yyjson_is_obj(root)) {
		return nullptr;
	}
	return yyjson_obj_get(root, component);
}

// Helper: extract "value" field as double from a quantity-like object
static Optional<double> get_component_value(yyjson_val *component) {
	if (!component || !yyjson_is_obj(component)) {
		return NullOpt<double>();
	}
	yyjson_val *val = yyjson_obj_get(component, "value");
	if (!val) {
		return NullOpt<double>();
	}
	if (yyjson_is_real(val)) {
		return yyjson_get_real(val);
	}
	if (yyjson_is_int(val)) {
		return static_cast<double>(yyjson_get_int(val));
	}
	return NullOpt<double>();
}

// Helper: extract unit string from a quantity-like object (tries "unit" then "code")
static Optional<std::string> get_component_unit(yyjson_val *component) {
	if (!component || !yyjson_is_obj(component)) {
		return NullOpt<std::string>();
	}
	yyjson_val *unit = yyjson_obj_get(component, "unit");
	if (unit && yyjson_is_str(unit)) {
		return std::string(yyjson_get_str(unit));
	}
	yyjson_val *code = yyjson_obj_get(component, "code");
	if (code && yyjson_is_str(code)) {
		return std::string(yyjson_get_str(code));
	}
	return NullOpt<std::string>();
}

static Optional<ParsedQuantity> get_component_quantity(yyjson_val *component) {
	if (!component || !yyjson_is_obj(component)) {
		return NullOpt<ParsedQuantity>();
	}
	auto value = get_component_value(component);
	if (!value.has_value() || !std::isfinite(value.value())) {
		return NullOpt<ParsedQuantity>();
	}
	std::string unit = "1";
	auto component_unit = get_component_unit(component);
	if (component_unit.has_value()) {
		unit = component_unit.value();
	}
	if (!is_valid_quantity_unit(unit)) {
		return NullOpt<ParsedQuantity>();
	}
	std::string system = "http://unitsofmeasure.org";
	yyjson_val *system_val = yyjson_obj_get(component, "system");
	if (system_val && yyjson_is_str(system_val)) {
		system = yyjson_get_str(system_val);
	}
	return ParsedQuantity{value.value(), unit, system, 0};
}

static std::string format_decimal_for_cql(double value) {
	std::ostringstream out;
	out << std::setprecision(15) << value;
	std::string text = out.str();
	if (text.find('.') == std::string::npos &&
	    text.find('e') == std::string::npos &&
	    text.find('E') == std::string::npos) {
		text += ".0";
	}
	return text;
}

static std::string format_quantity_text(const ParsedQuantity &quantity) {
	return format_decimal_for_cql(quantity.value) + " '" + quantity.code + "'";
}

Optional<double> ratio_numerator_value(const std::string &ratio_json) {
	yyjson_doc *doc = yyjson_read(ratio_json.c_str(), ratio_json.size(), 0);
	if (!doc) {
		return NullOpt<double>();
	}
	auto component = get_ratio_component(doc, "numerator");
	auto quantity = get_component_quantity(component);
	auto result = quantity.has_value() ? Optional<double>(quantity->value) : NullOpt<double>();
	yyjson_doc_free(doc);
	return result;
}

Optional<double> ratio_denominator_value(const std::string &ratio_json) {
	yyjson_doc *doc = yyjson_read(ratio_json.c_str(), ratio_json.size(), 0);
	if (!doc) {
		return NullOpt<double>();
	}
	auto component = get_ratio_component(doc, "denominator");
	auto quantity = get_component_quantity(component);
	auto result = quantity.has_value() ? Optional<double>(quantity->value) : NullOpt<double>();
	yyjson_doc_free(doc);
	return result;
}

Optional<double> ratio_value(const std::string &ratio_json) {
	yyjson_doc *doc = yyjson_read(ratio_json.c_str(), ratio_json.size(), 0);
	if (!doc) {
		return NullOpt<double>();
	}
	auto num = get_component_quantity(get_ratio_component(doc, "numerator"));
	auto denom = get_component_quantity(get_ratio_component(doc, "denominator"));
	yyjson_doc_free(doc);

	if (!num.has_value() || !denom.has_value() || denom->value == 0.0) {
		return NullOpt<double>();
	}
	return num->value / denom->value;
}

Optional<std::string> ratio_numerator_unit(const std::string &ratio_json) {
	yyjson_doc *doc = yyjson_read(ratio_json.c_str(), ratio_json.size(), 0);
	if (!doc) {
		return NullOpt<std::string>();
	}
	auto component = get_ratio_component(doc, "numerator");
	auto quantity = get_component_quantity(component);
	auto result = quantity.has_value() ? get_component_unit(component) : NullOpt<std::string>();
	yyjson_doc_free(doc);
	return result;
}

Optional<std::string> ratio_denominator_unit(const std::string &ratio_json) {
	yyjson_doc *doc = yyjson_read(ratio_json.c_str(), ratio_json.size(), 0);
	if (!doc) {
		return NullOpt<std::string>();
	}
	auto component = get_ratio_component(doc, "denominator");
	auto quantity = get_component_quantity(component);
	auto result = quantity.has_value() ? get_component_unit(component) : NullOpt<std::string>();
	yyjson_doc_free(doc);
	return result;
}

Optional<std::string> ratio_to_string(const std::string &ratio_json) {
	yyjson_doc *doc = yyjson_read(ratio_json.c_str(), ratio_json.size(), 0);
	if (!doc) {
		return NullOpt<std::string>();
	}
	auto numerator = get_component_quantity(get_ratio_component(doc, "numerator"));
	auto denominator = get_component_quantity(get_ratio_component(doc, "denominator"));
	yyjson_doc_free(doc);

	if (!numerator.has_value() || !denominator.has_value()) {
		return NullOpt<std::string>();
	}
	return format_quantity_text(numerator.value()) + ":" + format_quantity_text(denominator.value());
}

} // namespace cql

// =====================================================================
// ratio_compare — C++ port of the Python udf/ratio.py ratioCompare.
// Equality is component-wise Quantity equality (3VL AND); equivalence
// compares the represented ratio value via to_quantity division.
// =====================================================================
namespace cql {

// Serialize a ratio component object back to compact JSON text for
// quantity_compare.
static Optional<std::string> component_json_text(yyjson_val *component) {
	if (!component) {
		return NullOpt<std::string>();
	}
	size_t len = 0;
	char *buf = yyjson_val_write_opts(component, YYJSON_WRITE_NOFLAG, nullptr, &len, nullptr);
	if (!buf) {
		return NullOpt<std::string>();
	}
	std::string out(buf, len);
	free(buf);
	return out;
}
// Divide a ratio's components (numerator / denominator) producing a
// Quantity JSON — mirrors Python _quantity_from_ratio_json ->
// quantityDivide(orjson(numerator), orjson(denominator)).

// Python is_valid_quantity_object: dict with finite numeric value that is
// representable and a valid unit (unit/code, default '1').
static bool ratio_component_is_valid_quantity(yyjson_val *component) {
	if (!component || !yyjson_is_obj(component)) {
		return false;
	}
	yyjson_val *val = yyjson_obj_get(component, "value");
	if (!val || yyjson_is_null(val) || yyjson_is_bool(val) || yyjson_is_str(val)) {
		return false;
	}
	double numeric;
	if (yyjson_is_int(val)) {
		numeric = static_cast<double>(yyjson_get_int(val));
	} else if (yyjson_is_real(val)) {
		numeric = yyjson_get_real(val);
	} else {
		return false;
	}
	if (!std::isfinite(numeric)) {
		return false;
	}
	yyjson_val *unit_val = yyjson_obj_get(component, "unit");
	if (!unit_val || yyjson_is_null(unit_val)) {
		unit_val = yyjson_obj_get(component, "code");
	}
	std::string unit = "1";
	if (unit_val && yyjson_is_str(unit_val)) {
		unit = yyjson_get_str(unit_val);
	}
	return is_valid_quantity_unit(unit);
}

// Divide a ratio's components (numerator / denominator) producing a
// Quantity JSON — mirrors Python _quantity_from_ratio_json ->
// quantityDivide(orjson(numerator), orjson(denominator)).
static Optional<std::string> divide_ratio_components(yyjson_doc *doc) {
	yyjson_val *num = get_ratio_component(doc, "numerator");
	yyjson_val *den = get_ratio_component(doc, "denominator");
	auto num_json = component_json_text(num);
	auto den_json = component_json_text(den);
	if (!num_json.has_value() || !den_json.has_value()) {
		return NullOpt<std::string>();
	}
	return quantity_divide(*num_json, *den_json);
}

Optional<bool> ratio_compare(const std::string &left_json, const std::string &right_json,
                             const std::string &op) {
	if (op != "==" && op != "!=" && op != "~" && op != "!~") {
		return NullOpt<bool>();
	}

	bool left_null = left_json.empty();
	bool right_null = right_json.empty();

	if (op == "~" || op == "!~") {
		bool equivalent;
		if (left_null && right_null) {
			equivalent = true;
		} else if (left_null || right_null) {
			equivalent = false;
		} else {
			yyjson_doc *l_doc = yyjson_read(left_json.c_str(), left_json.size(), 0);
			yyjson_doc *r_doc = yyjson_read(right_json.c_str(), right_json.size(), 0);
			bool valid = false;
			cql::Optional<std::string> lq;
			cql::Optional<std::string> rq;
			if (l_doc && r_doc) {
				yyjson_val *l_num = get_ratio_component(l_doc, "numerator");
				yyjson_val *l_den = get_ratio_component(l_doc, "denominator");
				yyjson_val *r_num = get_ratio_component(r_doc, "numerator");
				yyjson_val *r_den = get_ratio_component(r_doc, "denominator");
				valid = ratio_component_is_valid_quantity(l_num) &&
				       ratio_component_is_valid_quantity(l_den) &&
				       ratio_component_is_valid_quantity(r_num) &&
				       ratio_component_is_valid_quantity(r_den);
				if (valid) {
					// Python authority: toQuantity(Ratio) divides numerator by
					// denominator (udf/quantity.py::_quantity_from_ratio_json),
					// then quantity_compare("~"). Divide while docs are ALIVE.
					lq = divide_ratio_components(l_doc);
					rq = divide_ratio_components(r_doc);
				}
			}
			if (l_doc) {
				yyjson_doc_free(l_doc);
			}
			if (r_doc) {
				yyjson_doc_free(r_doc);
			}
			if (!valid) {
				equivalent = false;
			} else if (!lq.has_value() || !rq.has_value()) {
				equivalent = false;
			} else {
				auto cmp = quantity_compare(*lq, *rq, "~");
				equivalent = cmp.has_value() && cmp.value();
			}
		}
		return op == "!~" ? Optional<bool>(!equivalent) : Optional<bool>(equivalent);
	}

	// == / !=
	if (left_null || right_null) {
		return NullOpt<bool>();
	}
	yyjson_doc *l_doc = yyjson_read(left_json.c_str(), left_json.size(), 0);
	yyjson_doc *r_doc = yyjson_read(right_json.c_str(), right_json.size(), 0);
	if (!l_doc || !r_doc) {
		if (l_doc) {
			yyjson_doc_free(l_doc);
		}
		if (r_doc) {
			yyjson_doc_free(r_doc);
		}
		return NullOpt<bool>();
	}
	yyjson_val *l_num = get_ratio_component(l_doc, "numerator");
	yyjson_val *l_den = get_ratio_component(l_doc, "denominator");
	yyjson_val *r_num = get_ratio_component(r_doc, "numerator");
	yyjson_val *r_den = get_ratio_component(r_doc, "denominator");
	if (!ratio_component_is_valid_quantity(l_num) || !ratio_component_is_valid_quantity(l_den) ||
	    !ratio_component_is_valid_quantity(r_num) || !ratio_component_is_valid_quantity(r_den)) {
		yyjson_doc_free(l_doc);
		yyjson_doc_free(r_doc);
		return NullOpt<bool>();
	}
	auto l_num_json = component_json_text(l_num);
	auto l_den_json = component_json_text(l_den);
	auto r_num_json = component_json_text(r_num);
	auto r_den_json = component_json_text(r_den);
	yyjson_doc_free(l_doc);
	yyjson_doc_free(r_doc);
	if (!l_num_json.has_value() || !l_den_json.has_value() || !r_num_json.has_value() ||
	    !r_den_json.has_value()) {
		return NullOpt<bool>();
	}

	auto numerator_equal = quantity_compare(*l_num_json, *r_num_json, "==");
	auto denominator_equal = quantity_compare(*l_den_json, *r_den_json, "==");
	// Python _cql_and 3VL: any False -> False; any NULL (without False) -> NULL.
	bool has_false = (numerator_equal.has_value() && !numerator_equal.value()) ||
	                 (denominator_equal.has_value() && !denominator_equal.value());
	bool has_null = !numerator_equal.has_value() || !denominator_equal.has_value();
	if (has_false) {
		return op == "!=" ? Optional<bool>(true) : Optional<bool>(false);
	}
	if (has_null) {
		return NullOpt<bool>();
	}
	bool equal = numerator_equal.value() && denominator_equal.value();
	return op == "!=" ? Optional<bool>(!equal) : Optional<bool>(equal);
}

} // namespace cql
