/**
 * SMART on FHIR Launch component.
 *
 * UI flow:
 *   1. Provider selector → User picks Epic/Cerner sandbox or Custom
 *   2. Auth redirect → User authorizes in EHR
 *   3. Callback → Token exchange, patient data fetch
 *   4. Patient banner → Shows demographics, resource counts
 */

import { useState, useEffect, useCallback, useRef } from "react";
import {
  SANDBOX_PROVIDERS,
  DEFAULT_CLIENT_IDS,
  type SmartProvider,
} from "../lib/smart-config";
import {
  buildAuthorizeUrl,
  isSmartCallback,
  isPopupContext,
  handleCallback,
  getAccessToken,
  clearAuth,
  getStoredSession,
  type SmartToken,
} from "../lib/smart-auth";
import { useSMARTData } from "../hooks/useSMARTData";
import type { FHIRResource } from "../lib/smart-data";

// ── Types ────────────────────────────────────────────────────────────────────

type AuthState =
  | { phase: "select" }
  | { phase: "authorizing" }
  | { phase: "loading"; token: SmartToken }
  | { phase: "ready"; token: SmartToken }
  | { phase: "error"; message: string };

// ── Component ────────────────────────────────────────────────────────────────

export function SMARTLaunch({
  getConnection,
  onAuthChange,
  onPatientName,
  wasmAppUrl,
  smartRedirectUri,
  duckdbReady,
}: {
  getConnection: () => any | null;
  onAuthChange?: (authenticated: boolean) => void;
  onPatientName?: (name: string) => void;
  wasmAppUrl?: string;
  smartRedirectUri?: string;
  duckdbReady?: boolean;
}) {
  const [authState, setAuthState] = useState<AuthState>({ phase: "select" });
  const [selectedProviderId, setSelectedProviderId] = useState<string>(
    SANDBOX_PROVIDERS[0].id,
  );
  const [clientId, setClientId] = useState(
    (SANDBOX_PROVIDERS[0].vendor === 'epic' 
      ? (import.meta.env.VITE_EPIC_CLIENT_ID || "5defe3d1-f428-4cae-923e-2564ff50759a")
      : (import.meta.env.VITE_CERNER_CLIENT_ID || "22c22bb4-76e9-4509-be6f-227d9de74358"))
  );
  const [customFhirUrl, setCustomFhirUrl] = useState("");

  const smartData = useSMARTData(getConnection);

  // Guard: only fire onAuthChange(true) once per authentication session.
  // We DEFER the notification until patient data is fully loaded into DuckDB
  // so that when the parent switches to the CQL/SDC tab the data is already
  // available for queries.
  const notifiedRef = useRef(false);
  useEffect(() => {
    if (authState.phase === "ready" && smartData.dataset && !notifiedRef.current) {
      notifiedRef.current = true;
      onAuthChange?.(true);
    }
  }, [authState.phase, smartData.dataset, onAuthChange]);

  // Sync patient name to parent for the header
  useEffect(() => {
    if (smartData.dataset?.patient) {
      const patient = smartData.dataset.patient as any;
      const name = patient.name?.[0];
      const display = name
        ? name.text || `${name.given?.join(" ")} ${name.family}`
        : "Unknown Patient";
      onPatientName?.(display);
    }
  }, [smartData.dataset, onPatientName]);

  // Automatically trigger data load when tokens are ready AND DuckDB is ready
  useEffect(() => {
    if (authState.phase === "ready" && !smartData.dataset && !smartData.loading && !smartData.error) {
      const provider = SANDBOX_PROVIDERS.find(p => p.id === selectedProviderId);
      const fhirUrl = customFhirUrl.trim() || provider?.fhirBaseUrl || "";
      
      smartData.loadPatientData(
        fhirUrl,
        authState.token,
        provider?.vendor || "epic",
        clientId.trim(),
      );
    }
  // duckdbReady is included so this re-fires once DuckDB initialises after a
  // page reload where the token was already stored (background resume case).
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authState.phase, smartData.dataset, smartData.loading, smartData.error, selectedProviderId, customFhirUrl, clientId, duckdbReady]);

  // Check for OAuth callback or existing session on mount
  useEffect(() => {
    if (isSmartCallback()) {
      // In a popup context the WC entry-point IIFE handles the callback and
      // closes the window — don't double-process here.
      if (isPopupContext()) return;

      setAuthState({ phase: "authorizing" });
      handleCallback()
        .then((token) => {
          setAuthState({ phase: "ready", token });
          // onAuthChange(true) fired by deferred effect once patient data loads
        })
        .catch((err) => {
          setAuthState({
            phase: "error",
            message: err instanceof Error ? err.message : String(err),
          });
        });
    } else {
      const token = getAccessToken();
      if (token) {
        const session = getStoredSession();
        if (session) {
          const provider = SANDBOX_PROVIDERS.find((p) => p.vendor === session.vendor);
          if (provider) setSelectedProviderId(provider.id);
          setClientId(session.clientId);
          setCustomFhirUrl(session.fhirBaseUrl);
        }
        setAuthState({ phase: "ready", token });
        // onAuthChange(true) fired by deferred effect once patient data loads
      }
    }
  }, []);

  const handleProviderChange = (id: string) => {
    setSelectedProviderId(id);
    const provider = SANDBOX_PROVIDERS.find((p) => p.id === id);
    if (provider) {
      const defaultId = (provider.vendor === 'epic' 
        ? (import.meta.env.VITE_EPIC_CLIENT_ID || "5defe3d1-f428-4cae-923e-2564ff50759a") 
        : (import.meta.env.VITE_CERNER_CLIENT_ID || "22c22bb4-76e9-4509-be6f-227d9de74358"));
      setClientId(defaultId);
      setCustomFhirUrl("");
    } else {
      // Custom mode
      setClientId("");
      setCustomFhirUrl("");
    }
  };

  const handleLaunch = async () => {
    const provider = SANDBOX_PROVIDERS.find(p => p.id === selectedProviderId);
    const finalClientId = clientId.trim();
    
    if (!finalClientId) {
      setAuthState({ phase: "error", message: "Please enter your registered Client ID" });
      return;
    }

    try {
      const fhirUrl = customFhirUrl.trim() || provider?.fhirBaseUrl || "";
      
      // Redirect URI: always point to the standalone WASM app so the popup
      // can handle the callback and post the token back.
      let redirectUri = provider?.redirectUriOverride;
      if (!redirectUri) {
        if (smartRedirectUri) {
          // Explicit override from the Web Component attribute
          redirectUri = smartRedirectUri;
        } else if (wasmAppUrl) {
          // Web Component context: use the explicit WASM app URL
          redirectUri = wasmAppUrl.replace(/\/$/, '');
        } else {
          // Standalone context: current origin + path
          const origin = window.location.origin;
          const path = window.location.pathname.replace(/\/$/, "");
          redirectUri = path ? `${origin}${path}` : origin;
        }
      }

      const url = await buildAuthorizeUrl(
        fhirUrl,
        finalClientId,
        provider?.vendor || "epic",
        redirectUri,
        provider?.scopes,
        provider?.customAuthorizeEndpoint,
      );

      // Open a popup for the auth flow. Popups navigate freely regardless
      // of the EHR's X-Frame-Options header.
      const popup = window.open(
        url,
        'fhir4ds-smart-auth',
        'popup=yes,width=600,height=700,resizable=yes,scrollbars=yes',
      );

      if (!popup) {
        // Popup blocked — fall back to full-page redirect
        console.warn("[SMARTLaunch] Popup blocked, falling back to redirect");
        window.location.href = url;
        return;
      }

      setAuthState({ phase: "authorizing" });

      // Listen for the token posted back by SmartCallbackPage
      const handleMessage = (event: MessageEvent) => {
        if (event.origin !== window.location.origin) return;

        if (event.data?.type === 'FHIR4DS_SMART_TOKEN') {
          window.removeEventListener('message', handleMessage);
          clearInterval(closedPoll);
          setAuthState({ phase: "ready", token: event.data.token });
          // onAuthChange(true) fired by deferred effect once patient data loads
        }

        if (event.data?.type === 'FHIR4DS_SMART_ERROR') {
          window.removeEventListener('message', handleMessage);
          clearInterval(closedPoll);
          setAuthState({ phase: "error", message: event.data.error });
        }
      };
      window.addEventListener('message', handleMessage);

      // Detect popup closed by user without completing auth
      const closedPoll = setInterval(() => {
        if (popup.closed) {
          clearInterval(closedPoll);
          window.removeEventListener('message', handleMessage);
          setAuthState(prev =>
            prev.phase === 'authorizing'
              ? { phase: "select" }
              : prev
          );
        }
      }, 500);

    } catch (err) {
      setAuthState({
        phase: "error",
        message: err instanceof Error ? err.message : String(err),
      });
    }
  };

  const handleDisconnect = useCallback(() => {
    clearAuth();
    smartData.clearData();
    notifiedRef.current = false;
    setAuthState({ phase: "select" });
    onAuthChange?.(false);
  }, [smartData, onAuthChange]);

  return (
    <div className="smart-container">
      <div className="smart-header">
        <h2>🔐 SMART on FHIR</h2>
        <p className="smart-subtitle">
          Connect to a live EHR sandbox and run FHIRPath/CQL queries against
          real patient data.
        </p>
      </div>

      {authState.phase === "select" && (
        <ProviderSelector
          selectedId={selectedProviderId}
          clientId={clientId}
          customFhirUrl={customFhirUrl}
          onProviderChange={handleProviderChange}
          onClientIdChange={setClientId}
          onCustomUrlChange={setCustomFhirUrl}
          onLaunch={handleLaunch}
        />
      )}

      {authState.phase === "authorizing" && (
        <div className="smart-status">
          <div className="loading-spinner" />
          <p>Waiting for authorization in the popup window…</p>
          <p style={{ fontSize: '0.85rem', color: '#64748b' }}>
            Complete the login in the popup, then return here.
          </p>
        </div>
      )}

      {(authState.phase === "loading" || smartData.loading) && (
        <div className="smart-status">
          <div className="loading-spinner" />
          <p>Fetching patient data…</p>
          {smartData.progress && (
            <p className="smart-progress">
              {smartData.progress.resourceType}: {smartData.progress.fetched}{" "}
              resources
            </p>
          )}
        </div>
      )}

      {authState.phase === "ready" && (
        <ConnectedView
          token={authState.token}
          dataset={smartData.dataset}
          resourceCount={smartData.resourceCount}
          onDisconnect={handleDisconnect}
        />
      )}

      {authState.phase === "error" && (
        <div className="smart-error">
          <h3>⚠️ Error</h3>
          <p>{authState.message}</p>
          <button
            className="smart-btn smart-btn--secondary"
            onClick={() => setAuthState({ phase: "select" })}
          >
            Try Again
          </button>
        </div>
      )}
    </div>
  );
}

