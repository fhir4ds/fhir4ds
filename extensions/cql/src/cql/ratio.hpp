#pragma once

#include <string>
#include "cql/optional.hpp"

namespace cql {

Optional<double> ratio_numerator_value(const std::string &ratio_json);
Optional<double> ratio_denominator_value(const std::string &ratio_json);
Optional<double> ratio_value(const std::string &ratio_json);
Optional<std::string> ratio_numerator_unit(const std::string &ratio_json);
Optional<std::string> ratio_denominator_unit(const std::string &ratio_json);

} // namespace cql
