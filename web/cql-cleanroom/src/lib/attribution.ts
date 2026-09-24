/**
 * Loader patient-attribution doctrine mirror (FEATURE_CLEANROOM_TEST_DATA_AUTHORING.md §3.2).
 *
 * attributePatient() must replicate fhir4ds/cql/loader/fhir_loader.py
 * `_extract_patient_ref` EXACTLY: the loader scans ONLY subject >
 * patient > beneficiary, requires a Reference OBJECT with a string
 * `reference`, attributes urn:uuid unconditionally, skips bare ids,
 * strips `/_history/{vid}`, and requires `segments[-2] === "Patient"`
 * (or the first Patient-typed entry for list-valued fields).
 *
 * The test table is the SHARED fixture
 * fhir4ds/operations/tests/fixtures/attribution_doctrine_cases.json
 * (F5: consumed by BOTH pytest and vitest — a Python loader change
 * fails here too).
 */

const ATTRIBUTION_FIELDS = ["subject", "patient", "beneficiary"] as const;

export function attributePatient(resource: Record<string, unknown>): string | null {
  const resourceType = resource.resourceType;
  if (resourceType === "Patient") {
    const id = resource.id;
    return typeof id === "string" ? id : null;
  }
  for (const path of ATTRIBUTION_FIELDS) {
    const value = resource[path];
    const candidates = Array.isArray(value) ? value : [value];
    for (const refObj of candidates) {
      if (!refObj || typeof refObj !== "object" || Array.isArray(refObj)) continue;
      const reference = (refObj as Record<string, unknown>).reference;
      if (typeof reference !== "string" || !reference) continue;
      if (reference.startsWith("urn:uuid:")) return reference.slice("urn:uuid:".length);
      if (!reference.includes("/")) continue; // bare id: no target type
      let segments = reference.split("/").filter((s) => s.length > 0);
      if (segments.length >= 2 && segments[segments.length - 2] === "_history") {
        segments = segments.slice(0, -2);
      }
      if (segments.length >= 2 && segments[segments.length - 2] === "Patient") {
        return segments[segments.length - 1];
      }
    }
  }
  return null;
}

export interface DoctrineCase {
  id: string;
  why: string;
  resource: Record<string, unknown>;
  expected: string | null;
}
