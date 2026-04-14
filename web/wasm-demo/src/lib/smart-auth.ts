/**
 * SMART on FHIR OAuth2 PKCE authentication flow.
 *
 * Implements the Standalone Launch sequence:
 * 1. Discover authorization/token endpoints from the FHIR server
 * 2. Generate PKCE code_verifier/code_challenge
 * 3. Redirect user to the authorization endpoint
 * 4. Exchange authorization code for access token
 *
 * No external SMART client library needed — pure browser APIs.
 */

import { SMART_SCOPES, type Vendor } from "./smart-config";

// ── Types ────────────────────────────────────────────────────────────────────

export interface SmartEndpoints {
  authorizationEndpoint: string;
  tokenEndpoint: string;
}

export interface SmartToken {
  accessToken: string;
  tokenType: string;
  expiresAt: number;
  patientId: string | null;
  scope: string;
}

export interface SmartSessionInfo {
  fhirBaseUrl: string;
  vendor: Vendor;
  clientId: string;
}

interface SmartState {
  codeVerifier: string;
  state: string;
  fhirBaseUrl: string;
  vendor: Vendor;
  clientId: string;
  tokenEndpoint: string;
  redirectUri: string;
}

// ── Storage keys ─────────────────────────────────────────────────────────────

const STORAGE_KEY_STATE = "fhir4ds_smart_state";
const STORAGE_KEY_TOKEN = "fhir4ds_smart_token";
const STORAGE_KEY_SESSION = "fhir4ds_smart_session";

// ── PKCE helpers ─────────────────────────────────────────────────────────────

function generateRandomString(length: number): string {
  const array = new Uint8Array(length);
  crypto.getRandomValues(array);
  return Array.from(array, (b) => b.toString(36).padStart(2, "0"))
    .join("")
    .slice(0, length);
}

async function sha256(plain: string): Promise<ArrayBuffer> {
  const encoder = new TextEncoder();
  return crypto.subtle.digest("SHA-256", encoder.encode(plain));
}

function base64UrlEncode(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (const b of bytes) binary += String.fromCharCode(b);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

// ── Discovery ────────────────────────────────────────────────────────────────

/**
 * Discover SMART authorization and token endpoints.
 * Tries `.well-known/smart-configuration` first, falls back to `metadata`.
 */
export async function discoverEndpoints(fhirBaseUrl: string): Promise<SmartEndpoints> {
  const base = fhirBaseUrl.replace(/\/$/, "");

  // Try .well-known/smart-configuration first
  try {
    const resp = await fetch(`${base}/.well-known/smart-configuration`, {
      headers: { Accept: "application/json" },
    });
    if (resp.ok) {
      const config = await resp.json();
      if (config.authorization_endpoint && config.token_endpoint) {
        return {
          authorizationEndpoint: config.authorization_endpoint,
          tokenEndpoint: config.token_endpoint,
        };
      }
    }
  } catch {
    // Fall through to metadata
  }

  // Fallback: capability statement metadata
  const metaResp = await fetch(`${base}/metadata`, {
    headers: { Accept: "application/fhir+json" },
  });
  if (!metaResp.ok) {
    throw new Error(`Failed to discover SMART endpoints from ${base}/metadata (${metaResp.status})`);
  }
  const meta = await metaResp.json();
  const security = meta?.rest?.[0]?.security;
  const oauthExt = security?.extension?.find(
    (e: any) => e.url === "http://fhir-registry.smarthealthit.org/StructureDefinition/oauth-uris",
  );

  if (!oauthExt) {
    throw new Error("FHIR server does not advertise SMART OAuth2 endpoints");
  }

  const authEp = oauthExt.extension?.find((e: any) => e.url === "authorize")?.valueUri;
  const tokenEp = oauthExt.extension?.find((e: any) => e.url === "token")?.valueUri;

  if (!authEp || !tokenEp) {
    throw new Error("SMART OAuth2 endpoints incomplete in server metadata");
  }

  return { authorizationEndpoint: authEp, tokenEndpoint: tokenEp };
}

// ── Authorization ────────────────────────────────────────────────────────────

/**
 * Build the OAuth2 authorize URL and store PKCE state for the callback.
 */
export async function buildAuthorizeUrl(
  fhirBaseUrl: string,
  clientId: string,
  vendor: Vendor,
  redirectUri: string,
  customScopes?: string,
  customAuthorizeEndpoint?: string,
): Promise<string> {
  const endpoints = await discoverEndpoints(fhirBaseUrl);

  const codeVerifier = generateRandomString(64);
  const codeChallenge = base64UrlEncode(await sha256(codeVerifier));
  const state = generateRandomString(32);

  // Store state for the callback. We use localStorage instead of sessionStorage
  // because the flow might start in an iframe, redirect in the top window,
  // and return to an iframe. sessionStorage is not shared across these transitions.
  const smartState: SmartState = {
    codeVerifier,
    state,
    fhirBaseUrl,
    vendor,
    clientId,
    tokenEndpoint: endpoints.tokenEndpoint,
    redirectUri,
  };
  console.log("[SMARTAuth] Storing state with redirectUri:", smartState.redirectUri);
  localStorage.setItem(STORAGE_KEY_STATE, JSON.stringify(smartState));

  const params = new URLSearchParams({
    response_type: "code",
    client_id: clientId,
    redirect_uri: smartState.redirectUri,
    scope: customScopes || SMART_SCOPES,
    state,
    aud: fhirBaseUrl,
    code_challenge: codeChallenge,
    code_challenge_method: "S256",
  });

  const authEndpoint = customAuthorizeEndpoint || endpoints.authorizationEndpoint;
  return `${authEndpoint}?${params.toString()}`;
}

// ── Callback ─────────────────────────────────────────────────────────────────

/**
 * Check if the current URL indicates a SMART callback (has code + state params).
 */
export function isSmartCallback(): boolean {
  const params = new URLSearchParams(window.location.search);
  return params.has("code") && params.has("state");
}

/**
 * Handle the OAuth2 callback: exchange authorization code for access token.
 */
export async function handleCallback(): Promise<SmartToken> {
  const params = new URLSearchParams(window.location.search);
  const code = params.get("code");
  const returnedState = params.get("state");

  if (!code || !returnedState) {
    throw new Error("Missing code or state in callback URL");
  }

  const stored = localStorage.getItem(STORAGE_KEY_STATE);
  if (!stored) {
    throw new Error("No SMART state found — authorization may have expired");
  }

  const smartState: SmartState = JSON.parse(stored);
  console.log("[SMARTAuth] Handling callback with stored redirectUri:", smartState.redirectUri);
  if (smartState.state !== returnedState) {
    throw new Error("State mismatch — possible CSRF attack");
  }

  // Exchange code for token
  const body = new URLSearchParams({
    grant_type: "authorization_code",
    code,
    redirect_uri: smartState.redirectUri,
    client_id: smartState.clientId,
    code_verifier: smartState.codeVerifier,
  });

  const resp = await fetch(smartState.tokenEndpoint, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: body.toString(),
  });

  if (!resp.ok) {
    const errorText = await resp.text().catch(() => "");
    throw new Error(`Token exchange failed (${resp.status}): ${errorText}`);
  }

  const tokenResp = await resp.json();

  const token: SmartToken = {
    accessToken: tokenResp.access_token,
    tokenType: tokenResp.token_type || "Bearer",
    expiresAt: Date.now() + (tokenResp.expires_in || 3600) * 1000,
    patientId: tokenResp.patient || null,
    scope: tokenResp.scope || "",
  };

  // Store token in localStorage for persistence and clean up
  localStorage.setItem(STORAGE_KEY_TOKEN, JSON.stringify(token));
  localStorage.setItem(STORAGE_KEY_SESSION, JSON.stringify({
    fhirBaseUrl: smartState.fhirBaseUrl,
    vendor: smartState.vendor,
    clientId: smartState.clientId,
  } satisfies SmartSessionInfo));
  localStorage.removeItem(STORAGE_KEY_STATE);

  // Clean URL without reloading
  const cleanUrl = window.location.origin + window.location.pathname;
  window.history.replaceState({}, "", cleanUrl);

  return token;
}

