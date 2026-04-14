/**
 * SMART on FHIR data retrieval service.
 *
 * Fetches US Core FHIR resources for a single patient using the access token
 * obtained from the SMART OAuth2 flow.
 */

import { RESOURCE_TYPES, type Vendor, type USCoreResourceType } from "./smart-config";

// ── Types ────────────────────────────────────────────────────────────────────

export interface FHIRResource {
  resourceType: string;
  id?: string;
  [key: string]: unknown;
}

export interface FHIRDataset {
  patient: FHIRResource;
  resources: FHIRResource[];
  fetchedAt: number;
  vendor: Vendor;
}

export interface FetchProgress {
  resourceType: string;
  fetched: number;
  total: number | null;
}

// ── Vendor-specific headers ──────────────────────────────────────────────────

function buildHeaders(token: string, vendor: Vendor, clientId?: string): Record<string, string> {
  const headers: Record<string, string> = {
    Authorization: `Bearer ${token}`,
    Accept: "application/fhir+json",
  };

  if (vendor === "epic" && clientId) {
    headers["Epic-Client-ID"] = clientId;
  }

  return headers;
}

// ── Pagination ───────────────────────────────────────────────────────────────

/**
 * Fetch all pages of a Bundle resource, following `next` links.
 */
async function fetchAllPages(
  url: string,
  headers: Record<string, string>,
  maxPages = 10,
): Promise<FHIRResource[]> {
  const resources: FHIRResource[] = [];
  let nextUrl: string | null = url;
  let page = 0;

  while (nextUrl && page < maxPages) {
    const resp = await fetch(nextUrl, { headers });

    if (resp.status === 401) {
      throw new AuthError("Access token expired or invalid. Please re-authorize.");
    }
    if (resp.status === 403) {
      throw new ScopeError("Insufficient permissions. Check your SMART scopes.");
    }
    if (!resp.ok) {
      // Retry once on transient errors
      if (page === 0 && resp.status >= 500) {
        await new Promise((r) => setTimeout(r, 1000));
        const retryResp: Response = await fetch(nextUrl!, { headers });
        if (!retryResp.ok) {
          throw new Error(`FHIR request failed: ${retryResp.status} ${retryResp.statusText}`);
        }
        const retryBundle: any = await retryResp.json();
        if (retryBundle.entry) {
          for (const entry of retryBundle.entry) {
            if (entry.resource) resources.push(entry.resource);
          }
        }
        nextUrl = retryBundle.link?.find((l: any) => l.relation === "next")?.url ?? null;
        page++;
        continue;
      }
      throw new Error(`FHIR request failed: ${resp.status} ${resp.statusText}`);
    }

    const bundle = await resp.json();

    if (bundle.resourceType === "Bundle" && bundle.entry) {
      for (const entry of bundle.entry) {
        if (entry.resource) {
          resources.push(entry.resource);
        }
      }
    }

    nextUrl = bundle.link?.find((l: any) => l.relation === "next")?.url ?? null;
    page++;
  }

  return resources;
}

// ── Custom errors ────────────────────────────────────────────────────────────

export class AuthError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "AuthError";
  }
}

export class ScopeError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ScopeError";
  }
}

// ── Main fetch function ──────────────────────────────────────────────────────

/**
 * Fetch all US Core resources for a patient.
 *
 * @param fhirBaseUrl - The FHIR server base URL
 * @param patientId - The patient ID from the token response
 * @param accessToken - The OAuth2 access token
 * @param vendor - "epic" or "cerner"
 * @param clientId - Client ID (required for Epic)
 * @param onProgress - Optional callback for progress updates
 */
export async function fetchPatientData(
  fhirBaseUrl: string,
  patientId: string,
  accessToken: string,
  vendor: Vendor,
  clientId?: string,
  onProgress?: (progress: FetchProgress) => void,
): Promise<FHIRDataset> {
  const base = fhirBaseUrl.replace(/\/$/, "");
  const headers = buildHeaders(accessToken, vendor, clientId);

  // Fetch the Patient resource directly
  const patientResp = await fetch(`${base}/Patient/${patientId}`, { headers });
  if (!patientResp.ok) {
    throw new Error(`Failed to fetch Patient/${patientId}: ${patientResp.status}`);
  }
  const patient: FHIRResource = await patientResp.json();

  // Fetch other resource types in parallel
  const allResources: FHIRResource[] = [patient];

  const fetchPromises = RESOURCE_TYPES
    .filter((rt) => rt !== "Patient")
    .map(async (resourceType: USCoreResourceType) => {
      onProgress?.({ resourceType, fetched: 0, total: null });

      // Epic uses `subject` for some resources instead of `patient`
      const searchParam =
        vendor === "epic" && ["Goal", "CarePlan"].includes(resourceType)
          ? "subject"
          : "patient";

      const url = `${base}/${resourceType}?${searchParam}=${patientId}&_count=100`;

      try {
        const resources = await fetchAllPages(url, headers);
        onProgress?.({ resourceType, fetched: resources.length, total: resources.length });
        return resources;
      } catch (e) {
        // Don't fail the entire fetch if one resource type fails (may not be supported)
        if (e instanceof AuthError || e instanceof ScopeError) throw e;
        console.warn(`Failed to fetch ${resourceType}: ${e}`);
        onProgress?.({ resourceType, fetched: 0, total: 0 });
        return [];
      }
    });

  const results = await Promise.all(fetchPromises);
  for (const resources of results) {
    allResources.push(...resources);
  }

  return {
    patient,
    resources: allResources,
    fetchedAt: Date.now(),
    vendor,
  };
}
