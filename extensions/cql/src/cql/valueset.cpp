#include "cql/valueset.hpp"
#include "yyjson.hpp"

#include <cctype>

using namespace duckdb_yyjson; // NOLINT

namespace cql {

namespace {

const char *PROFILE_URL_MARKER = "/StructureDefinition/";
const char *PROFILE_PREFIXES[] = {"qicore", "uscore"};
const char *PROFILE_STATUS_SUFFIXES[] = {"notrequested", "notdone", "cancelled", "rejected"};

const std::unordered_map<std::string, std::string> &normalized_resource_types() {
	static const std::unordered_map<std::string, std::string> resource_types = {
	    {"allergyintolerance", "AllergyIntolerance"},
	    {"bundle", "Bundle"},
	    {"careplan", "CarePlan"},
	    {"communication", "Communication"},
	    {"communicationrequest", "CommunicationRequest"},
	    {"composition", "Composition"},
	    {"condition", "Condition"},
	    {"devicerequest", "DeviceRequest"},
	    {"diagnosticreport", "DiagnosticReport"},
	    {"documentreference", "DocumentReference"},
	    {"encounter", "Encounter"},
	    {"immunization", "Immunization"},
	    {"location", "Location"},
	    {"medication", "Medication"},
	    {"medicationadministration", "MedicationAdministration"},
	    {"medicationrequest", "MedicationRequest"},
	    {"observation", "Observation"},
	    {"operationoutcome", "OperationOutcome"},
	    {"organization", "Organization"},
	    {"patient", "Patient"},
	    {"practitioner", "Practitioner"},
	    {"procedure", "Procedure"},
	    {"servicerequest", "ServiceRequest"},
	    {"specimen", "Specimen"},
	    {"task", "Task"},
	};
	return resource_types;
}

const std::unordered_map<std::string, std::string> &profile_resource_aliases() {
	static const std::unordered_map<std::string, std::string> aliases = {
	    {"bmi", "Observation"},
	    {"bloodpressure", "Observation"},
	    {"bodyheight", "Observation"},
	    {"bodytemperature", "Observation"},
	    {"bodyweight", "Observation"},
	    {"heartrate", "Observation"},
	    {"laboratoryresultobservation", "Observation"},
	    {"pulseoximetry", "Observation"},
	    {"respiratoryrate", "Observation"},
	    {"simpleobservation", "Observation"},
	    {"smokingstatus", "Observation"},
	};
	return aliases;
}

std::string normalize_profile_token(const std::string &value) {
	std::string normalized;
	normalized.reserve(value.size());
	for (char ch : value) {
		if (std::isalnum(static_cast<unsigned char>(ch))) {
			normalized.push_back(static_cast<char>(std::tolower(static_cast<unsigned char>(ch))));
		}
	}
	return normalized;
}

bool starts_with(const std::string &value, const std::string &prefix) {
	return value.size() >= prefix.size() && value.compare(0, prefix.size(), prefix) == 0;
}

bool ends_with(const std::string &value, const std::string &suffix) {
	return value.size() >= suffix.size() &&
	       value.compare(value.size() - suffix.size(), suffix.size(), suffix) == 0;
}

std::string canonicalize_profile_url(const std::string &profile_url) {
	auto version_pos = profile_url.find('|');
	std::string canonical = profile_url.substr(0, version_pos);
	while (!canonical.empty() && canonical.back() == '/') {
		canonical.pop_back();
	}
	return canonical;
}

std::string strip_profile_namespace(const std::string &profile_slug) {
	for (auto *prefix : PROFILE_PREFIXES) {
		if (starts_with(profile_slug, prefix)) {
			return profile_slug.substr(std::strlen(prefix));
		}
	}
	return profile_slug;
}

std::string resolve_profile_slug(const std::string &profile_slug) {
	const auto &resource_types = normalized_resource_types();
	auto it = resource_types.find(profile_slug);
	if (it != resource_types.end()) {
		return it->second;
	}

	const auto &aliases = profile_resource_aliases();
	it = aliases.find(profile_slug);
	if (it != aliases.end()) {
		return it->second;
	}

	for (auto *suffix : PROFILE_STATUS_SUFFIXES) {
		if (!ends_with(profile_slug, suffix)) {
			continue;
		}

		auto stem = profile_slug.substr(0, profile_slug.size() - std::strlen(suffix));
		if (std::string(suffix) == "notrequested") {
			auto request_slug = stem + "request";
			auto request_it = resource_types.find(request_slug);
			if (request_it != resource_types.end()) {
				return request_it->second;
			}
		}

		auto stem_it = resource_types.find(stem);
		if (stem_it != resource_types.end()) {
			return stem_it->second;
		}

		auto alias_it = aliases.find(stem);
		if (alias_it != aliases.end()) {
			return alias_it->second;
		}
	}

	std::string best_match;
	size_t best_match_len = 0;
	for (const auto &entry : resource_types) {
		if (starts_with(profile_slug, entry.first) && entry.first.size() > best_match_len) {
			best_match = entry.second;
			best_match_len = entry.first.size();
		}
	}

	return best_match;
}

} // namespace

static void extract_codes_from_val(yyjson_val *val, std::vector<CodeValue> &codes) {
	if (!val) {
		return;
	}

	if (yyjson_is_obj(val)) {
		// Check if this is a Coding object (has system and code)
		yyjson_val *system_val = yyjson_obj_get(val, "system");
		yyjson_val *code_val = yyjson_obj_get(val, "code");
		if (system_val && code_val && yyjson_is_str(system_val) && yyjson_is_str(code_val)) {
			codes.push_back({yyjson_get_str(system_val), yyjson_get_str(code_val)});
		}

		// Check for nested coding array
		yyjson_val *coding = yyjson_obj_get(val, "coding");
		if (coding && yyjson_is_arr(coding)) {
			size_t idx, max;
			yyjson_val *elem;
			yyjson_arr_foreach(coding, idx, max, elem) {
				extract_codes_from_val(elem, codes);
			}
		}
	} else if (yyjson_is_arr(val)) {
		size_t idx, max;
		yyjson_val *elem;
		yyjson_arr_foreach(val, idx, max, elem) {
			extract_codes_from_val(elem, codes);
		}
	}
}

std::vector<CodeValue> extract_codes(const std::string &resource_json, const std::string &path) {
	std::vector<CodeValue> codes;

	yyjson_doc *doc = yyjson_read(resource_json.c_str(), resource_json.size(), 0);
	if (!doc) {
		return codes;
	}

	yyjson_val *root = yyjson_doc_get_root(doc);
	yyjson_val *val = yyjson_obj_get(root, path.c_str());

	extract_codes_from_val(val, codes);

	yyjson_doc_free(doc);
	return codes;
}

std::string extract_first_code(const std::string &resource_json, const std::string &path) {
	auto codes = extract_codes(resource_json, path);
	if (codes.empty()) {
		return "";
	}
	return codes[0].system + "|" + codes[0].code;
}

std::string extract_first_code_system(const std::string &resource_json, const std::string &path) {
	auto codes = extract_codes(resource_json, path);
	if (codes.empty()) {
		return "";
	}
	return codes[0].system;
}

std::string extract_first_code_value(const std::string &resource_json, const std::string &path) {
	auto codes = extract_codes(resource_json, path);
	if (codes.empty()) {
		return "";
	}
	return codes[0].code;
}

std::string resolve_profile_url(const std::string &profile_url) {
	auto canonical_url = canonicalize_profile_url(profile_url);
	auto marker_pos = canonical_url.rfind(PROFILE_URL_MARKER);
	if (marker_pos == std::string::npos) {
		return "";
	}

	auto profile_slug = normalize_profile_token(
	    canonical_url.substr(marker_pos + std::strlen(PROFILE_URL_MARKER))
	);
	profile_slug = strip_profile_namespace(profile_slug);
	if (profile_slug.empty()) {
		return "";
	}

	return resolve_profile_slug(profile_slug);
}

bool in_valueset(const std::string &code, const std::string &system, const std::string &valueset_url,
                 const ValuesetCache &cache) {
	auto it = cache.find(valueset_url);
	if (it == cache.end()) {
		return false;
	}
	return it->second.count(system + "|" + code) > 0;
}

} // namespace cql
