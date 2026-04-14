/**
 * Lightweight OAuth2 callback handler for popup context.
 *
 * Rendered in place of the full App when:
 *   - The URL contains ?code= and ?state= (OAuth callback)
 *   - window.opener is set (we're inside a popup)
 *
 * Exchanges the authorization code for a token, posts the result to
 * the opener window, and closes the popup. DuckDB and Pyodide are
 * never initialized — the popup closes before they finish loading.
 */
import { useEffect, useState } from 'react';
import { handleCallback, getStoredSession } from '../lib/smart-auth';

export function SmartCallbackPage() {
  const [status, setStatus] = useState<'exchanging' | 'done' | 'error'>('exchanging');
  const [errorMsg, setErrorMsg] = useState('');

  useEffect(() => {
    handleCallback()
      .then((token) => {
        const session = getStoredSession();
        if (window.opener) {
          window.opener.postMessage(
            { type: 'FHIR4DS_SMART_TOKEN', token, session },
            window.location.origin,
          );
        }
        setStatus('done');
        // Small delay to ensure postMessage is delivered before close
        setTimeout(() => window.close(), 200);
      })
      .catch((err) => {
        const msg = err instanceof Error ? err.message : String(err);
        setErrorMsg(msg);
        setStatus('error');
        if (window.opener) {
          window.opener.postMessage(
            { type: 'FHIR4DS_SMART_ERROR', error: msg },
            window.location.origin,
          );
        }
      });
  }, []);

  const baseStyle: React.CSSProperties = {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    height: '100vh',
    background: '#0f172a',
    color: '#e2e8f0',
    fontFamily: 'Inter, system-ui, sans-serif',
    gap: '1rem',
    padding: '2rem',
    textAlign: 'center',
  };

  if (status === 'error') {
    return (
      <div style={baseStyle}>
        <p style={{ fontSize: '2rem' }}>⚠️</p>
        <p style={{ color: '#f87171', fontWeight: 600 }}>Authorization failed</p>
        <p style={{ color: '#94a3b8', fontSize: '0.9rem', maxWidth: 400 }}>{errorMsg}</p>
        <button
          onClick={() => window.close()}
          style={{
            padding: '0.5rem 1.5rem',
            cursor: 'pointer',
            marginTop: '1rem',
            background: '#334155',
            color: '#e2e8f0',
            border: '1px solid #475569',
            borderRadius: '6px',
          }}
        >
          Close
        </button>
      </div>
    );
  }

  return (
    <div style={baseStyle}>
      <div style={{
        width: 40, height: 40, border: '3px solid rgba(56,189,248,0.2)',
        borderTopColor: '#38bdf8', borderRadius: '50%',
        animation: 'spin 0.8s linear infinite',
      }} />
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      <p>{status === 'done' ? 'Authorization complete!' : 'Completing authorization…'}</p>
      <p style={{ color: '#64748b', fontSize: '0.8rem' }}>This window will close automatically.</p>
    </div>
  );
}
