/**
 * Notes → FHIR resources demo: type (or pick) a clinical note, and the live
 * medterm4ds Space runs the NER cascade (`CodeSystem/$extract`) over it.
 * Affirmed concepts become derived FHIR resources — the same output shape as
 * fhir4ds' NotesPipeline: a Coding with the autocoding audit extension
 * (engine=medterm4ds-ner) and a derived-from-text extension recording where in
 * the note each concept came from.
 *
 * The RESOURCE TYPE follows the extractor's `result_type`, so a vaccine lands
 * on an Immunization and a medication on a MedicationStatement rather than
 * everything becoming a Condition.
 */
import React, {useEffect, useMemo, useState} from 'react';
import BrowserOnly from '@docusaurus/BrowserOnly';
import {JsonTree} from './JsonTree';
import './styles.css';

const EXTRACT_URL =
  'https://fhir4ds-terminology-demo-server.hf.space/fhir/CodeSystem/$extract';

const DEFAULT_NOTE =
  'Patient is a 54-year-old male with a history of type 2 diabetes mellitus, ' +
  'hypertension, and hyperlipidemia. Presents with fatigue and polyuria. ' +
  'Assessment: uncontrolled diabetes. Plan: start metformin.';

const PRESETS: Array<{label: string; text: string}> = [
  {label: 'diabetes note', text: DEFAULT_NOTE},
  {
    label: 'cardiology note',
    text:
      '54yo male, history of myocardial infarction in 2023 and atrial ' +
      'fibrillation, on warfarin. Today reports chest pain and shortness ' +
      'of breath. Assessment: suspected acute coronary syndrome.',
  },
];

const SYSTEM_BY_SOURCE: Record<string, string> = {
  SNOMEDCT_US: 'http://snomed.info/sct',
  RXNORM: 'http://www.nlm.nih.gov/research/umls/rxnorm',
  LNC: 'http://loinc.org',
  ICD10CM: 'http://hl7.org/fhir/sid/icd-10-cm',
};

interface Concept {
  code: string;
  source: string;
  display: string;
  matched_text: string;
  status: string;
  confidence: number;
  match_grade: string;
  ner_label: string;
  result_type: string;
  span_start: number;
  span_end: number;
}

function systemName2(source: string): string {
  const map: Record<string, string> = {
    SNOMEDCT_US: 'SNOMED',
    RXNORM: 'RxNorm',
    LNC: 'LOINC',
    ICD10CM: 'ICD-10',
  };
  return map[source.toUpperCase()] ?? source;
}

// Resource type per extraction `result_type`. MIRRORS the Python source of
// truth in fhir4ds/cql/loader/derived_resources.py — keep the two in step.
// `symptom` shares Condition (FHIR has no symptom resource); `drug_class`
// shares MedicationStatement; `lab`/`vital` share Observation.
const RESOURCE_TYPE_BY_RESULT: Record<string, string> = {
  condition: 'Condition',
  symptom: 'Condition',
  medication: 'MedicationStatement',
  drug_class: 'MedicationStatement',
  vaccine: 'Immunization',
  procedure: 'Procedure',
  lab: 'Observation',
  vital: 'Observation',
};

// Element that carries the coded concept, per resource type.
const CODE_FIELD: Record<string, string> = {
  Condition: 'code',
  MedicationStatement: 'medication',
  Immunization: 'vaccineCode',
  Procedure: 'code',
  Observation: 'code',
};

// Element that references the patient (Immunization uses `patient`).
const SUBJECT_FIELD: Record<string, string> = {
  Condition: 'subject',
  MedicationStatement: 'subject',
  Immunization: 'patient',
  Procedure: 'subject',
  Observation: 'subject',
};

// Required status element for every non-Condition type (affirmed mention).
const STATUS_BY_RESOURCE: Record<string, string> = {
  MedicationStatement: 'active',
  Immunization: 'completed',
  Procedure: 'completed',
  Observation: 'final',
};

// ATC chapter J07 is "VACCINES". A vaccine mention resolved to an ATC group
// ("influenza vaccine" -> J07BB) reports result_type 'drug_class', because the
// type axis describes the ANCHOR and not the clinical category — so the code
// system gets a say here. Mirrors VACCINE_ATC_PREFIXES in the Python module.
const VACCINE_ATC_PREFIX = 'J07';

