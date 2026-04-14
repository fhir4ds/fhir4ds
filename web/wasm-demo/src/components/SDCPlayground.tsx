/**
 * SDC Forms Playground: split-pane layout with JSON editor (left)
 * and live form preview (right). Supports calculatedExpression and
 * initialExpression evaluation via FHIR4DS DuckDB WASM extensions.
 */
import { useState, useCallback, useRef, useEffect } from "react";
import { QuestionnaireEditor } from "./sdc/QuestionnaireEditor";
import { FormRenderer } from "./sdc/FormRenderer";
import { SDC_SAMPLES } from "../lib/sdc-samples";
import type {
  Questionnaire,
  QuestionnaireResponse,
  QuestionnaireResponseAnswer,
} from "../lib/sdc-types";
import {
  buildEmptyResponse,
  setAnswer,
  evaluateCalculatedExpressionsAsync,
  evaluateInitialExpressionsAsync,
} from "../lib/sdc-engine";
import { SAMPLE_RESOURCES } from "../lib/sample-data";
import { WorkspaceLayout, type PaneConfig } from "./WorkspaceLayout";
import { PatientDataViewer } from "./PatientDataViewer";
import { BrandedHeader } from "./BrandedHeader";
import { StatusDot } from "./StatusDot";

const DEBOUNCE_MS = 150;

