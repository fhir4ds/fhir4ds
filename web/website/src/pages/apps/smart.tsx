import type { ReactElement } from "react";
import DemoAppWindow from "@site/src/components/DemoAppWindow";
import WasmDemoWC from "@site/src/components/WasmDemoWC";

/** Standalone pop-out of the SMART on FHIR example (docs: /docs/examples/smart-demo).
 *  OAuth callbacks land back on this page — WasmDemoWC detects the code/state
 *  params and hands the token to the web component. */
export default function SmartAppPage(): ReactElement {
  return (
    <DemoAppWindow title="SMART on FHIR">
      <WasmDemoWC scenario="smart-flow" height="calc(100vh - 100px)" />
    </DemoAppWindow>
  );
}
