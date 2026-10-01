import { useEffect, useMemo, useState } from "react";
import type {
  LibraryText,
  MeasureMappingEntry,
  MeasureResult,
  ParseResult,
} from "../lib/protocol";
import { POPULATION_ORDER } from "../lib/protocol";
import type { LibraryClosure } from "../lib/libraryGraph";
import { workerRequest } from "./BootOverlay";

/**
 * MeasurePane — FHIR-native population mapping editor (INV-3 authority).
 *
 * Edits Measure.group.population: code (measure-population system) +
 * criteria.expression (define name picked from the parsed defines).
 * The pane never guesses roles: "Suggest mapping" offers a default the
 * user confirms; changes propagate via onChange as the Measure dict.
 */

interface PopulationRow {
  define: string;
  code: string;
}

interface Props {
  libraries: LibraryText[];
  main: LibraryText;
  measure: Record<string, unknown> | null;
  onChange: (measure: Record<string, unknown> | null) => void;
  /* 6f: primary-library association + surfaced dependency closure. */
  mainLibraryId?: string;
  libraryChoices?: Array<{ id: string; name: string }>;
  onMainLibraryChange?: (id: string) => void;
  closure?: LibraryClosure;
  valuesetSources?: Record<string, "workspace" | "dataset">;
  /* 6f: expected-results association. 6h: the full authored reports so
   * the pane can render the per-patient ✓/✗ tally strip. */
  expectedReports?: Array<Record<string, unknown>>;
  onOpenExpected?: () => void;
}

