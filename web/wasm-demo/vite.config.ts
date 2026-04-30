import { defineConfig, Plugin } from "vite";
import react from "@vitejs/plugin-react";
import { readFileSync, existsSync, copyFileSync, mkdirSync, readdirSync } from "fs";
import path, { resolve } from "path";

/** COOP/COEP headers required for SharedArrayBuffer (DuckDB-WASM & Pyodide). */
const ISOLATION_HEADERS = {
  "Cross-Origin-Opener-Policy": "same-origin",
  "Cross-Origin-Embedder-Policy": "require-corp",
};

/**
 * Discover the fhir4ds wheel name at config-parse time.
 * Injected into the Pyodide worker via Vite's `define` so the worker
 * can resolve the URL without any runtime fetch — works in both dev
 * and production modes without relying on a manifest file.
 */
const _publicDir = path.join(__dirname, "public");
const _wheels = readdirSync(_publicDir).filter(f => f.startsWith("fhir4ds_v2-") && f.endsWith(".whl"));
const WHEEL_NAME = _wheels[_wheels.length - 1] ?? "fhir4ds_v2-0.0.3-py3-none-any.whl";

/**
 * Middleware that serves `.duckdb_extension.wasm` files from `public/extensions/`.
 *
 * DuckDB-WASM's LOAD for WASM side-module extensions uses Emscripten's dlopen,
 * which resolves filenames relative to the worker script URL (inside node_modules).
 * This middleware intercepts those requests and serves the correct local files.
 */
function extensionHandler(req: any, res: any, next: Function) {
  const url: string = req.url || "";
  if (url.endsWith(".duckdb_extension.wasm")) {
    const filename = url.split("/").pop()!;
    const filePath = path.join(__dirname, "public/extensions", filename);
    if (existsSync(filePath)) {
      const data = readFileSync(filePath);
      res.setHeader("Content-Type", "application/wasm");
      res.setHeader("Cross-Origin-Resource-Policy", "cross-origin");
      res.setHeader("Content-Length", data.length);
      res.end(data);
      return;
    }
  }
  if (url.endsWith(".whl")) {
    const filename = url.split("/").pop()!;
    const filePath = path.join(__dirname, "public", filename);
    if (existsSync(filePath)) {
      const data = readFileSync(filePath);
      res.setHeader("Content-Type", "application/x-wheel+zip");
      res.setHeader("Cross-Origin-Resource-Policy", "cross-origin");
      res.setHeader("Content-Length", data.length);
      res.end(data);
      return;
    }
  }
  next();
}

/**
 * Vite plugin: applies COOP/COEP headers and DuckDB extension serving to both
 * the dev server AND the preview server so that Playwright tests work with
 * `vite preview` as well as `vite dev`.
 */
function duckdbExtensionMiddleware(): Plugin {
  return {
    name: "duckdb-extension-middleware",
    configureServer(server) {
      server.middlewares.use(extensionHandler);
    },
    configurePreviewServer(server) {
      server.middlewares.use(extensionHandler);
    },
  };
}

/**
 * In dev mode, Vite doesn't emit `/fhir4ds-demo.js` (that's build-only).
 * Rewrite requests to `/fhir4ds-demo.js` → `/src/web-component.tsx` so that
 * the WC test harness (`wc-test.html`) works during `vite dev`.
 */
function devWcAlias(): Plugin {
  return {
    name: "dev-wc-alias",
    configureServer(server) {
      server.middlewares.use((req, _res, next) => {
        if (req.url === "/fhir4ds-demo.js") {
          req.url = "/src/web-component.tsx";
        }
        next();
      });
    },
  };
}

/**
 * After build, copy `.duckdb_extension.wasm` files into `dist/assets/`.
 *
 * DuckDB-WASM's Emscripten dlopen resolves extension filenames relative to the
 * worker script URL (which lives in `assets/`). The files must therefore also
 * be present in `assets/` for production deployments where no catch-all
 * middleware is available (e.g. Docusaurus static hosting, GitHub Pages).
 */
function copyExtensionsToAssets(): Plugin {
  return {
    name: "copy-extensions-to-assets",
    writeBundle(options) {
      const outDir = options.dir || "dist";
      const assetsDir = path.join(outDir, "assets");
      const extensionsDir = path.join(__dirname, "public", "extensions");
      const publicDir = path.join(__dirname, "public");
      mkdirSync(assetsDir, { recursive: true });
      
      // Copy DuckDB extensions
      for (const ext of [
        "fhirpath.duckdb_extension.wasm",
        "cql.duckdb_extension.wasm",
      ]) {
        const src = path.join(extensionsDir, ext);
        const dst = path.join(assetsDir, ext);
        if (existsSync(src)) {
          copyFileSync(src, dst);
          console.log(`[copyExtensionsToAssets] ${ext} → dist/assets/`);
        }
      }

      // Copy Python wheel — WHEEL_NAME is already resolved at config time
      const wheelSrc = path.join(publicDir, WHEEL_NAME);
      const wheelDst = path.join(assetsDir, WHEEL_NAME);
      if (existsSync(wheelSrc)) {
        copyFileSync(wheelSrc, wheelDst);
        console.log(`[copyExtensionsToAssets] ${WHEEL_NAME} → dist/assets/`);
      }
    },
  };
}

export default defineConfig({
  base: '',
  envDir: "../../",
  define: {
    // Bake the wheel filename into the Pyodide worker at compile time.
    // This avoids any runtime fetch — works identically in dev and build modes.
    __FHIR4DS_WHEEL_NAME__: JSON.stringify(WHEEL_NAME),
  },
  plugins: [react(), devWcAlias(), duckdbExtensionMiddleware(), copyExtensionsToAssets()],
  build: {
    rollupOptions: {
      input: {
        main: resolve(__dirname, "index.html"),
        "fhir4ds-demo": resolve(__dirname, "src/web-component.tsx"),
      },
      output: {
        // Stable filename for the Web Component (no content hash) so the
        // Docusaurus <script src="..."> tag never needs updating.
        entryFileNames: (chunk) =>
          chunk.name === "fhir4ds-demo"
            ? "fhir4ds-demo.js"
            : "assets/[name]-[hash].js",
        chunkFileNames: "assets/[name]-[hash].js",
        assetFileNames: "assets/[name]-[hash][extname]",
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
