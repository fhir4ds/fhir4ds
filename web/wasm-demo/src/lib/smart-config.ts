/**
 * SMART on FHIR provider configurations.
 *
 * Each provider entry includes the FHIR base URL, vendor type, and display info.
 * Users will need to register their own Client IDs in the Epic/Cerner developer portals.
 */

export type Vendor = "epic" | "cerner";

export interface SmartProvider {
  id: string;
  name: string;
  vendor: Vendor;
  fhirBaseUrl: string;
  redirectUriOverride?: string;
  scopes?: string;
  customAuthorizeEndpoint?: string;
}

/**
 * Curated sandbox endpoints for development and demonstration.
 * Production endpoints would be loaded from the vendor endpoint directories.
 */
export const SANDBOX_PROVIDERS: SmartProvider[] = [
  {
    id: "epic-sandbox",
    name: "Epic Sandbox (Argonaut)",
    vendor: "epic",
    fhirBaseUrl: "https://fhir.epic.com/interconnect-fhir-oauth/api/FHIR/R4",
    redirectUriOverride: undefined, // Epic is strict and registered to 5173 exactly
    scopes: "openid fhirUser patient/Patient.read patient/Observation.read patient/Condition.read patient/MedicationRequest.read patient/Encounter.read patient/Procedure.read", 
    customAuthorizeEndpoint: "https://fhir.epic.com/interconnect-fhir-oauth/oauth2/authorize",
  },
  {
    id: "cerner-sandbox",
    name: "Cerner Sandbox (Millennium)",
    vendor: "cerner",
    fhirBaseUrl: "https://fhir-myrecord.cerner.com/r4/ec2458f2-1e24-41c8-b71b-0e701af7583d",
    redirectUriOverride: undefined, // Both now standardized to 5173 without trailing slash
    scopes: "launch/patient openid fhirUser patient/Patient.read patient/Observation.read patient/Condition.read patient/MedicationRequest.read patient/Encounter.read patient/Procedure.read",
  },
];

/**
 * Placeholder Client IDs — users must register their app in the vendor portals.
 * Pulls from VITE_EPIC_CLIENT_ID and VITE_CERNER_CLIENT_ID env vars if available.
 * Defaults to the public sandbox IDs provided by the project.
 */
export const DEFAULT_CLIENT_IDS: Record<Vendor, string> = {
  epic: import.meta.env.VITE_EPIC_CLIENT_ID || "5defe3d1-f428-4cae-923e-2564ff50759a",
  cerner: import.meta.env.VITE_CERNER_CLIENT_ID || "22c22bb4-76e9-4509-be6f-227d9de74358",
};

/**
 * SMART on FHIR scopes for patient-level access.
 * We use a set that is widely supported by sandbox environments.
 */
export const SMART_SCOPES = [
  "launch/patient",
  "openid",
  "fhirUser",
  "patient/Patient.read",
  "patient/Observation.read",
  "patient/Condition.read",
  "patient/MedicationRequest.read",
  "patient/Encounter.read",
  "patient/Procedure.read",
].join(" ");

/**
 * US Core resource types to fetch after authorization.
 */
export const RESOURCE_TYPES = [
  "Patient",
  "Observation",
  "Condition",
  "MedicationRequest",
  "Encounter",
  "Procedure",
] as const;

export type USCoreResourceType = (typeof RESOURCE_TYPES)[number];
