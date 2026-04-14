/**
 * PatientDataViewer: Inspect raw FHIR JSON for patients loaded in DuckDB.
 * - Dropdown to select a patient from the current DuckDB resources table.
 * - Syntax-highlighted JSON block showing the FHIR bundle for that patient.
 * - External selection support: a parent component can set selectedPatientId.
 */
import { useState, useEffect, useCallback } from "react";

interface PatientInfo {
  id: string;
  label: string;
}

interface PatientDataViewerProps {
  executeQuery: (sql: string) => Promise<any>;
  duckdbReady: boolean;
  /** Externally selected patient ID (e.g., from CMS results table click) */
  selectedPatientId?: string | null;
  onPatientSelect?: (patientId: string) => void;
}

export function PatientDataViewer({
  executeQuery,
  duckdbReady,
  selectedPatientId,
  onPatientSelect,
}: PatientDataViewerProps) {
  const [patients, setPatients] = useState<PatientInfo[]>([]);
  const [activePatientId, setActivePatientId] = useState<string>("");
  const [resources, setResources] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Load patient list from DuckDB
  const refreshPatients = useCallback(async () => {
    if (!duckdbReady) return;
    try {
      const result = await executeQuery(
        `SELECT DISTINCT
           json_extract_string(resource, '$.id') as id,
           COALESCE(
             json_extract_string(resource, '$.name[0].family') || ', ' ||
             json_extract_string(resource, '$.name[0].given[0]'),
             json_extract_string(resource, '$.id')
           ) as label
         FROM resources
         WHERE resourceType = 'Patient'
         ORDER BY label`,
      );
      const list: PatientInfo[] = result.rows.map((row: any[]) => ({
        id: String(row[0]),
        label: String(row[1]),
      }));
      setPatients(list);
      if (list.length > 0 && !activePatientId) {
        setActivePatientId(list[0].id);
      }
    } catch {
      setPatients([]);
    }
  }, [executeQuery, duckdbReady, activePatientId]);

  useEffect(() => {
    refreshPatients();
  }, [refreshPatients]);

  // Respond to external patient selection
  useEffect(() => {
    if (selectedPatientId) {
      // Normalize: if it comes as "Patient/abc", we want "abc" for the state/dropdown matching
      const id = selectedPatientId.startsWith("Patient/") 
        ? selectedPatientId.split("/").pop()! 
        : selectedPatientId;
      
      console.log(`[PatientDataViewer] External selection normalized: ${selectedPatientId} -> ${id}`);
      if (id !== activePatientId) {
        setActivePatientId(id);
      }
    }
  }, [selectedPatientId]);

  // Load resources for the selected patient
  useEffect(() => {
    if (!duckdbReady || !activePatientId) {
      setResources([]);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);

    const sql = `SELECT resourceType, resource
       FROM resources
       WHERE patient_ref = '${activePatientId}'
          OR patient_ref = 'Patient/${activePatientId}'
       ORDER BY resourceType, json_extract_string(resource, '$.id')`;

    console.log(`[PatientDataViewer] Querying resources for: ${activePatientId}`);

    executeQuery(sql)
      .then((result) => {
        if (cancelled) return;
        const parsed = result.rows.map((row: any[]) => {
          try {
            return JSON.parse(String(row[1]));
          } catch {
            return { resourceType: row[0], _raw: row[1] };
          }
        });
        console.log(`[PatientDataViewer] Found ${parsed.length} resources`);
        setResources(parsed);
        setLoading(false);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : String(err));
        setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [activePatientId, duckdbReady, executeQuery]);

  const handleChange = useCallback(
    (patientId: string) => {
      setActivePatientId(patientId);
      onPatientSelect?.(patientId);
    },
    [onPatientSelect],
  );

  return (
    <div className="patient-viewer" data-testid="patient-data-viewer">
      <div className="patient-viewer-controls">
        <select
          className="sample-select patient-viewer-select"
          value={activePatientId}
          onChange={(e) => handleChange(e.target.value)}
          disabled={patients.length === 0}
        >
          {patients.length === 0 && <option value="">No patients loaded</option>}
          {patients.map((p) => (
            <option key={p.id} value={p.id}>
              {p.label}
            </option>
          ))}
        </select>
        <button
          className="btn btn-secondary patient-viewer-refresh"
          onClick={refreshPatients}
          title="Refresh patient list"
        >
          ↻
        </button>
      </div>

      <div className="patient-viewer-body">
        {loading && (
          <div className="patient-viewer-loading">Loading patient data…</div>
        )}
        {error && (
          <div className="patient-viewer-error">Error: {error}</div>
        )}
        {!loading && !error && resources.length === 0 && (
          <div className="patient-viewer-empty">
            {patients.length === 0
              ? "No patient data in DuckDB. Load data via SMART on FHIR or sample resources."
              : `No resources found for patient ID: ${activePatientId}. (Check patient_ref column)`}
          </div>
        )}
        {!loading && !error && resources.length > 0 && (
          <div className="patient-viewer-content">
            <div className="patient-viewer-summary">
              {resources.length} resource{resources.length !== 1 ? "s" : ""}
              {" · "}
              {[...new Set(resources.map((r) => r.resourceType))].join(", ")}
            </div>
            <pre className="patient-viewer-json">
              <code>{JSON.stringify(resources, null, 2)}</code>
            </pre>
          </div>
        )}
      </div>
    </div>
  );
}
