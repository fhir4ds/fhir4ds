#pragma once

#include <string>
#include <unordered_map>
#include <unordered_set>
#include <vector>

namespace cql {

struct CodeValue {
	std::string system;
	std::string code;
};

std::vector<CodeValue> extract_codes(const std::string &resource_json, const std::string &path);
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

} // namespace cql
