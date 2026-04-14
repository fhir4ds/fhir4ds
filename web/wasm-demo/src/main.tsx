import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { SmartCallbackPage } from "./components/SmartCallbackPage";
import { isSmartCallback, isPopupContext } from "./lib/smart-auth";
import "./styles/index.css";

const root = document.getElementById("root")!;

// Short-circuit: if this is an OAuth popup callback, render the lightweight
// handler only. DuckDB and Pyodide are never initialized in this path.
if (isSmartCallback() && isPopupContext()) {
  createRoot(root).render(<SmartCallbackPage />);
} else {
  createRoot(root).render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
}
