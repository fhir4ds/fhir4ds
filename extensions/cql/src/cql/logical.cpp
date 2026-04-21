#include "cql/logical.hpp"
#include "yyjson.hpp"

using namespace duckdb_yyjson; // NOLINT

#include <cstring>
#include <string>

namespace cql {

// Parse a JSON array element as a boolean: "true" → true, "false" → false, null → absent
static Optional<bool> parse_bool_element(yyjson_val *val) {
	if (!val || yyjson_is_null(val)) {
		return NullOpt<bool>();
	}
	if (yyjson_is_bool(val)) {
		return Optional<bool>(yyjson_get_bool(val));
	}
	if (yyjson_is_str(val)) {
		const char *s = yyjson_get_str(val);
		if (std::strcmp(s, "true") == 0) return Optional<bool>(true);
		if (std::strcmp(s, "false") == 0) return Optional<bool>(false);
	}
	return NullOpt<bool>();
}

Optional<bool> logical_all_true(const std::string &json_array) {
	if (json_array.empty()) return Optional<bool>(true);

	yyjson_doc *doc = yyjson_read(json_array.c_str(), json_array.size(), 0);
	if (!doc) return Optional<bool>(true);

	yyjson_val *root = yyjson_doc_get_root(doc);
	if (!root || !yyjson_is_arr(root)) {
		yyjson_doc_free(doc);
		return Optional<bool>(true);
	}

	size_t idx, max;
	yyjson_val *val;
	yyjson_arr_foreach(root, idx, max, val) {
		auto b = parse_bool_element(val);
		if (b.has_value() && !b.value()) {
			yyjson_doc_free(doc);
			return Optional<bool>(false);
		}
	}

	yyjson_doc_free(doc);
	return Optional<bool>(true);
}

Optional<bool> logical_any_true(const std::string &json_array) {
	if (json_array.empty()) return Optional<bool>(false);

	yyjson_doc *doc = yyjson_read(json_array.c_str(), json_array.size(), 0);
	if (!doc) return Optional<bool>(false);

	yyjson_val *root = yyjson_doc_get_root(doc);
	if (!root || !yyjson_is_arr(root)) {
		yyjson_doc_free(doc);
		return Optional<bool>(false);
	}

	size_t idx, max;
	yyjson_val *val;
	yyjson_arr_foreach(root, idx, max, val) {
		auto b = parse_bool_element(val);
		if (b.has_value() && b.value()) {
			yyjson_doc_free(doc);
			return Optional<bool>(true);
		}
	}

	yyjson_doc_free(doc);
	return Optional<bool>(false);
}

Optional<bool> logical_all_false(const std::string &json_array) {
	if (json_array.empty()) return Optional<bool>(true);

	yyjson_doc *doc = yyjson_read(json_array.c_str(), json_array.size(), 0);
	if (!doc) return Optional<bool>(true);

	yyjson_val *root = yyjson_doc_get_root(doc);
	if (!root || !yyjson_is_arr(root)) {
		yyjson_doc_free(doc);
		return Optional<bool>(true);
	}

	size_t idx, max;
	yyjson_val *val;
	yyjson_arr_foreach(root, idx, max, val) {
		auto b = parse_bool_element(val);
		if (b.has_value() && b.value()) {
			yyjson_doc_free(doc);
			return Optional<bool>(false);
		}
	}

	yyjson_doc_free(doc);
	return Optional<bool>(true);
}

Optional<bool> logical_any_false(const std::string &json_array) {
	if (json_array.empty()) return Optional<bool>(false);

	yyjson_doc *doc = yyjson_read(json_array.c_str(), json_array.size(), 0);
	if (!doc) return Optional<bool>(false);

	yyjson_val *root = yyjson_doc_get_root(doc);
	if (!root || !yyjson_is_arr(root)) {
		yyjson_doc_free(doc);
		return Optional<bool>(false);
	}

	size_t idx, max;
	yyjson_val *val;
	yyjson_arr_foreach(root, idx, max, val) {
		auto b = parse_bool_element(val);
		if (b.has_value() && !b.value()) {
			yyjson_doc_free(doc);
			return Optional<bool>(true);
		}
	}

	yyjson_doc_free(doc);
	return Optional<bool>(false);
}

Optional<bool> logical_implies(bool a_null, bool a, bool b_null, bool b) {
	// 3-valued logic implication truth table:
	// a=false → true (regardless of b)
	// a=null, b=true → true
	// a=null, b=false → null
	// a=null, b=null → null
	// a=true → b
	if (!a_null && !a) {
		return Optional<bool>(true);
	}
	if (a_null) {
		if (!b_null && b) {
			return Optional<bool>(true);
		}
		return NullOpt<bool>();
	}
	// a is true
	if (b_null) {
		return NullOpt<bool>();
	}
	return Optional<bool>(b);
}

Optional<std::string> logical_coalesce(const std::string &json_array) {
	if (json_array.empty()) return NullOpt<std::string>();

	yyjson_doc *doc = yyjson_read(json_array.c_str(), json_array.size(), 0);
	if (!doc) return NullOpt<std::string>();

	yyjson_val *root = yyjson_doc_get_root(doc);
	if (!root || !yyjson_is_arr(root)) {
		yyjson_doc_free(doc);
		return NullOpt<std::string>();
	}

	size_t idx, max;
	yyjson_val *val;
	yyjson_arr_foreach(root, idx, max, val) {
		if (val && !yyjson_is_null(val)) {
			std::string result;
			if (yyjson_is_str(val)) {
				result = yyjson_get_str(val);
			} else if (yyjson_is_bool(val)) {
				result = yyjson_get_bool(val) ? "true" : "false";
			} else if (yyjson_is_int(val)) {
				result = std::to_string(yyjson_get_sint(val));
			} else if (yyjson_is_real(val)) {
				char buf[64];
				std::snprintf(buf, sizeof(buf), "%g", yyjson_get_real(val));
				result = buf;
			} else {
				char *json_str = yyjson_val_write(val, 0, NULL);
				if (json_str) {
					result = json_str;
					free(json_str);
				}
			}
			yyjson_doc_free(doc);
			return Optional<std::string>(result);
		}
	}

	yyjson_doc_free(doc);
	return NullOpt<std::string>();
}

} // namespace cql
