#pragma once

#include "ast.hpp"
#include "arena_allocator.hpp"
#include "duckdb/common/types/value.hpp"
#include <functional>
#include <map>
#include <set>
#include <string>
#include <vector>

// Forward declare yyjson types (namespaced in DuckDB v1.5.0)
namespace duckdb_yyjson {
struct yyjson_doc;
struct yyjson_val;
} // namespace duckdb_yyjson
using duckdb_yyjson::yyjson_doc;
using duckdb_yyjson::yyjson_val;

namespace fhirpath {

// FHIRPath result: a collection of values
struct FPValue {
	enum class Type {
		JsonVal,
		String,
		Integer,
		Decimal,
		Boolean,
		Date,
		DateTime,
		Time,
		Quantity
	};
	Type type;

	yyjson_val *json_val = nullptr;
	std::string string_val;
	int64_t int_val = 0;
	double decimal_val = 0.0;
	bool bool_val = false;

	double quantity_value = 0.0;
	std::string quantity_unit;
	std::string source_text;  // Original text representation (for decimal precision tracking)
	std::string fhir_type;    // FHIR type name from choice type resolution (e.g. "Quantity")
	std::string field_name;   // Source field name for primitive type inference

	static FPValue FromJson(yyjson_val *val) {
		FPValue v;
		v.type = Type::JsonVal;
		v.json_val = val;
		return v;
	}
	static FPValue FromString(const std::string &s) {
		FPValue v;
		v.type = Type::String;
		v.string_val = s;
		return v;
	}
	static FPValue FromInteger(int64_t i) {
		FPValue v;
		v.type = Type::Integer;
		v.int_val = i;
		return v;
	}
	static FPValue FromDecimal(double d) {
		FPValue v;
		v.type = Type::Decimal;
		v.decimal_val = d;
		return v;
	}
	static FPValue FromBoolean(bool b) {
		FPValue v;
		v.type = Type::Boolean;
		v.bool_val = b;
		return v;
	}
};

using FPCollection = std::vector<FPValue>;

// Exception for spec-mandated errors that must propagate to the caller
// (e.g., single() on multi-element collections per FHIRPath §5.2).
// Distinguished from std::runtime_error so the UDF layer can let
// data-dependent errors return empty while propagating spec errors.
class FHIRPathSpecError : public std::runtime_error {
public:
	using std::runtime_error::runtime_error;
};

class Evaluator {
public:
	~Evaluator();
	FPCollection evaluate(const ASTNode &ast, yyjson_doc *doc, yyjson_val *root);

	// Convert an FPValue to string representation
	std::string toString(const FPValue &val) const;
	double toNumber(const FPValue &val) const;
	bool toBoolean(const FPValue &val) const;

	// Phase 7: Arena allocator for per-batch temporary allocations
	void setArena(ArenaAllocator *arena) {
		arena_ = arena;
	}

private:
	FPCollection eval(const ASTNode &node, const FPCollection &input, yyjson_doc *doc);

	// Navigation
	FPCollection evalMemberAccess(const ASTNode &node, const FPCollection &input, yyjson_doc *doc);
	FPCollection evalIndexer(const ASTNode &node, const FPCollection &input, yyjson_doc *doc);

	// Filtering
	FPCollection evalWhere(const ASTNode &node, const FPCollection &input, yyjson_doc *doc);
	FPCollection evalExists(const ASTNode &node, const FPCollection &input, yyjson_doc *doc);
	FPCollection evalOfType(const ASTNode &node, const FPCollection &input, yyjson_doc *doc);

	// Functions
	FPCollection evalFunction(const ASTNode &node, const FPCollection &input, yyjson_doc *doc, const FPCollection *outer_input = nullptr);
	FPCollection evalArgIsolated(const ASTNode &arg_node, const FPCollection &ctx, yyjson_doc *doc);

