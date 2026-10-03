import type {
  EvaluateResult,
  EvidenceResult,
  HealthInfo,
  TranslateResult,
  Transport,
  VerifyResult,
  WorkspaceEvent,
  WorkspaceInfo,
  WorkspaceLibrary,
} from "./transport";

/** Server-side transport: thin fetch wrappers over the dev-server API. */
export class HttpTransport implements Transport {
  private base: string;
  private ws: WebSocket | null = null;

  constructor(base = "") {
    this.base = base;
  }

  private async get<T>(path: string): Promise<T> {
    const r = await fetch(`${this.base}${path}`);
    return (await r.json()) as T;
  }

  private async post<T>(path: string, body: unknown): Promise<T> {
    const r = await fetch(`${this.base}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    return (await r.json()) as T;
  }

  health(): Promise<HealthInfo> {
    return this.get("/health");
  }

  workspace(): Promise<WorkspaceInfo> {
    return this.get("/api/workspace").then((w: any) => w.workspace);
  }

  library(name: string): Promise<WorkspaceLibrary> {
    return this.get(`/api/libraries/${encodeURIComponent(name)}`);
  }

  translate(
    libraries: { name: string; text: string }[],
    library: string,
  ): Promise<TranslateResult> {
    return this.post("/api/translate", { libraries, library, emit_sql: true });
  }

  evaluate(
    libraries: { name: string; text: string }[],
    library: string,
    define?: string,
  ): Promise<EvaluateResult> {
    return this.post("/api/evaluate", { libraries, library, define });
  }

  verify(
    libraries: { name: string; text: string }[],
    library: string,
    cases: unknown[],
  ): Promise<VerifyResult> {
    return this.post("/api/verify", { libraries, library, cases });
  }

  explain(
    libraries: { name: string; text: string }[],
    library: string,
    patientId: string,
  ): Promise<EvidenceResult> {
    return this.post("/api/explain", {
      libraries,
      library,
      patient_id: patientId,
    });
  }

  restartKernel(): Promise<HealthInfo> {
    return this.post("/api/kernel/restart", {});
  }

  onWorkspaceEvent(cb: (e: WorkspaceEvent) => void): () => void {
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    const url = `${proto}//${location.host}${this.base}/api/events`;
    const socket = new WebSocket(url);
    this.ws = socket;
    socket.onmessage = (msg) => {
      try {
        const parsed = JSON.parse(msg.data) as
          | { kind: "ping" | "connected" }
          | WorkspaceEvent;
        if (parsed.kind === "changed" || parsed.kind === "data-hint") {
          cb(parsed);
        }
      } catch {
        /* ignore malformed frames */
      }
    };
    return () => {
      socket.close();
      if (this.ws === socket) this.ws = null;
    };
  }
}
