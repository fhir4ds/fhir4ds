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
  isSmartPopupCallback,
  handleCallback,
  getAccessToken,
  clearAuth,
  getStoredSession,
  markPopupAuthPending,
  clearPopupAuthPending,
  SMART_AUTH_CHANNEL,
  SMART_CALLBACK_RESULT_KEY,
  type SmartToken,
  type SmartCallbackMessage,
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
  const notifiedRef = useRef(false);
  useEffect(() => {
    if (authState.phase === "ready" && !notifiedRef.current) {
      notifiedRef.current = true;
      onAuthChange?.(true);
    }
  }, [authState.phase, onAuthChange]);

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
      if (isSmartPopupCallback()) return;

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
      markPopupAuthPending();
      const popup = window.open(
        url,
        'fhir4ds-smart-auth',
        'popup=yes,width=600,height=700,resizable=yes,scrollbars=yes',
      );

      if (!popup) {
        // Popup blocked — fall back to full-page redirect
        clearPopupAuthPending();
        console.warn("[SMARTLaunch] Popup blocked, falling back to redirect");
        window.location.href = url;
        return;
      }

      setAuthState({ phase: "authorizing" });

      let channel: BroadcastChannel | null = null;
      let closedPoll: ReturnType<typeof setInterval> | null = null;
      let popupClosedAt: number | null = null;

      const finish = () => {
        window.removeEventListener('message', handleMessage);
        window.removeEventListener('storage', handleStorage);
        channel?.close();
        if (closedPoll) clearInterval(closedPoll);
        if (!popup.closed) {
          try {
            popup.close();
          } catch {
            // Browser may reject close after cross-origin navigation; the
            // callback page also attempts to close itself.
          }
        }
        clearPopupAuthPending();
        localStorage.removeItem(SMART_CALLBACK_RESULT_KEY);
      };

      const handleAuthResult = (data: SmartCallbackMessage) => {
        if (data.type === 'FHIR4DS_SMART_TOKEN') {
          finish();
          setAuthState({ phase: "ready", token: data.token });
          // onAuthChange(true) fired by the ready-state effect.
        }

        if (data.type === 'FHIR4DS_SMART_ERROR') {
          finish();
          setAuthState({ phase: "error", message: data.error });
        }
      };

      // Listen for the token posted back by SmartCallbackPage. BroadcastChannel
      // and storage cover COOP/COEP cases where window.opener is severed.
      const handleMessage = (event: MessageEvent) => {
        if (event.origin !== window.location.origin) return;
        if (
          event.data?.type === 'FHIR4DS_SMART_TOKEN' ||
          event.data?.type === 'FHIR4DS_SMART_ERROR'
        ) {
          handleAuthResult(event.data);
        }
      };
      window.addEventListener('message', handleMessage);

      const handleStorage = (event: StorageEvent) => {
        if (event.key !== SMART_CALLBACK_RESULT_KEY || !event.newValue) return;
        try {
          const data = JSON.parse(event.newValue) as SmartCallbackMessage;
          if (
            data.type === 'FHIR4DS_SMART_TOKEN' ||
            data.type === 'FHIR4DS_SMART_ERROR'
          ) {
            handleAuthResult(data);
          }
        } catch {
          // Ignore malformed storage events from older tabs.
        }
      };
      window.addEventListener('storage', handleStorage);

      const consumeStoredAuthResult = () => {
        const storedResult = localStorage.getItem(SMART_CALLBACK_RESULT_KEY);
        if (!storedResult) return false;
        try {
          const data = JSON.parse(storedResult) as SmartCallbackMessage;
          if (
            data.type === 'FHIR4DS_SMART_TOKEN' ||
            data.type === 'FHIR4DS_SMART_ERROR'
          ) {
            handleAuthResult(data);
            return true;
          }
        } catch {
          localStorage.removeItem(SMART_CALLBACK_RESULT_KEY);
        }
        return false;
      };

      if ("BroadcastChannel" in window) {
        channel = new BroadcastChannel(SMART_AUTH_CHANNEL);
        channel.onmessage = (event) => {
          if (
            event.data?.type === 'FHIR4DS_SMART_TOKEN' ||
            event.data?.type === 'FHIR4DS_SMART_ERROR'
          ) {
            handleAuthResult(event.data);
          }
        };
      }

      // Detect popup closed by user without completing auth
      closedPoll = setInterval(() => {
        if (consumeStoredAuthResult()) {
          return;
        }

        const token = getAccessToken();
        if (token) {
          handleAuthResult({
            type: 'FHIR4DS_SMART_TOKEN',
            token,
            session: getStoredSession(),
          });
          return;
        }

        if (popup.closed) {
          popupClosedAt ??= Date.now();
          if (Date.now() - popupClosedAt < 5000) {
            return;
          }
          finish();
          setAuthState(prev =>
            prev.phase === 'authorizing'
              ? { phase: "select" }
              : prev
          );
        }
      }, 500);

      consumeStoredAuthResult();

    } catch (err) {
      clearPopupAuthPending();
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
