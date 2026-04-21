#pragma once

#include <string>
#include "optional.hpp"

namespace cql {

// CQL §22.10: HighBoundary — highest value within precision
Optional<std::string> high_boundary(const std::string &value, int precision);

// CQL §22.14: LowBoundary — lowest value within precision
Optional<std::string> low_boundary(const std::string &value, int precision);

// CQL §22.24: Precision — number of digits of precision
Optional<int> cql_precision(const std::string &value);

// CQL §18.12: TimezoneOffset — extract timezone offset in decimal hours
Optional<double> cql_timezone_offset(const std::string &value);

// CQL §22.25: Predecessor — value one step less than input
Optional<std::string> predecessor_of(const std::string &value);

// CQL §22.26: Successor — value one step greater than input
Optional<std::string> successor_of(const std::string &value);

} // namespace cql
