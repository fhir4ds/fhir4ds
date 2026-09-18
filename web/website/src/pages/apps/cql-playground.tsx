import type { ReactElement } from "react";
import DemoAppWindow from "@site/src/components/DemoAppWindow";
import WasmDemoWC from "@site/src/components/WasmDemoWC";

/** Standalone pop-out of the CQL Playground example (docs: /docs/examples/cql-playground). */
export default function CqlPlaygroundAppPage(): ReactElement {
  return (
    <DemoAppWindow title="CQL Playground">
      <WasmDemoWC scenario="cql-sandbox" height="calc(100vh - 100px)" />
    </DemoAppWindow>
  );
}
