import {useState, useCallback, useEffect} from 'react';
import type {ReactNode} from 'react';
import useDocusaurusContext from '@docusaurus/useDocusaurusContext';
import ExecutionEnvironment from '@docusaurus/ExecutionEnvironment';
import styles from './WasmDemo.module.css';

type DemoState = 'idle' | 'loading' | 'loaded' | 'error';
type DemoType = 'playground' | 'smart' | 'dqm' | 'forms';

interface WasmDemoProps {
  type?: DemoType;
}

const TYPE_TO_SCENARIO: Record<DemoType, string> = {
  playground: 'cql-sandbox',
  smart: 'smart-flow',
  dqm: 'cms-measures',
  forms: 'sdc-forms',
};

export default function WasmDemo({ type = 'playground' }: WasmDemoProps): ReactNode {
  const {siteConfig} = useDocusaurusContext();
  const baseUrl = siteConfig.baseUrl.replace(/\/$/, '');
  
  const [state, setState] = useState<DemoState>('idle');
  const [launched, setLaunched] = useState(false);

  // Parse callback parameters from the PARENT window URL
  let callbackParams = '';
  if (ExecutionEnvironment.canUseDOM) {
    const params = new URLSearchParams(window.location.search);
    const code = params.get('code');
    const stateParam = params.get('state');
    if (code && stateParam) {
      callbackParams = `&code=${encodeURIComponent(code)}&state=${encodeURIComponent(stateParam)}`;
    }
  }

  // Auto-launch if we have callback parameters (returning from EHR)
  useEffect(() => {
    if (callbackParams && !launched) {
      setLaunched(true);
      setState('loading');
    }
  }, [callbackParams, launched]);

  const scenario = TYPE_TO_SCENARIO[type];
  const demoSrc = `${baseUrl}/wasm-app/index.html?scenario=${scenario}${callbackParams}`;

  const launch = useCallback(() => {
    setLaunched(true);
    setState('loading');
  }, []);

  const handleLoad = useCallback(() => setState('loaded'), []);
  const handleError = useCallback(() => setState('error'), []);

  const title = type === 'smart' ? 'SMART on FHIR Demo'
    : type === 'forms' ? 'Interactive SDC Forms Demo'
    : 'Interactive CQL/DQM Demo';
  const desc = type === 'smart' 
    ? 'Connect to live EHR sandboxes (Epic, Cerner) and query data in your browser.'
    : type === 'forms'
    ? 'Render FHIR Questionnaires with live FHIRPath calculations and patient pre-population.'
    : 'Run CQL measures in your browser via DuckDB-WASM and C++ extensions.';

  if (!launched) {
    return (
      <div className={styles.launcher}>
        <div className={styles.launcherContent}>
          <div className={styles.launcherIcon}>🌐</div>
          <h3 className={styles.launcherTitle}>{title}</h3>
          <p className={styles.launcherDesc}>{desc}</p>
          <div className={styles.launcherBadges}>
            <span className={styles.badge}>🔒 Zero server</span>
            <span className={styles.badge}>🌐 WebAssembly</span>
            <span className={styles.badge}>🔍 Full audit evidence</span>
            <span className={styles.badge}>⚡ C++ extensions</span>
          </div>
          <button className={styles.launchBtn} onClick={launch}>
            Launch Demo
          </button>
          <p className={styles.launcherNote}>
            Requires SharedArrayBuffer support (Chrome, Firefox, Edge). First load
            downloads ~50MB of WASM assets.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.demoWrapper}>
      {state === 'loading' && (
        <div className={styles.loadingOverlay}>
          <div className={styles.spinner} />
          <p>Loading DuckDB-WASM and C++ extensions…</p>
          <p className={styles.loadingNote}>First load downloads ~50MB of WASM assets.</p>
        </div>
      )}
      {state === 'error' && (
        <div className={styles.errorOverlay}>
          <p>⚠️ Demo failed to load. Your browser may not support SharedArrayBuffer.</p>
          <p>
            Try Chrome, Firefox, or Edge with cross-origin isolation headers.
            Alternatively,{' '}
            <a href="https://github.com/joelmontavon/fhir4ds-v2" target="_blank" rel="noopener noreferrer">
              run the demo locally
            </a>.
          </p>
        </div>
      )}
      <iframe
        className={styles.demoIframe}
        src={demoSrc}
        title={`FHIR4DS ${title}`}
        allow="cross-origin-isolated"
        loading="eager"
        onLoad={handleLoad}
        onError={handleError}
        style={{display: state === 'error' ? 'none' : 'block'}}
      />
    </div>
  );
}
