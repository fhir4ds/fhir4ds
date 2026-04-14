import { BrandedHeader } from "./BrandedHeader";
import { StatusDot } from "./StatusDot";

interface HeaderProps {
  selectedSample: string;
  onSampleChange: (sample: string) => void;
  samples: { id: string; label: string }[];
  onRun: () => void;
  isTranslating: boolean;
  isExecuting: boolean;
  pyodideReady: boolean;
  duckdbReady: boolean;
  showSampleSelector?: boolean;
  connectionStatus?: {
    patientName?: string;
    vendor?: string;
    onLogout?: () => void;
  } | null;
}

export function Header({
  selectedSample,
  onSampleChange,
  samples,
  onRun,
  isTranslating,
  isExecuting,
  pyodideReady,
  duckdbReady,
  showSampleSelector = true,
  connectionStatus,
}: HeaderProps) {
  return (
    <BrandedHeader connectionStatus={connectionStatus}>
      {showSampleSelector && (
        <select
          className="sample-select"
          value={selectedSample}
          onChange={(e) => onSampleChange(e.target.value)}
        >
          <option value="">— Select a sample —</option>
          {samples.map((s) => (
            <option key={s.id} value={s.id}>
              {s.label}
            </option>
          ))}
        </select>
      )}
      <button
        className="btn btn-primary"
        onClick={onRun}
        disabled={isTranslating || isExecuting || !duckdbReady || !pyodideReady}
        title={!duckdbReady ? "DuckDB is loading…" : !pyodideReady ? "Pyodide is loading…" : "Translate CQL → SQL and execute"}
      >
        {isTranslating || isExecuting ? "Running…" : "▶ Run"}
      </button>

      <div className="header-status">
        <StatusDot ready={duckdbReady} label="DuckDB" />
        <StatusDot ready={pyodideReady} label="Pyodide" />
      </div>
    </BrandedHeader>
  );
}
