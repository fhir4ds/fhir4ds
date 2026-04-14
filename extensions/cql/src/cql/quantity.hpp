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

} // namespace cql
