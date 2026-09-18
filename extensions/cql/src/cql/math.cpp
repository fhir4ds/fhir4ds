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

// =====================================================================
// cqlDivide — exact Decimal division at the implementation scale (8).
//
// CQL §16.4 divide: the result is a Decimal quantized half-up (ties away
// from zero) to 8 fractional digits. DuckDB's native `/` promotes DECIMAL
// operands to DOUBLE (9.9 / 3.0 -> 3.3000000000000003), so the exact
// quotient must be computed with base-10 long division over digit
// strings. Mirrors the Python authority `_cql_divide`
// (fhir4ds/cql/duckdb/macros/math.py): NULL for NULL operands (handled
// by the UDF wrapper), non-numeric operands, a zero divisor, or a result
// whose magnitude reaches 10^28 (28 integer digits after rounding).
//
// Rounding-equivalence note: the Python authority divides at prec=60 and
// then quantizes ROUND_HALF_UP to scale 8. For every result Python
// returns (integer part <= 28 digits, so quantize never overflows the
// 60-digit context), the scale-8 guard digit at fractional position 9
// lies inside the preserved 60-significant-digit window, and half-even
// carries beyond position 60 can only reach position 9 through a run of
// 9s that HALF_UP rounds up anyway. Direct HALF_UP rounding of the true
// quotient at scale 8 is therefore byte-identical to the two-step
// Python result.
// =====================================================================
namespace {

const size_t CQL_DIVIDE_MAX_DIGITS = 5000;
const long long CQL_DIVIDE_MAX_EXP = 5000;

int compare_digit_strings(const std::string &a, const std::string &b) {
	if (a.size() != b.size()) return a.size() < b.size() ? -1 : 1;
	int c = a.compare(b);
	return c < 0 ? -1 : (c > 0 ? 1 : 0);
}

std::string subtract_digit_strings(const std::string &a, const std::string &b) {
	// a >= b, both without leading zeros ("0" allowed)
	std::string res(a.size(), '0');
	int borrow = 0;
	for (int i = static_cast<int>(a.size()) - 1, j = static_cast<int>(b.size()) - 1; i >= 0; --i, --j) {
		int da = a[i] - '0';
		int db = (j >= 0 ? b[j] - '0' : 0) + borrow;
		if (da < db) {
			da += 10;
			borrow = 1;
		} else {
			borrow = 0;
		}
		res[i] = static_cast<char>('0' + da - db);
	}
	size_t nz = res.find_first_not_of('0');
	return nz == std::string::npos ? "0" : res.substr(nz);
}

struct DecimalParts {
	int sign;
	std::string digits; // no leading zeros; "0" for the value 0
	long long exp10;    // value = sign * digits * 10^exp10
};

bool parse_cql_decimal_text(const std::string &raw, DecimalParts &out) {
	size_t b = 0, e = raw.size();
	auto is_ws = [](char c) {
		return c == ' ' || c == '\t' || c == '\n' || c == '\r' || c == '\v' || c == '\f';
	};
	while (b < e && is_ws(raw[b])) b++;
	while (e > b && is_ws(raw[e - 1])) e--;
	if (b >= e) return false;
	size_t p = b;
	out.sign = 1;
	if (raw[p] == '+' || raw[p] == '-') {
		if (raw[p] == '-') out.sign = -1;
		p++;
	}
	std::string int_digits, frac_digits;
	bool seen_dot = false, seen_digit = false;
	for (; p < e; ++p) {
		char c = raw[p];
		if (c >= '0' && c <= '9') {
			(seen_dot ? frac_digits : int_digits).push_back(c);
			seen_digit = true;
		} else if (c == '.' && !seen_dot) {
			seen_dot = true;
		} else {
			break;
		}
	}
	if (!seen_digit) return false;
	long long exp = 0;
	if (p < e && (raw[p] == 'e' || raw[p] == 'E')) {
		p++;
		bool eneg = false;
		if (p < e && (raw[p] == '+' || raw[p] == '-')) {
			eneg = raw[p] == '-';
			p++;
		}
		if (p >= e) return false;
		long long ev = 0;
		for (; p < e; ++p) {
			char c = raw[p];
			if (c < '0' || c > '9') return false;
			ev = ev * 10 + (c - '0');
			if (ev > CQL_DIVIDE_MAX_EXP) return false;
		}
		exp = eneg ? -ev : ev;
	} else if (p != e) {
		return false;
	}
	out.digits = int_digits + frac_digits;
	out.exp10 = exp - static_cast<long long>(frac_digits.size());
	if (out.digits.size() > CQL_DIVIDE_MAX_DIGITS) return false;
	size_t nz = out.digits.find_first_not_of('0');
	if (nz == std::string::npos) {
		out.digits = "0";
		out.sign = 1;
		return true;
	}
	// Stripping LEADING zeros does not change the value's exponent
	// ("05"e-1 == "5"e-1); only trailing-zero stripping would.
	out.digits = out.digits.substr(nz);
	if (out.exp10 > CQL_DIVIDE_MAX_EXP || out.exp10 < -CQL_DIVIDE_MAX_EXP) return false;
	return true;
}

std::string increment_digit_string(const std::string &s) {
	std::string res = s;
	int carry = 1;
	for (int i = static_cast<int>(res.size()) - 1; i >= 0 && carry; --i) {
		int d = res[i] - '0' + carry;
		carry = d / 10;
		res[i] = static_cast<char>('0' + d % 10);
	}
	if (carry) res.insert(res.begin(), '1');
	return res;
}

} // namespace