function ProviderSelector({
  selectedId,
  clientId,
  customFhirUrl,
  onProviderChange,
  onClientIdChange,
  onCustomUrlChange,
  onLaunch,
}: {
  selectedId: string;
  clientId: string;
  customFhirUrl: string;
  onProviderChange: (id: string) => void;
  onClientIdChange: (v: string) => void;
  onCustomUrlChange: (v: string) => void;
  onLaunch: () => void;
}) {
  const isCustom = selectedId === "custom";

  return (
    <div className="smart-form">
      <div className="smart-field">
        <label htmlFor="provider-select">Connection Profile</label>
        <select
          id="provider-select"
          value={selectedId}
          onChange={(e) => onProviderChange(e.target.value)}
          className="smart-select"
        >
          {SANDBOX_PROVIDERS.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
          <option value="custom">Custom Endpoint...</option>
        </select>
      </div>

      {isCustom && (
        <>
          <div className="smart-field">
            <label htmlFor="fhir-url">FHIR Server URL</label>
            <input
              id="fhir-url"
              type="url"
              value={customFhirUrl}
              onChange={(e) => onCustomUrlChange(e.target.value)}
              placeholder="https://fhir.example.com/api/R4"
              className="smart-input"
            />
          </div>

          <div className="smart-field">
            <label htmlFor="client-id">Client ID</label>
            <input
              id="client-id"
              type="text"
              value={clientId}
              onChange={(e) => onClientIdChange(e.target.value)}
              placeholder="Enter your registered Client ID"
              className="smart-input"
            />
          </div>
        </>
      )}

      {!isCustom && (
        <div className="smart-info-box">
          <p>
            This will use the official <strong>{SANDBOX_PROVIDERS.find(p => p.id === selectedId)?.name}</strong> public sandbox.
          </p>
        </div>
      )}

      <button className="smart-btn smart-btn--primary" onClick={onLaunch}>
        Connect to {isCustom ? "Custom FHIR Server" : SANDBOX_PROVIDERS.find(p => p.id === selectedId)?.name.split(" ")[0]}
      </button>
    </div>
  );
}

function ConnectedView({
  token,
  dataset,
  resourceCount,
  onDisconnect,
}: {
  token: SmartToken;
  dataset: any;
  resourceCount: number;
  onDisconnect: () => void;
}) {
  return (
    <div className="smart-connected">
      <PatientBanner patient={dataset?.patient ?? null} token={token} />

      <div className="smart-stats-row">
        <div className="smart-stat">
          <span className="smart-stat-value">{resourceCount}</span>
          <span className="smart-stat-label">Resources Loaded</span>
        </div>
        <div className="smart-stat">
          <span className="smart-stat-value">
            {token.scope.split(" ").length}
          </span>
          <span className="smart-stat-label">Scopes Granted</span>
        </div>
        <div className="smart-stat">
          <span className="smart-stat-value">
            {Math.max(0, Math.round((token.expiresAt - Date.now()) / 60000))}m
          </span>
          <span className="smart-stat-label">Token Expires</span>
        </div>
      </div>

      <div className="smart-info-box">
        <p>
          ✅ Connected! Patient data has been loaded into the DuckDB{" "}
          <code>resources</code> table. Switch to the <strong>CQL Playground</strong>{" "}
          tab to run FHIRPath and CQL queries against this data.
        </p>
      </div>

      <button
        className="smart-btn smart-btn--secondary"
        onClick={onDisconnect}
      >
        Disconnect
      </button>
    </div>
  );
}

function PatientBanner({
  patient,
  token,
}: {
  patient: FHIRResource | null;
  token: SmartToken;
}) {
  if (!patient) {
    return (
      <div className="smart-banner">
        <span className="smart-banner-id">
          Patient: {token.patientId ?? "Unknown"}
        </span>
      </div>
    );
  }

  const name =
    (patient.name as any)?.[0]?.text ??
    [
      (patient.name as any)?.[0]?.given?.join(" "),
      (patient.name as any)?.[0]?.family,
    ]
      .filter(Boolean)
      .join(" ") ??
    "Unknown";

  const gender = (patient.gender as string) ?? "";
  const birthDate = (patient.birthDate as string) ?? "";

  return (
    <div className="smart-banner">
      <div className="smart-banner-avatar">
        {name.charAt(0).toUpperCase()}
      </div>
      <div className="smart-banner-info">
        <span className="smart-banner-name">{name}</span>
        <span className="smart-banner-details">
          {[gender, birthDate, `ID: ${patient.id}`].filter(Boolean).join(" · ")}
        </span>
      </div>
    </div>
  );
}