export function MeasurePane({
  libraries,
  main,
  measure,
  onChange,
  mainLibraryId,
  libraryChoices,
  onMainLibraryChange,
  closure,
  valuesetSources,
  expectedReports,
  onOpenExpected,
}: Props) {
  const [parse, setParse] = useState<ParseResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [statusNote, setStatusNote] = useState<string | null>(null);
  // Draft rows: editable state including incomplete rows the Measure
  // itself cannot represent (empty code/define are dropped by emit()).
  // The measure is the authority; drafts only ADD in-progress rows.
  const [draft, setDraft] = useState<PopulationRow[]>([]);
  const [draftSeq, setDraftSeq] = useState(0);

  const definitions = useMemo(
    () => parse?.definition_names ?? [],
    [parse],
  );

  useEffect(() => {
    let cancelled = false;
    workerRequest({ type: "parse_cql", text: main.text })
      .then((resp) => {
        if (cancelled) return;
        const env: ParseResult = JSON.parse(
          (resp as { envelope: string }).envelope,
        );
        setParse(env);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [main.text]);

  const measureRows: PopulationRow[] = useMemo(() => {
    const groups = (measure?.group as Array<Record<string, unknown>> | undefined) ?? [];
    const out: PopulationRow[] = [];
    for (const g of groups) {
      for (const pop of (g.population as Array<Record<string, unknown>>) ?? []) {
        const coding =
          (
            (pop.code as Record<string, unknown> | undefined)?.coding as
              Array<Record<string, unknown>>
          )?.[0] ?? {};
        const criteria = pop.criteria as Record<string, unknown> | undefined;
        out.push({
          code: String(coding.code ?? ""),
          define: String(criteria?.expression ?? ""),
        });
      }
    }
    return out;
  }, [measure]);

  const rows: PopulationRow[] = useMemo(
    () => [...measureRows, ...draft],
    [measureRows, draft],
  );

  function emit(next: PopulationRow[]) {
    setDraft([]);
    if (!next.length) {
      onChange(null);
      return;
    }
    const complete = next.filter((r) => r.define && r.code);
    if (!complete.length) {
      // Only incomplete rows remain — keep them as drafts, drop the measure.
      onChange(null);
      setDraft(next);
      return;
    }
    // Preserve the measure's IDENTITY (name/version/url/id/status) —
    // editing populations must never rename or re-version the resource
    // (imported MADiE measures keep their name through edits).
    const identity: Record<string, unknown> = {};
    for (const k of ["name", "version", "url", "id", "status", "library", "scoring"]) {
      if (measure && k in (measure as Record<string, unknown>)) {
        identity[k] = (measure as Record<string, unknown>)[k];
      }
    }
    if (!("name" in identity)) identity.name = "CleanroomMeasure";
    if (!("status" in identity)) identity.status = "draft";
    const measureOut: Record<string, unknown> = {
      resourceType: "Measure",
      ...identity,
      group: [
        {
          id: groupId(),
          extension: [
            {
              url: "http://hl7.org/fhir/us/cqf-measures/StructureDefinition/cqfm-populationBasis",
              valueCode: "boolean",
            },
          ],
          population: complete
            .map((r) => ({
              code: {
                coding: [
                  {
                    system:
                      "http://terminology.hl7.org/CodeSystem/measure-population",
                    code: r.code,
                  },
                ],
              },
              criteria: {
                language: "text/cql-identifier",
                expression: r.define,
              },
            })),
        },
      ],
    };
    // Preserve any trailing incomplete rows as drafts for continued editing.
    const incomplete = next.filter((r) => !(r.define && r.code));
    if (incomplete.length) setDraft(incomplete);
    onChange(measureOut);
  }

  function groupId(): string {
    const groups = (measure?.group as Array<Record<string, unknown>>) ?? [];
    const gid = groups[0]?.id;
    return typeof gid === "string" && gid ? gid : "group-1";
  }

  function update(i: number, patch: Partial<PopulationRow>) {
    emit(rows.map((r, idx) => (idx === i ? { ...r, ...patch } : r)));
  }

  function remove(i: number) {
    emit(rows.filter((_, idx) => idx !== i));
  }

  function add() {
    // A new empty row lives as a draft (visible, editable) until both
    // code and define are chosen; emit() then persists it to the Measure.
    setDraft([...draft, { define: "", code: "" }]);
    setDraftSeq(draftSeq + 1);
  }

  async function suggest() {
    setBusy(true);
    setError(null);
    try {
      // Capability-side suggestion is explicit-user-confirmed only: we
      // propose a name-based default HERE (UI), the user applies it.
      const lower = (n: string) => n.toLowerCase();
      const proposed: PopulationRow[] = [];
      const used = new Set<string>();
      for (const code of POPULATION_ORDER.slice(0, 6)) {
        const label = code.replace(/-/g, " ");
        const match = definitions.find(
          (d) =>
            !proposed.some((p) => p.define === d) &&
            (lower(d) === label ||
              lower(d).includes(label) ||
              label.includes(lower(d))),
        );
        if (match && !used.has(code)) {
          proposed.push({ define: match, code });
          used.add(code);
        }
      }
      emit(proposed);
      setStatusNote(
        proposed.length
          ? `Suggested ${proposed.length} mapping(s) — review and adjust.`
          : "No obvious define matches found — map manually.",
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function applyViaCapability() {
    setBusy(true);
    setError(null);
    setStatusNote(null);
    try {
      const mapping: MeasureMappingEntry[] = rows
        .filter((r) => r.define && r.code)
        .map((r) => ({ define: r.define, code: r.code }));
      const resp = await workerRequest({
        type: "measure_from_definitions",
        libraries,
        main,
        mapping,
        // Keep the current resource identity through validation rebuilds.
        library_urls:
          Array.isArray(
            (measure as Record<string, unknown> | null)?.library,
          )
            ? ((measure as Record<string, unknown>).library as string[])
            : null,
      });
      const env: MeasureResult = JSON.parse(
        (resp as { envelope: string }).envelope,
      );
      if (env.ok) {
        onChange(env.measure);
        setStatusNote("Measure validated and rebuilt from mapping.");
      } else {
        setError(
          env.diagnostics?.map((d) => d.message).join("; ") ?? "invalid mapping",
        );
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const usedCodes = new Set(rows.map((r) => r.code).filter(Boolean));

  /* Expected-results association (option A): presence + a jump to the
   * dedicated editor — the data itself is authored/viewed there, not
   * duplicated here. */
  const nExpected = (expectedReports ?? []).filter(
    (r) =>
      typeof (r.subject as { reference?: string } | undefined)?.reference ===
      "string",
  ).length;

  const [inputsOpen, setInputsOpen] = useState(false);

  const unsourced = (closure?.valuesetDecls ?? []).filter(
    (v) => !valuesetSources?.[v.url],
  ).length;

  return (
    <section className="pane" data-testid="measure-pane">
      {/* #64: shared editor grammar — identity left, actions right (the
          mapping buttons live here, matching valueset/expected). */}
      <header className="pane-header">
        <div className="editor-identity">
          <span className="editor-name" data-testid="measure-name">
            {String(
              (measure?.name as string | undefined) ?? "unnamed measure",
            )}
          </span>
          <span className="type-badge">Measure</span>
        </div>
        <div className="pane-actions">
          {libraryChoices && onMainLibraryChange && (
            <select
              data-testid="measure-main-library"
              value={mainLibraryId ?? ""}
              onChange={(e) => onMainLibraryChange(e.target.value)}
              title="Primary library — brings in its dependent libraries and valuesets"
            >
              {libraryChoices.map((l) => (
                <option key={l.id} value={l.id}>
                  {l.name}
                </option>
              ))}
            </select>
          )}
          <button onClick={add} data-testid="measure-add-row">
            + population
          </button>
          <button onClick={suggest} disabled={busy} data-testid="measure-suggest">
            Suggest
          </button>
          <button
            onClick={applyViaCapability}
            disabled={busy}
            data-testid="measure-validate"
          >
            Validate
          </button>
        </div>
      </header>
      {error && (
        <div className="pane-error" data-testid="measure-error">
          {error}
        </div>
      )}
      {statusNote && (
        <div className="status-note" data-testid="measure-status">
          {statusNote}
        </div>
      )}
      {closure &&
       (closure.libraryNames.length > 0 || closure.valuesetDecls.length > 0) && (
        <section className="measure-inputs" data-testid="measure-inputs">
          <button
            className="inputs-toggle"
            data-testid="measure-inputs-toggle"
            aria-expanded={inputsOpen}
            onClick={() => setInputsOpen(!inputsOpen)}
          >
            <span className="inputs-caret" aria-hidden>
              {inputsOpen ? "▾" : "▸"}
            </span>
            <span className="assoc-label">Inputs</span>
            <span className="pane-meta">
              {closure.libraryNames.length}{" "}
              {closure.libraryNames.length === 1 ? "library" : "libraries"} ·{" "}
              {closure.valuesetDecls.length}{" "}
              {closure.valuesetDecls.length === 1 ? "valueset" : "valuesets"}
              {unsourced > 0 ? ` · ${unsourced} unsourced` : ""}
            </span>
          </button>
          {inputsOpen && (
            <table className="inputs-table">
              <thead>
                <tr>
                  <th>Kind</th>
                  <th>Name</th>
                  <th>Source</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {closure.libraryNames.map((n, i) => (
                  <tr key={`lib-${n}`} data-testid={`inputs-library-${i}`}>
                    <td>library</td>
                    <td>{n}</td>
                    <td>workspace</td>
                    <td>{n === main.name ? "primary" : ""}</td>
                  </tr>
                ))}
                {closure.valuesetDecls.map((v) => {
                  const src = valuesetSources?.[v.url];
                  return (
                    <tr key={v.url} title={v.url}>
                      <td>valueset</td>
                      <td>{v.name}</td>
                      <td>{src ?? "—"}</td>
                      <td>{src ? "" : <span className="warn">⚠ unsourced</span>}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </section>
      )}
      <div className="mapping-head">
        <span className="assoc-label">Population mapping</span>
      </div>
      {rows.length === 0 ? (
        <p className="pane-hint" data-testid="measure-empty">
          No Measure mapping — evaluation uses raw define columns. Add a
          population or press Suggest to bootstrap from define names.
        </p>
      ) : (
        <table className="mapping-table" data-testid="measure-table">
          <thead>
            <tr>
              <th>Population code</th>
              <th>CQL define</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i} data-testid={`measure-row-${i}`}>
                <td>
                  <select
                    value={r.code}
                    onChange={(e) => update(i, { code: e.target.value })}
                    data-testid={`measure-code-${i}`}
                  >
                    <option value="">— code —</option>
                    {POPULATION_ORDER.map((code) => (
                      <option
                        key={code}
                        value={code}
                        disabled={usedCodes.has(code) && code !== r.code}
                      >
                        {code}
                      </option>
                    ))}
                  </select>
                </td>
                <td>
                  <select
                    value={r.define}
                    onChange={(e) => update(i, { define: e.target.value })}
                    data-testid={`measure-define-${i}`}
                  >
                    <option value="">— define —</option>
                    {definitions.map((d) => (
                      <option key={d} value={d}>
                        {d}
                      </option>
                    ))}
                  </select>
                </td>
                <td>
                  <button
                    className="row-remove"
                    onClick={() => remove(i)}
                    aria-label={`remove row ${i}`}
                    data-testid={`measure-remove-${i}`}
                  >
                    ×
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {onOpenExpected && (
        <div className="measure-expected" data-testid="measure-expected">
          <span className="assoc-label">Expected</span>
          <span className="pane-meta" data-testid="expected-status">
            {nExpected > 0
              ? `${nExpected} patient${nExpected === 1 ? "" : "s"}`
              : "not authored"}
          </span>
          <button
            className="pane-action"
            onClick={onOpenExpected}
            data-testid="measure-open-expected"
            title="Open the expected-results editor"
          >
            open editor ↗
          </button>
        </div>
      )}
    </section>
  );
}
