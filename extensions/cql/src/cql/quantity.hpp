#pragma once

#include <string>
#include "cql/optional.hpp"

namespace cql {

struct ParsedQuantity {
	double value;
	std::string code;
	std::string system;
};

Optional<ParsedQuantity> parse_quantity_json(const std::string &json);
Optional<std::string> format_quantity_json(const ParsedQuantity &q);
Optional<double> quantity_value_fn(const std::string &json);
Optional<std::string> quantity_unit_fn(const std::string &json);
Optional<bool> quantity_compare(const std::string &q1_json, const std::string &q2_json, const std::string &op);
Optional<std::string> quantity_add(const std::string &q1_json, const std::string &q2_json);
Optional<std::string> quantity_subtract(const std::string &q1_json, const std::string &q2_json);
Optional<std::string> quantity_convert(const std::string &q_json, const std::string &target_unit);

// Phase 6: New quantity operations
Optional<std::string> quantity_multiply(const std::string &q1_json, const std::string &q2_json);
Optional<std::string> quantity_divide(const std::string &q1_json, const std::string &q2_json);
Optional<std::string> quantity_negate(const std::string &q_json);
Optional<std::string> quantity_abs(const std::string &q_json);
Optional<std::string> quantity_modulo(const std::string &q1_json, const std::string &q2_json);
Optional<std::string> quantity_truncated_divide(const std::string &q1_json, const std::string &q2_json);
Optional<std::string> to_quantity(const std::string &s);
Optional<std::string> to_concept(const std::string &code_json);

} // namespace cql
