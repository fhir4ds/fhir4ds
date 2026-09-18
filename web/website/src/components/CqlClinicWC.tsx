/**
 * CqlClinicWC — Docusaurus wrapper for the <cql-clinic> Web Component.
 *
 * Handles:
 *   - SSR: BrowserOnly guard (Docusaurus pre-renders; the WC requires browser APIs)
 *   - Script deduplication: cql-clinic.js is only injected once per page
 *
 * Usage in .mdx:
 *   import CqlClinicWC from '@site/src/components/CqlClinicWC';
 *   <CqlClinicWC />
 *   <CqlClinicWC height="90vh" />
 */

import BrowserOnly from "@docusaurus/BrowserOnly";
import useDocusaurusContext from "@docusaurus/useDocusaurusContext";
import PopoutPill from "./PopoutPill";

const SCRIPT_ID = "cql-clinic-wc-bundle";

function injectWcScript(scriptSrc: string): void {
  if (document.getElementById(SCRIPT_ID)) return;
  const script = document.createElement("script");
  script.id = SCRIPT_ID;
  script.type = "module";
  script.src = scriptSrc;
  document.head.appendChild(script);
}

interface CqlClinicWCProps {
  /** CSS height. Default: '85vh' */
  height?: string;
  /** Show an "Open in new window ↗" pill above the clinic that opens the
   *  standalone app (the clinic's static build is a full page on its own). */
  popout?: boolean;
}

function CqlClinicComponent({ height = "85vh", popout = false }: CqlClinicWCProps) {
  const {
    siteConfig: { baseUrl },
  } = useDocusaurusContext();
  injectWcScript(`${baseUrl}cql-clinic-app/cql-clinic.js`);

  return (
    <>
      {popout && <PopoutPill url={`${baseUrl}cql-clinic-app/`} />}
      <div style={{ margin: "1rem 0" }}>
        {/* @ts-expect-error cql-clinic is a custom element defined by the clinic bundle */}
        {typeof window !== "undefined" && <cql-clinic height={height} />}
      </div>
    </>
  );
}

export default function CqlClinicWC(props: CqlClinicWCProps) {
  return <BrowserOnly>{() => <CqlClinicComponent {...props} />}</BrowserOnly>;
}
