#pragma once

#include <string>
#include "cql/optional.hpp"

namespace cql {

// List-based logical aggregates. Input is a JSON array of "true"/"false"/null strings.
Optional<bool> logical_all_true(const std::string &json_array);
Optional<bool> logical_any_true(const std::string &json_array);
Optional<bool> logical_all_false(const std::string &json_array);
Optional<bool> logical_any_false(const std::string &json_array);

// Two-valued implication (3-valued logic)
// a_null/b_null indicate SQL NULL inputs
Optional<bool> logical_implies(bool a_null, bool a, bool b_null, bool b);

// Coalesce: return first non-null element from JSON array
Optional<std::string> logical_coalesce(const std::string &json_array);

} // namespace cql
