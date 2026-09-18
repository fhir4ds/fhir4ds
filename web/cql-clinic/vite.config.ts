import { defineConfig, Plugin } from "vite";
import react from "@vitejs/plugin-react";
import fs from "node:fs";
import path from "node:path";

// ---------------------------------------------------------------------------
// Wheel auto-discovery: exactly ONE fhir4ds_v2-*.whl lives in public/.
// The name is baked into the Pyodide worker via define so it can resolve the
// wheel next to its own bundle URL (new URL(`./${name}`, import.meta.url)).
// ---------------------------------------------------------------------------
function discoverWheelName(root: string): string {
  const publicDir = path.join(root, "public");
  const candidates = fs
    .readdirSync(publicDir)
    .filter((f) => /^fhir4ds_v2-.*\.whl$/.test(f))
    .sort();
  if (candidates.length > 0) return candidates[candidates.length - 1];
  return "fhir4ds_v2-0.0.13-py3-none-any.whl";
}

const WHEEL_NAME = discoverWheelName(__dirname);

declare const __FHIR4DS_WHEEL_NAME__: string;

// ---------------------------------------------------------------------------
// Dev/preview middleware: serve .duckdb_extension.wasm from public/extensions/
// and the fhir4ds wheel from public/ with the Cross-Origin-Resource-Policy
// header. Emscripten's dlopen in the DuckDB-WASM worker resolves extension
// URLs relative to the worker script, so they must carry CORP for COEP.
// ---------------------------------------------------------------------------
const ISOLATION_HEADERS = {
  "Cross-Origin-Opener-Policy": "same-origin",
  "Cross-Origin-Embedder-Policy": "require-corp",
};

function extensionHandler(root: string) {
  const publicDir = path.join(root, "public");
  return (req: any, res: any, next: any) => {
    const url = req.url ?? "";
    try {
      if (url.endsWith(".duckdb_extension.wasm")) {
        const file = path.join(publicDir, "extensions", path.basename(url));
        if (fs.existsSync(file)) {
          res.setHeader("Content-Type", "application/wasm");
          res.setHeader("Cross-Origin-Resource-Policy", "cross-origin");
          fs.createReadStream(file).pipe(res);
          return;
        }
      }
      if (url.endsWith(".whl")) {
        const file = path.join(publicDir, path.basename(url));
        if (fs.existsSync(file)) {
          res.setHeader("Content-Type", "application/x-wheel+zip");
          res.setHeader("Cross-Origin-Resource-Policy", "cross-origin");
          fs.createReadStream(file).pipe(res);
          return;
        }
      }
    } catch {
      // fall through to next handler
    }
    next();
  };
}

function duckdbExtensionMiddleware(): Plugin {
  const root = __dirname;
  return {
    name: "duckdb-extension-middleware",
    configureServer(server: any) {
      server.middlewares.use(extensionHandler(root));
    },
    configurePreviewServer(server: any) {
      server.middlewares.use(extensionHandler(root));
    },
  };
}

// ---------------------------------------------------------------------------
// Post-build: copy the WASM extensions + wheel into dist/assets/ so static
// hosting (GitHub Pages) serves them next to the hashed worker bundle.
// ---------------------------------------------------------------------------
function copyExtensionsToAssets(): Plugin {
  const root = __dirname;
  return {
    name: "copy-extensions-to-assets",
    writeBundle() {
      const assetsDir = path.join(root, "dist", "assets");
      fs.mkdirSync(assetsDir, { recursive: true });
      const extDir = path.join(root, "public", "extensions");
      for (const ext of [
        "fhirpath.duckdb_extension.wasm",
        "cql.duckdb_extension.wasm",
      ]) {
        const src = path.join(extDir, ext);
        if (fs.existsSync(src)) {
          fs.copyFileSync(src, path.join(assetsDir, ext));
        }
      }
      const wheel = path.join(root, "public", WHEEL_NAME);
      if (fs.existsSync(wheel)) {
        fs.copyFileSync(wheel, path.join(assetsDir, WHEEL_NAME));
      }
    },
  };
}

// ---------------------------------------------------------------------------
// Dev middleware: alias /cql-clinic.js to the WC source so the test harness
// works during `vite dev` (the stable filename is build-only).
// ---------------------------------------------------------------------------
function devWcAlias(): Plugin {
  return {
    name: "dev-wc-alias",
    configureServer(server) {
      server.middlewares.use((req: any, _res: any, next: any) => {
        if (req.url === "/cql-clinic.js") {
          req.url = "/src/web-component.tsx";
        }
        next();
      });
    },
  };
}

export default defineConfig({
  base: "",
  define: {
    __FHIR4DS_WHEEL_NAME__: JSON.stringify(WHEEL_NAME),
  },
  plugins: [react(), devWcAlias(), duckdbExtensionMiddleware(), copyExtensionsToAssets()],
  build: {
    rollupOptions: {
      input: {
        main: path.resolve(__dirname, "index.html"),
        "cql-clinic": path.resolve(__dirname, "src/web-component.tsx"),
      },
      output: {
        // Stable filename for the Web Component (no content hash) so the
        // Docusaurus <script src="..."> tag never needs updating.
        entryFileNames: (chunk: { name: string }) =>
          chunk.name === "cql-clinic"
            ? "cql-clinic.js"
            : "assets/[name]-[hash].js",
        chunkFileNames: "assets/[name]-[hash].js",
        // The shared chunk's CSS (Monaco's stylesheet) also needs a stable
        // name: module-script consumers (the web component) never link CSS
        // chunks, so it is fetched into the shadow root at runtime by name.
        assetFileNames: (assetInfo: any) => {
          // names include the extension ("App.css")
          const name = (assetInfo.names?.[0] ?? assetInfo.name ?? "").replace(/\.[^.]*$/, "");
          return name === "App" ? "assets/app.css" : "assets/[name]-[hash][extname]";
        },
      },
    },
  },
  server: {
    headers: ISOLATION_HEADERS,
  },
  preview: {
    headers: ISOLATION_HEADERS,
  },
  optimizeDeps: {
    exclude: ["@duckdb/duckdb-wasm"],
  },
  worker: {
    format: "es",
  },
});
