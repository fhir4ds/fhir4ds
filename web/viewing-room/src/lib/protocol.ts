/**
 * Worker protocol messages (schema:1 envelopes as JSON strings).
 */

export interface Diagnostic {
  code: string;
  severity?: string;
  message: string;
  location?: { start_line?: number | null; end_line?: number | null } | null;
}

export interface FlattenEnvelope {
  schema: 1;
  ok: boolean;
  sql?: string;
  columns?: string[];
  rows?: Array<Record<string, unknown>>;
  diagnostics?: Diagnostic[];
}

export type WorkerRequest =
  | { id: number; type: "boot" }
  | {
      id: number;
      type: "flatten_view";
      view_definition: Record<string, unknown>;
      resources: Array<Record<string, unknown>>;
      setup_sql?: string[];
    };

export interface BootOkResponse {
  id: number;
  type: "boot";
  ok: true;
  wheelVersion?: string;
  bootMs?: number;
}

export interface BootErrResponse {
  id: number;
  type: "boot";
  ok: false;
  error: string;
}

export interface CapabilityResponse {
  id: number;
  type: string;
  ok: boolean;
  envelope?: string;
  error?: string;
}

export type WorkerResponse = BootOkResponse | BootErrResponse | CapabilityResponse;
