// Compatibility shims so ONE source tree builds every bundled DuckDB ABI
// (1.5.5 / 1.5.6 / 2.0.0).
//
// DuckDB 2.0 split the vector headers and tightened const-correctness:
//   * FlatVector / ListVector moved to duckdb/common/vector/{flat,list}_vector.hpp
//   * FlatVector::GetData(Vector&) now returns READ-ONLY data; writing requires
//     GetDataMutable (1.5.x has a single mutable GetData<T>)
//   * FlatVector::Validity() returns const ValidityMask& (1.5.x returns mutable)
//
// Without these helpers, cql_extension.cpp reports 863 errors and
// fhirpath_extension.cpp 79 against v2.0.0 at -std=c++17.
//
// Detection is by header presence, not version macros: <duckdb/common/vector/
// flat_vector.hpp> exists in 2.0.0 and in none of the 1.5.x tags.
#pragma once

#if defined(__has_include)
#if __has_include("duckdb/common/vector/flat_vector.hpp")
#define FHIR4DS_DUCKDB_V2 1
#endif
#endif

#include "duckdb/common/types/vector.hpp"

#ifdef FHIR4DS_DUCKDB_V2
#include "duckdb/common/vector/flat_vector.hpp"
#include "duckdb/common/vector/list_vector.hpp"
#endif

namespace fhir4ds_compat {

// Mutable validity mask of a FLAT result vector.
//
// The const_cast is safe because every call site passes the function's own
// result Vector that it is about to populate; DuckDB 2.0 simply exposes the
// mask as const on the non-mutating accessor. Reads of INPUT vectors go through
// UnifiedVectorFormat and never use this.
inline duckdb::ValidityMask &validity(duckdb::Vector &vector) {
#ifdef FHIR4DS_DUCKDB_V2
	return const_cast<duckdb::ValidityMask &>(duckdb::FlatVector::Validity(vector));
#else
	return duckdb::FlatVector::Validity(vector);
#endif
}

// Mutable typed data pointer of a FLAT result vector (see `validity`).
template <typename T>
inline T *data(duckdb::Vector &vector) {
#ifdef FHIR4DS_DUCKDB_V2
	return duckdb::FlatVector::GetDataMutable<T>(vector);
#else
	return duckdb::FlatVector::GetData<T>(vector);
#endif
}


// --- Expression bind data -------------------------------------------------
//
// DuckDB 2.0 made BoundFunctionExpression::bind_info and
// BoundConstantExpression::value private, exposing BindInfo()/GetValue().

// Templates so the expression types only need to be complete at the CALL SITE
// (the planner headers are not includable this early in every DuckDB version).
template <typename Expr>
inline duckdb::FunctionData *bind_info(Expr &expr) {
#ifdef FHIR4DS_DUCKDB_V2
	return expr.BindInfo().get();
#else
	return expr.bind_info.get();
#endif
}

template <typename Expr>
inline const duckdb::Value &const_value(Expr &expr) {
#ifdef FHIR4DS_DUCKDB_V2
	return expr.GetValue();
#else
	return expr.value;
#endif
}

// --- Scalar-function bind callback ---------------------------------------
//
// 2.0 passes a single BindScalarFunctionInput& instead of
// (ClientContext&, ScalarFunction&, vector<unique_ptr<Expression>>&).
// Our bind callbacks never use the ScalarFunction argument, so the 2.0 adapter
// simply forwards context + arguments.
#ifdef FHIR4DS_DUCKDB_V2
#define FHIR4DS_BIND_FN(fn) \
	([](duckdb::BindScalarFunctionInput &input) -> duckdb::unique_ptr<duckdb::FunctionData> { \
		return fn(input.GetClientContext(), input.GetArguments()); \
	})
#else
#define FHIR4DS_BIND_FN(fn) fn
#endif

} // namespace fhir4ds_compat
