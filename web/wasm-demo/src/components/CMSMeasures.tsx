import { useState, useCallback, useEffect, useMemo } from "react";
import { useCMSDuckDB, type MeasureRunResult } from "../hooks/useCMSDuckDB";
import { isAuditCell, generateNarrative, type AuditCell } from "../lib/narrative";
import { EvidenceModal } from "./EvidenceModal";
import { PatientDataViewer } from "./PatientDataViewer";
import { WorkspaceLayout, type PaneConfig } from "./WorkspaceLayout";
import { BrandedHeader } from "./BrandedHeader";
import { StatusDot } from "./StatusDot";
import { getAssetBase } from "../lib/asset-base";

interface MeasureOption {
  id: string;
  label: string;
  description: string;
  populations: string[];
}

interface MeasureManifest {
  measures: Record<string, {
    title: string;
    populations: string[];
  }>;
}

const MEASURE_DESCRIPTIONS: Record<string, string> = {
  CMS124: "Women 21-64 who were screened for cervical cancer using either cytology or hrHPV testing.",
  CMS159: "Patients 12+ with a diagnosis of depression whose PHQ-9 score was <5 at twelve months.",
  CMS349: "Patients 15-65 who were screened for HIV infection using a FDA-approved test.",
};

const DEFAULT_MEASURES: MeasureOption[] = [
  {
    id: "CMS124",
    label: "CMS124 - Cervical Cancer Screening",
    description: MEASURE_DESCRIPTIONS.CMS124,
    populations: ["Initial Population", "Denominator", "Denominator Exclusions", "Numerator"],
  },
  {
    id: "CMS159",
    label: "CMS159 - Depression Remission at Twelve Months",
    description: MEASURE_DESCRIPTIONS.CMS159,
    populations: ["Initial Population", "Denominator", "Denominator Exclusions", "Numerator"],
  },
  {
    id: "CMS349",
    label: "CMS349 - HIV Screening",
    description: MEASURE_DESCRIPTIONS.CMS349,
    populations: ["Initial Population", "Denominator", "Denominator Exclusions", "Numerator"],
  },
];

const YEAR = 2026;