Optional<CqlDivideResult> cql_divide_text(const std::string &a, const std::string &b) {
	DecimalParts pa, pb;
	if (!parse_cql_decimal_text(a, pa)) return NullOpt<CqlDivideResult>();
	if (!parse_cql_decimal_text(b, pb)) return NullOpt<CqlDivideResult>();
	if (pb.digits == "0") return NullOpt<CqlDivideResult>();
	if (pa.digits == "0") {
		CqlDivideResult r;
		r.negative = false;
		r.unscaled = std::string(8, '0');
		return Optional<CqlDivideResult>(r);
	}

	// quotient magnitude = (Da / Db) * 10^(ea - eb) as N / D
	long long shift = pa.exp10 - pb.exp10;
	std::string num = pa.digits;
	std::string den = pb.digits;
	if (shift > 0) {
		num.append(static_cast<size_t>(shift), '0');
	} else if (shift < 0) {
		den.append(static_cast<size_t>(-shift), '0');
	}

	// Integer part: schoolbook long division. When num < den the integer
	// part is 0 and the remainder is num itself.
	std::string int_part = "0";
	std::string rem = "0";
	if (compare_digit_strings(num, den) >= 0) {
		int_part.clear();
		for (char cd : num) {
			if (rem == "0") {
				rem = std::string(1, cd);
			} else {
				rem.push_back(cd);
			}
			int qd = 0;
			while (qd < 9 && compare_digit_strings(rem, den) >= 0) {
				rem = subtract_digit_strings(rem, den);
				qd++;
			}
			int_part.push_back(static_cast<char>('0' + qd));
		}
		size_t nz = int_part.find_first_not_of('0');
		int_part = (nz == std::string::npos) ? "0" : int_part.substr(nz);
	} else {
		rem = num;
	}

	// Nine fractional digits: 8 scale digits + the HALF_UP guard digit.
	std::string frac(9, '0');
	for (int k = 0; k < 9; ++k) {
		if (rem == "0") break;
		rem.push_back('0');
		int qd = 0;
		while (qd < 9 && compare_digit_strings(rem, den) >= 0) {
			rem = subtract_digit_strings(rem, den);
			qd++;
		}
		frac[k] = static_cast<char>('0' + qd);
	}

	std::string magnitude = int_part + frac.substr(0, 8);
	if (frac[8] >= '5') {
		magnitude = increment_digit_string(magnitude);
	}

	// Implementation Decimal range: magnitude < 10^28 means at most 28
	// integer digits after rounding (the scale-8 suffix is 8 digits).
	if (magnitude.size() > 8 && magnitude.size() - 8 > 28) {
		return NullOpt<CqlDivideResult>();
	}

	CqlDivideResult r;
	r.negative = (pa.sign != pb.sign);
	r.unscaled = magnitude;
	return Optional<CqlDivideResult>(r);
}

} // namespace cql
