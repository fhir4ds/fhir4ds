import { defineConfig, Plugin } from "vite";
import react from "@vitejs/plugin-react";
import crypto from "node:crypto";
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

// Content hash for immutable-cached assets whose FILENAME does not change
// between rebuilds within a version (wheel + wasm extensions). Appended as
// ?v=<hash> so a rebuilt asset busts the browser cache automatically.
function assetHash(file: string): string {
  try {
    return crypto.createHash("sha256").update(fs.readFileSync(file)).digest("hex").slice(0, 12);
  } catch {
    return "none";
  }
}

const WHEEL_HASH = assetHash(path.join(__dirname, "public", WHEEL_NAME));
const FHIRPATH_EXT_HASH = assetHash(
  path.join(__dirname, "public", "extensions", "fhirpath.duckdb_extension.wasm"),
);
const CQL_EXT_HASH = assetHash(
  path.join(__dirname, "public", "extensions", "cql.duckdb_extension.wasm"),
);

declare const __FHIR4DS_WHEEL_NAME__: string;
declare const __FHIR4DS_WHEEL_HASH__: string;
declare const __FHIR4DS_FHIRPATH_EXT_HASH__: string;
declare const __FHIR4DS_CQL_EXT_HASH__: string;

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
    // Strip cache-bust query before matching (?v=<hash>).
    const url = (req.url ?? "").split("?")[0];
    try {
      if (url.endsWith(".duckdb_extension.wasm")) {
        const file = path.join(publicDir, "extensions", path.basename(url));
        if (fs.existsSync(file)) {
          res.setHeader("Content-Type", "application/wasm");
          res.setHeader("Cross-Origin-Resource-Policy", "cross-origin");
          // Boot perf (C2-U3): cached per content hash (?v=) — a rebuilt
          // extension changes the hash and busts the cache.
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
          // Cached per content hash (?v=) — same-name rebuilds bust the cache.
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
    __FHIR4DS_WHEEL_HASH__: JSON.stringify(WHEEL_HASH),
    __FHIR4DS_FHIRPATH_EXT_HASH__: JSON.stringify(FHIRPATH_EXT_HASH),
    __FHIR4DS_CQL_EXT_HASH__: JSON.stringify(CQL_EXT_HASH),
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
