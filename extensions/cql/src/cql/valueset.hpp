#pragma once

#include "optional.hpp"

#include <string>
#include <unordered_map>
#include <unordered_set>
#include <vector>

namespace cql {

struct CodeValue {
	std::string system;
	std::string code;
};

struct CodeExtractionResult {
	std::vector<CodeValue> codes;
	bool has_not_done_valueset = false;
};

std::vector<CodeValue> extract_codes(const std::string &resource_json, const std::string &path);
CodeExtractionResult extract_codes_with_not_done_valueset(const std::string &resource_json, const std::string &path,
                                                          const std::string &valueset_url);
std::string extract_first_code(const std::string &resource_json, const std::string &path);
std::string extract_first_code_system(const std::string &resource_json, const std::string &path);
std::string extract_first_code_value(const std::string &resource_json, const std::string &path);
std::string resolve_profile_url(const std::string &profile_url);

// Valueset membership cache: maps valueset_url → set of "system|code" strings
using ValuesetCache = std::unordered_map<std::string, std::unordered_set<std::string>>;

bool in_valueset(const std::string &code, const std::string &system, const std::string &valueset_url,
                 const ValuesetCache &cache);
std::string normalize_system(const std::string &system);
std::string canonicalize_url(const std::string &url);
bool has_not_done_valueset(const std::string &resource_json, const std::string &path, const std::string &valueset_url);

// CQL dynamic Code ~ / = against a retrieved coding at `path`.
// Both return NullOpt for NULL-equivalent inputs (null resource, empty
// path/code); FALSE when no coding matches; TRUE on match. Match rule:
// code equality plus system equality after normalization (OID aliases,
// SNOMED module URLs) OR raw system equality; the Python aliases
// QICoreCommon.SNOMEDCT / SNOMEDCT / LOINC are folded into the expected
// system before comparison. `coding_matches_exact` additionally requires
// display and version equality where an absent literal element (null)
// must also be absent in the coding (CQL Equal on Code semantics).
Optional<bool> coding_matches(const std::string &resource_json, const std::string &path, const std::string &system,
                              const std::string &code);
Optional<bool> coding_matches_exact(const std::string &resource_json, const std::string &path,
                                   const std::string &system, const std::string &code,
                                   const char *display, const char *version);

} // namespace cql
