/**
 * ServerConnection (c-cleanroom-redo S1): minimal connected-mode client.
 *
 * Detects `fhir4ds dev` via the additive /api/mode handshake. STANDALONE
 * GUARANTEE: when the handshake fails, no further server calls are made
 * (the automated e2e asserts zero /api/* requests in standalone). The
 * in-browser engine remains the executor; the server is a terminology /
 * workspace / big-data provider only (FDD §3).
 */

export type ServerMode =
  | { kind: "standalone" }
  | {
      kind: "connected";
      version: string;
      workspace: string;
    };

export interface TerminologyConfigStatus {
  provider: string;
  configured: boolean;
  api_key_set: boolean;
}

/** Boot handshake. Never throws; failures degrade to standalone. */
export async function detectServer(base = ""): Promise<ServerMode> {
  try {
    const res = await fetch(`${base}/api/mode`, { signal: AbortSignal.timeout(4000) });
    if (!res.ok) return { kind: "standalone" };
    const body = (await res.json()) as { data?: Record<string, unknown> };
    const d = body?.data ?? (body as Record<string, unknown>);
    if (d?.server === true && typeof d.version === "string") {
      return {
        kind: "connected",
        version: d.version,
        workspace: typeof d.workspace === "string" ? d.workspace : "workspace",
      };
    }
    return { kind: "standalone" };
  } catch {
    return { kind: "standalone" };
  }
}

function unwrap<T>(payload: unknown): T {
  const d = (payload as { data?: unknown })?.data ?? payload;
  return d as T;
}

function diagOf(payload: unknown): string {
  const d = (payload as { diagnostics?: { message?: string }[] })?.diagnostics;
  return d?.[0]?.message ?? "request failed";
}

export interface VsacPreview {
  ok: boolean;
  name?: string;
  concept_count?: number;
}

export async function terminologyPreview(
  url: string,
): Promise<{ ok: boolean; message: string }> {
  const res = await fetch("/api/terminology/preview", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url }),
  });
  const d = unwrap<VsacPreview>(await res.json());
  if (!d.ok) return { ok: false, message: diagOf(d) };
  return {
    ok: true,
    message: `preview: ${d.name ?? "ValueSet"} — ${d.concept_count ?? "?"} concepts`,
  };
}

export async function terminologyImport(
  url: string,
): Promise<{ ok: boolean; message: string; valueset?: Record<string, unknown> }> {
  const res = await fetch("/api/terminology/import", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url }),
  });
  const d = unwrap<{ ok: boolean; path?: string; valueset?: Record<string, unknown> }>(
    await res.json(),
  );
  if (!d.ok) return { ok: false, message: diagOf(d) };
  return {
    ok: true,
    message: `imported ${url} → ${d.path ?? "server valuesets/"}`,
    valueset: d.valueset,
  };
}

export interface UmlsResult {
  system?: string;
  code?: string;
  display?: string;
}

export async function umlsSearch(
  query: string,
): Promise<{ ok: boolean; message: string; results?: UmlsResult[] }> {
  const res = await fetch("/api/terminology/search", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query }),
  });
  const d = unwrap<{ ok: boolean; results?: UmlsResult[] }>(await res.json());
  if (!d.ok) return { ok: false, message: diagOf(d) };
  return { ok: true, message: `${d.results?.length ?? 0} matches`, results: d.results };
}

export async function terminologyStatus(
  base = "",
): Promise<TerminologyConfigStatus | null> {
  try {
    const res = await fetch(`${base}/api/terminology/config`, {
      signal: AbortSignal.timeout(4000),
    });
    if (!res.ok) return null;
    const d = unwrap<{ config?: TerminologyConfigStatus } & Partial<TerminologyConfigStatus>>(
      await res.json(),
    );
    return (d as { config?: TerminologyConfigStatus }).config ?? (d as TerminologyConfigStatus) ?? null;
  } catch {
    return null;
  }
}
