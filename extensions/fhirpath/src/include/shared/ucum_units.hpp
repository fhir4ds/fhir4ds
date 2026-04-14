#pragma once
// Shared UCUM unit conversion table for FHIRPath and CQL quantity operations.
// Canonical source: duckdb-fhirpath-cpp/src/include/shared/ucum_units.hpp
// Used by: duckdb-fhirpath-cpp (evaluator.cpp) and duckdb-cql-cpp (quantity.cpp)

#include <string>
#include <unordered_map>

namespace fhir {

struct UnitConversion {
	std::string base_unit;
	double factor; // multiply value by this to get base unit
};

// Returns the canonical UCUM unit conversion table.
// All time units normalize to seconds, length to meters, weight to grams, etc.
inline const std::unordered_map<std::string, UnitConversion> &GetUcumUnitTable() {
	static const std::unordered_map<std::string, UnitConversion> table = {
	    // ---- Time -> base: seconds ----
	    {"ms", {"s", 0.001}},
	    {"'ms'", {"s", 0.001}},
	    {"millisecond", {"s", 0.001}},
	    {"milliseconds", {"s", 0.001}},
	    {"s", {"s", 1.0}},
	    {"'s'", {"s", 1.0}},
	    {"second", {"s", 1.0}},
	    {"seconds", {"s", 1.0}},
	    {"min", {"s", 60.0}},
	    {"'min'", {"s", 60.0}},
	    {"minute", {"s", 60.0}},
	    {"minutes", {"s", 60.0}},
	    {"h", {"s", 3600.0}},
	    {"'h'", {"s", 3600.0}},
	    {"hour", {"s", 3600.0}},
	    {"hours", {"s", 3600.0}},
	    {"d", {"s", 86400.0}},
	    {"'d'", {"s", 86400.0}},
	    {"day", {"s", 86400.0}},
	    {"days", {"s", 86400.0}},
	    {"wk", {"s", 604800.0}},
	    {"'wk'", {"s", 604800.0}},
	    {"week", {"s", 604800.0}},
	    {"weeks", {"s", 604800.0}},
	    {"mo", {"s", 2629746.0}},      // avg month: 365.2425/12 * 86400
	    {"month", {"s", 2629746.0}},
	    {"months", {"s", 2629746.0}},
	    {"a", {"s", 31556952.0}},       // avg year: 365.2425 * 86400
	    {"year", {"s", 31556952.0}},
	    {"years", {"s", 31556952.0}},

	    // ---- Length -> base: meters ----
	    {"mm", {"m", 0.001}},
	    {"'mm'", {"m", 0.001}},
	    {"cm", {"m", 0.01}},
	    {"'cm'", {"m", 0.01}},
	    {"m", {"m", 1.0}},
	    {"'m'", {"m", 1.0}},
	    {"km", {"m", 1000.0}},
	    {"'km'", {"m", 1000.0}},
	    {"[in_i]", {"m", 0.0254}},
	    {"'[in_i]'", {"m", 0.0254}},
	    {"in", {"m", 0.0254}},
	    {"inch", {"m", 0.0254}},
	    {"[ft_i]", {"m", 0.3048}},
	    {"'[ft_i]'", {"m", 0.3048}},
	    {"ft", {"m", 0.3048}},
	    {"foot", {"m", 0.3048}},

	    // ---- Area -> base: m2 ----
	    {"m2", {"m2", 1.0}},
	    {"'m2'", {"m2", 1.0}},
	    {"cm2", {"m2", 0.0001}},
	    {"'cm2'", {"m2", 0.0001}},

	    // ---- Weight -> base: grams ----
	    {"ug", {"g", 0.000001}},
	    {"'ug'", {"g", 0.000001}},
	    {"mg", {"g", 0.001}},
	    {"'mg'", {"g", 0.001}},
	    {"g", {"g", 1.0}},
	    {"'g'", {"g", 1.0}},
	    {"kg", {"g", 1000.0}},
	    {"'kg'", {"g", 1000.0}},
	    {"[lb_av]", {"g", 453.59237}},
	    {"'[lb_av]'", {"g", 453.59237}},
	    {"lb", {"g", 453.59237}},
	    {"[oz_av]", {"g", 28.349523}},
	    {"'[oz_av]'", {"g", 28.349523}},
	    {"oz", {"g", 28.349523}},

	    // ---- Volume -> base: liters ----
	    {"uL", {"L", 0.000001}},
	    {"mL", {"L", 0.001}},
	    {"dL", {"L", 0.1}},
	    {"L", {"L", 1.0}},

	    // ---- Pressure -> base: pascal ----
	    {"Pa", {"Pa", 1.0}},
	    {"kPa", {"Pa", 1000.0}},
	    {"mm[Hg]", {"Pa", 133.322}},
	    {"mmHg", {"Pa", 133.322}},
	    {"cm[H2O]", {"Pa", 98.0665}},
	    {"cmH2O", {"Pa", 98.0665}},

	    // ---- Temperature -> Celsius base (Fahrenheit requires special handling) ----
	    {"Cel", {"Cel", 1.0}},
	    {"[degF]", {"Cel", -1.0}},  // sentinel: handled specially by caller
	    {"degF", {"Cel", -1.0}},    // sentinel: handled specially by caller

	    // ---- Concentration (compound units, same-unit comparison) ----
	    {"mg/dL", {"mg/dL", 1.0}},
	    {"g/dL", {"mg/dL", 1000.0}},
	    {"mmol/L", {"mmol/L", 1.0}},
	    {"ug/mL", {"ug/mL", 1.0}},

	    // ---- Counts / rates ----
	    {"/min", {"/min", 1.0}},
	    {"1", {"1", 1.0}},         // dimensionless
	    {"%", {"1", 0.01}},        // percent to fraction
	};
	return table;
}

// Convert a value from the given unit to its base unit.
// Returns the converted value and sets base_unit to the canonical base.
// If the unit is unknown, returns the original value and sets base_unit = unit.
inline double ConvertToBaseUnit(double value, const std::string &unit, std::string &base_unit) {
	// Strip surrounding single quotes if present (UCUM literal form)
	std::string clean_unit = unit;
	if (clean_unit.size() >= 2 && clean_unit.front() == '\'' && clean_unit.back() == '\'') {
		clean_unit = clean_unit.substr(1, clean_unit.size() - 2);
	}

	const auto &table = GetUcumUnitTable();

	// Try exact match first, then cleaned version
	auto it = table.find(unit);
	if (it == table.end()) {
		it = table.find(clean_unit);
	}

	if (it != table.end()) {
		base_unit = it->second.base_unit;
		return value * it->second.factor;
	}

	base_unit = unit;
	return value;
}

} // namespace fhir