// ── Token management ─────────────────────────────────────────────────────────

/**
 * True when this window was opened as a popup (window.opener is set)
 * and is the top-level window (not itself inside an iframe).
 * Used to detect the OAuth callback popup context.
 */
export function isPopupContext(): boolean {
  return typeof window !== 'undefined'
    && window.opener !== null
    && window.self === window.top;
}

/**
 * Get the stored access token, or null if not authenticated or expired.
 */
export function getAccessToken(): SmartToken | null {
  const stored = localStorage.getItem(STORAGE_KEY_TOKEN);
  if (!stored) return null;

  const token: SmartToken = JSON.parse(stored);
  if (Date.now() >= token.expiresAt) {
    localStorage.removeItem(STORAGE_KEY_TOKEN);
    return null;
  }
  return token;
}

/**
 * Get the stored FHIR base URL from the auth state or token context.
 */
export function getStoredFhirBaseUrl(): string | null {
  const stateStr = localStorage.getItem(STORAGE_KEY_STATE);
  if (stateStr) {
    try {
      return JSON.parse(stateStr).fhirBaseUrl;
    } catch { /* ignore */ }
  }
  return null;
}

/**
 * Get the stored vendor from the auth state.
 */
export function getStoredVendor(): Vendor | null {
  const stateStr = localStorage.getItem(STORAGE_KEY_STATE);
  if (stateStr) {
    try {
      return JSON.parse(stateStr).vendor;
    } catch { /* ignore */ }
  }
  return null;
}

/**
 * Clear all stored authentication data.
 */
export function clearAuth(): void {
  localStorage.removeItem(STORAGE_KEY_STATE);
  localStorage.removeItem(STORAGE_KEY_TOKEN);
  localStorage.removeItem(STORAGE_KEY_SESSION);
}

/**
 * Get the stored SMART session info (FHIR URL, vendor, client ID).
 */
export function getStoredSession(): SmartSessionInfo | null {
  const stored = localStorage.getItem(STORAGE_KEY_SESSION);
  if (!stored) return null;
  try {
    return JSON.parse(stored) as SmartSessionInfo;
  } catch {
    return null;
  }
}
