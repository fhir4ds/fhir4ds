/**
 * PatientDataViewer: Inspect raw FHIR JSON for patients loaded in DuckDB.
 * - Dropdown to select a patient from the current DuckDB resources table.
 * - Syntax-highlighted JSON block showing the FHIR bundle for that patient.
 * - External selection support: a parent component can set selectedPatientId.
 */
import { useState, useEffect, useCallback, useMemo } from "react";

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
  const [filterText, setFilterText] = useState("");
  const [expanded, setExpanded] = useState(true);

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
        onPatientSelect?.(list[0].id);
      }
    } catch {
      setPatients([]);
    }
  }, [executeQuery, duckdbReady, activePatientId, onPatientSelect]);

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
  }, [selectedPatientId, activePatientId]);

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

  const filteredResources = useMemo(() => {
    const query = filterText.trim().toLowerCase();
    if (!query) return resources;
    return resources.filter((resource) => resourceSearchText(resource).includes(query));
  }, [filterText, resources]);

  const resourceGroups = useMemo(() => {
    const groups = new Map<string, any[]>();
    for (const resource of filteredResources) {
      const type = String(resource.resourceType ?? "Unknown");
      const existing = groups.get(type) ?? [];
      existing.push(resource);
      groups.set(type, existing);
    }
    return [...groups.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [filteredResources]);

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

      <div className="patient-viewer-tools">
        <input
          className="patient-viewer-filter"
          type="search"
          placeholder="Filter resources"
          value={filterText}
          onChange={(e) => setFilterText(e.target.value)}
          aria-label="Filter patient resources"
        />
        <button
          className="btn btn-secondary patient-viewer-tree-toggle"
          onClick={() => setExpanded((value) => !value)}
        >
          {expanded ? "Collapse all" : "Expand all"}
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
              {filteredResources.length} of {resources.length} resource{resources.length !== 1 ? "s" : ""}
              {" · "}
              {resourceGroups.map(([type, items]) => `${type} (${items.length})`).join(", ")}
            </div>
            <div className="patient-resource-tree">
              {resourceGroups.map(([type, items]) => (
                <details className="patient-resource-group" key={type} open={expanded}>
                  <summary>
                    <span className="patient-tree-caret" />
                    <span className="patient-resource-type">{type}</span>
                    <span className="patient-resource-count">{items.length}</span>
                  </summary>
                  <div className="patient-resource-list">
                    {items.map((resource, index) => (
                      <details
                        className="patient-resource-item"
                        key={`${resource.resourceType ?? "Unknown"}-${resource.id ?? index}`}
                        open={expanded}
                      >
                        <summary>
                          <span className="patient-tree-caret" />
                          <span className="patient-resource-title">
                            {resourceLabel(resource)}
                          </span>
                          <span className="patient-resource-meta">
                            {resourceMeta(resource)}
                          </span>
                        </summary>
                        <JsonTree value={resource} expanded={expanded} />
                      </details>
                    ))}
                  </div>
                </details>
              ))}
              {resourceGroups.length === 0 && (
                <div className="patient-viewer-empty">
                  No resources match "{filterText}".
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function resourceSearchText(resource: any): string {
  return JSON.stringify(resource).toLowerCase();
}

function resourceLabel(resource: any): string {
  const type = resource.resourceType ?? "Resource";
  const id = resource.id ? `/${resource.id}` : "";
  const code = codingDisplay(resource);
  return code ? `${type}${id} · ${code}` : `${type}${id}`;
}

function resourceMeta(resource: any): string {
  const candidates = [
    resource.effectiveDateTime,
    resource.authoredOn,
    resource.recordedDate,
    resource.onsetDateTime,
    resource.performedDateTime,
    resource.period?.start,
    resource.effectivePeriod?.start,
  ].filter(Boolean);
  return candidates.length > 0 ? String(candidates[0]) : "";
}

function codingDisplay(resource: any): string {
  const coding = resource.code?.coding?.[0] ?? resource.type?.[0]?.coding?.[0] ?? resource.category?.[0]?.coding?.[0];
  return coding?.display ?? coding?.code ?? resource.code?.text ?? "";
}

function JsonTree({
  value,
  name,
  expanded,
}: {
  value: unknown;
  name?: string;
  expanded: boolean;
}) {
  if (value === null || typeof value !== "object") {
    return (
      <div className="json-tree-row">
        {name && <span className="json-tree-key">{name}: </span>}
        <span className={`json-tree-value json-tree-${typeof value}`}>
          {formatScalar(value)}
        </span>
      </div>
    );
  }

  const entries = Array.isArray(value)
    ? value.map((item, index) => [String(index), item] as const)
    : Object.entries(value as Record<string, unknown>);
  const label = Array.isArray(value)
    ? `Array(${entries.length})`
    : `Object(${entries.length})`;

  return (
    <details className="json-tree-node" open={expanded}>
      <summary>
        <span className="patient-tree-caret" />
        {name && <span className="json-tree-key">{name}: </span>}
        <span className="json-tree-kind">{label}</span>
      </summary>
      <div className="json-tree-children">
        {entries.map(([key, child]) => (
          <JsonTree key={key} name={key} value={child} expanded={expanded} />
        ))}
      </div>
    </details>
  );
}

function formatScalar(value: unknown): string {
  if (typeof value === "string") return `"${value}"`;
  if (value === null) return "null";
  return String(value);
}
