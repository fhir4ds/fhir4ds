/**
 * C2-U3: share links — workspace-in-a-URL.
 *
 * Encodes {libraries, cases, output_columns, parameters} (NEVER datasets,
 * per plan S-C2 constraint) into an LZ-compressed URL hash fragment
 * (`#s=<base64>`), capped at 100 KB. Fragment-only sharing keeps URLs
 * host-agnostic (any deployment can open the same share).
 */

import { deflateSync, inflateSync, strFromU8, strToU8 } from "fflate";

export interface SharePayloadLibrary {
  name: string;
  text: string;
}

export interface SharePayload {
  format: "cql-cleanroom-share";
  version: 1;
  libraries: SharePayloadLibrary[];
  activeIndex?: number | null;
  outputColumns?: Record<string, string> | null;
  parameters?: Record<string, unknown> | null;
  cases?: unknown | null;
}

const MAX_FRAGMENT_BYTES = 100 * 1024;
const PREFIX = "#s=";

function toBase64(bytes: Uint8Array): string {
  let bin = "";
  for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
  // URL-safe: hash fragments must survive copy/paste without escaping
  return btoa(bin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function fromBase64(b64: string): Uint8Array {
  const norm = b64.replace(/-/g, "+").replace(/_/g, "/");
  const pad = norm.length % 4 === 0 ? "" : "=".repeat(4 - (norm.length % 4));
  const bin = atob(norm + pad);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

/** Encode a share payload to `#s=...` (throws if > 100 KB). */
export function encodeShareFragment(payload: SharePayload): string {
  if (!payload.libraries?.length) {
    throw new Error("share payload requires at least one library");
  }
  const json = JSON.stringify(payload);
  const compressed = deflateSync(strToU8(json), { level: 9 });
  const frag = PREFIX + toBase64(compressed);
  if (frag.length > MAX_FRAGMENT_BYTES) {
    throw new Error(
      `share fragment too large (${frag.length} bytes > ${MAX_FRAGMENT_BYTES}); ` +
        "remove libraries or use Export zip instead",
    );
  }
  return frag;
}

/** Decode a `#s=...` hash; returns null when absent or malformed. */
export function decodeShareFragment(hash: string): SharePayload | null {
  const idx = hash.indexOf(PREFIX);
  if (idx === -1) return null;
  const b64 = hash.slice(idx + PREFIX.length).split("&")[0];
  if (!b64) return null;
  try {
    const json = strFromU8(inflateSync(fromBase64(b64)));
    const payload = JSON.parse(json) as SharePayload;
    if (payload?.format !== "cql-cleanroom-share" || payload.version !== 1) {
      return null;
    }
    if (!Array.isArray(payload.libraries) || payload.libraries.length === 0) {
      return null;
    }
    return payload;
  } catch {
    return null;
  }
}

/** Full URL for the current origin with the share fragment attached. */
export function buildShareUrl(payload: SharePayload): string {
  return `${location.origin}${location.pathname}${encodeShareFragment(payload)}`;
}
