import type { ReactElement } from "react";
import DemoAppWindow from "@site/src/components/DemoAppWindow";
import WasmDemoWC from "@site/src/components/WasmDemoWC";

/** Standalone pop-out of the SDC Forms example (docs: /docs/examples/sdc-playground). */
export default function SdcFormsAppPage(): ReactElement {
  return (
    <DemoAppWindow title="SDC Forms">
      <WasmDemoWC scenario="sdc-forms" height="calc(100vh - 100px)" />
    </DemoAppWindow>
  );
}
