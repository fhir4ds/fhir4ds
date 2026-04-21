#pragma once

#include "optional.hpp"
#include <string>

namespace cql {

// CQL §16.1: Abs
Optional<std::string> math_abs(const std::string &x);

// CQL §16.2: Ceiling
Optional<std::string> math_ceiling(const std::string &x);

// CQL §16.5: Exp
Optional<std::string> math_exp(const std::string &x);

// CQL §16.7: Floor
Optional<std::string> math_floor(const std::string &x);

// CQL §16.11: Log(x, base)
Optional<std::string> math_log(const std::string &x, const std::string &base);

// CQL §16.12: Ln(x) — natural log
Optional<std::string> math_ln(const std::string &x);

// CQL §16.15: Power(x, exp)
Optional<std::string> math_power(const std::string &x, const std::string &exp);

// CQL §16.17: Round(x, precision)
Optional<std::string> math_round(const std::string &x, const std::string &precision);

// CQL §16.19: Sqrt
Optional<std::string> math_sqrt(const std::string &x);

// CQL §16.20: Truncate
Optional<std::string> math_truncate(const std::string &x);

} // namespace cql
