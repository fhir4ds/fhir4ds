import type { ReactElement } from "react";
import DemoAppWindow from "@site/src/components/DemoAppWindow";
import WasmDemoWC from "@site/src/components/WasmDemoWC";

/** Standalone pop-out of the Quality Measures example (docs: /docs/examples/cms-measures). */
export default function QualityMeasuresAppPage(): ReactElement {
  return (
    <DemoAppWindow title="Quality Measures">
      <WasmDemoWC scenario="cms-measures" height="calc(100vh - 100px)" />
    </DemoAppWindow>
  );
}
