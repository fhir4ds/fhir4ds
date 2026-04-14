#include "cql/ratio.hpp"
#include "yyjson.hpp"

using namespace duckdb_yyjson; // NOLINT

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

Optional<double> ratio_numerator_value(const std::string &ratio_json) {
	yyjson_doc *doc = yyjson_read(ratio_json.c_str(), ratio_json.size(), 0);
	if (!doc) {
		return NullOpt<double>();
	}
	auto result = get_component_value(get_ratio_component(doc, "numerator"));
	yyjson_doc_free(doc);
	return result;
}

Optional<double> ratio_denominator_value(const std::string &ratio_json) {
	yyjson_doc *doc = yyjson_read(ratio_json.c_str(), ratio_json.size(), 0);
	if (!doc) {
		return NullOpt<double>();
	}
	auto result = get_component_value(get_ratio_component(doc, "denominator"));
	yyjson_doc_free(doc);
	return result;
}

Optional<double> ratio_value(const std::string &ratio_json) {
	yyjson_doc *doc = yyjson_read(ratio_json.c_str(), ratio_json.size(), 0);
	if (!doc) {
		return NullOpt<double>();
	}
	auto num = get_component_value(get_ratio_component(doc, "numerator"));
	auto denom = get_component_value(get_ratio_component(doc, "denominator"));
	yyjson_doc_free(doc);

	if (!num.has_value() || !denom.has_value() || denom.value() == 0.0) {
		return NullOpt<double>();
	}
	return num.value() / denom.value();
}

Optional<std::string> ratio_numerator_unit(const std::string &ratio_json) {
	yyjson_doc *doc = yyjson_read(ratio_json.c_str(), ratio_json.size(), 0);
	if (!doc) {
		return NullOpt<std::string>();
	}
	auto result = get_component_unit(get_ratio_component(doc, "numerator"));
	yyjson_doc_free(doc);
	return result;
}

Optional<std::string> ratio_denominator_unit(const std::string &ratio_json) {
	yyjson_doc *doc = yyjson_read(ratio_json.c_str(), ratio_json.size(), 0);
	if (!doc) {
		return NullOpt<std::string>();
	}
	auto result = get_component_unit(get_ratio_component(doc, "denominator"));
	yyjson_doc_free(doc);
	return result;
}

} // namespace cql
