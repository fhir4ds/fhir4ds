# Custom Web Components

The FHIR4DS WASM engine is designed to be the foundation for custom clinical applications. Because it runs entirely in the browser, you can use any modern UI framework (React, Vue, Svelte) or standard **Web Components** to build tailored workflows.

## Why Web Components?

Web Components are the ideal pattern for clinical software, particularly for **SMART on FHIR** applications meant to run inside an EHR portal (like Epic or Cerner). They provide three critical advantages for healthcare developers:

### 1. Style Isolation (Shadow DOM)
Standard EHR portals often have complex, rigid CSS. Using Web Components ensures your clinical logic and UI (e.g., a "Calculated Risk" badge) are encapsulated in a **Shadow DOM**. Your widget will look and behave exactly the same in Epic as it does in Cerner, and your styles will never "leak" out and break the host EHR's layout.

### 2. Framework-Agnostic Portability
Clinical IT departments often have restrictive environments. By building a Web Component, you can distribute a **single `.js` bundle** that can be dropped into any HTML page. Whether the host site uses React, Angular, or legacy PHP, your component will work without requiring the host to manage a complex build pipeline.

### 3. Local Performance
By using the FHIR4DS WASM engine inside your component, clinical calculations happen **locally on the clinician's machine**. This provides zero-latency feedback for real-time decision support and eliminates the need for a round-trip to a centralized clinical reasoning server.

---

## Blueprint: A Reactive Clinical Widget

A robust clinical widget should be **reactive**—it should update its internal state when the host application changes an attribute (like the current `patient-id`).

```typescript
class ClinicalWidget extends HTMLElement {
  static get observedAttributes() { return ['patient-id']; }

  async connectedCallback() {
    this.attachShadow({ mode: 'open' });
    await this.initEngine();
    this.render();
  }

  // Handle attribute changes (e.g. from the EHR)
  async attributeChangedCallback(name, oldVal, newVal) {
    if (name === 'patient-id' && oldVal !== newVal) {
      await this.updateData(newVal);
      this.render();
    }
  }

  async initEngine() {
    // 1. Initialize DuckDB + Extensions (see WASM Engine guide)
    // Be sure to register/load BOTH 'fhirpath' and 'cql' extensions.
    await db.registerFileURL("fhirpath.duckdb_extension.wasm", ...);
    await db.registerFileURL("cql.duckdb_extension.wasm", ...);
    
    await conn.query("LOAD 'fhirpath.duckdb_extension.wasm'");
    await conn.query("LOAD 'cql.duckdb_extension.wasm'");

    // 2. Load mandatory 'resources' table
  }

  render() {
    this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; padding: 1rem; background: var(--bg-color, #fff); }
        .score { font-weight: bold; color: var(--accent-color, blue); }
      </style>
      <div class="score">Calculated Score: ${this.score}</div>
    `;
  }
}
customElements.define('clinical-widget', ClinicalWidget);
```

---

## Reference Implementation

For a comprehensive example of this pattern—including how to handle complex React state, Monaco editors, and scenario-based routing—see the [FHIR4DS Reference Web Component](https://github.com/joelmontavon/fhir4ds-v2/blob/main/web/wasm-demo/src/web-component.tsx) on GitHub.
