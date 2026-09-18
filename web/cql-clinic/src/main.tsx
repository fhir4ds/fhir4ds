// Monaco's automaticLayout ResizeObserver commonly emits benign
// "ResizeObserver loop completed with undelivered notifications"
// errors (the observer reacts to its own resize; the browser retries
// next frame). Suppress exactly that message before anything mounts.
const suppressResizeLoop = (e: ErrorEvent) => {
  if (e.message?.includes("ResizeObserver loop")) {
    e.stopImmediatePropagation();
    e.preventDefault();
  }
};
window.addEventListener("error", suppressResizeLoop);

import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./styles.css";

const container = document.getElementById("root");
if (!container) throw new Error("missing #root");

createRoot(container).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
