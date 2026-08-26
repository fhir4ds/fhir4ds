#include "cql/math.hpp"
#include <cmath>
#include <cstdlib>
#include <sstream>
#include <cstring>
#include <cfloat>
#include <stdexcept>

namespace cql {

// =====================================================================
// Helper: parse string to double
// =====================================================================
static bool parse_double(const std::string &s, double &out) {
	if (s.empty()) return false;
	char *end = NULL;
	out = std::strtod(s.c_str(), &end);
	return (end != s.c_str() && *end == '\0' && !std::isinf(out) && !std::isnan(out));
}

static std::string format_result(double val) {
	// Integer result
	if (val == std::floor(val) && std::fabs(val) < 1e15 && !std::isinf(val)) {
		std::ostringstream oss;
		oss << static_cast<long long>(val);
		return oss.str();
	}
	std::ostringstream oss;
	oss.precision(15);
	oss << val;
	return oss.str();
}

// =====================================================================
// Abs
// =====================================================================
Optional<std::string> math_abs(const std::string &x) {
	double val;
	if (!parse_double(x, val)) return NullOpt<std::string>();
	return Optional<std::string>(format_result(std::fabs(val)));
}

// =====================================================================
// Ceiling
// =====================================================================
Optional<std::string> math_ceiling(const std::string &x) {
	double val;
	if (!parse_double(x, val)) return NullOpt<std::string>();
	// CQL 1.5 Appendix B: Ceiling(Decimal) returns Integer; results that
	// cannot be represented as an Integer are null.
	double result = std::ceil(val);
	if (std::isnan(result) || std::isinf(result) ||
	    result < -2147483648.0 || result > 2147483647.0) {
		return NullOpt<std::string>();
	}
	return Optional<std::string>(format_result(result));
}

// =====================================================================
// Floor
// =====================================================================
Optional<std::string> math_floor(const std::string &x) {
	double val;
	if (!parse_double(x, val)) return NullOpt<std::string>();
	// CQL 1.5 Appendix B: Floor(Decimal) returns Integer; results that
	// cannot be represented as an Integer are null.
	double result = std::floor(val);
	if (std::isnan(result) || std::isinf(result) ||
	    result < -2147483648.0 || result > 2147483647.0) {
		return NullOpt<std::string>();
	}
	return Optional<std::string>(format_result(result));
}

// =====================================================================
// Exp
// =====================================================================
Optional<std::string> math_exp(const std::string &x) {
	double val;
	if (!parse_double(x, val)) return NullOpt<std::string>();
	double result = std::exp(val);
	// CQL v1.5.3 §16.6 Exp: "If the result of the operation cannot be
	// represented, the result is null." Reinforced by section header:
	// "operations that cause arithmetic overflow or underflow ... will
	// result in null, rather than a run-time error." So we return NULL
	// (NullOpt) when the result overflows to infinity (e.g. Exp(710),
	// Exp(1000), Exp(1e5)), instead of raising a runtime error.
	if (std::isinf(result)) {
		return NullOpt<std::string>();
	}
	return Optional<std::string>(format_result(result));
}

// =====================================================================
// Ln — natural logarithm
// =====================================================================
Optional<std::string> math_ln(const std::string &x) {
	double val;
	if (!parse_double(x, val)) return NullOpt<std::string>();
	// CQL v1.5.3 §16.12 Ln: "If the result of the operation cannot be
	// represented, the result is null." Ln(0) is -infinity and cannot be
	// represented, so return NULL rather than raising a runtime error.
	if (val == 0) {
		return NullOpt<std::string>();
	}
	if (val < 0) return NullOpt<std::string>();
	return Optional<std::string>(format_result(std::log(val)));
}

// =====================================================================
// Log(x, base)
// =====================================================================
Optional<std::string> math_log(const std::string &x, const std::string &base) {
	double xval, bval;
	if (!parse_double(x, xval) || !parse_double(base, bval)) return NullOpt<std::string>();
	if (xval <= 0 || bval <= 0 || bval == 1.0) return NullOpt<std::string>();
	return Optional<std::string>(format_result(std::log(xval) / std::log(bval)));
}

// =====================================================================
// Power
// =====================================================================
Optional<std::string> math_power(const std::string &x, const std::string &exp) {
	double xval, eval;
	if (!parse_double(x, xval) || !parse_double(exp, eval)) return NullOpt<std::string>();
	double result = std::pow(xval, eval);
	if (std::isinf(result) || std::isnan(result)) return NullOpt<std::string>();
	if (result != 0.0 && std::fabs(result) < 1e-4) {
		// Sub-scale magnitudes must be emitted in fixed notation at the
		// implementation scale (8): '%.15g'-style scientific text is
		// rounded UP to 1E-8 by DuckDB's VARCHAR->DECIMAL(38,8) cast,
		// so Power(2, -30) returned 0.00000001 instead of the
		// correctly quantized 0.00000000.
		char buf[64];
		std::snprintf(buf, sizeof(buf), "%.8f", result);
		return Optional<std::string>(std::string(buf));
	}
	return Optional<std::string>(format_result(result));
}

// =====================================================================
// Round — CQL half-up rounding (not banker's rounding)
// =====================================================================
Optional<std::string> math_round(const std::string &x, const std::string &precision) {
	double val;
	int prec;
	if (!parse_double(x, val)) return NullOpt<std::string>();
	char *end = NULL;
	prec = static_cast<int>(std::strtol(precision.c_str(), &end, 10));
	if (end == precision.c_str()) prec = 0;

	// CQL traditional rounding moves negative half ties away from zero:
	// the reference explicitly gives Round(-0.5) = -1.
	double multiplier = std::pow(10.0, prec);
	double shifted = val * multiplier;
	if (shifted >= 0.0) {
		shifted = std::floor(shifted + 0.5);
	} else {
		shifted = std::ceil(shifted - 0.5);
	}
	double result = shifted / multiplier;

	if (prec <= 0) {
		return Optional<std::string>(format_result(result));
	}
	// Format with exact decimal places
	std::ostringstream oss;
	oss.precision(prec);
	oss << std::fixed << result;
	return Optional<std::string>(oss.str());
}

// =====================================================================
// Sqrt
// =====================================================================
Optional<std::string> math_sqrt(const std::string &x) {
	double val;
	if (!parse_double(x, val)) return NullOpt<std::string>();
	if (val < 0) return NullOpt<std::string>();
	return Optional<std::string>(format_result(std::sqrt(val)));
}

// =====================================================================
// Truncate — integer part toward zero
// =====================================================================
Optional<std::string> math_truncate(const std::string &x) {
	double val;
	if (!parse_double(x, val)) return NullOpt<std::string>();
	double result = (val >= 0) ? std::floor(val) : std::ceil(val);
	return Optional<std::string>(format_result(result));
}

} // namespace cql
