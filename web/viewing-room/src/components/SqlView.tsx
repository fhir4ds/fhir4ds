/** Verbatim generated SQL view (design §4: never rewritten). */

export function SqlView({ sql }: { sql: string | null }) {
  return (
    <pre className="sql-view" data-testid="sql-view">
      {sql ?? "-- run the view to see the generated SQL"}
    </pre>
  );
}
