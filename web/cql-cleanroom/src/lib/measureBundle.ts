/**
 * DQM/eCQM test-bundle → cleanroom workspace converter.
 *
 * Input: one of the 50 conformance bundles at
 * tests/data/ecqm-content-qicore-2025/bundles/measure/<CMS*>/*.json —
 * a FHIR Bundle with Library resources (content[text/cql]), the Measure,
 * ValueSets, per-patient test resources, and expected MeasureReports.
 *
 * Output: workspace-ready pieces sized for the cleanroom UI.
 */

export interface MeasureTestCase {
  libraryTexts: Array<{ name: string; text: string }>;
  measure: Record<string, unknown> | null;
  valuesets: Array<Record<string, unknown>>;
  patients: Array<Record<string, unknown>>;
  /** Non-patient clinical resources keyed by patient reference. */
  resourcesByPatient: Record<string, Array<Record<string, unknown>>>;
  /** Expected population memberships per patient (from MeasureReports). */
  expected: Record<string, Record<string, boolean>>;
  unattributed: Array<Record<string, unknown>>;
  skippedLibraries: string[];
}

function libName(text: string): string | null {
  const m = text.match(/^\s*library\s+([A-Za-z][A-Za-z0-9_]*)/m);
  return m ? m[1] : null;
}

function patientIdOf(r: Record<string, unknown>): string | null {
  // Exact 7-point doctrine (loader mirror): subject/patient/beneficiary,
  // Reference objects only, Patient-typed targets.
  for (const field of ["subject", "patient", "beneficiary"]) {
    const v = (r as Record<string, unknown>)[field];
    if (!v || typeof v !== "object" || Array.isArray(v)) continue;
    const ref = (v as Record<string, unknown>)["reference"];
    if (typeof ref !== "string") continue;
    const parts = ref.replace("/_history/", "/").split("/").filter(Boolean);
    if (parts.length >= 2 && parts[parts.length - 2] === "Patient") {
      return parts[parts.length - 1];
    }
  }
  return null;
}

/** Extract a cleanroom test case from a conformance measure bundle. */
export function measureBundleToTestCase(
  bundle: Record<string, unknown>,
): MeasureTestCase {
  const libraryTexts: Array<{ name: string; text: string }> = [];
  const skippedLibraries: string[] = [];
  const valuesets: Array<Record<string, unknown>> = [];
  const patients: Array<Record<string, unknown>> = [];
  const resourcesByPatient: Record<string, Array<Record<string, unknown>>> = {};
  const unattributed: Array<Record<string, unknown>> = [];
  const expected: Record<string, Record<string, boolean>> = {};
  let measure: Record<string, unknown> | null = null;

  for (const entry of (bundle.entry as Array<Record<string, unknown>>) ?? []) {
    const r = (entry.resource ?? {}) as Record<string, unknown>;
    switch (r.resourceType) {
      case "Library": {
        const contents = (r.content as Array<Record<string, unknown>>) ?? [];
        const cql = contents.find(
          (c) => c?.contentType === "text/cql" && typeof c.data === "string",
        );
        if (!cql) {
          skippedLibraries.push(String(r.id ?? r.name ?? "unknown"));
          break;
        }
        const name = libName(cql.data as string) ?? String(r.name ?? r.id ?? "lib");
        libraryTexts.push({ name, text: cql.data as string });
        break;
      }
      case "Measure":
        measure = r;
        break;
      case "ValueSet":
        valuesets.push(r);
        break;
      case "Patient":
        patients.push(r);
        break;
      case "MeasureReport": {
        // Expected memberships: population count 1 = true.
        const pid = ((r.subject as Record<string, unknown>)?.reference as string ?? "")
          .split("/")
          .pop() ?? "";
        if (!pid) break;
        const memberships: Record<string, boolean> = {};
        for (const g of (r.group as Array<Record<string, unknown>>) ?? []) {
          for (const pop of (g.population as Array<Record<string, unknown>>) ?? []) {
            const code =
              ((pop.code as { coding?: Array<{ code?: string }> })?.coding ?? [])[0]
                ?.code ?? "";
            if (code) memberships[code] = (pop.count as number) === 1;
          }
        }
        expected[pid] = memberships;
        break;
      }
      default: {
        const rt = r.resourceType as string | undefined;
        if (rt && !["Organization", "Practitioner", "Location", "Device"].includes(rt)) {
          const pid = patientIdOf(r);
          if (pid) {
            (resourcesByPatient[pid] ??= []).push(r);
          } else {
            unattributed.push(r);
          }
        }
        break;
      }
    }
  }

  return {
    libraryTexts,
    measure,
    valuesets,
    patients,
    resourcesByPatient,
    expected,
    unattributed,
    skippedLibraries,
  };
}
