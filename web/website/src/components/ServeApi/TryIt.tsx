import { useState } from "react";
import type { ReactElement } from "react";
import styles from "./TryIt.module.css";

/**
 * Live runner for the FHIR REST API docs page (docs/examples/serve-api).
 *
 * Executes one request against the public demo server and shows the raw
 * response. Keyed requests read the write key from the input (persisted to
 * localStorage under "fhir4ds-write-key") — the docs never ship a real key.
 */

const BASE = "https://fhir4ds-bulk-publish-demo-server.hf.space";

type TryItProps = {
  method: "GET" | "POST" | "PUT" | "DELETE";
  path: string;
  body?: string;
  needsKey?: boolean;
  label?: string;
};

type ResponseState = {
  status: number;
  statusText: string;
  contentType: string;
  body: string;
};

export default function TryIt({
  method,
  path,
  body,
  needsKey = false,
  label,
}: TryItProps): ReactElement {
  const [writeKey, setWriteKey] = useState<string>(
    () =>
      (typeof window !== "undefined" &&
        window.localStorage.getItem("fhir4ds-write-key")) ||
      "",
  );
  const [running, setRunning] = useState(false);
  const [response, setResponse] = useState<ResponseState | null>(null);
  const [error, setError] = useState<string | null>(null);

  const persistKey = (value: string) => {
    setWriteKey(value);
    try {
      window.localStorage.setItem("fhir4ds-write-key", value);
    } catch {
      /* private mode — the in-memory value still works for this page */
    }
  };

  const run = async () => {
    setRunning(true);
    setError(null);
    setResponse(null);
    try {
      const headers: Record<string, string> = { Accept: "application/json" };
      if (body) headers["Content-Type"] = "application/fhir+json";
      if (needsKey && writeKey) headers["X-Write-Key"] = writeKey;
      const result = await fetch(BASE + path, {
        method,
        headers,
        body: body || undefined,
      });
      const text = await result.text();
      let pretty = text;
      try {
        const parsed = JSON.parse(text);
        if (Array.isArray(parsed) && parsed.length > 5) {
          pretty =
            JSON.stringify(parsed.slice(0, 5), null, 2) +
            `\n… ${parsed.length - 5} more row(s) (use _limit)`;
        } else {
          pretty = JSON.stringify(parsed, null, 2);
        }
      } catch {
        /* not JSON (ndjson/csv) — show raw, truncated */
        const lines = pretty.split("\n");
        if (lines.length > 8) {
          pretty = lines.slice(0, 8).join("\n") + `\n… ${lines.length - 8} more line(s)`;
        }
      }
      setResponse({
        status: result.status,
        statusText: result.statusText,
        contentType: result.headers.get("content-type") || "-",
        body: pretty,
      });
    } catch (exc) {
      setError(
        exc instanceof Error
          ? exc.message
          : "request failed (network or CORS — is the demo server reachable?)",
      );
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className={styles.tryit}>
      <div className={styles.bar}>
        <code className={styles.request}>
          <span className={styles.method}>{method}</span> {path}
        </code>
        {needsKey ? (
          <input
            className={styles.keyInput}
            type="password"
            placeholder="X-Write-Key"
            value={writeKey}
            onChange={(event) => persistKey(event.target.value)}
            aria-label="write key"
          />
        ) : null}
        <button
          className={styles.runButton}
          type="button"
          onClick={run}
          disabled={running}
        >
          {running ? "Running…" : `▶ Run${label ? `: ${label}` : ""}`}
        </button>
      </div>
      {error ? <div className={styles.error}>{error}</div> : null}
      {response ? (
        <div className={styles.response}>
          <div className={styles.status}>
            <span className={response.status < 400 ? styles.ok : styles.bad}>
              HTTP {response.status} {response.statusText}
            </span>
            <span className={styles.contentType}>{response.contentType}</span>
          </div>
          <pre className={styles.body}>{response.body}</pre>
        </div>
      ) : null}
    </div>
  );
}
