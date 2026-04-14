/** Shared status indicator dot used in headers across CQL, CMS, and SDC. */
export function StatusDot({ ready, label }: { ready: boolean; label: string }) {
  return (
    <span className={`status-dot ${ready ? "ready" : "loading"}`}>
      <span className="dot" />
      {label}
    </span>
  );
}
