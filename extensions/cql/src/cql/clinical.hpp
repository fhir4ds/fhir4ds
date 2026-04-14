#pragma once

#include <string>
#include <vector>
#include "cql/optional.hpp"

namespace cql {

Optional<std::string> find_latest(const std::vector<std::string> &resources, const std::string &date_path);
Optional<std::string> find_earliest(const std::vector<std::string> &resources, const std::string &date_path);
Optional<std::string> claim_principal_diagnosis(const std::string &claim_json, const std::string &encounter_id);
Optional<std::string> claim_principal_procedure(const std::string &claim_json, const std::string &encounter_id);

} // namespace cql
