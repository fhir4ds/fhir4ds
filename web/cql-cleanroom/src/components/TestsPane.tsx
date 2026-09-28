import { useEffect, useMemo } from "react";
import { DropdownMenu } from "./DropdownMenu";

/**
 * TestsPane v5 — the authored MeasureReport editor (REORG 6c).
 *
 * Expected results are AUTHORED, not a mirror of the dataset: the grid
 * lists only the patients added to the active measure's expected
 * MeasureReports (one individual MR per patient, count 1|0 per code).
 * Header grammar matches the other editors (identity left, actions
 * right): "+ Add patient" curates subjects; the Default ▾ bulk-authors
 * (All true / All false) or seeds from the LATEST RUN ("Current
 * result" — the console's old Capture-as-expected, which lived in the
 * wrong place). MeasureReport .json import lives in the nav Expected
 * section's ▾ menu (#64); the compare vs. actual renders in the
 * console's Compare tab, derived from the latest library run (6h #62).
 */

interface ExpectedMap {
  [patientId: string]: { [populationCode: string]: boolean };
}

export function TestsPane({
  dataset,
  populationCodes,
  expectedValues,
  onExpectedValuesChange,
  measure,
  onUseCurrentResult,
  hasCurrentResult,
}: {
  dataset: { resources?: Record<string, unknown>[] } | null;
  populationCodes: string[];
  expectedValues: ExpectedMap | null;
  onExpectedValuesChange: (v: ExpectedMap | null) => void;
  measure: Record<string, unknown> | null;
  /** Default ▾ > Current result — seed expectations from the latest
   *  library run's populations (App's captureExpectedFromRun). */
  onUseCurrentResult?: () => void;
  /** False until a run produced populations (disables the item). */
  hasCurrentResult?: boolean;
}) {
  const patients = useMemo(() => {
    const ids = new Set<string>();
    for (const r of dataset?.resources ?? []) {
      if (r?.resourceType === "Patient" && typeof r.id === "string") {
        ids.add(r.id);
      }
    }
    return [...ids].sort();
  }, [dataset]);

  const expected: ExpectedMap = expectedValues ?? {};

  // Authored subjects: the grid lists exactly these patients, sorted.
  const addedPatients = useMemo(
    () => Object.keys(expected).sort(),
    [expectedValues],
  );
  const addablePatients = useMemo(
    () => patients.filter((pid) => !(pid in expected)),
    [patients, expectedValues],
  );

  function addPatient(pid: string) {
    if (!pid || pid in expected) return;
    const row: { [code: string]: boolean } = {};
    for (const code of populationCodes) row[code] = false;
    onExpectedValuesChange({ ...expected, [pid]: row });
  }

  function removePatient(pid: string) {
    const next: ExpectedMap = {};
    for (const [p, codes] of Object.entries(expected)) {
      if (p !== pid) next[p] = codes;
    }
    onExpectedValuesChange(Object.keys(next).length ? next : null);
  }

  useEffect(() => {
    // Keep the grid consistent with the current population codes.
    const codes = new Set(populationCodes);
    let changed = false;
    const next: ExpectedMap = {};
    for (const [pid, codes2] of Object.entries(expected)) {
      const filtered: { [code: string]: boolean } = {};
      for (const [code, v] of Object.entries(codes2)) {
        if (codes.has(code)) {
          filtered[code] = v;
        } else {
          changed = true;
        }
      }
      next[pid] = filtered;
    }
    if (changed && expectedValues) {
      onExpectedValuesChange(next);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [populationCodes.join(",")]);

  function setExpected(pid: string, code: string, value: boolean) {
    const next: ExpectedMap = {
      ...expected,
      [pid]: { ...(expected[pid] ?? {}), [code]: value },
    };
    onExpectedValuesChange(next);
  }

  function setAll(value: boolean) {
    const next: ExpectedMap = {};
    for (const pid of patients) {
      const row: { [code: string]: boolean } = {};
      for (const code of populationCodes) row[code] = value;
      next[pid] = row;
    }
    onExpectedValuesChange(next);
  }

  const measureAvailable = populationCodes.length > 0 && !!measure;

  return (
    <section className="pane" data-testid="tests-pane">
      <header className="pane-header">
        <div className="editor-identity">
          <span className="editor-name">Expected Results</span>
          <span className="type-badge" data-testid="expected-patient-count">
            {addedPatients.length} patient{addedPatients.length === 1 ? "" : "s"}
          </span>
        </div>
        <div className="pane-actions">
          <select
            data-testid="expected-add-patient"
            value=""
            disabled={!measureAvailable || addablePatients.length === 0}
            onChange={(e) => {
              addPatient(e.target.value);
              e.target.value = "";
            }}
            title="Add a dataset patient to the expected MeasureReport"
          >
            <option value="">+ Add patient…</option>
            {addablePatients.map((pid) => (
              <option key={pid} value={pid}>
                {pid}
              </option>
            ))}
          </select>
          <DropdownMenu label="Default" testId="expected-default">
            <button
              className="dropdown-item"
              data-testid="expected-default-all-true"
              disabled={!patients.length || !measureAvailable}
              onClick={() => setAll(true)}
              title="Author every dataset patient, all populations true"
            >
              All true
            </button>
            <button
              className="dropdown-item"
              data-testid="expected-default-all-false"
              disabled={!patients.length || !measureAvailable}
              onClick={() => setAll(false)}
              title="Author every dataset patient, all populations false"
            >
              All false
            </button>
            <button
              className="dropdown-item"
              data-testid="expected-default-current-result"
              disabled={!onUseCurrentResult || !hasCurrentResult}
              onClick={() => onUseCurrentResult?.()}
              title="Seed expectations from the latest run's populations"
            >
              Current result
            </button>
          </DropdownMenu>
        </div>
      </header>
      {!measureAvailable ? (
        <p className="pane-hint" data-testid="tests-no-measure">
          Define a Measure mapping first — expected values attach to
          population codes.
        </p>
      ) : (
        <div className="expected-grid-wrap">
        <table className="expected-grid" data-testid="expected-grid">
          <thead>
            <tr>
              <th>Patient</th>
              {populationCodes.map((c) => (
                <th key={c}>{c}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {addedPatients.map((pid) => (
              <tr key={pid} data-testid={`expected-row-${pid}`}>
                <td>
                  {pid}
                  <button
                    className="row-remove"
                    title="Remove this patient from the expected MeasureReport"
                    aria-label={`Remove ${pid}`}
                    onClick={() => removePatient(pid)}
                    data-testid={`expected-remove-${pid}`}
                  >
                    ×
                  </button>
                </td>
                {populationCodes.map((c) => {
                  const value = expected[pid]?.[c];
                  return (
                    <td key={c}>
                      <input
                        type="checkbox"
                        checked={value === true}
                        onChange={(e) => setExpected(pid, c, e.target.checked)}
                        data-testid={`expected-${pid}-${c}`}
                      />
                    </td>
                  );
                })}
              </tr>
            ))}
            {addedPatients.length === 0 && (
              <tr>
                <td colSpan={populationCodes.length + 1}>
                  <span className="pane-hint">
                    No patients in the expected report — add them above.
                  </span>
                </td>
              </tr>
            )}
          </tbody>
        </table>
        </div>
      )}
    </section>
  );
}
