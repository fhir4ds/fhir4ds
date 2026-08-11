/**
 * Hero ViewDefinition for the demo.
 *
 * Flattens Slot resources into one row per slot. Covers fields that exist
 * uniformly across all 5 providers' schema variants:
 *   - Slot's own scalar fields
 *   - The booking-deep-link extension
 *   - The serviceType specialty code
 *   - The schedule reference (used downstream to join to schedules)
 *
 * Per-provider schema variations (PractitionerRole vs direct Practitioner vs
 * contained PractitionerRole) are normalized in hand-written SQL that uses the
 * FHIR4DS fhirpath_* UDFs. See lib/cross-resource.ts. The split is honest:
 * ViewDefinition handles per-resource flattening; SQL handles cross-resource
 * composition across heterogeneous schemas. FHIR4DS contributes both layers.
 *
 * (FHIR4DS's ViewDefinition parser accepts a top-level `joins` clause per the
 * SQL-on-FHIR v2 spec, but the generator does not currently emit JOIN SQL for
 * it — a known gap we work around by composing in SQL.)
 */

export interface ViewDefinition {
  resource: string;
  select: Array<{
    column?: Array<{ path: string; name: string }>;
    select?: Array<{ column: Array<{ path: string; name: string }> }>;
  }>;
  where?: Array<{ path: string }>;
}

export const SLOTS_VIEW: ViewDefinition = {
  resource: "Slot",
  select: [
    {
      column: [
        { path: "id", name: "slot_id" },
        { path: "status", name: "status" },
        { path: "start", name: "start" },
        { path: "end", name: "end" },
        {
          path: "extension.where(url.contains('booking-deep-link')).value",
          name: "book_url",
        },
        {
          path: "serviceType.coding.where(system = 'http://terminology.hl7.org/CodeSystem/service-type').code",
          name: "specialty",
        },
        { path: "schedule.reference", name: "schedule_ref" },
      ],
    },
  ],
};

/** Stringify for display in the UI code panel and for passing to Pyodide. */
export function viewDefToJson(vd: ViewDefinition): string {
  return JSON.stringify(vd, null, 2);
}