function resourceTypeFor(resultType?: string, code?: string, source?: string): string {
  const mapped =
    RESOURCE_TYPE_BY_RESULT[(resultType ?? '').trim().toLowerCase()] ?? 'Condition';
  if (
    mapped === 'MedicationStatement' &&
    source?.trim().toUpperCase() === 'ATC' &&
    code?.trim().toUpperCase().startsWith(VACCINE_ATC_PREFIX)
  ) {
    return 'Immunization';
  }
  return mapped;
}

function buildDerivedResource(concept: Concept, note: string): any {
  const system = SYSTEM_BY_SOURCE[concept.source.toUpperCase()] ?? null;
  const coding: any = {
    system,
    code: concept.code,
    display: concept.display,
    userSelected: false,
    extension: [
      {
        url: 'http://fhir4ds.org/fhir/StructureDefinition/autocoding',
        extension: [
          {url: 'engine', valueString: 'medterm4ds-ner'},
          {url: 'search-mode', valueCode: 'ner-extract'},
          {url: 'score', valueDecimal: Number(concept.confidence.toFixed(4))},
          {url: 'match-grade', valueCode: concept.match_grade},
        ],
      },
    ],
  };
  const codeable: any = {coding: [coding], text: concept.display};
  const resourceType = resourceTypeFor(concept.result_type, concept.code, concept.source);
  const resource: any = {
    resourceType,
    [CODE_FIELD[resourceType]]: codeable,
    extension: [
      {
        url: 'http://fhir4ds.org/fhir/StructureDefinition/derived-from-text',
        extension: [
          {url: 'source', valueString: 'ClinicalImpression/demo/summary'},
          {
            url: 'span',
            valueString: `[${concept.span_start},${concept.span_end})`,
          },
          {url: 'matched-text', valueString: concept.matched_text},
        ],
      },
    ],
    note: [{text: `Derived from note: "${note.slice(0, 80)}…"`}],
    [SUBJECT_FIELD[resourceType]]: {reference: 'Patient/demo'},
  };
  if (resourceType === 'Condition') {
    resource.verificationStatus = {
      coding: [
        {
          system: 'http://terminology.hl7.org/CodeSystem/condition-ver-status',
          code: 'unconfirmed',
        },
      ],
    };
  } else {
    // Every other mapped type has a REQUIRED status element.
    resource.status = STATUS_BY_RESOURCE[resourceType];
  }
  return resource;
}

