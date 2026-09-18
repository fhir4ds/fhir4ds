#pragma once

#include <string>
#include "cql/optional.hpp"

namespace cql {

Optional<double> ratio_numerator_value(const std::string &ratio_json);
Optional<double> ratio_denominator_value(const std::string &ratio_json);
Optional<double> ratio_value(const std::string &ratio_json);
Optional<std::string> ratio_numerator_unit(const std::string &ratio_json);
Optional<std::string> ratio_denominator_unit(const std::string &ratio_json);
Optional<std::string> ratio_to_string(const std::string &ratio_json);
Optional<bool> ratio_compare(const std::string &left_json, const std::string &right_json,
                             const std::string &op);

} // namespace cql
