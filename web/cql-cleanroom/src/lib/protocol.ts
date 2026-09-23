/**
 * Cleanroom protocol: typed message contracts mirroring
 * fhir4ds.operations signatures 1:1 (schema: 1 envelopes).
 *
 * Every request maps to exactly one operations capability; the worker
 * never invents protocol-only capabilities. Envelope shapes are shared
 * with Python via the JSON fixtures under
 * fhir4ds/operations/tests/fixtures/.
 */

// ---------------------------------------------------------------------------
// Envelope shapes (mirror of Python envelopes.py)
// ---------------------------------------------------------------------------

export const ENVELOPE_SCHEMA = 1;

export type Severity = "error" | "warning" | "info";

export type DiagnosticCode =
  | "parse_error"
  | "translation_error"
  | "evaluation_error"
  | "input_error"
  | "dataset_error"
  | "not_found"
  | "unsupported_feature"
  | "timeout";

export interface ErrorLocation {
  start_line: number;
  start_column: number;
  end_line?: number;
  end_column?: number;
  library?: string;
}

export interface Diagnostics {
  code: DiagnosticCode;
  severity: Severity;
  message: string;
  detail?: string;
  location?: ErrorLocation;
  data?: Record<string, unknown>;
}

export interface EnvelopeBase {
  schema: number;
  ok: boolean;
  passed?: boolean;
  diagnostics?: Diagnostics[];
}

// LibraryText (Python: envelopes.py LibraryText)
export interface LibraryText {
  name: string;
  text: string;
  version?: string;
}

// DatasetSpec inline forms (browser workers use inline only — no fs)
export interface DatasetSpec {
  resources?: Record<string, unknown>[];
  valueset_resources?: Record<string, unknown>[];
}

export interface TestCase {
  patient: string;
  expect: boolean;
  population?: string;
  define?: string;
  comment?: string;
}

export interface TestsInput {
  schema: number;
  cases: TestCase[];
}

// ---------------------------------------------------------------------------
// Capability envelopes (mirror of Python capability result dataclasses)
// ---------------------------------------------------------------------------

export interface ParseResult extends EnvelopeBase {
  library_name: string;
  definition_names: string[];
  parameter_names: string[];
  declarations: Array<Record<string, unknown>>;
  /** Present only when parse_cql was called with include_ast=true. */
  ast?: {
    library: string;
    statements: Record<string, AstNode | null>;
  };
}

/** Serialized CQL AST node ({"kind", "children"}; leaves inline). */
export interface AstNode {
  kind: string;
  children: Record<string, unknown>;
}

export interface TranslateResult extends EnvelopeBase {
  sql: string;
  column_types: Record<string, string>;
  definitions: string[];
}

export interface FhirpathResult extends EnvelopeBase {
  results: unknown[];
}

export interface ValidateResourceResult extends EnvelopeBase {
  valid: boolean;
  resource_type: string | null;
  resource_id: string | null;
}

export interface SchemaField {
  name: string;
  types: string[];
  cardinality: string;
  choice: boolean;
  reference_targets: string[];
}

export interface ResourceSchemaResult extends EnvelopeBase {
  resource_type: string;
  fields: SchemaField[];
}

export interface EvaluateResult extends EnvelopeBase {
  patient_count: number;
  columns: string[];
  rows: Array<Record<string, unknown>>;
  column_types: Record<string, string>;
  timing_ms: Record<string, number>;
  sql?: string;
}

export interface VerifyEnvelope extends EnvelopeBase {
  library: string;
  patients_evaluated: number;
  summary: Record<string, number>;
  tests: {
    total: number;
    passed: number;
    failed: number;
    failures: Array<{
      patient: string;
      target: string;
      expected: boolean;
      actual: boolean | null;
      reason: string | null;
    }>;
  };
  timing_ms: Record<string, number>;
}

export interface EvidenceResult extends EnvelopeBase {
  patient_id: string;
  populations: Record<string, boolean>;
  definitions: Array<{
    column: string;
    result: boolean | null;
    evidence: unknown[];
  }>;
}

export interface DatasetResult extends EnvelopeBase {
  resource_counts: Record<string, number>;
  total: number;
  detail?: string;
}

export interface CompareEvidenceResult extends EnvelopeBase {
  changed: boolean;
  summary: {
    moved: number;
    added: number;
    removed: number;
    flipped: number;
  };
  patients: Array<{
    patient_id: string;
    column: string;
    classification: "moved" | "added" | "removed" | "flipped";
    from: boolean | null;
    to: boolean | null;
    rationale: string;
  }>;
}

// ---------------------------------------------------------------------------
// Worker protocol: requests 1:1 with operations signatures
// ---------------------------------------------------------------------------

export type WorkerRequest =
  | { id: number; type: "boot" }
  | {
      id: number;
      type: "parse_cql";
      text: string;
      include_ast?: boolean;
    }
  | {
      id: number;
      type: "translate_cql";
      libraries: LibraryText[];
      main: LibraryText;
      audit_mode?: "none" | "population" | "full";
      patient_ids?: string[];
    }
  | {
      id: number;
      type: "fhirpath_eval";
      path: string;
      resource: Record<string, unknown> | null;
    }
  | {
      id: number;
      type: "validate_resource";
      resource: unknown;
    }
  | {
      id: number;
      type: "resource_schema";
      resource_type: string;
    }
  | {
      id: number;
      type: "load_dataset";
      dataset: DatasetSpec;
    }
  | {
      id: number;
      type: "evaluate_library";
      libraries: LibraryText[];
      main: LibraryText;
      dataset: DatasetSpec | null;
      parameters?: Record<string, unknown> | null;
      output_columns?: Record<string, string> | null;
      emit_sql?: boolean;
    }
  | {
      id: number;
      type: "run_tests";
      libraries: LibraryText[];
      main: LibraryText;
      dataset: DatasetSpec | null;
      tests: TestsInput;
      parameters?: Record<string, unknown> | null;
      output_columns?: Record<string, string> | null;
    }
  | {
      id: number;
      type: "explain_patient";
      libraries: LibraryText[];
      main: LibraryText;
      dataset: DatasetSpec | null;
      patient_id: string;
      parameters?: Record<string, unknown> | null;
      output_columns?: Record<string, string> | null;
    }
  | {
      id: number;
      type: "compare_evidence";
      baseline: Record<string, unknown>;
      current: Record<string, unknown>;
      output_columns?: Record<string, string> | null;
    };

export type WorkerResponse =
  | { id: number; type: "boot"; ok: boolean; wheelVersion?: string; error?: string; bootMs?: number }
  | { id: number; type: string; ok: false; error: string }
  | ({ id: number; type: string; ok: true } & Record<string, unknown>);

/** Payload envelopes are JSON strings crossing the worker boundary. */
export interface EnvelopePayload {
  envelope: string; // JSON-serialized capability envelope (schema: 1)
}
