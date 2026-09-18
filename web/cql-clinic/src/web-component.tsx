/**
 * CQL Clinic — Web Component entry point.
 *
 * Registers <cql-clinic> as a custom element. The React app renders into
 * a Shadow DOM root for CSS isolation (prevents the app's dark-mode body
 * styles from leaking into the host page).
 *
 * Attributes:
 *   height — CSS height value for the component (default: "85vh")
 *
 * Usage:
 *   <cql-clinic height="90vh"></cql-clinic>
 *
 * Asset paths: DuckDB/Pyodide assets resolve relative to this bundle's URL.
 * In production this is typically /cql-clinic-app/.
 */

import { createRoot, type Root } from "react-dom/client";
import App from "./App";
import { startMonacoStylePorting } from "./lib/monaco-shadow-fix";

// Import full app CSS as a string for Shadow DOM injection.
import appStyles from "./styles.css?inline";

// Derive the app's base URL from this bundle's own URL.
// In production: "https://fhir4ds.com/cql-clinic-app/"
// In Vite dev: strip a leading /src/ (assets are at root).
const APP_BASE = (() => {
  const base = new URL("./", import.meta.url).href;
  const parsed = new URL(base);
  if (parsed.pathname.startsWith("/src")) {
    parsed.pathname = "/";
    return parsed.href;
  }
  return base;
})();

/**
 * Rewrite CSS selectors that target the document root (html, body, #root)
 * to target the shadow DOM host container instead.
 */
function scopeStyles(css: string): string {
  let scoped = css.replace(/:root\s*\{/g, ":host {");
  scoped = scoped.replace(/html\s*,\s*body\s*,\s*#root\s*\{/g, ".cql-clinic-root {");
  scoped = scoped.replace(/(?:^|\n)\s*body\s*\{/g, "\n.cql-clinic-root {");
  scoped = scoped.replace(/(?:^|\n)\s*html\s*\{/g, "\n.cql-clinic-root {");
  scoped = scoped.replace(/#root\s*\{/g, ".cql-clinic-root {");
  return scoped;
}

// Suppress Monaco's benign ResizeObserver-loop errors (see main.tsx).
const suppressResizeLoop = (e: ErrorEvent) => {
  if (e.message?.includes("ResizeObserver loop")) {
    e.stopImmediatePropagation();
    e.preventDefault();
  }
};
if (typeof window !== "undefined") {
  window.addEventListener("error", suppressResizeLoop);
}

class CqlClinicElement extends HTMLElement {
  private root: Root | null = null;
  private container: HTMLDivElement | null = null;
  private stopStylePorting: (() => void) | null = null;

  static get observedAttributes(): string[] {
    return ["height"];
  }

  connectedCallback() {
    if (this.root) return; // already mounted

    this.container = document.createElement("div");
    this.container.className = "cql-clinic-root";
    this.container.style.height = this.getAttribute("height") ?? "85vh";

    const shadow = this.attachShadow({ mode: "open" });
    // Monaco loads at runtime and injects its CSS into document.head, which
    // doesn't cross the shadow boundary — port those styles in as they appear.
    this.stopStylePorting = startMonacoStylePorting(shadow);
    const style = document.createElement("style");
    style.textContent = scopeStyles(appStyles) + `
      :host { display: block; }
      .cql-clinic-root {
        height: 100%;
        overflow-y: auto;
        color-scheme: dark;
        font-family: ui-sans-serif, system-ui, -apple-system, sans-serif;
      }
    `;
    shadow.appendChild(style);
    shadow.appendChild(this.container);

    this.root = createRoot(this.container);
    this.root.render(<App />);
  }

  attributeChangedCallback() {
    if (this.container) {
      this.container.style.height = this.getAttribute("height") ?? "85vh";
    }
  }

  disconnectedCallback() {
    this.stopStylePorting?.();
    this.stopStylePorting = null;
    this.root?.unmount();
    this.root = null;
    this.container = null;
  }
}

if (typeof window !== "undefined" && !customElements.get("cql-clinic")) {
  customElements.define("cql-clinic", CqlClinicElement);
}

export { APP_BASE };
