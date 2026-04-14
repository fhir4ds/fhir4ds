#include "fhirpath/evaluator.hpp"
#include "shared/ucum_units.hpp"
#include "yyjson.hpp"

using namespace duckdb_yyjson; // NOLINT
#include <algorithm>
#include <cctype>
#include <climits>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <ctime>
#include <iomanip>
#include <regex>
#include <sstream>
#include <stdexcept>
#include <unordered_map>

// Defensive bounds-check macro for AST child access.
// The parser should guarantee correct structure, but this guards against
// malformed input or future parser changes.
#define FHIRPATH_REQUIRE_CHILDREN(node, n) \
	do { if ((node).children.size() < static_cast<size_t>(n)) return {}; } while (0)

namespace fhirpath {

// Thread-local regex cache to avoid recompilation in hot paths
static const std::regex &get_cached_regex(const std::string &pattern,
                                          std::regex_constants::syntax_option_type flags = std::regex_constants::ECMAScript) {
	// Reject patterns that are too long to prevent ReDoS compilation delay.
	if (pattern.size() > 1024) {
		throw std::runtime_error("FHIRPath: regex pattern exceeds maximum length of 1024 characters");
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

// Forward declarations
static int countDecimalPlaces(const FPValue &val);

// --- Static helper functions (used throughout) ---

static FPValue::Type effectiveType(const FPValue &v) {
	if (v.type != FPValue::Type::JsonVal || !v.json_val) return v.type;
	if (yyjson_is_bool(v.json_val)) return FPValue::Type::Boolean;
	if (yyjson_is_int(v.json_val)) return FPValue::Type::Integer;
	if (yyjson_is_real(v.json_val)) return FPValue::Type::Decimal;
	if (yyjson_is_str(v.json_val)) return FPValue::Type::String;
	return v.type;
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

static double convertQuantityToBase(double value, const std::string &unit, std::string &base_unit) {
	return fhir::ConvertToBaseUnit(value, unit, base_unit);
}

// Try to convert a JSON value to a Quantity if it looks like one (has value, code/unit fields)
static bool tryJsonToQuantity(const FPValue &v, double &out_value, std::string &out_unit) {
	if (v.type != FPValue::Type::JsonVal || !v.json_val || !yyjson_is_obj(v.json_val)) return false;
	yyjson_val *val_field = yyjson_obj_get(v.json_val, "value");
	if (!val_field) return false;
	if (yyjson_is_num(val_field)) {
		out_value = yyjson_get_num(val_field);
	} else if (yyjson_is_str(val_field)) {
		try { out_value = std::stod(yyjson_get_str(val_field)); }
		catch (const std::exception &) { return false; }
	} else return false;
	yyjson_val *code_field = yyjson_obj_get(v.json_val, "code");
	if (code_field && yyjson_is_str(code_field)) {
		out_unit = yyjson_get_str(code_field);
	} else {
		yyjson_val *unit_field = yyjson_obj_get(v.json_val, "unit");
		if (unit_field && yyjson_is_str(unit_field)) out_unit = yyjson_get_str(unit_field);
		else out_unit = "1";
	}
	return true;
}

// FHIR field name to primitive type mapping for common fields
static const char* fhirFieldType(const std::string &field_name) {
	// code fields
	if (field_name == "gender" || field_name == "status" || field_name == "use" ||
	    field_name == "type" || field_name == "intent" || field_name == "priority" ||
	    field_name == "language" || field_name == "mode" || field_name == "code" ||
	    field_name == "comparator" || field_name == "direction" || field_name == "linkId")
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

FPCollection Evaluator::eval(const ASTNode &node, const FPCollection &input, yyjson_doc *doc) {
	switch (node.type) {
	case NodeType::IntegerLiteral:
		return {FPValue::FromInteger(node_value_get<int64_t>(node.value))};
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
		return {v};
	}
	case NodeType::QuantityLiteral: {
		auto qv = node_value_get<QuantityValue>(node.value);
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
		if (node.name == "%resource" || node.name == "%context") {
			if (resource_context_) {
				return {FPValue::FromJson(resource_context_)};
			}
		}
		// Well-known terminology URIs
		if (node.name == "%sct") return {FPValue::FromString("http://snomed.info/sct")};
		if (node.name == "%loinc") return {FPValue::FromString("http://loinc.org")};
		if (node.name == "%ucum") return {FPValue::FromString("http://unitsofmeasure.org")};
		if (node.name.substr(0, 4) == "%vs-") {
			return {FPValue::FromString("http://hl7.org/fhir/ValueSet/" + node.name.substr(4))};
		}
		if (node.name.substr(0, 5) == "%ext-") {
			return {FPValue::FromString("http://hl7.org/fhir/StructureDefinition/" + node.name.substr(5))};
		}
		// Check user-defined variables
		{
			std::string var_name = node.name;
			if (!var_name.empty() && var_name[0] == '%') var_name = var_name.substr(1);
			auto it = defined_variables_.find(var_name);
			if (it != defined_variables_.end()) {
				return it->second;
			}
			// If it looks like a user variable (not a known system var), throw
			// Known system vars: %resource, %context, %sct, %loinc, %ucum, %vs-*, %ext-*, %rootResource
			if (node.name == "%factory") {
				return {FPValue::FromString("__fhirpath_factory__")};
			}
			if (node.name != "%resource" && node.name != "%context" && node.name != "%rootResource" &&
			    node.name != "%sct" && node.name != "%loinc" && node.name != "%ucum" &&
			    node.name.substr(0, 4) != "%vs-" && node.name.substr(0, 4) != "%ext" &&
			    node.name != "%factory" && node.name != "%terminologies") {
				throw std::runtime_error("Undefined variable: " + node.name);
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

FPCollection Evaluator::evalMemberAccess(const ASTNode &node, const FPCollection &input, yyjson_doc *doc) {
	FPCollection result;
	const auto &field_name = node.name;

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
				if (yyjson_is_arr(child)) {
					size_t idx2, max2;
					yyjson_val *elem;
					yyjson_arr_foreach(child, idx2, max2, elem) {
						FPValue fpv = FPValue::FromJson(elem);
						fpv.field_name = field_name;
						result.push_back(fpv);
					}
				} else {
					FPValue fpv = FPValue::FromJson(child);
					fpv.field_name = field_name;
					result.push_back(fpv);
				}
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
									if (yyjson_is_arr(choice_val)) {
										size_t idx3, max3;
										yyjson_val *elem2;
										yyjson_arr_foreach(choice_val, idx3, max3, elem2) {
											FPValue fpv = FPValue::FromJson(elem2);
											fpv.fhir_type = choice_type;
											result.push_back(fpv);
										}
									} else {
										FPValue fpv = FPValue::FromJson(choice_val);
										fpv.fhir_type = choice_type;
										result.push_back(fpv);
									}
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
						if (yyjson_is_arr(child)) {
							size_t idx3, max3;
							yyjson_val *inner_elem;
							yyjson_arr_foreach(child, idx3, max3, inner_elem) {
								result.push_back(FPValue::FromJson(inner_elem));
							}
						} else {
							result.push_back(FPValue::FromJson(child));
						}
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

	int64_t idx = 0;
	auto &idx_val = index_col[0];
	if (idx_val.type == FPValue::Type::Integer) {
		idx = idx_val.int_val;
	} else if (idx_val.type == FPValue::Type::JsonVal && idx_val.json_val && yyjson_is_int(idx_val.json_val)) {
		idx = yyjson_get_sint(idx_val.json_val);
	}

	if (idx >= 0 && static_cast<size_t>(idx) < source_col.size()) {
		return {source_col[static_cast<size_t>(idx)]};
	}
	return {};
}

FPCollection Evaluator::evalWhere(const ASTNode &node, const FPCollection &input, yyjson_doc *doc) {
	if (node.children.empty()) {
		return input;
	}
	FPCollection result;
	for (const auto &item : input) {
		FPCollection single = {item};
		auto criteria_result = eval(*node.children[0], single, doc);
		if (isTruthy(criteria_result)) {
			result.push_back(item);
		}
	}
	return result;
}

FPCollection Evaluator::evalExists(const ASTNode &node, const FPCollection &input, yyjson_doc *doc) {
	if (node.children.empty()) {
		return {FPValue::FromBoolean(!input.empty())};
	}
	// exists(criteria) — check if any element matches
	for (const auto &item : input) {
		FPCollection single = {item};
		auto criteria_result = eval(*node.children[0], single, doc);
		if (isTruthy(criteria_result)) {
			return {FPValue::FromBoolean(true)};
		}
	}
	return {FPValue::FromBoolean(false)};
}

FPCollection Evaluator::evalOfType(const ASTNode &node, const FPCollection &input, yyjson_doc *doc) {
	if (node.children.empty()) {
		return {};
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
		target_type = node_value_get<std::string>(node.children[0]->value);
	} else {
		target_type = node.children[0]->name;
	}

	FPCollection result;
	for (const auto &item : input) {
		FPCollection single = {item};
		// ofType() uses exact type matching
		auto is_result = fn_isType(single, target_type, true);
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
		return fn_toQuantity(input);
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
		return fn_convertsToQuantity(input);
	}
	if (name == "toTime") {
		return fn_toTime(input);
	}
	if (name == "type") {
		if (input.empty()) return {};
		auto &val = input[0];
		auto t = effectiveType(val);
		std::string ns, nm;
		// Values from JSON navigation are FHIR types (lowercase names)
		bool is_fhir = (val.type == FPValue::Type::JsonVal);
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
			if (is_fhir) { ns = "FHIR"; nm = "string"; } else { ns = "System"; nm = "String"; }
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
				} else {
					ns = "FHIR";
					nm = "BackboneElement";
				}
			}
			break;
		}
		// Build a JSON string for the type info and parse it
		std::string json_str = "{\"namespace\":\"" + ns + "\",\"name\":\"" + nm + "\"}";
		yyjson_doc *type_doc = yyjson_read(json_str.c_str(), json_str.size(), 0);
		if (type_doc) {
			owned_docs_.push_back(type_doc);
			yyjson_val *type_root = yyjson_doc_get_root(type_doc);
			return {FPValue::FromJson(type_root)};
		}
		return {};
	}
	if (name == "conformsTo") {
		if (node.children.empty()) return {};
		auto arg = evalArgIsolated(*node.children[0], input, doc);
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
								throw std::runtime_error("Unknown modifier extension: " + url);
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
		std::string s = toString(input[0]);
		FPCollection result;
		for (size_t i = 0; i < s.size(); i++) {
			result.push_back(FPValue::FromString(std::string(1, s[i])));
		}
		return result;
	}
	if (name == "now") {
		time_t t = time(nullptr);
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
		time_t t = time(nullptr);
		struct tm tm_buf;
		gmtime_r(&t, &tm_buf);
		char buf[32];
		std::snprintf(buf, sizeof(buf), "%04d-%02d-%02d", tm_buf.tm_year + 1900, tm_buf.tm_mon + 1, tm_buf.tm_mday);
		FPValue v; v.type = FPValue::Type::Date; v.string_val = buf;
		return {v};
	}
	if (name == "timeOfDay") {
		time_t t = time(nullptr);
		struct tm tm_buf;
		gmtime_r(&t, &tm_buf);
		char buf[32];
		std::snprintf(buf, sizeof(buf), "%02d:%02d:%02d.000+00:00", tm_buf.tm_hour, tm_buf.tm_min, tm_buf.tm_sec);
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
		double n = toNumber(input[0]);
		return {FPValue::FromDecimal(std::exp(n))};
	}
	if (name == "ln") {
		if (input.empty()) return {};
		double n = toNumber(input[0]);
		if (n <= 0) return {};
		return {FPValue::FromDecimal(std::log(n))};
	}
	if (name == "log") {
		if (input.empty()) return {};
		if (node.children.empty()) return {};
		auto arg = evalArgIsolated(*node.children[0], input, doc);
		if (arg.empty()) return {};
		double val = toNumber(input[0]);
		double base = toNumber(arg[0]);
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

	// Single-argument functions
	if (!node.children.empty()) {
		if (name == "all") {
			return fn_all(*node.children[0], input, doc);
		}
		if (name == "select") {
			auto saved_vars = defined_variables_;
			auto saved_chain = chain_defined_vars_;
			chain_defined_vars_.clear();
			auto result = fn_select(*node.children[0], input, doc);
			defined_variables_ = saved_vars;
			chain_defined_vars_ = saved_chain;
			return result;
		}
		if (name == "repeat") {
			if (node.children.size() > 1) {
				throw std::runtime_error("repeat() takes exactly 1 argument");
			}
			return fn_repeat(*node.children[0], input, doc);
		}
		if (name == "repeatAll") {
			if (node.children.size() > 1) {
				throw std::runtime_error("repeatAll() takes exactly 1 argument");
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
					throw std::runtime_error("repeatAll() infinite loop detected");
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

		auto arg = evalArgIsolated(*node.children[0], input, doc);

		if (name == "is") {
			// .is(TypeName) - type name is passed as identifier, possibly qualified
			std::string type_name;
			// Reconstruct qualified name from member access chain (e.g. System.Patient)
			if (node.children[0]->type == NodeType::MemberAccess && node.children[0]->source) {
				// Walk the chain to build "Namespace.Type"
				std::string prefix;
				ASTNode *n = node.children[0]->source.get();
				while (n && n->type == NodeType::MemberAccess && n->source) {
					prefix = n->name + "." + prefix;
					n = n->source.get();
				}
				if (n && n->type == NodeType::MemberAccess) {
					prefix = n->name + "." + prefix;
				}
				type_name = prefix + node.children[0]->name;
			} else if (node.children[0]->type == NodeType::MemberAccess) {
				type_name = node.children[0]->name;
			} else if (!arg.empty()) {
				type_name = toString(arg[0]);
			}
			return fn_isType(input, type_name);
		}
		if (name == "as") {
			std::string type_name;
			if (node.children[0]->type == NodeType::MemberAccess && node.children[0]->source) {
				std::string prefix;
				ASTNode *n = node.children[0]->source.get();
				while (n && n->type == NodeType::MemberAccess && n->source) {
					prefix = n->name + "." + prefix;
					n = n->source.get();
				}
				if (n && n->type == NodeType::MemberAccess) {
					prefix = n->name + "." + prefix;
				}
				type_name = prefix + node.children[0]->name;
			} else if (node.children[0]->type == NodeType::MemberAccess) {
				type_name = node.children[0]->name;
			} else if (!arg.empty()) {
				type_name = toString(arg[0]);
			}
			return fn_asType(input, type_name);
		}

		if (name == "startsWith") {
			return fn_startsWith(input, arg);
		}
		if (name == "endsWith") {
			return fn_endsWith(input, arg);
		}
		if (name == "contains") {
			return fn_contains_fn(input, arg);
		}
		if (name == "matches") {
			return fn_matches(input, arg);
		}
		if (name == "matchesFull") {
			if (input.empty() || arg.empty()) return {};
			try {
				std::string s = toString(input[0]);
				std::string pattern = toString(arg[0]);
				const auto &re = get_cached_regex(pattern);
				return {FPValue::FromBoolean(std::regex_match(s, re))};
			} catch (const std::exception &) { return {}; }
		}
		if (name == "replaceMatches") {
			if (input.empty() || arg.empty()) return {};
			if (node.children.size() < 2) return {};
			auto sub_col = evalArgIsolated(*node.children[1], input, doc);
			if (sub_col.empty()) return {};  // empty substitution → empty result
			std::string s = toString(input[0]);
			std::string pattern = toString(arg[0]);
			std::string sub = toString(sub_col[0]);
			try {
				if (pattern.empty()) return {FPValue::FromString(s)};
				const auto &re = get_cached_regex(pattern);
				return {FPValue::FromString(std::regex_replace(s, re, sub))};
			} catch (const std::exception &) { return {FPValue::FromString(s)}; }
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
		if (name == "indexOf") {
			// indexOf(substring) → integer
			if (input.empty() || arg.empty()) {
				return {};
			}
			std::string s = toString(input[0]);
			std::string sub = toString(arg[0]);
			auto pos = s.find(sub);
			if (pos == std::string::npos) {
				return {FPValue::FromInteger(-1)};
			}
			return {FPValue::FromInteger(static_cast<int64_t>(pos))};
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

		if (name == "substring") {
			if (node.children.size() >= 2) {
				auto length_arg = evalArgIsolated(*node.children[1], input, doc);
				return fn_substring(input, arg, &length_arg);
			}
			return fn_substring(input, arg, nullptr);
		}
		if (name == "replace") {
			if (node.children.size() >= 2) {
				auto substitution = evalArgIsolated(*node.children[1], input, doc);
				return fn_replace(input, arg, substitution);
			}
			return {};
		}
		if (name == "iif") {
			if (node.children.size() >= 2) {
				return fn_iif(*node.children[0], *node.children[1],
				              node.children.size() >= 3 ? node.children[2].get() : nullptr, input, doc);
			}
			return {};
		}
		if (name == "aggregate") {
			return fn_aggregate(node, input, doc);
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
			if (!arg.empty()) {
				std::string var_name = toString(arg[0]);
				// Cannot overwrite system variables
				static const char* system_vars[] = {
					"context", "resource", "rootResource", "ucum", "sct", "loinc",
					"vs-administrative-gender", "ext-patient-birthTime", nullptr
				};
				for (int i = 0; system_vars[i]; ++i) {
					if (var_name == system_vars[i]) {
						throw std::runtime_error("Cannot overwrite system variable %" + var_name);
					}
				}
				// Check for redefinition in same chain
				if (chain_defined_vars_.count(var_name)) {
					throw std::runtime_error("Variable %" + var_name + " is already defined in this scope");
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
			}
			return input;
		}
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
		throw std::runtime_error("single() called on collection with multiple elements");
	}
	return {};
}

FPCollection Evaluator::fn_empty(const FPCollection &input) {
	return {FPValue::FromBoolean(input.empty())};
}

FPCollection Evaluator::fn_hasValue(const FPCollection &input) {
	return {FPValue::FromBoolean(!input.empty())};
}

FPCollection Evaluator::fn_not(const FPCollection &input) {
	if (input.empty()) {
		return {};
	}
	if (input.size() != 1) {
		return {};
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
		// Any single non-boolean value is truthy
		bool_val = true;
	}
	return {FPValue::FromBoolean(!bool_val)};
}

FPCollection Evaluator::fn_all(const ASTNode &criteria, const FPCollection &input, yyjson_doc *doc) {
	for (const auto &item : input) {
		FPCollection single = {item};
		auto result = eval(criteria, single, doc);
		if (!isTruthy(result)) {
			return {FPValue::FromBoolean(false)};
		}
	}
	return {FPValue::FromBoolean(true)};
}

FPCollection Evaluator::fn_allTrue(const FPCollection &input) {
	for (const auto &item : input) {
		bool is_true = false;
		if (item.type == FPValue::Type::Boolean) is_true = item.bool_val;
		else if (item.type == FPValue::Type::JsonVal && item.json_val && yyjson_is_bool(item.json_val))
			is_true = yyjson_get_bool(item.json_val);
		// Non-boolean items are not true
		if (!is_true) return {FPValue::FromBoolean(false)};
	}
	return {FPValue::FromBoolean(true)};
}

FPCollection Evaluator::fn_anyTrue(const FPCollection &input) {
	for (const auto &item : input) {
		bool is_true = false;
		if (item.type == FPValue::Type::Boolean) is_true = item.bool_val;
		else if (item.type == FPValue::Type::JsonVal && item.json_val && yyjson_is_bool(item.json_val))
			is_true = yyjson_get_bool(item.json_val);
		if (is_true) return {FPValue::FromBoolean(true)};
	}
	return {FPValue::FromBoolean(false)};
}

FPCollection Evaluator::fn_allFalse(const FPCollection &input) {
	for (const auto &item : input) {
		bool is_false = false;
		if (item.type == FPValue::Type::Boolean) is_false = !item.bool_val;
		else if (item.type == FPValue::Type::JsonVal && item.json_val && yyjson_is_bool(item.json_val))
			is_false = !yyjson_get_bool(item.json_val);
		// Non-boolean items are not false
		if (!is_false) return {FPValue::FromBoolean(false)};
	}
	return {FPValue::FromBoolean(true)};
}

FPCollection Evaluator::fn_anyFalse(const FPCollection &input) {
	for (const auto &item : input) {
		bool is_false = false;
		if (item.type == FPValue::Type::Boolean) is_false = !item.bool_val;
		else if (item.type == FPValue::Type::JsonVal && item.json_val && yyjson_is_bool(item.json_val))
			is_false = !yyjson_get_bool(item.json_val);
		if (is_false) return {FPValue::FromBoolean(true)};
	}
	return {FPValue::FromBoolean(false)};
}

FPCollection Evaluator::fn_startsWith(const FPCollection &input, const FPCollection &arg) {
	if (input.empty() || arg.empty()) {
		return {};
	}
	if (input.size() > 1) {
		throw std::runtime_error("startsWith() requires a single item input");
	}
	auto t = effectiveType(input[0]);
	if (t != FPValue::Type::String && input[0].type == FPValue::Type::JsonVal && input[0].json_val &&
	    yyjson_is_obj(input[0].json_val)) {
		throw std::runtime_error("startsWith() requires a string input, got complex type");
	}
	std::string s = toString(input[0]);
	std::string prefix = toString(arg[0]);
	return {FPValue::FromBoolean(s.size() >= prefix.size() && s.substr(0, prefix.size()) == prefix)};
}

FPCollection Evaluator::fn_endsWith(const FPCollection &input, const FPCollection &arg) {
	if (input.empty() || arg.empty()) {
		return {};
	}
	std::string s = toString(input[0]);
	std::string suffix = toString(arg[0]);
	return {FPValue::FromBoolean(s.size() >= suffix.size() &&
	                             s.substr(s.size() - suffix.size()) == suffix)};
}

FPCollection Evaluator::fn_contains_fn(const FPCollection &input, const FPCollection &arg) {
	if (input.empty() || arg.empty()) {
		return {};
	}
	std::string s = toString(input[0]);
	std::string sub = toString(arg[0]);
	return {FPValue::FromBoolean(s.find(sub) != std::string::npos)};
}

FPCollection Evaluator::fn_matches(const FPCollection &input, const FPCollection &arg) {
	if (input.empty() || arg.empty()) {
		return {};
	}
	try {
		std::string s = toString(input[0]);
		std::string pattern = toString(arg[0]);
		// FHIRPath matches uses DOTALL (dot matches newlines) per spec
		// std::regex doesn't have DOTALL; replace standalone '.' with [\s\S]
		std::string dotall_pattern;
		bool in_bracket = false;
		for (size_t i = 0; i < pattern.size(); ++i) {
			if (pattern[i] == '\\' && i + 1 < pattern.size()) {
				dotall_pattern += pattern[i];
				dotall_pattern += pattern[i + 1];
				++i;
			} else if (pattern[i] == '[') {
				in_bracket = true;
				dotall_pattern += pattern[i];
			} else if (pattern[i] == ']') {
				in_bracket = false;
				dotall_pattern += pattern[i];
			} else if (pattern[i] == '.' && !in_bracket) {
				dotall_pattern += "[\\s\\S]";
			} else {
				dotall_pattern += pattern[i];
			}
		}
		const auto &re2 = get_cached_regex(dotall_pattern);
		return {FPValue::FromBoolean(std::regex_search(s, re2))};
	} catch (const std::exception &) {
		return {};
	}
}

FPCollection Evaluator::fn_replace(const FPCollection &input, const FPCollection &pattern,
                                   const FPCollection &substitution) {
	if (input.empty() || pattern.empty() || substitution.empty()) {
		return {};
	}
	std::string s = toString(input[0]);
	std::string pat = toString(pattern[0]);
	std::string sub = substitution.empty() ? "" : toString(substitution[0]);
	if (pat.empty()) {
		// FHIRPath spec: replace with empty pattern inserts between each character
		std::string result;
		result += sub;
		for (size_t i = 0; i < s.size(); i++) {
			result += s[i];
			result += sub;
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
	if (input.empty() || start.empty()) {
		return {};
	}
	std::string s = toString(input[0]);
	int64_t start_idx = 0;
	if (start[0].type == FPValue::Type::Integer) {
		start_idx = start[0].int_val;
	} else {
		start_idx = static_cast<int64_t>(toNumber(start[0]));
	}

	// Negative start index → empty
	if (start_idx < 0) {
		return {};
	}
	// Start beyond string → empty
	if (static_cast<size_t>(start_idx) >= s.size()) {
		return {};
	}

	if (length && !length->empty()) {
		int64_t len = 0;
		if ((*length)[0].type == FPValue::Type::Integer) {
			len = (*length)[0].int_val;
		} else {
			len = static_cast<int64_t>(toNumber((*length)[0]));
		}
		if (len < 0) {
			return {};
		}
		return {FPValue::FromString(s.substr(static_cast<size_t>(start_idx), static_cast<size_t>(len)))};
	}
	return {FPValue::FromString(s.substr(static_cast<size_t>(start_idx)))};
}

FPCollection Evaluator::fn_length(const FPCollection &input) {
	if (input.empty()) {
		return {};
	}
	std::string s = toString(input[0]);
	return {FPValue::FromInteger(static_cast<int64_t>(s.size()))};
}

FPCollection Evaluator::fn_upper(const FPCollection &input) {
	if (input.empty()) {
		return {};
	}
	std::string s = toString(input[0]);
	std::transform(s.begin(), s.end(), s.begin(), [](unsigned char c) { return std::toupper(c); });
	return {FPValue::FromString(s)};
}

FPCollection Evaluator::fn_lower(const FPCollection &input) {
	if (input.empty()) {
		return {};
	}
	std::string s = toString(input[0]);
	std::transform(s.begin(), s.end(), s.begin(), [](unsigned char c) { return std::tolower(c); });
	return {FPValue::FromString(s)};
}

FPCollection Evaluator::fn_trim(const FPCollection &input) {
	if (input.empty()) {
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
		if (val.type == FPValue::Type::Integer) {
			return {val};
		}
		if (effectiveType(val) == FPValue::Type::Integer) {
			return {FPValue::FromInteger(static_cast<int64_t>(getNumericValue(val)))};
		}
		if (val.type == FPValue::Type::Boolean || effectiveType(val) == FPValue::Type::Boolean) {
			bool b = val.type == FPValue::Type::Boolean ? val.bool_val :
			         (val.json_val && yyjson_get_bool(val.json_val));
			return {FPValue::FromInteger(b ? 1 : 0)};
		}
		std::string s = toString(val);
		// Validate: must be a pure integer (optional sign + digits only)
		size_t idx = 0;
		long long result = std::stoll(s, &idx);
		if (idx != s.size()) return {};  // not all characters consumed
		return {FPValue::FromInteger(static_cast<int64_t>(result))};
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
		std::string s = toString(val);
		size_t idx = 0;
		double d = std::stod(s, &idx);
		if (idx != s.size()) return {};
		return {FPValue::FromDecimal(d)};
	} catch (const std::exception &) {
		return {};
	}
}

FPCollection Evaluator::fn_toString(const FPCollection &input) {
	if (input.empty()) {
		return {};
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
	std::string s = toString(input[0]);
	// Validate: must match YYYY(-MM(-DD)?)?
	if (s.size() >= 4 && std::isdigit((unsigned char)s[0]) && std::isdigit((unsigned char)s[1]) &&
	    std::isdigit((unsigned char)s[2]) && std::isdigit((unsigned char)s[3])) {
		// Could be a dateTime string - truncate to date part
		auto tpos = s.find('T');
		if (tpos != std::string::npos) s = s.substr(0, tpos);
		// Remove timezone if present on date-only
		for (size_t i = 4; i < s.size(); ++i) {
			if (s[i] == '+' || s[i] == 'Z' || (s[i] == '-' && i > 7)) {
				s = s.substr(0, i);
				break;
			}
		}
		FPValue v; v.type = FPValue::Type::Date; v.string_val = s;
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
		// Date → DateTime: just change the type
		FPValue v; v.type = FPValue::Type::DateTime; v.string_val = toString(input[0]);
		return {v};
	}
	std::string s = toString(input[0]);
	// Validate: must start with YYYY
	if (s.size() >= 4 && std::isdigit((unsigned char)s[0]) && std::isdigit((unsigned char)s[1]) &&
	    std::isdigit((unsigned char)s[2]) && std::isdigit((unsigned char)s[3])) {
		FPValue v; v.type = FPValue::Type::DateTime; v.string_val = s;
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
	std::string s = toString(val);
	if (s == "true" || s == "1") {
		return {FPValue::FromBoolean(true)};
	}
	if (s == "false" || s == "0") {
		return {FPValue::FromBoolean(false)};
	}
	return {};
}

FPCollection Evaluator::fn_toQuantity(const FPCollection &input) {
	if (input.empty()) {
		return {};
	}
	auto &val = input[0];
	if (val.type == FPValue::Type::Quantity) {
		return {val};
	}
	if (val.type == FPValue::Type::Integer) {
		FPValue v;
		v.type = FPValue::Type::Quantity;
		v.quantity_value = static_cast<double>(val.int_val);
		v.quantity_unit = "1";
		return {v};
	}
	if (val.type == FPValue::Type::Decimal) {
		FPValue v;
		v.type = FPValue::Type::Quantity;
		v.quantity_value = val.decimal_val;
		v.quantity_unit = "1";
		return {v};
	}
	if (val.type == FPValue::Type::Boolean) {
		FPValue v;
		v.type = FPValue::Type::Quantity;
		v.quantity_value = val.bool_val ? 1.0 : 0.0;
		v.quantity_unit = "1";
		return {v};
	}
	// String → Quantity: parse "number unit" format
	auto t = effectiveType(val);
	if (t == FPValue::Type::String) {
		std::string s = toString(val);
		// Try to parse as "number" or "number unit"
		size_t idx = 0;
		// Skip leading whitespace
		while (idx < s.size() && std::isspace((unsigned char)s[idx])) idx++;
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
		// Skip whitespace
		while (idx < s.size() && std::isspace((unsigned char)s[idx])) idx++;
		std::string unit_str;
		if (idx < s.size()) {
			// Parse unit: either 'quoted' or bare keyword
			if (s[idx] == '\'') {
				idx++; // skip opening quote
				size_t unit_start = idx;
				while (idx < s.size() && s[idx] != '\'') idx++;
				unit_str = s.substr(unit_start, idx - unit_start);
			} else {
				unit_str = s.substr(idx);
				// Trim trailing whitespace
				while (!unit_str.empty() && std::isspace((unsigned char)unit_str.back())) unit_str.pop_back();
			}
		} else {
			unit_str = "1";
		}
		FPValue v;
		v.type = FPValue::Type::Quantity;
		v.quantity_value = num_val;
		v.quantity_unit = unit_str;
		return {v};
	}
	return {};
}

FPCollection Evaluator::fn_abs(const FPCollection &input) {
	if (input.empty()) {
		return {};
	}
	auto &val = input[0];
	if (val.type == FPValue::Type::Integer) {
		return {FPValue::FromInteger(std::abs(val.int_val))};
	}
	if (val.type == FPValue::Type::Decimal) {
		return {FPValue::FromDecimal(std::abs(val.decimal_val))};
	}
	if (val.type == FPValue::Type::Quantity) {
		FPValue v;
		v.type = FPValue::Type::Quantity;
		v.quantity_value = std::abs(val.quantity_value);
		v.quantity_unit = val.quantity_unit;
		return {v};
	}
	double n = toNumber(val);
	return {FPValue::FromDecimal(std::abs(n))};
}

FPCollection Evaluator::fn_ceiling(const FPCollection &input) {
	if (input.empty()) {
		return {};
	}
	return {FPValue::FromInteger(static_cast<int64_t>(std::ceil(toNumber(input[0]))))};
}

FPCollection Evaluator::fn_floor(const FPCollection &input) {
	if (input.empty()) {
		return {};
	}
	return {FPValue::FromInteger(static_cast<int64_t>(std::floor(toNumber(input[0]))))};
}

FPCollection Evaluator::fn_round(const FPCollection &input, const FPCollection *precision) {
	if (input.empty()) {
		return {};
	}
	double val = toNumber(input[0]);
	int64_t prec = 0;
	if (precision && !precision->empty()) {
		prec = static_cast<int64_t>(toNumber((*precision)[0]));
	}
	double factor = std::pow(10.0, static_cast<double>(prec));
	return {FPValue::FromDecimal(std::round(val * factor) / factor)};
}

FPCollection Evaluator::fn_ln(const FPCollection &input) {
	if (input.empty()) {
		return {};
	}
	double val = toNumber(input[0]);
	if (val <= 0) {
		return {};
	}
	return {FPValue::FromDecimal(std::log(val))};
}

FPCollection Evaluator::fn_log(const FPCollection &input, const FPCollection &base) {
	if (input.empty() || base.empty()) {
		return {};
	}
	double val = toNumber(input[0]);
	double b = toNumber(base[0]);
	if (val <= 0 || b <= 0 || b == 1.0) {
		return {};
	}
	return {FPValue::FromDecimal(std::log(val) / std::log(b))};
}

FPCollection Evaluator::fn_power(const FPCollection &input, const FPCollection &exponent) {
	if (input.empty() || exponent.empty()) {
		return {};
	}
	double base = toNumber(input[0]);
	double exp = toNumber(exponent[0]);
	double result = std::pow(base, exp);
	if (std::isnan(result) || std::isinf(result)) {
		return {};
	}
	return {FPValue::FromDecimal(result)};
}

FPCollection Evaluator::fn_sqrt(const FPCollection &input) {
	if (input.empty()) {
		return {};
	}
	double val = toNumber(input[0]);
	if (val < 0) {
		return {};
	}
	return {FPValue::FromDecimal(std::sqrt(val))};
}

FPCollection Evaluator::fn_truncate(const FPCollection &input) {
	if (input.empty()) {
		return {};
	}
	return {FPValue::FromInteger(static_cast<int64_t>(toNumber(input[0])))};
}

FPCollection Evaluator::fn_iif(const ASTNode &criterion, const ASTNode &trueResult, const ASTNode *falseResult,
                               const FPCollection &input, yyjson_doc *doc) {
	// FHIRPath spec: if input collection has more than one item, return empty
	if (input.size() > 1) return {};
	auto cond = eval(criterion, input, doc);
	// If criterion has more than one item, it's an error → return empty
	if (cond.size() > 1) return {};
	if (cond.size() == 1 && isTruthy(cond)) {
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
	std::vector<std::string> seen;

	// Mark initial input as seen but don't add to result yet
	FPCollection work = input;
	for (const auto &item : input) {
		seen.push_back(toString(item));
	}

	// Track type tags of input and produced items for seed inclusion decision
	bool input_all_numeric_temporal = true;
	bool produced_all_numeric_temporal = true;
	bool has_produced = false;
	for (const auto &item : input) {
		auto t = effectiveType(item);
		if (t != FPValue::Type::Integer && t != FPValue::Type::Decimal &&
		    t != FPValue::Type::Date && t != FPValue::Type::DateTime &&
		    t != FPValue::Type::Time && t != FPValue::Type::Quantity) {
			input_all_numeric_temporal = false;
			break;
		}
	}

	size_t iterations = 0;
	while (!work.empty()) {
		FPCollection next;
		for (const auto &item : work) {
			FPCollection single_col = {item};
			auto projected = eval(projection, single_col, doc);
			for (const auto &p : projected) {
				std::string key = toString(p);
				if (std::find(seen.begin(), seen.end(), key) == seen.end()) {
					seen.push_back(key);
					result.push_back(p);
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
				}
			}
		}
		work = next;
		if (++iterations > 1000 || result.size() > 10000) {
			throw std::runtime_error("repeat() infinite loop detected");
		}
	}

	// Include seeds (input) only for numeric/temporal/quantity sequences
	if (input_all_numeric_temporal && produced_all_numeric_temporal && has_produced) {
		FPCollection final_result;
		std::vector<std::string> final_seen;
		for (const auto &item : input) {
			std::string key = toString(item);
			if (std::find(final_seen.begin(), final_seen.end(), key) == final_seen.end()) {
				final_seen.push_back(key);
				final_result.push_back(item);
			}
		}
		for (const auto &item : result) {
			final_result.push_back(item);
		}
		return final_result;
	}
	return result;
}

FPCollection Evaluator::fn_distinct(const FPCollection &input) {
	FPCollection result;
	std::vector<std::string> seen;
	for (const auto &item : input) {
		std::string s = toString(item);
		if (std::find(seen.begin(), seen.end(), s) == seen.end()) {
			seen.push_back(s);
			result.push_back(item);
		}
	}
	return result;
}

FPCollection Evaluator::fn_trace(const FPCollection &input) {
	return input;
}

FPCollection Evaluator::fn_aggregate(const ASTNode &node, const FPCollection &input, yyjson_doc *doc) {
	// aggregate(aggregator [, init])
	if (node.children.empty()) {
		return {};
	}
	FPCollection saved_total = total_context_;
	int64_t saved_index = index_context_;

	if (node.children.size() >= 2) {
		total_context_ = eval(*node.children[1], input, doc);
	} else {
		total_context_ = {};
	}

	for (size_t i = 0; i < input.size(); i++) {
		index_context_ = static_cast<int64_t>(i);
		FPCollection single = {input[i]};
		total_context_ = eval(*node.children[0], single, doc);
	}

	FPCollection result = total_context_;
	total_context_ = saved_total;
	index_context_ = saved_index;
	return result;
}

FPCollection Evaluator::fn_combine(const FPCollection &input, const FPCollection &other) {
	FPCollection result = input;
	result.insert(result.end(), other.begin(), other.end());
	return result;
}

FPCollection Evaluator::fn_union(const FPCollection &left, const FPCollection &right) {
	FPCollection result;
	// Deduplicate left side first
	for (const auto &item : left) {
		std::string s = toString(item);
		bool found = false;
		for (const auto &existing : result) {
			if (toString(existing) == s) { found = true; break; }
		}
		if (!found) result.push_back(item);
	}
	// Add right side elements not already present
	for (const auto &item : right) {
		std::string s = toString(item);
		bool found = false;
		for (const auto &existing : result) {
			if (toString(existing) == s) { found = true; break; }
		}
		if (!found) result.push_back(item);
	}
	return result;
}

FPCollection Evaluator::fn_intersect(const FPCollection &input, const FPCollection &other) {
	FPCollection result;
	for (const auto &item : input) {
		std::string s = toString(item);
		// Check if already in result (dedup)
		bool dup = false;
		for (const auto &r : result) {
			if (toString(r) == s) { dup = true; break; }
		}
		if (dup) continue;
		// Check if in other collection
		for (const auto &o : other) {
			if (toString(o) == s) {
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
		std::string s = toString(item);
		bool found = false;
		for (const auto &o : other) {
			if (toString(o) == s) {
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
	if (input.empty() || count.empty()) {
		return {};
	}
	int64_t n = static_cast<int64_t>(toNumber(count[0]));
	if (n <= 0) {
		return {};
	}
	size_t take_n = std::min(static_cast<size_t>(n), input.size());
	return FPCollection(input.begin(), input.begin() + static_cast<ptrdiff_t>(take_n));
}

FPCollection Evaluator::fn_skip(const FPCollection &input, const FPCollection &count) {
	if (input.empty() || count.empty()) {
		return {};
	}
	int64_t n = static_cast<int64_t>(toNumber(count[0]));
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
	if (col.size() > 1) return false; // multi-element → not convertible
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
struct DateTimeParts {
	int year, month, day, hour, minute, second, millisecond;
	int tz_offset_minutes; // offset from UTC in minutes, INT_MIN if no TZ
	int precision; // 1=year,2=month,3=day,4=hour,5=minute,6=second,7=millisecond
	bool valid;
};

static DateTimeParts parseDateTimeParts(const std::string &s) {
	DateTimeParts p;
	p.year = p.month = p.day = p.hour = p.minute = p.second = p.millisecond = 0;
	p.tz_offset_minutes = INT_MIN;
	p.precision = 0;
	p.valid = false;

	if (s.empty()) return p;
	const char *c = s.c_str();

	// Parse year
	if (std::sscanf(c, "%d", &p.year) != 1) return p;
	p.precision = 1;
	p.valid = true;
	if (s.size() <= 4) return p;
	if (s[4] != '-') return p;

	// Parse month
	if (std::sscanf(c + 5, "%d", &p.month) != 1) return p;
	p.precision = 2;
	if (s.size() <= 7) return p;
	if (s[7] != '-') return p;

	// Parse day
	if (std::sscanf(c + 8, "%d", &p.day) != 1) return p;
	p.precision = 3;
	if (s.size() <= 10) return p;
	if (s[10] != 'T') return p;

	// Parse hour
	if (s.size() < 13) return p;
	if (std::sscanf(c + 11, "%d", &p.hour) != 1) return p;
	p.precision = 4;
	if (s.size() <= 13 || s[13] != ':') {
		// ISO 8601: T08 implies T08:00 (minute-level precision with minute=0)
		p.minute = 0;
		p.precision = 5;
		return p;
	}

	// Parse minute
	if (s.size() < 16) return p;
	if (std::sscanf(c + 14, "%d", &p.minute) != 1) return p;
	p.precision = 5;
	if (s.size() <= 16 || s[16] != ':') return p;

	// Parse second
	if (s.size() < 19) return p;
	if (std::sscanf(c + 17, "%d", &p.second) != 1) return p;
	p.precision = 6;

	size_t pos = 19;
	if (pos < s.size() && s[pos] == '.') {
		pos++;
		std::string ms_str;
		while (pos < s.size() && std::isdigit(static_cast<unsigned char>(s[pos]))) {
			ms_str += s[pos++];
		}
		while (ms_str.size() < 3) ms_str += '0';
		p.millisecond = std::atoi(ms_str.substr(0, 3).c_str());
		p.precision = 7;
	}

	// Parse timezone
	if (pos < s.size()) {
		if (s[pos] == 'Z') {
			p.tz_offset_minutes = 0;
		} else if (s[pos] == '+' || s[pos] == '-') {
			int sign = (s[pos] == '+') ? 1 : -1;
			int tz_h = 0, tz_m = 0;
			if (pos + 3 <= s.size()) {
				(void)std::sscanf(c + pos + 1, "%d", &tz_h);
			}
			if (pos + 6 <= s.size() && s[pos + 3] == ':') {
				(void)std::sscanf(c + pos + 4, "%d", &tz_m);
			}
			p.tz_offset_minutes = sign * (tz_h * 60 + tz_m);
		}
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
	const char *c = s.c_str();
	size_t pos = 0;
	if (s[0] == 'T') pos = 1;

	if (pos + 2 > s.size()) return p;
	p.hour = std::atoi(s.substr(pos, 2).c_str());
	p.precision = 4;
	p.valid = true;
	pos += 2;

	if (pos >= s.size() || s[pos] != ':') return p;
	pos++;
	if (pos + 2 > s.size()) return p;
	p.minute = std::atoi(s.substr(pos, 2).c_str());
	p.precision = 5;
	pos += 2;

	if (pos >= s.size() || s[pos] != ':') return p;
	pos++;
	if (pos + 2 > s.size()) return p;
	p.second = std::atoi(s.substr(pos, 2).c_str());
	p.precision = 6;
	pos += 2;

	if (pos < s.size() && s[pos] == '.') {
		pos++;
		std::string ms_str;
		while (pos < s.size() && std::isdigit(static_cast<unsigned char>(s[pos]))) {
			ms_str += s[pos++];
		}
		while (ms_str.size() < 3) ms_str += '0';
		p.millisecond = std::atoi(ms_str.substr(0, 3).c_str());
		p.precision = 7;
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
		std::string l_str = left.empty() ? "" : toString(left[0]);
		std::string r_str = right.empty() ? "" : toString(right[0]);
		return {FPValue::FromString(l_str + r_str)};
	}

	// Membership operators
	if (op == "in") {
		if (left.empty()) return {};
		if (left.size() > 1) return {};
		// Single element in empty collection → false
		if (right.empty()) return {FPValue::FromBoolean(false)};
		std::string needle = toString(left[0]);
		for (const auto &item : right) {
			if (toString(item) == needle) {
				return {FPValue::FromBoolean(true)};
			}
		}
		return {FPValue::FromBoolean(false)};
	}
	if (op == "contains") {
		if (right.empty()) return {};
		if (right.size() > 1) return {};
		// Empty collection contains single element → false
		if (left.empty()) return {FPValue::FromBoolean(false)};
		std::string needle = toString(right[0]);
		for (const auto &item : left) {
			if (toString(item) == needle) {
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
		if ((left.size() == 1 && left[0].type == FPValue::Type::Quantity) ||
		    (right.size() == 1 && right[0].type == FPValue::Type::Quantity)) {
			maybeConvertQuantity(left);
			maybeConvertQuantity(right);
		}
	}

	// Equality
	if (op == "=" || op == "~" || op == "!=" || op == "!~") {
		bool is_equiv = (op == "~" || op == "!~");
		// Multi-element collection comparison
		if (left.size() > 1 || right.size() > 1) {
			if (left.size() != right.size()) {
				if (is_equiv) return {FPValue::FromBoolean(op == "!~")};
				// For =, if sizes differ, result is false
				return {FPValue::FromBoolean(op == "!=")};
			}
			if (is_equiv) {
				// Equivalence: compare as sets (same elements regardless of order)
				std::vector<bool> matched(right.size(), false);
				bool all_match = true;
				for (size_t i = 0; i < left.size(); ++i) {
					bool found = false;
					std::string ls = toString(left[i]);
					std::transform(ls.begin(), ls.end(), ls.begin(), ::tolower);
					for (size_t j = 0; j < right.size(); ++j) {
						if (!matched[j]) {
							std::string rs = toString(right[j]);
							std::transform(rs.begin(), rs.end(), rs.begin(), ::tolower);
							if (ls == rs) {
								matched[j] = true;
								found = true;
								break;
							}
						}
					}
					if (!found) { all_match = false; break; }
				}
				return {FPValue::FromBoolean(op == "~" ? all_match : !all_match)};
			} else {
				// Equality: ordered element-by-element comparison
				bool all_eq = true;
				for (size_t i = 0; i < left.size(); ++i) {
					if (toString(left[i]) != toString(right[i])) { all_eq = false; break; }
				}
				return {FPValue::FromBoolean(op == "=" ? all_eq : !all_eq)};
			}
		}

		auto &lv = left[0];
		auto &rv = right[0];
		bool is_eq = false;

		// Date/time equality with precision
		if (isDateTimeType(lv) && isDateTimeType(rv)) {
			auto lt = effectiveType(lv);
			auto rt = effectiveType(rv);
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
					is_eq = (std::abs(l_conv - r_conv) < 1e-10);
				}
			} else {
				// Incompatible units: return empty for = and !=
				if (op == "=" || op == "!=") return {};
				is_eq = false;
			}
		} else if (is_equiv && effectiveType(lv) == FPValue::Type::String && effectiveType(rv) == FPValue::Type::String) {
			// Equivalence: case-insensitive string comparison
			std::string ls = toString(lv), rs = toString(rv);
			std::transform(ls.begin(), ls.end(), ls.begin(), ::tolower);
			std::transform(rs.begin(), rs.end(), rs.begin(), ::tolower);
			is_eq = (ls == rs);
		} else {
			is_eq = (toString(lv) == toString(rv));
		}

		if (op == "=" || op == "~") return {FPValue::FromBoolean(is_eq)};
		return {FPValue::FromBoolean(!is_eq)};
	}

	// Comparison
	if (op == "<" || op == ">" || op == "<=" || op == ">=") {
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
			std::string l_base, r_base;
			double l_conv = convertQuantityToBase(lv.quantity_value, lv.quantity_unit, l_base);
			double r_conv = convertQuantityToBase(rv.quantity_value, rv.quantity_unit, r_base);
			if (l_base != r_base) return {};
			if (op == "<") return {FPValue::FromBoolean(l_conv < r_conv)};
			if (op == ">") return {FPValue::FromBoolean(l_conv > r_conv)};
			if (op == "<=") return {FPValue::FromBoolean(l_conv <= r_conv)};
			return {FPValue::FromBoolean(l_conv >= r_conv)};
		}

		// Numeric comparison (handle JSON values stored as strings)
		double l_num, r_num;
		bool l_numeric = false, r_numeric = false;
		if (isNumericType(lv)) { l_num = getNumericValue(lv); l_numeric = true; }
		else if (effectiveType(lv) == FPValue::Type::String) {
			std::string s = toString(lv);
			char *end = nullptr;
			l_num = std::strtod(s.c_str(), &end);
			if (end && end != s.c_str() && *end == '\0') l_numeric = true;
		}
		if (isNumericType(rv)) { r_num = getNumericValue(rv); r_numeric = true; }
		else if (effectiveType(rv) == FPValue::Type::String) {
			std::string s = toString(rv);
			char *end = nullptr;
			r_num = std::strtod(s.c_str(), &end);
			if (end && end != s.c_str() && *end == '\0') r_numeric = true;
		}
		if (l_numeric && r_numeric) {
			if (op == "<") return {FPValue::FromBoolean(l_num < r_num)};
			if (op == ">") return {FPValue::FromBoolean(l_num > r_num)};
			if (op == "<=") return {FPValue::FromBoolean(l_num <= r_num)};
			return {FPValue::FromBoolean(l_num >= r_num)};
		}
		// One numeric, one not → incompatible
		if (l_numeric || r_numeric) return {};

		// String comparison - only between same types
		auto lt = effectiveType(lv);
		auto rt = effectiveType(rv);
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
		    (effectiveType(lv) == FPValue::Type::Date || effectiveType(lv) == FPValue::Type::DateTime ||
		     effectiveType(lv) == FPValue::Type::Time) &&
		    rv.type == FPValue::Type::Quantity) {
			return fn_dateArith(lv, rv, op == "-");
		}
		// quantity + date/time (reversed)
		if (op == "+" &&
		    lv.type == FPValue::Type::Quantity &&
		    (effectiveType(rv) == FPValue::Type::Date || effectiveType(rv) == FPValue::Type::DateTime ||
		     effectiveType(rv) == FPValue::Type::Time)) {
			return fn_dateArith(rv, lv, false);
		}

		// Quantity arithmetic
		if (lv.type == FPValue::Type::Quantity && rv.type == FPValue::Type::Quantity) {
			if (op == "+" || op == "-") {
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
					// Same unit cancels out → decimal
					return {FPValue::FromDecimal(result_val)};
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
				} else {
					qval = rv.quantity_value; qunit = rv.quantity_unit; nval = getNumericValue(lv);
				}
				FPValue v; v.type = FPValue::Type::Quantity; v.quantity_unit = qunit;
				if (op == "*") { v.quantity_value = qval * nval; }
				else { if (nval == 0) return {}; v.quantity_value = qval / nval; }
				return {v};
			}
		}

		if (!isNumericType(lv) || !isNumericType(rv)) {
			return {};
		}

		double l_num = getNumericValue(lv);
		double r_num = getNumericValue(rv);
		double result = 0;

		if (op == "+") result = l_num + r_num;
		else if (op == "-") result = l_num - r_num;
		else if (op == "*") result = l_num * r_num;
		else if (op == "/") {
			if (r_num == 0) return {};
			result = l_num / r_num;
		} else if (op == "div") {
			if (r_num == 0) return {};
			result = std::floor(l_num / r_num);
		} else if (op == "mod") {
			if (r_num == 0) return {};
			result = std::fmod(l_num, r_num);
		}

		// Preserve integer type if both inputs are integer
		bool l_int = (effectiveType(lv) == FPValue::Type::Integer);
		bool r_int = (effectiveType(rv) == FPValue::Type::Integer);
		if (l_int && r_int && op != "/") {
			return {FPValue::FromInteger(static_cast<int64_t>(result))};
		}
		return {FPValue::FromDecimal(result)};
	}

	return {};
}

FPCollection Evaluator::evalUnaryOp(const ASTNode &node, const FPCollection &input, yyjson_doc *doc) {
	auto operand = eval(*node.children[0], input, doc);
	if (operand.empty()) {
		return {};
	}
	if (node.op == "-") {
		if (operand[0].type == FPValue::Type::Integer) {
			return {FPValue::FromInteger(-operand[0].int_val)};
		}
		if (operand[0].type == FPValue::Type::Decimal) {
			return {FPValue::FromDecimal(-operand[0].decimal_val)};
		}
		if (operand[0].type == FPValue::Type::Quantity) {
			FPValue v;
			v.type = FPValue::Type::Quantity;
			v.quantity_value = -operand[0].quantity_value;
			v.quantity_unit = operand[0].quantity_unit;
			return {v};
		}
		throw std::runtime_error("Unary - applied to non-numeric type");
	}
	if (node.op == "+") {
		if (operand[0].type != FPValue::Type::Integer && operand[0].type != FPValue::Type::Decimal &&
		    operand[0].type != FPValue::Type::Quantity) {
			throw std::runtime_error("Unary + applied to non-numeric type");
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
		std::ostringstream oss;
		oss << val.decimal_val;
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
		return val.int_val != 0;
	case FPValue::Type::String: {
		if (val.string_val == "true" || val.string_val == "1") {
			return true;
		}
		return false;
	}
	case FPValue::Type::JsonVal:
		if (val.json_val) {
			if (yyjson_is_bool(val.json_val)) {
				return yyjson_get_bool(val.json_val);
			}
			if (yyjson_is_str(val.json_val)) {
				std::string s = yyjson_get_str(val.json_val);
				return s == "true" || s == "1";
			}
		}
		return false;
	default:
		return false;
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
		    lower == "y" || lower == "n") {
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
	if (t == FPValue::Type::Integer) return {FPValue::FromBoolean(true)};
	if (t == FPValue::Type::Boolean) return {FPValue::FromBoolean(true)};
	if (t == FPValue::Type::String) {
		std::string s = toString(val);
		try {
			size_t pos;
			std::stoll(s, &pos);
			if (pos == s.size()) return {FPValue::FromBoolean(true)};
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
		try {
			size_t pos;
			std::stod(s, &pos);
			if (pos == s.size()) return {FPValue::FromBoolean(true)};
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
		// Check if it looks like a date: YYYY, YYYY-MM, or YYYY-MM-DD
		if (s.size() >= 4 && std::isdigit(static_cast<unsigned char>(s[0]))) {
			DateTimeParts p = parseDateTimeParts(s);
			if (p.valid && p.precision >= 1 && p.precision <= 3) return {FPValue::FromBoolean(true)};
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
			if (p.valid) return {FPValue::FromBoolean(true)};
		}
		return {FPValue::FromBoolean(false)};
	}
	return {FPValue::FromBoolean(false)};
}

FPCollection Evaluator::fn_convertsToQuantity(const FPCollection &input) {
	if (input.empty() || input.size() != 1) return {};
	auto &val = input[0];
	auto t = effectiveType(val);
	if (t == FPValue::Type::Quantity) return {FPValue::FromBoolean(true)};
	if (t == FPValue::Type::Integer || t == FPValue::Type::Decimal) return {FPValue::FromBoolean(true)};
	if (t == FPValue::Type::Boolean) return {FPValue::FromBoolean(true)};
	if (t == FPValue::Type::String) {
		std::string s = toString(val);
		// Parse number carefully
		size_t idx = 0;
		while (idx < s.size() && std::isspace((unsigned char)s[idx])) idx++;
		size_t num_start = idx;
		if (idx < s.size() && (s[idx] == '+' || s[idx] == '-')) idx++;
		bool has_digit = false;
		while (idx < s.size() && std::isdigit((unsigned char)s[idx])) { idx++; has_digit = true; }
		if (idx < s.size() && s[idx] == '.') {
			idx++;
			bool has_frac = false;
			while (idx < s.size() && std::isdigit((unsigned char)s[idx])) { idx++; has_frac = true; }
			if (!has_frac) return {FPValue::FromBoolean(false)};
		}
		if (!has_digit) return {FPValue::FromBoolean(false)};
		while (idx < s.size() && std::isspace((unsigned char)s[idx])) idx++;
		if (idx >= s.size()) return {FPValue::FromBoolean(true)};
		// Check for UCUM unit in quotes
		if (s[idx] == '\'') {
			auto end_quote = s.find('\'', idx + 1);
			if (end_quote != std::string::npos && end_quote == s.size() - 1) {
				return {FPValue::FromBoolean(true)};
			}
		}
		// Accept FHIRPath time unit keywords
		std::string remaining = s.substr(idx);
		while (!remaining.empty() && std::isspace((unsigned char)remaining.back())) remaining.pop_back();
		static const char* valid_keywords[] = {
			"year", "years", "month", "months", "week", "weeks", "day", "days",
			"hour", "hours", "minute", "minutes", "second", "seconds",
			"millisecond", "milliseconds", nullptr
		};
		for (int i = 0; valid_keywords[i]; ++i) {
			if (remaining == valid_keywords[i]) return {FPValue::FromBoolean(true)};
		}
		return {FPValue::FromBoolean(false)};
	}
	return {FPValue::FromBoolean(false)};
}

// --- Phase 4: is()/as() type operations ---

FPCollection Evaluator::fn_isType(const FPCollection &input, const std::string &type_name, bool exact) {
	if (input.empty()) return {};
	auto &val = input[0];

	// Parse namespace from qualified type name (e.g., "FHIR.boolean", "System.Boolean")
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
		static const char* system_types[] = {
			"Boolean", "Integer", "Decimal", "String", "Date", "DateTime", "Time", "Quantity", nullptr
		};
		bool is_system = false;
		for (int i = 0; system_types[i]; ++i) {
			if (target == system_types[i]) { is_system = true; break; }
		}
		if (is_system) {
			ns = "System";
		} else if (!target.empty() && std::islower(static_cast<unsigned char>(target[0]))) {
			ns = "FHIR";
		} else {
			ns = "FHIR";
		}
	}

	auto t = effectiveType(val);
	bool is_fhir = (val.type == FPValue::Type::JsonVal);

	// Check fhir_type from choice type resolution first
	if (!val.fhir_type.empty()) {
		if (ns == "FHIR" || ns == "System") {
			// Case-insensitive compare (fhir_type is capitalized suffix like "Integer", target may be "integer")
			std::string ft_lower = val.fhir_type;
			std::string tg_lower = target;
			for (auto &c : ft_lower) c = std::tolower(static_cast<unsigned char>(c));
			for (auto &c : tg_lower) c = std::tolower(static_cast<unsigned char>(c));
			if (ft_lower == tg_lower) return {FPValue::FromBoolean(true)};
			// Subtypes can match parent (only in non-exact mode)
			if (!exact) {
				if ((val.fhir_type == "Age" || val.fhir_type == "Duration" ||
				     val.fhir_type == "SimpleQuantity" || val.fhir_type == "MoneyQuantity") &&
				    target == "Quantity") {
					return {FPValue::FromBoolean(true)};
				}
			}
			// uuid is a subtype of uri
			if (!exact && ft_lower == "uuid" && tg_lower == "uri") {
				return {FPValue::FromBoolean(true)};
			}
		}
	}

	// System type checks
	if (ns == "System") {
		if (!is_fhir) {
			if (target == "Boolean") return {FPValue::FromBoolean(t == FPValue::Type::Boolean)};
			if (target == "Integer") return {FPValue::FromBoolean(t == FPValue::Type::Integer)};
			if (target == "Decimal") return {FPValue::FromBoolean(t == FPValue::Type::Decimal)};
			if (target == "String") return {FPValue::FromBoolean(t == FPValue::Type::String)};
			if (target == "Date") return {FPValue::FromBoolean(t == FPValue::Type::Date)};
			if (target == "DateTime") return {FPValue::FromBoolean(t == FPValue::Type::DateTime)};
			if (target == "Time") return {FPValue::FromBoolean(t == FPValue::Type::Time)};
			if (target == "Quantity") return {FPValue::FromBoolean(t == FPValue::Type::Quantity)};
		}
		return {FPValue::FromBoolean(false)};
	}

	// FHIR type checks
	if (ns == "FHIR") {
		// FHIR resource types - check resourceType
		if (val.type == FPValue::Type::JsonVal && val.json_val && yyjson_is_obj(val.json_val)) {
			yyjson_val *rt = yyjson_obj_get(val.json_val, "resourceType");
			if (rt && yyjson_is_str(rt)) {
				std::string actual_type = yyjson_get_str(rt);
				if (actual_type == target) return {FPValue::FromBoolean(true)};
			}

			// FHIR complex types - detect by structure (only if no fhir_type is set)
			if (val.fhir_type.empty()) {
				if (target == "Quantity" || target == "SimpleQuantity" || target == "MoneyQuantity" ||
				    target == "Age" || target == "Duration") {
					yyjson_val *qval = yyjson_obj_get(val.json_val, "value");
					yyjson_val *qunit = yyjson_obj_get(val.json_val, "unit");
					yyjson_val *qcode = yyjson_obj_get(val.json_val, "code");
					if (qval || qunit || qcode) return {FPValue::FromBoolean(true)};
				}
				if (target == "HumanName") {
					yyjson_val *family = yyjson_obj_get(val.json_val, "family");
					yyjson_val *given = yyjson_obj_get(val.json_val, "given");
					yyjson_val *use = yyjson_obj_get(val.json_val, "use");
					if (family || given || use) return {FPValue::FromBoolean(true)};
				}
				if (target == "Coding") {
					yyjson_val *sys = yyjson_obj_get(val.json_val, "system");
					yyjson_val *code = yyjson_obj_get(val.json_val, "code");
					if (sys || code) return {FPValue::FromBoolean(true)};
				}
				if (target == "Period") {
					yyjson_val *start = yyjson_obj_get(val.json_val, "start");
					yyjson_val *end = yyjson_obj_get(val.json_val, "end");
					if (start || end) return {FPValue::FromBoolean(true)};
				}
			}
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
						// Exact: only match if actual type IS string (not code/uri/id)
						if (!actual_type || std::string(actual_type) == "string") return {FPValue::FromBoolean(true)};
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
			if (target == "date") return {FPValue::FromBoolean(t == FPValue::Type::Date)};
			if (target == "dateTime" || target == "instant") return {FPValue::FromBoolean(t == FPValue::Type::DateTime)};
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
	if (input.empty()) return {};
	if (input.size() > 1) return {};

	// as() uses exact type matching
	auto is_result = fn_isType(input, type_name, true);
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
	std::string s = toString(val);
	if (s.size() >= 2) {
		FPValue v;
		v.type = FPValue::Type::Time;
		v.string_val = s;
		return {v};
	}
	return {};
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

	double d = (val.type == FPValue::Type::Integer) ? static_cast<double>(val.int_val) : val.decimal_val;
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
		if (s.size() >= 4 && std::isdigit((unsigned char)s[0]) && std::isdigit((unsigned char)s[1]) &&
		    std::isdigit((unsigned char)s[2]) && std::isdigit((unsigned char)s[3])) {
			FPValue date_val;
			if (s.find('T') != std::string::npos) {
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
		// Default behavior (no precision arg) - return at maximum precision (DateTime)
		if (t == FPValue::Type::Date) {
			std::string result = formatDateTimeBoundary(p, 17, false, "", false);
			FPValue v; v.type = FPValue::Type::DateTime; v.string_val = result; return {v};
		}
		// DateTime default
		std::ostringstream oss;
		oss << std::setfill('0') << std::setw(4) << p.year
		    << "-" << std::setfill('0') << std::setw(2) << (p.precision >= 2 ? p.month : 1)
		    << "-" << std::setfill('0') << std::setw(2) << (p.precision >= 3 ? p.day : 1)
		    << "T" << std::setfill('0') << std::setw(2) << (p.precision >= 4 ? p.hour : 0)
		    << ":" << std::setfill('0') << std::setw(2) << (p.precision >= 5 ? p.minute : 0)
		    << ":" << std::setfill('0') << std::setw(2) << 0
		    << "." << std::setfill('0') << std::setw(3) << 0;
		FPValue v; v.type = FPValue::Type::DateTime; v.string_val = oss.str(); return {v};
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
		if (s.size() >= 4 && std::isdigit((unsigned char)s[0]) && std::isdigit((unsigned char)s[1]) &&
		    std::isdigit((unsigned char)s[2]) && std::isdigit((unsigned char)s[3])) {
			FPValue date_val;
			if (s.find('T') != std::string::npos) {
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
		// Default (no precision arg) - return at maximum precision (DateTime)
		if (t == FPValue::Type::Date) {
			std::string result = formatDateTimeBoundary(p, 17, true, "", false);
			FPValue v; v.type = FPValue::Type::DateTime; v.string_val = result; return {v};
		}
		// DateTime default
		int max_month = 12, max_hour = 23, max_minute = 59;
		int days_in_month[] = {31,28,31,30,31,30,31,31,30,31,30,31};
		bool leap = (p.year % 4 == 0 && (p.year % 100 != 0 || p.year % 400 == 0));
		if (leap) days_in_month[1] = 29;
		int use_month = (p.precision >= 2) ? p.month : max_month;
		int max_day = (use_month >= 1 && use_month <= 12) ? days_in_month[use_month - 1] : 31;
		std::ostringstream oss;
		oss << std::setfill('0') << std::setw(4) << p.year
		    << "-" << std::setfill('0') << std::setw(2) << (p.precision >= 2 ? p.month : max_month)
		    << "-" << std::setfill('0') << std::setw(2) << (p.precision >= 3 ? p.day : max_day)
		    << "T" << std::setfill('0') << std::setw(2) << (p.precision >= 4 ? p.hour : max_hour)
		    << ":" << std::setfill('0') << std::setw(2) << (p.precision >= 5 ? p.minute : max_minute)
		    << ":59.999";
		FPValue v; v.type = FPValue::Type::DateTime; v.string_val = oss.str(); return {v};
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
	FPCollection current = fn_children(input);
	size_t depth = 0;
	while (!current.empty() && depth < 100) {
		result.insert(result.end(), current.begin(), current.end());
		current = fn_children(current);
		depth++;
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
	std::vector<std::string> seen;
	for (const auto &item : input) {
		std::string s = toString(item);
		if (std::find(seen.begin(), seen.end(), s) != seen.end()) {
			return {FPValue::FromBoolean(false)};
		}
		seen.push_back(s);
	}
	return {FPValue::FromBoolean(true)};
}

FPCollection Evaluator::fn_subsetOf(const FPCollection &input, const FPCollection &other) {
	for (const auto &item : input) {
		std::string s = toString(item);
		bool found = false;
		for (const auto &o : other) {
			if (toString(o) == s) { found = true; break; }
		}
		if (!found) return {FPValue::FromBoolean(false)};
	}
	return {FPValue::FromBoolean(true)};
}

FPCollection Evaluator::fn_supersetOf(const FPCollection &input, const FPCollection &other) {
	return fn_subsetOf(other, input);
}

// --- Date arithmetic ---

static bool isLeapYear(int y) {
	return (y % 4 == 0 && y % 100 != 0) || (y % 400 == 0);
}

static int daysInMonth(int y, int m) {
	static const int days[] = {0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31};
	if (m == 2 && isLeapYear(y)) return 29;
	if (m >= 1 && m <= 12) return days[m];
	return 30;
}

FPCollection Evaluator::fn_dateArith(const FPValue &date_val, const FPValue &qty_val, bool subtract) {
	std::string dt = toString(date_val);
	double amount = qty_val.quantity_value;
	if (subtract) amount = -amount;
	std::string unit = qty_val.quantity_unit;

	// Normalize unit keywords
	if (unit == "year" || unit == "years" || unit == "'a'" || unit == "a") unit = "year";
	else if (unit == "month" || unit == "months" || unit == "'mo'" || unit == "mo") unit = "month";
	else if (unit == "week" || unit == "weeks" || unit == "'wk'" || unit == "wk") unit = "week";
	else if (unit == "day" || unit == "days" || unit == "'d'" || unit == "d") unit = "day";
	else if (unit == "hour" || unit == "hours" || unit == "'h'" || unit == "h") unit = "hour";
	else if (unit == "minute" || unit == "minutes" || unit == "'min'" || unit == "min") unit = "minute";
	else if (unit == "second" || unit == "seconds" || unit == "'s'" || unit == "s") unit = "second";
	else if (unit == "millisecond" || unit == "milliseconds" || unit == "'ms'" || unit == "ms") unit = "millisecond";
	else return {};

	auto orig_type = effectiveType(date_val);
	bool is_time = (orig_type == FPValue::Type::Time);

	if (is_time) {
		// Time arithmetic: parse HH:MM:SS.mmm
		// Strip leading 'T' if present
		std::string time_str = dt;
		if (!time_str.empty() && time_str[0] == 'T') time_str = time_str.substr(1);
		int hour = 0, minute = 0, second = 0, millis = 0;
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

		int iamount = static_cast<int>(amount);
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
			std::snprintf(buf, sizeof(buf), "%02d", hour);
		} else if (!has_second) {
			std::snprintf(buf, sizeof(buf), "%02d:%02d", hour, minute);
		} else if (!has_millis) {
			std::snprintf(buf, sizeof(buf), "%02d:%02d:%02d", hour, minute, second);
		} else {
			std::snprintf(buf, sizeof(buf), "%02d:%02d:%02d.%03d", hour, minute, second, millis);
		}
		result.string_val = std::string("T") + buf;
		return {result};
	}

	// Date/DateTime arithmetic
	int year = 0, month = 1, day = 1, hour = 0, minute = 0, second = 0, millis = 0;
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

	int iamount = static_cast<int>(amount);

	// Handle fractional seconds by converting to milliseconds
	if (unit == "second" && amount != static_cast<double>(iamount)) {
		int ms_amount = static_cast<int>(std::round(amount * 1000));
		millis += ms_amount;
		has_millis = true; has_second = true; has_minute = true;
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
	} else if (unit == "year") {
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

	// Reconstruct the date string with the same precision as input
	char buf[64];
	FPValue result;
	if (orig_type == FPValue::Type::Date) result.type = FPValue::Type::Date;
	else result.type = FPValue::Type::DateTime;

	if (!has_month) {
		std::snprintf(buf, sizeof(buf), "%04d", year);
	} else if (!has_day) {
		std::snprintf(buf, sizeof(buf), "%04d-%02d", year, month);
	} else if (!has_time) {
		std::snprintf(buf, sizeof(buf), "%04d-%02d-%02d", year, month, day);
	} else if (!has_minute) {
		std::snprintf(buf, sizeof(buf), "%04d-%02d-%02dT%02d%s", year, month, day, hour, tz.c_str());
	} else if (!has_second) {
		std::snprintf(buf, sizeof(buf), "%04d-%02d-%02dT%02d:%02d%s", year, month, day, hour, minute, tz.c_str());
	} else if (!has_millis) {
		std::snprintf(buf, sizeof(buf), "%04d-%02d-%02dT%02d:%02d:%02d%s", year, month, day, hour, minute, second, tz.c_str());
	} else {
		std::snprintf(buf, sizeof(buf), "%04d-%02d-%02dT%02d:%02d:%02d.%03d%s", year, month, day, hour, minute, second, millis, tz.c_str());
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
