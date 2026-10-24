/**
 * SQL-on-FHIR Viewing Room — Web Component entry point (design §0/§2).
 *
 * Registers <sqlonfhir-viewing-room> as a custom element (Shadow DOM for
 * CSS isolation; Monaco head styles ported into the shadow root; app CSS
 * inlined via ?inline and scoped). Cloned from web/cql-cleanroom's
 * web-component.tsx pattern.
 *
 * Attributes:
 *   height — CSS height value for the component (default: "85vh")
 *
 * Usage:
 *   <sqlonfhir-viewing-room height="90vh"></sqlonfhir-viewing-room>
 */

import { createRoot, type Root } from "react-dom/client";
import "./lib/monaco-setup";
import App from "./App";
import { startMonacoStylePorting } from "./lib/monaco-shadow-fix";
import { setSampleBase } from "./lib/samples";

// Import full app CSS as a string for Shadow DOM injection.
import appStyles from "./styles.css?inline";

// Display name lives here (design §0: one-line swap).
export const APP_NAME = "SQL-on-FHIR Viewing Room";

// Derive the app's base URL from this bundle's own URL.
const APP_BASE = (() => {
  const base = new URL("./", import.meta.url).href;
  const parsed = new URL(base);
  if (parsed.pathname.startsWith("/src")) {
    parsed.pathname = "/";
    return parsed.href;
  }
  return base;
})();

// Samples resolve from the bundle's own location, not the host page's URL.
setSampleBase(APP_BASE);

/**
 * Rewrite CSS selectors that target the document root (html, body, #root)
 * to target the shadow DOM host container instead.
 */
function scopeStyles(css: string): string {
  let scoped = css.replace(/:root\s*\{/g, ":host {");
  scoped = scoped.replace(/html\s*,\s*body\s*,\s*#root\s*\{/g, ".viewing-room-root {");
  scoped = scoped.replace(/(?:^|\n)\s*body\s*\{/g, "\n.viewing-room-root {");
  scoped = scoped.replace(/(?:^|\n)\s*html\s*\{/g, "\n.viewing-room-root {");
  scoped = scoped.replace(/#root\s*\{/g, ".viewing-room-root {");
  return scoped;
}

// Suppress Monaco's benign ResizeObserver-loop errors.
const suppressResizeLoop = (e: ErrorEvent) => {
  if (e.message?.includes("ResizeObserver loop")) {
    e.stopImmediatePropagation();
    e.preventDefault();
  }
};
if (typeof window !== "undefined") {
  window.addEventListener("error", suppressResizeLoop);
}

class ViewingRoomElement extends HTMLElement {
  private root: Root | null = null;
  private container: HTMLDivElement | null = null;
  private stopStylePorting: (() => void) | null = null;

  static get observedAttributes(): string[] {
    return ["height"];
  }

  connectedCallback() {
    if (this.root) return; // already mounted

    this.container = document.createElement("div");
    this.container.className = "viewing-room-root";
    this.container.style.height = this.getAttribute("height") ?? "85vh";

    const shadow = this.attachShadow({ mode: "open" });
    this.stopStylePorting = startMonacoStylePorting(shadow);
    // The module-script WC build never links CSS chunks — fetch the two
    // stable-named stylesheets (app.css / monaco.css) into the shadow root.
    fetch(new URL("assets/app.css", APP_BASE).href, { mode: "same-origin" })
      .then((r) => (r.ok ? r.text() : Promise.reject(new Error(String(r.status)))))
      .then((css) => {
        const style = document.createElement("style");
        style.setAttribute("data-viewing-room-app-css", "");
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
        style.setAttribute("data-viewing-room-monaco-css", "");
        style.textContent = css;
        shadow.appendChild(style);
      })
      .catch(() => {
        // Dev server — same as above.
      });
    const style = document.createElement("style");
    // Scope viewport-fixed app chrome (boot overlay) to the component.
    style.textContent = scopeStyles(appStyles) + `
      :host { display: block; }
      .viewing-room-root {
        height: 100%;
        overflow: visible;
        position: relative;
        color-scheme: dark;
        font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
      }
      .viewing-room-root .app { height: 100%; min-height: 480px; }
      .viewing-room-root .boot-overlay {
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
    if (name === "height" && this.container) {
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

if (typeof window !== "undefined" && !customElements.get("sqlonfhir-viewing-room")) {
  customElements.define("sqlonfhir-viewing-room", ViewingRoomElement);
}

export { APP_BASE };
