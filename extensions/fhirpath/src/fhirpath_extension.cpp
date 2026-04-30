#define DUCKDB_EXTENSION_MAIN

#include "fhirpath_extension.hpp"
#include "fhirpath/ast.hpp"
#include "fhirpath/arena_allocator.hpp"
#include "fhirpath/evaluator.hpp"
#include "fhirpath/expression_cache.hpp"
#include "fhirpath/parser.hpp"

#include "duckdb.hpp"
#include "duckdb/common/exception.hpp"
#include "duckdb/common/types/value.hpp"
#include "duckdb/common/vector_operations/unary_executor.hpp"
#include "duckdb/function/scalar_function.hpp"
#include "duckdb/planner/expression/bound_constant_expression.hpp"
#include "duckdb/planner/expression/bound_function_expression.hpp"
#include "duckdb/execution/expression_executor.hpp"
#include "duckdb/execution/expression_executor_state.hpp"
#include "yyjson.hpp"

using namespace duckdb_yyjson; // NOLINT

#include <memory>
#include <mutex>
#include <stdexcept>
#include <utility>

namespace duckdb {

// Check if an AST is a simple dotted path (e.g., "birthDate", "name.given")
static bool IsSimplePath(const fhirpath::ASTNode &ast) {
	if (ast.type == fhirpath::NodeType::MemberAccess) {
		if (!ast.source) {
			return true; // Single field from root
		}
		return IsSimplePath(*ast.source);
	}
	return false;
}

// Collect path segments from a simple path AST in order
static void CollectPathSegments(const fhirpath::ASTNode &ast, std::vector<std::string> &segments) {
	if (ast.source) {
		CollectPathSegments(*ast.source, segments);
	}
	if (ast.type == fhirpath::NodeType::MemberAccess) {
		segments.push_back(ast.name);
	}
}

// Bind data: shared across all threads via FunctionData
struct FhirpathBindData : public FunctionData {
	std::shared_ptr<fhirpath::ExpressionCache> cache;
	std::shared_ptr<fhirpath::Parser> parser;

	// Phase 7: Constant expression optimization
	bool expression_is_constant = false;
	std::shared_ptr<fhirpath::ASTNode> precompiled_ast;
	bool is_simple_path = false;
	std::vector<std::string> path_segments;

	FhirpathBindData()
	    : cache(std::make_shared<fhirpath::ExpressionCache>(1024)),
	      parser(std::make_shared<fhirpath::Parser>()) {
	}

	unique_ptr<FunctionData> Copy() const override {
		auto copy = make_uniq<FhirpathBindData>();
		copy->cache = cache;
		copy->parser = parser;
		copy->expression_is_constant = expression_is_constant;
		copy->precompiled_ast = precompiled_ast;
		copy->is_simple_path = is_simple_path;
		copy->path_segments = path_segments;
		return std::move(copy);
	}
	bool Equals(const FunctionData &other) const override {
		return true;
	}
};

// Global shared state for FHIRPath (thread-safe: shared_ptr, cache is mutex-protected)
static std::shared_ptr<fhirpath::ExpressionCache> g_fhirpath_cache;
static std::shared_ptr<fhirpath::Parser> g_fhirpath_parser;

static void EnsureGlobalState() {
	static std::once_flag g_init_flag;
	std::call_once(g_init_flag, []() {
		g_fhirpath_cache = std::make_shared<fhirpath::ExpressionCache>(1024);
		g_fhirpath_parser = std::make_shared<fhirpath::Parser>();
	});
}

// Wrapper to access state — prefers bind data if available, falls back to global
struct FhirpathState {
	FhirpathBindData *bind_data;

	FhirpathState() : bind_data(nullptr) {}
	explicit FhirpathState(FhirpathBindData *bd) : bind_data(bd) {}

