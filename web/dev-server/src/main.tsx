import React from "react";
import ReactDOM from "react-dom/client";
import { App } from "./App";
import "@wasm-demo/styles/index.css";
import "./styles.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
