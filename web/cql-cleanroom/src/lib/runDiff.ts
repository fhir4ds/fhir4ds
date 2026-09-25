/**
 * Client-side run-diff for output-table change highlighting.
 *
 * Compares the current evaluation's rows-shaped artifact against a
 * baseline artifact (prior run). Both share the operations rows shape
 * {patient_id: {population: bool|null}} — the same semantic compare_evidence
 * computes server-side, done locally here so tables can highlight per
 * cell without a worker round-trip.
 */

export interface DiffCell {
  /** previous value (null = absent/unknown) */
  from: boolean | null;
  /** current value */
  to: boolean | null;
}

export interface RunDiff {
  /** changed cells keyed `${patientId}\u0000${population}` */
  cells: Map<string, DiffCell>;
  /** patients in baseline but absent now */
  removedPatients: string[];
  /** patients present now but absent from baseline */
  addedPatients: string[];
  /** total populations compared (union of columns) */
  populationCount: number;
}

export type Artifact = Record<string, Record<string, boolean | null>>;

function cellsOf(artifact: Artifact): Map<string, Set<string>> {
  const out = new Map<string, Set<string>>();
  for (const [pid, pops] of Object.entries(artifact)) {
    out.set(pid, new Set(Object.keys(pops ?? {})));
  }
  return out;
}

export function diffRuns(
  current: Artifact | null,
  baseline: Artifact | null,
): RunDiff | null {
  if (!current || !baseline) return null;
  const cells = new Map<string, DiffCell>();
  const curCells = cellsOf(current);
  const baseCells = cellsOf(baseline);
  const removedPatients: string[] = [];
  const addedPatients: string[] = [];
  const populations = new Set<string>();
  for (const pops of [...Object.values(current), ...Object.values(baseline)]) {
    for (const p of Object.keys(pops ?? {})) populations.add(p);
  }

  for (const pid of new Set([...curCells.keys(), ...baseCells.keys()])) {
    const inCur = curCells.has(pid);
    const inBase = baseCells.has(pid);
    if (inBase && !inCur) {
      removedPatients.push(pid);
      continue;
    }
    if (inCur && !inBase) {
      addedPatients.push(pid);
      // still mark all cells as added via from:null below
    }
    const curPops = current[pid] ?? {};
    const basePops = baseline[pid] ?? {};
    for (const pop of populations) {
      const curVal = curPops[pop] ?? null;
      const baseVal = basePops[pop] ?? null;
      if (curVal !== baseVal) {
        cells.set(`${pid}\u0000${pop}`, { from: baseVal, to: curVal });
      }
    }
  }
  return {
    cells,
    removedPatients: removedPatients.sort(),
    addedPatients: addedPatients.sort(),
    populationCount: populations.size,
  };
}

/** CSS class for a changed cell (null when unchanged). */
export function cellDiffClass(
  diff: RunDiff | null,
  patientId: string,
  population: string,
): string | null {
  const cell = diff?.cells.get(`${patientId}\u0000${population}`);
  if (!cell) return null;
  const toTrue = cell.to === true;
  const fromNull = cell.from === null;
  if (fromNull) return toTrue ? "diff-added-cell" : "diff-added-cell";
  if (cell.to === null) return "diff-null-cell";
  return toTrue ? "diff-up-cell" : "diff-down-cell";
}

/** Summary chips for the footer. */
export function diffSummary(diff: RunDiff | null): {
  changed: number;
  added: number;
  removed: number;
} {
  if (!diff) return { changed: 0, added: 0, removed: 0 };
  let up = 0;
  let down = 0;
  for (const c of diff.cells.values()) {
    if (c.from === null) continue;
    if (c.to === true) up += 1;
    else down += 1;
  }
  return {
    changed: up + down,
    added: diff.addedPatients.length,
    removed: diff.removedPatients.length,
  };
}
