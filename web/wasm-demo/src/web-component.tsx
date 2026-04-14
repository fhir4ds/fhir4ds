/**
 * FHIR4DS Demo — Web Component entry point.
 *
 * Registers <fhir4ds-demo> as a custom element. The React app renders into
 * a Shadow DOM root for CSS isolation (prevents the app's dark-mode body
 * styles from leaking into the host page).
 *
 * Attributes:
 *   scenario  — one of: workbench | cql-sandbox | sdc-forms | cms-measures | smart-flow
 *   height    — CSS height value for the component (default: "80vh")
 *
 * Usage:
 *   <fhir4ds-demo scenario="cms-measures" height="85vh"></fhir4ds-demo>
 *
 * Asset paths: DuckDB/Pyodide assets resolve relative to this bundle's URL.
 * In production this is typically /wasm-app/.
 */

import { createRoot, type Root } from "react-dom/client";
import { App } from "./App";

// Import full app CSS as a string for Shadow DOM injection.
// The ?inline suffix is a Vite transform — returns CSS as a JS string.
import appStyles from "./styles/index.css?inline";

// Derive the WASM app's base URL from this bundle's own URL.
// In production: "https://fhir4ds.com/wasm-app/"
// In preview:   "http://localhost:4173/"
// In Vite dev:  "http://localhost:5173/src/"  ← wrong, assets are at root
//   Fix: if the resolved path starts with /src/, strip it.
const WASM_APP_BASE = (() => {
  const base = new URL("./", import.meta.url).href;
  const parsed = new URL(base);
  if (parsed.pathname.startsWith("/src")) {
    parsed.pathname = "/";
    return parsed.href;
  }
  return base;
})();

/**
 * Rewrite CSS selectors that target the document root (html, body, :root, #root)
 * to target the shadow DOM host container instead.
 *
 * In Shadow DOM:
 *   :root   → :host  (CSS variables need to be on :host for cascade)
 *   html, body, #root → .fhir4ds-root  (our container div)
 */
function scopeStyles(css: string): string {
  // Replace :root { with :host {
  let scoped = css.replace(/:root\s*\{/g, ":host {");

  // Replace "html,\nbody,\n#root {" compound selector with container class
  scoped = scoped.replace(
    /html\s*,\s*body\s*,\s*#root\s*\{/g,
    ".fhir4ds-root {"
  );

  // Catch any standalone body { or html { selectors
  scoped = scoped.replace(/(?:^|\n)\s*body\s*\{/g, "\n.fhir4ds-root {");
  scoped = scoped.replace(/(?:^|\n)\s*html\s*\{/g, "\n.fhir4ds-root {");

  return scoped;
}

/**
 * Additional CSS fixes for Shadow DOM context.
 *
 * Monaco editor loads its CSS into document.head, but those styles don't
 * cascade into shadow DOM. Without these rules, Monaco's hidden textarea
 * renders at position (0,0) with default browser styling (visible gray box).
 *
 * Targets BOTH the legacy class (.inputarea, Monaco < 0.52) and the new
 * class (.ime-text-area, Monaco >= 0.52 which renamed the element).
 */
const SHADOW_DOM_FIXES = `
  /* Monaco: move the hidden keyboard-input textarea fully off-screen.
     Targets both pre-0.52 (.inputarea) and 0.52+ (.ime-text-area) class names. */
  .monaco-editor .inputarea,
  .monaco-editor .inputarea.ime-input,
  .monaco-editor .ime-text-area {
    position: absolute !important;
    top: 0 !important;
    left: -10000px !important;
    width: 1px !important;
    height: 1px !important;
    min-width: 0 !important;
    min-height: 0 !important;
    color: transparent !important;
    background-color: transparent !important;
    caret-color: transparent !important;
    border: none !important;
    outline: none !important;
    padding: 0 !important;
    margin: 0 !important;
    overflow: hidden !important;
    resize: none !important;
    white-space: nowrap !important;
    z-index: -10 !important;
    opacity: 0 !important;
  }
`;

class FhirDsDemo extends HTMLElement {
  private _shadowRoot!: ShadowRoot;
  private _container!: HTMLDivElement;
  private _root?: Root;

  static get observedAttributes(): string[] {
    return ["scenario", "height", "redirect-uri"];
  }

  connectedCallback(): void {
    // Inject Google Fonts into the document head (fonts are document-level;
    // @import inside shadow DOM style may not load in some browsers).
    if (!document.getElementById("fhir4ds-inter-font")) {
      const link = document.createElement("link");
      link.id = "fhir4ds-inter-font";
      link.rel = "stylesheet";
      link.href =
        "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Fira+Code:wght@400;500&display=swap";
      document.head.appendChild(link);
    }

    // Create shadow DOM for style isolation
    this._shadowRoot = this.attachShadow({ mode: "open" });

    // Apply component styles scoped to shadow root
    const style = document.createElement("style");
    style.textContent = scopeStyles(appStyles) + SHADOW_DOM_FIXES;
    this._shadowRoot.appendChild(style);

    // Container fills the custom element's box
    this._container = document.createElement("div");
    this._container.className = "fhir4ds-root";
    this._container.style.cssText = `
      width: 100%;
      height: 100%;
      display: flex;
      flex-direction: column;
    `;
    this._shadowRoot.appendChild(this._container);

    // Set the host element's height if specified as an attribute
    const attrHeight = this.getAttribute("height");
    if (attrHeight) {
      this.style.height = attrHeight;
    }
    if (!this.style.height) {
      this.style.height = "80vh";
    }
    this.style.display = "block";

    this._root = createRoot(this._container);
    this._render();
  }

  attributeChangedCallback(name: string, _oldValue: string, newValue: string): void {
    if (name === "height" && this._container) {
      this.style.height = newValue || "80vh";
    }
    this._render();
  }

  disconnectedCallback(): void {
    this._root?.unmount();
  }

  private _render(): void {
    if (!this._root) return;

    const scenario = this.getAttribute("scenario") ?? "workbench";
    const smartRedirectUri = this.getAttribute("redirect-uri") ?? undefined;

    this._root.render(
      <App
        forceScenario={scenario}
        wasmAppUrl={WASM_APP_BASE}
        smartRedirectUri={smartRedirectUri}
      />
    );
  }
}

// Register only once (guard against duplicate script loading)
if (!customElements.get("fhir4ds-demo")) {
  customElements.define("fhir4ds-demo", FhirDsDemo);
}

// ── Popup OAuth callback handler ──────────────────────────────────────────
// When this script loads in a popup window that was redirected from an OAuth
// provider (URL has ?code= and ?state=, and window.opener exists), handle the
// token exchange and post the result back to the opener. This enables redirect
// URIs that point to the Docusaurus docs page rather than the standalone SPA.
(async () => {
  const params = new URLSearchParams(window.location.search);
  if (
    !params.has("code") ||
    !params.has("state") ||
    !window.opener ||
    window.self !== window.top
  ) {
    return; // Not a popup OAuth callback
  }

  try {
    const { handleCallback, getStoredSession } = await import("./lib/smart-auth");
    const token = await handleCallback();
    const session = getStoredSession();
    window.opener.postMessage(
      { type: "FHIR4DS_SMART_TOKEN", token, session },
      window.location.origin,
    );
    setTimeout(() => window.close(), 200);
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    if (window.opener) {
      window.opener.postMessage(
        { type: "FHIR4DS_SMART_ERROR", error: msg },
        window.location.origin,
      );
    }
  }
})();
