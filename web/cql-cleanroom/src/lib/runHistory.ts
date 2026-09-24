/**
 * WORKBENCH_REORG §3.3 — run history helpers.
 *
 * Pure functions for building run entries from evaluation results.
 * Hashes are SHA-256 (Web Crypto) over normalized inputs: library
 * text with line endings normalized, dataset as key-sorted canonical
 * JSON — so whitespace-only edits and property reordering do not
 * produce false drift warnings.
 */

import type { RunEntry } from "../state/workspace";

export async function sha256Hex(input: string): Promise<string> {
  const data = new TextEncoder().encode(input);
  const digest = await crypto.subtle.digest("SHA-256", data);
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

export function normalizeText(text: string): string {
  return text.replace(/\r\n?/g, "\n");
}

/** Deterministic canonical JSON: object keys sorted recursively. */
export function canonicalJson(value: unknown): string {
  if (value === null || typeof value !== "object") {
    return JSON.stringify(value) ?? "null";
  }
  if (Array.isArray(value)) {
    return `[${value.map(canonicalJson).join(",")}]`;
  }
  const obj = value as Record<string, unknown>;
  const keys = Object.keys(obj).sort();
  return `{${keys
    .map((k) => `${JSON.stringify(k)}:${canonicalJson(obj[k])}`)
    .join(",")}}`;
}

export async function libraryHash(text: string): Promise<string> {
  return sha256Hex(normalizeText(text));
}

export async function datasetHash(
  dataset: { resources?: unknown[] } | null,
): Promise<string> {
  return sha256Hex(canonicalJson(dataset?.resources ?? []));
}

/**
 * Row-shaped memberships artifact from evaluation rows: population
 * columns (non-patient_id) per patient, booleans preserved as-is
 * (null stays null — the flipped domain in compare).
 */
export function artifactFromRows(
  rows: Array<Record<string, unknown>>,
  columns: string[],
): RunEntry["artifact"] {
  const populationColumns = columns.filter((c) => c !== "patient_id");
  const patients: RunEntry["artifact"]["patients"] = {};
  for (const row of rows) {
    const pid = String(row["patient_id"] ?? "");
    const populations: Record<string, boolean | null> = {};
    for (const col of populationColumns) {
      const v = row[col];
      populations[col] = v === true || v === false ? v : null;
    }
    patients[pid] = { populations };
  }
  return { patients };
}

export function appendRun(
  history: RunEntry[],
  entry: RunEntry,
  cap: number,
): RunEntry[] {
  const next = [...history, entry];
  return next.length > cap ? next.slice(next.length - cap) : next;
}

export function defaultRunName(createdAt: number): string {
  return formatRunTimestamp(createdAt);
}

/** Full date+time label for runs and eval surfaces (2026-09-23 14:03:05). */
export function formatRunTimestamp(createdAt: number): string {
  const d = new Date(createdAt);
  const pad = (n: number) => String(n).padStart(2, "0");
  return (
    `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ` +
    `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
  );
}

/** Which inputs drifted between a saved run and the current inputs. */
export function driftKind(
  run: RunEntry,
  currentLibraryHash: string,
  currentDatasetHash: string,
): { library: boolean; dataset: boolean } {
  return {
    library: run.libraryHash !== currentLibraryHash,
    dataset: run.datasetHash !== currentDatasetHash,
  };
}

export function newRunId(): string {
  return `r${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`;
}
