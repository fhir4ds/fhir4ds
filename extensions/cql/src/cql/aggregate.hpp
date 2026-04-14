#pragma once

#include <vector>
#include "cql/optional.hpp"

namespace cql {

Optional<double> statistical_median(const std::vector<double> &values);
Optional<double> statistical_mode(const std::vector<double> &values);
Optional<double> statistical_stddev(const std::vector<double> &values);
Optional<double> statistical_variance(const std::vector<double> &values);

} // namespace cql