export function CMSMeasures({
  executeQuery,
  duckdbReady,
  paneVisibility,
  onTogglePane,
  selectedPatientId,
  onPatientSelect,
  connectionStatus,
  wasmAppUrl,
}: {
  executeQuery: (sql: string) => Promise<any>;
  duckdbReady: boolean;
  paneVisibility: Record<string, boolean>;
  onTogglePane: (id: string) => void;
  selectedPatientId?: string | null;
  onPatientSelect?: (id: string) => void;
  connectionStatus?: {
    patientName?: string;
    vendor?: string;
    onLogout?: () => void;
  } | null;
  wasmAppUrl?: string;
}) {
  const [measures, setMeasures] = useState<MeasureOption[]>(DEFAULT_MEASURES);
  const [selectedMeasureId, setSelectedSample] = useState(DEFAULT_MEASURES[0].id);
  const selectedMeasure = useMemo(
    () => measures.find((m) => m.id === selectedMeasureId) ?? measures[0],
    [measures, selectedMeasureId],
  );

  useEffect(() => {
    let cancelled = false;
    async function loadManifest() {
      try {
        const resp = await fetch(`${getAssetBase(wasmAppUrl)}/data/manifest.json`);
        if (!resp.ok) return;
        const manifest = await resp.json() as MeasureManifest;
        const next = Object.entries(manifest.measures)
          .map(([id, measure]) => ({
            id,
            label: `${id} - ${measure.title}`,
            description: MEASURE_DESCRIPTIONS[id] ?? measure.title,
            populations: measure.populations,
          }))
          .sort((a, b) => a.id.localeCompare(b.id, undefined, { numeric: true }));
        if (!cancelled && next.length > 0) {
          setMeasures(next);
          setSelectedSample((current) => next.some((m) => m.id === current) ? current : next[0].id);
        }
      } catch {
        // Keep built-in measure metadata if the manifest is unavailable.
      }
    }
    loadManifest();
    return () => {
      cancelled = true;
    };
  }, [wasmAppUrl]);

  const {
    executeMeasure,
    executeQuery: executeCMSQuery,
    error,
    loadingMessage,
    ready,
  } = useCMSDuckDB(wasmAppUrl);
  const [runResult, setRunResult] = useState<MeasureRunResult | null>(null);
  const [executing, setExecuting] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  const [modalCell, setModalCell] = useState<{ cell: AuditCell; columnName: string } | null>(null);

  const handleRun = useCallback(async () => {
    setExecuting(true);
    setRunError(null);
    try {
      const res = await executeMeasure(selectedMeasureId, YEAR, true);
      setRunResult(res);
    } catch (e) {
      console.error(e);
      setRunError(e instanceof Error ? e.message : String(e));
    } finally {
      setExecuting(false);
    }
  }, [executeMeasure, selectedMeasureId]);

  const handleRowClick = (row: unknown[]) => {
    if (row.length > 0 && onPatientSelect) {
      onPatientSelect(String(row[0]));
    }
  };

  const isLoading = executing || (!ready && !error);

  return (
    <div className="cms-measures-ui">
      <BrandedHeader connectionStatus={connectionStatus}>
        <select
          className="sample-select"
          value={selectedMeasureId}
          onChange={(e) => {
            setSelectedSample(e.target.value);
            setRunResult(null); // Clear stale results when measure changes
          }}
        >
          {measures.map((m) => (
            <option key={m.id} value={m.id}>
              {m.label}
            </option>
          ))}
        </select>
        <button
          className="btn btn-primary"
          onClick={handleRun}
          disabled={isLoading}
        >
          {isLoading ? "Executing…" : "▶ Run"}
        </button>

        <div className="header-status">
          {runResult?.accuracy && <AccuracyBadge accuracy={runResult.accuracy} />}
          <StatusDot ready={ready} label="DuckDB" />
        </div>
      </BrandedHeader>

      <WorkspaceLayout
        panes={[
          {
            id: "cms-info",
            label: "Measure Definition",
            icon: "ℹ️",
            content: (
              <div style={{ padding: 20 }}>
                <h3 style={{ marginBottom: 12 }}>{selectedMeasure.label}</h3>
                <p style={{ color: "var(--color-text-muted)", lineHeight: 1.6 }}>
                  {selectedMeasure.description}
                </p>
                <div style={{ marginTop: 24 }}>
                  <h4 style={{ fontSize: 11, textTransform: "uppercase", color: "var(--color-text-muted)", marginBottom: 8 }}>Populations</h4>
                  <ul style={{ listStyle: "none" }}>
                    {selectedMeasure.populations.map(p => (
                      <li key={p} style={{ fontSize: 13, marginBottom: 4 }}>• {p}</li>
                    ))}
                  </ul>
                </div>
              </div>
            ),
            badge: "read-only",
            badgeType: "readonly",
          },
          {
            id: "cms-stats",
            label: "Population Stats",
            icon: "📊",
            content: (
              <div className="cms-summary">
                {selectedMeasure.populations.map((pop) => {
                  const count = runResult?.results.filter((r) =>
                    popResult(r.populations[pop])
                  ).length ?? 0;
                  return (
                    <div key={pop} className="stat-card">
                      <span className="stat-label">{pop}</span>
                      <span className="stat-value">{isLoading ? "…" : count}</span>
                    </div>
                  );
                })}
              </div>
            ),
            badge: "calculated",
            badgeType: "calculated",
          },
          {
            id: "patient-data",
            label: "Patient Data",
            icon: "🧑",
            content: (
              <PatientDataViewer
                executeQuery={executeCMSQuery}
                duckdbReady={ready}
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
        footer={
          <div className="results-pane cms-results">
            <div className="pane-header">
              <span className="pane-title">Patient Results</span>
              {runResult && (
                <span className="pane-meta">
                  {runResult.rowCount} patients in {runResult.executionTimeMs.toFixed(1)}ms
                </span>
              )}
            </div>
            <div className="results-body" style={{ flex: 1, overflow: 'auto' }}>
              {(error || runError) && <div className="results-error">{error || runError}</div>}
              {!error && !runError && !runResult && !executing && (
                <div className="results-message">{loadingMessage || "Run the measure to see patient results."}</div>
              )}
              {runResult && (
                <div className="table-wrapper">
                  <table className="results-table">
                    <thead>
                      <tr>
                        <th>Patient ID</th>
                        {selectedMeasure.populations.map((pop) => (
                          <th key={pop}>{pop}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {runResult.results.map((r, ri) => (
                        <tr key={ri} 
                            onClick={() => handleRowClick([r.patientId])}
                            className="clickable-row"
                            style={{ background: selectedPatientId === r.patientId ? "rgba(56, 189, 248, 0.1)" : undefined }}>
                          <td>{r.patientId}</td>
                          {selectedMeasure.populations.map((pop, pi) => (
                            <td key={pi}>
                              {renderCell(r.populations[pop], pop, setModalCell)}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        }
      />

      {modalCell && (
        <EvidenceModal
          cell={modalCell.cell}
          columnName={modalCell.columnName}
          onClose={() => setModalCell(null)}
        />
      )}
    </div>
  );
}

function popResult(val: boolean | AuditCell | undefined | null): boolean {
  if (val === undefined || val === null) return false;
  if (typeof val === "boolean") return val;
  if (isAuditCell(val)) return val.result;
  return Boolean(val);
}

function renderCell(
  value: unknown,
  columnName: string,
  onAuditClick: (info: { cell: AuditCell; columnName: string }) => void,
): React.ReactNode {
  if (value === null || value === undefined) return <span className="cell-null">✗</span>;
  if (isAuditCell(value)) {
    return (
      <AuditBadge
        cell={value}
        columnName={columnName}
        onClick={() => onAuditClick({ cell: value, columnName })}
      />
    );
  }
  return <BoolBadge value={Boolean(value)} />;
}

function BoolBadge({ value }: { value: boolean }) {
  return (
    <span className={`cell-bool ${value ? "cell-bool--true" : "cell-bool--false"}`}>
      {value ? "✓" : "✗"}
    </span>
  );
}

function AuditBadge({
  cell,
  columnName,
  onClick,
}: {
  cell: AuditCell;
  columnName: string;
  onClick: () => void;
}) {
  const narrative = generateNarrative(columnName, cell.evidence ?? [], cell.result);
  return (
    <span className="audit-cell" title={narrative.join("\n")} onClick={(e) => { e.stopPropagation(); onClick(); }}>
      <span className={`cell-bool ${cell.result ? "cell-bool--true" : "cell-bool--false"}`}>
        {cell.result ? "✓" : "✗"}
      </span>
      <span className="audit-icon">🔍</span>
    </span>
  );
}

function AccuracyBadge({ accuracy }: { accuracy: MeasureRunResult["accuracy"] }) {
  if (!accuracy) return null;
  const color = accuracy.pct >= 90 ? "#14532d" : accuracy.pct >= 70 ? "#78350f" : "#7f1d1d";
  const bg = accuracy.pct >= 90 ? "#dcfce7" : accuracy.pct >= 70 ? "#fef3c7" : "#fee2e2";
  return (
    <span
      style={{
        display: "inline-block",
        padding: "3px 10px",
        borderRadius: 4,
        fontSize: 12,
        fontWeight: 600,
        background: bg,
        color,
      }}
    >
      {accuracy.pct.toFixed(1)}% accuracy
    </span>
  );
}
