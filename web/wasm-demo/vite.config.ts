import { defineConfig, Plugin } from "vite";
import react from "@vitejs/plugin-react";
import { readFileSync, writeFileSync, existsSync, copyFileSync, mkdirSync, readdirSync } from "fs";
import path, { resolve } from "path";

/** COOP/COEP headers required for SharedArrayBuffer (DuckDB-WASM & Pyodide). */
const ISOLATION_HEADERS = {
  "Cross-Origin-Opener-Policy": "same-origin",
  "Cross-Origin-Embedder-Policy": "require-corp",
};

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

      // Copy Python wheel — discover by glob so the name never goes stale on version bumps
      const wheels = readdirSync(publicDir).filter(f => f.startsWith("fhir4ds_v2-") && f.endsWith(".whl"));
      for (const wheelName of wheels) {
        const wheelSrc = path.join(publicDir, wheelName);
        const wheelDst = path.join(assetsDir, wheelName);
        copyFileSync(wheelSrc, wheelDst);
        console.log(`[copyExtensionsToAssets] ${wheelName} → dist/assets/`);
      }

      // Write a manifest so the Pyodide worker can discover the wheel at runtime
      if (wheels.length > 0) {
        const manifest = JSON.stringify({ wheel: wheels[wheels.length - 1] });
        writeFileSync(path.join(assetsDir, "fhir4ds-wheel.json"), manifest);
        console.log(`[copyExtensionsToAssets] fhir4ds-wheel.json → dist/assets/`);
      }
    },
  };
}

export default defineConfig({
  base: '',
  envDir: "../../",
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