	// Function implementations
	FPCollection fn_count(const FPCollection &input);
	FPCollection fn_first(const FPCollection &input);
	FPCollection fn_last(const FPCollection &input);
	FPCollection fn_single(const FPCollection &input);
	FPCollection fn_empty(const FPCollection &input);
	FPCollection fn_hasValue(const FPCollection &input);
	FPCollection fn_not(const FPCollection &input);
	FPCollection fn_all(const ASTNode &criteria, const FPCollection &input, yyjson_doc *doc);
	FPCollection fn_allTrue(const FPCollection &input);
	FPCollection fn_anyTrue(const FPCollection &input);
	FPCollection fn_allFalse(const FPCollection &input);
	FPCollection fn_anyFalse(const FPCollection &input);
	FPCollection fn_startsWith(const FPCollection &input, const FPCollection &arg);
	FPCollection fn_endsWith(const FPCollection &input, const FPCollection &arg);
	FPCollection fn_contains_fn(const FPCollection &input, const FPCollection &arg);
	FPCollection fn_matches(const FPCollection &input, const FPCollection &arg);
	FPCollection fn_replace(const FPCollection &input, const FPCollection &pattern, const FPCollection &substitution);
	FPCollection fn_substring(const FPCollection &input, const FPCollection &start, const FPCollection *length);
	FPCollection fn_length(const FPCollection &input);
	FPCollection fn_upper(const FPCollection &input);
	FPCollection fn_lower(const FPCollection &input);
	FPCollection fn_trim(const FPCollection &input);
	FPCollection fn_toInteger(const FPCollection &input);
	FPCollection fn_toDecimal(const FPCollection &input);
	FPCollection fn_toString(const FPCollection &input);
	FPCollection fn_toDate(const FPCollection &input);
	FPCollection fn_toDateTime(const FPCollection &input);
	FPCollection fn_toBoolean(const FPCollection &input);
	FPCollection fn_toQuantity(const FPCollection &input);
	FPCollection fn_abs(const FPCollection &input);
	FPCollection fn_ceiling(const FPCollection &input);
	FPCollection fn_floor(const FPCollection &input);
	FPCollection fn_round(const FPCollection &input, const FPCollection *precision);
	FPCollection fn_ln(const FPCollection &input);
	FPCollection fn_log(const FPCollection &input, const FPCollection &base);
	FPCollection fn_power(const FPCollection &input, const FPCollection &exponent);
	FPCollection fn_sqrt(const FPCollection &input);
	FPCollection fn_truncate(const FPCollection &input);
	FPCollection fn_iif(const ASTNode &criterion, const ASTNode &trueResult, const ASTNode *falseResult,
	                    const FPCollection &input, yyjson_doc *doc);
	FPCollection fn_extension(const FPCollection &input, const FPCollection &url);
	FPCollection fn_select(const ASTNode &projection, const FPCollection &input, yyjson_doc *doc);
	FPCollection fn_repeat(const ASTNode &projection, const FPCollection &input, yyjson_doc *doc);
	FPCollection fn_distinct(const FPCollection &input);
	FPCollection fn_trace(const FPCollection &input);
	FPCollection fn_aggregate(const ASTNode &node, const FPCollection &input, yyjson_doc *doc);
	FPCollection fn_combine(const FPCollection &input, const FPCollection &other);
	FPCollection fn_union(const FPCollection &left, const FPCollection &right);
	FPCollection fn_intersect(const FPCollection &input, const FPCollection &other);
	FPCollection fn_exclude(const FPCollection &input, const FPCollection &other);
	FPCollection fn_tail(const FPCollection &input);
	FPCollection fn_take(const FPCollection &input, const FPCollection &count);
	FPCollection fn_skip(const FPCollection &input, const FPCollection &count);
	FPCollection fn_split(const FPCollection &input, const FPCollection &delimiter);
	FPCollection fn_toTime(const FPCollection &input);
	FPCollection fn_children(const FPCollection &input);
	FPCollection fn_descendants(const FPCollection &input);
	FPCollection fn_convertsToBoolean(const FPCollection &input);
	FPCollection fn_convertsToInteger(const FPCollection &input);
	FPCollection fn_convertsToDecimal(const FPCollection &input);
	FPCollection fn_convertsToString(const FPCollection &input);
	FPCollection fn_convertsToDate(const FPCollection &input);
	FPCollection fn_convertsToDateTime(const FPCollection &input);
	FPCollection fn_convertsToTime(const FPCollection &input);
	FPCollection fn_convertsToQuantity(const FPCollection &input);
	FPCollection fn_lowBoundary(const FPCollection &input, const FPCollection *precision_arg);
	FPCollection fn_highBoundary(const FPCollection &input, const FPCollection *precision_arg);
	FPCollection fn_precision(const FPCollection &input);
	FPCollection fn_encode(const FPCollection &input, const FPCollection &format);
	FPCollection fn_decode(const FPCollection &input, const FPCollection &format);
	FPCollection fn_isType(const FPCollection &input, const std::string &type_name, bool exact = false);
	FPCollection fn_asType(const FPCollection &input, const std::string &type_name);
	FPCollection fn_sort(const std::vector<const ASTNode *> &criteria, const FPCollection &input, yyjson_doc *doc);
	FPCollection fn_coalesce(const ASTNode &node, const FPCollection &input, yyjson_doc *doc);
	FPCollection fn_isDistinct(const FPCollection &input);
	FPCollection fn_supersetOf(const FPCollection &input, const FPCollection &other);
	FPCollection fn_subsetOf(const FPCollection &input, const FPCollection &other);
	FPCollection fn_dateArith(const FPValue &date_val, const FPValue &qty_val, bool subtract);
	FPCollection evalFactoryMethod(const ASTNode &node, yyjson_doc *doc);

	// Binary operators
	FPCollection evalBinaryOp(const ASTNode &node, const FPCollection &input, yyjson_doc *doc);
	FPCollection evalUnaryOp(const ASTNode &node, const FPCollection &input, yyjson_doc *doc);

	// Helpers
	bool isTruthy(const FPCollection &collection) const;
	FPCollection jsonValToCollection(yyjson_val *val) const;
	std::string jsonValToString(yyjson_val *val) const;

	// Arena-backed string allocation helper
	const char *arenaString(const char *str, size_t len) {
		if (arena_) {
			return arena_->copy_string(str, len);
		}
		return str;
	}

	// Context
	yyjson_val *resource_context_ = nullptr;
	yyjson_doc *current_doc_ = nullptr;

	// Variable contexts for aggregate ($total), defineVariable, $index
	FPCollection total_context_;
	int64_t index_context_ = -1;
	std::map<std::string, FPCollection> defined_variables_;
	std::set<std::string> chain_defined_vars_; // Track redefinition in same chain

	// Phase 7: Arena allocator (optional, set per-batch)
	ArenaAllocator *arena_ = nullptr;

	// Factory-created yyjson documents (freed in destructor)
	std::vector<yyjson_doc*> owned_docs_;
};

} // namespace fhirpath
