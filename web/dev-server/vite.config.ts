import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

// Dev-server UI: reuses wasm-demo components via fs alias (no copies).
export default defineConfig({
  plugins: [react()],
  resolve: {
    // Reused wasm-demo components live outside this package root; resolve
    // their bare imports (react, @monaco-editor/react) against OUR
    // node_modules so Rollup bundles them exactly once.
    alias: [
      {
        find: "@wasm-demo",
        replacement: path.resolve(__dirname, "../wasm-demo/src"),
      },
    ],
    dedupe: ["react", "react-dom", "@monaco-editor/react"],
  },
  build: {
    outDir: path.resolve(__dirname, "../../fhir4ds/devserver/static"),
    emptyOutDir: true,
  },
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8765",
      "/health": "http://127.0.0.1:8765",
    },
  },
});