export function SDCPlayground({
  executeQuery,
  duckdbReady,
  showSampleSelector = true,
  scenario,
  paneVisibility,
  onTogglePane,
  selectedPatientId,
  onPatientSelect,
  connectionStatus,
}: {
  executeQuery: (sql: string) => Promise<any>;
  duckdbReady: boolean;
  showSampleSelector?: boolean;
  scenario?: string;
  paneVisibility: Record<string, boolean>;
  onTogglePane: (id: string) => void;
  selectedPatientId?: string | null;
  onPatientSelect?: (id: string) => void;
  connectionStatus?: {
    patientName?: string;
    vendor?: string;
    onLogout?: () => void;
  } | null;
}) {
  // Progressive disclosure: in smart-flow, only show Common Core SDC samples
  const filteredSamples = scenario === "smart-flow"
    ? SDC_SAMPLES.filter((s) => s.commonCore)
    : SDC_SAMPLES;

  const [selectedSample, setSelectedSample] = useState(filteredSamples[0].id);
  const [questionnaire, setQuestionnaire] = useState<Questionnaire>(
    filteredSamples[0].questionnaire,
  );
  const [jsonText, setJsonText] = useState(
    JSON.stringify(filteredSamples[0].questionnaire, null, 2),
  );
  const [jsonError, setJsonError] = useState<string | null>(null);
  const [response, setResponse] = useState<QuestionnaireResponse>(
    buildEmptyResponse(filteredSamples[0].questionnaire),
  );
  const [calcErrors, setCalcErrors] = useState<Record<string, string>>({});
  const [evalTimeMs, setEvalTimeMs] = useState<number | null>(null);
  const [statusMessage, setStatusMessage] = useState("Ready");
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Load patient list for the header selector
  const [patientList, setPatientList] = useState<{id: string, label: string}[]>([]);
  useEffect(() => {
    if (duckdbReady) {
      executeQuery("SELECT DISTINCT json_extract_string(resource, '$.id') as id, json_extract_string(resource, '$.name[0].family') as family FROM resources WHERE resourceType = 'Patient' ORDER BY family")
        .then(res => {
          setPatientList(res.rows.map((r: any) => ({ id: String(r[0]), label: String(r[1]) })));
        }).catch(() => {});
    }
  }, [duckdbReady, executeQuery]);

  // Recalculate all calculatedExpressions after response changes.
  // When `silent` is true, don't update the status message (used for
  // background recalculations triggered by answer changes).
  const runCalculations = useCallback(
    async (q: Questionnaire, resp: QuestionnaireResponse, silent = false) => {
      if (!duckdbReady) return;

      const start = performance.now();
      const results = await evaluateCalculatedExpressionsAsync(q, resp, executeQuery);
      const elapsed = performance.now() - start;

      let updated = resp;
      const errors: Record<string, string> = {};

      for (const { linkId, value, error } of results) {
        if (error) {
          errors[linkId] = error;
          continue;
        }
        if (value !== null && value !== undefined) {
          const answer = valueToAnswer(value, linkId, q);
          updated = setAnswer(updated, linkId, answer);
        }
      }

      setCalcErrors(errors);
      setResponse(updated);
      // Only update visible status metrics on explicit user actions, not background recalcs.
      // Silent recalculations (triggered by answer-change debounce) must not reset
      // the expression-count display the user just saw after pre-populate.
      if (!silent) {
        setEvalTimeMs(elapsed);
        setStatusMessage(
          `${results.length} expression${results.length !== 1 ? "s" : ""} evaluated in ${elapsed.toFixed(1)}ms`,
        );
      }
    },
    [duckdbReady, executeQuery],
  );

  // Handle answer changes from form inputs
  const handleAnswer = useCallback(
    (linkId: string, answer: QuestionnaireResponseAnswer | null) => {
      setResponse((prev) => {
        const next = setAnswer(prev, linkId, answer);

        // Debounce recalculation (silent — don't overwrite user-triggered status)
        if (debounceRef.current) clearTimeout(debounceRef.current);
        debounceRef.current = setTimeout(() => {
          runCalculations(questionnaire, next, true);
        }, DEBOUNCE_MS);

        return next;
      });
    },
    [questionnaire, runCalculations],
  );

  // Handle JSON editor changes
  const handleJsonChange = useCallback(
    (text: string) => {
      setJsonText(text);
      try {
        const parsed = JSON.parse(text) as Questionnaire;
        if (!parsed.resourceType || parsed.resourceType !== "Questionnaire") {
          setJsonError("JSON must have resourceType: 'Questionnaire'");
          return;
        }
        setQuestionnaire(parsed);
        setJsonError(null);
        const newResp = buildEmptyResponse(parsed);
        setResponse(newResp);
        runCalculations(parsed, newResp);
        setStatusMessage("Questionnaire updated from editor");
      } catch (e) {
        setJsonError(e instanceof Error ? e.message : "Invalid JSON");
      }
    },
    [runCalculations],
  );

  // Handle sample selection
  const handleSampleChange = useCallback(
    (sampleId: string) => {
      setSelectedSample(sampleId);
      const sample = SDC_SAMPLES.find((s) => s.id === sampleId);
      if (sample) {
        setQuestionnaire(sample.questionnaire);
        setJsonText(JSON.stringify(sample.questionnaire, null, 2));
        setJsonError(null);
        const newResp = buildEmptyResponse(sample.questionnaire);
        setResponse(newResp);
        setCalcErrors({});
        setEvalTimeMs(null);
        setStatusMessage(`Loaded: ${sample.label}`);
        // Trigger initial calculation
        setTimeout(() => runCalculations(sample.questionnaire, newResp), 50);
      }
    },
    [runCalculations],
  );

  // Pre-populate from DuckDB (real data if connected, else sample data)
  const handlePrePopulate = useCallback(async () => {
    if (!duckdbReady) {
      setStatusMessage("DuckDB not ready");
      return;
    }

    setStatusMessage("Fetching patient context...");
    let patient: Record<string, unknown> | null = null;

    try {
      // Use the globally selected patient if available
      const pid = selectedPatientId || "first";
      const sql = pid === "first" 
        ? "SELECT resource FROM resources WHERE resourceType = 'Patient' LIMIT 1"
        : `SELECT resource FROM resources WHERE resourceType = 'Patient' AND id = '${pid}' LIMIT 1`;

      const result = await executeQuery(sql);
      if (result.rows.length > 0) {
        patient = JSON.parse(result.rows[0][0] as string);
        console.log(`[SDC] Pre-populating from Patient ${patient?.id} in DuckDB`);
      }
    } catch (e) {
      console.warn("[SDC] Failed to fetch patient from DuckDB:", e);
    }

    // Fallback to static sample data
    if (!patient) {
      patient =
        (SAMPLE_RESOURCES as Record<string, unknown>[]).find(
          (r) => r.resourceType === "Patient",
        ) || null;
      if (patient) console.log("[SDC] Pre-populating from static sample patient");
    }

    if (!patient) {
      setStatusMessage("No patient data available");
      return;
    }

    const results = await evaluateInitialExpressionsAsync(
      questionnaire,
      patient,
      executeQuery,
    );
    let updated = response;
    const errors: Record<string, string> = {};

    for (const { linkId, value, error } of results) {
      if (error) {
        errors[linkId] = error;
        continue;
      }
      if (value !== null && value !== undefined) {
        const answer = valueToAnswer(value, linkId, questionnaire);
        updated = setAnswer(updated, linkId, answer);
      }
    }

    setResponse(updated);
    setCalcErrors((prev) => ({ ...prev, ...errors }));
    setStatusMessage(
      `Pre-populated ${results.filter((r) => !r.error).length} field(s) from patient data`,
    );

    // Run calculations after pre-population
    setTimeout(() => runCalculations(questionnaire, updated), 50);
  }, [duckdbReady, executeQuery, questionnaire, response, runCalculations, selectedPatientId]);

  // Initial calculation run
  useEffect(() => {
    if (duckdbReady) {
        runCalculations(questionnaire, response);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [duckdbReady]);

  return (
    <div className="sdc-playground">
      <BrandedHeader connectionStatus={connectionStatus}>
        {showSampleSelector && (
          <select
            className="sample-select"
            value={selectedSample}
            onChange={(e) => handleSampleChange(e.target.value)}
          >
            <option value="">— Select a form —</option>
            {filteredSamples.map((s) => (
              <option key={s.id} value={s.id}>
                {s.label}
              </option>
            ))}
          </select>
        )}
        <button
          className="btn btn-primary"
          onClick={handlePrePopulate}
          disabled={!duckdbReady}
          title="Fill initialExpression fields from patient data using SQL-on-FHIR"
        >
          ▶ Pre-Populate
        </button>

        <div className="header-status">
          <StatusDot ready={duckdbReady} label="DuckDB" />
        </div>
      </BrandedHeader>

      <WorkspaceLayout
        panes={[
          {
            id: "sdc-editor",
            label: "Questionnaire JSON",
            icon: "📄",
            content: (
              <QuestionnaireEditor
                value={jsonText}
                onChange={handleJsonChange}
                error={jsonError}
              />
            ),
            badge: "editable",
          },
          {
            id: "sdc-preview",
            label: "Form Preview",
            icon: "👁️",
            content: (
              <div className="sdc-form-body">
                {questionnaire.title && (
                  <h3 className="sdc-form-title">{questionnaire.title}</h3>
                )}
                <FormRenderer
                  items={questionnaire.item ?? []}
                  response={response}
                  onAnswer={handleAnswer}
                  calcErrors={calcErrors}
                />
              </div>
            ),
            badge: "live",
            badgeType: "readonly",
          },
          {
            id: "patient-data",
            label: "Patient Data",
            icon: "🧑",
            content: (
              <PatientDataViewer
                executeQuery={executeQuery}
                duckdbReady={duckdbReady}
                selectedPatientId={selectedPatientId}
                onPatientSelect={onPatientSelect}
              />
            ),
            badge: "raw fhir",
            badgeType: "readonly",
          },
        ] as [PaneConfig, PaneConfig, PaneConfig]}
        visiblePanes={paneVisibility}
        onTogglePane={onTogglePane}
      />

      {/* Status bar */}
      <div className="status-bar">
        <span className="status-message">{statusMessage}</span>
        <div className="status-metrics">
          {evalTimeMs !== null && (
            <span className="metric">
              DuckDB Eval: {evalTimeMs.toFixed(1)}ms
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

/**
 * Convert a FHIRPath evaluation result to a QuestionnaireResponseAnswer,
 * inferring the answer type from the questionnaire item definition.
 */
function valueToAnswer(
  value: unknown,
  linkId: string,
  q: Questionnaire,
): QuestionnaireResponseAnswer | null {
  const item = findItem(q.item ?? [], linkId);
  if (!item) return null;

  // Unpack Quantity object if necessary
  let cleanValue: any = value;
  if (value && typeof value === 'object' && 'value' in value) {
    cleanValue = (value as any).value;
  }

  switch (item.type) {
    case "integer":
      return { valueInteger: typeof cleanValue === "number" ? Math.round(cleanValue) : parseInt(String(cleanValue), 10) || 0 };
    case "decimal":
      return { valueDecimal: typeof cleanValue === "number" ? cleanValue : parseFloat(String(cleanValue)) || 0 };
    case "boolean":
      return { valueBoolean: Boolean(cleanValue) };
    case "date":
      return { valueDate: String(cleanValue) };
    case "choice": {
      const strVal = String(cleanValue);
      const opt = item.answerOption?.find(
        (o) => (o.valueCoding?.code === strVal) || (o.valueString === strVal),
      );
      if (opt?.valueCoding) return { valueCoding: opt.valueCoding };
      return { valueString: strVal };
    }
    case "string":
    case "text":
    default:
      return { valueString: String(value) };
  }
}

function findItem(
  items: import("../lib/sdc-types").QuestionnaireItem[],
  linkId: string,
): import("../lib/sdc-types").QuestionnaireItem | undefined {
  for (const item of items) {
    if (item.linkId === linkId) return item;
    if (item.item) {
      const found = findItem(item.item, linkId);
      if (found) return found;
    }
  }
  return undefined;
}
