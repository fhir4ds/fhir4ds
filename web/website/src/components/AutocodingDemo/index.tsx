/**
 * Interactive Auto-Coding demo — the real fhir4ds AutoCoder in the browser.
 *
 * A Pyodide worker installs the shipped fhir4ds-v2 wheel and runs
 * AutoCoder.augment_resource() against the live public terminology Space.
 * Every step shown (detection, hybrid search, grade filtering, the audit
 * extension) is the package's own logic; only the HTTP hop is bridged.
 */
import React, {useCallback, useEffect, useMemo, useRef, useState} from 'react';
import BrowserOnly from '@docusaurus/BrowserOnly';
import {JsonTree} from './JsonTree';
import './styles.css';

const DEFAULT_RESOURCE = `{
  "resourceType": "Condition",
  "id": "cond-1",
  "subject": { "reference": "Patient/demo" },
  "code": { "text": "uncontrolled type 2 diabetes" }
}`;

const PRESETS: Array<{label: string; resource: string}> = [
  {label: 'diabetes', resource: DEFAULT_RESOURCE},
  {
    label: 'heart attack',
    resource: JSON.stringify(
      {
        resourceType: 'Condition',
        id: 'cond-2',
        subject: {reference: 'Patient/demo'},
        code: {text: 'heart attack'},
      },
      null,
      2,
    ),
  },
  {
    label: 'metformin',
    resource: JSON.stringify(
      {
        resourceType: 'MedicationRequest',
        id: 'med-1',
        subject: {reference: 'Patient/demo'},
        medicationCodeableConcept: {text: 'metformin 500 mg tablet'},
      },
      null,
      2,
    ),
  },
];

type Row = {
  code?: string;
  system?: string;
  display?: string;
  score?: number;
  match_grade?: string;
};

