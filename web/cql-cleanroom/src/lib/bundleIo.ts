/**
 * Bundle collection export/import (FEATURE_CLEANROOM_TEST_DATA_AUTHORING §3.4).
 *
 * Export: the dataset as one FHIR Bundle (type "collection") — the
 * interoperable interchange format for MADiE/Synthea tooling.
 *
 * Import (F1): Synthea/MADiE bundles frequently omit resource.id — ids are
 * synthesized from entry.fullUrl (urn:uuid tail or trailing URL segment)
 * BEFORE dedup/attribution so those invariants hold. Bundle.type is
 * validated client-side against the 9 collection-compatible codes;
 * per-entry shape problems fail the whole import atomically.
 *
 * Merge semantics (S-8): default merge = last-write-wins by
 * (resourceType, id); "replace" swaps the dataset wholesale.
 */

export const BUNDLE_TYPES = [
  "document",
  "message",
  "transaction",
  "transaction-response",
  "batch",
  "batch-response",
  "history",
  "searchset",
  "collection",
] as const;

export interface BundleImportResult {
  resources: Array<Record<string, unknown>>;
  /** count of ids synthesized from fullUrl (F1) */
  synthesizedIds: number;
  /** count of entries with neither id nor fullUrl — rejected */
  rejected: Array<number>;
}

/** The entry's resource with an id synthesized from fullUrl when absent. */
function synthId(
  entry: Record<string, unknown>,
): { resource: Record<string, unknown> | null; synthesized: boolean } {
  const resource = entry.resource;
  if (typeof resource !== "object" || resource === null) {
    return { resource: null, synthesized: false };
  }
  const res = resource as Record<string, unknown>;
  if (typeof res.id === "string" && res.id !== "") {
    return { resource: res, synthesized: false };
  }
  const fullUrl = typeof entry.fullUrl === "string" ? entry.fullUrl : "";
  let id = "";
  if (fullUrl.startsWith("urn:uuid:")) {
    id = fullUrl.slice("urn:uuid:".length);
  } else if (fullUrl) {
    const noSlash = fullUrl.replace(/\/+$/, "");
    const idx = noSlash.lastIndexOf("/");
    id = idx >= 0 ? noSlash.slice(idx + 1) : noSlash;
  }
  if (!id || !/^[A-Za-z0-9-.]{1,64}$/.test(id)) {
    return { resource: res, synthesized: false };
  }
  return { resource: { ...res, id }, synthesized: true };
}

/**
 * Validate + flatten a parsed Bundle JSON into dataset resources.
 * Throws Error (with entry index attribution) on shape problems;
 * entries without a usable id (and no fullUrl tail) are REJECTED
 * (counted, not silently dropped) — the caller decides.
 */
export function importBundle(
  parsed: unknown,
): BundleImportResult {
  if (typeof parsed !== "object" || parsed === null) {
    throw new Error("bundle must be a JSON object");
  }
  const bundle = parsed as Record<string, unknown>;
  if (bundle.resourceType !== "Bundle") {
    throw new Error(
      `not a Bundle: resourceType=${String(bundle.resourceType)}`,
    );
  }
  const type = typeof bundle.type === "string" ? bundle.type : "";
  if (!(BUNDLE_TYPES as readonly string[]).includes(type)) {
    throw new Error(
      `invalid Bundle.type ${JSON.stringify(type)} (expected one of ${BUNDLE_TYPES.join(", ")})`,
    );
  }
  const entries = Array.isArray(bundle.entry) ? bundle.entry : [];
  const resources: Array<Record<string, unknown>> = [];
  const rejected: Array<number> = [];
  let synthesizedIds = 0;
  entries.forEach((rawEntry, i) => {
    if (typeof rawEntry !== "object" || rawEntry === null) {
      throw new Error(`Bundle.entry[${i}] is not an object`);
    }
    const entry = rawEntry as Record<string, unknown>;
    const { resource, synthesized } = synthId(entry);
    if (!resource) {
      throw new Error(`Bundle.entry[${i}].resource is not an object`);
    }
    if (!("id" in resource) || typeof resource.id !== "string" || resource.id === "") {
      rejected.push(i);
      return;
    }
    if (typeof resource.resourceType !== "string" || !resource.resourceType) {
      throw new Error(
        `Bundle.entry[${i}].resource.resourceType is missing`,
      );
    }
    if (synthesized) synthesizedIds += 1;
    resources.push(resource);
  });
  return { resources, synthesizedIds, rejected };
}

/**
 * Merge imported resources into an existing dataset (S-8 default):
 * last-write-wins by (resourceType, id); resources without ids keep
 * their position (appended). Returns the merged array.
 */
export function mergeDatasets(
  current: Array<Record<string, unknown>>,
  incoming: Array<Record<string, unknown>>,
): Array<Record<string, unknown>> {
  const keyOf = (r: Record<string, unknown>) =>
    typeof r.id === "string" && r.id !== ""
      ? `${String(r.resourceType)}/${r.id}`
      : null;
  const byKey = new Map<string, number>();
  current.forEach((r, i) => {
    const k = keyOf(r);
    if (k) byKey.set(k, i);
  });
  const out = [...current];
  for (const r of incoming) {
    const k = keyOf(r);
    if (k && byKey.has(k)) {
      out[byKey.get(k)!] = r; // last-write-wins
    } else {
      out.push(r);
      if (k) byKey.set(k, out.length - 1);
    }
  }
  return out;
}

/** Export dataset resources as a collection Bundle JSON object. */
export function exportBundle(
  resources: Array<Record<string, unknown>>,
): Record<string, unknown> {
  return {
    resourceType: "Bundle",
    type: "collection",
    entry: resources.map((r) => ({ resource: r })),
  };
}
