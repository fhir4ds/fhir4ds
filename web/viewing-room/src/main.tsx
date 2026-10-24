import { createRoot } from "react-dom/client";
import "./lib/monaco-setup";
import App from "./App";
import "./styles.css";

// Suppress Monaco's benign ResizeObserver-loop errors.
const suppressResizeLoop = (e: ErrorEvent) => {
  if (e.message?.includes("ResizeObserver loop")) {
    e.stopImmediatePropagation();
    e.preventDefault();
  }
};
window.addEventListener("error", suppressResizeLoop);

createRoot(document.getElementById("root")!).render(<App />);
