import { defineConfig, Plugin } from "vite";
import react from "@vitejs/plugin-react";
import fs from "node:fs";
import path from "node:path";

// ---------------------------------------------------------------------------
// Wheel auto-discovery: exactly ONE fhir4ds_v2-*.whl lives in public/.
// Built from the WORKING TREE (hatch build -t wheel → copy), never a stale
// released version — the cleanroom must test current operations.
// ---------------------------------------------------------------------------
function discoverWheelName(root: string): string {
  const publicDir = path.join(root, "public");
  const candidates = fs
    .readdirSync(publicDir)
    .filter((f) => /^fhir4ds_v2-.*\.whl$/.test(f))
    .sort();
  if (candidates.length === 0) return "fhir4ds_v2-0.0.17-py3-none-any.whl";
  if (candidates.length > 1) {
    throw new Error(
      `multiple wheels in public/: ${candidates.join(", ")} — keep exactly one`,
    );
  }
  return candidates[0];
}

const WHEEL_NAME = discoverWheelName(__dirname);

declare const __FHIR4DS_WHEEL_NAME__: string;

// ---------------------------------------------------------------------------
// Cross-origin isolation: DuckDB-WASM needs SharedArrayBuffer (COOP/COEP).
// The .whl and .duckdb_extension.wasm assets carry CORP for COEP.
// ---------------------------------------------------------------------------
const ISOLATION_HEADERS = {
  "Cross-Origin-Opener-Policy": "same-origin",
  "Cross-Origin-Embedder-Policy": "require-corp",
};

function assetMiddleware(): Plugin {
  const root = __dirname;
  const publicDir = path.join(root, "public");
  return {
    name: "cleanroom-asset-middleware",
    configureServer(server: any) {
      server.middlewares.use(handler(publicDir));
    },
    configurePreviewServer(server: any) {
      server.middlewares.use(handler(publicDir));
    },
  };
}

function handler(publicDir: string) {
  return (req: any, res: any, next: () => void) => {
    const url = req.url ?? "";
    try {
      if (url.endsWith(".duckdb_extension.wasm")) {
        const file = path.join(publicDir, "extensions", path.basename(url));
        if (fs.existsSync(file)) {
          res.setHeader("Content-Type", "application/wasm");
          res.setHeader("Cross-Origin-Resource-Policy", "cross-origin");
          // Boot perf (C2-U3): the bundled wasm extensions are immutable
          // per build — let the browser cache them across sessions.
          res.setHeader("Cache-Control", "public, max-age=31536000, immutable");
          fs.createReadStream(file).pipe(res);
          return;
        }
      }
      if (url.endsWith(".whl")) {
        const file = path.join(publicDir, path.basename(url));
        if (fs.existsSync(file)) {
          res.setHeader("Content-Type", "application/x-wheel+zip");
          res.setHeader("Cross-Origin-Resource-Policy", "cross-origin");
          // Versioned filename (fhir4ds_v2-X.Y.Z) — safe to cache hard.
          res.setHeader("Cache-Control", "public, max-age=31536000, immutable");
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

// ---------------------------------------------------------------------------
// Post-build: copy the WASM extensions + wheel into dist/assets/ so static
// hosting serves them next to the hashed worker bundle.
// ---------------------------------------------------------------------------
function copyAssetsToDist(): Plugin {
  const root = __dirname;
  return {
    name: "copy-cleanroom-assets",
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

export default defineConfig({
  base: "",
  define: {
    __FHIR4DS_WHEEL_NAME__: JSON.stringify(WHEEL_NAME),
  },
  plugins: [react(), assetMiddleware(), copyAssetsToDist()],
  build: {
    rollupOptions: {
      output: {
        entryFileNames: "assets/[name]-[hash].js",
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
