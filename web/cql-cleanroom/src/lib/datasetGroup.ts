/**
 * Dataset grouping derivation (FEATURE_CLEANROOM_TEST_DATA_AUTHORING.md §3.2).
 *
 * Pure helper: flat resource list -> patient groups. The flat list stays
 * the single storage truth (INV-4); the tree is a derived view.
 *
 * Group order (second-opinion F6): Patient groups alphabetical by id,
 * uuid-phantom groups after, Unattributed last. Rows keep the FLAT
 * STORAGE INDEX as their identity (review finding 8) — display order
 * changes, storage indices never do.
 */

import { attributePatient } from "./attribution";

export interface DatasetRowRef {
  /** Flat storage index into dataset.resources — testids + callbacks. */
  index: number;
  resource: Record<string, unknown>;
  resourceType: string;
  id: string;
}

export interface PatientGroup {
  /** Patient id, a uuid phantom key, or "__unattributed__". */
  key: string;
  /** Display label for the group header. */
  label: string;
  /** true when keyed by a urn:uuid phantom (no Patient resource). */
  phantom: boolean;
  /** true for the Unattributed bucket. */
  unattributed: boolean;
  rows: DatasetRowRef[];
}

const UNATTRIBUTED = "__unattributed__";
const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** Short human hint for why a resource did not attribute (S-3). */
export function attributionWhy(resource: Record<string, unknown>): string {
  const resourceType = resource.resourceType;
  for (const path of ["subject", "patient", "beneficiary"] as const) {
    const value = resource[path];
    const candidates = Array.isArray(value) ? value : [value];
    for (const c of candidates) {
      if (!c || typeof c !== "object" || Array.isArray(c)) continue;
      const reference = (c as Record<string, unknown>).reference;
      if (typeof reference !== "string" || !reference) continue;
      if (reference.startsWith("urn:uuid:")) {
        return `${path}: urn:uuid phantom — no Patient resource with that id in the dataset`;
      }
      if (!reference.includes("/")) {
        return `${path}: bare id "${reference}" — no target type, cannot attribute`;
      }
      const segments = reference
        .split("/")
        .filter((s) => s.length > 0);
      const tail =
        segments.length >= 2 && segments[segments.length - 2] === "_history"
          ? segments.slice(0, -2)
          : segments;
      if (tail.length >= 2 && tail[tail.length - 2] !== "Patient") {
        return `${path}: target is ${tail[tail.length - 2]}/${tail[tail.length - 1]} — not a Patient reference`;
      }
    }
  }
  return `no ${resourceType === "Patient" ? "id" : "subject/patient/beneficiary reference"} — patient-context evaluation ignores this resource`;
}

export function groupDataset(
  resources: unknown[] | null | undefined,
): PatientGroup[] {
  const byKey = new Map<string, PatientGroup>();
  const order: string[] = [];

  const group = (key: string, label: string, phantom: boolean, unattr = false): PatientGroup => {
    let g = byKey.get(key);
    if (!g) {
      g = { key, label, phantom, unattributed: unattr, rows: [] };
      byKey.set(key, g);
      order.push(key);
    }
    return g;
  };

  (resources ?? []).forEach((r, index) => {
    if (!r || typeof r !== "object") return;
    const rec = r as Record<string, unknown>;
    const resourceType =
      typeof rec.resourceType === "string" ? rec.resourceType : "?";
    const id = typeof rec.id === "string" ? rec.id : "";
    const row: DatasetRowRef = { index, resource: rec, resourceType, id };

    const pid = attributePatient(rec);
    if (pid !== null) {
      group(pid, pid, UUID_RE.test(pid)).rows.push(row);
    } else {
      group(UNATTRIBUTED, "Unattributed", false, true).rows.push(row);
    }
  });

  // Phantom is a DERIVED property: a uuid-keyed group stops being a
  // phantom the moment a Patient resource with that id exists.
  for (const g of byKey.values()) {
    if (!g.unattributed) {
      g.phantom = !g.rows.some((r) => r.resourceType === "Patient");
      g.label = g.phantom ? `phantom ${g.key}` : g.key;
    }
  }

  // F6 ordering: real Patient groups alphabetical, uuid phantoms after,
  // Unattributed last. A group is "real" when a Patient resource is its
  // first row.
  const rank = (g: PatientGroup): number => {
    if (g.unattributed) return 2;
    if (g.rows.some((r) => r.resourceType === "Patient")) return 0;
    return 1;
  };
  return [...byKey.values()].sort((a, b) => {
    const ra = rank(a);
    const rb = rank(b);
    if (ra !== rb) return ra - rb;
    return a.label.localeCompare(b.label);
  });
}
