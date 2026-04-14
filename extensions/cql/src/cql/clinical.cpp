#include "cql/clinical.hpp"
#include "cql/datetime.hpp"
#include "yyjson.hpp"

using namespace duckdb_yyjson; // NOLINT
#include <algorithm>

namespace cql {

static Optional<DateTimeValue> extract_date_from_json(const std::string &resource_json,
                                                           const std::string &date_path) {
	yyjson_doc *doc = yyjson_read(resource_json.c_str(), resource_json.size(), 0);
	if (!doc) {
		return NullOpt<DateTimeValue>();
	}

	yyjson_val *root = yyjson_doc_get_root(doc);
	yyjson_val *val = yyjson_obj_get(root, date_path.c_str());

	Optional<DateTimeValue> result;
	if (val && yyjson_is_str(val)) {
		result = DateTimeValue::parse(yyjson_get_str(val));
	}
	yyjson_doc_free(doc);
	return result;
}

Optional<std::string> find_latest(const std::vector<std::string> &resources, const std::string &date_path) {
	if (resources.empty()) {
		return NullOpt<std::string>();
	}

	Optional<std::string> best;
	Optional<DateTimeValue> best_date;

	for (const auto &res : resources) {
		auto dt = extract_date_from_json(res, date_path);
		if (dt) {
			if (!best_date || *dt > *best_date) {
				best_date = dt;
				best = res;
			}
		}
	}
	return best;
}

Optional<std::string> find_earliest(const std::vector<std::string> &resources, const std::string &date_path) {
	if (resources.empty()) {
		return NullOpt<std::string>();
	}

	Optional<std::string> best;
	Optional<DateTimeValue> best_date;

	for (const auto &res : resources) {
		auto dt = extract_date_from_json(res, date_path);
		if (dt) {
			if (!best_date || *dt < *best_date) {
				best_date = dt;
				best = res;
			}
		}
	}
	return best;
}

Optional<std::string> claim_principal_diagnosis(const std::string &claim_json, const std::string &encounter_id) {
	yyjson_doc *doc = yyjson_read(claim_json.c_str(), claim_json.size(), 0);
	if (!doc) {
		return NullOpt<std::string>();
	}

	yyjson_val *root = yyjson_doc_get_root(doc);

	// Step 1: collect diagnosisSequence values from items matching encounter_id
	std::vector<int> diag_seqs;
	yyjson_val *items = yyjson_obj_get(root, "item");
	if (items && yyjson_is_arr(items)) {
		size_t ii, imax;
		yyjson_val *item;
		yyjson_arr_foreach(items, ii, imax, item) {
			yyjson_val *enc_refs = yyjson_obj_get(item, "encounter");
			if (!enc_refs || !yyjson_is_arr(enc_refs)) continue;
			bool enc_match = false;
			size_t ei, emax;
			yyjson_val *enc;
			yyjson_arr_foreach(enc_refs, ei, emax, enc) {
				yyjson_val *ref = yyjson_obj_get(enc, "reference");
				if (ref && yyjson_is_str(ref)) {
					const char *ref_str = yyjson_get_str(ref);
					size_t ref_len = strlen(ref_str);
					size_t id_len = encounter_id.size();
					if (ref_len >= id_len &&
					    strcmp(ref_str + ref_len - id_len, encounter_id.c_str()) == 0) {
						enc_match = true;
						break;
					}
				}
			}
			if (!enc_match) continue;
			yyjson_val *ds_arr = yyjson_obj_get(item, "diagnosisSequence");
			if (ds_arr && yyjson_is_arr(ds_arr)) {
				size_t di, dmax;
				yyjson_val *dv;
				yyjson_arr_foreach(ds_arr, di, dmax, dv) {
					if (yyjson_is_int(dv)) diag_seqs.push_back(static_cast<int>(yyjson_get_int(dv)));
				}
			}
		}
	}

	// Step 2: find diagnosis with matching sequence and type.code == "principal"
	Optional<std::string> result;
	yyjson_val *diagnoses = yyjson_obj_get(root, "diagnosis");
	if (!diag_seqs.empty() && diagnoses && yyjson_is_arr(diagnoses)) {
		size_t di, dmax;
		yyjson_val *diag;
		yyjson_arr_foreach(diagnoses, di, dmax, diag) {
			yyjson_val *seq = yyjson_obj_get(diag, "sequence");
			if (!seq || !yyjson_is_int(seq)) continue;
			int seq_val = static_cast<int>(yyjson_get_int(seq));
			bool seq_match = false;
			for (size_t s = 0; s < diag_seqs.size(); s++) {
				if (diag_seqs[s] == seq_val) { seq_match = true; break; }
			}
			if (!seq_match) continue;
			yyjson_val *types = yyjson_obj_get(diag, "type");
			if (!types || !yyjson_is_arr(types)) continue;
			size_t ti, tmax;
			yyjson_val *type_cc;
			bool found = false;
			yyjson_arr_foreach(types, ti, tmax, type_cc) {
				yyjson_val *codings = yyjson_obj_get(type_cc, "coding");
				if (!codings || !yyjson_is_arr(codings)) continue;
				size_t ci, cmax;
				yyjson_val *coding;
				yyjson_arr_foreach(codings, ci, cmax, coding) {
					yyjson_val *code = yyjson_obj_get(coding, "code");
					if (code && yyjson_is_str(code) &&
					    strcmp(yyjson_get_str(code), "principal") == 0) {
						char *json = yyjson_val_write(diag, 0, nullptr);
						if (json) { result = std::string(json); free(json); }
						found = true;
						break;
					}
				}
				if (found) break;
			}
			if (found) break;
		}
	}

	yyjson_doc_free(doc);
	return result;
}

Optional<std::string> claim_principal_procedure(const std::string &claim_json, const std::string &encounter_id) {
	yyjson_doc *doc = yyjson_read(claim_json.c_str(), claim_json.size(), 0);
	if (!doc) {
		return NullOpt<std::string>();
	}

	yyjson_val *root = yyjson_doc_get_root(doc);

	// Step 1: collect procedureSequence values from items matching encounter_id
	std::vector<int> proc_seqs;
	yyjson_val *items = yyjson_obj_get(root, "item");
	if (items && yyjson_is_arr(items)) {
		size_t ii, imax;
		yyjson_val *item;
		yyjson_arr_foreach(items, ii, imax, item) {
			yyjson_val *enc_refs = yyjson_obj_get(item, "encounter");
			if (!enc_refs || !yyjson_is_arr(enc_refs)) continue;
			bool enc_match = false;
			size_t ei, emax;
			yyjson_val *enc;
			yyjson_arr_foreach(enc_refs, ei, emax, enc) {
				yyjson_val *ref = yyjson_obj_get(enc, "reference");
				if (ref && yyjson_is_str(ref)) {
					const char *ref_str = yyjson_get_str(ref);
					size_t ref_len = strlen(ref_str);
					size_t id_len = encounter_id.size();
					if (ref_len >= id_len &&
					    strcmp(ref_str + ref_len - id_len, encounter_id.c_str()) == 0) {
						enc_match = true;
						break;
					}
				}
			}
			if (!enc_match) continue;
			yyjson_val *ps_arr = yyjson_obj_get(item, "procedureSequence");
			if (ps_arr && yyjson_is_arr(ps_arr)) {
				size_t pi, pmax;
				yyjson_val *pv;
				yyjson_arr_foreach(ps_arr, pi, pmax, pv) {
					if (yyjson_is_int(pv)) proc_seqs.push_back(static_cast<int>(yyjson_get_int(pv)));
				}
			}
		}
	}

	// Step 2: find procedure with matching sequence and type.code == "primary"
	Optional<std::string> result;
	yyjson_val *procedures = yyjson_obj_get(root, "procedure");
	if (!proc_seqs.empty() && procedures && yyjson_is_arr(procedures)) {
		size_t pi, pmax;
		yyjson_val *proc;
		yyjson_arr_foreach(procedures, pi, pmax, proc) {
			yyjson_val *seq = yyjson_obj_get(proc, "sequence");
			if (!seq || !yyjson_is_int(seq)) continue;
			int seq_val = static_cast<int>(yyjson_get_int(seq));
			bool seq_match = false;
			for (size_t s = 0; s < proc_seqs.size(); s++) {
				if (proc_seqs[s] == seq_val) { seq_match = true; break; }
			}
			if (!seq_match) continue;
			yyjson_val *types = yyjson_obj_get(proc, "type");
			if (!types || !yyjson_is_arr(types)) continue;
			size_t ti, tmax;
			yyjson_val *type_cc;
			bool found = false;
			yyjson_arr_foreach(types, ti, tmax, type_cc) {
				yyjson_val *codings = yyjson_obj_get(type_cc, "coding");
				if (!codings || !yyjson_is_arr(codings)) continue;
				size_t ci, cmax;
				yyjson_val *coding;
				yyjson_arr_foreach(codings, ci, cmax, coding) {
					yyjson_val *code = yyjson_obj_get(coding, "code");
					if (code && yyjson_is_str(code) &&
					    strcmp(yyjson_get_str(code), "primary") == 0) {
						char *json = yyjson_val_write(proc, 0, nullptr);
						if (json) { result = std::string(json); free(json); }
						found = true;
						break;
					}
				}
				if (found) break;
			}
			if (found) break;
		}
	}

	yyjson_doc_free(doc);
	return result;
}

} // namespace cql