const GRADES = ['certain', 'probable', 'possible', 'broader'];
const gradeRank = (g?: string) => {
  const i = GRADES.indexOf(g ?? '');
  return i === -1 ? GRADES.length : i;
};
const systemName = (uri?: string) => {
  if (!uri) return '';
  if (uri.includes('snomed')) return 'SNOMED CT';
  if (uri.includes('rxnorm')) return 'RxNorm';
  if (uri.includes('loinc')) return 'LOINC';
  return uri.replace(/^https?:\/\//, '');
};

function DemoInner(): JSX.Element {
  const [resourceText, setResourceText] = useState(DEFAULT_RESOURCE);
  const [minGrade, setMinGrade] = useState('probable');
  const [mode, setMode] = useState('semantic');
  const [topK, setTopK] = useState(1);
  const [engine, setEngine] = useState<'loading' | 'ready' | 'error'>('loading');
  const [initError, setInitError] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [rows, setRows] = useState<Row[] | null>(null);
  const [augmented, setAugmented] = useState<any>(null);
  const workerRef = useRef<Worker | null>(null);
  const pending = useRef<Map<number, (r: any) => void>>(new Map());

  useEffect(() => {
    const w = new Worker(
      new URL('./workers/autocoding.worker.ts', import.meta.url),
      {type: 'module'},
    );
    w.onmessage = (e: MessageEvent<any>) => {
      const resolve = pending.current.get(e.data.id);
      if (resolve) {
        pending.current.delete(e.data.id);
        resolve(e.data);
      }
    };
    workerRef.current = w;
    const call = (type: string, extra: Record<string, unknown> = {}) =>
      new Promise<any>((resolve) => {
        const id = Date.now() + Math.random();
        pending.current.set(id, resolve);
        w.postMessage({id, type, ...extra});
      });
    (w as any)._call = call;
    call('init').then((r) => {
      if (r.ok) {
        setEngine('ready');
      } else {
        console.error('[AutocodingDemo] worker init failed:', r.error);
        setEngine('error');
        setInitError(String(r.error ?? 'unknown error'));
      }
    });
    return () => w.terminate();
  }, []);

  const parsed = useMemo<{ok: boolean; resource?: any; error?: string}>(() => {
    try {
      return {ok: true, resource: JSON.parse(resourceText)};
    } catch (e) {
      return {ok: false, error: String((e as Error).message)};
    }
  }, [resourceText]);

  const run = useCallback(async () => {
    const w = workerRef.current as any;
    if (!w || engine !== 'ready') return;
    setBusy(true);
    setError('');
    setRows(null);
    setAugmented(null);
    const r = await w._call('autocode', {
      resource: resourceText,
      minGrade,
      topK,
      mode,
    });
    setBusy(false);
    if (!r.ok) {
      setError(r.error ?? 'unknown error');
      return;
    }
    setRows(JSON.parse(r.rows));
    setAugmented(JSON.parse(r.augmented));
    if (r.logs) console.log('[AutocodingDemo] engine log:\n' + r.logs);
  }, [engine, resourceText, minGrade, topK]);

  const ready = engine === 'ready';

  // Auto-run when the selected example changes (debounced for free-form edits).
  useEffect(() => {
    if (!ready || !parsed.ok) return;
    const t = setTimeout(() => {
      void run();
    }, 800);
    return () => clearTimeout(t);
  }, [ready, resourceText]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="autocoding-demo">
      <div className="adc-status">
        {engine === 'loading' && (
          <span className="adc-status-loading">
            <span className="adc-spinner" aria-hidden="true" />
            <span>
              <strong>Loading fhir4ds into your browser</strong>
              <span className="adc-status-sub">
                Pyodide + the shipped wheel (~30 MB; cached after the first visit)
              </span>
            </span>
          </span>
        )}
        {engine === 'error' && (
          <span className="adc-status-badge error">
            ⚠ engine failed to load — <code>{initError}</code>
          </span>
        )}
        {ready && (
          <span className="adc-status-badge">
            <span className="adc-status-dot" aria-hidden="true" /> fhir4ds · medterm4ds
          </span>
        )}
      </div>

      <div className="adc-step">
        <div className="adc-step-title">
          <span className="adc-num">1</span> FHIR data is messy
        </div>
        <p className="adc-narrative">
          Legacy exports routinely ship concepts with a free-text label and no{' '}
          <code>code</code>/<code>system</code> — CQL retrieves like{' '}
          <code>[Code: &lt;valueset&gt;]</code> can&apos;t match these rows at all.
          Pick a preset or try your own example below; any <code>code.text</code> works.
        </p>
        <div className="adc-presets">
          {PRESETS.map((p) => (
            <button key={p.label} className={`adc-preset ${resourceText === p.resource ? 'active' : ''}`} onClick={() => setResourceText(p.resource)}>
              {p.label}
            </button>
          ))}
        </div>
        {parsed.ok ? (
          <textarea
            className="adc-input"
            rows={9}
            spellCheck={false}
            value={resourceText}
            onChange={(e) => setResourceText(e.target.value)}
          />
        ) : null}
        {!parsed.ok && <div className="adc-error">Invalid JSON: {parsed.error}</div>}
      </div>

      <div className="adc-step">
        <div className="adc-step-title"><span className="adc-num">2</span> Search by meaning</div>
        <p className="adc-narrative">
          Embeddings let us search by <em>meaning</em>, not just words — the
          text goes to the terminology engine (semantic mode, SapBERT
          embeddings) and comes back ranked, graded, and ready to use.
          Colloquial phrases find their clinical concepts: &quot;heart attack&quot;
          resolves to <em>Myocardial infarction</em>.
        </p>
        <div className="adc-controls">
          {busy && <span className="adc-hint">searching the terminology engine…</span>}
        </div>
        {error && <div className="adc-error">{error}</div>}
        {rows && (
          <table className="adc-table">
            <thead>
              <tr><th>Kept</th><th>Code</th><th>System</th><th>Display</th><th>Score</th><th>Grade</th></tr>
            </thead>
            <tbody>
              {(() => {
                const floor = gradeRank(minGrade);
                const kept = rows
                  .filter((r) => gradeRank(r.match_grade) <= floor)
                  .sort((a, b) => (b.score ?? 0) - (a.score ?? 0))
                  .slice(0, topK);
                const keptSet = new Set(kept);
                return rows
                  .slice()
                  .sort((a, b) => (b.score ?? 0) - (a.score ?? 0))
                  .slice(0, Math.max(kept.length, 5))
                  .map((r, i) => (
                  <tr key={i} className={keptSet.has(r) ? 'adc-kept' : ''}>
                    <td>{keptSet.has(r) ? '✓' : ''}</td>
                    <td><code>{r.code}</code></td>
                    <td>{systemName(r.system)}</td>
                    <td>{r.display}</td>
                    <td>{r.score != null ? Number(r.score).toFixed(3) : ''}</td>
                    <td><span className={`badge ${(r.match_grade ?? '').split(' ')[0]}`}>{r.match_grade}</span></td>
                  </tr>
                ));
              })()}
            </tbody>
          </table>
        )}
      </div>

      <div className="adc-step">
        <div className="adc-step-title"><span className="adc-num">3</span> The augmented resource</div>
        <p className="adc-narrative">
          The AutoCoder inserts the winning concept as a proper coding — with{' '}
          <code>code</code>, <code>system</code>, and <code>display</code> — and marks it
          honestly: <code>userSelected: false</code> (a machine suggestion, not a human
          choice) plus an audit <code>extension</code> recording the engine, search mode,
          score, and match grade behind the pick.
        </p>
        {augmented ? (
          <div className="adc-tree adc-tree-lg">
            <JsonTree value={augmented} expanded collapseKey="extension" />
          </div>
        ) : (
          <div className="adc-hint">
            The full output of <code>AutoCoder.augment_resource()</code> — new Codings with the
            audit extension (engine, search mode, score, match grade) and <code>userSelected: false</code>.
          </div>
        )}
      </div>
    </div>
  );
}

export default function AutocodingDemo(): JSX.Element {
  return (
    <BrowserOnly fallback={<div className="autocoding-demo">Loading demo…</div>}>
      {() => <DemoInner />}
    </BrowserOnly>
  );
}
