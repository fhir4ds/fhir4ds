#include "fhirpath/evaluator.hpp"
#include "shared/ucum_units.hpp"
#include "yyjson.hpp"

using namespace duckdb_yyjson; // NOLINT
#include <algorithm>
#include <cctype>
#include <climits>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <ctime>
#include <functional>
#include <iomanip>
#include <regex>
#include <sstream>
#include <stdexcept>
#include <unordered_map>
#include <unordered_set>

// Defensive bounds-check macro for AST child access.
// The parser should guarantee correct structure, but this guards against
// malformed input or future parser changes.
#define FHIRPATH_REQUIRE_CHILDREN(node, n) \
	do { if ((node).children.size() < static_cast<size_t>(n)) return {}; } while (0)

namespace fhirpath {

// ---------------------------------------------------------------------------
// UTF-8 helpers — all FHIRPath string functions must operate on Unicode
// code-point positions, not byte offsets.  std::string stores UTF-8 bytes,
// so we provide small inline helpers to translate between the two spaces.
// ---------------------------------------------------------------------------

/// Return the byte index that corresponds to Unicode code-point position
/// `char_pos` in the UTF-8 string `s`.  If `char_pos` exceeds the number
/// of code-points, returns `s.size()`.
static size_t utf8CharToByte(const std::string &s, size_t char_pos) {
	size_t cp = 0;
	size_t byte = 0;
	while (cp < char_pos && byte < s.size()) {
		unsigned char c = static_cast<unsigned char>(s[byte]);
		if (c < 0x80)      byte += 1;
		else if (c < 0xE0) byte += 2;
		else if (c < 0xF0) byte += 3;
		else               byte += 4;
		++cp;
	}
	return byte;
}

/// Count the number of Unicode code-points in the UTF-8 string `s`.
static size_t utf8Len(const std::string &s) {
	size_t cp = 0;
	size_t byte = 0;
	while (byte < s.size()) {
		unsigned char c = static_cast<unsigned char>(s[byte]);
		if (c < 0x80)      byte += 1;
		else if (c < 0xE0) byte += 2;
		else if (c < 0xF0) byte += 3;
		else               byte += 4;
		++cp;
	}
	return cp;
}

/// Convert a byte offset in `s` to the corresponding Unicode code-point
/// position.  Returns the code-point index of the code-point that contains
/// `byte_pos`.  Used to translate `std::string::find()` results.
static size_t utf8ByteToChar(const std::string &s, size_t byte_pos) {
	size_t cp = 0;
	size_t byte = 0;
	while (byte < byte_pos && byte < s.size()) {
		unsigned char c = static_cast<unsigned char>(s[byte]);
		if (c < 0x80)      byte += 1;
		else if (c < 0xE0) byte += 2;
		else if (c < 0xF0) byte += 3;
		else               byte += 4;
		++cp;
	}
	return cp;
}

static bool hasReDoSRisk(const std::string &pattern) {
	for (size_t i = 0; i < pattern.size(); ++i) {
		if (pattern[i] != '(' || (i > 0 && pattern[i - 1] == '\\')) {
			continue;
		}
		bool in_bracket = false;
		bool has_inner_quantifier = false;
		bool has_alternation = false;
		for (size_t j = i + 1; j < pattern.size(); ++j) {
			char c = pattern[j];
			if (c == '\\' && j + 1 < pattern.size()) {
				++j;
				continue;
			}
			if (c == '[') {
				in_bracket = true;
				continue;
			}
			if (c == ']') {
				in_bracket = false;
				continue;
			}
			if (in_bracket) {
				continue;
			}
			if (c == '(') {
				break;
			}
			if (c == ')') {
				if (j + 1 < pattern.size() && (pattern[j + 1] == '+' || pattern[j + 1] == '*')) {
					return has_inner_quantifier || has_alternation;
				}
				break;
			}
			if (c == '+' || c == '*') {
				has_inner_quantifier = true;
			} else if (c == '|') {
				has_alternation = true;
			}
		}
	}
	return false;
}

static std::string normalizeFHIRPathRegex(const std::string &pattern);

static void validateFHIRPathRegex(const std::string &pattern) {
	if (pattern.size() > 1000) {
		throw FHIRPathSpecError("FHIRPath: regex pattern exceeds maximum length of 1000 characters");
	}
	if (hasReDoSRisk(pattern)) {
		throw FHIRPathSpecError("FHIRPath: regex pattern contains nested quantifiers or quantified alternations");
	}
	std::string normalized = normalizeFHIRPathRegex(pattern);
	static thread_local std::unordered_set<std::string> syntax_validated;
	if (syntax_validated.size() >= 256) {
		syntax_validated.clear();
	}
	if (syntax_validated.find(normalized) == syntax_validated.end()) {
		try {
			std::regex syntax_probe(normalized, std::regex_constants::ECMAScript);
			(void)syntax_probe;
		} catch (const std::regex_error &e) {
			throw FHIRPathSpecError(std::string("FHIRPath: invalid regular expression: ") + e.what());
		}
		syntax_validated.insert(normalized);
	}
}

// Thread-local regex cache to avoid recompilation in hot paths
static const std::regex &get_cached_regex(const std::string &pattern,
                                          std::regex_constants::syntax_option_type flags = std::regex_constants::ECMAScript) {
	if (pattern.size() > 1000) {
		throw FHIRPathSpecError("FHIRPath: regex pattern exceeds maximum length of 1000 characters");
	}
	static thread_local std::unordered_map<std::string, std::regex> cache;
	// Bound the cache to avoid unbounded memory growth per thread.
	if (cache.size() >= 256) {
		cache.clear();
	}
	// Key includes flags to distinguish different compilation modes
	std::string cache_key = pattern + "|" + std::to_string(static_cast<unsigned>(flags));
	auto it = cache.find(cache_key);
	if (it != cache.end()) {
		return it->second;
	}
	auto result = cache.emplace(cache_key, std::regex(pattern, flags));
	return result.first->second;
}

// std::regex operates over UTF-8 bytes. FHIRPath §5.6.9 requires single-line
// regex behavior that allows Unicode characters, so an unescaped "." must
// consume one UTF-8 code point rather than one byte.
static std::string normalizeFHIRPathRegex(const std::string &pattern) {
	static const std::string utf8_codepoint =
	    "(?:[\\x00-\\x7F]|[\\xC2-\\xDF][\\x80-\\xBF]|[\\xE0-\\xEF][\\x80-\\xBF]{2}|[\\xF0-\\xF4][\\x80-\\xBF]{3})";
	std::string normalized;
	bool in_bracket = false;
	for (size_t i = 0; i < pattern.size(); ++i) {
		if (pattern[i] == '\\' && i + 1 < pattern.size()) {
			normalized += pattern[i];
			normalized += pattern[i + 1];
			++i;
		} else if (pattern[i] == '[') {
			in_bracket = true;
			normalized += pattern[i];
		} else if (pattern[i] == ']') {
			in_bracket = false;
			normalized += pattern[i];
		} else if (pattern[i] == '.' && !in_bracket) {
			normalized += utf8_codepoint;
		} else {
			normalized += pattern[i];
		}
	}
	return normalized;
}

// Forward declarations
static int countDecimalPlaces(const FPValue &val);
static std::string escapeJsonString(const std::string &s);
static bool quantityValuesEqual(const FPValue &a, const FPValue &b);
static bool isCalendarDurationUnit(const std::string &unit);
static bool isUcumDurationUnit(const std::string &unit);
static bool isSecondOrMillisecondDuration(const std::string &unit);

// --- Static helper functions (used throughout) ---

static FPValue::Type effectiveType(const FPValue &v) {
	if (v.type != FPValue::Type::JsonVal || !v.json_val) return v.type;
	if (yyjson_is_bool(v.json_val)) return FPValue::Type::Boolean;
	if (yyjson_is_int(v.json_val)) return FPValue::Type::Integer;
	if (yyjson_is_real(v.json_val)) return FPValue::Type::Decimal;
	if (yyjson_is_str(v.json_val)) return FPValue::Type::String;
	return v.type;
}

static bool extractStrictInteger(const FPValue &v, int64_t &out) {
	if (v.type == FPValue::Type::Integer) {
		out = v.int_val;
		return true;
	}
	if (v.type == FPValue::Type::JsonVal && v.json_val &&
	    !yyjson_is_bool(v.json_val) && yyjson_is_int(v.json_val)) {
		out = yyjson_get_sint(v.json_val);
		return true;
	}
	return false;
}

static bool isFHIRPathIntegerString(const std::string &s) {
	if (s.empty()) return false;
	size_t pos = 0;
	if (s[0] == '+' || s[0] == '-') {
		if (s.size() == 1) return false;
		pos = 1;
	}
	for (; pos < s.size(); ++pos) {
		if (!std::isdigit(static_cast<unsigned char>(s[pos]))) return false;
	}
	return true;
}

static bool isFHIRPathDecimalString(const std::string &s) {
	if (s.empty()) return false;
	size_t pos = 0;
	if (s[0] == '+' || s[0] == '-') {
		if (s.size() == 1) return false;
		pos = 1;
	}
	bool saw_digit = false;
	for (; pos < s.size(); ++pos) {
		if (std::isdigit(static_cast<unsigned char>(s[pos]))) {
			saw_digit = true;
			continue;
		}
		break;
	}
	if (!saw_digit) return false;
	if (pos == s.size()) return true;
	if (s[pos] != '.') return false;
	++pos;
	if (pos == s.size()) return false;
	for (; pos < s.size(); ++pos) {
		if (!std::isdigit(static_cast<unsigned char>(s[pos]))) return false;
	}
	return true;
}

static bool fhirTypeIsA(const std::string &type_name, const std::string &parent_type) {
	if (type_name == parent_type) return true;

	static const std::unordered_map<std::string, std::string> hierarchy = {
		{"Address", "Element"},
		{"Age", "Quantity"},
		{"AllergyIntolerance", "DomainResource"},
		{"Annotation", "Element"},
		{"Attachment", "Element"},
		{"BackboneElement", "Element"},
		{"Bundle", "Resource"},
		{"CarePlan", "DomainResource"},
		{"CodeableConcept", "Element"},
		{"Coding", "Element"},
		{"Composition", "DomainResource"},
		{"Condition", "DomainResource"},
		{"ContactPoint", "Element"},
		{"Count", "Quantity"},
		{"DiagnosticReport", "DomainResource"},
		{"Distance", "Quantity"},
		{"DocumentReference", "DomainResource"},
		{"DomainResource", "Resource"},
		{"Dosage", "BackboneElement"},
		{"Duration", "Quantity"},
		{"Encounter", "DomainResource"},
		{"Extension", "Element"},
		{"HumanName", "Element"},
		{"Identifier", "Element"},
		{"Immunization", "DomainResource"},
		{"Location", "DomainResource"},
		{"Medication", "DomainResource"},
		{"MedicationRequest", "DomainResource"},
		{"Meta", "Element"},
		{"Money", "Quantity"},
		{"Narrative", "Element"},
		{"Observation", "DomainResource"},
		{"OperationOutcome", "DomainResource"},
		{"Organization", "DomainResource"},
		{"Patient", "DomainResource"},
		{"Period", "Element"},
		{"Practitioner", "DomainResource"},
		{"Procedure", "DomainResource"},
		{"Quantity", "Element"},
		{"Range", "Element"},
		{"Ratio", "Element"},
		{"Reference", "Element"},
		{"SampledData", "Element"},
		{"ServiceRequest", "DomainResource"},
		{"Signature", "Element"},
		{"Specimen", "DomainResource"},
		{"Timing", "BackboneElement"},
		{"canonical", "uri"},
		{"code", "string"},
		{"id", "string"},
		{"instant", "dateTime"},
		{"markdown", "string"},
		{"oid", "uri"},
		{"positiveInt", "integer"},
		{"unsignedInt", "integer"},
		{"url", "uri"},
		{"uuid", "uri"},
		{"uri", "string"}
	};

	std::string current = type_name;
	for (int depth = 0; depth < 16; ++depth) {
		auto it = hierarchy.find(current);
		if (it == hierarchy.end()) return false;
		current = it->second;
		if (current == parent_type) return true;
	}
	return false;
}

static bool isKnownFHIRType(const std::string &type_name) {
	static const std::unordered_set<std::string> known = {
		"Address", "Age", "AllergyIntolerance", "Annotation", "Attachment",
		"BackboneElement", "Bundle", "CarePlan", "CodeableConcept", "Coding",
		"Composition", "Condition", "ContactPoint", "Count", "DiagnosticReport",
		"Distance", "DocumentReference", "DomainResource", "Dosage", "Duration",
		"Element", "Encounter", "Extension", "HumanName", "Identifier",
		"Immunization", "Location", "Medication", "MedicationRequest", "Meta",
		"Money", "Narrative", "Observation", "OperationOutcome", "Organization",
		"Patient", "Period", "Practitioner", "Procedure", "Quantity", "Range",
		"Ratio", "Reference", "Resource", "SampledData", "ServiceRequest",
		"Signature", "Specimen", "Timing",
		"base64Binary", "boolean", "canonical", "code", "date", "dateTime",
		"decimal", "id", "instant", "integer", "markdown", "oid", "positiveInt",
		"string", "time", "unsignedInt", "uri", "url", "uuid", "xhtml"
	};
	return known.find(type_name) != known.end();
}

static std::string normalizeFHIRChoiceTypeName(const std::string &type_name) {
	static const std::unordered_map<std::string, std::string> primitive_names = {
		{"Base64Binary", "base64Binary"},
		{"Boolean", "boolean"},
		{"Canonical", "canonical"},
		{"Code", "code"},
		{"Date", "date"},
		{"DateTime", "dateTime"},
		{"Decimal", "decimal"},
		{"Id", "id"},
		{"Instant", "instant"},
		{"Integer", "integer"},
		{"Markdown", "markdown"},
		{"Oid", "oid"},
		{"PositiveInt", "positiveInt"},
		{"String", "string"},
		{"Time", "time"},
		{"UnsignedInt", "unsignedInt"},
		{"Uri", "uri"},
		{"Url", "url"},
		{"Uuid", "uuid"},
		{"Xhtml", "xhtml"}
	};
	auto it = primitive_names.find(type_name);
	return it == primitive_names.end() ? type_name : it->second;
}

static bool isKnownSystemType(const std::string &type_name) {
	static const std::unordered_set<std::string> known = {
		"Any", "Boolean", "Integer", "Decimal", "String", "Date", "DateTime",
		"Time", "Quantity"
	};
	return known.find(type_name) != known.end();
}

static bool isKnownTypeSpecifier(const std::string &ns, const std::string &target) {
	if (target.empty()) return false;
	if (ns == "System") return isKnownSystemType(target) || isKnownFHIRType(target);
	if (ns == "FHIR") return isKnownFHIRType(target);
	if (ns.empty()) {
		return isKnownFHIRType(target) || isKnownSystemType(target);
	}
	return false;
}

static bool isDistinctSystemTypeName(const std::string &type_name) {
	return type_name == "Any" || type_name == "Boolean" || type_name == "Integer" ||
	       type_name == "Decimal" || type_name == "String" || type_name == "Date" ||
	       type_name == "DateTime" || type_name == "Time";
}

static bool isFHIRPrimitiveTypeName(const std::string &type_name) {
	return !type_name.empty() && std::islower(static_cast<unsigned char>(type_name[0]));
}

static bool collectTypeNameParts(const ASTNode &node, std::vector<std::string> &parts) {
	if (node.type != NodeType::MemberAccess) return false;
	if (node.source) {
		if (!collectTypeNameParts(*node.source, parts)) return false;
	}
	if (node.name.empty()) return false;
	parts.push_back(node.name);
	return true;
}

static std::string typeNameFromSpecifierNode(const ASTNode &node) {
	std::vector<std::string> parts;
	if (!collectTypeNameParts(node, parts) || parts.empty()) {
		throw FHIRPathSpecError("Type argument must be a type specifier");
	}
	std::string type_name;
	for (size_t i = 0; i < parts.size(); ++i) {
		if (i > 0) type_name += ".";
		type_name += parts[i];
	}
	return type_name;
}

static bool isNumericType(const FPValue &v) {
	auto t = effectiveType(v);
	return t == FPValue::Type::Integer || t == FPValue::Type::Decimal;
}

static bool isDateTimeType(const FPValue &v) {
	auto t = effectiveType(v);
	if (t == FPValue::Type::Date || t == FPValue::Type::DateTime || t == FPValue::Type::Time) return true;
	// Check for date-like strings (from JSON)
	if (t == FPValue::Type::String) {
		std::string s;
		if (v.type == FPValue::Type::JsonVal && v.json_val && yyjson_is_str(v.json_val))
			s = yyjson_get_str(v.json_val);
		else if (v.type == FPValue::Type::String)
			s = v.string_val;
		if (s.size() >= 4 && std::isdigit((unsigned char)s[0]) && std::isdigit((unsigned char)s[1]) &&
		    std::isdigit((unsigned char)s[2]) && std::isdigit((unsigned char)s[3])) {
			if (s.size() == 4) return true; // YYYY
			if (s.size() >= 7 && s[4] == '-') return true; // YYYY-MM...
		}
	}
	return false;
}

static double getNumericValue(const FPValue &v) {
	if (v.type == FPValue::Type::Integer) return static_cast<double>(v.int_val);
	if (v.type == FPValue::Type::Decimal) return v.decimal_val;
	if (v.type == FPValue::Type::Quantity) return v.quantity_value;
	if (v.type == FPValue::Type::JsonVal && v.json_val) {
		if (yyjson_is_int(v.json_val)) return static_cast<double>(yyjson_get_sint(v.json_val));
		if (yyjson_is_real(v.json_val)) return yyjson_get_real(v.json_val);
		if (yyjson_is_num(v.json_val)) return yyjson_get_num(v.json_val);
	}
	return 0.0;
}

// Forward declarations for date parsing (defined later in this file)
struct DateTimeParts {
	int year, month, day, hour, minute, second, millisecond;
	int tz_offset_minutes; // offset from UTC in minutes, INT_MIN if no TZ
	int precision; // 1=year,2=month,3=day,4=hour,5=minute,6=second,7=millisecond
	bool valid;
};
static DateTimeParts parseDateTimeParts(const std::string &s);
static DateTimeParts parseTimeParts(const std::string &s);
static int compareDateTimes(const std::string &a, const std::string &b,
                            FPValue::Type a_type, FPValue::Type b_type,
                            bool is_equivalence, bool is_equality);

static std::string rawStringValue(const FPValue &v) {
	if (v.type == FPValue::Type::String || v.type == FPValue::Type::Date ||
	    v.type == FPValue::Type::DateTime || v.type == FPValue::Type::Time) {
		return v.string_val;
	}
	if (v.type == FPValue::Type::JsonVal && v.json_val && yyjson_is_str(v.json_val)) {
		const char *s = yyjson_get_str(v.json_val);
		return s ? std::string(s) : std::string();
	}
	return "";
}

static FPValue::Type temporalArithmeticType(const FPValue &v) {
	auto t = effectiveType(v);
	if (t == FPValue::Type::Date || t == FPValue::Type::DateTime || t == FPValue::Type::Time) {
		return t;
	}
	if (!v.fhir_type.empty()) {
		std::string ft = v.fhir_type;
		std::transform(ft.begin(), ft.end(), ft.begin(), [](unsigned char c) {
			return static_cast<char>(std::tolower(c));
		});
		if (ft == "date") return FPValue::Type::Date;
		if (ft == "datetime" || ft == "instant") return FPValue::Type::DateTime;
		if (ft == "time") return FPValue::Type::Time;
	}
	std::string s = rawStringValue(v);
	if (!s.empty()) {
		DateTimeParts tp = parseTimeParts(s);
		if (tp.valid && tp.precision > 0) return FPValue::Type::Time;
		DateTimeParts dp = parseDateTimeParts(s);
		if (dp.valid && dp.precision > 0) {
			return s.find('T') == std::string::npos ? FPValue::Type::Date : FPValue::Type::DateTime;
		}
	}
	return t;
}

static std::string normalizeTimeLiteralString(const std::string &s) {
	std::string out = s;
	if (!out.empty() && out[0] == 'T') {
		out = out.substr(1);
	}
	return out;
}

// Standalone string conversion for FPValue equality (avoids needing Evaluator::toString).
// Only handles types used by fpValuesEqual for string-based comparison.
static std::string fpValueToString(const FPValue &val) {
	switch (val.type) {
	case FPValue::Type::String:
	case FPValue::Type::Date:
	case FPValue::Type::DateTime:
	case FPValue::Type::Time:
		return val.string_val;
	case FPValue::Type::Integer:
		return std::to_string(val.int_val);
	case FPValue::Type::Decimal: {
		std::ostringstream oss;
		oss << std::setprecision(17) << val.decimal_val;
		return oss.str();
	}
	case FPValue::Type::Boolean:
		return val.bool_val ? "true" : "false";
	case FPValue::Type::JsonVal:
		if (val.json_val && yyjson_is_str(val.json_val))
			return yyjson_get_str(val.json_val);
		if (val.json_val && yyjson_is_bool(val.json_val))
			return yyjson_get_bool(val.json_val) ? "true" : "false";
		if (val.json_val && yyjson_is_int(val.json_val))
			return std::to_string(yyjson_get_sint(val.json_val));
		if (val.json_val && yyjson_is_real(val.json_val)) {
			std::ostringstream oss;
			oss << yyjson_get_real(val.json_val);
			return oss.str();
		}
		if (val.json_val && (yyjson_is_obj(val.json_val) || yyjson_is_arr(val.json_val))) {
			// Serialize complex JSON values for equality comparison
			char *json = yyjson_val_write(val.json_val, 0, nullptr);
			if (json) {
				std::string result(json);
				free(json);
				return result;
			}
		}
		return "";
	default:
		return "";
	}
}

static double convertQuantityToBase(double value, const std::string &unit, std::string &base_unit);

static std::string normalizeEquivalentString(const std::string &in) {
	std::string out;
	bool prev_ws = true;
	for (char c : in) {
		if (std::isspace(static_cast<unsigned char>(c))) {
			if (!prev_ws) out += ' ';
			prev_ws = true;
		} else {
			out += static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
			prev_ws = false;
		}
	}
	if (!out.empty() && out.back() == ' ') out.pop_back();
	return out;
}

static std::string jsonNumberText(yyjson_val *val) {
	if (!val) return "";
	char *json = yyjson_val_write(val, 0, nullptr);
	if (!json) return "";
	std::string result(json);
	free(json);
	return result;
}

static int decimalPlacesFromNumberText(std::string text) {
	if (text.empty()) return 0;
	if (text[0] == '+' || text[0] == '-') text = text.substr(1);
	size_t exp_pos = text.find_first_of("eE");
	int exponent = 0;
	if (exp_pos != std::string::npos) {
		try {
			exponent = std::stoi(text.substr(exp_pos + 1));
		} catch (const std::exception &) {
			exponent = 0;
		}
		text = text.substr(0, exp_pos);
	}
	size_t dot = text.find('.');
	int places = 0;
	if (dot != std::string::npos) {
		places = static_cast<int>(text.size() - dot - 1);
		while (places > 0 && !text.empty() && text.back() == '0') {
			text.pop_back();
			places--;
		}
	}
	places -= exponent;
	return places > 0 ? places : 0;
}

static bool jsonNumbersEquivalent(yyjson_val *left, yyjson_val *right) {
	if (!(left && right && yyjson_is_num(left) && yyjson_is_num(right))) return false;
	double l_num = yyjson_get_num(left);
	double r_num = yyjson_get_num(right);
	int l_prec = decimalPlacesFromNumberText(jsonNumberText(left));
	int r_prec = decimalPlacesFromNumberText(jsonNumberText(right));
	int cmp_prec = (l_prec > 0 && r_prec > 0) ? std::min(l_prec, r_prec)
	             : std::max(l_prec, r_prec);
	if (cmp_prec > 0) {
		double scale = std::pow(10.0, cmp_prec);
		return std::round(l_num * scale) == std::round(r_num * scale);
	}
	return (l_num == r_num) || std::abs(l_num - r_num) < 1e-10;
}

static bool jsonValueAsQuantity(yyjson_val *val, FPValue &out) {
	if (!val || !yyjson_is_obj(val)) return false;
	yyjson_val *value_field = yyjson_obj_get(val, "value");
	if (!value_field) return false;

	double value = 0.0;
	if (yyjson_is_num(value_field)) {
		value = yyjson_get_num(value_field);
		if (std::isnan(value) || std::isinf(value)) return false;
	} else if (yyjson_is_str(value_field)) {
		try {
			std::string raw = yyjson_get_str(value_field);
			size_t pos = 0;
			value = std::stod(raw, &pos);
			if (pos != raw.size() || std::isnan(value) || std::isinf(value)) return false;
		} catch (const std::exception &) {
			return false;
		}
	} else {
		return false;
	}

	yyjson_val *code_field = yyjson_obj_get(val, "code");
	yyjson_val *unit_field = yyjson_obj_get(val, "unit");
	const char *unit = nullptr;
	if (code_field && yyjson_is_str(code_field)) {
		unit = yyjson_get_str(code_field);
	} else if (unit_field && yyjson_is_str(unit_field)) {
		unit = yyjson_get_str(unit_field);
	}
	if (!unit || std::string(unit).empty()) return false;

	out = FPValue();
	out.type = FPValue::Type::Quantity;
	out.quantity_value = value;
	out.quantity_unit = unit;
	if (yyjson_is_str(value_field)) {
		out.source_text = yyjson_get_str(value_field);
	} else if (yyjson_is_num(value_field)) {
		out.source_text = jsonNumberText(value_field);
	}
	return true;
}

static int quantityEqualState(const FPValue &left, const FPValue &right) {
	bool mixed_calendar_ucum =
	    (isCalendarDurationUnit(left.quantity_unit) && isUcumDurationUnit(right.quantity_unit)) ||
	    (isUcumDurationUnit(left.quantity_unit) && isCalendarDurationUnit(right.quantity_unit));
	if (mixed_calendar_ucum &&
	    !(isSecondOrMillisecondDuration(left.quantity_unit) && isSecondOrMillisecondDuration(right.quantity_unit))) {
		return 0;
	}
	std::string left_base, right_base;
	convertQuantityToBase(left.quantity_value, left.quantity_unit, left_base);
	convertQuantityToBase(right.quantity_value, right.quantity_unit, right_base);
	if (left_base != right_base) return -1;
	return quantityValuesEqual(left, right) ? 1 : 0;
}

static bool quantitiesEquivalent(const FPValue &left, const FPValue &right) {
	std::string left_base, right_base;
	double left_conv = convertQuantityToBase(left.quantity_value, left.quantity_unit, left_base);
	double right_conv = convertQuantityToBase(right.quantity_value, right.quantity_unit, right_base);
	if (left_base != right_base) return false;
	int left_dp = countDecimalPlaces(left);
	int right_dp = countDecimalPlaces(right);
	double left_scale = (left.quantity_value != 0) ? left_conv / left.quantity_value : 1.0;
	double right_scale = (right.quantity_value != 0) ? right_conv / right.quantity_value : 1.0;
	double left_half = 0.5 * std::pow(10.0, -left_dp) * std::abs(left_scale);
	double right_half = 0.5 * std::pow(10.0, -right_dp) * std::abs(right_scale);
	return std::abs(left_conv - right_conv) < std::max(left_half, right_half);
}

static int jsonValuesEqualState(yyjson_val *left, yyjson_val *right) {
	if (!left || !right) return left == right ? 1 : 0;

	FPValue left_quantity, right_quantity;
	if (jsonValueAsQuantity(left, left_quantity) && jsonValueAsQuantity(right, right_quantity)) {
		return quantityEqualState(left_quantity, right_quantity);
	}

	if (yyjson_is_null(left) || yyjson_is_null(right)) {
		return yyjson_is_null(left) && yyjson_is_null(right) ? 1 : 0;
	}
	if (yyjson_is_bool(left) || yyjson_is_bool(right)) {
		return (yyjson_is_bool(left) && yyjson_is_bool(right) &&
		        yyjson_get_bool(left) == yyjson_get_bool(right)) ? 1 : 0;
	}
	if (yyjson_is_num(left) || yyjson_is_num(right)) {
		if (!(yyjson_is_num(left) && yyjson_is_num(right))) return 0;
		double left_num = yyjson_get_num(left);
		double right_num = yyjson_get_num(right);
		double diff = std::abs(left_num - right_num);
		double maxval = std::max(std::abs(left_num), std::abs(right_num));
		return ((left_num == right_num) || diff < 1e-10 || (maxval > 0 && diff / maxval < 1e-10)) ? 1 : 0;
	}
	if (yyjson_is_str(left) || yyjson_is_str(right)) {
		return (yyjson_is_str(left) && yyjson_is_str(right) &&
		        std::string(yyjson_get_str(left)) == std::string(yyjson_get_str(right))) ? 1 : 0;
	}
	if (yyjson_is_arr(left) || yyjson_is_arr(right)) {
		if (!(yyjson_is_arr(left) && yyjson_is_arr(right))) return 0;
		size_t left_size = yyjson_arr_size(left);
		size_t right_size = yyjson_arr_size(right);
		if (left_size != right_size) return 0;
		size_t idx, max;
		yyjson_val *left_value;
		size_t right_idx = 0;
		yyjson_arr_foreach(left, idx, max, left_value) {
			yyjson_val *right_value = yyjson_arr_get(right, right_idx++);
			int state = jsonValuesEqualState(left_value, right_value);
			if (state != 1) return state;
		}
		return 1;
	}
	if (yyjson_is_obj(left) || yyjson_is_obj(right)) {
		if (!(yyjson_is_obj(left) && yyjson_is_obj(right))) return 0;
		if (yyjson_obj_size(left) != yyjson_obj_size(right)) return 0;
		yyjson_obj_iter iter;
		yyjson_obj_iter_init(left, &iter);
		yyjson_val *key;
		while ((key = yyjson_obj_iter_next(&iter))) {
			const char *key_str = yyjson_get_str(key);
			yyjson_val *left_value = yyjson_obj_iter_get_val(key);
			yyjson_val *right_value = yyjson_obj_get(right, key_str);
			if (!right_value) return 0;
			int state = jsonValuesEqualState(left_value, right_value);
			if (state != 1) return state;
		}
		return 1;
	}
	return yyjson_equals(left, right) ? 1 : 0;
}

static bool jsonValuesEquivalent(yyjson_val *left, yyjson_val *right) {
	if (!left || !right) return left == right;

	FPValue left_quantity, right_quantity;
	if (jsonValueAsQuantity(left, left_quantity) && jsonValueAsQuantity(right, right_quantity)) {
		return quantitiesEquivalent(left_quantity, right_quantity);
	}

	if (yyjson_is_null(left) || yyjson_is_null(right)) {
		return yyjson_is_null(left) && yyjson_is_null(right);
	}
	if (yyjson_is_bool(left) || yyjson_is_bool(right)) {
		return yyjson_is_bool(left) && yyjson_is_bool(right) &&
		       yyjson_get_bool(left) == yyjson_get_bool(right);
	}
	if (yyjson_is_num(left) || yyjson_is_num(right)) {
		if (!(yyjson_is_num(left) && yyjson_is_num(right))) return false;
		return jsonNumbersEquivalent(left, right);
	}
	if (yyjson_is_str(left) || yyjson_is_str(right)) {
		return yyjson_is_str(left) && yyjson_is_str(right) &&
		       normalizeEquivalentString(yyjson_get_str(left)) ==
		           normalizeEquivalentString(yyjson_get_str(right));
	}
	if (yyjson_is_arr(left) || yyjson_is_arr(right)) {
		if (!(yyjson_is_arr(left) && yyjson_is_arr(right))) return false;
		size_t left_size = yyjson_arr_size(left);
		size_t right_size = yyjson_arr_size(right);
		if (left_size != right_size) return false;
		std::vector<bool> matched(right_size, false);
		size_t li, lmax, ri, rmax;
		yyjson_val *lval, *rval;
		yyjson_arr_foreach(left, li, lmax, lval) {
			bool found = false;
			size_t current = 0;
			yyjson_arr_foreach(right, ri, rmax, rval) {
				if (!matched[current] && jsonValuesEquivalent(lval, rval)) {
					matched[current] = true;
					found = true;
					break;
				}
				++current;
			}
			if (!found) return false;
		}
		return true;
	}
	if (yyjson_is_obj(left) || yyjson_is_obj(right)) {
		if (!(yyjson_is_obj(left) && yyjson_is_obj(right))) return false;
		if (yyjson_obj_size(left) != yyjson_obj_size(right)) return false;
		yyjson_obj_iter iter;
		yyjson_obj_iter_init(left, &iter);
		yyjson_val *key;
		while ((key = yyjson_obj_iter_next(&iter))) {
			const char *key_str = yyjson_get_str(key);
			yyjson_val *left_value = yyjson_obj_iter_get_val(key);
			yyjson_val *right_value = yyjson_obj_get(right, key_str);
			if (!right_value || !jsonValuesEquivalent(left_value, right_value)) {
				return false;
			}
		}
		return true;
	}
	return yyjson_equals(left, right);
}

static bool isCalendarDurationUnit(const std::string &unit) {
	return unit == "year" || unit == "years" || unit == "month" || unit == "months" ||
	       unit == "week" || unit == "weeks" || unit == "day" || unit == "days" ||
	       unit == "hour" || unit == "hours" || unit == "minute" || unit == "minutes" ||
	       unit == "second" || unit == "seconds" ||
	       unit == "millisecond" || unit == "milliseconds";
}

static bool isUcumDurationUnit(const std::string &unit) {
	return unit == "'a'" || unit == "'mo'" || unit == "'wk'" || unit == "'d'" ||
	       unit == "'h'" || unit == "'min'" || unit == "'s'" || unit == "'ms'" ||
	       unit == "a" || unit == "mo" || unit == "wk" || unit == "d" ||
	       unit == "h" || unit == "min" || unit == "s" || unit == "ms";
}

static bool isSecondOrMillisecondDuration(const std::string &unit) {
	return unit == "second" || unit == "seconds" || unit == "millisecond" ||
	       unit == "milliseconds" || unit == "'s'" || unit == "'ms'" ||
	       unit == "s" || unit == "ms";
}

static bool isMixedCalendarUcumDurationAboveSeconds(const std::string &left_unit,
                                                    const std::string &right_unit) {
	bool mixed_calendar_ucum =
	    (isCalendarDurationUnit(left_unit) && isUcumDurationUnit(right_unit)) ||
	    (isUcumDurationUnit(left_unit) && isCalendarDurationUnit(right_unit));
	if (!mixed_calendar_ucum) {
		return false;
	}
	return !(isSecondOrMillisecondDuration(left_unit) && isSecondOrMillisecondDuration(right_unit));
}

static bool isDateVsDateTimePair(FPValue::Type a_type, FPValue::Type b_type) {
	return (a_type == FPValue::Type::Date && b_type == FPValue::Type::DateTime) ||
	       (a_type == FPValue::Type::DateTime && b_type == FPValue::Type::Date);
}

static bool quantityValuesEqual(const FPValue &a, const FPValue &b) {
	if (a.quantity_unit == b.quantity_unit) {
		return std::abs(a.quantity_value - b.quantity_value) < 1e-10;
	}

	bool mixed_calendar_ucum =
	    (isCalendarDurationUnit(a.quantity_unit) && isUcumDurationUnit(b.quantity_unit)) ||
	    (isUcumDurationUnit(a.quantity_unit) && isCalendarDurationUnit(b.quantity_unit));
	if (mixed_calendar_ucum &&
	    !(isSecondOrMillisecondDuration(a.quantity_unit) && isSecondOrMillisecondDuration(b.quantity_unit))) {
		return false;
	}

	std::string a_base, b_base;
	double a_converted = convertQuantityToBase(a.quantity_value, a.quantity_unit, a_base);
	double b_converted = convertQuantityToBase(b.quantity_value, b.quantity_unit, b_base);
	if (a_base != b_base) {
		return false;
	}
	double diff = std::abs(a_converted - b_converted);
	double maxval = std::max(std::abs(a_converted), std::abs(b_converted));
	return (a_converted == b_converted) || diff < 1e-10 || (maxval > 0 && diff / maxval < 1e-10);
}

static bool fpValueAsQuantity(const FPValue &v, FPValue &out);

// FHIRPath = operator equality for two single FPValue items.
// Used by distinct(), isDistinct(), subsetOf(), supersetOf().
// Mirrors the = operator logic in evalBinaryOp for single-item comparisons.
static bool fpValuesEqual(const FPValue &a, const FPValue &b) {
	auto at = effectiveType(a);
	auto bt = effectiveType(b);

	// Both numeric: compare by value (1 == 1.0)
	if (isNumericType(a) && isNumericType(b)) {
		double an = getNumericValue(a);
		double bn = getNumericValue(b);
		double diff = std::abs(an - bn);
		double maxval = std::max(std::abs(an), std::abs(bn));
		return (an == bn) || diff < 1e-10 || (maxval > 0 && diff / maxval < 1e-10);
	}

	FPValue qa, qb;
	if (fpValueAsQuantity(a, qa) && fpValueAsQuantity(b, qb)) {
		return quantityValuesEqual(qa, qb);
	}

	if (a.type == FPValue::Type::JsonVal && b.type == FPValue::Type::JsonVal) {
		if (!a.json_val || !b.json_val) return a.json_val == b.json_val;
		return jsonValuesEqualState(a.json_val, b.json_val) == 1;
	}

	// Both date/time types: compare string values
	if (isDateTimeType(a) && isDateTimeType(b)) {
		auto at = effectiveType(a);
		auto bt = effectiveType(b);
		if (isDateVsDateTimePair(at, bt)) return false;
		bool a_is_time = (at == FPValue::Type::Time);
		bool b_is_time = (bt == FPValue::Type::Time);
		if (a_is_time != b_is_time) return false;
		return compareDateTimes(fpValueToString(a), fpValueToString(b), at, bt, false, true) == 0;
	}

	// Quantity comparison
	if (a.type == FPValue::Type::Quantity && b.type == FPValue::Type::Quantity) {
		return quantityValuesEqual(a, b);
	}

	// Incompatible types: not equal
	if (at != bt) return false;

	// Same type: compare string representations
	return fpValueToString(a) == fpValueToString(b);
}

static bool requireBooleanValue(const FPValue &item, const std::string &function_name) {
	if (item.type == FPValue::Type::Boolean) {
		return item.bool_val;
	}
	if (item.type == FPValue::Type::JsonVal && item.json_val && yyjson_is_bool(item.json_val)) {
		return yyjson_get_bool(item.json_val);
	}
	throw FHIRPathSpecError(function_name + "() requires a collection of Boolean values");
}

static double convertQuantityToBase(double value, const std::string &unit, std::string &base_unit) {
	return fhir::ConvertToBaseUnit(value, unit, base_unit);
}

static bool isBareDurationKeyword(const std::string &unit) {
	return unit == "year" || unit == "years" || unit == "month" || unit == "months" ||
	       unit == "week" || unit == "weeks" || unit == "day" || unit == "days" ||
	       unit == "hour" || unit == "hours" || unit == "minute" || unit == "minutes" ||
	       unit == "second" || unit == "seconds" ||
	       unit == "millisecond" || unit == "milliseconds";
}

static bool isBareDurationCode(const std::string &unit) {
	return unit == "a" || unit == "mo" || unit == "wk" || unit == "d" ||
	       unit == "h" || unit == "min" || unit == "s" || unit == "ms";
}

static bool convertQuantityUnit(const FPValue &quantity, const std::string &to_unit, FPValue &out) {
	if (to_unit.empty() || quantity.quantity_unit == to_unit) {
		out = quantity;
		return true;
	}

	std::string from_base;
	double from_base_value = convertQuantityToBase(quantity.quantity_value, quantity.quantity_unit, from_base);
	std::string to_base;
	double to_base_factor = convertQuantityToBase(1.0, to_unit, to_base);
	if (from_base != to_base || to_base_factor == 0.0) {
		return false;
	}

	out = quantity;
	out.quantity_value = from_base_value / to_base_factor;
	out.quantity_unit = to_unit;
	out.source_text.clear();
	return true;
}

// Try to convert a JSON value to a Quantity if it looks like one (has value, code/unit fields)
static bool tryJsonToQuantity(const FPValue &v, double &out_value, std::string &out_unit) {
	if (v.type != FPValue::Type::JsonVal || !v.json_val || !yyjson_is_obj(v.json_val)) return false;
	yyjson_val *val_field = yyjson_obj_get(v.json_val, "value");
	if (!val_field) return false;
	if (yyjson_is_num(val_field)) {
		out_value = yyjson_get_num(val_field);
		if (std::isnan(out_value) || std::isinf(out_value)) return false;
	} else if (yyjson_is_str(val_field)) {
		try {
			std::string raw = yyjson_get_str(val_field);
			size_t pos = 0;
			out_value = std::stod(raw, &pos);
			if (pos != raw.size() || std::isnan(out_value) || std::isinf(out_value)) return false;
		}
		catch (const std::exception &) { return false; }
	} else return false;
	yyjson_val *code_field = yyjson_obj_get(v.json_val, "code");
	if (code_field && yyjson_is_str(code_field)) {
		out_unit = yyjson_get_str(code_field);
	} else {
		yyjson_val *unit_field = yyjson_obj_get(v.json_val, "unit");
		if (unit_field && yyjson_is_str(unit_field)) out_unit = yyjson_get_str(unit_field);
		else return false;
	}
	return true;
}

static bool isQuantityLike(const FPValue &v) {
	if (v.type == FPValue::Type::Quantity) return true;
	if (v.type != FPValue::Type::JsonVal || !v.json_val || !yyjson_is_obj(v.json_val)) return false;
	if (!v.fhir_type.empty() && fhirTypeIsA(v.fhir_type, "Quantity")) return true;
	return yyjson_obj_get(v.json_val, "value") &&
	       (yyjson_obj_get(v.json_val, "code") || yyjson_obj_get(v.json_val, "unit"));
}

static bool fpValueAsQuantity(const FPValue &v, FPValue &out) {
	if (v.type == FPValue::Type::Quantity) {
		out = v;
		return true;
	}
	if (!isQuantityLike(v)) return false;
	double value;
	std::string unit;
	if (!tryJsonToQuantity(v, value, unit)) return false;
	out = FPValue();
	out.type = FPValue::Type::Quantity;
	out.quantity_value = value;
	out.quantity_unit = unit;
	yyjson_val *value_field = yyjson_obj_get(v.json_val, "value");
	if (value_field && yyjson_is_str(value_field)) {
		out.source_text = yyjson_get_str(value_field);
	} else if (value_field && yyjson_is_num(value_field)) {
		char *json = yyjson_val_write(value_field, 0, nullptr);
		if (json) {
			out.source_text = json;
			free(json);
		}
	}
	return true;
}

static std::string canonicalJsonForRepeatKey(yyjson_val *val) {
	if (!val) return "null";
	if (yyjson_is_null(val)) return "null";
	if (yyjson_is_bool(val)) return yyjson_get_bool(val) ? "true" : "false";
	if (yyjson_is_num(val)) {
		std::ostringstream oss;
		oss << std::setprecision(17) << yyjson_get_num(val);
		return oss.str();
	}
	if (yyjson_is_str(val)) {
		return "\"" + escapeJsonString(yyjson_get_str(val)) + "\"";
	}
	if (yyjson_is_arr(val)) {
		std::string out = "[";
		size_t idx, max;
		yyjson_val *elem;
		bool first = true;
		yyjson_arr_foreach(val, idx, max, elem) {
			if (!first) out += ",";
			first = false;
			out += canonicalJsonForRepeatKey(elem);
		}
		out += "]";
		return out;
	}
	if (yyjson_is_obj(val)) {
		std::vector<std::pair<std::string, std::string>> entries;
		yyjson_obj_iter iter;
		yyjson_obj_iter_init(val, &iter);
		yyjson_val *key;
		while ((key = yyjson_obj_iter_next(&iter))) {
			const char *key_str = yyjson_get_str(key);
			if (!key_str) continue;
			yyjson_val *child = yyjson_obj_iter_get_val(key);
			entries.push_back(std::make_pair(std::string(key_str), canonicalJsonForRepeatKey(child)));
		}
		std::sort(entries.begin(), entries.end(),
		          [](const std::pair<std::string, std::string> &a,
		             const std::pair<std::string, std::string> &b) {
			          return a.first < b.first;
		          });
		std::string out = "{";
		for (size_t i = 0; i < entries.size(); i++) {
			if (i > 0) out += ",";
			out += "\"" + escapeJsonString(entries[i].first) + "\":" + entries[i].second;
		}
		out += "}";
		return out;
	}
	return "";
}

static std::string fpValueRepeatKey(const FPValue &v) {
	FPValue quantity;
	if (fpValueAsQuantity(v, quantity)) {
		std::string base_unit;
		double base_value = convertQuantityToBase(quantity.quantity_value, quantity.quantity_unit, base_unit);
		std::ostringstream oss;
		oss << std::setprecision(17);
		if (!base_unit.empty()) {
			oss << "quantity:" << base_unit << ":" << base_value;
		} else {
			oss << "quantity:" << quantity.quantity_unit << ":" << quantity.quantity_value;
		}
		return oss.str();
	}

	if (isNumericType(v)) {
		std::ostringstream oss;
		oss << std::setprecision(17) << getNumericValue(v);
		return "number:" + oss.str();
	}

	if (v.type == FPValue::Type::JsonVal && v.json_val) {
		if (yyjson_is_null(v.json_val)) return "json:null";
		if (yyjson_is_bool(v.json_val)) return std::string("boolean:") + (yyjson_get_bool(v.json_val) ? "true" : "false");
		if (yyjson_is_num(v.json_val)) {
			std::ostringstream oss;
			oss << std::setprecision(17) << yyjson_get_num(v.json_val);
			return "number:" + oss.str();
		}
		if (yyjson_is_str(v.json_val)) return std::string("string:") + yyjson_get_str(v.json_val);
		if (yyjson_is_obj(v.json_val) || yyjson_is_arr(v.json_val)) {
			return std::string("json:") + canonicalJsonForRepeatKey(v.json_val);
		}
	}

	if (isDateTimeType(v)) {
		return std::string("temporal:") + fpValueToString(v);
	}
	if (v.type == FPValue::Type::Boolean) {
		return std::string("boolean:") + (v.bool_val ? "true" : "false");
	}
	return std::string("value:") + fpValueToString(v);
}

// FHIR field name to primitive type mapping for common fields
static const char* fhirFieldType(const std::string &field_name) {
	// code fields
	if (field_name == "gender" || field_name == "status" || field_name == "use" ||
	    field_name == "type" || field_name == "intent" || field_name == "priority" ||
	    field_name == "language" || field_name == "mode" || field_name == "code" ||
	    field_name == "comparator" || field_name == "direction" || field_name == "linkId" ||
	    field_name == "contentType" || field_name == "subjectType")
		return "code";
	// uri fields
	if (field_name == "url" || field_name == "system" || field_name == "reference" ||
	    field_name == "profile" || field_name == "instantiatesUri" || field_name == "implicitRules")
		return "uri";
	// id fields
	if (field_name == "id" || field_name == "versionId")
		return "id";
	// string fields
	if (field_name == "display" || field_name == "family" || field_name == "text" ||
	    field_name == "description" || field_name == "comment" || field_name == "version" ||
	    field_name == "name" || field_name == "title" || field_name == "publisher" ||
	    field_name == "city" || field_name == "state" || field_name == "country" ||
	    field_name == "district" || field_name == "postalCode")
		return "string";
	// boolean fields
	if (field_name == "active" || field_name == "experimental" || field_name == "abstract" ||
	    field_name == "required" || field_name == "repeats" || field_name == "readOnly" ||
	    field_name == "immutable" || field_name == "deceasedBoolean" ||
	    field_name == "multipleBirthBoolean")
		return "boolean";
	// dateTime fields
	if (field_name == "issued" || field_name == "created" || field_name == "authored" ||
	    field_name == "lastUpdated" || field_name == "date")
		return "dateTime";
	// date fields
	if (field_name == "birthDate")
		return "date";
	return nullptr; // unknown
}

FPCollection Evaluator::evaluate(const ASTNode &ast, yyjson_doc *doc, yyjson_val *root) {
	current_doc_ = doc;
	resource_context_ = root;
	current_time_cached_ = false;
	current_time_ = 0;
	FPCollection input;
	if (root) {
		input.push_back(FPValue::FromJson(root));
	}
	return eval(ast, input, doc);
}

Evaluator::~Evaluator() {
	for (size_t i = 0; i < owned_docs_.size(); i++) {
		yyjson_doc_free(owned_docs_[i]);
	}
}

time_t Evaluator::currentTime() {
	if (!current_time_cached_) {
		current_time_ = time(nullptr);
		current_time_cached_ = true;
	}
	return current_time_;
}

FPCollection Evaluator::eval(const ASTNode &node, const FPCollection &input, yyjson_doc *doc) {
	switch (node.type) {
	case NodeType::IntegerLiteral: {
		int64_t ival = node_value_get<int64_t>(node.value);
		if (ival > 2147483647LL) {
			throw FHIRPathSpecError("Integer literal out of range");
		}
		return {FPValue::FromInteger(ival)};
	}
	case NodeType::DecimalLiteral: {
		auto v = FPValue::FromDecimal(node_value_get<double>(node.value));
		v.source_text = node.value.string_val;
		return {v};
	}
	case NodeType::StringLiteral:
		return {FPValue::FromString(node_value_get<std::string>(node.value))};
	case NodeType::BooleanLiteral:
		return {FPValue::FromBoolean(node_value_get<bool>(node.value))};
	case NodeType::DateLiteral:
	case NodeType::DateTimeLiteral:
	case NodeType::TimeLiteral: {
		FPValue v;
		v.type = (node.type == NodeType::DateLiteral)      ? FPValue::Type::Date
		         : (node.type == NodeType::DateTimeLiteral) ? FPValue::Type::DateTime
		                                                    : FPValue::Type::Time;
		v.string_val = node_value_get<std::string>(node.value);
		if (node.type == NodeType::DateLiteral && !parseDateTimeParts(v.string_val).valid) {
			throw FHIRPathSpecError("Invalid Date literal: " + v.string_val);
		}
		if (node.type == NodeType::DateTimeLiteral && !parseDateTimeParts(v.string_val).valid) {
			throw FHIRPathSpecError("Invalid DateTime literal: " + v.string_val);
		}
		if (node.type == NodeType::TimeLiteral) {
			DateTimeParts parts = parseTimeParts(v.string_val);
			if (!parts.valid) {
				throw FHIRPathSpecError("Invalid Time literal: " + v.string_val);
			}
			v.string_val = normalizeTimeLiteralString(v.string_val);
		}
		return {v};
	}
	case NodeType::QuantityLiteral: {
		auto qv = node_value_get<QuantityValue>(node.value);
		if (qv.unit.empty()) {
			throw FHIRPathSpecError("Quantity literal unit must not be empty");
		}
		FPValue v;
		v.type = FPValue::Type::Quantity;
		v.quantity_value = qv.value;
		v.quantity_unit = qv.unit;
		v.source_text = node.value.string_val;
		return {v};
	}

	case NodeType::MemberAccess: {
		FPCollection source_collection = input;
		if (node.source) {
			source_collection = eval(*node.source, input, doc);
		}
		return evalMemberAccess(node, source_collection, doc);
	}
	case NodeType::Indexer:
		return evalIndexer(node, input, doc);

	case NodeType::WhereCall:
		return evalWhere(node, node.source ? eval(*node.source, input, doc) : input, doc);
	case NodeType::ExistsCall:
		return evalExists(node, node.source ? eval(*node.source, input, doc) : input, doc);
	case NodeType::OfTypeCall:
		return evalOfType(node, node.source ? eval(*node.source, input, doc) : input, doc);
	case NodeType::ExtensionCall: {
		auto source_col = node.source ? eval(*node.source, input, doc) : input;
		FPCollection url_arg;
		if (!node.children.empty()) {
			url_arg = eval(*node.children[0], input, doc);
		}
		return fn_extension(source_col, url_arg);
	}

	case NodeType::FunctionCall: {
		auto source_col = node.source ? eval(*node.source, input, doc) : input;
		return evalFunction(node, source_col, doc, node.source ? &input : nullptr);
	}

	case NodeType::BinaryOp:
		return evalBinaryOp(node, input, doc);
	case NodeType::UnaryOp:
		return evalUnaryOp(node, input, doc);
	case NodeType::UnionOp: {
		FHIRPATH_REQUIRE_CHILDREN(node, 2);
		// Save variable scope for union branches
		auto saved_vars = defined_variables_;
		auto saved_chain = chain_defined_vars_;
		chain_defined_vars_.clear();
		auto left = eval(*node.children[0], input, doc);
		defined_variables_ = saved_vars;
		chain_defined_vars_ = saved_chain;
		auto right = eval(*node.children[1], input, doc);
		defined_variables_ = saved_vars;
		chain_defined_vars_ = saved_chain;
		return fn_union(left, right);
	}

	case NodeType::TypeExpression: {
		FHIRPATH_REQUIRE_CHILDREN(node, 1);
		auto source_col = eval(*node.children[0], input, doc);
		if (node.op == "is") {
			return fn_isType(source_col, node.name);
		} else if (node.op == "as") {
			return fn_asType(source_col, node.name);
		}
		return {};
	}

	case NodeType::EnvVariable:
		if (node.name == "%resource" || node.name == "%context" || node.name == "%rootResource") {
			if (resource_context_) {
				return {FPValue::FromJson(resource_context_)};
			}
		}
		// Well-known terminology URIs
		if (node.name == "%sct") return {FPValue::FromString("http://snomed.info/sct")};
		if (node.name == "%loinc") return {FPValue::FromString("http://loinc.org")};
		if (node.name == "%ucum") return {FPValue::FromString("http://unitsofmeasure.org")};
		if (node.name == "%vs-administrative-gender") return {FPValue::FromString("http://hl7.org/fhir/ValueSet/administrative-gender")};
		if (node.name == "%ext-patient-birthTime") return {FPValue::FromString("http://hl7.org/fhir/StructureDefinition/patient-birthTime")};
		// Check user-defined variables
		{
			std::string var_name = node.name;
			if (!var_name.empty() && var_name[0] == '%') var_name = var_name.substr(1);
			auto it = defined_variables_.find(var_name);
			if (it != defined_variables_.end()) {
				return it->second;
			}
			// If it looks like a user variable (not a known system var), throw.
			// Environment variables must be provided explicitly; do not fabricate
			// arbitrary %vs-* or %ext-* values at the public DuckDB surface.
			if (node.name != "%resource" && node.name != "%context" && node.name != "%rootResource" &&
			    node.name != "%sct" && node.name != "%loinc" && node.name != "%ucum" &&
			    node.name != "%vs-administrative-gender" && node.name != "%ext-patient-birthTime") {
				throw FHIRPathSpecError("Undefined variable: " + node.name);
			}
		}
		return {};

	case NodeType::This:
		return input;
	case NodeType::Total:
		return total_context_;
	case NodeType::Index:
		if (index_context_ >= 0) {
			return {FPValue::FromInteger(index_context_)};
		}
		return {};

	default:
		return {};
	}
}

static std::string infer_fhir_type(const std::string &field_name) {
	// Common FHIR type suffixes for choice types [x]. 
	// This ensures direct access like valueQuantity sets fhir_type metadata.
	static const char* suffixes[] = {
		"Boolean", "Integer", "Decimal", "String", "Date", "DateTime", "Time", "Quantity",
		"Attachment", "Identifier", "CodeableConcept", "Coding", "Reference", "Period",
		"Range", "Ratio", "SampledData", "Signature", "HumanName", "Address", "ContactPoint", "Timing",
		"Uri", "Url", "Canonical", "Base64Binary", "Code", "Id", "Oid", "UnsignedInt", "PositiveInt",
		"Markdown", "Uuid", "Age", "Distance", "Duration", "Count", "Money", nullptr
	};
	for (int i = 0; suffixes[i]; ++i) {
		std::string s = suffixes[i];
		if (field_name.size() > s.size() && field_name.substr(field_name.size() - s.size()) == s) {
			// Check if it follows camelCase (e.g. valueQuantity)
			if (std::islower(static_cast<unsigned char>(field_name[field_name.size() - s.size() - 1]))) {
				return s;
			}
		}
	}
	return "";
}

FPCollection Evaluator::evalMemberAccess(const ASTNode &node, const FPCollection &input, yyjson_doc *doc) {
	FPCollection result;
	const auto &field_name = node.name;

	std::function<void(yyjson_val*, const std::string&, const std::string&)> add_flattened =
		[&](yyjson_val *v, const std::string &fname, const std::string &ftype) {
			if (yyjson_is_arr(v)) {
				size_t idx, max; yyjson_val *elem;
				yyjson_arr_foreach(v, idx, max, elem) {
					add_flattened(elem, fname, ftype);
				}
			} else if (!yyjson_is_null(v)) {
				// FHIRPath §2.1.1: null values from navigation produce empty collections.
				// Skip null JSON values to maintain consistency across all existence functions.
				FPValue fpv = FPValue::FromJson(v);
				if (yyjson_is_num(v)) fpv.source_text = jsonNumberText(v);
				if (!fname.empty()) fpv.field_name = fname;
				if (!ftype.empty()) fpv.fhir_type = ftype;
				result.push_back(fpv);
			}
		};

	for (const auto &item : input) {
		if (item.type != FPValue::Type::JsonVal || !item.json_val) {
			continue;
		}

		yyjson_val *val = item.json_val;

		if (yyjson_is_obj(val)) {
			// FHIRPath type-qualified access: if field_name matches resourceType, return the object itself
			yyjson_val *rt = yyjson_obj_get(val, "resourceType");
			if (rt && yyjson_is_str(rt) && std::string(yyjson_get_str(rt)) == field_name) {
				result.push_back(item);
				continue;
			}

			yyjson_val *child = yyjson_obj_get(val, field_name.c_str());
			if (child) {
				add_flattened(child, field_name, infer_fhir_type(field_name));
			} else {
				// Check for choice types (e.g., value[x] pattern)
				if (field_name.size() > 0) {
					std::string prefix = field_name;
					yyjson_obj_iter iter;
					yyjson_obj_iter_init(val, &iter);
					yyjson_val *key;
					while ((key = yyjson_obj_iter_next(&iter))) {
						const char *key_str = yyjson_get_str(key);
						if (key_str) {
							std::string key_s(key_str);
							if (key_s.size() > prefix.size() && key_s.substr(0, prefix.size()) == prefix &&
							    std::isupper(static_cast<unsigned char>(key_s[prefix.size()]))) {
								std::string choice_type = key_s.substr(prefix.size());
								yyjson_val *choice_val = yyjson_obj_iter_get_val(key);
								if (choice_val) {
									add_flattened(choice_val, field_name, choice_type);
								}
								break;
							}
						}
					}
				}
			}
		} else if (yyjson_is_arr(val)) {
			size_t idx2, max2;
			yyjson_val *elem;
			yyjson_arr_foreach(val, idx2, max2, elem) {
				if (yyjson_is_obj(elem)) {
					yyjson_val *child = yyjson_obj_get(elem, field_name.c_str());
					if (child) {
						add_flattened(child, field_name, infer_fhir_type(field_name));
					}
				}
			}
		}
	}
	return result;
}

FPCollection Evaluator::evalIndexer(const ASTNode &node, const FPCollection &input, yyjson_doc *doc) {
	auto source_col = node.source ? eval(*node.source, input, doc) : input;
	if (node.children.empty()) {
		return {};
	}
	auto index_col = eval(*node.children[0], input, doc);
	if (index_col.empty()) {
		return {};
	}
	if (index_col.size() > 1) {
		throw FHIRPathSpecError("Indexer requires a single integer index");
	}

	int64_t idx = 0;
	if (!extractStrictInteger(index_col[0], idx)) {
		throw FHIRPathSpecError("Indexer requires an integer index");
	}

	if (idx >= 0 && static_cast<size_t>(idx) < source_col.size()) {
		return {source_col[static_cast<size_t>(idx)]};
	}
	return {};
}

FPCollection Evaluator::evalWhere(const ASTNode &node, const FPCollection &input, yyjson_doc *doc) {
	if (node.children.size() != 1) {
		throw FHIRPathSpecError("where() takes exactly 1 criteria argument");
	}
	FPCollection result;
	int64_t idx = 0;
	auto saved_chain_vars = chain_defined_vars_;
	auto saved_defined_vars = defined_variables_;
	for (const auto &item : input) {
		FPCollection single = {item};
		int64_t old_index = index_context_;
		index_context_ = idx;
		chain_defined_vars_ = saved_chain_vars;
		defined_variables_ = saved_defined_vars;
		auto criteria_result = eval(*node.children[0], single, doc);
		index_context_ = old_index;
		defined_variables_ = saved_defined_vars;
		if (isCriteriaTrue(criteria_result, "where")) {
			result.push_back(item);
		}
		++idx;
	}
	chain_defined_vars_ = saved_chain_vars;
	defined_variables_ = saved_defined_vars;
	return result;
}

FPCollection Evaluator::evalExists(const ASTNode &node, const FPCollection &input, yyjson_doc *doc) {
	if (node.children.size() > 1) {
		throw FHIRPathSpecError("exists() takes at most 1 criteria argument");
	}
	if (node.children.empty()) {
		return {FPValue::FromBoolean(!input.empty())};
	}
	// exists(criteria) is specified as where(criteria).exists(), so validate
	// every criteria result before returning whether any item matched.
	auto saved_chain_vars = chain_defined_vars_;
	auto saved_index_context = index_context_;
	auto saved_defined_vars = defined_variables_;
	int64_t idx = 0;
	bool any_match = false;
	try {
		for (const auto &item : input) {
			FPCollection single = {item};
			chain_defined_vars_ = saved_chain_vars;
			index_context_ = idx;
			defined_variables_ = saved_defined_vars;
			auto criteria_result = eval(*node.children[0], single, doc);
			if (isCriteriaTrue(criteria_result, "exists")) {
				any_match = true;
			}
			++idx;
		}
	} catch (const std::exception &) {
		chain_defined_vars_ = saved_chain_vars;
		index_context_ = saved_index_context;
		defined_variables_ = saved_defined_vars;
		throw;
	}
	chain_defined_vars_ = saved_chain_vars;
	index_context_ = saved_index_context;
	defined_variables_ = saved_defined_vars;
	return {FPValue::FromBoolean(any_match)};
}

FPCollection Evaluator::evalOfType(const ASTNode &node, const FPCollection &input, yyjson_doc *doc) {
	if (node.children.size() != 1) {
		throw FHIRPathSpecError("ofType() takes exactly 1 type argument");
	}
	// Build qualified type name
	std::string target_type;
	if (node.children[0]->type == NodeType::MemberAccess && node.children[0]->source) {
		// Qualified: Namespace.Type (e.g., FHIR.Patient)
		std::string prefix;
		ASTNode *n = node.children[0]->source.get();
		while (n && n->type == NodeType::MemberAccess && n->source) {
			prefix = n->name + "." + prefix;
			n = n->source.get();
		}
		if (n && n->type == NodeType::MemberAccess) {
			prefix = n->name + "." + prefix;
		}
		target_type = prefix + node.children[0]->name;
	} else if (node.children[0]->type == NodeType::MemberAccess) {
		target_type = node.children[0]->name;
	} else if (node.children[0]->type == NodeType::StringLiteral) {
		throw FHIRPathSpecError("ofType() argument must be a type specifier");
	} else {
		target_type = node.children[0]->name;
	}

	FPCollection result;
	std::string base_target = target_type;
	auto dot_pos = base_target.find('.');
	if (dot_pos != std::string::npos) {
		base_target = base_target.substr(dot_pos + 1);
	}
	if (base_target.size() >= 2 && base_target.front() == '`' && base_target.back() == '`') {
		base_target = base_target.substr(1, base_target.size() - 2);
	}
	bool exact = !base_target.empty() && std::islower(static_cast<unsigned char>(base_target[0]));
	// FHIRPath §5.2.4 requires the type argument to resolve to a model type.
	// Validate before iterating so empty inputs cannot mask unknown types.
	(void)fn_isType({}, target_type, exact);
	for (const auto &item : input) {
		FPCollection single = {item};
		auto is_result = fn_isType(single, target_type, exact);
		if (!is_result.empty() && is_result[0].type == FPValue::Type::Boolean && is_result[0].bool_val) {
			result.push_back(item);
		}
	}
	return result;
}

// Helper: evaluate function argument with chain scope isolation
FPCollection Evaluator::evalArgIsolated(const ASTNode &arg_node, const FPCollection &ctx, yyjson_doc *doc) {
	auto saved_chain = chain_defined_vars_;
	chain_defined_vars_.clear();
	auto result = eval(arg_node, ctx, doc);
	chain_defined_vars_ = saved_chain;
	return result;
}

FPCollection Evaluator::evalFunction(const ASTNode &node, const FPCollection &input, yyjson_doc *doc, const FPCollection *outer_input) {
	const auto &name = node.name;

	// Factory method dispatch
	if (!input.empty() && input[0].type == FPValue::Type::String && input[0].string_val == "__fhirpath_factory__") {
		return evalFactoryMethod(node, doc);
	}

	const size_t arg_count = node.children.size();
	if ((name == "single" || name == "first" || name == "last" || name == "tail") && arg_count != 0) {
		throw FHIRPathSpecError(name + "() takes no arguments");
	}
	if (name == "not" && arg_count != 0) {
		throw FHIRPathSpecError("not() takes no arguments");
	}
	if ((name == "skip" || name == "take" || name == "combine" || name == "intersect" ||
	     name == "exclude" || name == "union") && arg_count != 1) {
		throw FHIRPathSpecError(name + "() takes exactly 1 argument");
	}
	if ((name == "indexOf" || name == "startsWith" || name == "endsWith" || name == "contains") &&
	    arg_count != 1) {
		throw FHIRPathSpecError(name + "() takes exactly 1 argument");
	}
	if (name == "substring" && !(arg_count == 1 || arg_count == 2)) {
		throw FHIRPathSpecError("substring() takes 1 or 2 arguments");
	}
	if ((name == "upper" || name == "lower" || name == "length" || name == "toChars") && arg_count != 0) {
		throw FHIRPathSpecError(name + "() takes no arguments");
	}
	if (name == "matches" && arg_count != 1) {
		throw FHIRPathSpecError("matches() takes exactly 1 argument");
	}
	if ((name == "replace" || name == "replaceMatches") && arg_count != 2) {
		throw FHIRPathSpecError(name + "() takes exactly 2 arguments");
	}
	if (name == "iif" && !(arg_count == 2 || arg_count == 3)) {
		throw FHIRPathSpecError("iif() takes 2 or 3 arguments");
	}
	if (name == "aggregate" && !(arg_count == 1 || arg_count == 2)) {
		throw FHIRPathSpecError("aggregate() takes 1 or 2 arguments");
	}
	if (name == "where" && arg_count != 1) {
		throw FHIRPathSpecError("where() takes exactly 1 criteria argument");
	}
	if ((name == "empty" || name == "count" || name == "distinct" || name == "isDistinct" ||
	     name == "hasValue" ||
	     name == "allTrue" || name == "anyTrue" || name == "allFalse" || name == "anyFalse") &&
	    arg_count != 0) {
		throw FHIRPathSpecError(name + "() takes no arguments");
	}
	if (name == "exists" && arg_count > 1) {
		throw FHIRPathSpecError("exists() takes at most 1 criteria argument");
	}
	if ((name == "all" || name == "subsetOf" || name == "supersetOf") && arg_count != 1) {
		throw FHIRPathSpecError(name + "() takes exactly 1 argument");
	}
	if ((name == "toBoolean" || name == "toInteger") && arg_count != 0) {
		throw FHIRPathSpecError(name + "() takes no arguments");
	}
	if ((name == "toDecimal" || name == "toDate" || name == "toDateTime") && arg_count != 0) {
		throw FHIRPathSpecError(name + "() takes no arguments");
	}
	if ((name == "toString" || name == "toTime" ||
	     name == "convertsToString" || name == "convertsToTime") && arg_count != 0) {
		throw FHIRPathSpecError(name + "() takes no arguments");
	}
	if ((name == "toQuantity" || name == "convertsToQuantity") && arg_count > 1) {
		throw FHIRPathSpecError(name + "() takes at most 1 argument");
	}
	if ((name == "convertsToBoolean" || name == "convertsToInteger") && arg_count != 0) {
		throw FHIRPathSpecError(name + "() takes no arguments");
	}
	if ((name == "convertsToDecimal" || name == "convertsToDate" || name == "convertsToDateTime") && arg_count != 0) {
		throw FHIRPathSpecError(name + "() takes no arguments");
	}
	if ((name == "abs" || name == "ceiling" || name == "exp" || name == "floor" ||
	     name == "ln" || name == "sqrt" || name == "truncate") && arg_count != 0) {
		throw FHIRPathSpecError(name + "() takes no arguments");
	}
	if ((name == "log" || name == "power") && arg_count != 1) {
		throw FHIRPathSpecError(name + "() takes exactly 1 argument");
	}
	if (name == "round" && !(arg_count == 0 || arg_count == 1)) {
		throw FHIRPathSpecError("round() takes 0 or 1 arguments");
	}
	if ((name == "children" || name == "descendants" || name == "now" ||
	     name == "today" || name == "timeOfDay") && arg_count != 0) {
		throw FHIRPathSpecError(name + "() takes no arguments");
	}
	if (name == "trace" && !(arg_count == 1 || arg_count == 2)) {
		throw FHIRPathSpecError("trace() takes 1 or 2 arguments");
	}
	if (name == "defineVariable" && !(arg_count == 1 || arg_count == 2)) {
		throw FHIRPathSpecError("defineVariable() takes 1 or 2 arguments");
	}

	// Singleton Enforcement (FHIRPath 5.2, 5.3, 5.4)
	if (input.size() > 1) {
		if (name == "indexOf" || name == "substring" || name == "startsWith" || name == "endsWith" || 
		    name == "contains" || name == "upper" || name == "lower" || name == "replace" || 
		    name == "matches" || name == "replaceMatches" || name == "length" || name == "toChars" ||
		    name == "abs" || name == "ceiling" || name == "exp" || name == "floor" || name == "ln" || 
		    name == "log" || name == "power" || name == "round" || name == "sqrt" || name == "truncate" ||
		    name == "toInteger" || name == "toDecimal" || name == "toString" || name == "toDate" || 
		    name == "toDateTime" || name == "toTime" || name == "toQuantity" || name == "toBoolean" ||
		    name == "convertsToInteger" || name == "convertsToDecimal" || name == "convertsToString" || 
		    name == "convertsToDate" || name == "convertsToDateTime" || name == "convertsToTime" || 
		    name == "convertsToQuantity" || name == "convertsToBoolean" || name == "iif") {
			throw FHIRPathSpecError(name + "() requires a single item input collection");
		}
	}

	// No-argument functions
	if (name == "count") {
		return fn_count(input);
	}
	if (name == "first") {
		return fn_first(input);
	}
	if (name == "last") {
		return fn_last(input);
	}
	if (name == "single") {
		return fn_single(input);
	}
	if (name == "empty") {
		return fn_empty(input);
	}
	if (name == "hasValue") {
		return fn_hasValue(input);
	}
	if (name == "not") {
		return fn_not(input);
	}
	if (name == "where") {
		return evalWhere(node, input, doc);
	}
	if (name == "allTrue") {
		return fn_allTrue(input);
	}
	if (name == "anyTrue") {
		return fn_anyTrue(input);
	}
	if (name == "allFalse") {
		return fn_allFalse(input);
	}
	if (name == "anyFalse") {
		return fn_anyFalse(input);
	}
	if (name == "length") {
		return fn_length(input);
	}
	if (name == "upper") {
		return fn_upper(input);
	}
	if (name == "lower") {
		return fn_lower(input);
	}
	if (name == "trim") {
		return fn_trim(input);
	}
	if (name == "toInteger") {
		return fn_toInteger(input);
	}
	if (name == "toDecimal") {
		return fn_toDecimal(input);
	}
	if (name == "toString") {
		return fn_toString(input);
	}
	if (name == "toDate") {
		return fn_toDate(input);
	}
	if (name == "toDateTime") {
		return fn_toDateTime(input);
	}
	if (name == "toBoolean") {
		return fn_toBoolean(input);
	}
	if (name == "toQuantity") {
		std::string to_unit;
		if (!node.children.empty()) {
			auto arg = evalArgIsolated(*node.children[0], input, doc);
			if (arg.empty()) return {};
			if (arg.size() > 1 || effectiveType(arg[0]) != FPValue::Type::String) {
				throw FHIRPathSpecError("toQuantity() unit argument must be a single String");
			}
			to_unit = toString(arg[0]);
		}
		return fn_toQuantity(input, to_unit);
	}
	if (name == "abs") {
		return fn_abs(input);
	}
	if (name == "ceiling") {
		return fn_ceiling(input);
	}
	if (name == "floor") {
		return fn_floor(input);
	}
	if (name == "sqrt") {
		return fn_sqrt(input);
	}
	if (name == "truncate") {
		return fn_truncate(input);
	}
	if (name == "distinct") {
		return fn_distinct(input);
	}
	if (name == "trace") {
		FPCollection label_ctx = outer_input ? *outer_input : input;
		auto label = evalArgIsolated(*node.children[0], label_ctx, doc);
		if (label.empty()) return {};
		if (label.size() > 1 || effectiveType(label[0]) != FPValue::Type::String) {
			throw FHIRPathSpecError("trace() name argument must be a single String");
		}
		if (node.children.size() == 2) {
			(void)evalArgIsolated(*node.children[1], input, doc);
		}
		return fn_trace(input);
	}
	if (name == "tail") {
		return fn_tail(input);
	}
	if (name == "join") {
		// join() with no args uses empty string as separator
		if (node.children.empty()) {
			std::string result;
			for (size_t i = 0; i < input.size(); i++) {
				result += toString(input[i]);
			}
			return {FPValue::FromString(result)};
		}
	}
	if (name == "empty_collection") {
		return {};
	}
	if (name == "children") {
		return fn_children(input);
	}
	if (name == "descendants") {
		return fn_descendants(input);
	}
	if (name == "convertsToBoolean") {
		return fn_convertsToBoolean(input);
	}
	if (name == "convertsToInteger") {
		return fn_convertsToInteger(input);
	}
	if (name == "convertsToDecimal") {
		return fn_convertsToDecimal(input);
	}
	if (name == "convertsToString") {
		return fn_convertsToString(input);
	}
	if (name == "convertsToDate") {
		return fn_convertsToDate(input);
	}
	if (name == "convertsToDateTime") {
		return fn_convertsToDateTime(input);
	}
	if (name == "convertsToTime") {
		return fn_convertsToTime(input);
	}
	if (name == "convertsToQuantity") {
		std::string to_unit;
		if (!node.children.empty()) {
			auto arg = evalArgIsolated(*node.children[0], input, doc);
			if (arg.empty()) return {};
			if (arg.size() > 1 || effectiveType(arg[0]) != FPValue::Type::String) {
				throw FHIRPathSpecError("convertsToQuantity() unit argument must be a single String");
			}
			to_unit = toString(arg[0]);
		}
		return fn_convertsToQuantity(input, to_unit);
	}
	if (name == "toTime") {
		return fn_toTime(input);
	}
	if (name == "type") {
		if (!node.children.empty()) {
			throw FHIRPathSpecError("type() takes no arguments");
		}
		if (input.empty()) return {};
		FPCollection result;
		for (const auto &val : input) {
			auto t = effectiveType(val);
			std::string ns, nm;
			bool is_fhir = (val.type == FPValue::Type::JsonVal);
			if (is_fhir && !val.fhir_type.empty()) {
				ns = "FHIR";
				nm = normalizeFHIRChoiceTypeName(val.fhir_type);
			} else {
				switch (t) {
				case FPValue::Type::Boolean:
					if (is_fhir) { ns = "FHIR"; nm = "boolean"; } else { ns = "System"; nm = "Boolean"; }
					break;
				case FPValue::Type::Integer:
					if (is_fhir) { ns = "FHIR"; nm = "integer"; } else { ns = "System"; nm = "Integer"; }
					break;
				case FPValue::Type::Decimal:
					if (is_fhir) { ns = "FHIR"; nm = "decimal"; } else { ns = "System"; nm = "Decimal"; }
					break;
				case FPValue::Type::String:
					if (is_fhir) {
						ns = "FHIR";
						const char *actual_type = fhirFieldType(val.field_name);
						nm = actual_type ? actual_type : "string";
					} else {
						ns = "System";
						nm = "String";
					}
					break;
				case FPValue::Type::Date:
					if (is_fhir) { ns = "FHIR"; nm = "date"; } else { ns = "System"; nm = "Date"; }
					break;
				case FPValue::Type::DateTime:
					if (is_fhir) { ns = "FHIR"; nm = "dateTime"; } else { ns = "System"; nm = "DateTime"; }
					break;
				case FPValue::Type::Time:
					if (is_fhir) { ns = "FHIR"; nm = "time"; } else { ns = "System"; nm = "Time"; }
					break;
				case FPValue::Type::Quantity:
					ns = "System"; nm = "Quantity";
					break;
				default:
					if (val.type == FPValue::Type::JsonVal && val.json_val && yyjson_is_obj(val.json_val)) {
						yyjson_val *rt = yyjson_obj_get(val.json_val, "resourceType");
						if (rt && yyjson_is_str(rt)) {
							ns = "FHIR";
							nm = yyjson_get_str(rt);
						} else if (yyjson_obj_get(val.json_val, "reference")) {
							ns = "FHIR";
							nm = "Reference";
						} else if (yyjson_obj_get(val.json_val, "contentType")) {
							ns = "FHIR";
							nm = "Attachment";
						} else if (val.field_name == "name") {
							ns = "FHIR";
							nm = "HumanName";
						} else if (val.field_name == "address") {
							ns = "FHIR";
							nm = "Address";
						} else if (val.field_name == "identifier") {
							ns = "FHIR";
							nm = "Identifier";
						} else if (val.field_name == "telecom") {
							ns = "FHIR";
							nm = "ContactPoint";
						} else if (val.field_name == "coding") {
							ns = "FHIR";
							nm = "Coding";
						} else if (val.field_name == "code") {
							ns = "FHIR";
							nm = "CodeableConcept";
						} else {
							ns = "FHIR";
							nm = "BackboneElement";
						}
					}
					break;
				}
			}
			std::string json_str = "{\"name\":\"" + escapeJsonString(nm) + "\",\"namespace\":\"" + escapeJsonString(ns) + "\"}";
			yyjson_doc *type_doc = yyjson_read(json_str.c_str(), json_str.size(), 0);
			if (type_doc) {
				owned_docs_.push_back(type_doc);
				yyjson_val *type_root = yyjson_doc_get_root(type_doc);
				result.push_back(FPValue::FromJson(type_root));
			}
		}
		return result;
	}
	if (name == "conformsTo") {
		if (node.children.empty()) return {};
		FPCollection arg_ctx = outer_input ? *outer_input : input;
		auto arg = evalArgIsolated(*node.children[0], arg_ctx, doc);
		if (arg.empty() || input.empty()) return {};
		std::string profile = toString(arg[0]);
		for (const auto &item : input) {
			if (item.type == FPValue::Type::JsonVal && item.json_val && yyjson_is_obj(item.json_val)) {
				yyjson_val *rt = yyjson_obj_get(item.json_val, "resourceType");
				if (rt && yyjson_is_str(rt)) {
					std::string rtype = yyjson_get_str(rt);
					auto lastSlash = profile.rfind('/');
					if (lastSlash != std::string::npos) {
						std::string profileType = profile.substr(lastSlash + 1);
						if (rtype == profileType) return {FPValue::FromBoolean(true)};
						// Known FHIR StructureDefinition URL format - we can determine it's a different type
						if (profile.find("hl7.org/fhir/StructureDefinition/") != std::string::npos) {
							return {FPValue::FromBoolean(false)};
						}
					}
				}
			}
		}
		return {};
	}
	if (name == "htmlChecks" || name == "htmlChecks2") {
		if (input.empty()) return {};
		std::string html = toString(input[0]);
		static const char* blocked_tags[] = {
			"script", "style", "iframe", "object", "embed", "applet",
			"form", "input", "button", "select", "textarea",
			"frame", "frameset", "link", "meta", "base", NULL
		};
		bool valid = true;
		for (size_t pos = 0; pos < html.size() && valid; pos++) {
			if (html[pos] == '<' && pos + 1 < html.size() && html[pos+1] != '/' && html[pos+1] != '!') {
				size_t start = pos + 1;
				size_t end = start;
				while (end < html.size() && html[end] != ' ' && html[end] != '>' && html[end] != '/' && html[end] != '\t' && html[end] != '\n') {
					end++;
				}
				std::string tag;
				for (size_t j = start; j < end; j++) {
					tag += (char)std::tolower((unsigned char)html[j]);
				}
				for (int k = 0; blocked_tags[k]; k++) {
					if (tag == blocked_tags[k]) {
						valid = false;
						break;
					}
				}
				if (valid && end < html.size()) {
					size_t attr_end = html.find('>', end);
					if (attr_end != std::string::npos) {
						std::string attrs = html.substr(end, attr_end - end);
						std::string lower_attrs;
						for (size_t j = 0; j < attrs.size(); j++) {
							lower_attrs += (char)std::tolower((unsigned char)attrs[j]);
						}
						size_t opos = 0;
						while ((opos = lower_attrs.find(" on", opos)) != std::string::npos) {
							size_t eq = lower_attrs.find('=', opos + 3);
							if (eq != std::string::npos) {
								bool is_attr = true;
								for (size_t j = opos + 3; j < eq; j++) {
									if (!std::isalpha((unsigned char)lower_attrs[j])) {
										is_attr = false;
										break;
									}
								}
								if (is_attr && eq > opos + 3) {
									valid = false;
									break;
								}
							}
							opos += 3;
						}
					}
				}
			}
		}
		return {FPValue::FromBoolean(valid)};
	}
	if (name == "getValue") {
		// Returns the FHIR primitive value
		if (input.empty()) return {};
		return input;
	}
	if (name == "getResourceKey") {
		if (!node.children.empty()) {
			throw FHIRPathSpecError("getResourceKey() takes no arguments");
		}
		FPCollection result;
		for (const auto &item : input) {
			if (item.type != FPValue::Type::JsonVal || !item.json_val || !yyjson_is_obj(item.json_val)) {
				continue;
			}
			yyjson_val *resource_type = yyjson_obj_get(item.json_val, "resourceType");
			yyjson_val *id = yyjson_obj_get(item.json_val, "id");
			if (resource_type && yyjson_is_str(resource_type) && id && yyjson_is_str(id)) {
				result.push_back(FPValue::FromString(
				    std::string(yyjson_get_str(resource_type)) + "/" + yyjson_get_str(id)));
			}
		}
		return result;
	}
	if (name == "getReferenceKey") {
		if (node.children.size() > 1) {
			throw FHIRPathSpecError("getReferenceKey() takes at most one type argument");
		}
		std::string type_filter;
		if (!node.children.empty()) {
			type_filter = typeNameFromSpecifierNode(*node.children[0]);
			fn_isType({}, type_filter);
			auto dot_pos = type_filter.find('.');
			if (dot_pos != std::string::npos) {
				type_filter = type_filter.substr(dot_pos + 1);
			}
			if (type_filter.size() >= 2 && type_filter.front() == '`' && type_filter.back() == '`') {
				type_filter = type_filter.substr(1, type_filter.size() - 2);
			}
		}
		FPCollection result;
		for (const auto &item : input) {
			if (item.type != FPValue::Type::JsonVal || !item.json_val || !yyjson_is_obj(item.json_val)) {
				continue;
			}
			yyjson_val *reference = yyjson_obj_get(item.json_val, "reference");
			if (!reference || !yyjson_is_str(reference)) {
				continue;
			}
			std::string ref = yyjson_get_str(reference);
			if (!type_filter.empty() && ref.find(type_filter + "/") != 0) {
				continue;
			}
			result.push_back(FPValue::FromString(ref));
		}
		return result;
	}
	if (name == "checkModifiers") {
		if (input.empty()) return {};
		std::vector<std::string> allowed;
		for (size_t ci = 0; ci < node.children.size(); ci++) {
			auto child_result = eval(*node.children[ci], input, doc);
			for (const auto &a : child_result) {
				allowed.push_back(toString(a));
			}
		}
		for (const auto &item : input) {
			if (item.type == FPValue::Type::JsonVal && item.json_val && yyjson_is_obj(item.json_val)) {
				yyjson_val *mod_ext = yyjson_obj_get(item.json_val, "modifierExtension");
				if (mod_ext && yyjson_is_arr(mod_ext)) {
					size_t idx3, max3;
					yyjson_val *ext;
					yyjson_arr_foreach(mod_ext, idx3, max3, ext) {
						yyjson_val *url_val = yyjson_obj_get(ext, "url");
						if (url_val && yyjson_is_str(url_val)) {
							std::string url = yyjson_get_str(url_val);
							bool found = false;
							for (const auto &a : allowed) {
								if (a == url) { found = true; break; }
							}
							if (!found) {
								throw FHIRPathSpecError("Unknown modifier extension: " + url);
							}
						}
					}
				}
			}
		}
		return input;
	}
	if (name == "hasTemplateIdOf") {
		if (input.empty()) return {};
		if (node.children.empty()) return {};
		auto arg_result = eval(*node.children[0], input, doc);
		if (arg_result.empty()) return {};
		std::string profile_url = toString(arg_result[0]);

		for (size_t i = 0; i < input.size(); i++) {
			const auto &item = input[i];
			if (item.type != FPValue::Type::JsonVal || !item.json_val || !yyjson_is_obj(item.json_val))
				continue;

			// Check explicit templateId field
			yyjson_val *tmpl_arr = yyjson_obj_get(item.json_val, "templateId");
			if (tmpl_arr) {
				if (yyjson_is_arr(tmpl_arr)) {
					size_t idx4, max4;
					yyjson_val *tmpl;
					yyjson_arr_foreach(tmpl_arr, idx4, max4, tmpl) {
						if (yyjson_is_obj(tmpl)) {
							yyjson_val *root_val = yyjson_obj_get(tmpl, "root");
							if (!root_val) root_val = yyjson_obj_get(tmpl, "@root");
							if (root_val && yyjson_is_str(root_val) && std::string(yyjson_get_str(root_val)) == profile_url) {
								return {FPValue::FromBoolean(true)};
							}
						} else if (yyjson_is_str(tmpl)) {
							if (std::string(yyjson_get_str(tmpl)) == profile_url) {
								return {FPValue::FromBoolean(true)};
							}
						}
					}
				} else if (yyjson_is_obj(tmpl_arr)) {
					yyjson_val *root_val = yyjson_obj_get(tmpl_arr, "root");
					if (!root_val) root_val = yyjson_obj_get(tmpl_arr, "@root");
					if (root_val && yyjson_is_str(root_val) && std::string(yyjson_get_str(root_val)) == profile_url) {
						return {FPValue::FromBoolean(true)};
					}
				}
			}

			// Structural matching fallback for known CDA types
			if (profile_url.find("ContinuityofCareDocumentCCD") != std::string::npos) {
				yyjson_val *rt = yyjson_obj_get(item.json_val, "resourceType");
				bool is_clinical_doc = (rt && yyjson_is_str(rt) && std::string(yyjson_get_str(rt)) == "ClinicalDocument");
				if (is_clinical_doc) {
					bool has_component = yyjson_obj_get(item.json_val, "component") != nullptr;
					bool has_record_target = yyjson_obj_get(item.json_val, "recordTarget") != nullptr;
					bool has_title = yyjson_obj_get(item.json_val, "title") != nullptr;
					if (has_component && has_record_target && has_title) {
						return {FPValue::FromBoolean(true)};
					}
				}
			}
		}
		return {FPValue::FromBoolean(false)};
	}
	if (name == "isDistinct") {
		return fn_isDistinct(input);
	}
	if (name == "resolve") {
		if (input.empty()) return {};
		FPCollection result;
		for (size_t idx = 0; idx < input.size(); idx++) {
			const auto &item = input[idx];
			std::string ref;
			if (item.type == FPValue::Type::JsonVal && item.json_val && yyjson_is_obj(item.json_val)) {
				yyjson_val *ref_val = yyjson_obj_get(item.json_val, "reference");
				if (ref_val && yyjson_is_str(ref_val)) {
					ref = yyjson_get_str(ref_val);
				}
			} else if (item.type == FPValue::Type::String) {
				ref = item.string_val;
			} else if (item.type == FPValue::Type::JsonVal && item.json_val && yyjson_is_str(item.json_val)) {
				ref = yyjson_get_str(item.json_val);
			}
			if (ref.empty()) continue;

			if (ref[0] == '#') {
				// Contained reference
				std::string target_id = ref.substr(1);
				if (resource_context_ && yyjson_is_obj(resource_context_)) {
					yyjson_val *contained = yyjson_obj_get(resource_context_, "contained");
					if (contained && yyjson_is_arr(contained)) {
						size_t ci, cmax;
						yyjson_val *cres;
						yyjson_arr_foreach(contained, ci, cmax, cres) {
							if (yyjson_is_obj(cres)) {
								yyjson_val *id_val = yyjson_obj_get(cres, "id");
								if (id_val && yyjson_is_str(id_val) &&
								    std::string(yyjson_get_str(id_val)) == target_id) {
									result.push_back(FPValue::FromJson(cres));
									break;
								}
							}
						}
					}
				}
			} else if (ref.find('/') != std::string::npos) {
				// Bundle reference: Type/id or full URL
				std::string ref_type, ref_id;
				size_t slash = ref.rfind('/');
				ref_id = ref.substr(slash + 1);
				std::string before_slash = ref.substr(0, slash);
				size_t prev_slash = before_slash.rfind('/');
				if (prev_slash != std::string::npos) {
					ref_type = before_slash.substr(prev_slash + 1);
				} else {
					ref_type = before_slash;
				}

				if (resource_context_ && yyjson_is_obj(resource_context_)) {
					yyjson_val *rt = yyjson_obj_get(resource_context_, "resourceType");
					if (rt && yyjson_is_str(rt) && std::string(yyjson_get_str(rt)) == "Bundle") {
						yyjson_val *entries = yyjson_obj_get(resource_context_, "entry");
						if (entries && yyjson_is_arr(entries)) {
							size_t ei, emax;
							yyjson_val *entry;
							bool found = false;
							yyjson_arr_foreach(entries, ei, emax, entry) {
								if (!yyjson_is_obj(entry)) continue;
								yyjson_val *eres = yyjson_obj_get(entry, "resource");
								if (!eres || !yyjson_is_obj(eres)) continue;
								yyjson_val *ert = yyjson_obj_get(eres, "resourceType");
								yyjson_val *eid = yyjson_obj_get(eres, "id");
								if (ert && yyjson_is_str(ert) && eid && yyjson_is_str(eid)) {
									if (std::string(yyjson_get_str(ert)) == ref_type &&
									    std::string(yyjson_get_str(eid)) == ref_id) {
										result.push_back(FPValue::FromJson(eres));
										found = true;
										break;
									}
								}
								if (!found) {
									yyjson_val *full_url = yyjson_obj_get(entry, "fullUrl");
									if (full_url && yyjson_is_str(full_url) &&
									    std::string(yyjson_get_str(full_url)) == ref) {
										result.push_back(FPValue::FromJson(eres));
										found = true;
										break;
									}
								}
							}
						}
					}
				}
			}
		}
		return result;
	}
	if (name == "sort") {
		if (node.children.empty()) {
			std::vector<const ASTNode *> empty_criteria;
			return fn_sort(empty_criteria, input, doc);
		}
	}
	if (name == "toChars") {
		if (input.empty()) return {};
		if (input.size() > 1) {
			throw FHIRPathSpecError("toChars() requires a single item input");
		}
		if (effectiveType(input[0]) != FPValue::Type::String) {
			throw FHIRPathSpecError("toChars() requires a String input");
		}
		std::string s = toString(input[0]);
		FPCollection result;
		size_t byte = 0;
		while (byte < s.size()) {
			unsigned char c = static_cast<unsigned char>(s[byte]);
			size_t char_bytes;
			if (c < 0x80)      char_bytes = 1;
			else if (c < 0xE0) char_bytes = 2;
			else if (c < 0xF0) char_bytes = 3;
			else               char_bytes = 4;
			result.push_back(FPValue::FromString(s.substr(byte, char_bytes)));
			byte += char_bytes;
		}
		return result;
	}
	if (name == "now") {
		time_t t = currentTime();
		struct tm tm_buf;
		gmtime_r(&t, &tm_buf);
		char buf[64];
		std::snprintf(buf, sizeof(buf), "%04d-%02d-%02dT%02d:%02d:%02d+00:00",
		              tm_buf.tm_year + 1900, tm_buf.tm_mon + 1, tm_buf.tm_mday,
		              tm_buf.tm_hour, tm_buf.tm_min, tm_buf.tm_sec);
		FPValue v; v.type = FPValue::Type::DateTime; v.string_val = buf;
		return {v};
	}
	if (name == "today") {
		time_t t = currentTime();
		struct tm tm_buf;
		gmtime_r(&t, &tm_buf);
		char buf[32];
		std::snprintf(buf, sizeof(buf), "%04d-%02d-%02d", tm_buf.tm_year + 1900, tm_buf.tm_mon + 1, tm_buf.tm_mday);
		FPValue v; v.type = FPValue::Type::Date; v.string_val = buf;
		return {v};
	}
	if (name == "timeOfDay") {
		time_t t = currentTime();
		struct tm tm_buf;
		gmtime_r(&t, &tm_buf);
		char buf[32];
		std::snprintf(buf, sizeof(buf), "%02d:%02d:%02d.000", tm_buf.tm_hour, tm_buf.tm_min, tm_buf.tm_sec);
		FPValue v; v.type = FPValue::Type::Time; v.string_val = buf;
		return {v};
	}

	// Date/DateTime component extraction functions
	if (name == "yearOf" || name == "monthOf" || name == "dayOf" ||
	    name == "hourOf" || name == "minuteOf" || name == "secondOf" || name == "millisecondOf" ||
	    name == "timezoneOffsetOf") {
		// These are singleton functions - return empty for non-singleton input
		if (input.size() != 1) return {};
		auto &item = input[0];
		std::string dt_str;
		auto t = effectiveType(item);
		if (t == FPValue::Type::Date || t == FPValue::Type::DateTime || t == FPValue::Type::Time || t == FPValue::Type::String) {
			dt_str = toString(item);
		} else return {};
		if (dt_str.empty()) return {};

		// Strip leading 'T' for time values
		std::string time_str = dt_str;
		if (t == FPValue::Type::Time && !time_str.empty() && time_str[0] == 'T') {
			time_str = time_str.substr(1);
		}

		if (name == "yearOf") {
			if (t == FPValue::Type::Time) return {};
			if (dt_str.size() >= 4) return {FPValue::FromInteger(std::stoi(dt_str.substr(0, 4)))};
		} else if (name == "monthOf") {
			if (t == FPValue::Type::Time) return {};
			if (dt_str.size() >= 7) return {FPValue::FromInteger(std::stoi(dt_str.substr(5, 2)))};
		} else if (name == "dayOf") {
			if (t == FPValue::Type::Time) return {};
			if (dt_str.size() >= 10) return {FPValue::FromInteger(std::stoi(dt_str.substr(8, 2)))};
		} else if (name == "hourOf") {
			if (t == FPValue::Type::Time) {
				if (time_str.size() >= 2) return {FPValue::FromInteger(std::stoi(time_str.substr(0, 2)))};
			} else {
				auto tpos = dt_str.find('T');
				if (tpos != std::string::npos && dt_str.size() >= tpos + 3)
					return {FPValue::FromInteger(std::stoi(dt_str.substr(tpos + 1, 2)))};
			}
		} else if (name == "minuteOf") {
			if (t == FPValue::Type::Time) {
				if (time_str.size() >= 5) return {FPValue::FromInteger(std::stoi(time_str.substr(3, 2)))};
			} else {
				auto tpos = dt_str.find('T');
				if (tpos != std::string::npos && dt_str.size() >= tpos + 6)
					return {FPValue::FromInteger(std::stoi(dt_str.substr(tpos + 4, 2)))};
			}
		} else if (name == "secondOf") {
			if (t == FPValue::Type::Time) {
				if (time_str.size() >= 8) return {FPValue::FromInteger(std::stoi(time_str.substr(6, 2)))};
			} else {
				auto tpos = dt_str.find('T');
				if (tpos != std::string::npos && dt_str.size() >= tpos + 9)
					return {FPValue::FromInteger(std::stoi(dt_str.substr(tpos + 7, 2)))};
			}
		} else if (name == "millisecondOf") {
			std::string search_str = (t == FPValue::Type::Time) ? time_str : dt_str;
			if (t != FPValue::Type::Time) {
				auto tpos = dt_str.find('T');
				if (tpos == std::string::npos) return {};
				search_str = dt_str.substr(tpos);
			}
			auto dotpos = search_str.find('.');
			if (dotpos != std::string::npos) {
				std::string ms_str;
				for (size_t i = dotpos + 1; i < search_str.size() && std::isdigit((unsigned char)search_str[i]); ++i)
					ms_str += search_str[i];
				while (ms_str.size() < 3) ms_str += '0';
				ms_str = ms_str.substr(0, 3);
				return {FPValue::FromInteger(std::stoi(ms_str))};
			}
		} else if (name == "timezoneOffsetOf") {
			// Return timezone offset in minutes as a Decimal
			size_t search_start = 0;
			auto tpos = dt_str.find('T');
			if (tpos != std::string::npos) search_start = tpos;
			for (size_t i = search_start; i < dt_str.size(); ++i) {
				if (dt_str[i] == 'Z') {
					return {FPValue::FromDecimal(0.0)};
				} else if ((dt_str[i] == '+' || dt_str[i] == '-') && i > search_start) {
					std::string tz = dt_str.substr(i);
					int sign = (tz[0] == '-') ? -1 : 1;
					int hours = 0, minutes = 0;
					if (tz.size() >= 3) hours = std::stoi(tz.substr(1, 2));
					if (tz.size() >= 6) minutes = std::stoi(tz.substr(4, 2));
					return {FPValue::FromDecimal(sign * (hours * 60 + minutes))};
				}
			}
		}
		return {};
	}

	// exp() and ln() math functions
	if (name == "exp") {
		if (input.empty()) return {};
		auto &val = input[0];
		if (!isNumericType(val)) {
			throw FHIRPathSpecError("exp() requires a numeric input");
		}
		double n = getNumericValue(val);
		double result = std::exp(n);
		if (std::isnan(result) || std::isinf(result)) return {};
		return {FPValue::FromDecimal(result)};
	}
	if (name == "ln") {
		if (input.empty()) return {};
		auto &val = input[0];
		if (!isNumericType(val)) {
			throw FHIRPathSpecError("ln() requires a numeric input");
		}
		double n = getNumericValue(val);
		if (n <= 0) return {};
		return {FPValue::FromDecimal(std::log(n))};
	}
	if (name == "log") {
		if (input.empty()) return {};
		FPCollection arg_ctx = outer_input ? *outer_input : input;
		auto arg = evalArgIsolated(*node.children[0], arg_ctx, doc);
		if (arg.empty()) return {};
		if (arg.size() > 1) {
			throw FHIRPathSpecError("log() base argument requires a single item collection");
		}
		auto &logVal = input[0];
		auto &baseVal = arg[0];
		if (!isNumericType(logVal)) {
			throw FHIRPathSpecError("log() requires a numeric input");
		}
		if (!isNumericType(baseVal)) {
			throw FHIRPathSpecError("log() base argument must be numeric");
		}
		double val = getNumericValue(logVal);
		double base = getNumericValue(baseVal);
		if (val <= 0 || base <= 0 || base == 1.0) return {};
		return {FPValue::FromDecimal(std::log(val) / std::log(base))};
	}

	// escape() and unescape() for HTML
	if (name == "escape") {
		if (input.empty()) return {};
		if (node.children.empty()) return {};
		auto arg = evalArgIsolated(*node.children[0], input, doc);
		if (arg.empty()) return {};
		std::string mode = toString(arg[0]);
		std::string s = toString(input[0]);
		if (mode == "html") {
			std::string result;
			for (size_t i = 0; i < s.size(); ++i) {
				switch (s[i]) {
				case '&': result += "&amp;"; break;
				case '<': result += "&lt;"; break;
				case '>': result += "&gt;"; break;
				case '"': result += "&quot;"; break;
				case '\'': result += "&#39;"; break;
				default: result += s[i]; break;
				}
			}
			return {FPValue::FromString(result)};
		}
		if (mode == "json") {
			std::string result;
			for (size_t i = 0; i < s.size(); ++i) {
				unsigned char c = static_cast<unsigned char>(s[i]);
				switch (c) {
				case '"':  result += "\\\""; break;
				case '\\': result += "\\\\"; break;
				case '\b': result += "\\b"; break;
				case '\f': result += "\\f"; break;
				case '\n': result += "\\n"; break;
				case '\r': result += "\\r"; break;
				case '\t': result += "\\t"; break;
				default:
					if (c < 0x20) {
						char buf[8];
						snprintf(buf, sizeof(buf), "\\u%04x", c);
						result += buf;
					} else {
						result += s[i];
					}
					break;
				}
			}
			return {FPValue::FromString(result)};
		}
		return {FPValue::FromString(s)};
	}
	if (name == "unescape") {
		if (input.empty()) return {};
		if (node.children.empty()) return {};
		auto arg = evalArgIsolated(*node.children[0], input, doc);
		if (arg.empty()) return {};
		std::string mode = toString(arg[0]);
		std::string s = toString(input[0]);
		if (mode == "html") {
			std::string result;
			for (size_t i = 0; i < s.size(); ++i) {
				if (s[i] == '&') {
					if (s.compare(i, 4, "&lt;") == 0) { result += '<'; i += 3; }
					else if (s.compare(i, 4, "&gt;") == 0) { result += '>'; i += 3; }
					else if (s.compare(i, 5, "&amp;") == 0) { result += '&'; i += 4; }
					else if (s.compare(i, 6, "&quot;") == 0) { result += '"'; i += 5; }
					else if (s.compare(i, 5, "&#39;") == 0) { result += '\''; i += 4; }
					else if (s.compare(i, 6, "&apos;") == 0) { result += '\''; i += 5; }
					else result += s[i];
				} else {
					result += s[i];
				}
			}
			return {FPValue::FromString(result)};
		}
		return {FPValue::FromString(s)};
	}

	// comparable() for quantities
	if (name == "comparable") {
		if (input.empty()) return {};
		if (node.children.empty()) return {};
		auto arg = evalArgIsolated(*node.children[0], input, doc);
		if (arg.empty()) return {FPValue::FromBoolean(false)};
		auto t1 = effectiveType(input[0]);
		auto t2 = effectiveType(arg[0]);
		// Two quantities are comparable if they have the same unit type
		if (t1 == FPValue::Type::Quantity && t2 == FPValue::Type::Quantity) {
			// For now, check if units are the same or convertible
			std::string u1, u2;
			if (input[0].type == FPValue::Type::Quantity) u1 = input[0].quantity_unit;
			if (arg[0].type == FPValue::Type::Quantity) u2 = arg[0].quantity_unit;
			// Simple: same unit = comparable
			if (u1 == u2) return {FPValue::FromBoolean(true)};
			// Check UCUM conversion table
			std::string b1, b2;
			convertQuantityToBase(input[0].quantity_value, u1, b1);
			convertQuantityToBase(arg[0].quantity_value, u2, b2);
			return {FPValue::FromBoolean(b1 == b2 && !b1.empty())};
		}
		return {FPValue::FromBoolean(false)};
	}

	if (name == "select") {
		if (node.children.size() != 1) {
			throw FHIRPathSpecError("select() takes exactly 1 projection argument");
		}
		auto saved_vars = defined_variables_;
		auto saved_chain = chain_defined_vars_;
		chain_defined_vars_.clear();
		auto result = fn_select(*node.children[0], input, doc);
		defined_variables_ = saved_vars;
		chain_defined_vars_ = saved_chain;
		return result;
	}
	if (name == "repeat") {
		if (node.children.size() != 1) {
			throw FHIRPathSpecError("repeat() takes exactly 1 projection argument");
		}
		auto saved_vars = defined_variables_;
		auto saved_chain = chain_defined_vars_;
		chain_defined_vars_.clear();
		auto result = fn_repeat(*node.children[0], input, doc);
		defined_variables_ = saved_vars;
		chain_defined_vars_ = saved_chain;
		return result;
	}

	// Single-argument functions
	if (!node.children.empty()) {
		if (name == "all") {
			return fn_all(*node.children[0], input, doc);
		}
		if (name == "repeatAll") {
			if (node.children.size() > 1) {
				throw FHIRPathSpecError("repeatAll() takes exactly 1 argument");
			}
			FPCollection result;
			FPCollection work = input;
			// Track unique values to detect termination
			std::vector<std::string> unique_seen;
			// Track type tags for seed inclusion
			bool input_all_numeric_temporal = true;
			bool produced_all_numeric_temporal = true;
			bool has_produced = false;
			for (const auto &item : input) {
				std::string key = toString(item);
				if (std::find(unique_seen.begin(), unique_seen.end(), key) == unique_seen.end()) {
					unique_seen.push_back(key);
				}
				auto t = effectiveType(item);
				if (t != FPValue::Type::Integer && t != FPValue::Type::Decimal &&
				    t != FPValue::Type::Date && t != FPValue::Type::DateTime &&
				    t != FPValue::Type::Time && t != FPValue::Type::Quantity) {
					input_all_numeric_temporal = false;
				}
			}
			size_t iterations = 0;
			while (!work.empty()) {
				FPCollection next;
				FPCollection batch;
				bool has_new_unique = false;
				for (const auto &item : work) {
					FPCollection single_col = {item};
					auto projected = eval(*node.children[0], single_col, doc);
					for (const auto &p : projected) {
						batch.push_back(p);
						next.push_back(p);
						has_produced = true;
						if (produced_all_numeric_temporal) {
							auto pt = effectiveType(p);
							if (pt != FPValue::Type::Integer && pt != FPValue::Type::Decimal &&
							    pt != FPValue::Type::Date && pt != FPValue::Type::DateTime &&
							    pt != FPValue::Type::Time && pt != FPValue::Type::Quantity) {
								produced_all_numeric_temporal = false;
							}
						}
						std::string key = toString(p);
						if (std::find(unique_seen.begin(), unique_seen.end(), key) == unique_seen.end()) {
							unique_seen.push_back(key);
							has_new_unique = true;
						}
					}
				}
				if (!has_new_unique) break;
				result.insert(result.end(), batch.begin(), batch.end());
				work = next;
				if (++iterations > 1000 || result.size() > 10000) {
					throw FHIRPathSpecError("repeatAll() infinite loop detected");
				}
			}
			// Include seeds only for numeric/temporal sequences
			if (input_all_numeric_temporal && produced_all_numeric_temporal && has_produced) {
				FPCollection final_result;
				for (const auto &item : input) {
					final_result.push_back(item);
				}
				final_result.insert(final_result.end(), result.begin(), result.end());
				return final_result;
			}
			return result;
		}
		if (name == "trace") {
			return fn_trace(input);
		}
		if (name == "aggregate") {
			return fn_aggregate(node, input, doc, outer_input);
		}
		if (name == "sort") {
			// Collect all sort criteria
			std::vector<const ASTNode *> criteria;
			for (size_t i = 0; i < node.children.size(); i++) {
				criteria.push_back(&(*node.children[i]));
			}
			return fn_sort(criteria, input, doc);
		}
		if (name == "coalesce") {
			return fn_coalesce(node, input, doc);
		}

		if (name == "is") {
			if (node.children.size() != 1) {
				throw FHIRPathSpecError("is() takes exactly 1 type argument");
			}
			return fn_isType(input, typeNameFromSpecifierNode(*node.children[0]));
		}
		if (name == "as") {
			if (node.children.size() != 1) {
				throw FHIRPathSpecError("as() takes exactly 1 type argument");
			}
			return fn_asType(input, typeNameFromSpecifierNode(*node.children[0]));
		}

		if (name == "startsWith") {
			FPCollection arg_ctx = outer_input ? *outer_input : input;
			auto arg = evalArgIsolated(*node.children[0], arg_ctx, doc);
			return fn_startsWith(input, arg);
		}
		if (name == "endsWith") {
			FPCollection arg_ctx = outer_input ? *outer_input : input;
			auto arg = evalArgIsolated(*node.children[0], arg_ctx, doc);
			return fn_endsWith(input, arg);
		}
		if (name == "contains") {
			FPCollection arg_ctx = outer_input ? *outer_input : input;
			auto arg = evalArgIsolated(*node.children[0], arg_ctx, doc);
			return fn_contains_fn(input, arg);
		}
		if (name == "indexOf") {
			// indexOf(substring) -> integer. Evaluate ordinary value arguments
			// against the outer focus for sourced calls such as s.indexOf(term).
			FPCollection arg_ctx = outer_input ? *outer_input : input;
			auto arg = evalArgIsolated(*node.children[0], arg_ctx, doc);
			if (arg.empty()) {
				return {};
			}
			if (arg.size() > 1) {
				throw FHIRPathSpecError("indexOf() requires a single substring argument");
			}
			auto arg_t = effectiveType(arg[0]);
			if (arg_t != FPValue::Type::String) {
				throw FHIRPathSpecError("indexOf() requires a String substring argument");
			}
			if (input.empty()) {
				return {};
			}
			if (input.size() > 1) {
				throw FHIRPathSpecError("indexOf() requires a single item input");
			}
			auto t = effectiveType(input[0]);
			if (t != FPValue::Type::String) {
				throw FHIRPathSpecError("indexOf() requires a String input");
			}
			std::string s = toString(input[0]);
			std::string sub = toString(arg[0]);
			auto pos = s.find(sub);
			if (pos == std::string::npos) {
				return {FPValue::FromInteger(-1)};
			}
			return {FPValue::FromInteger(static_cast<int64_t>(utf8ByteToChar(s, pos)))};
		}
		if (name == "substring") {
			FPCollection arg_ctx = outer_input ? *outer_input : input;
			auto arg = evalArgIsolated(*node.children[0], arg_ctx, doc);
			if (node.children.size() >= 2) {
				auto length_arg = evalArgIsolated(*node.children[1], arg_ctx, doc);
				return fn_substring(input, arg, &length_arg);
			}
			return fn_substring(input, arg, nullptr);
		}

		FPCollection string_arg_ctx = outer_input ? *outer_input : input;
		auto arg = evalArgIsolated(*node.children[0], string_arg_ctx, doc);

		if (name == "matches") {
			return fn_matches(input, arg);
		}
		if (name == "matchesFull") {
			if (arg.empty()) return {};
			if (arg.size() > 1) {
				throw FHIRPathSpecError("matchesFull() requires a single regex argument");
			}
			if (effectiveType(arg[0]) != FPValue::Type::String) {
				throw FHIRPathSpecError("matchesFull() requires a String regex argument");
			}
			std::string pattern = toString(arg[0]);
			validateFHIRPathRegex(pattern);
			if (input.empty()) return {};
			if (input.size() > 1) {
				throw FHIRPathSpecError("matchesFull() requires a single item input");
			}
			if (effectiveType(input[0]) != FPValue::Type::String) {
				throw FHIRPathSpecError("matchesFull() requires a String input");
			}
			try {
				std::string s = toString(input[0]);
				const auto &re = get_cached_regex(normalizeFHIRPathRegex(pattern));
				return {FPValue::FromBoolean(std::regex_match(s, re))};
			} catch (const std::regex_error &e) {
				throw FHIRPathSpecError(std::string("matchesFull() invalid regular expression: ") + e.what());
			}
		}
		if (name == "replaceMatches") {
			if (arg.empty()) return {};
			if (arg.size() > 1) {
				throw FHIRPathSpecError("replaceMatches() requires a single regex argument");
			}
			if (effectiveType(arg[0]) != FPValue::Type::String) {
				throw FHIRPathSpecError("replaceMatches() requires a String regex argument");
			}
			auto sub_col = evalArgIsolated(*node.children[1], string_arg_ctx, doc);
			if (sub_col.empty()) return {};  // empty substitution → empty result
			if (sub_col.size() > 1) {
				throw FHIRPathSpecError("replaceMatches() requires a single substitution argument");
			}
			if (effectiveType(sub_col[0]) != FPValue::Type::String) {
				throw FHIRPathSpecError("replaceMatches() requires a String substitution argument");
			}
			std::string pattern = toString(arg[0]);
			if (!pattern.empty()) {
				validateFHIRPathRegex(pattern);
			}
			if (input.empty()) return {};
			if (input.size() > 1) {
				throw FHIRPathSpecError("replaceMatches() requires a single item input");
			}
			if (effectiveType(input[0]) != FPValue::Type::String) {
				throw FHIRPathSpecError("replaceMatches() requires a String input");
			}
			std::string s = toString(input[0]);
			std::string sub = toString(sub_col[0]);
			if (pattern.empty()) return {FPValue::FromString(s)};
			try {
				const auto &re = get_cached_regex(normalizeFHIRPathRegex(pattern));
				return {FPValue::FromString(std::regex_replace(s, re, sub))};
			} catch (const std::regex_error &e) {
				throw FHIRPathSpecError(std::string("replaceMatches() invalid regular expression: ") + e.what());
			}
		}
		if (name == "join") {
			std::string separator = toString(arg[0]);
			std::string result;
			for (size_t i = 0; i < input.size(); i++) {
				if (i > 0) result += separator;
				result += toString(input[i]);
			}
			return {FPValue::FromString(result)};
		}
		if (name == "take") {
			return fn_take(input, arg);
		}
		if (name == "skip") {
			return fn_skip(input, arg);
		}
		if (name == "combine" || name == "intersect" || name == "exclude" || name == "union") {
			// Evaluate argument against the outer invocation context (for select/where),
			// falling back to root resource context
			FPCollection eval_ctx;
			if (outer_input && !outer_input->empty()) {
				eval_ctx = *outer_input;
			} else if (resource_context_) {
				eval_ctx.push_back(FPValue::FromJson(resource_context_));
			}
			auto coll_arg = evalArgIsolated(*node.children[0], eval_ctx, doc);
			if (name == "combine") return fn_combine(input, coll_arg);
			if (name == "intersect") return fn_intersect(input, coll_arg);
			if (name == "exclude") return fn_exclude(input, coll_arg);
			return fn_union(input, coll_arg);
		}
		if (name == "subsetOf") {
			// Evaluate argument against root resource context
			FPCollection root_ctx;
			if (resource_context_) root_ctx.push_back(FPValue::FromJson(resource_context_));
			auto subset_arg = evalArgIsolated(*node.children[0], root_ctx, doc);
			return fn_subsetOf(input, subset_arg);
		}
		if (name == "supersetOf") {
			FPCollection root_ctx;
			if (resource_context_) root_ctx.push_back(FPValue::FromJson(resource_context_));
			auto superset_arg = evalArgIsolated(*node.children[0], root_ctx, doc);
			return fn_supersetOf(input, superset_arg);
		}

		if (name == "round") {
			return fn_round(input, &arg);
		}
		if (name == "log") {
			return fn_log(input, arg);
		}
		if (name == "power") {
			return fn_power(input, arg);
		}
		if (name == "ln") {
			return fn_ln(input);
		}

		if (name == "replace") {
			auto substitution = evalArgIsolated(*node.children[1], string_arg_ctx, doc);
			return fn_replace(input, arg, substitution);
		}
		if (name == "iif") {
			if (node.children.size() >= 2) {
				return fn_iif(*node.children[0], *node.children[1],
				              node.children.size() >= 3 ? node.children[2].get() : nullptr, input, doc);
			}
			return {};
		}
		if (name == "split") {
			return fn_split(input, arg);
		}
		if (name == "encode") {
			return fn_encode(input, arg);
		}
		if (name == "decode") {
			return fn_decode(input, arg);
		}
		if (name == "lowBoundary") {
			return fn_lowBoundary(input, &arg);
		}
		if (name == "highBoundary") {
			return fn_highBoundary(input, &arg);
		}
		if (name == "defineVariable") {
			// defineVariable('name', expr) - sets variable and returns input
			if (arg.empty() || arg.size() > 1 || effectiveType(arg[0]) != FPValue::Type::String) {
				throw FHIRPathSpecError("defineVariable() name argument must be a single String");
			}
			std::string var_name = toString(arg[0]);
			// Cannot overwrite system variables
			static const char* system_vars[] = {
				"context", "resource", "rootResource", "ucum", "sct", "loinc",
				"vs-administrative-gender", "ext-patient-birthTime", nullptr
			};
			for (int i = 0; system_vars[i]; ++i) {
				if (var_name == system_vars[i]) {
					throw FHIRPathSpecError("Cannot overwrite system variable %" + var_name);
				}
			}
			// Check for redefinition in same chain
			if (chain_defined_vars_.count(var_name)) {
				throw FHIRPathSpecError("Variable %" + var_name + " is already defined in this scope");
			}
			chain_defined_vars_.insert(var_name);
			FPCollection var_value = input;
			if (node.children.size() >= 2) {
				// Save/restore scope for value expression evaluation
				auto saved_vars = defined_variables_;
				auto saved_chain = chain_defined_vars_;
				chain_defined_vars_.clear();
				var_value = eval(*node.children[1], input, doc);
				defined_variables_ = saved_vars;
				chain_defined_vars_ = saved_chain;
			}
			defined_variables_[var_name] = var_value;
			return input;
		}
	}

	if ((name == "is" || name == "as") && node.children.empty()) {
		throw FHIRPathSpecError(name + "() takes exactly 1 type argument");
	}

	// No-argument functions that weren't handled above
	if (name == "round" && node.children.empty()) {
		return fn_round(input, nullptr);
	}
	if (name == "lowBoundary" && node.children.empty()) {
		return fn_lowBoundary(input, nullptr);
	}
	if (name == "highBoundary" && node.children.empty()) {
		return fn_highBoundary(input, nullptr);
	}
	if (name == "precision" && node.children.empty()) {
		return fn_precision(input);
	}

	// Fallback: return empty collection for unknown functions
	return {};
}

// --- Function implementations ---

FPCollection Evaluator::fn_count(const FPCollection &input) {
	return {FPValue::FromInteger(static_cast<int64_t>(input.size()))};
}

FPCollection Evaluator::fn_first(const FPCollection &input) {
	if (input.empty()) {
		return {};
	}
	return {input[0]};
}

FPCollection Evaluator::fn_last(const FPCollection &input) {
	if (input.empty()) {
		return {};
	}
	return {input.back()};
}

FPCollection Evaluator::fn_single(const FPCollection &input) {
	if (input.size() == 1) {
		return {input[0]};
	}
	if (input.size() > 1) {
		throw FHIRPathSpecError("single() called on collection with multiple elements");
	}
	return {};
}

FPCollection Evaluator::fn_empty(const FPCollection &input) {
	return {FPValue::FromBoolean(input.empty())};
}

FPCollection Evaluator::fn_hasValue(const FPCollection &input) {
	if (input.empty() || input.size() > 1) {
		return {FPValue::FromBoolean(false)};
	}
	auto &val = input[0];
	bool is_primitive = (val.type != FPValue::Type::JsonVal) || 
	                    (val.json_val && !yyjson_is_obj(val.json_val) && !yyjson_is_arr(val.json_val));
	return {FPValue::FromBoolean(is_primitive)};
}

FPCollection Evaluator::fn_not(const FPCollection &input) {
	if (input.empty()) {
		return {};
	}
	if (input.size() != 1) {
		throw FHIRPathSpecError("not() requires a single boolean item input");
	}
	auto &val = input[0];
	// FHIRPath singleton boolean evaluation:
	// - Boolean true/false → use as-is
	// - Any other single value → truthy (true)
	bool bool_val;
	if (val.type == FPValue::Type::Boolean) {
		bool_val = val.bool_val;
	} else if (val.type == FPValue::Type::JsonVal && val.json_val && yyjson_is_bool(val.json_val)) {
		bool_val = yyjson_get_bool(val.json_val);
	} else {
		bool_val = true;
	}
	return {FPValue::FromBoolean(!bool_val)};
}

FPCollection Evaluator::fn_all(const ASTNode &criteria, const FPCollection &input, yyjson_doc *doc) {
	auto saved_chain_vars = chain_defined_vars_;
	auto saved_index_context = index_context_;
	auto saved_defined_vars = defined_variables_;
	int64_t idx = 0;
	for (const auto &item : input) {
		FPCollection single = {item};
		chain_defined_vars_ = saved_chain_vars;
		index_context_ = idx;
		defined_variables_ = saved_defined_vars;
		auto result = eval(criteria, single, doc);
		if (!isCriteriaTrue(result, "all")) {
			chain_defined_vars_ = saved_chain_vars;
			index_context_ = saved_index_context;
			defined_variables_ = saved_defined_vars;
			return {FPValue::FromBoolean(false)};
		}
		++idx;
	}
	chain_defined_vars_ = saved_chain_vars;
	index_context_ = saved_index_context;
	defined_variables_ = saved_defined_vars;
	return {FPValue::FromBoolean(true)};
}

FPCollection Evaluator::fn_allTrue(const FPCollection &input) {
	// FHIRPath §5.1.4: If the input is empty, the result is true
	if (input.empty()) return {FPValue::FromBoolean(true)};
	std::vector<bool> values;
	for (const auto &item : input) {
		values.push_back(requireBooleanValue(item, "allTrue"));
	}
	for (bool value : values) {
		if (!value) return {FPValue::FromBoolean(false)};
	}
	return {FPValue::FromBoolean(true)};
}

FPCollection Evaluator::fn_anyTrue(const FPCollection &input) {
	// FHIRPath §5.1.5: If the input is empty, the result is false
	if (input.empty()) return {FPValue::FromBoolean(false)};
	std::vector<bool> values;
	for (const auto &item : input) {
		values.push_back(requireBooleanValue(item, "anyTrue"));
	}
	for (bool value : values) {
		if (value) return {FPValue::FromBoolean(true)};
	}
	return {FPValue::FromBoolean(false)};
}

FPCollection Evaluator::fn_allFalse(const FPCollection &input) {
	// FHIRPath §5.1.6: If the input is empty, the result is true
	if (input.empty()) return {FPValue::FromBoolean(true)};
	std::vector<bool> values;
	for (const auto &item : input) {
		values.push_back(requireBooleanValue(item, "allFalse"));
	}
	for (bool value : values) {
		if (value) return {FPValue::FromBoolean(false)};
	}
	return {FPValue::FromBoolean(true)};
}

FPCollection Evaluator::fn_anyFalse(const FPCollection &input) {
	// FHIRPath §5.1.7: If the input is empty, the result is false
	if (input.empty()) return {FPValue::FromBoolean(false)};
	std::vector<bool> values;
	for (const auto &item : input) {
		values.push_back(requireBooleanValue(item, "anyFalse"));
	}
	for (bool value : values) {
		if (!value) return {FPValue::FromBoolean(true)};
	}
	return {FPValue::FromBoolean(false)};
}

FPCollection Evaluator::fn_startsWith(const FPCollection &input, const FPCollection &arg) {
	if (arg.empty()) {
		return {};
	}
	if (arg.size() > 1) {
		throw FHIRPathSpecError("startsWith() requires a single prefix argument");
	}
	auto arg_t = effectiveType(arg[0]);
	if (arg_t != FPValue::Type::String) {
		throw FHIRPathSpecError("startsWith() requires a String prefix argument");
	}
	if (input.empty()) {
		return {};
	}
	if (input.size() > 1) {
		throw FHIRPathSpecError("startsWith() requires a single item input");
	}
	// FHIRPath spec: startsWith() requires a String input
	auto t = effectiveType(input[0]);
	if (t != FPValue::Type::String) {
		throw FHIRPathSpecError("startsWith() requires a String input");
	}
	std::string s = toString(input[0]);
	std::string prefix = toString(arg[0]);
	return {FPValue::FromBoolean(s.size() >= prefix.size() && s.substr(0, prefix.size()) == prefix)};
}

FPCollection Evaluator::fn_endsWith(const FPCollection &input, const FPCollection &arg) {
	if (arg.empty()) {
		return {};
	}
	if (arg.size() > 1) {
		throw FHIRPathSpecError("endsWith() requires a single suffix argument");
	}
	auto arg_t = effectiveType(arg[0]);
	if (arg_t != FPValue::Type::String) {
		throw FHIRPathSpecError("endsWith() requires a String suffix argument");
	}
	if (input.empty()) {
		return {};
	}
	if (input.size() > 1) {
		throw FHIRPathSpecError("endsWith() requires a single item input");
	}
	// FHIRPath spec: endsWith() requires a String input
	auto t = effectiveType(input[0]);
	if (t != FPValue::Type::String) {
		throw FHIRPathSpecError("endsWith() requires a String input");
	}
	std::string s = toString(input[0]);
	std::string suffix = toString(arg[0]);
	return {FPValue::FromBoolean(s.size() >= suffix.size() &&
	                             s.substr(s.size() - suffix.size()) == suffix)};
}

FPCollection Evaluator::fn_contains_fn(const FPCollection &input, const FPCollection &arg) {
	if (arg.empty()) {
		return {};
	}
	if (arg.size() > 1) {
		throw FHIRPathSpecError("contains() requires a single substring argument");
	}
	auto arg_t = effectiveType(arg[0]);
	if (arg_t != FPValue::Type::String) {
		throw FHIRPathSpecError("contains() requires a String substring argument");
	}
	if (input.empty()) {
		return {};
	}
	if (input.size() > 1) {
		throw FHIRPathSpecError("contains() requires a single item input");
	}
	// FHIRPath spec: contains() in this section requires String input and argument.
	auto t = effectiveType(input[0]);
	if (t != FPValue::Type::String) {
		throw FHIRPathSpecError("contains() requires a String input");
	}
	std::string s = toString(input[0]);
	std::string sub = toString(arg[0]);
	return {FPValue::FromBoolean(s.find(sub) != std::string::npos)};
}

FPCollection Evaluator::fn_matches(const FPCollection &input, const FPCollection &arg) {
	if (arg.empty()) {
		return {};
	}
	if (arg.size() > 1) {
		throw FHIRPathSpecError("matches() requires a single regex argument");
	}
	if (effectiveType(arg[0]) != FPValue::Type::String) {
		throw FHIRPathSpecError("matches() requires a String regex argument");
	}
	std::string pattern = toString(arg[0]);
	validateFHIRPathRegex(pattern);
	if (input.empty()) {
		return {};
	}
	if (input.size() > 1) {
		throw FHIRPathSpecError("matches() requires a single item input");
	}
	if (effectiveType(input[0]) != FPValue::Type::String) {
		throw FHIRPathSpecError("matches() requires a String input");
	}
	try {
			std::string s = toString(input[0]);
			std::string dotall_pattern = normalizeFHIRPathRegex(pattern);
		const auto &re2 = get_cached_regex(dotall_pattern);
		return {FPValue::FromBoolean(std::regex_match(s, re2))};
	} catch (const std::regex_error &e) {
		throw FHIRPathSpecError(std::string("matches() invalid regular expression: ") + e.what());
	}
}

FPCollection Evaluator::fn_replace(const FPCollection &input, const FPCollection &pattern,
                                   const FPCollection &substitution) {
	if (pattern.empty() || substitution.empty()) {
		return {};
	}
	if (pattern.size() > 1) {
		throw FHIRPathSpecError("replace() requires a single pattern argument");
	}
	if (substitution.size() > 1) {
		throw FHIRPathSpecError("replace() requires a single substitution argument");
	}
	// FHIRPath spec: replace() requires a String input
	if (effectiveType(pattern[0]) != FPValue::Type::String) {
		throw FHIRPathSpecError("replace() requires a String pattern argument");
	}
	if (effectiveType(substitution[0]) != FPValue::Type::String) {
		throw FHIRPathSpecError("replace() requires a String substitution argument");
	}
	if (input.empty()) {
		return {};
	}
	if (input.size() > 1) {
		throw FHIRPathSpecError("replace() requires a single item input");
	}
	if (effectiveType(input[0]) != FPValue::Type::String) {
		throw FHIRPathSpecError("replace() requires a String input");
	}
	std::string s = toString(input[0]);
	std::string pat = toString(pattern[0]);
	std::string sub = substitution.empty() ? "" : toString(substitution[0]);
	if (pat.empty()) {
		// FHIRPath spec: replace with empty pattern inserts between each character (Unicode code point)
		std::string result;
		result += sub;
		size_t byte = 0;
		while (byte < s.size()) {
			unsigned char c = static_cast<unsigned char>(s[byte]);
			size_t char_bytes;
			if (c < 0x80)      char_bytes = 1;
			else if (c < 0xE0) char_bytes = 2;
			else if (c < 0xF0) char_bytes = 3;
			else               char_bytes = 4;
			result += s.substr(byte, char_bytes);
			result += sub;
			byte += char_bytes;
		}
		return {FPValue::FromString(result)};
	}
	std::string result;
	size_t pos = 0;
	while (true) {
		size_t found = s.find(pat, pos);
		if (found == std::string::npos) {
			result += s.substr(pos);
			break;
		}
		result += s.substr(pos, found - pos) + sub;
		pos = found + pat.size();
	}
	return {FPValue::FromString(result)};
}

FPCollection Evaluator::fn_substring(const FPCollection &input, const FPCollection &start,
                                     const FPCollection *length) {
	if (start.empty()) {
		return {};
	}
	if (start.size() > 1) {
		throw FHIRPathSpecError("substring() requires a single start argument");
	}
	int64_t start_idx = 0;
	if (!extractStrictInteger(start[0], start_idx)) {
		throw FHIRPathSpecError("substring() requires an Integer start argument");
	}
	if (length && !length->empty()) {
		if (length->size() > 1) {
			throw FHIRPathSpecError("substring() requires a single length argument");
		}
		int64_t len_probe = 0;
		if (!extractStrictInteger((*length)[0], len_probe)) {
			throw FHIRPathSpecError("substring() requires an Integer length argument");
		}
	}
	if (input.empty()) {
		return {};
	}
	if (input.size() > 1) {
		throw FHIRPathSpecError("substring() requires a single item input");
	}
	// FHIRPath spec: substring() requires a String input
	auto t = effectiveType(input[0]);
	if (t != FPValue::Type::String) {
		throw FHIRPathSpecError("substring() requires a String input");
	}
	std::string s = toString(input[0]);

	// FHIRPath 5.2. substring: If startIndex is less than 0, the result is empty.
	if (start_idx < 0) {
		return {};
	}

	// Use Unicode code-point length for boundary check
	size_t char_len = utf8Len(s);
	if (static_cast<size_t>(start_idx) >= char_len) {
		return {};
	}

	// Convert character start to byte offset
	size_t byte_start = utf8CharToByte(s, static_cast<size_t>(start_idx));

	if (length && !length->empty()) {
		int64_t len = 0;
		extractStrictInteger((*length)[0], len);
		// Spec: "If a negative or zero length is provided, the function
		// returns an empty string ('')" — NOT an empty collection.
		if (len <= 0) {
			return {FPValue::FromString("")};
		}
		// Convert character length to byte length
		size_t byte_end = utf8CharToByte(s, static_cast<size_t>(start_idx + len));
		return {FPValue::FromString(s.substr(byte_start, byte_end - byte_start))};
	}
	return {FPValue::FromString(s.substr(byte_start))};
}

FPCollection Evaluator::fn_length(const FPCollection &input) {
	if (input.empty()) {
		return {};
	}
	if (input.size() > 1) {
		throw FHIRPathSpecError("length() requires a single item input");
	}
	// FHIRPath spec: length() requires a String input
	auto t = effectiveType(input[0]);
	if (t != FPValue::Type::String) {
		throw FHIRPathSpecError("length() requires a String input");
	}
	std::string s = toString(input[0]);
	// FHIRPath length counts Unicode code-points, not bytes
	return {FPValue::FromInteger(static_cast<int64_t>(utf8Len(s)))};
}

FPCollection Evaluator::fn_upper(const FPCollection &input) {
	if (input.empty()) {
		return {};
	}
	if (input.size() > 1) {
		throw FHIRPathSpecError("upper() requires a single item input");
	}
	// FHIRPath spec: upper() requires a String input
	auto t = effectiveType(input[0]);
	if (t != FPValue::Type::String) {
		throw FHIRPathSpecError("upper() requires a String input");
	}
	std::string s = toString(input[0]);
	// Unicode-aware uppercase: iterate code points, case-map, re-encode.
	std::string result;
	result.reserve(s.size());
	size_t byte = 0;
	while (byte < s.size()) {
		unsigned char c = static_cast<unsigned char>(s[byte]);
		uint32_t cp;
		size_t char_bytes;
		if (c < 0x80) {
			cp = c; char_bytes = 1;
		} else if (c < 0xE0) {
			cp = ((c & 0x1F) << 6) | (static_cast<unsigned char>(s[byte+1]) & 0x3F);
			char_bytes = 2;
		} else if (c < 0xF0) {
			cp = ((c & 0x0F) << 12) | ((static_cast<unsigned char>(s[byte+1]) & 0x3F) << 6)
			     | (static_cast<unsigned char>(s[byte+2]) & 0x3F);
			char_bytes = 3;
		} else {
			cp = ((c & 0x07) << 18) | ((static_cast<unsigned char>(s[byte+1]) & 0x3F) << 12)
			     | ((static_cast<unsigned char>(s[byte+2]) & 0x3F) << 6)
			     | (static_cast<unsigned char>(s[byte+3]) & 0x3F);
			char_bytes = 4;
		}
		// Simple Unicode case mapping for common ranges (Latin-1 Supplement, Latin Extended-A)
		uint32_t upper_cp = cp;
		if (cp == 0x00DF) {
			// German sharp s uppercases to two code points.
			result += "SS";
			byte += char_bytes;
			continue;
		}
		if (cp >= 0x0061 && cp <= 0x007A) upper_cp = cp - 32;            // a-z → A-Z
		else if (cp >= 0x00E0 && cp <= 0x00F6) upper_cp = cp - 32;      // à-ö → À-Ö
		else if (cp >= 0x00F8 && cp <= 0x00FE) upper_cp = cp - 32;      // ø-þ → Ø-Þ
		else if (cp == 0x00FF) upper_cp = 0x0178;                         // ÿ → Ÿ
		else if (cp == 0x0131) upper_cp = 0x0049;                         // dotless ı → I
		else if (cp >= 0x0101 && cp <= 0x012F && (cp & 1) == 1) upper_cp = cp - 1; // Latin Ext-A lowercase
		else if (cp >= 0x0133 && cp <= 0x0137 && (cp & 1) == 1) upper_cp = cp - 1;
		else if (cp >= 0x013A && cp <= 0x0148 && (cp & 1) == 0) upper_cp = cp - 1;
		else if (cp == 0x014B) upper_cp = 0x014A;
		else if (cp >= 0x014D && cp <= 0x0177 && (cp & 1) == 1) upper_cp = cp - 1;
		else if (cp >= 0x017A && cp <= 0x017E && (cp & 1) == 0) upper_cp = cp - 1;
		else if (cp == 0x03AC) upper_cp = 0x0386;                         // ά → Ά
		else if (cp == 0x03AD) upper_cp = 0x0388;                         // έ → Έ
		else if (cp == 0x03AE) upper_cp = 0x0389;                         // ή → Ή
		else if (cp == 0x03AF) upper_cp = 0x038A;                         // ί → Ί
		else if (cp == 0x03CC) upper_cp = 0x038C;                         // ό → Ό
		else if (cp == 0x03CD) upper_cp = 0x038E;                         // ύ → Ύ
		else if (cp == 0x03CE) upper_cp = 0x038F;                         // ώ → Ώ
		else if (cp == 0x03CA) upper_cp = 0x03AA;                         // ϊ → Ϊ
		else if (cp == 0x03CB) upper_cp = 0x03AB;                         // ϋ → Ϋ
		else if (cp == 0x03C2) upper_cp = 0x03A3;                         // ς → Σ (final sigma)
		else if (cp >= 0x03B1 && cp <= 0x03C9) upper_cp = cp - 32;      // Greek α-ω → Α-Ω
		else if (cp >= 0x0430 && cp <= 0x044F) upper_cp = cp - 32;      // Russian а-я → А-Я
		else if (cp == 0x0451) upper_cp = 0x0401;                         // ё → Ё
		// Re-encode code point to UTF-8
		if (upper_cp < 0x80) {
			result += static_cast<char>(upper_cp);
		} else if (upper_cp < 0x800) {
			result += static_cast<char>(0xC0 | (upper_cp >> 6));
			result += static_cast<char>(0x80 | (upper_cp & 0x3F));
		} else if (upper_cp < 0x10000) {
			result += static_cast<char>(0xE0 | (upper_cp >> 12));
			result += static_cast<char>(0x80 | ((upper_cp >> 6) & 0x3F));
			result += static_cast<char>(0x80 | (upper_cp & 0x3F));
		} else {
			result += static_cast<char>(0xF0 | (upper_cp >> 18));
			result += static_cast<char>(0x80 | ((upper_cp >> 12) & 0x3F));
			result += static_cast<char>(0x80 | ((upper_cp >> 6) & 0x3F));
			result += static_cast<char>(0x80 | (upper_cp & 0x3F));
		}
		byte += char_bytes;
	}
	return {FPValue::FromString(result)};
}

FPCollection Evaluator::fn_lower(const FPCollection &input) {
	if (input.empty()) {
		return {};
	}
	if (input.size() > 1) {
		throw FHIRPathSpecError("lower() requires a single item input");
	}
	// FHIRPath spec: lower() requires a String input
	auto t = effectiveType(input[0]);
	if (t != FPValue::Type::String) {
		throw FHIRPathSpecError("lower() requires a String input");
	}
	std::string s = toString(input[0]);
	// Unicode-aware lowercase: iterate code points, case-map, re-encode.
	std::string result;
	result.reserve(s.size());
	size_t byte = 0;
	while (byte < s.size()) {
		unsigned char c = static_cast<unsigned char>(s[byte]);
		uint32_t cp;
		size_t char_bytes;
		if (c < 0x80) {
			cp = c; char_bytes = 1;
		} else if (c < 0xE0) {
			cp = ((c & 0x1F) << 6) | (static_cast<unsigned char>(s[byte+1]) & 0x3F);
			char_bytes = 2;
		} else if (c < 0xF0) {
			cp = ((c & 0x0F) << 12) | ((static_cast<unsigned char>(s[byte+1]) & 0x3F) << 6)
			     | (static_cast<unsigned char>(s[byte+2]) & 0x3F);
			char_bytes = 3;
		} else {
			cp = ((c & 0x07) << 18) | ((static_cast<unsigned char>(s[byte+1]) & 0x3F) << 12)
			     | ((static_cast<unsigned char>(s[byte+2]) & 0x3F) << 6)
			     | (static_cast<unsigned char>(s[byte+3]) & 0x3F);
			char_bytes = 4;
		}
		// Simple Unicode case mapping for common ranges
		uint32_t lower_cp = cp;
		if (cp == 0x0130) {
			// Unicode simple lower for dotted capital I expands to i + combining dot.
			result += "i";
			result += "\xCC\x87";
			byte += char_bytes;
			continue;
		}
		if (cp >= 0x0041 && cp <= 0x005A) lower_cp = cp + 32;            // A-Z → a-z
		else if (cp >= 0x00C0 && cp <= 0x00D6) lower_cp = cp + 32;      // À-Ö → à-ö
		else if (cp >= 0x00D8 && cp <= 0x00DE) lower_cp = cp + 32;      // Ø-Þ → ø-þ
		else if (cp == 0x0178) lower_cp = 0x00FF;                         // Ÿ → ÿ
		else if (cp >= 0x0100 && cp <= 0x012E && (cp & 1) == 0) lower_cp = cp + 1; // Latin Ext-A uppercase
		else if (cp >= 0x0132 && cp <= 0x0136 && (cp & 1) == 0) lower_cp = cp + 1;
		else if (cp >= 0x0139 && cp <= 0x0147 && (cp & 1) == 1) lower_cp = cp + 1;
		else if (cp == 0x014A) lower_cp = 0x014B;
		else if (cp >= 0x014C && cp <= 0x0176 && (cp & 1) == 0) lower_cp = cp + 1;
		else if (cp >= 0x0179 && cp <= 0x017D && (cp & 1) == 1) lower_cp = cp + 1;
		else if (cp == 0x0386) lower_cp = 0x03AC;                         // Ά → ά
		else if (cp == 0x0388) lower_cp = 0x03AD;                         // Έ → έ
		else if (cp == 0x0389) lower_cp = 0x03AE;                         // Ή → ή
		else if (cp == 0x038A) lower_cp = 0x03AF;                         // Ί → ί
		else if (cp == 0x038C) lower_cp = 0x03CC;                         // Ό → ό
		else if (cp == 0x038E) lower_cp = 0x03CD;                         // Ύ → ύ
		else if (cp == 0x038F) lower_cp = 0x03CE;                         // Ώ → ώ
		else if (cp == 0x03AA) lower_cp = 0x03CA;                         // Ϊ → ϊ
		else if (cp == 0x03AB) lower_cp = 0x03CB;                         // Ϋ → ϋ
		else if (cp >= 0x0391 && cp <= 0x03A9) lower_cp = cp + 32;      // Greek Α-Ω → α-ω
		else if (cp >= 0x0410 && cp <= 0x042F) lower_cp = cp + 32;      // Russian А-Я → а-я
		else if (cp == 0x0401) lower_cp = 0x0451;                         // Ё → ё
		// Re-encode code point to UTF-8
		if (lower_cp < 0x80) {
			result += static_cast<char>(lower_cp);
		} else if (lower_cp < 0x800) {
			result += static_cast<char>(0xC0 | (lower_cp >> 6));
			result += static_cast<char>(0x80 | (lower_cp & 0x3F));
		} else if (lower_cp < 0x10000) {
			result += static_cast<char>(0xE0 | (lower_cp >> 12));
			result += static_cast<char>(0x80 | ((lower_cp >> 6) & 0x3F));
			result += static_cast<char>(0x80 | (lower_cp & 0x3F));
		} else {
			result += static_cast<char>(0xF0 | (lower_cp >> 18));
			result += static_cast<char>(0x80 | ((lower_cp >> 12) & 0x3F));
			result += static_cast<char>(0x80 | ((lower_cp >> 6) & 0x3F));
			result += static_cast<char>(0x80 | (lower_cp & 0x3F));
		}
		byte += char_bytes;
	}
	return {FPValue::FromString(result)};
}

FPCollection Evaluator::fn_trim(const FPCollection &input) {
	if (input.empty()) {
		return {};
	}
	if (input.size() > 1) {
		throw FHIRPathSpecError("trim() requires a single string item input");
	}
	// FHIRPath spec: trim() requires a String input
	auto t = effectiveType(input[0]);
	if (t != FPValue::Type::String) {
		return {};
	}
	std::string s = toString(input[0]);
	size_t start = s.find_first_not_of(" \t\n\r");
	size_t end = s.find_last_not_of(" \t\n\r");
	if (start == std::string::npos) {
		return {FPValue::FromString("")};
	}
	return {FPValue::FromString(s.substr(start, end - start + 1))};
}

FPCollection Evaluator::fn_toInteger(const FPCollection &input) {
	if (input.empty()) {
		return {};
	}
	try {
		auto &val = input[0];
		// FHIRPath spec: Integer is 32-bit signed (-2^31 to 2^31-1)
		constexpr int64_t INT32_MIN_VAL = -2147483648LL;
		constexpr int64_t INT32_MAX_VAL = 2147483647LL;
		auto t = effectiveType(val);
		if (t == FPValue::Type::Integer) {
			int64_t iv = static_cast<int64_t>(getNumericValue(val));
			if (iv < INT32_MIN_VAL || iv > INT32_MAX_VAL) return {};
			return {FPValue::FromInteger(iv)};
		}
		if (t == FPValue::Type::Boolean) {
			bool b = val.type == FPValue::Type::Boolean ? val.bool_val :
			         (val.json_val && yyjson_get_bool(val.json_val));
			return {FPValue::FromInteger(b ? 1 : 0)};
		}
		if (t != FPValue::Type::String) return {};
		std::string s = toString(val);
		// First try: pure integer string (optional sign + digits only)
		if (!isFHIRPathIntegerString(s)) return {};
		{
			size_t idx = 0;
			long long result = std::stoll(s, &idx);
			if (idx == s.size()) {
				// All characters consumed → pure integer string
				if (result < INT32_MIN_VAL || result > INT32_MAX_VAL) return {};
				return {FPValue::FromInteger(static_cast<int64_t>(result))};
			}
		}
		return {};
	} catch (const std::exception &) {
		return {};
	}
}

FPCollection Evaluator::fn_toDecimal(const FPCollection &input) {
	if (input.empty()) {
		return {};
	}
	try {
		auto &val = input[0];
		if (val.type == FPValue::Type::Decimal) {
			return {val};
		}
		if (val.type == FPValue::Type::Integer) {
			return {FPValue::FromDecimal(static_cast<double>(val.int_val))};
		}
		auto t = effectiveType(val);
		if (t == FPValue::Type::Boolean) {
			bool b = (val.type == FPValue::Type::Boolean) ? val.bool_val :
			         (val.json_val && yyjson_get_bool(val.json_val));
			return {FPValue::FromDecimal(b ? 1.0 : 0.0)};
		}
		if (t == FPValue::Type::Integer) {
			return {FPValue::FromDecimal(getNumericValue(val))};
		}
		if (t != FPValue::Type::String) {
			return {};
		}
		std::string s = toString(val);
		if (!isFHIRPathDecimalString(s)) return {};
		size_t idx = 0;
		double d = std::stod(s, &idx);
		if (idx != s.size()) return {};
		// Reject NaN and Infinity - not valid FHIRPath decimals
		if (std::isnan(d) || std::isinf(d)) return {};
		return {FPValue::FromDecimal(d)};
	} catch (const std::exception &) {
		return {};
	}
}

FPCollection Evaluator::fn_toString(const FPCollection &input) {
	if (input.empty()) {
		return {};
	}
	FPValue quantity_value;
	if (fpValueAsQuantity(input[0], quantity_value)) {
		return {FPValue::FromString(toString(quantity_value))};
	}
	if (input[0].type == FPValue::Type::JsonVal && input[0].json_val) {
		if (!(yyjson_is_str(input[0].json_val) || yyjson_is_bool(input[0].json_val) ||
		      yyjson_is_num(input[0].json_val))) {
			return {};
		}
	}
	return {FPValue::FromString(toString(input[0]))};
}

FPCollection Evaluator::fn_toDate(const FPCollection &input) {
	if (input.empty()) {
		return {};
	}
	auto t = effectiveType(input[0]);
	if (t == FPValue::Type::Date) {
		return input;
	}
	if (t == FPValue::Type::DateTime) {
		// Extract date part (first 10 chars or fewer if partial)
		std::string s = toString(input[0]);
		// Find the 'T' to get just the date portion
		auto tpos = s.find('T');
		if (tpos != std::string::npos) s = s.substr(0, tpos);
		FPValue v; v.type = FPValue::Type::Date; v.string_val = s;
		return {v};
	}
	if (t != FPValue::Type::String) return {};
	std::string s = toString(input[0]);
	DateTimeParts dp = parseDateTimeParts(s);
	if (dp.valid && dp.precision >= 1) {
		auto tpos = s.find('T');
		std::string date_part = (tpos != std::string::npos) ? s.substr(0, tpos) : s;
		FPValue v; v.type = FPValue::Type::Date; v.string_val = date_part;
		return {v};
	}
	return {};
}

FPCollection Evaluator::fn_toDateTime(const FPCollection &input) {
	if (input.empty()) {
		return {};
	}
	auto t = effectiveType(input[0]);
	if (t == FPValue::Type::DateTime) {
		return input;
	}
	if (t == FPValue::Type::Date) {
		// Date → DateTime preserves date precision and marks DateTime with T.
		FPValue v; v.type = FPValue::Type::DateTime; v.string_val = toString(input[0]) + "T";
		return {v};
	}
	if (t != FPValue::Type::String) return {};
	std::string s = toString(input[0]);
	// Validate using parseDateTimeParts for strict format checking
	DateTimeParts dp = parseDateTimeParts(s);
	if (dp.valid) {
		FPValue v; v.type = FPValue::Type::DateTime;
		v.string_val = (s.find('T') == std::string::npos && dp.precision <= 3) ? s + "T" : s;
		return {v};
	}
	return {};
}

FPCollection Evaluator::fn_toBoolean(const FPCollection &input) {
	if (input.empty()) {
		return {};
	}
	auto &val = input[0];
	if (val.type == FPValue::Type::Boolean) {
		return {val};
	}
	// FHIRPath §5.1.2: toBoolean on Integer
	if (effectiveType(val) == FPValue::Type::Integer) {
		int64_t iv = static_cast<int64_t>(getNumericValue(val));
		if (iv == 1) return {FPValue::FromBoolean(true)};
		if (iv == 0) return {FPValue::FromBoolean(false)};
		return {};
	}
	// FHIRPath §5.1.2: toBoolean on Decimal
	if (effectiveType(val) == FPValue::Type::Decimal) {
		double dv = getNumericValue(val);
		if (dv == 1.0) return {FPValue::FromBoolean(true)};
		if (dv == 0.0) return {FPValue::FromBoolean(false)};
		return {};
	}
	std::string s = toString(val);
	// FHIRPath §5.1.2: case-insensitive boolean string conversion
	std::string lower;
	for (auto c : s) lower += static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
	if (lower == "true" || lower == "t" || lower == "yes" || lower == "y" || lower == "1" || lower == "1.0") {
		return {FPValue::FromBoolean(true)};
	}
	if (lower == "false" || lower == "f" || lower == "no" || lower == "n" || lower == "0" || lower == "0.0") {
		return {FPValue::FromBoolean(false)};
	}
	return {};
}

FPCollection Evaluator::fn_toQuantity(const FPCollection &input, const std::string &to_unit) {
	if (input.empty()) {
		return {};
	}
	auto finish_quantity = [&to_unit](const FPValue &quantity) -> FPCollection {
		FPValue converted;
		if (!convertQuantityUnit(quantity, to_unit, converted)) {
			return {};
		}
		return {converted};
	};
	auto &val = input[0];
	if (val.type == FPValue::Type::Quantity) {
		return finish_quantity(val);
	}
	FPValue quantity_value;
	if (fpValueAsQuantity(val, quantity_value)) {
		return finish_quantity(quantity_value);
	}
	// Handle both native types and JsonVal-wrapped types (the "Decimal Type
	// Blindness" pattern from GLOBAL_KNOWLEDGE: JSON integers/decimals/booleans
	// arrive as FPValue::Type::JsonVal, not as the concrete type).
	auto t = effectiveType(val);
	if (t == FPValue::Type::Integer) {
		FPValue v;
		v.type = FPValue::Type::Quantity;
		v.quantity_value = getNumericValue(val);
		v.quantity_unit = "1";
		return finish_quantity(v);
	}
	if (t == FPValue::Type::Decimal) {
		FPValue v;
		v.type = FPValue::Type::Quantity;
		v.quantity_value = getNumericValue(val);
		v.quantity_unit = "1";
		return finish_quantity(v);
	}
	if (t == FPValue::Type::Boolean) {
		bool b = (val.type == FPValue::Type::Boolean) ? val.bool_val :
		         (val.json_val && yyjson_get_bool(val.json_val));
		FPValue v;
		v.type = FPValue::Type::Quantity;
		v.quantity_value = b ? 1.0 : 0.0;
		v.quantity_unit = "1";
		return finish_quantity(v);
	}
	// String → Quantity: parse "number unit" format
	if (t == FPValue::Type::String) {
		std::string s = toString(val);
		// Try to parse as "number" or "number unit"
		size_t idx = 0;
		// Parse number
		size_t num_start = idx;
		if (idx < s.size() && (s[idx] == '+' || s[idx] == '-')) idx++;
		bool has_digit = false;
		while (idx < s.size() && std::isdigit((unsigned char)s[idx])) { idx++; has_digit = true; }
		if (idx < s.size() && s[idx] == '.') {
			idx++;
			bool has_frac = false;
			while (idx < s.size() && std::isdigit((unsigned char)s[idx])) { idx++; has_frac = true; }
			if (!has_frac) return {};
		}
		if (!has_digit) return {};
		double num_val;
		try { num_val = std::stod(s.substr(num_start, idx - num_start)); } catch (const std::exception &) { return {}; }
		// After number, the next character (if any) must be whitespace or a quote.
		// Reject strings like "42abc" or "0xFF" where non-whitespace/non-quote
		// text immediately follows the number.
		if (idx < s.size() && !std::isspace((unsigned char)s[idx]) && s[idx] != '\'') {
			return {};
		}
		// Skip whitespace
		while (idx < s.size() && std::isspace((unsigned char)s[idx])) idx++;
		std::string unit_str;
		if (idx < s.size()) {
			// Parse unit: either 'quoted' or bare keyword
			if (s[idx] == '\'') {
				idx++; // skip opening quote
				size_t unit_start = idx;
				while (idx < s.size() && s[idx] != '\'') idx++;
				if (idx >= s.size()) return {};
				if (idx == unit_start) return {};
				unit_str = s.substr(unit_start, idx - unit_start);
				idx++; // skip closing quote
				while (idx < s.size() && std::isspace((unsigned char)s[idx])) idx++;
				if (idx != s.size()) return {};
			} else {
				unit_str = s.substr(idx);
				// Trim trailing whitespace
				while (!unit_str.empty() && std::isspace((unsigned char)unit_str.back())) unit_str.pop_back();
				if (isBareDurationCode(unit_str)) return {};
				if (isBareDurationKeyword(unit_str)) {
					// Calendar duration keywords stay in their keyword form.
				}
			}
		} else {
			unit_str = "1";
		}
		FPValue v;
		v.type = FPValue::Type::Quantity;
		v.quantity_value = num_val;
		v.quantity_unit = unit_str;
		return finish_quantity(v);
	}
	return {};
}

FPCollection Evaluator::fn_abs(const FPCollection &input) {
	if (input.empty()) {
		return {};
	}
	auto &val = input[0];
	if (val.type == FPValue::Type::Quantity) {
		FPValue v;
		v.type = FPValue::Type::Quantity;
		v.quantity_value = std::abs(val.quantity_value);
		v.quantity_unit = val.quantity_unit;
		return {v};
	}
	if (isNumericType(val)) {
		double n = getNumericValue(val);
		auto et = effectiveType(val);
		if (et == FPValue::Type::Integer) {
			return {FPValue::FromInteger(static_cast<int64_t>(std::abs(n)))};
		}
		auto result = FPValue::FromDecimal(std::abs(n));
		if (val.type == FPValue::Type::Decimal && !val.source_text.empty()) {
			if (val.source_text[0] == '-') {
				result.source_text = val.source_text.substr(1);
			} else {
				result.source_text = val.source_text;
			}
		}
		return {result};
	}
	throw FHIRPathSpecError("abs() requires a numeric or Quantity input");
}

FPCollection Evaluator::fn_ceiling(const FPCollection &input) {
	if (input.empty()) {
		return {};
	}
	auto &val = input[0];
	if (isNumericType(val)) {
		double n = getNumericValue(val);
		return {FPValue::FromInteger(static_cast<int64_t>(std::ceil(n)))};
	}
	throw FHIRPathSpecError("ceiling() requires a numeric input");
}

FPCollection Evaluator::fn_floor(const FPCollection &input) {
	if (input.empty()) {
		return {};
	}
	auto &val = input[0];
	if (isNumericType(val)) {
		double n = getNumericValue(val);
		return {FPValue::FromInteger(static_cast<int64_t>(std::floor(n)))};
	}
	throw FHIRPathSpecError("floor() requires a numeric input");
}

static std::string normalizeRoundedDecimalText(std::string int_part, std::string frac_part, bool negative) {
	size_t first_digit = int_part.find_first_not_of('0');
	if (first_digit == std::string::npos) {
		int_part = "0";
	} else if (first_digit > 0) {
		int_part.erase(0, first_digit);
	}
	while (frac_part.size() > 1 && frac_part.back() == '0') {
		frac_part.pop_back();
	}
	if (frac_part.empty()) {
		frac_part = "0";
	}
	bool zero = (int_part == "0");
	for (char ch : frac_part) {
		if (ch != '0') {
			zero = false;
			break;
		}
	}
	return (negative && !zero ? "-" : "") + int_part + "." + frac_part;
}

static std::string roundDecimalSourceText(const std::string &source_text, int64_t precision) {
	std::string text = source_text;
	bool negative = false;
	if (!text.empty() && (text[0] == '-' || text[0] == '+')) {
		negative = text[0] == '-';
		text.erase(0, 1);
	}
	size_t dot = text.find('.');
	std::string int_part = dot == std::string::npos ? text : text.substr(0, dot);
	std::string frac_part = dot == std::string::npos ? "" : text.substr(dot + 1);
	if (int_part.empty()) {
		int_part = "0";
	}
	if (precision >= static_cast<int64_t>(frac_part.size())) {
		return normalizeRoundedDecimalText(int_part, frac_part, negative);
	}

	std::string kept_frac = frac_part.substr(0, static_cast<size_t>(precision));
	std::string digits = int_part + kept_frac;
	if (digits.empty()) {
		digits = "0";
	}
	bool carry = precision >= 0 && frac_part[static_cast<size_t>(precision)] >= '5';
	for (int i = static_cast<int>(digits.size()) - 1; carry && i >= 0; --i) {
		if (digits[static_cast<size_t>(i)] == '9') {
			digits[static_cast<size_t>(i)] = '0';
		} else {
			digits[static_cast<size_t>(i)]++;
			carry = false;
		}
	}
	if (carry) {
		digits.insert(digits.begin(), '1');
	}

	size_t int_len = int_part.size();
	size_t expected_len = int_part.size() + static_cast<size_t>(precision);
	if (digits.size() > expected_len) {
		int_len += digits.size() - expected_len;
	}
	std::string rounded_int = digits.substr(0, int_len);
	std::string rounded_frac = digits.substr(int_len);
	while (rounded_frac.size() < static_cast<size_t>(precision)) {
		rounded_frac.push_back('0');
	}
	return normalizeRoundedDecimalText(rounded_int, rounded_frac, negative);
}

FPCollection Evaluator::fn_round(const FPCollection &input, const FPCollection *precision) {
	int64_t prec = 0;
	if (precision) {
		if (precision->empty()) {
			return {};
		}
		if (precision->size() > 1) {
			throw FHIRPathSpecError("round() precision argument requires a single item collection");
		}
		if (!extractStrictInteger((*precision)[0], prec)) {
			throw FHIRPathSpecError("round() precision argument must be an Integer");
		}
		if (prec < 0) {
			throw FHIRPathSpecError("round() precision argument must be >= 0");
		}
	}
	if (input.empty()) {
		return {};
	}
	auto &val = input[0];
	if (isNumericType(val)) {
		if (val.type == FPValue::Type::Decimal && !val.source_text.empty()) {
			std::string text = roundDecimalSourceText(val.source_text, prec);
			std::istringstream iss(text);
			double rounded_value = 0.0;
			iss >> rounded_value;
			auto rounded = FPValue::FromDecimal(rounded_value);
			rounded.source_text = text;
			return {rounded};
		}
		double dval = getNumericValue(val);
		double factor = std::pow(10.0, static_cast<double>(prec));
		double result = std::round(dval * factor) / factor;
		auto rounded = FPValue::FromDecimal(result);
		std::ostringstream oss;
		oss << std::fixed << std::setprecision(static_cast<int>(prec)) << result;
		std::string text = oss.str();
		if (prec == 0 && text.find('.') == std::string::npos && text.find('e') == std::string::npos &&
		    text.find('E') == std::string::npos) {
			text += ".0";
		}
		auto dot = text.find('.');
		if (dot != std::string::npos) {
			while (text.size() > dot + 2 && text.back() == '0') {
				text.pop_back();
			}
		}
		rounded.source_text = text;
		return {rounded};
	}
	throw FHIRPathSpecError("round() requires a numeric input");
}

FPCollection Evaluator::fn_ln(const FPCollection &input) {
	if (input.empty()) {
		return {};
	}
	auto &val = input[0];
	if (!isNumericType(val)) {
		throw FHIRPathSpecError("ln() requires a numeric input");
	}
	double dval = getNumericValue(val);
	if (dval <= 0) {
		return {};
	}
	return {FPValue::FromDecimal(std::log(dval))};
}

FPCollection Evaluator::fn_log(const FPCollection &input, const FPCollection &base) {
	if (input.empty() || base.empty()) {
		return {};
	}
	if (base.size() > 1) {
		throw FHIRPathSpecError("log() base argument requires a single item collection");
	}
	auto &val = input[0];
	auto &bval = base[0];
	if (!isNumericType(val)) {
		throw FHIRPathSpecError("log() requires a numeric input");
	}
	if (!isNumericType(bval)) {
		throw FHIRPathSpecError("log() base argument must be numeric");
	}
	double dval = getNumericValue(val);
	double b = getNumericValue(bval);
	if (dval <= 0 || b <= 0 || b == 1.0) {
		return {};
	}
	return {FPValue::FromDecimal(std::log(dval) / std::log(b))};
}

FPCollection Evaluator::fn_power(const FPCollection &input, const FPCollection &exponent) {
	if (input.empty() || exponent.empty()) {
		return {};
	}
	if (exponent.size() > 1) {
		throw FHIRPathSpecError("power() exponent argument requires a single item collection");
	}
	auto &baseVal = input[0];
	auto &expVal = exponent[0];
	if (!isNumericType(baseVal)) {
		throw FHIRPathSpecError("power() requires a numeric input");
	}
	if (!isNumericType(expVal)) {
		throw FHIRPathSpecError("power() exponent argument must be numeric");
	}
	double base = getNumericValue(baseVal);
	double exp = getNumericValue(expVal);
	// FHIRPath spec: 0^0 is undefined
	if (base == 0.0 && exp == 0.0) {
		return {};
	}
	double result = std::pow(base, exp);
	if (std::isnan(result) || std::isinf(result)) {
		return {};
	}
	if (effectiveType(baseVal) == FPValue::Type::Integer &&
	    effectiveType(expVal) == FPValue::Type::Integer &&
	    exp >= 0.0 &&
	    result >= static_cast<double>(INT64_MIN) &&
	    result <= static_cast<double>(INT64_MAX) &&
	    std::floor(result) == result) {
		return {FPValue::FromInteger(static_cast<int64_t>(result))};
	}
	return {FPValue::FromDecimal(result)};
}

FPCollection Evaluator::fn_sqrt(const FPCollection &input) {
	if (input.empty()) {
		return {};
	}
	auto &val = input[0];
	if (!isNumericType(val)) {
		throw FHIRPathSpecError("sqrt() requires a numeric input");
	}
	double dval = getNumericValue(val);
	if (dval < 0) {
		return {};
	}
	return {FPValue::FromDecimal(std::sqrt(dval))};
}

FPCollection Evaluator::fn_truncate(const FPCollection &input) {
	if (input.empty()) {
		return {};
	}
	auto &val = input[0];
	if (!isNumericType(val)) {
		throw FHIRPathSpecError("truncate() requires a numeric input");
	}
	double raw = getNumericValue(val);
	if (raw > static_cast<double>(INT64_MAX) || raw < static_cast<double>(INT64_MIN)) {
		return {};
	}
	return {FPValue::FromInteger(static_cast<int64_t>(raw))};
}

FPCollection Evaluator::fn_iif(const ASTNode &criterion, const ASTNode &trueResult, const ASTNode *falseResult,
                               const FPCollection &input, yyjson_doc *doc) {
	// Conversion-section functions evaluate against an empty or singleton input.
	if (input.size() > 1) {
		throw FHIRPathSpecError("iif() requires a single item input collection");
	}

	auto saved_vars = defined_variables_;
	auto cond = eval(criterion, input, doc);
	defined_variables_ = saved_vars; // Restore after criterion evaluation
	
	if (cond.size() > 1) {
		throw FHIRPathSpecError("iif() criterion requires a single Boolean result");
	}
	// Empty criterion is falsey and selects the otherwise branch when present.
	if (cond.empty()) {
		if (falseResult) {
			auto saved_vars = defined_variables_;
			auto saved_chain = chain_defined_vars_;
			chain_defined_vars_.clear();
			auto result = eval(*falseResult, input, doc);
			defined_variables_ = saved_vars;
			chain_defined_vars_ = saved_chain;
			return result;
		}
		return {};
	}

	if (isTruthy(cond)) {
		auto saved_vars = defined_variables_;
		auto saved_chain = chain_defined_vars_;
		chain_defined_vars_.clear();
		auto result = eval(trueResult, input, doc);
		defined_variables_ = saved_vars;
		chain_defined_vars_ = saved_chain;
		return result;
	}
	if (falseResult) {
		auto saved_vars = defined_variables_;
		auto saved_chain = chain_defined_vars_;
		chain_defined_vars_.clear();
		auto result = eval(*falseResult, input, doc);
		defined_variables_ = saved_vars;
		chain_defined_vars_ = saved_chain;
		return result;
	}
	return {};
}

FPCollection Evaluator::fn_extension(const FPCollection &input, const FPCollection &url_arg) {
	if (url_arg.empty()) {
		return {};
	}
	std::string target_url = toString(url_arg[0]);

	FPCollection result;
	for (const auto &item : input) {
		// For JSON objects, look at direct extension field
		if (item.type == FPValue::Type::JsonVal && item.json_val && yyjson_is_obj(item.json_val)) {
			yyjson_val *extensions = yyjson_obj_get(item.json_val, "extension");
			if (extensions && yyjson_is_arr(extensions)) {
				size_t idx2, max2;
				yyjson_val *ext;
				yyjson_arr_foreach(extensions, idx2, max2, ext) {
					yyjson_val *url_val = yyjson_obj_get(ext, "url");
					if (url_val && yyjson_is_str(url_val)) {
						if (target_url == yyjson_get_str(url_val)) {
							result.push_back(FPValue::FromJson(ext));
						}
					}
				}
			}
			continue;
		}

		// For primitive values, check shadow field (_fieldName) on the parent resource
		if (!item.field_name.empty() && resource_context_ && yyjson_is_obj(resource_context_)) {
			std::string shadow = "_" + item.field_name;
			yyjson_val *shadow_obj = yyjson_obj_get(resource_context_, shadow.c_str());
			if (shadow_obj && yyjson_is_obj(shadow_obj)) {
				yyjson_val *extensions = yyjson_obj_get(shadow_obj, "extension");
				if (extensions && yyjson_is_arr(extensions)) {
					size_t idx2, max2;
					yyjson_val *ext;
					yyjson_arr_foreach(extensions, idx2, max2, ext) {
						yyjson_val *url_val = yyjson_obj_get(ext, "url");
						if (url_val && yyjson_is_str(url_val)) {
							if (target_url == yyjson_get_str(url_val)) {
								result.push_back(FPValue::FromJson(ext));
							}
						}
					}
				}
			}
		}
	}
	return result;
}

FPCollection Evaluator::fn_select(const ASTNode &projection, const FPCollection &input, yyjson_doc *doc) {
	FPCollection result;
	int64_t idx = 0;
	for (const auto &item : input) {
		FPCollection single = {item};
		int64_t old_index = index_context_;
		index_context_ = idx;
		auto saved_chain = chain_defined_vars_;
		chain_defined_vars_.clear();
		auto projected = eval(projection, single, doc);
		chain_defined_vars_ = saved_chain;
		index_context_ = old_index;
		result.insert(result.end(), projected.begin(), projected.end());
		++idx;
	}
	return result;
}

FPCollection Evaluator::fn_repeat(const ASTNode &projection, const FPCollection &input, yyjson_doc *doc) {
	// repeat evaluates expression on each item, adds new results, deduplicates
	FPCollection result;
	FPCollection seen;
	FPCollection work = input;

	size_t iterations = 0;
	int64_t repeat_idx = 0;
	while (!work.empty()) {
		FPCollection next;
		for (const auto &item : work) {
			FPCollection single_col = {item};
			int64_t old_index = index_context_;
			index_context_ = repeat_idx;
			auto saved_chain = chain_defined_vars_;
			chain_defined_vars_.clear();
			auto projected = eval(projection, single_col, doc);
			chain_defined_vars_ = saved_chain;
			index_context_ = old_index;
			for (const auto &p : projected) {
				bool is_seen = false;
				for (const auto &s : seen) {
					if (fpValuesEqual(s, p)) {
						is_seen = true;
						break;
					}
				}
				if (!is_seen) {
					seen.push_back(p);
					result.push_back(p);
					next.push_back(p);
				}
			}
			++repeat_idx;
		}
		work = next;
		if (++iterations > 1000 || result.size() > 10000) {
			throw FHIRPathSpecError("repeat() infinite loop detected");
		}
	}

	return result;
}

FPCollection Evaluator::fn_distinct(const FPCollection &input) {
	// FHIRPath §5.1.2: Uses FHIRPath = operator for comparison
	FPCollection result;
	for (const auto &item : input) {
		bool found = false;
		for (const auto &existing : result) {
			if (fpValuesEqual(item, existing)) {
				found = true;
				break;
			}
		}
		if (!found) {
			result.push_back(item);
		}
	}
	return result;
}

FPCollection Evaluator::fn_trace(const FPCollection &input) {
	return input;
}

FPCollection Evaluator::fn_aggregate(const ASTNode &node, const FPCollection &input, yyjson_doc *doc,
                                     const FPCollection *outer_input) {
	// aggregate(aggregator [, init])
	if (node.children.empty()) {
		return {};
	}
	FPCollection saved_total = total_context_;
	int64_t saved_index = index_context_;
	auto saved_vars = defined_variables_;
	auto saved_chain_vars = chain_defined_vars_;

	if (node.children.size() >= 2) {
		const FPCollection &init_context = outer_input ? *outer_input : input;
		total_context_ = eval(*node.children[1], init_context, doc);
	} else {
		total_context_ = {};
	}

	for (size_t i = 0; i < input.size(); i++) {
		auto iter_vars = defined_variables_;
		auto iter_chain = chain_defined_vars_;
		index_context_ = static_cast<int64_t>(i);
		FPCollection single = {input[i]};
		total_context_ = eval(*node.children[0], single, doc);
		defined_variables_ = iter_vars;
		chain_defined_vars_ = iter_chain;
	}

	FPCollection result = total_context_;
	total_context_ = saved_total;
	index_context_ = saved_index;
	defined_variables_ = saved_vars;
	chain_defined_vars_ = saved_chain_vars;
	return result;
}

FPCollection Evaluator::fn_combine(const FPCollection &input, const FPCollection &other) {
	FPCollection result = input;
	result.insert(result.end(), other.begin(), other.end());
	return result;
}

FPCollection Evaluator::fn_union(const FPCollection &left, const FPCollection &right) {
	FPCollection result;
	// Deduplicate left side first using FHIRPath = operator (fpValuesEqual)
	for (const auto &item : left) {
		bool found = false;
		for (const auto &existing : result) {
			if (fpValuesEqual(item, existing)) { found = true; break; }
		}
		if (!found) result.push_back(item);
	}
	// Add right side elements not already present
	for (const auto &item : right) {
		bool found = false;
		for (const auto &existing : result) {
			if (fpValuesEqual(item, existing)) { found = true; break; }
		}
		if (!found) result.push_back(item);
	}
	return result;
}

FPCollection Evaluator::fn_intersect(const FPCollection &input, const FPCollection &other) {
	FPCollection result;
	for (const auto &item : input) {
		// Check if already in result (dedup) using FHIRPath = operator
		bool dup = false;
		for (const auto &r : result) {
			if (fpValuesEqual(item, r)) { dup = true; break; }
		}
		if (dup) continue;
		// Check if in other collection
		for (const auto &o : other) {
			if (fpValuesEqual(item, o)) {
				result.push_back(item);
				break;
			}
		}
	}
	return result;
}

FPCollection Evaluator::fn_exclude(const FPCollection &input, const FPCollection &other) {
	FPCollection result;
	for (const auto &item : input) {
		bool found = false;
		for (const auto &o : other) {
			if (fpValuesEqual(item, o)) {
				found = true;
				break;
			}
		}
		if (!found) {
			result.push_back(item);
		}
	}
	return result;
}

FPCollection Evaluator::fn_tail(const FPCollection &input) {
	if (input.size() <= 1) {
		return {};
	}
	return FPCollection(input.begin() + 1, input.end());
}

FPCollection Evaluator::fn_take(const FPCollection &input, const FPCollection &count) {
	if (count.empty()) {
		return {};
	}
	if (count.size() > 1) {
		throw FHIRPathSpecError("take() requires a single integer argument");
	}
	int64_t n = 0;
	if (!extractStrictInteger(count[0], n)) {
		throw FHIRPathSpecError("take() requires an integer argument");
	}
	if (input.empty()) {
		return {};
	}
	if (n <= 0) {
		return {};
	}
	size_t take_n = std::min(static_cast<size_t>(n), input.size());
	return FPCollection(input.begin(), input.begin() + static_cast<ptrdiff_t>(take_n));
}

FPCollection Evaluator::fn_skip(const FPCollection &input, const FPCollection &count) {
	if (count.empty()) {
		return {};
	}
	if (count.size() > 1) {
		throw FHIRPathSpecError("skip() requires a single integer argument");
	}
	int64_t n = 0;
	if (!extractStrictInteger(count[0], n)) {
		throw FHIRPathSpecError("skip() requires an integer argument");
	}
	if (input.empty()) {
		return {};
	}
	if (n <= 0) {
		return input;
	}
	if (static_cast<size_t>(n) >= input.size()) {
		return {};
	}
	return FPCollection(input.begin() + n, input.end());
}

// --- Helper: check if an FPCollection represents a boolean value ---
// Per FHIRPath spec, a single non-boolean value is treated as truthy for boolean operators
static bool collectionIsBool(const FPCollection &col, bool &out) {
	if (col.empty()) return false;
	if (col.size() > 1) {
		throw FHIRPathSpecError("Cannot convert a collection with multiple items to a boolean");
	}
	auto &v = col[0];
	if (v.type == FPValue::Type::Boolean) { out = v.bool_val; return true; }
	if (v.type == FPValue::Type::JsonVal && v.json_val && yyjson_is_bool(v.json_val)) {
		out = yyjson_get_bool(v.json_val); return true;
	}
	// Any other singleton value is truthy
	out = true;
	return true;
}

// --- Helper: parse date/datetime string components for comparison ---
static DateTimeParts parseDateTimeParts(const std::string &s) {
	DateTimeParts p;
	p.year = p.month = p.day = p.hour = p.minute = p.second = p.millisecond = 0;
	p.tz_offset_minutes = INT_MIN;
	p.precision = 0;
	p.valid = false;

	if (s.empty()) return p;

	// Parse year: must be exactly 4 digits at positions 0-3
	if (s.size() < 4) return p;
	if (!std::isdigit((unsigned char)s[0]) || !std::isdigit((unsigned char)s[1]) ||
	    !std::isdigit((unsigned char)s[2]) || !std::isdigit((unsigned char)s[3])) return p;
	p.year = std::atoi(s.substr(0, 4).c_str());
	if (p.year < 1 || p.year > 9999) {
		return p;
	}
	p.precision = 1;
	p.valid = true;
	if (s.size() <= 4) return p;
	if (s[4] == 'T') {
		if (s.size() == 5) return p;
		p.valid = false;
		return p;
	}
	if (s[4] != '-') { p.valid = false; return p; }

	// Parse month: must be exactly 2 digits at positions 5-6
	// If we have a '-' at pos 4, we MUST have at least 2 digit chars at pos 5-6
	if (s.size() < 7) { p.valid = false; return p; }  // Malformed: '-' present but month incomplete
	if (!std::isdigit((unsigned char)s[5]) || !std::isdigit((unsigned char)s[6])) { p.valid = false; return p; }  // Separator commits to month
	p.month = std::atoi(s.substr(5, 2).c_str());
	if (p.month < 1 || p.month > 12) { p.valid = false; return p; }
	p.precision = 2;
	if (s.size() <= 7) return p;
	if (s[7] == 'T') {
		if (s.size() == 8) return p;
		p.valid = false;
		return p;
	}
	if (s[7] != '-') { p.valid = false; return p; }

	// Parse day: must be exactly 2 digits at positions 8-9
	// If we have a '-' at pos 7, we MUST have at least 2 digit chars at pos 8-9
	if (s.size() < 10) { p.valid = false; return p; }  // Malformed: '-' present but day incomplete
	if (!std::isdigit((unsigned char)s[8]) || !std::isdigit((unsigned char)s[9])) { p.valid = false; return p; }
	p.day = std::atoi(s.substr(8, 2).c_str());
	if (p.day < 1 || p.day > 31) { p.valid = false; return p; }
	// Month/day validation with leap-year awareness for February
	static const int days_in_month_common[] = {0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31};
	int max_day = days_in_month_common[p.month];
	if (p.month == 2 && p.day == 29) {
		// Leap year check: divisible by 4, except centuries unless divisible by 400
		bool is_leap = (p.year % 4 == 0) && (p.year % 100 != 0 || p.year % 400 == 0);
		if (!is_leap) { p.valid = false; return p; }
	} else if (p.day > max_day) {
		p.valid = false;
		return p;
	}
	p.precision = 3;
	if (s.size() <= 10) return p;
	// Anything after the date portion must be 'T' (datetime) — reject trailing garbage
	if (s[10] != 'T') { p.valid = false; return p; }
	if (s.size() == 11) return p;

	auto consume_timezone = [&](size_t &tz_pos) -> bool {
		size_t pos = tz_pos;
		if (pos >= s.size()) {
			return true;
		}
		if (s[pos] == 'Z') {
			p.tz_offset_minutes = 0;
			pos++;
		} else if (s[pos] == '+' || s[pos] == '-') {
			int sign = (s[pos] == '+') ? 1 : -1;
			if (pos + 6 > s.size() || s[pos + 3] != ':') {
				p.valid = false;
				return false;
			}
			if (!std::isdigit(static_cast<unsigned char>(s[pos + 1])) ||
			    !std::isdigit(static_cast<unsigned char>(s[pos + 2])) ||
			    !std::isdigit(static_cast<unsigned char>(s[pos + 4])) ||
			    !std::isdigit(static_cast<unsigned char>(s[pos + 5]))) {
				p.valid = false;
				return false;
			}
			int tz_h = std::atoi(s.substr(pos + 1, 2).c_str());
			int tz_m = std::atoi(s.substr(pos + 4, 2).c_str());
			if (tz_h < 0 || tz_h > 23 || tz_m < 0 || tz_m > 59) {
				p.valid = false;
				return false;
			}
			p.tz_offset_minutes = sign * (tz_h * 60 + tz_m);
			pos += 6;
		} else {
			p.valid = false;
			return false;
		}
		if (pos != s.size()) {
			p.valid = false;
			return false;
		}
		tz_pos = pos;
		return true;
	};

	// Parse hour
	if (s.size() < 13) { p.valid = false; return p; }
	if (!std::isdigit(static_cast<unsigned char>(s[11])) ||
	    !std::isdigit(static_cast<unsigned char>(s[12]))) { p.valid = false; return p; }
	p.hour = std::atoi(s.substr(11, 2).c_str());
	if (p.hour < 0 || p.hour > 23) { p.valid = false; return p; }
	p.precision = 4;
	size_t pos = 13;
	if (pos >= s.size()) {
		// FHIRPath: hour-only precision (e.g. @2018-01-01T10) is precision 4.
		// Do NOT promote to minute-level -- precision mismatch with minute-level
		// DateTime must return empty per spec §6.2.
		return p;
	}
	if (s[pos] == 'Z' || s[pos] == '+' || s[pos] == '-') {
		consume_timezone(pos);
		return p;
	}
	if (s[pos] != ':') { p.valid = false; return p; }

	// Parse minute
	pos++;
	if (pos + 2 > s.size()) { p.valid = false; return p; }
	if (!std::isdigit(static_cast<unsigned char>(s[pos])) ||
	    !std::isdigit(static_cast<unsigned char>(s[pos + 1]))) { p.valid = false; return p; }
	p.minute = std::atoi(s.substr(pos, 2).c_str());
	if (p.minute < 0 || p.minute > 59) { p.valid = false; return p; }
	p.precision = 5;
	pos += 2;
	if (pos >= s.size()) return p;
	if (s[pos] == 'Z' || s[pos] == '+' || s[pos] == '-') {
		consume_timezone(pos);
		return p;
	}
	if (s[pos] != ':') { p.valid = false; return p; }

	// Parse second
	pos++;
	if (pos + 2 > s.size()) { p.valid = false; return p; }
	if (!std::isdigit(static_cast<unsigned char>(s[pos])) ||
	    !std::isdigit(static_cast<unsigned char>(s[pos + 1]))) { p.valid = false; return p; }
	p.second = std::atoi(s.substr(pos, 2).c_str());
	if (p.second < 0 || p.second > 59) { p.valid = false; return p; }
	p.precision = 6;
	pos += 2;

	if (pos < s.size() && s[pos] == '.') {
		pos++;
		std::string ms_str;
		while (pos < s.size() && std::isdigit(static_cast<unsigned char>(s[pos]))) {
			ms_str += s[pos++];
		}
		if (ms_str.empty()) { p.valid = false; return p; }
		while (ms_str.size() < 3) ms_str += '0';
		p.millisecond = std::atoi(ms_str.substr(0, 3).c_str());
		p.precision = 7;
	}

	// Parse timezone
	if (pos < s.size()) {
		consume_timezone(pos);
	}

	return p;
}

static DateTimeParts parseTimeParts(const std::string &s) {
	DateTimeParts p;
	p.year = p.month = p.day = p.hour = p.minute = p.second = p.millisecond = 0;
	p.tz_offset_minutes = INT_MIN;
	p.precision = 0;
	p.valid = false;

	if (s.empty()) return p;
	size_t pos = 0;
	if (s[0] == 'T') pos = 1;

	// Hour: exactly 2 digits
	if (pos + 2 > s.size()) return p;
	if (!std::isdigit(static_cast<unsigned char>(s[pos])) ||
	    !std::isdigit(static_cast<unsigned char>(s[pos + 1]))) return p;
	p.hour = std::atoi(s.substr(pos, 2).c_str());
	if (p.hour < 0 || p.hour > 23) { p.valid = false; return p; }
	p.precision = 4;
	p.valid = true;
	pos += 2;

	if (pos >= s.size()) return p;
	if (s[pos] != ':') { p.valid = false; return p; }
	pos++;
	// Minute: exactly 2 digits
	if (pos + 2 > s.size()) return p;
	if (!std::isdigit(static_cast<unsigned char>(s[pos])) ||
	    !std::isdigit(static_cast<unsigned char>(s[pos + 1]))) return p;
	p.minute = std::atoi(s.substr(pos, 2).c_str());
	if (p.minute < 0 || p.minute > 59) { p.valid = false; return p; }
	p.precision = 5;
	pos += 2;

	if (pos >= s.size()) return p;
	if (s[pos] != ':') { p.valid = false; return p; }
	pos++;
	// Second: exactly 2 digits
	if (pos + 2 > s.size()) return p;
	if (!std::isdigit(static_cast<unsigned char>(s[pos])) ||
	    !std::isdigit(static_cast<unsigned char>(s[pos + 1]))) return p;
	p.second = std::atoi(s.substr(pos, 2).c_str());
	if (p.second < 0 || p.second > 59) { p.valid = false; return p; }
	p.precision = 6;
	pos += 2;

	if (pos < s.size() && s[pos] == '.') {
		pos++;
		std::string ms_str;
		while (pos < s.size() && std::isdigit(static_cast<unsigned char>(s[pos]))) {
			ms_str += s[pos++];
		}
		if (ms_str.empty()) { p.valid = false; return p; }
		while (ms_str.size() < 3) ms_str += '0';
		p.millisecond = std::atoi(ms_str.substr(0, 3).c_str());
		p.precision = 7;
	}

	if (pos != s.size()) {
		p.valid = false;
	}

	return p;
}

// Normalize a DateTimeParts to UTC
static void normalizeToUTC(DateTimeParts &p) {
	if (p.tz_offset_minutes == INT_MIN || p.tz_offset_minutes == 0) return;
	// Subtract offset to get UTC
	int total_minutes = p.hour * 60 + p.minute - p.tz_offset_minutes;
	int day_adj = 0;
	if (total_minutes < 0) { total_minutes += 24 * 60; day_adj = -1; }
	if (total_minutes >= 24 * 60) { total_minutes -= 24 * 60; day_adj = 1; }
	p.hour = total_minutes / 60;
	p.minute = total_minutes % 60;
	p.day += day_adj;
	// Simple month/year rollover
	int days_in_month[] = {31,28,31,30,31,30,31,31,30,31,30,31};
	bool leap = (p.year % 4 == 0 && (p.year % 100 != 0 || p.year % 400 == 0));
	if (leap) days_in_month[1] = 29;
	if (p.day < 1 && p.month > 1) {
		p.month--;
		p.day += days_in_month[p.month - 1];
	} else if (p.day < 1) {
		p.year--;
		p.month = 12;
		p.day += 31;
	}
	if (p.month >= 1 && p.month <= 12 && p.day > days_in_month[p.month - 1]) {
		p.day -= days_in_month[p.month - 1];
		p.month++;
		if (p.month > 12) { p.month = 1; p.year++; }
	}
	p.tz_offset_minutes = 0;
}

// Compare two date/time values. Returns -1, 0, 1, or INT_MIN if incomparable (different precision)
static int compareDateTimes(const std::string &a, const std::string &b,
                            FPValue::Type a_type, FPValue::Type b_type,
                            bool is_equivalence = false, bool is_equality = false) {
	bool a_is_time = (a_type == FPValue::Type::Time);
	bool b_is_time = (b_type == FPValue::Type::Time);

	// Date/DateTime vs Time → incomparable
	if (a_is_time != b_is_time) return INT_MIN;

	DateTimeParts pa, pb;
	if (a_is_time) pa = parseTimeParts(a); else pa = parseDateTimeParts(a);
	if (b_is_time) pb = parseTimeParts(b); else pb = parseDateTimeParts(b);

	if (!pa.valid || !pb.valid) return INT_MIN;

	// Timezone handling
	bool both_have_tz = (pa.tz_offset_minutes != INT_MIN && pb.tz_offset_minutes != INT_MIN);
	bool tz_mismatch = ((pa.tz_offset_minutes != INT_MIN) != (pb.tz_offset_minutes != INT_MIN));
	if (both_have_tz) {
		normalizeToUTC(pa);
		normalizeToUTC(pb);
	} else if (tz_mismatch && is_equality && !is_equivalence) {
		// For strict equality, TZ mismatch is incomparable
		return INT_MIN;
	}
	// For comparison/equivalence with TZ mismatch, compare raw values at shared precision

	int min_prec = std::min(pa.precision, pb.precision);
	int max_prec = std::max(pa.precision, pb.precision);

	// Seconds (6) and milliseconds (7) are the SAME precision level in FHIRPath.
	// "31" and "31.0" and "31.100" are all second-level representations.
	int norm_min = (min_prec == 7) ? 6 : min_prec;
	int norm_max = (max_prec == 7) ? 6 : max_prec;
	bool same_precision_level = (norm_min == norm_max);

	// Compare at shared precision first (all fields up to min_prec)
	int fields_a[] = {pa.year, pa.month, pa.day, pa.hour, pa.minute, pa.second, pa.millisecond};
	int fields_b[] = {pb.year, pb.month, pb.day, pb.hour, pb.minute, pb.second, pb.millisecond};
	int start_idx = a_is_time ? 3 : 0;
	// Always compare through milliseconds if both have second-level precision
	int cmp_to = same_precision_level ? max_prec : min_prec;
	for (int i = start_idx; i < cmp_to; i++) {
		if (fields_a[i] < fields_b[i]) return -1;
		if (fields_a[i] > fields_b[i]) return 1;
	}
	// Equal at all compared fields
	if (same_precision_level) return 0;

	// Different precision levels, equal at shared fields → incomparable
	return INT_MIN;
}

// --- Binary operators ---

static std::string stripQuantityUnitQuotes(const std::string &unit);

FPCollection Evaluator::evalBinaryOp(const ASTNode &node, const FPCollection &input, yyjson_doc *doc) {
	const auto &op = node.op;

	FHIRPATH_REQUIRE_CHILDREN(node, 2);

	// Boolean operators with three-valued logic (empty = unknown)
	if (op == "and") {
		auto left = eval(*node.children[0], input, doc);
		auto right = eval(*node.children[1], input, doc);
		bool l_val, r_val;
		bool l_has = collectionIsBool(left, l_val);
		bool r_has = collectionIsBool(right, r_val);

		if (l_has && r_has) return {FPValue::FromBoolean(l_val && r_val)};
		if (l_has && !l_val) return {FPValue::FromBoolean(false)};  // false and {} = false
		if (r_has && !r_val) return {FPValue::FromBoolean(false)};  // {} and false = false
		return {};  // true and {} = {}, {} and {} = {}
	}
	if (op == "or") {
		auto left = eval(*node.children[0], input, doc);
		auto right = eval(*node.children[1], input, doc);
		bool l_val, r_val;
		bool l_has = collectionIsBool(left, l_val);
		bool r_has = collectionIsBool(right, r_val);

		if (l_has && r_has) return {FPValue::FromBoolean(l_val || r_val)};
		if (l_has && l_val) return {FPValue::FromBoolean(true)};   // true or {} = true
		if (r_has && r_val) return {FPValue::FromBoolean(true)};   // {} or true = true
		return {};  // false or {} = {}, {} or {} = {}
	}
	if (op == "xor") {
		auto left = eval(*node.children[0], input, doc);
		auto right = eval(*node.children[1], input, doc);
		bool l_val, r_val;
		bool l_has = collectionIsBool(left, l_val);
		bool r_has = collectionIsBool(right, r_val);

		if (l_has && r_has) return {FPValue::FromBoolean(l_val != r_val)};
		return {};  // any empty → empty
	}
	if (op == "implies") {
		auto left = eval(*node.children[0], input, doc);
		bool l_val;
		bool l_has = collectionIsBool(left, l_val);

		if (l_has && !l_val) return {FPValue::FromBoolean(true)};  // false implies X = true

		auto right = eval(*node.children[1], input, doc);
		bool r_val;
		bool r_has = collectionIsBool(right, r_val);

		if (!l_has) {
			// {} implies true = true, {} implies false/empty = empty
			if (r_has && r_val) return {FPValue::FromBoolean(true)};
			return {};
		}
		// l_val is true
		if (r_has) return {FPValue::FromBoolean(r_val)};
		return {};  // true implies {} = {}
	}

	auto left = eval(*node.children[0], input, doc);
	auto right = eval(*node.children[1], input, doc);

	// String concatenation (&) - empty treated as empty string, not propagated
	if (op == "&") {
		if (left.size() > 1 || right.size() > 1) {
			throw FHIRPathSpecError("String concatenation requires collections with at most one item");
		}
		std::string l_str = left.empty() ? "" : toString(left[0]);
		std::string r_str = right.empty() ? "" : toString(right[0]);
		return {FPValue::FromString(l_str + r_str)};
	}

	// Membership operators (use fpValuesEqual per FHIRPath = semantics)
	// Spec §6.4.2: in returns true if the left element is equal to an item in the right
	// Spec §6.4.3: contains returns true if an item in the left is equal to the right element
	if (op == "in") {
		if (left.empty()) return {};
		if (left.size() > 1) {
			throw FHIRPathSpecError("in requires the left operand to contain at most one item");
		}
		// Single element in empty collection → false
		if (right.empty()) return {FPValue::FromBoolean(false)};
		for (const auto &item : right) {
			if (fpValuesEqual(item, left[0])) {
				return {FPValue::FromBoolean(true)};
			}
		}
		return {FPValue::FromBoolean(false)};
	}
	if (op == "contains") {
		if (right.empty()) return {};
		if (right.size() > 1) {
			throw FHIRPathSpecError("contains requires the right operand to contain at most one item");
		}
		// Empty collection contains single element → false
		if (left.empty()) return {FPValue::FromBoolean(false)};
		for (const auto &item : left) {
			if (fpValuesEqual(item, right[0])) {
				return {FPValue::FromBoolean(true)};
			}
		}
		return {FPValue::FromBoolean(false)};
	}

	// Empty propagation for equality, comparison, arithmetic
	if (left.empty() || right.empty()) {
		// Equivalence operators handle empty differently
		if (op == "~") {
			return {FPValue::FromBoolean(left.empty() && right.empty())};
		}
		if (op == "!~") {
			return {FPValue::FromBoolean(!(left.empty() && right.empty()))};
		}
		return {};
	}

	// Convert JSON Quantity objects to FPValue::Quantity for comparison
	auto maybeConvertQuantity = [](FPCollection &col) {
		if (col.size() == 1 && col[0].type == FPValue::Type::JsonVal) {
			double val; std::string unit;
			if (tryJsonToQuantity(col[0], val, unit)) {
				FPValue q;
				q.type = FPValue::Type::Quantity;
				q.quantity_value = val;
				q.quantity_unit = unit;
				col[0] = q;
			}
		}
	};
	if (op == "=" || op == "~" || op == "!=" || op == "!~" ||
	    op == "<" || op == ">" || op == "<=" || op == ">=") {
		if ((left.size() == 1 && isQuantityLike(left[0])) ||
		    (right.size() == 1 && isQuantityLike(right[0]))) {
			maybeConvertQuantity(left);
			maybeConvertQuantity(right);
		}
	}

	// Equality
	if (op == "=" || op == "~" || op == "!=" || op == "!~") {
		bool is_equiv = (op == "~" || op == "!~");
		auto valuesEquivalent = [this](const FPValue &lv, const FPValue &rv) -> bool {
			FPValue lq, rq;
			if (fpValueAsQuantity(lv, lq) && fpValueAsQuantity(rv, rq)) {
				std::string l_base, r_base;
				double l_conv = convertQuantityToBase(lq.quantity_value, lq.quantity_unit, l_base);
				double r_conv = convertQuantityToBase(rq.quantity_value, rq.quantity_unit, r_base);
				if (l_base != r_base) return false;
				int l_dp = countDecimalPlaces(lq);
				int r_dp = countDecimalPlaces(rq);
				double l_scale = (lq.quantity_value != 0) ? l_conv / lq.quantity_value : 1.0;
				double r_scale = (rq.quantity_value != 0) ? r_conv / rq.quantity_value : 1.0;
				double l_half = 0.5 * std::pow(10.0, -l_dp) * std::abs(l_scale);
				double r_half = 0.5 * std::pow(10.0, -r_dp) * std::abs(r_scale);
				return std::abs(l_conv - r_conv) < std::max(l_half, r_half);
			}
			if (isDateTimeType(lv) && isDateTimeType(rv)) {
				auto lt = effectiveType(lv);
				auto rt = effectiveType(rv);
				if (isDateVsDateTimePair(lt, rt)) return false;
				bool l_is_time = (lt == FPValue::Type::Time);
				bool r_is_time = (rt == FPValue::Type::Time);
				if (l_is_time != r_is_time) return false;
				return compareDateTimes(this->toString(lv), this->toString(rv), lt, rt, true, false) == 0;
			}
			if (isNumericType(lv) && isNumericType(rv)) {
				double l_num = getNumericValue(lv);
				double r_num = getNumericValue(rv);
				int l_prec = 0, r_prec = 0;
				std::string ls = this->toString(lv), rs = this->toString(rv);
				auto l_dot = ls.find('.');
				auto r_dot = rs.find('.');
				if (l_dot != std::string::npos) l_prec = (int)(ls.size() - l_dot - 1);
				if (r_dot != std::string::npos) r_prec = (int)(rs.size() - r_dot - 1);
				int cmp_prec = (l_prec > 0 && r_prec > 0) ? std::min(l_prec, r_prec)
				             : std::max(l_prec, r_prec);
				if (cmp_prec > 0) {
					double scale = std::pow(10.0, cmp_prec);
					return std::round(l_num * scale) == std::round(r_num * scale);
				}
				return (l_num == r_num) || std::abs(l_num - r_num) < 1e-10;
			}
			if (lv.type == FPValue::Type::JsonVal && rv.type == FPValue::Type::JsonVal &&
			    ((lv.json_val && (yyjson_is_obj(lv.json_val) || yyjson_is_arr(lv.json_val))) ||
			     (rv.json_val && (yyjson_is_obj(rv.json_val) || yyjson_is_arr(rv.json_val))))) {
				return jsonValuesEquivalent(lv.json_val, rv.json_val);
			}
			if (effectiveType(lv) == FPValue::Type::String && effectiveType(rv) == FPValue::Type::String) {
				return normalizeEquivalentString(this->toString(lv)) ==
				       normalizeEquivalentString(this->toString(rv));
			}
			if (effectiveType(lv) != effectiveType(rv)) return false;
			return this->toString(lv) == this->toString(rv);
		};
		auto valuesEqualState = [this](const FPValue &lv, const FPValue &rv) -> int {
			// Return 1 for true, 0 for false, and -1 for empty/indeterminate.
			if (isDateTimeType(lv) && isDateTimeType(rv)) {
				auto lt = effectiveType(lv);
				auto rt = effectiveType(rv);
				if (isDateVsDateTimePair(lt, rt)) return -1;
				bool l_is_time = (lt == FPValue::Type::Time);
				bool r_is_time = (rt == FPValue::Type::Time);
				if (l_is_time != r_is_time) return 0;
				int cmp = compareDateTimes(this->toString(lv), this->toString(rv), lt, rt, false, true);
				if (cmp == INT_MIN) return -1;
				return cmp == 0 ? 1 : 0;
			}

			if (isNumericType(lv) && isNumericType(rv)) {
				return fpValuesEqual(lv, rv) ? 1 : 0;
			}

			FPValue lq, rq;
			if (fpValueAsQuantity(lv, lq) && fpValueAsQuantity(rv, rq)) {
				bool mixed_calendar_ucum =
				    (isCalendarDurationUnit(lq.quantity_unit) && isUcumDurationUnit(rq.quantity_unit)) ||
				    (isUcumDurationUnit(lq.quantity_unit) && isCalendarDurationUnit(rq.quantity_unit));
				if (mixed_calendar_ucum &&
				    !(isSecondOrMillisecondDuration(lq.quantity_unit) && isSecondOrMillisecondDuration(rq.quantity_unit))) {
					return 0;
				}
				std::string l_base, r_base;
				convertQuantityToBase(lq.quantity_value, lq.quantity_unit, l_base);
				convertQuantityToBase(rq.quantity_value, rq.quantity_unit, r_base);
				if (l_base != r_base) return -1;
				return quantityValuesEqual(lq, rq) ? 1 : 0;
			}

			if (lv.type == FPValue::Type::JsonVal && rv.type == FPValue::Type::JsonVal &&
			    ((lv.json_val && (yyjson_is_obj(lv.json_val) || yyjson_is_arr(lv.json_val))) ||
			     (rv.json_val && (yyjson_is_obj(rv.json_val) || yyjson_is_arr(rv.json_val))))) {
				return jsonValuesEqualState(lv.json_val, rv.json_val);
			}

			if (effectiveType(lv) != effectiveType(rv)) return -1;
			return fpValuesEqual(lv, rv) ? 1 : 0;
		};
		// Multi-element collection comparison
		if (left.size() > 1 || right.size() > 1) {
			if (left.size() != right.size()) {
				if (is_equiv) return {FPValue::FromBoolean(op == "!~")};
				return {FPValue::FromBoolean(op == "!=")};
			}
			if (is_equiv) {
				std::vector<bool> matched(right.size(), false);
				bool all_match = true;
				for (size_t i = 0; i < left.size(); ++i) {
					bool found = false;
					for (size_t j = 0; j < right.size(); ++j) {
						if (!matched[j] && valuesEquivalent(left[i], right[j])) {
							matched[j] = true;
							found = true;
							break;
						}
					}
					if (!found) { all_match = false; break; }
				}
				return {FPValue::FromBoolean(op == "~" ? all_match : !all_match)};
			} else {
				bool all_match = true;
				for (size_t i = 0; i < left.size(); ++i) {
					int equality_state = valuesEqualState(left[i], right[i]);
					if (equality_state < 0) {
						return {};
					}
					if (equality_state == 0) {
						all_match = false;
						break;
					}
				}
				return {FPValue::FromBoolean(op == "=" ? all_match : !all_match)};
			}
		}

		auto &lv = left[0];
		auto &rv = right[0];
		bool is_eq = false;

		// Date/time equality with precision
		if (isDateTimeType(lv) && isDateTimeType(rv)) {
			auto lt = effectiveType(lv);
			auto rt = effectiveType(rv);
			if (isDateVsDateTimePair(lt, rt)) {
				if (op == "=" || op == "!=") return {};
				is_eq = false;
			} else {
				bool l_is_time = (lt == FPValue::Type::Time);
				bool r_is_time = (rt == FPValue::Type::Time);
				// Date/DateTime vs Time → fundamentally different types, not equal
				if (l_is_time != r_is_time) {
					is_eq = false;
				} else {
					bool is_eq_op = (op == "=" || op == "!=");
					int cmp = compareDateTimes(toString(lv), toString(rv), lt, rt, is_equiv, is_eq_op);
					if (cmp == INT_MIN) {
						if (is_eq_op) return {};
						is_eq = false;
					} else {
						is_eq = (cmp == 0);
					}
				}
			}
		} else if (isNumericType(lv) && isNumericType(rv)) {
			double l_num = getNumericValue(lv);
			double r_num = getNumericValue(rv);
			if (is_equiv) {
				// Equivalence: compare at the precision of the least precise value
				int l_prec = 0, r_prec = 0;
				std::string ls = toString(lv), rs = toString(rv);
				auto l_dot = ls.find('.');
				auto r_dot = rs.find('.');
				if (l_dot != std::string::npos) l_prec = (int)(ls.size() - l_dot - 1);
				if (r_dot != std::string::npos) r_prec = (int)(rs.size() - r_dot - 1);
				int cmp_prec = (l_prec > 0 && r_prec > 0) ? std::min(l_prec, r_prec)
				             : std::max(l_prec, r_prec);
				if (cmp_prec > 0) {
					double scale = std::pow(10.0, cmp_prec);
					is_eq = (std::round(l_num * scale) == std::round(r_num * scale));
				} else {
					is_eq = (l_num == r_num) || std::abs(l_num - r_num) < 1e-10;
				}
			} else {
				double diff = std::abs(l_num - r_num);
				double maxval = std::max(std::abs(l_num), std::abs(r_num));
				is_eq = (l_num == r_num) || diff < 1e-10 || (maxval > 0 && diff / maxval < 1e-10);
			}
		} else if (lv.type == FPValue::Type::Quantity && rv.type == FPValue::Type::Quantity) {
			bool mixed_calendar_ucum =
			    (isCalendarDurationUnit(lv.quantity_unit) && isUcumDurationUnit(rv.quantity_unit)) ||
			    (isUcumDurationUnit(lv.quantity_unit) && isCalendarDurationUnit(rv.quantity_unit));
			if (!is_equiv && mixed_calendar_ucum &&
			    !(isSecondOrMillisecondDuration(lv.quantity_unit) && isSecondOrMillisecondDuration(rv.quantity_unit))) {
				is_eq = false;
			} else {
				std::string l_base, r_base;
				double l_conv = convertQuantityToBase(lv.quantity_value, lv.quantity_unit, l_base);
				double r_conv = convertQuantityToBase(rv.quantity_value, rv.quantity_unit, r_base);
				if (l_base == r_base) {
					if (is_equiv) {
						// Equivalence: compare with precision tolerance
						int l_dp = countDecimalPlaces(lv);
						int r_dp = countDecimalPlaces(rv);
						// Get the scale factor to convert precision from original units
						double l_scale = (lv.quantity_value != 0) ? l_conv / lv.quantity_value : 1.0;
						double r_scale = (rv.quantity_value != 0) ? r_conv / rv.quantity_value : 1.0;
						double l_half = 0.5 * std::pow(10.0, -l_dp) * std::abs(l_scale);
						double r_half = 0.5 * std::pow(10.0, -r_dp) * std::abs(r_scale);
						double tolerance = std::max(l_half, r_half);
						is_eq = (std::abs(l_conv - r_conv) < tolerance);
					} else {
						is_eq = quantityValuesEqual(lv, rv);
					}
				} else {
					// Incompatible units: return empty for = and !=
					if (op == "=" || op == "!=") return {};
					is_eq = false;
				}
			}
		} else if (lv.type == FPValue::Type::JsonVal && rv.type == FPValue::Type::JsonVal &&
		           ((lv.json_val && (yyjson_is_obj(lv.json_val) || yyjson_is_arr(lv.json_val))) ||
		            (rv.json_val && (yyjson_is_obj(rv.json_val) || yyjson_is_arr(rv.json_val))))) {
			if (is_equiv) {
				is_eq = jsonValuesEquivalent(lv.json_val, rv.json_val);
			} else {
				int state = jsonValuesEqualState(lv.json_val, rv.json_val);
				if (state < 0) return {};
				is_eq = state == 1;
			}
		} else if (is_equiv && effectiveType(lv) == FPValue::Type::String && effectiveType(rv) == FPValue::Type::String) {
			// Equivalence: case-insensitive, whitespace-normalized comparison (FHIRPath §6.5)
			is_eq = (normalizeEquivalentString(toString(lv)) == normalizeEquivalentString(toString(rv)));
		} else {
			// Incompatible types
			auto lt = effectiveType(lv);
			auto rt = effectiveType(rv);
			if (lt != rt) {
				// FHIRPath §6.1: = between incompatible types returns empty
				if (op == "=" || op == "!=") return {};
				// Equivalence (~) between incompatible types returns false
				is_eq = false;
			} else {
				is_eq = (toString(lv) == toString(rv));
			}
		}

		if (op == "=" || op == "~") return {FPValue::FromBoolean(is_eq)};
		return {FPValue::FromBoolean(!is_eq)};
	}

	// Comparison
	if (op == "<" || op == ">" || op == "<=" || op == ">=") {
		if (left.size() > 1 || right.size() > 1) {
			throw FHIRPathSpecError("Comparison operators require singleton operands");
		}
		auto &lv = left[0];
		auto &rv = right[0];

		// Date/time comparison
		if (isDateTimeType(lv) && isDateTimeType(rv)) {
			int cmp = compareDateTimes(toString(lv), toString(rv), effectiveType(lv), effectiveType(rv));
			if (cmp == INT_MIN) return {};
			if (op == "<") return {FPValue::FromBoolean(cmp < 0)};
			if (op == ">") return {FPValue::FromBoolean(cmp > 0)};
			if (op == "<=") return {FPValue::FromBoolean(cmp <= 0)};
			return {FPValue::FromBoolean(cmp >= 0)};
		}

		// Quantity comparison with unit conversion
		if (lv.type == FPValue::Type::Quantity && rv.type == FPValue::Type::Quantity) {
			if (isMixedCalendarUcumDurationAboveSeconds(lv.quantity_unit, rv.quantity_unit)) return {};
			std::string l_base, r_base;
			double l_conv = convertQuantityToBase(lv.quantity_value, lv.quantity_unit, l_base);
			double r_conv = convertQuantityToBase(rv.quantity_value, rv.quantity_unit, r_base);
			if (l_base != r_base) return {};
			if (op == "<") return {FPValue::FromBoolean(l_conv < r_conv)};
			if (op == ">") return {FPValue::FromBoolean(l_conv > r_conv)};
			if (op == "<=") return {FPValue::FromBoolean(l_conv <= r_conv)};
			return {FPValue::FromBoolean(l_conv >= r_conv)};
		}

		// FHIRPath §6.2 defines ordering for strings, numerics,
		// quantities, dates, datetimes, and times, but not Boolean.
		auto lt = effectiveType(lv);
		auto rt = effectiveType(rv);
		if (lt == FPValue::Type::Boolean && rt == FPValue::Type::Boolean) {
			throw FHIRPathSpecError("Comparison operators are not defined for Boolean operands");
		}

		// Numeric comparison
		if (isNumericType(lv) && isNumericType(rv)) {
			double l_num = getNumericValue(lv);
			double r_num = getNumericValue(rv);
			if (op == "<") return {FPValue::FromBoolean(l_num < r_num)};
			if (op == ">") return {FPValue::FromBoolean(l_num > r_num)};
			if (op == "<=") return {FPValue::FromBoolean(l_num <= r_num)};
			return {FPValue::FromBoolean(l_num >= r_num)};
		}
		// One numeric, one not → incompatible
		if (isNumericType(lv) || isNumericType(rv)) return {};

		// String comparison - lexicographic, only between same types
		if (lt == FPValue::Type::String && rt == FPValue::Type::String) {
			std::string l_str = toString(lv);
			std::string r_str = toString(rv);
			if (op == "<") return {FPValue::FromBoolean(l_str < r_str)};
			if (op == ">") return {FPValue::FromBoolean(l_str > r_str)};
			if (op == "<=") return {FPValue::FromBoolean(l_str <= r_str)};
			return {FPValue::FromBoolean(l_str >= r_str)};
		}
		// Incompatible types → empty
		return {};
	}

	// Arithmetic
	if (op == "+" || op == "-" || op == "*" || op == "/" || op == "div" || op == "mod") {
		if (left.size() > 1 || right.size() > 1) {
			throw FHIRPathSpecError(std::string("Operator '") + op + "' requires a single item input collection");
		}
		auto &lv = left[0];
		auto &rv = right[0];

		// String concatenation with +
		if (op == "+") {
			if (effectiveType(lv) == FPValue::Type::String && effectiveType(rv) == FPValue::Type::String) {
				return {FPValue::FromString(toString(lv) + toString(rv))};
			}
		}

		// Date/Time ± quantity (date arithmetic)
		if ((op == "+" || op == "-") &&
		    (temporalArithmeticType(lv) == FPValue::Type::Date ||
		     temporalArithmeticType(lv) == FPValue::Type::DateTime ||
		     temporalArithmeticType(lv) == FPValue::Type::Time) &&
		    rv.type == FPValue::Type::Quantity) {
			return fn_dateArith(lv, rv, op == "-");
		}
		if (temporalArithmeticType(lv) == FPValue::Type::Date ||
		    temporalArithmeticType(lv) == FPValue::Type::DateTime ||
		    temporalArithmeticType(lv) == FPValue::Type::Time ||
		    temporalArithmeticType(rv) == FPValue::Type::Date ||
		    temporalArithmeticType(rv) == FPValue::Type::DateTime ||
		    temporalArithmeticType(rv) == FPValue::Type::Time) {
			throw FHIRPathSpecError("Invalid operands for date/time arithmetic");
		}

		// Quantity arithmetic
		if (lv.type == FPValue::Type::Quantity && rv.type == FPValue::Type::Quantity) {
			if (op == "+" || op == "-") {
				// If units are identical, operate directly and preserve original units
				if (lv.quantity_unit == rv.quantity_unit) {
					double result_val = (op == "+") ? lv.quantity_value + rv.quantity_value
					                                : lv.quantity_value - rv.quantity_value;
					FPValue v;
					v.type = FPValue::Type::Quantity;
					v.quantity_value = result_val;
					v.quantity_unit = lv.quantity_unit;
					return {v};
				}
				// Different units: convert to base for compatibility check
				std::string l_base, r_base;
				double l_conv = convertQuantityToBase(lv.quantity_value, lv.quantity_unit, l_base);
				double r_conv = convertQuantityToBase(rv.quantity_value, rv.quantity_unit, r_base);
				if (l_base != r_base) return {};
				double result_val = (op == "+") ? l_conv + r_conv : l_conv - r_conv;
				FPValue v;
				v.type = FPValue::Type::Quantity;
				v.quantity_value = result_val;
				v.quantity_unit = l_base;
				return {v};
			}
			if (op == "*") {
				// Convert both to base units, multiply
				std::string l_base, r_base;
				double l_conv = convertQuantityToBase(lv.quantity_value, lv.quantity_unit, l_base);
				double r_conv = convertQuantityToBase(rv.quantity_value, rv.quantity_unit, r_base);
				double result_val = l_conv * r_conv;
				if (l_base == r_base) {
					FPValue v; v.type = FPValue::Type::Quantity;
					v.quantity_value = result_val;
					v.quantity_unit = l_base + "2";
					return {v};
				}
				FPValue v; v.type = FPValue::Type::Quantity;
				v.quantity_value = result_val;
				v.quantity_unit = l_base + "." + r_base;
				return {v};
			}
			if (op == "/") {
				std::string l_base, r_base;
				double l_conv = convertQuantityToBase(lv.quantity_value, lv.quantity_unit, l_base);
				double r_conv = convertQuantityToBase(rv.quantity_value, rv.quantity_unit, r_base);
				if (r_conv == 0) return {};
				double result_val = l_conv / r_conv;
				if (l_base == r_base) {
					// Same unit cancels out to the UCUM dimensionless unit.
					FPValue v; v.type = FPValue::Type::Quantity;
					v.quantity_value = result_val;
					v.quantity_unit = "1";
					return {v};
				}
				FPValue v; v.type = FPValue::Type::Quantity;
				v.quantity_value = result_val;
				v.quantity_unit = l_base + "/" + r_base;
				return {v};
			}
		}
		// Quantity * number or number * quantity
		if ((lv.type == FPValue::Type::Quantity && isNumericType(rv)) ||
		    (isNumericType(lv) && rv.type == FPValue::Type::Quantity)) {
			if (op == "*" || op == "/") {
				double qval, nval;
				std::string qunit;
				if (lv.type == FPValue::Type::Quantity) {
					qval = lv.quantity_value; qunit = lv.quantity_unit; nval = getNumericValue(rv);
					if (op == "/" && nval == 0) return {};
					FPValue v; v.type = FPValue::Type::Quantity; v.quantity_unit = qunit;
					v.quantity_value = (op == "*") ? qval * nval : qval / nval;
					return {v};
				} else {
					qval = rv.quantity_value; qunit = rv.quantity_unit; nval = getNumericValue(lv);
					if (op == "/" && qval == 0) return {};
					FPValue v; v.type = FPValue::Type::Quantity;
					if (op == "*") {
						v.quantity_value = qval * nval;
						v.quantity_unit = qunit;
					} else {
						v.quantity_value = nval / qval;
						v.quantity_unit = "1/" + stripQuantityUnitQuotes(qunit);
					}
					return {v};
				}
			}
		}

		if (!isNumericType(lv) || !isNumericType(rv)) {
			return {};
		}

		double l_num = getNumericValue(lv);
		double r_num = getNumericValue(rv);
		double result = 0;
		int mod_decimal_places = 0;
		auto decimalPlacesForArithmetic = [this](const FPValue &v) -> int {
			std::string s = v.source_text.empty() ? this->toString(v) : v.source_text;
			auto exp_pos = s.find_first_of("eE");
			if (exp_pos != std::string::npos) s = s.substr(0, exp_pos);
			auto dot = s.find('.');
			if (dot == std::string::npos) return 0;
			return static_cast<int>(s.size() - dot - 1);
		};
		auto decimalWithScaleText = [](double value, int decimal_places) -> FPValue {
			FPValue out = FPValue::FromDecimal(value);
			if (decimal_places > 0 && decimal_places < 16) {
				double scale = std::pow(10.0, decimal_places);
				double rounded = std::round(value * scale) / scale;
				out.decimal_val = rounded;
				std::ostringstream oss;
				oss << std::fixed << std::setprecision(decimal_places) << rounded;
				std::string text = oss.str();
				auto dot = text.find('.');
				if (dot != std::string::npos) {
					while (text.size() > dot + 2 && text.back() == '0') {
						text.pop_back();
					}
				}
				out.source_text = text;
			}
			return out;
		};

		if (op == "+") result = l_num + r_num;
		else if (op == "-") result = l_num - r_num;
		else if (op == "*") result = l_num * r_num;
		else if (op == "/") {
			if (r_num == 0) return {};
			result = l_num / r_num;
		} else if (op == "div") {
			if (r_num == 0) return {};
			result = std::trunc(l_num / r_num);
		} else if (op == "mod") {
			if (r_num == 0) return {};
			result = std::fmod(l_num, r_num);
			mod_decimal_places = std::max(decimalPlacesForArithmetic(lv), decimalPlacesForArithmetic(rv));
		}

		// Preserve integer type if both inputs are integer
		bool l_int = (effectiveType(lv) == FPValue::Type::Integer);
		bool r_int = (effectiveType(rv) == FPValue::Type::Integer);
		int decimal_result_places = 0;
		if (op == "+" || op == "-") {
			decimal_result_places = std::max(decimalPlacesForArithmetic(lv), decimalPlacesForArithmetic(rv));
		} else if (op == "*") {
			decimal_result_places = decimalPlacesForArithmetic(lv) + decimalPlacesForArithmetic(rv);
		}
		if (l_int && r_int && op != "/") {
			// FHIRPath Integer is 32-bit signed; promote to Decimal on overflow
			constexpr double INT32_MIN_D = -2147483648.0;
			constexpr double INT32_MAX_D = 2147483647.0;
			if (result < INT32_MIN_D || result > INT32_MAX_D) {
				return {FPValue::FromDecimal(result)};
			}
			return {FPValue::FromInteger(static_cast<int64_t>(result))};
		}
		if (op == "div" &&
		    result >= static_cast<double>(LLONG_MIN) &&
		    result <= static_cast<double>(LLONG_MAX)) {
			return {FPValue::FromInteger(static_cast<int64_t>(result))};
		}
		if (op == "mod") {
			return {decimalWithScaleText(result, mod_decimal_places)};
		}
		if (op == "+" || op == "-" || op == "*") {
			return {decimalWithScaleText(result, decimal_result_places)};
		}
		return {FPValue::FromDecimal(result)};
	}

	return {};
}

FPCollection Evaluator::evalUnaryOp(const ASTNode &node, const FPCollection &input, yyjson_doc *doc) {
	if (node.op == "-" && !node.children.empty() &&
	    node.children[0]->type == NodeType::IntegerLiteral &&
	    node_value_get<int64_t>(node.children[0]->value) == 2147483648LL) {
		return {FPValue::FromInteger(-2147483647LL - 1LL)};
	}
	auto operand = eval(*node.children[0], input, doc);
	if (operand.empty()) {
		return {};
	}
	if (operand.size() > 1) {
		throw FHIRPathSpecError("Unary " + node.op + " requires a single item input collection");
	}
	if (node.op == "-") {
		auto et = effectiveType(operand[0]);
		if (et == FPValue::Type::Integer) {
			double result = -getNumericValue(operand[0]);
			constexpr double INT32_MIN_D = -2147483648.0;
			constexpr double INT32_MAX_D = 2147483647.0;
			if (result < INT32_MIN_D || result > INT32_MAX_D) {
				return {FPValue::FromDecimal(result)};
			}
			return {FPValue::FromInteger(static_cast<int64_t>(result))};
		}
		if (et == FPValue::Type::Decimal) {
			auto result = FPValue::FromDecimal(-getNumericValue(operand[0]));
			if (operand[0].type == FPValue::Type::Decimal && !operand[0].source_text.empty()) {
				if (operand[0].source_text[0] == '-') {
					result.source_text = operand[0].source_text.substr(1);
				} else {
					result.source_text = "-" + operand[0].source_text;
				}
			}
			return {result};
		}
		if (et == FPValue::Type::Quantity) {
			FPValue v;
			v.type = FPValue::Type::Quantity;
			v.quantity_value = -operand[0].quantity_value;
			v.quantity_unit = operand[0].quantity_unit;
			return {v};
		}
		throw FHIRPathSpecError("Unary - applied to non-numeric type");
	}
	if (node.op == "+") {
		auto et = effectiveType(operand[0]);
		if (et != FPValue::Type::Integer && et != FPValue::Type::Decimal &&
		    et != FPValue::Type::Quantity) {
			throw FHIRPathSpecError("Unary + applied to non-numeric type");
		}
		return operand;
	}
	return {};
}

// --- Helpers ---

bool Evaluator::isTruthy(const FPCollection &collection) const {
	if (collection.empty()) {
		return false;
	}
	auto &val = collection[0];
	if (val.type == FPValue::Type::Boolean) {
		return val.bool_val;
	}
	if (val.type == FPValue::Type::JsonVal && val.json_val) {
		if (yyjson_is_bool(val.json_val)) {
			return yyjson_get_bool(val.json_val);
		}
		return true; // Non-null JSON value is truthy
	}
	return !collection.empty();
}

bool Evaluator::isCriteriaTrue(const FPCollection &collection, const std::string &function_name) const {
	if (collection.empty()) {
		return false;
	}
	if (collection.size() != 1) {
		throw FHIRPathSpecError(function_name + "() criteria must evaluate to a single Boolean value");
	}
	auto &val = collection[0];
	if (val.type == FPValue::Type::Boolean) {
		return val.bool_val;
	}
	if (val.type == FPValue::Type::JsonVal && val.json_val && yyjson_is_bool(val.json_val)) {
		return yyjson_get_bool(val.json_val);
	}
	throw FHIRPathSpecError(function_name + "() criteria must evaluate to a single Boolean value");
}

std::string Evaluator::toString(const FPValue &val) const {
	switch (val.type) {
	case FPValue::Type::String:
	case FPValue::Type::Date:
	case FPValue::Type::DateTime:
	case FPValue::Type::Time:
		return val.string_val;
	case FPValue::Type::Integer:
		return std::to_string(val.int_val);
	case FPValue::Type::Decimal: {
		// Use source_text for literal decimals to preserve exact input precision.
		// Otherwise use high-precision output (17 significant digits) to preserve
		// double precision for computed results, per CQL spec requirement of
		// at least 18 digits of precision for Decimal values.
		if (!val.source_text.empty()) {
			return val.source_text;
		}
		std::ostringstream oss;
		oss << std::setprecision(17) << val.decimal_val;
		std::string s = oss.str();
		// Ensure decimal always has a decimal point
		if (s.find('.') == std::string::npos && s.find('e') == std::string::npos && s.find('E') == std::string::npos) {
			s += ".0";
		}
		return s;
	}
	case FPValue::Type::Boolean:
		return val.bool_val ? "true" : "false";
	case FPValue::Type::Quantity: {
		std::ostringstream oss;
		std::string u = val.quantity_unit;
		static const char* keyword_units[] = {
			"year", "years", "month", "months", "week", "weeks", "day", "days",
			"hour", "hours", "minute", "minutes", "second", "seconds",
			"millisecond", "milliseconds", nullptr
		};
		bool is_keyword = false;
		for (int i = 0; keyword_units[i]; ++i) {
			if (u == keyword_units[i]) { is_keyword = true; break; }
		}
		// Format number: use source_text if available for precision-preserving output
		std::string num_str;
		if (!val.source_text.empty()) {
			num_str = val.source_text;
		} else if (val.quantity_value == std::floor(val.quantity_value) && std::abs(val.quantity_value) < 1e15) {
			oss << static_cast<int64_t>(val.quantity_value);
			num_str = oss.str();
		} else {
			oss << val.quantity_value;
			num_str = oss.str();
		}
		if (is_keyword) {
			return num_str + " " + u;
		}
		return num_str + " '" + u + "'";
	}
	case FPValue::Type::Null:
		return "";
	case FPValue::Type::JsonVal:
		return jsonValToString(val.json_val);
	default:
		return "";
	}
}

double Evaluator::toNumber(const FPValue &val) const {
	switch (val.type) {
	case FPValue::Type::Integer:
		return static_cast<double>(val.int_val);
	case FPValue::Type::Decimal:
		return val.decimal_val;
	case FPValue::Type::Quantity:
		return val.quantity_value;
	case FPValue::Type::Boolean:
		return val.bool_val ? 1.0 : 0.0;
	case FPValue::Type::String:
		try {
			return std::stod(val.string_val);
		} catch (const std::exception &) {
			return 0.0;
		}
	case FPValue::Type::JsonVal:
		if (val.json_val) {
			if (yyjson_is_int(val.json_val)) {
				return static_cast<double>(yyjson_get_sint(val.json_val));
			}
			if (yyjson_is_real(val.json_val)) {
				return yyjson_get_real(val.json_val);
			}
			if (yyjson_is_num(val.json_val)) {
				return yyjson_get_num(val.json_val);
			}
			if (yyjson_is_bool(val.json_val)) {
				return yyjson_get_bool(val.json_val) ? 1.0 : 0.0;
			}
			if (yyjson_is_str(val.json_val)) {
				try {
					return std::stod(yyjson_get_str(val.json_val));
				} catch (const std::exception &) {
					return 0.0;
				}
			}
		}
		return 0.0;
	default:
		return 0.0;
	}
}

bool Evaluator::toBoolean(const FPValue &val) const {
	switch (val.type) {
	case FPValue::Type::Boolean:
		return val.bool_val;
	case FPValue::Type::Integer:
		// FHIRPath §6.4: only 0 and 1 convert to boolean
		if (val.int_val == 0) return false;
		if (val.int_val == 1) return true;
		throw FHIRPathSpecError("Cannot convert integer " + std::to_string(val.int_val) + " to boolean (only 0 and 1 are valid)");
	case FPValue::Type::String: {
		std::string lower;
		for (auto c : val.string_val) lower += static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
		if (lower == "true" || lower == "t" || lower == "yes" || lower == "y" || lower == "1") {
			return true;
		}
		if (lower == "false" || lower == "f" || lower == "no" || lower == "n" || lower == "0") {
			return false;
		}
		throw FHIRPathSpecError("Cannot convert string '" + val.string_val + "' to boolean");
	}
	case FPValue::Type::JsonVal:
		if (val.json_val) {
			if (yyjson_is_bool(val.json_val)) {
				return yyjson_get_bool(val.json_val);
			}
			if (yyjson_is_str(val.json_val)) {
				std::string s = yyjson_get_str(val.json_val);
				std::string lower;
				for (auto c : s) lower += static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
				if (lower == "true" || lower == "t" || lower == "yes" || lower == "y" || lower == "1") return true;
				if (lower == "false" || lower == "f" || lower == "no" || lower == "n" || lower == "0") return false;
				throw FHIRPathSpecError("Cannot convert string '" + s + "' to boolean");
			}
			if (yyjson_is_int(val.json_val)) {
				int64_t v = yyjson_get_sint(val.json_val);
				if (v == 0) return false;
				if (v == 1) return true;
				throw FHIRPathSpecError("Cannot convert integer to boolean (only 0 and 1 are valid)");
			}
		}
		throw FHIRPathSpecError("Cannot convert value to boolean");
	default:
		throw FHIRPathSpecError("Cannot convert value to boolean");
	}
}

std::string Evaluator::jsonValToString(yyjson_val *val) const {
	if (!val) {
		return "";
	}
	if (yyjson_is_str(val)) {
		return std::string(yyjson_get_str(val));
	}
	if (yyjson_is_int(val)) {
		return std::to_string(yyjson_get_sint(val));
	}
	if (yyjson_is_real(val)) {
		std::ostringstream oss;
		oss << yyjson_get_real(val);
		return oss.str();
	}
	if (yyjson_is_bool(val)) {
		return yyjson_get_bool(val) ? "true" : "false";
	}
	if (yyjson_is_null(val)) {
		return "";
	}
	// For objects and arrays, serialize to JSON string
	char *json = yyjson_val_write(val, 0, nullptr);
	if (json) {
		std::string result(json);
		free(json);
		return result;
	}
	return "";
}

FPCollection Evaluator::jsonValToCollection(yyjson_val *val) const {
	if (!val) {
		return {};
	}
	if (yyjson_is_arr(val)) {
		FPCollection result;
		size_t idx2, max2;
		yyjson_val *elem;
		yyjson_arr_foreach(val, idx2, max2, elem) {
			result.push_back(FPValue::FromJson(elem));
		}
		return result;
	}
	return {FPValue::FromJson(val)};
}

// --- Phase 3: convertsTo* functions ---

FPCollection Evaluator::fn_convertsToBoolean(const FPCollection &input) {
	if (input.empty() || input.size() != 1) return {};
	auto &val = input[0];
	auto t = effectiveType(val);
	if (t == FPValue::Type::Boolean) return {FPValue::FromBoolean(true)};
	if (t == FPValue::Type::Integer) {
		int64_t iv = (val.type == FPValue::Type::Integer) ? val.int_val :
		             static_cast<int64_t>(getNumericValue(val));
		return {FPValue::FromBoolean(iv == 0 || iv == 1)};
	}
	if (t == FPValue::Type::Decimal) {
		double dv = getNumericValue(val);
		return {FPValue::FromBoolean(dv == 0.0 || dv == 1.0)};
	}
	if (t == FPValue::Type::String) {
		std::string s = toString(val);
		// Convert to lowercase for comparison
		std::string lower;
		for (auto c : s) lower += static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
		if (lower == "true" || lower == "false" || lower == "1" || lower == "0" ||
		    lower == "t" || lower == "f" || lower == "yes" || lower == "no" ||
		    lower == "y" || lower == "n" || lower == "1.0" || lower == "0.0") {
			return {FPValue::FromBoolean(true)};
		}
		return {FPValue::FromBoolean(false)};
	}
	return {FPValue::FromBoolean(false)};
}

FPCollection Evaluator::fn_convertsToInteger(const FPCollection &input) {
	if (input.empty() || input.size() != 1) return {};
	auto &val = input[0];
	auto t = effectiveType(val);
	// FHIRPath spec: Integer is 32-bit signed (-2^31 to 2^31-1)
	constexpr int64_t INT32_MIN_VAL = -2147483648LL;
	constexpr int64_t INT32_MAX_VAL = 2147483647LL;
	if (t == FPValue::Type::Integer) {
		int64_t iv = (val.type == FPValue::Type::Integer) ? val.int_val :
		             static_cast<int64_t>(getNumericValue(val));
		return {FPValue::FromBoolean(iv >= INT32_MIN_VAL && iv <= INT32_MAX_VAL)};
	}
	if (t == FPValue::Type::Boolean) return {FPValue::FromBoolean(true)};
	if (t == FPValue::Type::String) {
		std::string s = toString(val);
		if (!isFHIRPathIntegerString(s)) {
			return {FPValue::FromBoolean(false)};
		}
		try {
			size_t pos;
			long long result = std::stoll(s, &pos);
			if (pos == s.size() && result >= INT32_MIN_VAL && result <= INT32_MAX_VAL) {
				return {FPValue::FromBoolean(true)};
			}
		} catch (const std::exception &) {}
		return {FPValue::FromBoolean(false)};
	}
	return {FPValue::FromBoolean(false)};
}

FPCollection Evaluator::fn_convertsToDecimal(const FPCollection &input) {
	if (input.empty() || input.size() != 1) return {};
	auto &val = input[0];
	auto t = effectiveType(val);
	if (t == FPValue::Type::Decimal || t == FPValue::Type::Integer) return {FPValue::FromBoolean(true)};
	if (t == FPValue::Type::Boolean) return {FPValue::FromBoolean(true)};
	if (t == FPValue::Type::String) {
		std::string s = toString(val);
		if (!isFHIRPathDecimalString(s)) return {FPValue::FromBoolean(false)};
		try {
			size_t pos;
			double d = std::stod(s, &pos);
			if (pos == s.size() && !std::isnan(d) && !std::isinf(d)) return {FPValue::FromBoolean(true)};
		} catch (const std::exception &) {}
		return {FPValue::FromBoolean(false)};
	}
	return {FPValue::FromBoolean(false)};
}

FPCollection Evaluator::fn_convertsToString(const FPCollection &input) {
	if (input.empty() || input.size() != 1) return {};
	// Everything can be converted to string
	auto t = effectiveType(input[0]);
	if (t == FPValue::Type::String || t == FPValue::Type::Boolean ||
	    t == FPValue::Type::Integer || t == FPValue::Type::Decimal ||
	    t == FPValue::Type::Date || t == FPValue::Type::DateTime ||
	    t == FPValue::Type::Time || t == FPValue::Type::Quantity) {
		return {FPValue::FromBoolean(true)};
	}
	FPValue quantity_value;
	if (fpValueAsQuantity(input[0], quantity_value)) {
		return {FPValue::FromBoolean(true)};
	}
	// JSON primitive values
	if (input[0].type == FPValue::Type::JsonVal && input[0].json_val) {
		if (yyjson_is_str(input[0].json_val) || yyjson_is_bool(input[0].json_val) ||
		    yyjson_is_num(input[0].json_val)) {
			return {FPValue::FromBoolean(true)};
		}
	}
	return {FPValue::FromBoolean(false)};
}

FPCollection Evaluator::fn_convertsToDate(const FPCollection &input) {
	if (input.empty() || input.size() != 1) return {};
	auto &val = input[0];
	auto t = effectiveType(val);
	if (t == FPValue::Type::Date) return {FPValue::FromBoolean(true)};
	if (t == FPValue::Type::DateTime) return {FPValue::FromBoolean(true)};
	if (t == FPValue::Type::String) {
		std::string s = toString(val);
		// Check if it looks like a date or datetime (any precision with valid date part)
		if (s.size() >= 4 && std::isdigit(static_cast<unsigned char>(s[0]))) {
			DateTimeParts p = parseDateTimeParts(s);
			// Date or DateTime strings are convertible to Date (date portion extracted)
			if (p.valid && p.precision >= 1) return {FPValue::FromBoolean(true)};
		}
		return {FPValue::FromBoolean(false)};
	}
	return {FPValue::FromBoolean(false)};
}

FPCollection Evaluator::fn_convertsToDateTime(const FPCollection &input) {
	if (input.empty() || input.size() != 1) return {};
	auto &val = input[0];
	auto t = effectiveType(val);
	if (t == FPValue::Type::DateTime) return {FPValue::FromBoolean(true)};
	if (t == FPValue::Type::Date) return {FPValue::FromBoolean(true)};
	if (t == FPValue::Type::String) {
		std::string s = toString(val);
		if (s.size() >= 4 && std::isdigit(static_cast<unsigned char>(s[0]))) {
			DateTimeParts p = parseDateTimeParts(s);
			if (p.valid) return {FPValue::FromBoolean(true)};
		}
		return {FPValue::FromBoolean(false)};
	}
	return {FPValue::FromBoolean(false)};
}

FPCollection Evaluator::fn_convertsToTime(const FPCollection &input) {
	if (input.empty() || input.size() != 1) return {};
	auto &val = input[0];
	auto t = effectiveType(val);
	if (t == FPValue::Type::Time) return {FPValue::FromBoolean(true)};
	if (t == FPValue::Type::String) {
		std::string s = toString(val);
		if (s.size() >= 2 && (s[0] == 'T' || std::isdigit(static_cast<unsigned char>(s[0])))) {
			DateTimeParts p = parseTimeParts(s);
			if (!p.valid) return {FPValue::FromBoolean(false)};
			// Validate ranges
			if (p.hour < 0 || p.hour > 23) return {FPValue::FromBoolean(false)};
			if (p.precision >= 5 && p.minute > 59) return {FPValue::FromBoolean(false)};
			if (p.precision >= 6 && p.second > 59) return {FPValue::FromBoolean(false)};
			// Reject timezone suffixes
			size_t check_pos = (s[0] == 'T') ? 1 : 0;
			if (check_pos + 2 <= s.size()) check_pos += 2;
			if (check_pos < s.size() && s[check_pos] == ':') { check_pos++; if (check_pos + 2 <= s.size()) check_pos += 2; }
			if (check_pos < s.size() && s[check_pos] == ':') { check_pos++; if (check_pos + 2 <= s.size()) check_pos += 2; }
			if (check_pos < s.size() && s[check_pos] == '.') { check_pos++; while (check_pos < s.size() && std::isdigit((unsigned char)s[check_pos])) check_pos++; }
			if (check_pos < s.size()) return {FPValue::FromBoolean(false)};
			return {FPValue::FromBoolean(true)};
		}
		return {FPValue::FromBoolean(false)};
	}
	return {FPValue::FromBoolean(false)};
}

FPCollection Evaluator::fn_convertsToQuantity(const FPCollection &input, const std::string &to_unit) {
	if (input.empty() || input.size() != 1) return {};
	auto &val = input[0];
	auto t = effectiveType(val);
	if (isQuantityLike(val) || t == FPValue::Type::Quantity || t == FPValue::Type::Integer ||
	    t == FPValue::Type::Decimal || t == FPValue::Type::Boolean) {
		return {FPValue::FromBoolean(!fn_toQuantity(input, to_unit).empty())};
	}
	if (t == FPValue::Type::String) {
		return {FPValue::FromBoolean(!fn_toQuantity(input, to_unit).empty())};
	}
	return {FPValue::FromBoolean(false)};
}

// --- Phase 4: is()/as() type operations ---

FPCollection Evaluator::fn_isType(const FPCollection &input, const std::string &type_name, bool exact) {
	// Parse namespace from qualified type name (e.g., "FHIR.boolean", "System.Boolean")
	std::string ns, target;
	auto dot_pos = type_name.find('.');
	bool explicit_namespace = dot_pos != std::string::npos;
	if (dot_pos != std::string::npos) {
		ns = type_name.substr(0, dot_pos);
		target = type_name.substr(dot_pos + 1);
		if (target.size() >= 2 && target.front() == '`' && target.back() == '`') {
			target = target.substr(1, target.size() - 2);
		}
	} else {
		target = type_name;
		if (target.size() >= 2 && target.front() == '`' && target.back() == '`') {
			target = target.substr(1, target.size() - 2);
		}
		// Determine namespace for unqualified type names
		if (isDistinctSystemTypeName(target)) {
			ns = "System";
		} else if (!target.empty() && std::islower(static_cast<unsigned char>(target[0]))) {
			ns = "FHIR";
		} else if (isKnownFHIRType(target) || isKnownSystemType(target)) {
			ns = "FHIR";
		}
	}
	if (!isKnownTypeSpecifier(ns, target)) {
		throw FHIRPathSpecError("Unknown type: " + type_name);
	}
	if (input.empty()) return {};
	if (input.size() > 1) {
		throw FHIRPathSpecError("is() requires a singleton input collection");
	}
	auto &val = input[0];

	if (target == "Any") {
		return {FPValue::FromBoolean(true)};
	}

	auto t = effectiveType(val);
	bool is_fhir = (val.type == FPValue::Type::JsonVal);

	// Check fhir_type from choice type resolution first
	if (!val.fhir_type.empty()) {
		if (ns == "FHIR" || !explicit_namespace) {
			// Case-insensitive compare (fhir_type is capitalized suffix like "Integer", target may be "integer")
			std::string ft_lower = val.fhir_type;
			std::string tg_lower = target;
			for (auto &c : ft_lower) c = std::tolower(static_cast<unsigned char>(c));
			for (auto &c : tg_lower) c = std::tolower(static_cast<unsigned char>(c));
			if (ft_lower == tg_lower) return {FPValue::FromBoolean(true)};
			if (!exact) {
				if (fhirTypeIsA(val.fhir_type, target) || fhirTypeIsA(ft_lower, tg_lower)) {
					return {FPValue::FromBoolean(true)};
				}
			}
		}
	}

	// System type checks — effectiveType resolves JSON primitives to their System type
	// FHIR-typed values (from JSON fields) should NOT match System types
	if (ns == "System") {
		if (is_fhir) return {FPValue::FromBoolean(false)};
		if (target == "Boolean") return {FPValue::FromBoolean(t == FPValue::Type::Boolean)};
		if (target == "Integer") return {FPValue::FromBoolean(t == FPValue::Type::Integer)};
		if (target == "Decimal") return {FPValue::FromBoolean(t == FPValue::Type::Decimal)};
		if (target == "String") return {FPValue::FromBoolean(t == FPValue::Type::String)};
		if (target == "Date") return {FPValue::FromBoolean(t == FPValue::Type::Date)};
		if (target == "DateTime") return {FPValue::FromBoolean(t == FPValue::Type::DateTime)};
		if (target == "Time") return {FPValue::FromBoolean(t == FPValue::Type::Time)};
		if (target == "Quantity") return {FPValue::FromBoolean(t == FPValue::Type::Quantity)};
		return {FPValue::FromBoolean(false)};
	}

	// FHIR type checks
	if (ns == "FHIR") {
			if (val.type == FPValue::Type::JsonVal && val.json_val && yyjson_is_obj(val.json_val)) {
				const char *inferred_type = nullptr;
				if (val.field_name == "name") inferred_type = "HumanName";
				else if (val.field_name == "address") inferred_type = "Address";
				else if (val.field_name == "identifier") inferred_type = "Identifier";
				else if (val.field_name == "telecom") inferred_type = "ContactPoint";
				else if (val.field_name == "coding") inferred_type = "Coding";
				else if (val.field_name == "code") inferred_type = "CodeableConcept";
				else if (yyjson_obj_get(val.json_val, "reference")) inferred_type = "Reference";
				else if (yyjson_obj_get(val.json_val, "contentType")) inferred_type = "Attachment";
				else if (!val.field_name.empty()) inferred_type = "BackboneElement";
				if (inferred_type) {
					if (target == inferred_type) return {FPValue::FromBoolean(true)};
				if (!exact && fhirTypeIsA(inferred_type, target)) return {FPValue::FromBoolean(true)};
			}
		}
		// FHIR resource types - check resourceType
		if (val.type == FPValue::Type::JsonVal && val.json_val && yyjson_is_obj(val.json_val)) {
			yyjson_val *rt = yyjson_obj_get(val.json_val, "resourceType");
			if (rt && yyjson_is_str(rt)) {
				std::string actual_type = yyjson_get_str(rt);
				if (actual_type == target) return {FPValue::FromBoolean(true)};
				if (!exact && fhirTypeIsA(actual_type, target)) return {FPValue::FromBoolean(true)};
			}

			// FHIR complex types must rely on fhir_type metadata.
			// Heuristic structural detection has been removed to prevent schema coupling
			// and false positives on generic JSON objects.
		}
		// FHIR primitive types from JSON values
		if (is_fhir) {
			if (target == "boolean") return {FPValue::FromBoolean(t == FPValue::Type::Boolean)};
			if (target == "integer" || target == "positiveInt" || target == "unsignedInt")
				return {FPValue::FromBoolean(t == FPValue::Type::Integer)};
			if (target == "decimal") return {FPValue::FromBoolean(t == FPValue::Type::Decimal)};
			// FHIR string type hierarchy
			if (t == FPValue::Type::String) {
				const char *actual_type = fhirFieldType(val.field_name);
				if (target == "string") {
					if (exact) {
						// Exact (as/ofType): only match if the actual field type IS string
						// Subtypes like code, id, uri should NOT match
						if (actual_type && std::string(actual_type) == "string") return {FPValue::FromBoolean(true)};
						if (!actual_type) return {FPValue::FromBoolean(true)}; // No field info, assume string
						return {FPValue::FromBoolean(false)};
					}
					// Non-exact (is()): string is the parent type - matches all string subtypes
					return {FPValue::FromBoolean(true)};
				}
				// Specific subtype checks: code, id, uri, url, etc.
				if (target == "code" || target == "id" || target == "uri" || target == "url" ||
				    target == "canonical" || target == "uuid" || target == "oid" ||
				    target == "markdown" || target == "xhtml") {
					if (actual_type && target == actual_type) return {FPValue::FromBoolean(true)};
					return {FPValue::FromBoolean(false)};
				}
			}
			if (target == "date") {
				if (t == FPValue::Type::Date) return {FPValue::FromBoolean(true)};
				// FHIR date fields arrive as JSON strings — check field metadata
				if (t == FPValue::Type::String) {
					const char *actual_type = fhirFieldType(val.field_name);
					if (actual_type && std::string(actual_type) == "date") return {FPValue::FromBoolean(true)};
					// Also check if the string looks like a date and has no field name
					if (!actual_type && isDateTimeType(val)) {
						std::string s;
						if (val.type == FPValue::Type::JsonVal && val.json_val && yyjson_is_str(val.json_val))
							s = yyjson_get_str(val.json_val);
						else if (val.type == FPValue::Type::String)
							s = val.string_val;
						// Date (not dateTime): YYYY, YYYY-MM, or YYYY-MM-DD (no T)
						if (!s.empty() && s.find('T') == std::string::npos) return {FPValue::FromBoolean(true)};
					}
				}
				return {FPValue::FromBoolean(false)};
			}
			if (target == "dateTime" || target == "instant") {
				if (t == FPValue::Type::DateTime) return {FPValue::FromBoolean(true)};
				// FHIR dateTime fields arrive as JSON strings — check field metadata
				if (t == FPValue::Type::String) {
					const char *actual_type = fhirFieldType(val.field_name);
					if (actual_type && (std::string(actual_type) == "dateTime" || std::string(actual_type) == "instant"))
						return {FPValue::FromBoolean(true)};
					// String with 'T' is a dateTime
					if (!actual_type && isDateTimeType(val)) {
						std::string s;
						if (val.type == FPValue::Type::JsonVal && val.json_val && yyjson_is_str(val.json_val))
							s = yyjson_get_str(val.json_val);
						else if (val.type == FPValue::Type::String)
							s = val.string_val;
						if (!s.empty() && s.find('T') != std::string::npos) return {FPValue::FromBoolean(true)};
					}
				}
				return {FPValue::FromBoolean(false)};
			}
			if (target == "time") return {FPValue::FromBoolean(t == FPValue::Type::Time)};
		}
		// System literals that map to FHIR types
		if (!is_fhir) {
			if (target == "Quantity" || target == "Age" || target == "Duration") {
				return {FPValue::FromBoolean(t == FPValue::Type::Quantity)};
			}
		}
		return {FPValue::FromBoolean(false)};
	}

	return {FPValue::FromBoolean(false)};
}

FPCollection Evaluator::fn_asType(const FPCollection &input, const std::string &type_name) {
	std::string ns, target;
	auto dot_pos = type_name.find('.');
	if (dot_pos != std::string::npos) {
		ns = type_name.substr(0, dot_pos);
		target = type_name.substr(dot_pos + 1);
		if (target.size() >= 2 && target.front() == '`' && target.back() == '`') {
			target = target.substr(1, target.size() - 2);
		}
	} else {
		target = type_name;
		if (target.size() >= 2 && target.front() == '`' && target.back() == '`') {
			target = target.substr(1, target.size() - 2);
		}
		if (isDistinctSystemTypeName(target)) {
			ns = "System";
		} else if (!target.empty() && std::islower(static_cast<unsigned char>(target[0]))) {
			ns = "FHIR";
		} else if (isKnownFHIRType(target) || isKnownSystemType(target)) {
			ns = "FHIR";
		}
	}
	if (!isKnownTypeSpecifier(ns, target)) {
		throw FHIRPathSpecError("Unknown type: " + type_name);
	}
	if (input.empty()) return {};
	if (input.size() > 1) {
		throw FHIRPathSpecError("as() requires a singleton input collection");
	}

	bool exact = false;
	if (input[0].type != FPValue::Type::JsonVal) {
		exact = true;
	} else if (ns == "System" || isFHIRPrimitiveTypeName(target)) {
		exact = true;
	} else {
		auto t = effectiveType(input[0]);
		exact = (t != FPValue::Type::JsonVal);
	}

	auto is_result = fn_isType(input, type_name, exact);
	if (!is_result.empty() && is_result[0].type == FPValue::Type::Boolean && is_result[0].bool_val) {
		return input;
	}
	return {};
}

// --- Phase 5: split() ---

FPCollection Evaluator::fn_split(const FPCollection &input, const FPCollection &delimiter) {
	if (input.empty() || delimiter.empty()) return {};
	std::string s = toString(input[0]);
	std::string delim = toString(delimiter[0]);
	FPCollection result;
	if (delim.empty()) {
		// Split into individual characters
		for (size_t i = 0; i < s.size(); i++) {
			result.push_back(FPValue::FromString(std::string(1, s[i])));
		}
		return result;
	}
	size_t pos = 0;
	while (true) {
		size_t found = s.find(delim, pos);
		if (found == std::string::npos) {
			result.push_back(FPValue::FromString(s.substr(pos)));
			break;
		}
		result.push_back(FPValue::FromString(s.substr(pos, found - pos)));
		pos = found + delim.size();
	}
	return result;
}

// --- Phase 5: toTime() ---

FPCollection Evaluator::fn_toTime(const FPCollection &input) {
	if (input.empty()) return {};
	auto &val = input[0];
	if (val.type == FPValue::Type::Time) return {val};
	auto t = effectiveType(val);
	// Only strings (and time, already handled) can be converted to time.
	// Integers, decimals, booleans, objects, arrays are not valid inputs.
	if (t != FPValue::Type::String) return {};
	std::string s = toString(val);
	// Validate the time string using parseTimeParts.
	// parseTimeParts accepts HH, HH:MM, HH:MM:SS, HH:MM:SS.sss with optional T prefix.
	// Reject timezone suffixes (FHIRPath time type does not include timezone).
	DateTimeParts p = parseTimeParts(s);
	if (!p.valid) return {};
	// Validate hour/minute/second ranges (parseTimeParts parses but doesn't validate ranges)
	if (p.hour < 0 || p.hour > 23) return {};
	if (p.precision >= 5 && (p.minute < 0 || p.minute > 59)) return {};
	if (p.precision >= 6 && (p.second < 0 || p.second > 59)) return {};
	// Reject timezone suffixes: if the string has '+' or 'Z' after the time part, reject
	size_t check_pos = (s[0] == 'T') ? 1 : 0;
	// Skip past HH:MM:SS.sss
	if (check_pos + 2 <= s.size()) check_pos += 2; // HH
	if (check_pos < s.size() && s[check_pos] == ':') { check_pos++; if (check_pos + 2 <= s.size()) check_pos += 2; } // :MM
	if (check_pos < s.size() && s[check_pos] == ':') { check_pos++; if (check_pos + 2 <= s.size()) check_pos += 2; } // :SS
	if (check_pos < s.size() && s[check_pos] == '.') { check_pos++; while (check_pos < s.size() && std::isdigit((unsigned char)s[check_pos])) check_pos++; } // .sss
	// If there's anything left (timezone), reject
	if (check_pos < s.size()) return {};
	FPValue v;
	v.type = FPValue::Type::Time;
	v.string_val = normalizeTimeLiteralString(s);
	return {v};
}

// --- Phase 6: Boundary functions ---

static int countDecimalPlaces(const FPValue &val) {
	// Use source_text if available (preserves trailing zeros like "12.500")
	std::string s = val.source_text.empty() ? "" : val.source_text;
	if (s.empty()) {
		// Fall back to toString
		if (val.type == FPValue::Type::Decimal) {
			std::ostringstream oss;
			oss << val.decimal_val;
			s = oss.str();
		} else if (val.type == FPValue::Type::Integer) {
			return 0;
		}
	}
	auto dot = s.find('.');
	if (dot == std::string::npos) return 0;
	return static_cast<int>(s.size() - dot - 1);
}

static int countDigits(const std::string &s) {
	int count = 0;
	for (size_t i = 0; i < s.size(); i++) {
		if (s[i] >= '0' && s[i] <= '9') count++;
	}
	return count;
}

static FPCollection decimalBoundary(const FPValue &val, const FPCollection *precision_arg, bool is_high) {
	int out_prec = 8;
	if (precision_arg && !precision_arg->empty()) {
		out_prec = static_cast<int>((*precision_arg)[0].type == FPValue::Type::Integer ?
		    (*precision_arg)[0].int_val : static_cast<int64_t>((*precision_arg)[0].decimal_val));
	}
	if (out_prec < 0 || out_prec > 28) return {};

	double d;
	if (val.type == FPValue::Type::Integer) {
		d = static_cast<double>(val.int_val);
	} else if (val.type == FPValue::Type::Decimal) {
		d = val.decimal_val;
	} else {
		d = getNumericValue(val);
	}
	int decimal_places = countDecimalPlaces(val);
	double half_unit = 0.5 * std::pow(10.0, -decimal_places);

	double boundary = is_high ? (d + half_unit) : (d - half_unit);

	// Special case near zero
	double out_half = 0.5 * std::pow(10.0, -(out_prec > 0 ? out_prec : 0));
	if (is_high && boundary > 0 && boundary <= out_half) {
		return {FPValue::FromDecimal(0.0)};
	}
	if (is_high && boundary < 0 && std::abs(boundary) <= out_half) {
		return {FPValue::FromDecimal(0.0)};
	}
	if (!is_high && boundary < 0 && std::abs(boundary) <= out_half) {
		return {FPValue::FromDecimal(-0.0)};
	}
	if (!is_high && boundary > 0 && boundary <= out_half) {
		return {FPValue::FromDecimal(0.0)};
	}

	double factor = std::pow(10.0, out_prec);
	double result;
	if (is_high) {
		result = std::ceil(boundary * factor) / factor;
	} else {
		result = std::floor(boundary * factor) / factor;
	}
	FPValue rv = FPValue::FromDecimal(result);
	// Store source_text with padded precision for proper formatting
	if (out_prec > 0) {
		std::ostringstream pad_oss;
		pad_oss << std::fixed << std::setprecision(out_prec) << result;
		rv.source_text = pad_oss.str();
	}
	return {rv};
}

static std::string formatDateTimeBoundary(const DateTimeParts &p, int digit_prec, bool is_high,
                                           const std::string &orig_tz, bool is_time) {
	std::ostringstream oss;
	if (is_time) oss << "T";

	if (!is_time) {
		oss << std::setfill('0') << std::setw(4) << p.year;
		if (digit_prec <= 4) return oss.str();
		oss << "-" << std::setfill('0') << std::setw(2)
		    << ((p.precision >= 2) ? p.month : (is_high ? 12 : 1));
		if (digit_prec <= 6) return oss.str();
		int use_month = (p.precision >= 2) ? p.month : (is_high ? 12 : 1);
		int days_in_month[] = {31,28,31,30,31,30,31,31,30,31,30,31};
		bool leap = (p.year % 4 == 0 && (p.year % 100 != 0 || p.year % 400 == 0));
		if (leap) days_in_month[1] = 29;
		int max_day = (use_month >= 1 && use_month <= 12) ? days_in_month[use_month - 1] : 31;
		oss << "-" << std::setfill('0') << std::setw(2)
		    << ((p.precision >= 3) ? p.day : (is_high ? max_day : 1));
		if (digit_prec <= 8) return oss.str();
		oss << "T";
	}

	oss << std::setfill('0') << std::setw(2)
	    << ((p.precision >= 4) ? p.hour : (is_high ? (is_time ? p.hour : 23) : 0));
	if (digit_prec <= (is_time ? 2 : 10)) return oss.str();
	oss << ":" << std::setfill('0') << std::setw(2)
	    << ((p.precision >= 5) ? p.minute : (is_high ? 59 : 0));
	if (digit_prec <= (is_time ? 4 : 12)) return oss.str();
	oss << ":" << std::setfill('0') << std::setw(2)
	    << (is_high ? 59 : 0);
	if (digit_prec <= (is_time ? 6 : 14)) return oss.str();
	oss << "." << std::setfill('0') << std::setw(3)
	    << (is_high ? 999 : 0);

	// Add timezone for high precision
	if (!is_time) {
		if (!orig_tz.empty()) {
			oss << orig_tz;
		} else {
			// For unknown timezone: high gets min offset (-12:00), low gets max offset (+14:00)
			oss << (is_high ? "-12:00" : "+14:00");
		}
	}
	return oss.str();
}

FPCollection Evaluator::fn_lowBoundary(const FPCollection &input, const FPCollection *precision_arg) {
	if (input.empty()) return {};
	auto &val = input[0];
	auto t = effectiveType(val);

	// Detect date/dateTime strings from JSON
	if (t == FPValue::Type::String) {
		std::string s = toString(val);
		std::string fhir_type = val.fhir_type;
		std::transform(fhir_type.begin(), fhir_type.end(), fhir_type.begin(), [](unsigned char c) {
			return static_cast<char>(std::tolower(c));
		});
		const char *field_type = fhirFieldType(val.field_name);
		bool is_time_typed = fhir_type == "time" || (field_type && std::string(field_type) == "time");
		DateTimeParts time_parts = parseTimeParts(s);
		if (time_parts.valid && (is_time_typed || (s.find(':') != std::string::npos && s.find('-') == std::string::npos))) {
			FPValue time_val;
			time_val.type = FPValue::Type::Time;
			time_val.string_val = normalizeTimeLiteralString(s);
			FPCollection single = {time_val};
			return fn_lowBoundary(single, precision_arg);
		}
		if (s.size() >= 4 && std::isdigit((unsigned char)s[0]) && std::isdigit((unsigned char)s[1]) &&
		    std::isdigit((unsigned char)s[2]) && std::isdigit((unsigned char)s[3])) {
			FPValue date_val;
			bool is_datetime_typed = fhir_type == "datetime" || fhir_type == "instant" ||
			                         (field_type && (std::string(field_type) == "dateTime" ||
			                                         std::string(field_type) == "instant"));
			if (s.find('T') != std::string::npos || is_datetime_typed) {
				date_val.type = FPValue::Type::DateTime;
			} else {
				date_val.type = FPValue::Type::Date;
			}
			date_val.string_val = s;
			FPCollection single = {date_val};
			return fn_lowBoundary(single, precision_arg);
		}
	}

	if (t == FPValue::Type::Integer || t == FPValue::Type::Decimal) {
		return decimalBoundary(val, precision_arg, false);
	}
	if (t == FPValue::Type::Quantity) {
		FPValue dec_val = FPValue::FromDecimal(val.quantity_value);
		dec_val.source_text = val.source_text;
		auto result = decimalBoundary(dec_val, precision_arg, false);
		if (result.empty()) return {};
		FPValue qv;
		qv.type = FPValue::Type::Quantity;
		qv.quantity_value = result[0].decimal_val;
		qv.quantity_unit = val.quantity_unit;
		qv.source_text = result[0].source_text;
		return {qv};
	}
	// Get target digit precision
	int digit_prec = -1;
	if (precision_arg && !precision_arg->empty()) {
		digit_prec = static_cast<int>(toNumber((*precision_arg)[0]));
	}

	if (t == FPValue::Type::Date || t == FPValue::Type::DateTime) {
		std::string s = toString(val);
		DateTimeParts p = parseDateTimeParts(s);
		if (!p.valid) return {};
		// Extract original timezone
		std::string tz;
		auto tz_pos = s.find_last_of("+-Z");
		if (tz_pos != std::string::npos && tz_pos > 10) tz = s.substr(tz_pos);

		if (digit_prec > 0) {
			std::string result = formatDateTimeBoundary(p, digit_prec, false, tz, false);
			FPValue v;
			v.type = (digit_prec <= 8) ? FPValue::Type::Date : FPValue::Type::DateTime;
			v.string_val = result;
			return {v};
		}
		if (t == FPValue::Type::Date) {
			FPValue v;
			v.type = FPValue::Type::Date;
			v.string_val = formatDateTimeBoundary(p, 8, false, "", false);
			return {v};
		}
		// Default behavior (no precision arg) - return at maximum precision (DateTime)
		FPValue v;
		v.type = FPValue::Type::DateTime;
		v.string_val = formatDateTimeBoundary(p, 17, false, tz, false);
		return {v};
	}
	if (t == FPValue::Type::Time) {
		std::string s = toString(val);
		DateTimeParts p = parseTimeParts(s);
		if (!p.valid) return {};
		if (digit_prec > 0) {
			std::string result = formatDateTimeBoundary(p, digit_prec, false, "", true);
			FPValue v; v.type = FPValue::Type::Time; v.string_val = result; return {v};
		}
		std::ostringstream oss;
		oss << std::setfill('0') << std::setw(2) << p.hour
		    << ":" << std::setfill('0') << std::setw(2) << (p.precision >= 5 ? p.minute : 0)
		    << ":00.000";
		FPValue v; v.type = FPValue::Type::Time; v.string_val = oss.str(); return {v};
	}
	return {};
}

FPCollection Evaluator::fn_highBoundary(const FPCollection &input, const FPCollection *precision_arg) {
	if (input.empty()) return {};
	auto &val = input[0];
	auto t = effectiveType(val);

	// Detect date/dateTime strings from JSON
	if (t == FPValue::Type::String) {
		std::string s = toString(val);
		std::string fhir_type = val.fhir_type;
		std::transform(fhir_type.begin(), fhir_type.end(), fhir_type.begin(), [](unsigned char c) {
			return static_cast<char>(std::tolower(c));
		});
		const char *field_type = fhirFieldType(val.field_name);
		bool is_time_typed = fhir_type == "time" || (field_type && std::string(field_type) == "time");
		DateTimeParts time_parts = parseTimeParts(s);
		if (time_parts.valid && (is_time_typed || (s.find(':') != std::string::npos && s.find('-') == std::string::npos))) {
			FPValue time_val;
			time_val.type = FPValue::Type::Time;
			time_val.string_val = normalizeTimeLiteralString(s);
			FPCollection single = {time_val};
			return fn_highBoundary(single, precision_arg);
		}
		if (s.size() >= 4 && std::isdigit((unsigned char)s[0]) && std::isdigit((unsigned char)s[1]) &&
		    std::isdigit((unsigned char)s[2]) && std::isdigit((unsigned char)s[3])) {
			FPValue date_val;
			bool is_datetime_typed = fhir_type == "datetime" || fhir_type == "instant" ||
			                         (field_type && (std::string(field_type) == "dateTime" ||
			                                         std::string(field_type) == "instant"));
			if (s.find('T') != std::string::npos || is_datetime_typed) {
				date_val.type = FPValue::Type::DateTime;
			} else {
				date_val.type = FPValue::Type::Date;
			}
			date_val.string_val = s;
			FPCollection single = {date_val};
			return fn_highBoundary(single, precision_arg);
		}
	}

	if (t == FPValue::Type::Integer || t == FPValue::Type::Decimal) {
		return decimalBoundary(val, precision_arg, true);
	}
	if (t == FPValue::Type::Quantity) {
		FPValue dec_val = FPValue::FromDecimal(val.quantity_value);
		dec_val.source_text = val.source_text;
		auto result = decimalBoundary(dec_val, precision_arg, true);
		if (result.empty()) return {};
		FPValue qv;
		qv.type = FPValue::Type::Quantity;
		qv.quantity_value = result[0].decimal_val;
		qv.quantity_unit = val.quantity_unit;
		qv.source_text = result[0].source_text;
		return {qv};
	}

	int digit_prec = -1;
	if (precision_arg && !precision_arg->empty()) {
		digit_prec = static_cast<int>(toNumber((*precision_arg)[0]));
	}

	if (t == FPValue::Type::Date || t == FPValue::Type::DateTime) {
		std::string s = toString(val);
		DateTimeParts p = parseDateTimeParts(s);
		if (!p.valid) return {};
		std::string tz;
		auto tz_pos = s.find_last_of("+-Z");
		if (tz_pos != std::string::npos && tz_pos > 10) tz = s.substr(tz_pos);

		if (digit_prec > 0) {
			std::string result = formatDateTimeBoundary(p, digit_prec, true, tz, false);
			FPValue v;
			v.type = (digit_prec <= 8) ? FPValue::Type::Date : FPValue::Type::DateTime;
			v.string_val = result;
			return {v};
		}
		if (t == FPValue::Type::Date) {
			FPValue v;
			v.type = FPValue::Type::Date;
			v.string_val = formatDateTimeBoundary(p, 8, true, "", false);
			return {v};
		}
		// Default (no precision arg) - return at maximum precision (DateTime)
		FPValue v;
		v.type = FPValue::Type::DateTime;
		v.string_val = formatDateTimeBoundary(p, 17, true, tz, false);
		return {v};
	}
	if (t == FPValue::Type::Time) {
		std::string s = toString(val);
		DateTimeParts p = parseTimeParts(s);
		if (!p.valid) return {};
		if (digit_prec > 0) {
			std::string result = formatDateTimeBoundary(p, digit_prec, true, "", true);
			FPValue v; v.type = FPValue::Type::Time; v.string_val = result; return {v};
		}
		std::ostringstream oss;
		oss << std::setfill('0') << std::setw(2) << p.hour
		    << ":" << std::setfill('0') << std::setw(2) << (p.precision >= 5 ? p.minute : 59)
		    << ":59.999";
		FPValue v; v.type = FPValue::Type::Time; v.string_val = oss.str(); return {v};
	}
	return {};
}

FPCollection Evaluator::fn_precision(const FPCollection &input) {
	if (input.empty()) return {};
	auto &val = input[0];
	auto t = effectiveType(val);

	if (t == FPValue::Type::Integer) {
		return {FPValue::FromInteger(0)};
	}
	if (t == FPValue::Type::Decimal) {
		return {FPValue::FromInteger(countDecimalPlaces(val))};
	}
	if (t == FPValue::Type::Date || t == FPValue::Type::DateTime) {
		std::string s = toString(val);
		return {FPValue::FromInteger(countDigits(s))};
	}
	if (t == FPValue::Type::Time) {
		std::string s = toString(val);
		// Strip T prefix
		if (!s.empty() && s[0] == 'T') s = s.substr(1);
		// Strip timezone
		auto tz_pos = s.find_last_of("+-Z");
		if (tz_pos != std::string::npos && tz_pos > 4) s = s.substr(0, tz_pos);
		return {FPValue::FromInteger(countDigits(s))};
	}
	return {};
}

// --- Phase 8: children() and descendants() ---

FPCollection Evaluator::fn_children(const FPCollection &input) {
	FPCollection result;
	for (const auto &item : input) {
		if (item.type != FPValue::Type::JsonVal || !item.json_val) continue;
		yyjson_val *obj = item.json_val;
		if (yyjson_is_obj(obj)) {
			yyjson_obj_iter iter;
			yyjson_obj_iter_init(obj, &iter);
			yyjson_val *key;
			while ((key = yyjson_obj_iter_next(&iter))) {
				const char *key_str = yyjson_get_str(key);
				if (!key_str || key_str[0] == '_') continue; // skip primitive extensions
				if (std::string(key_str) == "resourceType") continue; // skip meta
				yyjson_val *val = yyjson_obj_iter_get_val(key);
				if (!val) continue;
				if (yyjson_is_arr(val)) {
					size_t idx2, max2;
					yyjson_val *elem;
					yyjson_arr_foreach(val, idx2, max2, elem) {
						result.push_back(FPValue::FromJson(elem));
					}
				} else {
					result.push_back(FPValue::FromJson(val));
				}
			}
		} else if (yyjson_is_arr(obj)) {
			size_t idx2, max2;
			yyjson_val *elem;
			yyjson_arr_foreach(obj, idx2, max2, elem) {
				result.push_back(FPValue::FromJson(elem));
			}
		}
	}
	return result;
}

FPCollection Evaluator::fn_descendants(const FPCollection &input) {
	FPCollection result;
	FPCollection current = input;
	std::unordered_set<std::string> seen;
	while (!current.empty()) {
		FPCollection next;
		std::unordered_set<std::string> pending;
		for (const auto &item : current) {
			FPCollection children = fn_children({item});
			for (const auto &child : children) {
				std::string key = fpValueRepeatKey(child);
				if (seen.find(key) == seen.end() && pending.find(key) == pending.end()) {
					next.push_back(child);
					pending.insert(key);
				}
			}
		}
		result.insert(result.end(), next.begin(), next.end());
		seen.insert(pending.begin(), pending.end());
		current = next;
		if (result.size() > 50000) break; // Safety limit
	}
	return result;
}

// --- Phase 8: encode()/decode() ---

static const char BASE64_CHARS[] = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

static std::string base64_encode(const std::string &input) {
	std::string output;
	int val = 0, valb = -6;
	for (unsigned char c : input) {
		val = (val << 8) + c;
		valb += 8;
		while (valb >= 0) {
			output.push_back(BASE64_CHARS[(val >> valb) & 0x3F]);
			valb -= 6;
		}
	}
	if (valb > -6) output.push_back(BASE64_CHARS[((val << 8) >> (valb + 8)) & 0x3F]);
	while (output.size() % 4) output.push_back('=');
	return output;
}

static std::string base64_decode(const std::string &input) {
	std::string output;
	int val = 0, valb = -8;
	for (unsigned char c : input) {
		if (c == '=') break;
		const char *p = std::strchr(BASE64_CHARS, c);
		if (!p) continue;
		val = (val << 6) + static_cast<int>(p - BASE64_CHARS);
		valb += 6;
		if (valb >= 0) {
			output.push_back(static_cast<char>((val >> valb) & 0xFF));
			valb -= 8;
		}
	}
	return output;
}

static std::string hex_encode(const std::string &input) {
	std::string output;
	static const char hex_chars[] = "0123456789abcdef";
	for (unsigned char c : input) {
		output.push_back(hex_chars[c >> 4]);
		output.push_back(hex_chars[c & 0x0F]);
	}
	return output;
}

static std::string hex_decode(const std::string &input) {
	std::string output;
	for (size_t i = 0; i + 1 < input.size(); i += 2) {
		char hi = input[i], lo = input[i + 1];
		auto hex_val = [](char c) -> int {
			if (c >= '0' && c <= '9') return c - '0';
			if (c >= 'a' && c <= 'f') return c - 'a' + 10;
			if (c >= 'A' && c <= 'F') return c - 'A' + 10;
			return 0;
		};
		output.push_back(static_cast<char>((hex_val(hi) << 4) | hex_val(lo)));
	}
	return output;
}

FPCollection Evaluator::fn_encode(const FPCollection &input, const FPCollection &format) {
	if (input.empty() || format.empty()) return {};
	std::string s = toString(input[0]);
	std::string fmt = toString(format[0]);
	if (fmt == "base64") return {FPValue::FromString(base64_encode(s))};
	if (fmt == "urlbase64" || fmt == "base64url") {
		std::string encoded = base64_encode(s);
		for (auto &c : encoded) {
			if (c == '+') c = '-';
			else if (c == '/') c = '_';
		}
		return {FPValue::FromString(encoded)};
	}
	if (fmt == "hex") return {FPValue::FromString(hex_encode(s))};
	return {};
}

FPCollection Evaluator::fn_decode(const FPCollection &input, const FPCollection &format) {
	if (input.empty() || format.empty()) return {};
	std::string s = toString(input[0]);
	std::string fmt = toString(format[0]);
	if (fmt == "base64") return {FPValue::FromString(base64_decode(s))};
	if (fmt == "urlbase64" || fmt == "base64url") {
		std::string decoded = s;
		for (auto &c : decoded) {
			if (c == '-') c = '+';
			else if (c == '_') c = '/';
		}
		return {FPValue::FromString(base64_decode(decoded))};
	}
	if (fmt == "hex") return {FPValue::FromString(hex_decode(s))};
	return {};
}

// --- Sort, coalesce, isDistinct, subsetOf, supersetOf ---

FPCollection Evaluator::fn_sort(const std::vector<const ASTNode *> &criteria, const FPCollection &input, yyjson_doc *doc) {
	if (input.empty()) return {};

	std::vector<size_t> indices(input.size());
	for (size_t i = 0; i < indices.size(); i++) indices[i] = i;

	std::sort(indices.begin(), indices.end(), [&](size_t a_idx, size_t b_idx) {
		for (size_t ci = 0; ci < criteria.size() || ci == 0; ci++) {
			FPCollection a_key, b_key;
			bool descending = false;

			if (ci < criteria.size() && criteria[ci]) {
				const ASTNode *key_node = criteria[ci];
				// Detect UnaryOp '-' for descending
				if (key_node->type == NodeType::UnaryOp && key_node->op == "-" && !key_node->children.empty()) {
					descending = true;
					key_node = key_node->children[0].get();
				}
				FPCollection a_single = {input[a_idx]};
				FPCollection b_single = {input[b_idx]};
				a_key = eval(*key_node, a_single, const_cast<yyjson_doc *>(current_doc_));
				b_key = eval(*key_node, b_single, const_cast<yyjson_doc *>(current_doc_));
			} else {
				a_key = {input[a_idx]};
				b_key = {input[b_idx]};
			}

			if (a_key.empty() && b_key.empty()) {
				continue; // equal at this criterion, try next
			}
			if (a_key.empty()) return true; // empty always sorts first
			if (b_key.empty()) return false;

			auto &av = a_key[0];
			auto &bv = b_key[0];
			bool less;
			if (isNumericType(av) && isNumericType(bv)) {
				double da = getNumericValue(av);
				double db = getNumericValue(bv);
				if (da == db) continue; // equal, try next criterion
				less = da < db;
			} else {
				std::string sa = toString(av);
				std::string sb = toString(bv);
				if (sa == sb) continue; // equal, try next criterion
				less = sa < sb;
			}
			return descending ? !less : less;
		}
		return false; // equal on all criteria
	});

	FPCollection result;
	for (auto idx : indices) {
		result.push_back(input[idx]);
	}
	return result;
}

FPCollection Evaluator::fn_coalesce(const ASTNode &node, const FPCollection &input, yyjson_doc *doc) {
	// coalesce(e1, e2, ...) - returns first non-empty argument
	// If called on a collection (source), check if source is non-empty
	if (node.source) {
		auto source = eval(*node.source, input, doc);
		if (!source.empty()) return source;
	}
	for (size_t i = 0; i < node.children.size(); i++) {
		auto result = eval(*node.children[i], input, doc);
		if (!result.empty()) return result;
	}
	return {};
}

FPCollection Evaluator::fn_isDistinct(const FPCollection &input) {
	// FHIRPath §5.1.3: Uses FHIRPath = operator for comparison
	FPCollection seen;
	for (const auto &item : input) {
		for (const auto &s : seen) {
			if (fpValuesEqual(item, s)) {
				return {FPValue::FromBoolean(false)};
			}
		}
		seen.push_back(item);
	}
	return {FPValue::FromBoolean(true)};
}

FPCollection Evaluator::fn_subsetOf(const FPCollection &input, const FPCollection &other) {
	// FHIRPath §5.1.8: Uses FHIRPath = operator for comparison
	for (const auto &item : input) {
		bool found = false;
		for (const auto &o : other) {
			if (fpValuesEqual(item, o)) { found = true; break; }
		}
		if (!found) return {FPValue::FromBoolean(false)};
	}
	return {FPValue::FromBoolean(true)};
}

FPCollection Evaluator::fn_supersetOf(const FPCollection &input, const FPCollection &other) {
	return fn_subsetOf(other, input);
}

// --- Date arithmetic ---

static bool isLeapYear(int64_t y) {
	return (y % 4 == 0 && y % 100 != 0) || (y % 400 == 0);
}

static int daysInMonth(int64_t y, int64_t m) {
	static const int days[] = {0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31};
	if (m == 2 && isLeapYear(y)) return 29;
	if (m >= 1 && m <= 12) return days[m];
	return 30;
}

static std::string stripQuantityUnitQuotes(const std::string &unit) {
	if (unit.size() >= 2 && unit.front() == '\'' && unit.back() == '\'') {
		return unit.substr(1, unit.size() - 2);
	}
	return unit;
}

FPCollection Evaluator::fn_dateArith(const FPValue &date_val, const FPValue &qty_val, bool subtract) {
	std::string dt = toString(date_val);
	double amount = qty_val.quantity_value;
	if (subtract) amount = -amount;
	std::string unit = qty_val.quantity_unit;
	auto orig_type = temporalArithmeticType(date_val);
	bool is_time = (orig_type == FPValue::Type::Time);

	// Normalize unit keywords
	if (unit == "'a'" || unit == "a" || unit == "'mo'" || unit == "mo") {
		throw FHIRPathSpecError("Definite year/month quantities are not valid for date/time arithmetic");
	}
	if (unit == "year" || unit == "years") unit = "year";
	else if (unit == "month" || unit == "months") unit = "month";
	else if (unit == "week" || unit == "weeks" || unit == "'wk'" || unit == "wk") unit = "week";
	else if (unit == "day" || unit == "days" || unit == "'d'" || unit == "d") unit = "day";
	else if (unit == "hour" || unit == "hours" || unit == "'h'" || unit == "h") unit = "hour";
	else if (unit == "minute" || unit == "minutes" || unit == "'min'" || unit == "min") unit = "minute";
	else if (unit == "second" || unit == "seconds" || unit == "'s'" || unit == "s") unit = "second";
	else if (unit == "millisecond" || unit == "milliseconds" || unit == "'ms'" || unit == "ms") unit = "millisecond";
	else throw FHIRPathSpecError("Invalid unit for date/time arithmetic");

	if ((orig_type == FPValue::Type::Date && !(unit == "year" || unit == "month" || unit == "week" || unit == "day")) ||
	    (orig_type == FPValue::Type::Time && !(unit == "hour" || unit == "minute" || unit == "second" || unit == "millisecond"))) {
		throw FHIRPathSpecError("Invalid unit for date/time arithmetic");
	}

	// Prevent overflow in intermediate calculations
	if (amount > 100000.0 || amount < -100000.0) {
		return {};
	}

	// For partial date/time values, determine the highest precision present.
	// If the quantity unit is more precise, convert it to the highest precision
	// of the partial (removing any decimal value), per spec §6.7:
	// "the operation is performed by converting the time-valued quantity to
	//  the highest precision in the partial (removing any decimal value off)"
	//
	// Unit precision hierarchy: year=1, month=2, week=3, day=4, hour=5, minute=6, second=7, millisecond=8
	if (!is_time) {
		// Parse date precision from the string representation
		// (done here before the main parsing block below)
		bool p_has_month = (dt.size() >= 7);
		bool p_has_day = (dt.size() >= 10);
		auto p_tpos = dt.find('T');
		bool p_has_time = (p_tpos != std::string::npos);

		// Determine the precision level of the date/time
		// 1=year, 2=month, 3=day, 5=hour, 6=minute, 7=second, 8=millisecond
		int date_prec = 1; // year only
		if (p_has_month) date_prec = 2;
		if (p_has_day) date_prec = 3;
		if (p_has_time) {
			// Extract time part (before timezone) to determine time precision
			std::string time_part = dt.substr(p_tpos + 1);
			// Strip timezone
			for (size_t i = 0; i < time_part.size(); ++i) {
				if (time_part[i] == '+' || time_part[i] == 'Z' || (time_part[i] == '-' && i > 0)) {
					time_part = time_part.substr(0, i);
					break;
				}
			}
			date_prec = 5; // at least hour
			if (time_part.size() >= 5) date_prec = 6; // has minutes
			if (time_part.size() >= 8) date_prec = 7; // has seconds
			auto pdot = time_part.find('.');
			if (pdot != std::string::npos) date_prec = 8; // has milliseconds
		}

		// Determine the precision level of the quantity unit
		int unit_prec = 0;
		if (unit == "year") unit_prec = 1;
		else if (unit == "month") unit_prec = 2;
		else if (unit == "week") unit_prec = 3;
		else if (unit == "day") unit_prec = 4;
		else if (unit == "hour") unit_prec = 5;
		else if (unit == "minute") unit_prec = 6;
		else if (unit == "second") unit_prec = 7;
		else if (unit == "millisecond") unit_prec = 8;

		// If the quantity is more precise than the date, convert down
		if (unit_prec > date_prec) {
			// Conversion to year
			if (date_prec == 1) {
				if (unit == "month") { amount = std::trunc(amount / 12.0); unit = "year"; }
				else if (unit == "week") { amount = std::trunc(amount * 7.0 / 365.0); unit = "year"; }
				else if (unit == "day") { amount = std::trunc(amount / 365.0); unit = "year"; }
				else if (unit == "hour") { amount = std::trunc(amount / (365.0 * 24.0)); unit = "year"; }
				else if (unit == "minute") { amount = std::trunc(amount / (365.0 * 24.0 * 60.0)); unit = "year"; }
				else if (unit == "second") { amount = std::trunc(amount / (365.0 * 24.0 * 3600.0)); unit = "year"; }
				else if (unit == "millisecond") { amount = std::trunc(amount / (365.0 * 24.0 * 3600000.0)); unit = "year"; }
			}
			// Conversion to month
			else if (date_prec == 2) {
				if (unit == "week") { amount = std::trunc(amount * 7.0 / 30.0); unit = "month"; }
				else if (unit == "day") { amount = std::trunc(amount / 30.0); unit = "month"; }
				else if (unit == "hour") { amount = std::trunc(amount / (30.0 * 24.0)); unit = "month"; }
				else if (unit == "minute") { amount = std::trunc(amount / (30.0 * 24.0 * 60.0)); unit = "month"; }
				else if (unit == "second") { amount = std::trunc(amount / (30.0 * 24.0 * 3600.0)); unit = "month"; }
				else if (unit == "millisecond") { amount = std::trunc(amount / (30.0 * 24.0 * 3600000.0)); unit = "month"; }
			}
			// Conversion to day
			else if (date_prec == 3) {
				if (unit == "hour") { amount = std::trunc(amount / 24.0); unit = "day"; }
				else if (unit == "minute") { amount = std::trunc(amount / (24.0 * 60.0)); unit = "day"; }
				else if (unit == "second") { amount = std::trunc(amount / (24.0 * 3600.0)); unit = "day"; }
				else if (unit == "millisecond") { amount = std::trunc(amount / (24.0 * 3600000.0)); unit = "day"; }
			}
			// Conversion to hour (date_prec == 5, has only hour)
			else if (date_prec == 5) {
				if (unit == "minute") { amount = std::trunc(amount / 60.0); unit = "hour"; }
				else if (unit == "second") { amount = std::trunc(amount / 3600.0); unit = "hour"; }
				else if (unit == "millisecond") { amount = std::trunc(amount / 3600000.0); unit = "hour"; }
			}
			// Conversion to minute (date_prec == 6, has minutes)
			else if (date_prec == 6) {
				if (unit == "second") { amount = std::trunc(amount / 60.0); unit = "minute"; }
				else if (unit == "millisecond") { amount = std::trunc(amount / 60000.0); unit = "minute"; }
			}
			// Conversion to second (date_prec == 7, has seconds)
			else if (date_prec == 7) {
				if (unit == "millisecond") { amount = std::trunc(amount / 1000.0); unit = "second"; }
			}
		}
	}

	if (is_time) {
		// Time arithmetic: parse HH:MM:SS.mmm
		// Strip leading 'T' if present
		std::string time_str = dt;
		if (!time_str.empty() && time_str[0] == 'T') time_str = time_str.substr(1);
		int64_t hour = 0, minute = 0, second = 0, millis = 0;
		bool has_minute = false, has_second = false, has_millis = false;
		if (time_str.size() >= 2) hour = std::stoi(time_str.substr(0, 2));
		if (time_str.size() >= 5) { minute = std::stoi(time_str.substr(3, 2)); has_minute = true; }
		if (time_str.size() >= 8) { second = std::stoi(time_str.substr(6, 2)); has_second = true; }
		auto dotpos = time_str.find('.');
		if (dotpos != std::string::npos) {
			std::string ms = time_str.substr(dotpos + 1);
			while (ms.size() < 3) ms += '0';
			millis = std::stoi(ms.substr(0, 3));
			has_millis = true;
		}

		int time_prec = has_millis ? 4 : (has_second ? 3 : (has_minute ? 2 : 1));
		int unit_prec = 0;
		if (unit == "hour") unit_prec = 1;
		else if (unit == "minute") unit_prec = 2;
		else if (unit == "second") unit_prec = 3;
		else if (unit == "millisecond") unit_prec = 4;

		if (unit_prec > time_prec) {
			if (time_prec == 1) {
				if (unit == "minute") { amount = std::trunc(amount / 60.0); unit = "hour"; }
				else if (unit == "second") { amount = std::trunc(amount / 3600.0); unit = "hour"; }
				else if (unit == "millisecond") { amount = std::trunc(amount / 3600000.0); unit = "hour"; }
			} else if (time_prec == 2) {
				if (unit == "second") { amount = std::trunc(amount / 60.0); unit = "minute"; }
				else if (unit == "millisecond") { amount = std::trunc(amount / 60000.0); unit = "minute"; }
			} else if (time_prec == 3) {
				if (unit == "millisecond") { amount = std::trunc(amount / 1000.0); unit = "second"; }
			}
		}

		int64_t iamount = static_cast<int64_t>(amount);
		if (unit == "hour") hour += iamount;
		else if (unit == "minute") { minute += iamount; has_minute = true; }
		else if (unit == "second") { second += iamount; has_second = true; has_minute = true; }
		else if (unit == "millisecond") { millis += iamount; has_millis = true; has_second = true; has_minute = true; }
		else return {};

		// Normalize
		while (millis >= 1000) { millis -= 1000; second++; }
		while (millis < 0) { millis += 1000; second--; }
		while (second >= 60) { second -= 60; minute++; }
		while (second < 0) { second += 60; minute--; }
		while (minute >= 60) { minute -= 60; hour++; }
		while (minute < 0) { minute += 60; hour--; }
		// Time wraps at 24
		hour = ((hour % 24) + 24) % 24;

		char buf[32];
		FPValue result;
		result.type = FPValue::Type::Time;
		if (!has_minute) {
			std::snprintf(buf, sizeof(buf), "%02d", static_cast<int>(hour));
		} else if (!has_second) {
			std::snprintf(buf, sizeof(buf), "%02d:%02d", static_cast<int>(hour), static_cast<int>(minute));
		} else if (!has_millis) {
			std::snprintf(buf, sizeof(buf), "%02d:%02d:%02d", static_cast<int>(hour), static_cast<int>(minute), static_cast<int>(second));
		} else {
			std::snprintf(buf, sizeof(buf), "%02d:%02d:%02d.%03d", static_cast<int>(hour), static_cast<int>(minute), static_cast<int>(second), static_cast<int>(millis));
		}
		result.string_val = std::string("T") + buf;
		return {result};
	}

	// Date/DateTime arithmetic (use int64_t to prevent overflow in day addition loops)
	int64_t year = 0, month = 1, day = 1, hour = 0, minute = 0, second = 0, millis = 0;
	std::string tz;
	bool has_month = false, has_day = false, has_time = false;
	bool has_hour = false, has_minute = false, has_second = false, has_millis = false;

	if (dt.size() >= 4) year = std::stoi(dt.substr(0, 4));
	if (dt.size() >= 7) { month = std::stoi(dt.substr(5, 2)); has_month = true; }
	if (dt.size() >= 10) { day = std::stoi(dt.substr(8, 2)); has_day = true; }

	auto tpos = dt.find('T');
	if (tpos != std::string::npos) {
		has_time = true;
		std::string time_part = dt.substr(tpos + 1);
		// Find timezone
		size_t tz_pos = std::string::npos;
		for (size_t i = 0; i < time_part.size(); ++i) {
			if (time_part[i] == '+' || time_part[i] == 'Z' || (time_part[i] == '-' && i > 0)) {
				tz_pos = i;
				break;
			}
		}
		if (tz_pos != std::string::npos) {
			tz = time_part.substr(tz_pos);
			time_part = time_part.substr(0, tz_pos);
		}
		if (time_part.size() >= 2) { hour = std::stoi(time_part.substr(0, 2)); has_hour = true; }
		if (time_part.size() >= 5) { minute = std::stoi(time_part.substr(3, 2)); has_minute = true; }
		if (time_part.size() >= 8) { second = std::stoi(time_part.substr(6, 2)); has_second = true; }
		auto dot = time_part.find('.');
		if (dot != std::string::npos) {
			std::string ms = time_part.substr(dot + 1);
			while (ms.size() < 3) ms += '0';
			millis = std::stoi(ms.substr(0, 3));
			has_millis = true;
		}
	}

	int64_t iamount = static_cast<int64_t>(amount);

	if (unit == "year") {
		year += iamount;
		// Clamp day for leap year
		if (has_day && day > daysInMonth(year, month)) {
			day = daysInMonth(year, month);
		}
	} else if (unit == "month") {
		month += iamount;
		while (month > 12) { month -= 12; year++; }
		while (month < 1) { month += 12; year--; }
		if (has_day && day > daysInMonth(year, month)) {
			day = daysInMonth(year, month);
		}
	} else if (unit == "week") {
		day += iamount * 7;
		// Normalize days
		while (day > daysInMonth(year, month)) {
			day -= daysInMonth(year, month);
			month++;
			if (month > 12) { month = 1; year++; }
		}
		while (day < 1) {
			month--;
			if (month < 1) { month = 12; year--; }
			day += daysInMonth(year, month);
		}
	} else if (unit == "day") {
		day += iamount;
		while (day > daysInMonth(year, month)) {
			day -= daysInMonth(year, month);
			month++;
			if (month > 12) { month = 1; year++; }
		}
		while (day < 1) {
			month--;
			if (month < 1) { month = 12; year--; }
			day += daysInMonth(year, month);
		}
	} else if (unit == "hour") {
		hour += iamount;
		while (hour >= 24) { hour -= 24; day++; }
		while (hour < 0) { hour += 24; day--; }
		while (day > daysInMonth(year, month)) { day -= daysInMonth(year, month); month++; if (month > 12) { month = 1; year++; } }
		while (day < 1) { month--; if (month < 1) { month = 12; year--; } day += daysInMonth(year, month); }
	} else if (unit == "minute") {
		minute += iamount;
		while (minute >= 60) { minute -= 60; hour++; }
		while (minute < 0) { minute += 60; hour--; }
		while (hour >= 24) { hour -= 24; day++; }
		while (hour < 0) { hour += 24; day--; }
		while (day > daysInMonth(year, month)) { day -= daysInMonth(year, month); month++; if (month > 12) { month = 1; year++; } }
		while (day < 1) { month--; if (month < 1) { month = 12; year--; } day += daysInMonth(year, month); }
	} else if (unit == "second") {
		second += iamount;
		while (second >= 60) { second -= 60; minute++; }
		while (second < 0) { second += 60; minute--; }
		while (minute >= 60) { minute -= 60; hour++; }
		while (minute < 0) { minute += 60; hour--; }
		while (hour >= 24) { hour -= 24; day++; }
		while (hour < 0) { hour += 24; day--; }
		while (day > daysInMonth(year, month)) { day -= daysInMonth(year, month); month++; if (month > 12) { month = 1; year++; } }
		while (day < 1) { month--; if (month < 1) { month = 12; year--; } day += daysInMonth(year, month); }
	} else if (unit == "millisecond") {
		millis += iamount;
		while (millis >= 1000) { millis -= 1000; second++; }
		while (millis < 0) { millis += 1000; second--; }
		while (second >= 60) { second -= 60; minute++; }
		while (second < 0) { second += 60; minute--; }
		while (minute >= 60) { minute -= 60; hour++; }
		while (minute < 0) { minute += 60; hour--; }
		while (hour >= 24) { hour -= 24; day++; }
		while (hour < 0) { hour += 24; day--; }
		while (day > daysInMonth(year, month)) { day -= daysInMonth(year, month); month++; if (month > 12) { month = 1; year++; } }
		while (day < 1) { month--; if (month < 1) { month = 12; year--; } day += daysInMonth(year, month); }
	}

	if (year < 1 || year > 9999) {
		throw FHIRPathSpecError("Date/time arithmetic result year is out of range");
	}

	// Reconstruct the date string with the same precision as input
	char buf[64];
	FPValue result;
	if (orig_type == FPValue::Type::Date) result.type = FPValue::Type::Date;
	else result.type = FPValue::Type::DateTime;

	if (!has_month) {
		std::snprintf(buf, sizeof(buf), "%04d", static_cast<int>(year));
	} else if (!has_day) {
		std::snprintf(buf, sizeof(buf), "%04d-%02d", static_cast<int>(year), static_cast<int>(month));
	} else if (!has_time) {
		std::snprintf(buf, sizeof(buf), "%04d-%02d-%02d", static_cast<int>(year), static_cast<int>(month), static_cast<int>(day));
	} else if (!has_minute) {
		std::snprintf(buf, sizeof(buf), "%04d-%02d-%02dT%02d%s", static_cast<int>(year), static_cast<int>(month), static_cast<int>(day), static_cast<int>(hour), tz.c_str());
	} else if (!has_second) {
		std::snprintf(buf, sizeof(buf), "%04d-%02d-%02dT%02d:%02d%s", static_cast<int>(year), static_cast<int>(month), static_cast<int>(day), static_cast<int>(hour), static_cast<int>(minute), tz.c_str());
	} else if (!has_millis) {
		std::snprintf(buf, sizeof(buf), "%04d-%02d-%02dT%02d:%02d:%02d%s", static_cast<int>(year), static_cast<int>(month), static_cast<int>(day), static_cast<int>(hour), static_cast<int>(minute), static_cast<int>(second), tz.c_str());
	} else {
		std::snprintf(buf, sizeof(buf), "%04d-%02d-%02dT%02d:%02d:%02d.%03d%s", static_cast<int>(year), static_cast<int>(month), static_cast<int>(day), static_cast<int>(hour), static_cast<int>(minute), static_cast<int>(second), static_cast<int>(millis), tz.c_str());
	}
	result.string_val = buf;
	return {result};
}

// --- Factory support ---

// Escape a string for safe embedding inside a JSON string literal.
// Handles: " \ / \b \f \n \r \t and control characters.
static std::string escapeJsonString(const std::string &s) {
	std::string out;
	out.reserve(s.size() + 4);
	for (unsigned char c : s) {
		switch (c) {
		case '"':  out += "\\\""; break;
		case '\\': out += "\\\\"; break;
		case '\b': out += "\\b";  break;
		case '\f': out += "\\f";  break;
		case '\n': out += "\\n";  break;
		case '\r': out += "\\r";  break;
		case '\t': out += "\\t";  break;
		default:
			if (c < 0x20) {
				char buf[8];
				std::snprintf(buf, sizeof(buf), "\\u%04x", static_cast<unsigned>(c));
				out += buf;
			} else {
				out += static_cast<char>(c);
			}
		}
	}
	return out;
}

static yyjson_val* createOwnedDoc(std::vector<yyjson_doc*> &owned_docs, const std::string &json_str) {
	yyjson_doc *d = yyjson_read(json_str.c_str(), json_str.size(), 0);
	if (!d) return nullptr;
	owned_docs.push_back(d);
	return yyjson_doc_get_root(d);
}

FPCollection Evaluator::evalFactoryMethod(const ASTNode &node, yyjson_doc *doc) {
	const auto &name = node.name;

	if (name == "exists") {
		return {FPValue::FromBoolean(true)};
	}

	// Evaluate all arguments
	std::vector<FPCollection> args;
	for (size_t i = 0; i < node.children.size(); i++) {
		args.push_back(eval(*node.children[i], {FPValue::FromJson(resource_context_)}, doc));
	}

	if (name == "Coding") {
		std::string system_str, code_str, display_str;
		if (args.size() >= 1 && !args[0].empty()) system_str = toString(args[0][0]);
		if (args.size() >= 2 && !args[1].empty()) code_str = toString(args[1][0]);
		if (args.size() >= 3 && !args[2].empty()) display_str = toString(args[2][0]);

		std::string json = "{\"system\":\"" + escapeJsonString(system_str) + "\",\"code\":\"" + escapeJsonString(code_str) + "\"";
		if (!display_str.empty()) {
			json += ",\"display\":\"" + escapeJsonString(display_str) + "\"";
		}
		json += "}";
		yyjson_val *root = createOwnedDoc(owned_docs_, json);
		if (root) return {FPValue::FromJson(root)};
		return {};
	}

	if (name == "Extension") {
		std::string url_str, value_str;
		if (args.size() >= 1 && !args[0].empty()) url_str = toString(args[0][0]);
		if (args.size() >= 2 && !args[1].empty()) value_str = toString(args[1][0]);

		std::string json = "{\"url\":\"" + escapeJsonString(url_str) + "\",\"valueString\":\"" + escapeJsonString(value_str) + "\"}";
		yyjson_val *root = createOwnedDoc(owned_docs_, json);
		if (root) return {FPValue::FromJson(root)};
		return {};
	}

	if (name == "Identifier") {
		std::string system_str, value_str;
		if (args.size() >= 1 && !args[0].empty()) system_str = toString(args[0][0]);
		if (args.size() >= 2 && !args[1].empty()) value_str = toString(args[1][0]);

		std::string json = "{\"system\":\"" + escapeJsonString(system_str) + "\",\"value\":\"" + escapeJsonString(value_str) + "\"}";
		yyjson_val *root = createOwnedDoc(owned_docs_, json);
		if (root) return {FPValue::FromJson(root)};
		return {};
	}

	if (name == "HumanName") {
		std::string family_str;
		if (args.size() >= 1 && !args[0].empty()) family_str = toString(args[0][0]);

		std::string json = "{\"family\":\"" + escapeJsonString(family_str) + "\"}";
		yyjson_val *root = createOwnedDoc(owned_docs_, json);
		if (root) return {FPValue::FromJson(root)};
		return {};
	}

	if (name == "ContactPoint") {
		std::string system_str, value_str;
		if (args.size() >= 1 && !args[0].empty()) system_str = toString(args[0][0]);
		if (args.size() >= 2 && !args[1].empty()) value_str = toString(args[1][0]);

		std::string json = "{\"system\":\"" + escapeJsonString(system_str) + "\",\"value\":\"" + escapeJsonString(value_str) + "\"}";
		yyjson_val *root = createOwnedDoc(owned_docs_, json);
		if (root) return {FPValue::FromJson(root)};
		return {};
	}

	if (name == "Address") {
		std::string city_str, state_str, zip_str, country_str;
		if (args.size() >= 2 && !args[1].empty()) city_str = toString(args[1][0]);
		if (args.size() >= 3 && !args[2].empty()) state_str = toString(args[2][0]);
		if (args.size() >= 4 && !args[3].empty()) zip_str = toString(args[3][0]);
		if (args.size() >= 5 && !args[4].empty()) country_str = toString(args[4][0]);

		std::string json = "{\"line\":[],\"city\":\"" + escapeJsonString(city_str) + "\",\"state\":\"" + escapeJsonString(state_str) +
		                   "\",\"postalCode\":\"" + escapeJsonString(zip_str) + "\",\"country\":\"" + escapeJsonString(country_str) + "\"}";
		yyjson_val *root = createOwnedDoc(owned_docs_, json);
		if (root) return {FPValue::FromJson(root)};
		return {};
	}

	if (name == "Quantity") {
		std::string system_str, code_str;
		double value_num = 0;
		if (args.size() >= 1 && !args[0].empty()) system_str = toString(args[0][0]);
		if (args.size() >= 2 && !args[1].empty()) code_str = toString(args[1][0]);
		if (args.size() >= 3 && !args[2].empty()) value_num = toNumber(args[2][0]);

		std::string value_str;
		if (value_num == (double)(int64_t)value_num) {
			char buf[64];
			std::snprintf(buf, sizeof(buf), "%lld", (long long)(int64_t)value_num);
			value_str = buf;
		} else {
			char buf[64];
			std::snprintf(buf, sizeof(buf), "%g", value_num);
			value_str = buf;
		}

		std::string json = "{\"system\":\"" + escapeJsonString(system_str) + "\",\"code\":\"" + escapeJsonString(code_str) + "\",\"value\":" + value_str + "}";
		yyjson_val *root = createOwnedDoc(owned_docs_, json);
		if (root) return {FPValue::FromJson(root)};
		return {};
	}

	if (name == "CodeableConcept") {
		std::string text_str;
		std::string coding_json = "{}";
		if (args.size() >= 1 && !args[0].empty()) {
			const FPValue &coding_val = args[0][0];
			if (coding_val.type == FPValue::Type::JsonVal && coding_val.json_val) {
				char *s = yyjson_val_write(coding_val.json_val, 0, nullptr);
				if (s) { coding_json = s; free(s); }
			}
		}
		if (args.size() >= 2 && !args[1].empty()) text_str = toString(args[1][0]);

		std::string json = "{\"coding\":[" + coding_json + "],\"text\":\"" + escapeJsonString(text_str) + "\"}";
		yyjson_val *root = createOwnedDoc(owned_docs_, json);
		if (root) return {FPValue::FromJson(root)};
		return {};
	}

	if (name == "create") {
		std::string rt_str;
		if (args.size() >= 1 && !args[0].empty()) rt_str = toString(args[0][0]);

		std::string json = "{\"resourceType\":\"" + escapeJsonString(rt_str) + "\"}";
		yyjson_val *root = createOwnedDoc(owned_docs_, json);
		if (root) return {FPValue::FromJson(root)};
		return {};
	}

	if (name == "withProperty") {
		if (args.size() < 3) return {};
		std::string instance_json = "{}";
		if (!args[0].empty()) {
			const FPValue &inst = args[0][0];
			if (inst.type == FPValue::Type::JsonVal && inst.json_val) {
				char *s = yyjson_val_write(inst.json_val, 0, nullptr);
				if (s) { instance_json = s; free(s); }
			}
		}
		std::string prop_name;
		if (!args[1].empty()) prop_name = toString(args[1][0]);

		std::string value_json;
		if (!args[2].empty()) {
			const FPValue &val = args[2][0];
			FPValue::Type vt = effectiveType(val);
			if (vt == FPValue::Type::Boolean) {
				value_json = toBoolean(val) ? "true" : "false";
			} else if (vt == FPValue::Type::Integer) {
				char buf[64];
				std::snprintf(buf, sizeof(buf), "%lld", (long long)val.int_val);
				value_json = buf;
			} else if (vt == FPValue::Type::Decimal) {
				char buf[64];
				std::snprintf(buf, sizeof(buf), "%g", val.decimal_val);
				value_json = buf;
			} else if (val.type == FPValue::Type::JsonVal && val.json_val) {
				if (yyjson_is_bool(val.json_val)) {
					value_json = yyjson_get_bool(val.json_val) ? "true" : "false";
				} else {
					char *s = yyjson_val_write(val.json_val, 0, nullptr);
					if (s) { value_json = s; free(s); }
				}
			} else {
				value_json = "\"" + escapeJsonString(toString(val)) + "\"";
			}
		}

		if (instance_json.size() >= 2 && instance_json.back() == '}') {
			std::string new_json = instance_json.substr(0, instance_json.size() - 1);
			if (new_json.size() > 1) new_json += ",";
			new_json += "\"" + escapeJsonString(prop_name) + "\":" + value_json + "}";
			yyjson_val *root = createOwnedDoc(owned_docs_, new_json);
			if (root) return {FPValue::FromJson(root)};
		}
		return {};
	}

	if (name == "withExtension") {
		if (args.size() < 3) return {};
		std::string instance_json = "{}";
		if (!args[0].empty()) {
			const FPValue &inst = args[0][0];
			if (inst.type == FPValue::Type::JsonVal && inst.json_val) {
				char *s = yyjson_val_write(inst.json_val, 0, nullptr);
				if (s) { instance_json = s; free(s); }
			}
		}
		std::string ext_url;
		if (!args[1].empty()) ext_url = toString(args[1][0]);
		std::string ext_val;
		if (!args[2].empty()) ext_val = toString(args[2][0]);

		std::string ext_json = "{\"url\":\"" + escapeJsonString(ext_url) + "\",\"valueString\":\"" + escapeJsonString(ext_val) + "\"}";
		if (instance_json.size() >= 2 && instance_json.back() == '}') {
			std::string new_json = instance_json.substr(0, instance_json.size() - 1);
			if (new_json.size() > 1) new_json += ",";
			new_json += "\"extension\":[" + ext_json + "]}";
			yyjson_val *root = createOwnedDoc(owned_docs_, new_json);
			if (root) return {FPValue::FromJson(root)};
		}
		return {};
	}

	return {};
}

} // namespace fhirpath
