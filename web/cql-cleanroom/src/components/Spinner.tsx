/**
 * S30: the app-wide loading indicator. Replaces bare-text loading states
 * ("loading…", "running view…", "explaining…") with one consistent
 * animated spinner. `label` is the accessible name (aria-label); it is
 * NOT rendered as visible text — the spinner is the state.
 */
export function Spinner({ label }: { label: string }) {
  return (
    <span
      className="spinner"
      role="status"
      aria-label={label}
      data-testid="spinner"
    />
  );
}
