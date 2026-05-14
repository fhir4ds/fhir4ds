#include "cql/valueset.hpp"
#include "yyjson.hpp"

#include <cctype>
#include <mutex>

using namespace duckdb_yyjson; // NOLINT

namespace cql {

namespace {

const char *PROFILE_URL_MARKER = "/StructureDefinition/";
const char *PROFILE_PREFIXES[] = {"qicore", "uscore"};
const char *PROFILE_STATUS_SUFFIXES[] = {"notrequested", "notdone", "cancelled", "rejected"};
const char *NOT_DONE_VALUESET_EXT = "http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-notDoneValueSet";

const std::unordered_map<std::string, std::string> &oid_system_map() {
	static const std::unordered_map<std::string, std::string> systems = {
	    {"urn:oid:2.16.840.1.113883.6.96", "http://snomed.info/sct"},
	    {"urn:oid:2.16.840.1.113883.6.1", "http://loinc.org"},
	    {"urn:oid:2.16.840.1.113883.6.88", "http://www.nlm.nih.gov/research/umls/rxnorm"},
	    {"urn:oid:2.16.840.1.113883.6.90", "http://hl7.org/fhir/sid/icd-10-cm"},
	    {"urn:oid:2.16.840.1.113883.6.3", "http://hl7.org/fhir/sid/icd-10"},
	    {"urn:oid:2.16.840.1.113883.6.103", "http://hl7.org/fhir/sid/icd-9-cm"},
	    {"urn:oid:2.16.840.1.113883.6.12", "http://www.ama-assn.org/go/cpt"},
	    {"urn:oid:2.16.840.1.113883.6.285", "https://www.cms.gov/Medicare/Coding/HCPCSReleaseCodeSets"},
	    {"urn:oid:2.16.840.1.113883.6.14", "http://terminology.hl7.org/CodeSystem/HCPCS"},
	    {"urn:oid:2.16.840.1.113883.12.292", "http://hl7.org/fhir/sid/cvx"},
	    {"urn:oid:2.16.840.1.113883.6.69", "http://hl7.org/fhir/sid/ndc"},
	    {"urn:oid:2.16.840.1.113883.4.642.3.1", "http://hl7.org/fhir/administrative-gender"},
	    {"urn:oid:2.16.840.1.113883.5.4", "http://terminology.hl7.org/CodeSystem/v3-ActCode"},
	    {"urn:oid:2.16.840.1.113883.4.642.1.1125", "http://terminology.hl7.org/CodeSystem/observation-category"},
	    {"urn:oid:2.16.840.1.113883.4.642.1.1074", "http://terminology.hl7.org/CodeSystem/condition-clinical"},
	    {"urn:oid:2.16.840.1.113883.4.642.1.1075", "http://terminology.hl7.org/CodeSystem/condition-ver-status"},
	};
	return systems;
}

const std::unordered_map<std::string, std::string> &qicore_extension_props() {
	static const std::unordered_map<std::string, std::string> props = {
	    {"notDoneReason", "http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-notDoneReason"},
	    {"doNotPerformReason", "http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-doNotPerformReason"},
	    {"reasonRefused", "http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-doNotPerformReason"},
	};
	return props;
}

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

bool is_simple_path_segment(const std::string &part) {
	if (part.empty()) {
		return false;
	}
	for (char ch : part) {
		auto uch = static_cast<unsigned char>(ch);
		if (!(std::isalnum(uch) || ch == '_' || ch == '-')) {
			return false;
		}
	}
	return true;
}

bool split_simple_path(const std::string &path, std::vector<std::string> &parts) {
	parts.clear();
	if (path.empty()) {
		return false;
	}

	std::string current;
	for (char ch : path) {
		if (ch == '.') {
			if (!is_simple_path_segment(current)) {
				parts.clear();
				return false;
			}
			parts.push_back(current);
			current.clear();
			continue;
		}
		current.push_back(ch);
	}
	if (!is_simple_path_segment(current)) {
		parts.clear();
		return false;
	}
	parts.push_back(current);
	return true;
}

const std::vector<std::string> *cached_simple_path_parts(const std::string &path) {
	static std::unordered_map<std::string, std::vector<std::string>> simple_path_cache;
	static std::unordered_set<std::string> non_simple_path_cache;
	static std::mutex cache_mutex;

	std::lock_guard<std::mutex> lock(cache_mutex);
	auto it = simple_path_cache.find(path);
	if (it != simple_path_cache.end()) {
		return &it->second;
	}
	if (non_simple_path_cache.find(path) != non_simple_path_cache.end()) {
		return nullptr;
	}

	std::vector<std::string> parts;
	if (!split_simple_path(path, parts)) {
		non_simple_path_cache.insert(path);
		return nullptr;
	}
	auto inserted = simple_path_cache.emplace(path, std::move(parts));
	return &inserted.first->second;
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

std::vector<std::string> split_fhir_path(const std::string &path) {
	std::vector<std::string> parts;
	std::string current;
	int paren_depth = 0;
	bool in_quote = false;
	for (size_t i = 0; i < path.size(); i++) {
		char ch = path[i];
		if (ch == '\'') {
			in_quote = !in_quote;
			current.push_back(ch);
			continue;
		}
		if (!in_quote) {
			if (ch == '(') {
				paren_depth++;
			} else if (ch == ')' && paren_depth > 0) {
				paren_depth--;
			} else if (ch == '.' && paren_depth == 0) {
				if (path.compare(i + 1, 6, "where(") == 0) {
					current.push_back(ch);
					continue;
				}
				if (!current.empty()) {
					parts.push_back(current);
					current.clear();
				}
				continue;
			}
		}
		current.push_back(ch);
	}
	if (!current.empty()) {
		parts.push_back(current);
	}
	return parts;
}

std::string extract_extension_url_filter(const std::string &part) {
	const std::string prefix = "extension.where(";
	if (!starts_with(part, prefix)) {
		return "";
	}
	auto url_pos = part.find("url=");
	if (url_pos == std::string::npos) {
		return "";
	}
	auto quote_start = part.find('\'', url_pos);
	if (quote_start == std::string::npos) {
		return "";
	}
	auto quote_end = part.find('\'', quote_start + 1);
	if (quote_end == std::string::npos) {
		return "";
	}
	return part.substr(quote_start + 1, quote_end - quote_start - 1);
}

yyjson_val *first_list_item(yyjson_val *value) {
	if (!value || !yyjson_is_arr(value) || yyjson_arr_size(value) == 0) {
		return nullptr;
	}
	return yyjson_arr_get(value, 0);
}

yyjson_val *resolve_extension_value(yyjson_val *object, const std::string &extension_url) {
	if (!object || !yyjson_is_obj(object)) {
		return nullptr;
	}
	yyjson_val *extensions = yyjson_obj_get(object, "extension");
	if (!extensions || !yyjson_is_arr(extensions)) {
		return nullptr;
	}
	size_t idx, max;
	yyjson_val *ext;
	yyjson_arr_foreach(extensions, idx, max, ext) {
		if (!yyjson_is_obj(ext)) {
			continue;
		}
		yyjson_val *url = yyjson_obj_get(ext, "url");
		if (!url || !yyjson_is_str(url) || extension_url != yyjson_get_str(url)) {
			continue;
		}
		const char *value_keys[] = {"valueCodeableConcept", "valueCoding", "valueCode", "valueCanonical"};
		for (auto *key : value_keys) {
			yyjson_val *value = yyjson_obj_get(ext, key);
			if (value) {
				return value;
			}
		}
	}
	return nullptr;
}

yyjson_val *find_extension(yyjson_val *object, const std::string &extension_url) {
	if (!object || !yyjson_is_obj(object)) {
		return nullptr;
	}
	yyjson_val *extensions = yyjson_obj_get(object, "extension");
	if (!extensions || !yyjson_is_arr(extensions)) {
		return nullptr;
	}
	size_t idx, max;
	yyjson_val *ext;
	yyjson_arr_foreach(extensions, idx, max, ext) {
		if (!yyjson_is_obj(ext)) {
			continue;
		}
		yyjson_val *url = yyjson_obj_get(ext, "url");
		if (url && yyjson_is_str(url) && extension_url == yyjson_get_str(url)) {
			return ext;
		}
	}
	return nullptr;
}

yyjson_val *resolve_child(yyjson_val *current, const std::string &part) {
	if (!current) {
		return nullptr;
	}
	bool from_array = false;
	if (yyjson_is_arr(current)) {
		current = first_list_item(current);
		from_array = true;
	}
	if (!current || !yyjson_is_obj(current)) {
		return nullptr;
	}

	auto extension_url = extract_extension_url_filter(part);
	if (!extension_url.empty()) {
		return find_extension(current, extension_url);
	}

	yyjson_val *value = yyjson_obj_get(current, part.c_str());
	if (!value && !from_array) {
		const char *suffixes[] = {"CodeableConcept", "Coding"};
		for (auto *suffix : suffixes) {
			auto choice_key = part + suffix;
			value = yyjson_obj_get(current, choice_key.c_str());
			if (value) {
				break;
			}
		}
	}
	if (!value && !from_array) {
		const auto &props = qicore_extension_props();
		auto it = props.find(part);
		if (it != props.end()) {
			value = resolve_extension_value(current, it->second);
		}
	}
	return value;
}

yyjson_val *resolve_simple_child(yyjson_val *current, const std::string &part) {
	if (!current) {
		return nullptr;
	}
	bool from_array = false;
	if (yyjson_is_arr(current)) {
		current = first_list_item(current);
		from_array = true;
	}
	if (!current || !yyjson_is_obj(current)) {
		return nullptr;
	}

	yyjson_val *value = yyjson_obj_get(current, part.c_str());
	if (!value && !from_array) {
		const char *suffixes[] = {"CodeableConcept", "Coding"};
		for (auto *suffix : suffixes) {
			auto choice_key = part + suffix;
			value = yyjson_obj_get(current, choice_key.c_str());
			if (value) {
				break;
			}
		}
	}
	if (!value && !from_array) {
		const auto &props = qicore_extension_props();
		auto it = props.find(part);
		if (it != props.end()) {
			value = resolve_extension_value(current, it->second);
		}
	}
	return value;
}

yyjson_val *resolve_path(yyjson_val *root, const std::string &path) {
	if (const auto *simple_parts = cached_simple_path_parts(path)) {
		yyjson_val *current = root;
		for (const auto &part : *simple_parts) {
			current = resolve_simple_child(current, part);
			if (!current) {
				return nullptr;
			}
		}
		return current;
	}

	auto parts = split_fhir_path(path);
	yyjson_val *current = root;
	for (const auto &part : parts) {
		current = resolve_child(current, part);
		if (!current) {
			return nullptr;
		}
	}
	return current;
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
	} else if (yyjson_is_str(val)) {
		const char *raw = yyjson_get_str(val);
		if (!raw) {
			return;
		}
		std::string nested(raw);
		auto first = nested.find_first_not_of(" \t\r\n");
		if (first == std::string::npos || (nested[first] != '{' && nested[first] != '[')) {
			return;
		}
		yyjson_doc *nested_doc = yyjson_read(nested.c_str(), nested.size(), 0);
		if (!nested_doc) {
			return;
		}
		extract_codes_from_val(yyjson_doc_get_root(nested_doc), codes);
		yyjson_doc_free(nested_doc);
	}
}

static bool has_not_done_valueset_value(yyjson_val *val, const std::string &valueset_url) {
	if (!val || !yyjson_is_obj(val)) {
		return false;
	}
	yyjson_val *extensions = yyjson_obj_get(val, "extension");
	if (!extensions || !yyjson_is_arr(extensions)) {
		return false;
	}

	auto canonical_target = canonicalize_url(valueset_url);
	size_t idx, max;
	yyjson_val *ext;
	yyjson_arr_foreach(extensions, idx, max, ext) {
		if (!yyjson_is_obj(ext)) {
			continue;
		}
		yyjson_val *url = yyjson_obj_get(ext, "url");
		if (!url || !yyjson_is_str(url) || std::string(yyjson_get_str(url)) != NOT_DONE_VALUESET_EXT) {
			continue;
		}
		yyjson_val *value = yyjson_obj_get(ext, "valueCanonical");
		if (value && yyjson_is_str(value) && canonicalize_url(yyjson_get_str(value)) == canonical_target) {
			return true;
		}
	}
	return false;
}

std::vector<CodeValue> extract_codes(const std::string &resource_json, const std::string &path) {
	std::vector<CodeValue> codes;

	yyjson_doc *doc = yyjson_read(resource_json.c_str(), resource_json.size(), 0);
	if (!doc) {
		return codes;
	}

	yyjson_val *root = yyjson_doc_get_root(doc);
	yyjson_val *val = resolve_path(root, path);

	extract_codes_from_val(val, codes);

	yyjson_doc_free(doc);
	return codes;
}

CodeExtractionResult extract_codes_with_not_done_valueset(const std::string &resource_json, const std::string &path,
                                                          const std::string &valueset_url) {
	CodeExtractionResult result;

	yyjson_doc *doc = yyjson_read(resource_json.c_str(), resource_json.size(), 0);
	if (!doc) {
		return result;
	}

	yyjson_val *root = yyjson_doc_get_root(doc);
	yyjson_val *val = resolve_path(root, path);
	extract_codes_from_val(val, result.codes);
	if (result.codes.empty()) {
		result.has_not_done_valueset = has_not_done_valueset_value(val, valueset_url);
	}

	yyjson_doc_free(doc);
	return result;
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

std::string normalize_system(const std::string &system) {
	const auto &systems = oid_system_map();
	auto it = systems.find(system);
	if (it != systems.end()) {
		return it->second;
	}
	const std::string snomed_prefix = "http://snomed.info/sct";
	if (starts_with(system, snomed_prefix) && system.size() > snomed_prefix.size()) {
		return snomed_prefix;
	}
	return system;
}

std::string canonicalize_url(const std::string &url) {
	return canonicalize_profile_url(url);
}

bool has_not_done_valueset(const std::string &resource_json, const std::string &path, const std::string &valueset_url) {
	yyjson_doc *doc = yyjson_read(resource_json.c_str(), resource_json.size(), 0);
	if (!doc) {
		return false;
	}

	yyjson_val *root = yyjson_doc_get_root(doc);
	yyjson_val *val = resolve_path(root, path);
	bool found = has_not_done_valueset_value(val, valueset_url);
	yyjson_doc_free(doc);
	return found;
}

} // namespace cql
