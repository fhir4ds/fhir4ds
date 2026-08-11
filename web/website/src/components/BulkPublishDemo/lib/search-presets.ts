/**
 * Static preset lists and types for the search form. Kept in a separate file
 * from search.ts so the presets/types can be imported by App sections that
 * don't need the query composer.
 */

export interface SearchInputs {
  status: string;
  specialty: string;
  dateFrom: string;
  dateTo: string;
  /** City key from CITIES preset list. Empty string = no geo filter. */
  city: string;
  /** Maximum distance in miles. 0 = no geo filter. */
  radiusMiles: number;
}

export function todayPlus(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}

export const DEFAULT_INPUTS: SearchInputs = {
  status: "free",
  specialty: "",
  dateFrom: todayPlus(0),
  dateTo: todayPlus(14),
  city: "Minneapolis",
  radiusMiles: 25,
};

export const SPECIALTIES = [
  { code: "", label: "(any)" },
  { code: "primary-care", label: "Primary Care" },
  { code: "cardiology", label: "Cardiology" },
  { code: "dermatology", label: "Dermatology" },
  { code: "pediatrics", label: "Pediatrics" },
  { code: "orthopedics", label: "Orthopedics" },
];

/** City presets with centroid lat/lon. Drawn from the synthesizer's TC_ZIPS. */
export interface City {
  city: string;
  label: string;
  lat: number;
  lon: number;
}

export const CITIES: City[] = [
  { city: "", label: "(any location)", lat: 0, lon: 0 },
  { city: "Minneapolis", label: "Minneapolis", lat: 44.98, lon: -93.275 },
  { city: "Saint Paul", label: "Saint Paul", lat: 44.954, lon: -93.09 },
  { city: "Rochester", label: "Rochester (Mayo)", lat: 44.021, lon: -92.465 },
  { city: "Burnsville", label: "Burnsville", lat: 44.77, lon: -93.278 },
  { city: "Maple Grove", label: "Maple Grove", lat: 45.102, lon: -93.456 },
];

export const RADII = [0, 5, 10, 25, 50, 100];

/** Known FHIR resource types in the published feed (used by the resource browser). */
export const RESOURCE_TYPES = [
  "Slot",
  "Schedule",
  "Location",
  "Practitioner",
  "PractitionerRole",
  "HealthcareService",
];
