/**
 * CQL Cleanroom — Web Component entry point.
 *
 * Registers <cql-cleanroom> as a custom element, mirroring the CQL Clinic's
 * web-component.tsx: React app renders into a Shadow DOM root for CSS
 * isolation; Monaco's runtime-injected head styles are ported into the
 * shadow root; the app's own CSS is inlined via ?inline and scoped.
 *
 * Attributes:
 *   height — CSS height value for the component (default: "85vh")
 *
 * Usage:
 *   <cql-cleanroom height="90vh"></cql-cleanroom>
 *
 * Asset paths: DuckDB/Pyodide assets resolve relative to this bundle's URL
 * (workers resolve via import.meta.url; the DuckDB extension base falls
 * back to window.location when no wasmAppUrl is passed, which is correct
 * for the /cql-cleanroom/ static deployment).
 */

import { createRoot, type Root } from "react-dom/client";
import "./lib/monaco-setup";
import App from "./App";
import { startMonacoStylePorting } from "./lib/monaco-shadow-fix";
import { setPendingDefaultExample } from "./lib/defaultExample";

// Import full app CSS as a string for Shadow DOM injection.
import appStyles from "./styles.css?inline";

// Derive the app's base URL from this bundle's own URL.
// In production: "https://fhir4ds.com/cql-cleanroom/"
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
  scoped = scoped.replace(/html\s*,\s*body\s*,\s*#root\s*\{/g, ".cql-cleanroom-root {");
  scoped = scoped.replace(/(?:^|\n)\s*body\s*\{/g, "\n.cql-cleanroom-root {");
  scoped = scoped.replace(/(?:^|\n)\s*html\s*\{/g, "\n.cql-cleanroom-root {");
  scoped = scoped.replace(/#root\s*\{/g, ".cql-cleanroom-root {");
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

class CqlCleanroomElement extends HTMLElement {
  private root: Root | null = null;
  private container: HTMLDivElement | null = null;
  private stopStylePorting: (() => void) | null = null;

  static get observedAttributes(): string[] {
    return ["height", "default-example"];
  }

  connectedCallback() {
    if (this.root) return; // already mounted

    // Host-declared initial content: default-example="cms69" boots the
    // workbench with the featured example (fresh installs only; saved
    // workspaces and share fragments take precedence inside the app).
    const defaultExample = this.getAttribute("default-example");
    if (defaultExample) setPendingDefaultExample(defaultExample);

    this.container = document.createElement("div");
    this.container.className = "cql-cleanroom-root";
    this.container.style.height = this.getAttribute("height") ?? "85vh";

    const shadow = this.attachShadow({ mode: "open" });
    // Monaco loads at runtime and injects its CSS into document.head, which
    // doesn't cross the shadow boundary — port those styles in as they appear.
    this.stopStylePorting = startMonacoStylePorting(shadow);
    // Monaco's bundled stylesheet is never linked in the module-script
    // context — fetch it into the shadow root. The cleanroom emits two
    // stable-named stylesheets: app.css (shared app styles) and
    // monaco.css (the monaco-setup chunk's stylesheet).
    fetch(new URL("assets/app.css", APP_BASE).href, { mode: "same-origin" })
      .then((r) => (r.ok ? r.text() : Promise.reject(new Error(String(r.status)))))
      .then((css) => {
        const style = document.createElement("style");
        style.setAttribute("data-cleanroom-app-css", "");
        style.textContent = css;
        shadow.appendChild(style);
      })
      .catch(() => {
        // Dev server (no built asset) — vite injects styles there anyway.
      });
    fetch(new URL("assets/monaco.css", APP_BASE).href, { mode: "same-origin" })
      .then((r) => (r.ok ? r.text() : Promise.reject(new Error(String(r.status)))))
      .then((css) => {
        const style = document.createElement("style");
        style.setAttribute("data-cleanroom-monaco-css", "");
        style.textContent = css;
        shadow.appendChild(style);
      })
      .catch(() => {
        // Dev server (no built asset) — vite injects styles there anyway.
      });
    const style = document.createElement("style");
    // Scope viewport-fixed app chrome (boot overlay, dropdown portals) to
    // the component: inside the shadow root, `position: fixed` would cover
    // the whole host page — the embed must show loading INSIDE the card
    // like the other example web components.
    style.textContent = scopeStyles(appStyles) + `
      :host { display: block; }
      .cql-cleanroom-root {
        height: 100%;
        overflow: visible;
        position: relative;
        color-scheme: dark;
        font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
      }
      /* Embed context: the app was laid out for the viewport (100vh shell,
         no page scroll). Inside the component card, let the app itself own
         scrolling (the pinned workbench scrolls internally) so header
         dropdown flyouts (File > Open > Examples) are never clipped by an
         overflow container. */
      .cql-cleanroom-root .app { height: 100%; min-height: 480px; }
      .cql-cleanroom-root .boot-overlay {
        position: absolute;
        inset: 0;
        z-index: 100;
      }
    `;
    shadow.appendChild(style);
    shadow.appendChild(this.container);

    this.root = createRoot(this.container);
    this.root.render(<App />);
  }

  attributeChangedCallback(name: string) {
    if (name === "default-example") {
      // Only meaningful before mount; attribute changes after mount are
      // ignored (the workspace restore has already consumed the value).
      return;
    }
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

if (typeof window !== "undefined" && !customElements.get("cql-cleanroom")) {
  customElements.define("cql-cleanroom", CqlCleanroomElement);
}

export { APP_BASE };
