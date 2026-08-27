import {useState, ReactNode} from 'react';
import clsx from 'clsx';
import Link from '@docusaurus/Link';
import useDocusaurusContext from '@docusaurus/useDocusaurusContext';
import useBaseUrl from '@docusaurus/useBaseUrl';
import Layout from '@theme/Layout';
import Heading from '@theme/Heading';
import styles from './index.module.css';

const PRODUCT_VERSION = '0.0.13';
const SQL_EXECUTION_MEAN_ALL_MEASURES = '~3.9ms';
const SQL_EXECUTION_MEAN_SHARED_MEASURES = '~6.9ms';
const JAVA_EXECUTION_MEAN_SHARED_MEASURES = '~936ms';
const MEAN_SPEEDUP_SHARED_MEASURES = '~137×';
const TOTAL_CONFORMANCE_TESTS = '2,822';
const CQL_CONFORMANCE_TESTS = '1,706';
const FHIRPATH_CONFORMANCE_TESTS = '935';
const VIEWDEF_CONFORMANCE_TESTS = '134';
const ECQM_MEASURES = '47/47';

// ── Stats bar ────────────────────────────────────────────────────────────────

function StatsBar() {
  const stats = [
    {value: SQL_EXECUTION_MEAN_ALL_MEASURES, label: 'SQL mean / patient'},
    {value: 'Zero', label: 'Server infrastructure'},
    {value: TOTAL_CONFORMANCE_TESTS, label: 'Tests passing'},
    {value: 'Full', label: 'Audit Evidence'},
  ];
  return (
    <div className={styles.statsBar}>
      <div className="container">
        <div className={styles.statsRow}>
          {stats.map(s => (
            <div key={s.label} className={styles.statItem}>
              <span className={styles.statValue}>{s.value}</span>
              <span className={styles.statLabel}>{s.label}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ── Interactive Snippet ──────────────────────────────────────────────────────

function InteractiveSnippet() {
  const snippets = [
    {
      title: 'FHIRPath',
      code: `import fhir4ds\n\ncon = fhir4ds.create_connection()\ncon.execute("""\n  SELECT fhirpath_text(resource, 'Patient.name.family') \n  FROM resources\n""")`,
      desc: 'Query FHIR resources using native FHIRPath expressions directly in SQL.'
    },
    {
      title: 'CQL Logic',
      code: `result = fhir4ds.evaluate_measure(\n    library_path="./CMS165.cql",\n    conn=con,\n    parameters={"Period": ("2025-01-01", "2025-12-31")}\n)`,
      desc: 'Compile Clinical Quality Language to vectorized population-scale SQL.'
    },
    {
      title: 'Flattening',
      code: `view = {\n    "resource": "Observation",\n    "select": [\n        {"column": [{"path": "id", "name": "id"}]},\n        {"forEach": "component", "column": [...]}\n    ]\n}\nsql = fhir4ds.generate_view_sql(view)`,
      desc: 'Flatten complex FHIR resources using SQL-on-FHIR v2 ViewDefinitions.'
    },
    {
      title: 'Terminology',
      code: `from fhir4ds.cql.terminology import (\n    TerminologyConfig,\n    get_terminology_endpoint,\n)\n\n# Env-driven: FHIR4DS_TERMINOLOGY_MODE, _URL, _DB, ...\nendpoint = get_terminology_endpoint()\n\n# Expand a ValueSet (SNOMED descendants of Diabetes)\nrefs = endpoint.expand(\n    "http://snomed.info/sct?fhir_vs=isa/73211009"\n)\n# → [CodeRef("http://snomed.info/sct", "73211009", ...), ...]`,
      desc: 'Expand ValueSets and auto-code text-only concepts via medterm4ds — HTTP or in-process.'
    }
  ];

  const [active, setActive] = useState(0);

  return (
    <section className={styles.snippetSection}>
      <div className="container">
        <div className="row">
          <div className="col col--6">
            <Heading as="h2">Native FHIR Analytics</Heading>
            <p className={styles.snippetLead}>
              FHIR4DS treats FHIR as a first-class citizen in the analytical stack. 
              No pre-flattening, no complex ETL—just standard SQL powered by high-performance 
              DuckDB extensions.
            </p>
            <div className={styles.snippetNav}>
              {snippets.map((s, i) => (
                <button 
                  key={i} 
                  className={clsx(styles.snippetTab, i === active && styles.snippetTabActive)}
                  onClick={() => setActive(i)}
                >
                  {s.title}
                </button>
              ))}
            </div>
            <p className={styles.snippetDesc}>{snippets[active].desc}</p>
          </div>
          <div className="col col--6">
            <div className={styles.codeBlock}>
              <div className={styles.codeHeader}>
                <span className={styles.dot} style={{background: '#ff5f56'}} />
                <span className={styles.dot} style={{background: '#ffbd2e'}} />
                <span className={styles.dot} style={{background: '#27c93f'}} />
                <span className={styles.codeTitle}>python</span>
              </div>
              <pre><code>{snippets[active].code}</code></pre>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

// ── Feature cards ─────────────────────────────────────────────────────────────

type Feature = {
  icon: string;
  title: string;
  description: ReactNode;
};

const FEATURES: Feature[] = [
  {
    icon: '⚡',
    title: 'Columnar Speed',
    description: (
      <>
        Process entire populations in a single SQL scan. {MEAN_SPEEDUP_SHARED_MEASURES} faster than 
        traditional engines by utilizing vectorized execution and SIMD.
      </>
    ),
  },
  {
    icon: '🌐',
    title: 'Zero Infrastructure',
    description: (
      <>
        No JVM, no Docker, no servers. Runs locally in notebooks or 100% 
        client-side via WebAssembly for secure SMART on FHIR apps.
      </>
    ),
  },
  {
    icon: '🔍',
    title: 'Full Auditability',
    description: (
      <>
        Every decision includes a human-readable narrative and a logical 
        breadcrumb trail through the logic tree. No more "black box" results.
      </>
    ),
  },
  {
    icon: '🔬',
    title: 'Inspectable SQL',
    description: (
      <>
        Logic compiles to standard, optimisable DuckDB SQL. Debug, index, 
        or export to Parquet—you own the query and the data pipeline.
      </>
    ),
  },
  {
    icon: '📚',
    title: 'Terminology-Aware',
    description: (
      <>
        Expand ValueSets, auto-code text-only concepts, and derive Conditions
        from clinical notes via medterm4ds — over HTTP or embedded in-process.
        <br />
        <Link
          to="/docs/user-guide/terminology/terminology-service"
          style={{fontSize: '0.85rem', fontWeight: 600, display: 'inline-block', marginTop: '0.5rem'}}
        >
          Learn more →
        </Link>
      </>
    ),
  },
  {
    icon: '🎯',
    title: 'Standards Compliant',
    description: (
      <ul style={{listStyleType: 'none', padding: 0, margin: '0.5rem 0 0', fontSize: '0.88rem'}}>
        <li><strong style={{color: 'rgb(95, 237, 131)'}}>100%</strong> CQL ({CQL_CONFORMANCE_TESTS} tests)</li>
        <li><strong style={{color: 'rgb(95, 237, 131)'}}>100%</strong> FHIRPath ({FHIRPATH_CONFORMANCE_TESTS} tests)</li>
        <li><strong style={{color: 'rgb(95, 237, 131)'}}>100%</strong> SQL-on-FHIR v2 ({VIEWDEF_CONFORMANCE_TESTS} tests)</li>
        <li><strong style={{color: 'rgb(95, 237, 131)'}}>{ECQM_MEASURES}</strong> eCQM measures</li>
      </ul>
    ),
  },

];

function FeatureCard({icon, title, description}: Feature) {
  return (
    <div className={clsx('col col--4', styles.featureCol)}>
      <div className={styles.featureCard}>
        <div className={styles.featureIcon}>{icon}</div>
        <Heading as="h3">{title}</Heading>
        <div className={styles.featureDescription}>{description}</div>
      </div>
    </div>
  );
}

function FeaturesSection() {
  return (
    <section className={styles.featuresSection}>
      <div className="container">
        <div className="row">
          {FEATURES.map(f => (
            <FeatureCard key={f.title} {...f} />
          ))}
        </div>
      </div>
    </section>
  );
}

// ── Architecture ──────────────────────────────────────────────────────────────

function ArchitectureSection() {
  return (
    <section className={styles.archSection}>
      <div className="container">
        <div className="text--center" style={{marginBottom: '2.5rem'}}>
          <Heading as="h2">How It Works</Heading>
          <p style={{color: '#94a3b8', maxWidth: 560, margin: '0.75rem auto 0'}}>
            Clinical logic compiles to a single, self-contained DuckDB SQL query.
            Query raw FHIR JSON directly without pre-flattening or ETL.
          </p>
        </div>

        <div className={styles.archPipeline}>
          {['CQL Source', 'Parser', 'SQL Translator', 'DuckDB SQL', 'Results'].map(
            (step, i, arr) => (
              <span key={step} style={{display: 'flex', alignItems: 'center'}}>
                <span className={styles.archStep}>{step}</span>
                {i < arr.length - 1 && (
                  <span className={styles.archArrow}>→</span>
                )}
              </span>
            ),
          )}
        </div>
      </div>
    </section>
  );
}

// ── Comparison table ──────────────────────────────────────────────────────────

function ComparisonSection() {
  return (
    <section className={styles.comparisonSection}>
      <div className="container">
        <div className="text--center" style={{marginBottom: '2rem'}}>
          <Heading as="h2" style={{color: '#f8fafc'}}>FHIR4DS vs <a href="https://github.com/cqframework/clinical-reasoning" style={{color: '#38bdf8'}}>CQF Clinical Reasoning</a></Heading>
          <p style={{color: '#94a3b8'}}>
            Same accuracy target. Radically different performance.
          </p>
        </div>
        <div className={styles.compTableWrapper}>
          <table className={styles.compTable}>
            <thead>
              <tr>
                <th>Capability</th>
                <th className={styles.colFhir4ds}>FHIR4DS</th>
                <th className={styles.colJava}>CQF Clinical Reasoning</th>
              </tr>
            </thead>
            <tbody>
              {[
                ['SQL execution per patient (all 47 measures)', SQL_EXECUTION_MEAN_ALL_MEASURES, 'N/A', true],
                ['SQL execution per patient (12 shared measures)', SQL_EXECUTION_MEAN_SHARED_MEASURES, JAVA_EXECUTION_MEAN_SHARED_MEASURES, true],
                ['Speedup (mean, 12 shared measures)', `${MEAN_SPEEDUP_SHARED_MEASURES} faster`, 'baseline', true],
                ['Zero server infrastructure', '✅ DuckDB-WASM', '❌ Requires JVM + server', true],
                ['Audit evidence trail', '✅ Full narrative', '❌ Aggregate counts only', true],
                ['Output is inspectable', '✅ Plain SQL', '❌ Black-box engine', true],
                ['Columnar scalability', '✅ Vectorized', '⚠️ Sequential loop', true],
                ['SQL-on-FHIR v2 support', '✅ 100% compliance', '❌ Not supported', true],
              ].map(([cap, f4ds, java, highlight]) => (
                <tr key={cap as string}>
                  <td>{cap}</td>
                  <td className={highlight ? styles.cellGood : ''}>{f4ds}</td>
                  <td className={styles.cellMuted}>{java}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="text--center" style={{marginTop: '2rem'}}>
          <Link className="button button--outline button--primary" to="/docs/getting-started/benchmarking">
            View Full Benchmarking Report →
          </Link>
        </div>
      </div>
    </section>
  );
}

function CtaSection() {
  return (
    <section className={styles.ctaSection}>
      <div className="container text--center">
        <Heading as="h2">Ready to scale your FHIR analytics?</Heading>
        <p style={{color: '#94a3b8', marginBottom: '2rem', maxWidth: '600px', margin: '0 auto 2rem'}}>
          Join the modern healthcare data stack. Open-source, standards-compliant, 
          and built for high-performance clinical quality measurement.
        </p>
        <div style={{display: 'flex', gap: '1rem', justifyContent: 'center', flexWrap: 'wrap'}}>
          <Link className="button button--primary button--lg" to="/docs/getting-started/installation">
            Install fhir4ds
          </Link>
          <Link className="button button--secondary button--lg" to="/docs/user-guide/index">
            Explore User Guide
          </Link>
          <Link
            className="button button--secondary button--lg"
            href="https://github.com/fhir4ds/fhir4ds">
            ⭐ GitHub
          </Link>
        </div>
      </div>
    </section>
  );
}

// ── Hero ──────────────────────────────────────────────────────────────────────

function Hero() {
  const logoUrl = useBaseUrl('img/icon.svg');
  return (
    <header className={clsx('hero hero--primary', styles.heroBanner)}>
      <div className={styles.heroGrid} />
      <div className="container">
        <div style={{display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '1rem', marginBottom: '1rem', flexWrap: 'wrap'}}>
          <img src={logoUrl} alt="FHIR for Data Science Logo" style={{width: '4rem', height: '4rem'}} />
          <Heading as="h1" className="hero__title" style={{marginBottom: 0, background: 'none', WebkitTextFillColor: 'rgb(95, 237, 131)', color: 'rgb(95, 237, 131)'}}>
            FHIR for Data Science
          </Heading>
          <span className={styles.versionBadge}>v{PRODUCT_VERSION}</span>
          <Link
            to="/docs/user-guide/terminology/terminology-service"
            style={{
              background: 'rgba(95, 237, 131, 0.12)',
              border: '1px solid rgba(95, 237, 131, 0.4)',
              color: 'rgb(95, 237, 131)',
              padding: '0.2rem 0.75rem',
              borderRadius: '20px',
              fontSize: '0.78rem',
              fontWeight: 600,
              textDecoration: 'none',
              transition: 'background 0.15s ease',
            }}
          >
            New in 0.0.13: Native Engine Restorations &amp; medterm4ds 0.0.3 →
          </Link>
        </div>
        <p style={{fontSize: '1.35rem', fontWeight: 600, color: '#e2e8f0', margin: '0.4rem 0 0.6rem'}}>
          Production-Scale FHIR Analytics. Running Anywhere.
        </p>
        <p className="hero__subtitle" style={{fontSize: '1.1rem', fontWeight: 400, color: '#94a3b8', marginBottom: '2rem', maxWidth: '800px', margin: '0 auto 2rem'}}>
          The first SQL-native clinical reasoning engine. Translate CQL to DuckDB SQL
          for blazing fast, auditable population health analytics with zero server infrastructure.
        </p>
        <div style={{display: 'flex', gap: '1rem', justifyContent: 'center', flexWrap: 'wrap'}}>
          <Link className="button button--primary button--lg" to="/docs/getting-started/installation">
            Get Started →
          </Link>
          <Link className="button button--secondary button--lg" to="/docs/examples/cql-playground">
            🌐 Live Demo
          </Link>
        </div>
      </div>
    </header>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function Home(): ReactNode {
  const {siteConfig} = useDocusaurusContext();
  return (
    <Layout
      title={siteConfig.title}
      description="SQL-Native CQL Evaluation for FHIR — Production-Accurate, In-Browser, Auditable">
      <Hero />
      <StatsBar />
      <InteractiveSnippet />
      <FeaturesSection />
      <ArchitectureSection />
      <ComparisonSection />
      <CtaSection />
    </Layout>
  );
}