	std::shared_ptr<fhirpath::ExpressionCache> &cache() {
		return bind_data ? bind_data->cache : g_fhirpath_cache;
	}
	std::shared_ptr<fhirpath::Parser> &parser() {
		return bind_data ? bind_data->parser : g_fhirpath_parser;
	}
	bool expression_is_constant() const {
		return bind_data ? bind_data->expression_is_constant : false;
	}
	std::shared_ptr<fhirpath::ASTNode> &precompiled_ast() {
		static thread_local std::shared_ptr<fhirpath::ASTNode> null_ast;
		return bind_data ? bind_data->precompiled_ast : null_ast;
	}
	bool is_simple_path() const {
		return bind_data ? bind_data->is_simple_path : false;
	}
	const std::vector<std::string> &path_segments() const {
		static thread_local std::vector<std::string> empty;
		return bind_data ? bind_data->path_segments : empty;
	}
};

// Helper to get FhirpathState from ExpressionState
static FhirpathState GetFhirpathState(ExpressionState &state) {
	EnsureGlobalState();
	auto &func_expr = state.expr.Cast<BoundFunctionExpression>();
	if (func_expr.bind_info) {
		return FhirpathState(static_cast<FhirpathBindData *>(func_expr.bind_info.get()));
	}
	return FhirpathState();
}

static unique_ptr<FunctionData> FhirpathBind(ClientContext &context, ScalarFunction &function,
                                             vector<unique_ptr<Expression>> &arguments) {
	auto data = make_uniq<FhirpathBindData>();

	// Phase 7: Detect constant expressions at bind time
	// Note: In loadable extension context, we check for constant string values
	// directly instead of using ExpressionExecutor::EvaluateScalar which can
	// crash due to missing internal state in the loadable extension context.
	if (arguments.size() >= 2 && arguments[1]->IsFoldable()) {
		try {
			// Try to get the constant value directly from the expression
			if (arguments[1]->type == ExpressionType::VALUE_CONSTANT) {
				auto &const_expr = arguments[1]->Cast<BoundConstantExpression>();
				if (!const_expr.value.IsNull()) {
					auto expr_str = const_expr.value.GetValue<string>();
					auto ast = data->parser->parse(expr_str);
					if (ast) {
						data->precompiled_ast = ast;
						data->expression_is_constant = true;
						data->cache->put(expr_str, ast);

						if (IsSimplePath(*ast)) {
							data->is_simple_path = true;
							CollectPathSegments(*ast, data->path_segments);
						}
					}
				}
			}
		} catch (const std::bad_alloc&) {
			throw;
		} catch (const std::exception&) {
			// Parse or evaluation failure: leave as non-constant
		}
	}

	return std::move(data);
}

// Helper: get or compile an expression
static std::shared_ptr<fhirpath::ASTNode> GetOrCompile(FhirpathState &state, const std::string &expr_str) {
	// Phase 7: Use precompiled AST for constant expressions (lock-free)
	if (state.expression_is_constant() && state.precompiled_ast()) {
		return state.precompiled_ast();
	}
	auto cached = state.cache()->get(expr_str);
	if (cached) {
		return cached;
	}
	try {
		// Create a local Parser per call — Parser has mutable state (tokens_, pos_)
		// and is NOT thread-safe. Using a shared g_fhirpath_parser across threads
		// causes data races. A fresh Parser per parse() call is cheap.
		fhirpath::Parser local_parser;
		auto ast = local_parser.parse(expr_str);
		if (ast) {
			state.cache()->put(expr_str, ast);
		}
		return ast;
	} catch (const std::bad_alloc&) {
		throw;
	} catch (const std::exception&) {
		return nullptr;
	}
}

// Phase 7: Fast path for simple dotted path expressions (e.g., "birthDate", "id")
// Bypasses full evaluator — direct yyjson field lookup
// Returns <found, value> pair (C++11 compatible, no std::optional)
// Compute how many leading path segments to skip in the fast path.
// FHIRPath treats the first segment as a type qualifier when it matches the
// root resource's resourceType (e.g., "Observation.valueQuantity.value" against
// an Observation resource — "Observation" is not a field key, it's the type).
// Returns 0 when no prefix should be skipped (no allocation, pure pointer ops).
static size_t ComputeSegStart(yyjson_val *root, const std::vector<std::string> &segments) {
	if (segments.empty() || !root || !yyjson_is_obj(root)) {
		return 0;
	}
	yyjson_val *rt = yyjson_obj_get(root, "resourceType");
	if (rt && yyjson_is_str(rt)) {
		const char *resource_type = yyjson_get_str(rt);
		if (resource_type && segments[0] == resource_type) {
			return 1;
		}
	}
	return 0;
}

// W1 fix: seg_start computed from the already-parsed root pointer — zero allocation,
//         single JSON parse per call.
// W3 fix: return {false,""} when all segments are consumed by the prefix (single-
//         segment type-only paths like 'Patient') so callers fall through to the full
//         evaluator rather than serialising the whole root object.
static std::pair<bool, std::string> FastPathLookup(const char *json_data, idx_t json_len,
                                                   const std::vector<std::string> &segments) {
	yyjson_doc *doc = yyjson_read(json_data, json_len, 0);
	if (!doc) {
		return std::make_pair(false, std::string());
	}

	yyjson_val *current = yyjson_doc_get_root(doc);

	// Compute seg_start from the already-parsed root — no allocation needed.
	size_t seg_start = ComputeSegStart(current, segments);

	// Guard (W3): if the prefix skip consumed all segments, yield a miss so the
	// caller falls through to the full evaluator.
	if (seg_start >= segments.size()) {
		yyjson_doc_free(doc);
		return std::make_pair(false, std::string());
	}

	for (size_t seg_idx = seg_start; seg_idx < segments.size(); seg_idx++) {
		const auto &seg = segments[seg_idx];
		// FHIRPath auto-flattens arrays: descend into first element if current is an array
		if (current && yyjson_is_arr(current)) {
			current = yyjson_arr_get_first(current);
		}
		if (!current || !yyjson_is_obj(current)) {
			yyjson_doc_free(doc);
			return std::make_pair(false, std::string());
		}
		current = yyjson_obj_get(current, seg.c_str());
	}

	std::pair<bool, std::string> result(false, std::string());
	if (current) {
		if (yyjson_is_str(current)) {
			result = std::make_pair(true, std::string(yyjson_get_str(current)));
		} else if (yyjson_is_int(current)) {
			result = std::make_pair(true, std::to_string(yyjson_get_sint(current)));
		} else if (yyjson_is_real(current)) {
			result = std::make_pair(true, std::to_string(yyjson_get_real(current)));
		} else if (yyjson_is_bool(current)) {
			result = std::make_pair(true, std::string(yyjson_get_bool(current) ? "true" : "false"));
		} else if (yyjson_is_arr(current)) {
			yyjson_val *first = yyjson_arr_get_first(current);
			if (first && yyjson_is_str(first)) {
				result = std::make_pair(true, std::string(yyjson_get_str(first)));
			} else if (first) {
				char *json = yyjson_val_write(first, 0, nullptr);
				if (json) {
					result = std::make_pair(true, std::string(json));
					free(json);
				}
			}
		} else {
			char *json = yyjson_val_write(current, 0, nullptr);
			if (json) {
				result = std::make_pair(true, std::string(json));
				free(json);
			}
		}
	}

	yyjson_doc_free(doc);
	return result;
}

// Helper: evaluate FHIRPath and return the collection
// Phase 7: Accepts optional arena allocator for per-batch allocation reuse
static fhirpath::FPCollection EvaluateFhirpath(FhirpathState &state, const char *json_data, idx_t json_len,
                                                const std::string &expr_str,
                                                fhirpath::ArenaAllocator *arena = nullptr) {
	if (expr_str.empty()) {
		throw std::runtime_error("FHIRPath expression cannot be empty");
	}
	auto ast = GetOrCompile(state, expr_str);
	if (!ast) {
		throw std::runtime_error("Invalid FHIRPath expression: " + expr_str);
	}

	yyjson_doc *doc = yyjson_read(json_data, json_len, 0);
	if (!doc) {
		return {};
	}

	fhirpath::Evaluator evaluator;
	if (arena) {
		evaluator.setArena(arena);
	}
	fhirpath::FPCollection results;
	try {
		results = evaluator.evaluate(*ast, doc, yyjson_doc_get_root(doc));
	} catch (const fhirpath::FHIRPathSpecError&) {
		yyjson_doc_free(doc);
		throw;
	} catch (const std::bad_alloc&) {
		yyjson_doc_free(doc);
		throw;
	} catch (const std::exception&) {
		yyjson_doc_free(doc);
		return {};
	}

	// We need to convert JSON-backed values to owned strings before freeing doc
	fhirpath::FPCollection owned_results;
	for (auto &val : results) {
		if (val.type == fhirpath::FPValue::Type::JsonVal && val.json_val) {
			// Convert to owned representation
			if (yyjson_is_str(val.json_val)) {
				owned_results.push_back(fhirpath::FPValue::FromString(yyjson_get_str(val.json_val)));
			} else if (yyjson_is_int(val.json_val)) {
				owned_results.push_back(fhirpath::FPValue::FromInteger(yyjson_get_sint(val.json_val)));
			} else if (yyjson_is_real(val.json_val)) {
				owned_results.push_back(fhirpath::FPValue::FromDecimal(yyjson_get_real(val.json_val)));
			} else if (yyjson_is_bool(val.json_val)) {
				owned_results.push_back(fhirpath::FPValue::FromBoolean(yyjson_get_bool(val.json_val)));
			} else if (yyjson_is_null(val.json_val)) {
				// Skip nulls
			} else {
				// Objects/arrays: serialize to JSON string
				char *json = yyjson_val_write(val.json_val, 0, nullptr);
				if (json) {
					owned_results.push_back(fhirpath::FPValue::FromString(json));
					free(json);
				}
			}
		} else {
			owned_results.push_back(val);
		}
	}

	yyjson_doc_free(doc);
	return owned_results;
}

// --- UDF Implementations ---

// fhirpath(resource JSON, expression VARCHAR) → VARCHAR[]
static void FhirpathFunction(DataChunk &args, ExpressionState &state, Vector &result) {
	auto func_state = GetFhirpathState(state);
	idx_t count = args.size();

	UnifiedVectorFormat resource_data, expr_data;
	args.data[0].ToUnifiedFormat(count, resource_data);
	args.data[1].ToUnifiedFormat(count, expr_data);

	auto resources = UnifiedVectorFormat::GetData<string_t>(resource_data);
	auto expressions = UnifiedVectorFormat::GetData<string_t>(expr_data);

	fhirpath::Evaluator str_helper;

	// Collect offsets first, push all values, then write list_entries
	// to avoid stale pointer after ListVector::PushBack reallocation
	std::vector<idx_t> row_offsets(count);
	std::vector<idx_t> row_counts(count);
	std::vector<bool> row_valid(count, false);
	idx_t total_size = 0;

	for (idx_t i = 0; i < count; i++) {
		auto r_idx = resource_data.sel->get_index(i);
		auto e_idx = expr_data.sel->get_index(i);

		if (!resource_data.validity.RowIsValid(r_idx) || !expr_data.validity.RowIsValid(e_idx)) {
			row_offsets[i] = 0;
			row_counts[i] = 0;
			continue;
		}

		row_valid[i] = true;
		auto fp_results =
		    EvaluateFhirpath(func_state, resources[r_idx].GetData(), resources[r_idx].GetSize(),
		                     expressions[e_idx].GetString());

		row_offsets[i] = total_size;
		row_counts[i] = static_cast<idx_t>(fp_results.size());
		for (const auto &val : fp_results) {
			auto str = str_helper.toString(val);
			ListVector::PushBack(result, Value(str));
		}
		total_size += fp_results.size();
	}

	auto list_entries = ListVector::GetData(result);
	for (idx_t i = 0; i < count; i++) {
		list_entries[i] = {row_offsets[i], row_counts[i]};
		if (!row_valid[i]) {
			FlatVector::Validity(result).SetInvalid(i);
		}
	}
	ListVector::SetListSize(result, total_size);
}

// fhirpath_text(resource JSON, expression VARCHAR) → VARCHAR
static void FhirpathTextFunction(DataChunk &args, ExpressionState &state, Vector &result) {
	auto func_state = GetFhirpathState(state);
	idx_t count = args.size();

	UnifiedVectorFormat resource_data, expr_data;
	args.data[0].ToUnifiedFormat(count, resource_data);
	args.data[1].ToUnifiedFormat(count, expr_data);

	auto resources = UnifiedVectorFormat::GetData<string_t>(resource_data);
	auto expressions = UnifiedVectorFormat::GetData<string_t>(expr_data);

	result.SetVectorType(VectorType::FLAT_VECTOR);
	auto result_data = FlatVector::GetData<string_t>(result);
	auto &result_mask = FlatVector::Validity(result);

	fhirpath::Evaluator str_helper;

	// Phase 7: Per-batch arena allocator for temporary strings
	fhirpath::ArenaAllocator arena;

	for (idx_t i = 0; i < count; i++) {
		auto r_idx = resource_data.sel->get_index(i);
		auto e_idx = expr_data.sel->get_index(i);

		if (!resource_data.validity.RowIsValid(r_idx) || !expr_data.validity.RowIsValid(e_idx)) {
			result_mask.SetInvalid(i);
			continue;
		}

		// Phase 7: Simple path fast path — bypass full evaluator.
		// FastPathLookup handles resourceType prefix-skip and W3 guard internally.
		if (func_state.is_simple_path() && !func_state.path_segments().empty()) {
			auto fast_result = FastPathLookup(resources[r_idx].GetData(), resources[r_idx].GetSize(),
			                                  func_state.path_segments());
			if (fast_result.first) {
				result_data[i] = StringVector::AddString(result, fast_result.second);
				continue;
			}
			// Fall through to full evaluator (handles choice types, arrays, etc.)
		}

		auto fp_results =
		    EvaluateFhirpath(func_state, resources[r_idx].GetData(), resources[r_idx].GetSize(),
		                     expressions[e_idx].GetString(), &arena);

		if (fp_results.empty()) {
			result_mask.SetInvalid(i);
		} else {
			auto str = str_helper.toString(fp_results[0]);
			result_data[i] = StringVector::AddString(result, str);
		}
	}
}

// fhirpath_number(resource JSON, expression VARCHAR) → DOUBLE
static void FhirpathNumberFunction(DataChunk &args, ExpressionState &state, Vector &result) {
	auto func_state = GetFhirpathState(state);
	idx_t count = args.size();

	UnifiedVectorFormat resource_data, expr_data;
	args.data[0].ToUnifiedFormat(count, resource_data);
	args.data[1].ToUnifiedFormat(count, expr_data);

	auto resources = UnifiedVectorFormat::GetData<string_t>(resource_data);
	auto expressions = UnifiedVectorFormat::GetData<string_t>(expr_data);

	result.SetVectorType(VectorType::FLAT_VECTOR);
	auto result_data = FlatVector::GetData<double>(result);
	auto &result_mask = FlatVector::Validity(result);

	fhirpath::Evaluator str_helper;

	for (idx_t i = 0; i < count; i++) {
		auto r_idx = resource_data.sel->get_index(i);
		auto e_idx = expr_data.sel->get_index(i);

		if (!resource_data.validity.RowIsValid(r_idx) || !expr_data.validity.RowIsValid(e_idx)) {
			result_mask.SetInvalid(i);
			continue;
		}

		// Phase 7: Simple path fast path for numeric extraction.
		// Uses ComputeSegStart to skip resource-type prefix without allocation.
		// W2: non-numeric terminal values fall through to the full evaluator
		// instead of silently returning NULL (matches FhirpathTextFunction behavior).
		if (func_state.is_simple_path() && !func_state.path_segments().empty()) {
			yyjson_doc *doc = yyjson_read(resources[r_idx].GetData(), resources[r_idx].GetSize(), 0);
			if (doc) {
				yyjson_val *current = yyjson_doc_get_root(doc);
				const auto &segments = func_state.path_segments();
				size_t seg_start = ComputeSegStart(current, segments);

				// W3: all segments consumed by prefix — fall through
				if (seg_start >= segments.size()) {
					yyjson_doc_free(doc);
					// fall through to full evaluator below
				} else {
					bool found = true;
					for (size_t seg_idx = seg_start; seg_idx < segments.size(); seg_idx++) {
						const auto &seg = segments[seg_idx];
						if (current && yyjson_is_arr(current)) {
							current = yyjson_arr_get_first(current);
						}
						if (!current || !yyjson_is_obj(current)) {
							found = false;
							break;
						}
						current = yyjson_obj_get(current, seg.c_str());
					}
					yyjson_doc_free(doc);
					if (found && current) {
						if (yyjson_is_int(current)) {
							result_data[i] = static_cast<double>(yyjson_get_sint(current));
							continue;
						} else if (yyjson_is_real(current)) {
							result_data[i] = yyjson_get_real(current);
							continue;
						}
						// Non-numeric type (e.g. string "42"): fall through to full
						// evaluator which handles toString→toNumber conversions.
					} else if (!found) {
						// Path not found in this resource: NULL
						result_mask.SetInvalid(i);
						continue;
					}
					// current==NULL (key exists but value is null): NULL
					if (!current) {
						result_mask.SetInvalid(i);
						continue;
					}
					// fall through for non-numeric types
				}
			}
		}

		auto fp_results =
		    EvaluateFhirpath(func_state, resources[r_idx].GetData(), resources[r_idx].GetSize(),
		                     expressions[e_idx].GetString());

		if (fp_results.empty()) {
			result_mask.SetInvalid(i);
		} else {
			result_data[i] = str_helper.toNumber(fp_results[0]);
		}
	}
}

// fhirpath_date(resource JSON, expression VARCHAR) → VARCHAR
static void FhirpathDateFunction(DataChunk &args, ExpressionState &state, Vector &result) {
	auto func_state = GetFhirpathState(state);
	idx_t count = args.size();

	UnifiedVectorFormat resource_data, expr_data;
	args.data[0].ToUnifiedFormat(count, resource_data);
	args.data[1].ToUnifiedFormat(count, expr_data);

	auto resources = UnifiedVectorFormat::GetData<string_t>(resource_data);
	auto expressions = UnifiedVectorFormat::GetData<string_t>(expr_data);

	result.SetVectorType(VectorType::FLAT_VECTOR);
	auto result_data = FlatVector::GetData<string_t>(result);
	auto &result_mask = FlatVector::Validity(result);

	fhirpath::Evaluator str_helper;

	for (idx_t i = 0; i < count; i++) {
		auto r_idx = resource_data.sel->get_index(i);
		auto e_idx = expr_data.sel->get_index(i);

		if (!resource_data.validity.RowIsValid(r_idx) || !expr_data.validity.RowIsValid(e_idx)) {
			result_mask.SetInvalid(i);
			continue;
		}

		auto fp_results =
		    EvaluateFhirpath(func_state, resources[r_idx].GetData(), resources[r_idx].GetSize(),
		                     expressions[e_idx].GetString());

		if (fp_results.empty()) {
			result_mask.SetInvalid(i);
		} else {
			std::string date_str = str_helper.toString(fp_results[0]);
			// Preserve partial date precision (YYYY, YYYY-MM, YYYY-MM-DD)
			// Only strip time portion if present (>10 chars means datetime)
			if (date_str.size() > 10) {
				date_str = date_str.substr(0, 10);
			}
			result_data[i] = StringVector::AddString(result, date_str);
		}
	}
}

// fhirpath_bool(resource JSON, expression VARCHAR) → BOOLEAN
static void FhirpathBoolFunction(DataChunk &args, ExpressionState &state, Vector &result) {
	auto func_state = GetFhirpathState(state);
	idx_t count = args.size();

	UnifiedVectorFormat resource_data, expr_data;
	args.data[0].ToUnifiedFormat(count, resource_data);
	args.data[1].ToUnifiedFormat(count, expr_data);

	auto resources = UnifiedVectorFormat::GetData<string_t>(resource_data);
	auto expressions = UnifiedVectorFormat::GetData<string_t>(expr_data);

	result.SetVectorType(VectorType::FLAT_VECTOR);
	auto result_data = FlatVector::GetData<bool>(result);
	auto &result_mask = FlatVector::Validity(result);

	fhirpath::Evaluator str_helper;

	for (idx_t i = 0; i < count; i++) {
		auto r_idx = resource_data.sel->get_index(i);
		auto e_idx = expr_data.sel->get_index(i);

		if (!resource_data.validity.RowIsValid(r_idx) || !expr_data.validity.RowIsValid(e_idx)) {
			result_mask.SetInvalid(i);
			continue;
		}

		auto fp_results =
		    EvaluateFhirpath(func_state, resources[r_idx].GetData(), resources[r_idx].GetSize(),
		                     expressions[e_idx].GetString());

		if (fp_results.empty()) {
			result_mask.SetInvalid(i);
		} else {
			try {
				result_data[i] = str_helper.toBoolean(fp_results[0]);
			} catch (const std::exception&) {
				result_mask.SetInvalid(i);
			}
		}
	}
}

// fhirpath_json(resource JSON, expression VARCHAR) → VARCHAR (JSON string)
static void FhirpathJsonFunction(DataChunk &args, ExpressionState &state, Vector &result) {
	auto func_state = GetFhirpathState(state);
	idx_t count = args.size();

	UnifiedVectorFormat resource_data, expr_data;
	args.data[0].ToUnifiedFormat(count, resource_data);
	args.data[1].ToUnifiedFormat(count, expr_data);

	auto resources = UnifiedVectorFormat::GetData<string_t>(resource_data);
	auto expressions = UnifiedVectorFormat::GetData<string_t>(expr_data);

	result.SetVectorType(VectorType::FLAT_VECTOR);
	auto result_data = FlatVector::GetData<string_t>(result);
	auto &result_mask = FlatVector::Validity(result);

	fhirpath::Evaluator str_helper;

	for (idx_t i = 0; i < count; i++) {
		auto r_idx = resource_data.sel->get_index(i);
		auto e_idx = expr_data.sel->get_index(i);

		if (!resource_data.validity.RowIsValid(r_idx) || !expr_data.validity.RowIsValid(e_idx)) {
			result_mask.SetInvalid(i);
			continue;
		}

		auto fp_results =
		    EvaluateFhirpath(func_state, resources[r_idx].GetData(), resources[r_idx].GetSize(),
		                     expressions[e_idx].GetString());

		// Return as JSON array
		std::string json_str = "[";
		for (size_t j = 0; j < fp_results.size(); j++) {
			if (j > 0) {
				json_str += ",";
			}
			auto s = str_helper.toString(fp_results[j]);
			// JSON escaping — handle all control characters (0x00-0x1F)
			json_str += "\"";
			for (unsigned char c : s) {
				switch (c) {
				case '"':  json_str += "\\\""; break;
				case '\\': json_str += "\\\\"; break;
				case '\b': json_str += "\\b"; break;
				case '\f': json_str += "\\f"; break;
				case '\n': json_str += "\\n"; break;
				case '\r': json_str += "\\r"; break;
				case '\t': json_str += "\\t"; break;
				default:
					if (c < 0x20) {
						char buf[8];
						snprintf(buf, sizeof(buf), "\\u%04x", c);
						json_str += buf;
					} else {
						json_str += static_cast<char>(c);
					}
					break;
				}
			}
			json_str += "\"";
		}
		json_str += "]";
		result_data[i] = StringVector::AddString(result, json_str);
	}
}

// fhirpath_timestamp(resource JSON, expression VARCHAR) → VARCHAR
static void FhirpathTimestampFunction(DataChunk &args, ExpressionState &state, Vector &result) {
	auto func_state = GetFhirpathState(state);
	idx_t count = args.size();

	UnifiedVectorFormat resource_data, expr_data;
	args.data[0].ToUnifiedFormat(count, resource_data);
	args.data[1].ToUnifiedFormat(count, expr_data);

	auto resources = UnifiedVectorFormat::GetData<string_t>(resource_data);
	auto expressions = UnifiedVectorFormat::GetData<string_t>(expr_data);

	result.SetVectorType(VectorType::FLAT_VECTOR);
	auto result_data = FlatVector::GetData<string_t>(result);
	auto &result_mask = FlatVector::Validity(result);

	fhirpath::Evaluator str_helper;

	for (idx_t i = 0; i < count; i++) {
		auto r_idx = resource_data.sel->get_index(i);
		auto e_idx = expr_data.sel->get_index(i);

		if (!resource_data.validity.RowIsValid(r_idx) || !expr_data.validity.RowIsValid(e_idx)) {
			result_mask.SetInvalid(i);
			continue;
		}

		auto fp_results =
		    EvaluateFhirpath(func_state, resources[r_idx].GetData(), resources[r_idx].GetSize(),
		                     expressions[e_idx].GetString());

		if (fp_results.empty()) {
			result_mask.SetInvalid(i);
		} else {
			auto str = str_helper.toString(fp_results[0]);
			result_data[i] = StringVector::AddString(result, str);
		}
	}
}

// fhirpath_quantity(resource JSON, expression VARCHAR) → VARCHAR
static void FhirpathQuantityFunction(DataChunk &args, ExpressionState &state, Vector &result) {
	auto func_state = GetFhirpathState(state);
	idx_t count = args.size();

	UnifiedVectorFormat resource_data, expr_data;
	args.data[0].ToUnifiedFormat(count, resource_data);
	args.data[1].ToUnifiedFormat(count, expr_data);

	auto resources = UnifiedVectorFormat::GetData<string_t>(resource_data);
	auto expressions = UnifiedVectorFormat::GetData<string_t>(expr_data);

	result.SetVectorType(VectorType::FLAT_VECTOR);
	auto result_data = FlatVector::GetData<string_t>(result);
	auto &result_mask = FlatVector::Validity(result);

	fhirpath::Evaluator str_helper;

	for (idx_t i = 0; i < count; i++) {
		auto r_idx = resource_data.sel->get_index(i);
		auto e_idx = expr_data.sel->get_index(i);

		if (!resource_data.validity.RowIsValid(r_idx) || !expr_data.validity.RowIsValid(e_idx)) {
			result_mask.SetInvalid(i);
			continue;
		}

		auto fp_results =
		    EvaluateFhirpath(func_state, resources[r_idx].GetData(), resources[r_idx].GetSize(),
		                     expressions[e_idx].GetString());

		if (fp_results.empty()) {
			result_mask.SetInvalid(i);
		} else {
			auto str = str_helper.toString(fp_results[0]);
			result_data[i] = StringVector::AddString(result, str);
		}
	}
}

// fhirpath_is_valid(expression VARCHAR) → BOOLEAN
static void FhirpathIsValidFunction(DataChunk &args, ExpressionState &state, Vector &result) {
	idx_t count = args.size();

	UnifiedVectorFormat expr_data;
	args.data[0].ToUnifiedFormat(count, expr_data);
	auto expressions = UnifiedVectorFormat::GetData<string_t>(expr_data);

	result.SetVectorType(VectorType::FLAT_VECTOR);
	auto result_data = FlatVector::GetData<bool>(result);

	// Use thread_local parser — Parser has mutable state and is NOT thread-safe
	static thread_local fhirpath::Parser tls_parser;

	for (idx_t i = 0; i < count; i++) {
		auto e_idx = expr_data.sel->get_index(i);
		if (!expr_data.validity.RowIsValid(e_idx)) {
			result_data[i] = false;
			continue;
		}

		try {
			auto ast = tls_parser.parse(expressions[e_idx].GetString());
			result_data[i] = (ast != nullptr);
		} catch (const std::bad_alloc&) {
			throw;
		} catch (const std::exception&) {
			result_data[i] = false;
		}
	}
}

// fhirpath_predicate(resource JSON, expression VARCHAR) → VARCHAR[]
// Returns ["true"] if expression evaluates to non-empty, ["false"] otherwise
static void FhirpathPredicateFunction(DataChunk &args, ExpressionState &state, Vector &result) {
	auto func_state = GetFhirpathState(state);
	idx_t count = args.size();

	UnifiedVectorFormat resource_data, expr_data;
	args.data[0].ToUnifiedFormat(count, resource_data);
	args.data[1].ToUnifiedFormat(count, expr_data);

	auto resources = UnifiedVectorFormat::GetData<string_t>(resource_data);
	auto expressions = UnifiedVectorFormat::GetData<string_t>(expr_data);

	// Collect offsets first, push all values, then write list_entries
	// to avoid stale pointer after ListVector::PushBack reallocation
	std::vector<idx_t> row_offsets(count);
	std::vector<idx_t> row_counts(count);
	std::vector<bool> row_valid(count, false);
	idx_t total_size = 0;

	for (idx_t i = 0; i < count; i++) {
		auto r_idx = resource_data.sel->get_index(i);
		auto e_idx = expr_data.sel->get_index(i);

		if (!resource_data.validity.RowIsValid(r_idx) || !expr_data.validity.RowIsValid(e_idx)) {
			row_offsets[i] = 0;
			row_counts[i] = 0;
			continue;
		}

		row_valid[i] = true;
		auto fp_results =
		    EvaluateFhirpath(func_state, resources[r_idx].GetData(), resources[r_idx].GetSize(),
		                     expressions[e_idx].GetString());

		std::string pred_result = fp_results.empty() ? "false" : "true";
		row_offsets[i] = total_size;
		row_counts[i] = 1;
		ListVector::PushBack(result, Value(pred_result));
		total_size += 1;
	}

	auto list_entries = ListVector::GetData(result);
	for (idx_t i = 0; i < count; i++) {
		list_entries[i] = {row_offsets[i], row_counts[i]};
		if (!row_valid[i]) {
			FlatVector::Validity(result).SetInvalid(i);
		}
	}
	ListVector::SetListSize(result, total_size);
}

// --- Registration ---

static void LoadInternal(ExtensionLoader &loader) {
	// fhirpath(JSON, VARCHAR) → VARCHAR[]
	auto fhirpath_func = ScalarFunction("fhirpath", {LogicalType::VARCHAR, LogicalType::VARCHAR},
	                                    LogicalType::LIST(LogicalType::VARCHAR), FhirpathFunction, FhirpathBind);

	loader.RegisterFunction(fhirpath_func);

	// fhirpath_text(JSON, VARCHAR) → VARCHAR
	auto text_func = ScalarFunction("fhirpath_text", {LogicalType::VARCHAR, LogicalType::VARCHAR},
	                                LogicalType::VARCHAR, FhirpathTextFunction, FhirpathBind);
	text_func.null_handling = FunctionNullHandling::SPECIAL_HANDLING;

	loader.RegisterFunction(text_func);

	// fhirpath_number(JSON, VARCHAR) → DOUBLE
	auto number_func = ScalarFunction("fhirpath_number", {LogicalType::VARCHAR, LogicalType::VARCHAR},
	                                  LogicalType::DOUBLE, FhirpathNumberFunction, FhirpathBind);
	number_func.null_handling = FunctionNullHandling::SPECIAL_HANDLING;

	loader.RegisterFunction(number_func);

	// fhirpath_date(JSON, VARCHAR) → VARCHAR
	auto date_func = ScalarFunction("fhirpath_date", {LogicalType::VARCHAR, LogicalType::VARCHAR},
	                                LogicalType::VARCHAR, FhirpathDateFunction, FhirpathBind);
	date_func.null_handling = FunctionNullHandling::SPECIAL_HANDLING;

	loader.RegisterFunction(date_func);

	// fhirpath_bool(JSON, VARCHAR) → BOOLEAN
	auto bool_func = ScalarFunction("fhirpath_bool", {LogicalType::VARCHAR, LogicalType::VARCHAR},
	                                LogicalType::BOOLEAN, FhirpathBoolFunction, FhirpathBind);
	bool_func.null_handling = FunctionNullHandling::SPECIAL_HANDLING;

	loader.RegisterFunction(bool_func);

	// fhirpath_json(JSON, VARCHAR) → VARCHAR
	auto json_func = ScalarFunction("fhirpath_json", {LogicalType::VARCHAR, LogicalType::VARCHAR},
	                                LogicalType::VARCHAR, FhirpathJsonFunction, FhirpathBind);
	json_func.null_handling = FunctionNullHandling::SPECIAL_HANDLING;

	loader.RegisterFunction(json_func);

	// fhirpath_timestamp(JSON, VARCHAR) → VARCHAR
	auto timestamp_func = ScalarFunction("fhirpath_timestamp", {LogicalType::VARCHAR, LogicalType::VARCHAR},
	                                     LogicalType::VARCHAR, FhirpathTimestampFunction, FhirpathBind);
	timestamp_func.null_handling = FunctionNullHandling::SPECIAL_HANDLING;

	loader.RegisterFunction(timestamp_func);

	// fhirpath_quantity(JSON, VARCHAR) → VARCHAR
	auto quantity_func = ScalarFunction("fhirpath_quantity", {LogicalType::VARCHAR, LogicalType::VARCHAR},
	                                    LogicalType::VARCHAR, FhirpathQuantityFunction, FhirpathBind);
	quantity_func.null_handling = FunctionNullHandling::SPECIAL_HANDLING;

	loader.RegisterFunction(quantity_func);

	// fhirpath_is_valid(VARCHAR) → BOOLEAN
	auto is_valid_func = ScalarFunction("fhirpath_is_valid", {LogicalType::VARCHAR}, LogicalType::BOOLEAN,
	                                    FhirpathIsValidFunction, FhirpathBind);

	loader.RegisterFunction(is_valid_func);

	// fhirpath_predicate(JSON, VARCHAR) → VARCHAR[]
	auto predicate_func = ScalarFunction("fhirpath_predicate", {LogicalType::VARCHAR, LogicalType::VARCHAR},
	                                     LogicalType::LIST(LogicalType::VARCHAR), FhirpathPredicateFunction, FhirpathBind);
	loader.RegisterFunction(predicate_func);
}

void FhirpathExtension::Load(ExtensionLoader &loader) {
	LoadInternal(loader);
}

std::string FhirpathExtension::Name() {
	return "fhirpath";
}

std::string FhirpathExtension::Version() const {
#ifdef EXT_VERSION_FHIRPATH
	return EXT_VERSION_FHIRPATH;
#else
	return "0.1.0";
#endif
}

} // namespace duckdb

extern "C" {

DUCKDB_CPP_EXTENSION_ENTRY(fhirpath, loader) {
	duckdb::LoadInternal(loader);
}
}