function Inner(): JSX.Element {
  const [note, setNote] = useState(DEFAULT_NOTE);
  const [concepts, setConcepts] = useState<Concept[] | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  async function run(text: string): Promise<void> {
    setBusy(true);
    setError('');
    try {
      const resp = await fetch(
        `${EXTRACT_URL}?${new URLSearchParams({
          text,
          // Full assertion picture: historical/family/uncertain concepts
          // are opt-in on $extract — default is affirmed-only.
          includeFamily: 'true',
          includeHistorical: 'true',
          includeUncertain: 'true',
        })}`,
      );
      if (resp.status === 503) {
        setError('The NER engine is waking up — try again in a minute.');
        setConcepts(null);
        return;
      }
      if (resp.status === 429) {
        setError('Rate limit reached (30/min) — wait a moment and retry.');
        return;
      }
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const bundle = await resp.json();
      const rows: Concept[] = (bundle.entry ?? [])
        .map((e: any) => e.resource ?? {})
        .filter((r: any) => r.code && r.matched_text);
      setConcepts(rows);
    } catch (e) {
      setError(String((e as Error).message));
      setConcepts(null);
    } finally {
      setBusy(false);
    }
  }

  // Auto-run (debounced) on note edits.
  useEffect(() => {
    if (!note.trim()) return;
    const t = setTimeout(() => void run(note), 800);
    return () => clearTimeout(t);
  }, [note]);

  // Inline annotation view (pattern from the medterm4ds terminology-search
  // demo): the note with a <mark> at each extraction span, a concept pill
  // beside it, and a status tag tinted by assertion status.
  const annotatedNote = useMemo(() => {
    const marks = (concepts ?? [])
      .filter((c) => c.span_start != null && c.span_end != null && c.span_end > c.span_start)
      .sort((a, b) => a.span_start - b.span_start);
    if (marks.length === 0) return null;
    const parts: React.ReactNode[] = [];
    let cursor = 0;
    marks.forEach((c, i) => {
      if (c.span_start > cursor) {
        parts.push(<span key={`t${i}`}>{note.slice(cursor, c.span_start)}</span>);
      }
      const status = c.status || 'affirmed';
      parts.push(
        <span key={`m${i}`} className={`adc-term adc-term--${status}`}>
          <mark className="adc-term-mark">{note.slice(c.span_start, c.span_end)}</mark>
          <span className="adc-term-pill">
            {c.display}
            {c.source && c.code ? ` · ${systemName2(c.source)} ${c.code}` : ''}
          </span>
          <span className="adc-term-tag">{status}</span>
        </span>,
      );
      cursor = c.span_end;
    });
    if (cursor < note.length) parts.push(<span key="tail">{note.slice(cursor)}</span>);
    return <div className="adc-note-annotated">{parts}</div>;
  }, [concepts, note]);

  const derivedResources = useMemo(
    () =>
      (concepts ?? [])
        .filter((c) => c.status === 'affirmed')
        .slice(0, 6)
        .map((c) => buildDerivedResource(c, note)),
    [concepts, note],
  );

  return (
    <div className="autocoding-demo">
      <div className="adc-status">
        {busy ? (
          <span className="adc-status-loading">
            <span className="adc-spinner" aria-hidden="true" />
            <span>
              <strong>Extracting concepts</strong>
              <span className="adc-status-sub">live medterm4ds NER (CodeSystem/$extract)</span>
            </span>
          </span>
        ) : (
          <span className="adc-status-badge">
            <span className="adc-status-dot" aria-hidden="true" /> fhir4ds · medterm4ds
          </span>
        )}
        {error && (
          <span className="adc-status-badge error">⚠ {error}</span>
        )}
      </div>

      <div className="adc-step">
        <div className="adc-step-title">
          <span className="adc-num">1</span> A clinical note, as written
        </div>
        <p className="adc-narrative">
          Free text is where clinical intent actually lives. Edit the note or
          pick a preset — everything below reacts live.
        </p>
        <div className="adc-presets">
          {PRESETS.map((p) => (
            <button
              key={p.label}
              className={`adc-preset ${note === p.text ? 'active' : ''}`}
              onClick={() => setNote(p.text)}>
              {p.label}
            </button>
          ))}
        </div>
        <textarea
          className="adc-input"
          rows={6}
          spellCheck={false}
          value={note}
          onChange={(e) => setNote(e.target.value)}
        />
        {error && <div className="adc-error">{error}</div>}
      </div>

      <div className="adc-step">
        <div className="adc-step-title">
          <span className="adc-num">2</span> The note, annotated
        </div>
        <p className="adc-narrative">
          The engine reads the note by meaning and annotates what it finds —
          including the <em>assertion context</em>. Watch what it does with
          &quot;a history of&quot;: those concepts are extracted but marked
          historical (amber); only affirmed findings (green) become
          resources. Negated text is struck through, family history flagged.
        </p>
        {annotatedNote && (
          <div className="adc-note-wrap">{annotatedNote}</div>
        )}
        {!annotatedNote && !error && !busy && concepts !== null && (
          <div className="adc-hint">No concepts found in the note.</div>
        )}
      </div>

      <div className="adc-step">
        <div className="adc-step-title">
          <span className="adc-num">3</span> Derived FHIR resources
        </div>
        <p className="adc-narrative">
          Each affirmed concept becomes the resource its <code>result_type</code>{' '}
          implies — a <strong>Condition</strong> for a disease or symptom, a{' '}
          <strong>MedicationStatement</strong> for a drug or drug class, an{' '}
          <strong>Immunization</strong> for a vaccine, a{' '}
          <strong>Procedure</strong> for a procedure, and an{' '}
          <strong>Observation</strong> for a lab or vital sign. Filing a vaccine
          as a diagnosis is how derived data becomes unusable downstream. Every
          resource carries the audit trail (engine, confidence, match grade, exact
          character span) on the coding and the note provenance on the resource.
          This is the shape fhir4ds&apos; <code>NotesPipeline</code> produces.
        </p>
        {derivedResources.length > 0 && (
          <div className="adc-tree adc-tree-lg">
            <JsonTree value={derivedResources} expanded collapseKey="extension" />
          </div>
        )}
      </div>
    </div>
  );
}

export default function NotesDemo(): JSX.Element {
  return (
    <BrowserOnly fallback={<div className="autocoding-demo">Loading demo…</div>}>
      {() => <Inner />}
    </BrowserOnly>
  );
}
