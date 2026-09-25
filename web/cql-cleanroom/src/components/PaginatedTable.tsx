import { useEffect, useState } from "react";

/**
 * Output table with horizontal-scroll containment + pagination.
 * - Wide tables scroll INSIDE the pane (scrollbar under the table),
 *   never bleeding into neighboring grid columns.
 * - >PAGE_SIZE rows paginate (prev/next + range of total).
 */
const PAGE_SIZE = 10;

export interface RowRange {
  start: number;
  end: number;
  slice: <T>(arr: T[]) => T[];
}

export function PaginatedTable({
  testId,
  header,
  renderRows,
  rowCount,
}: {
  testId: string;
  /** <tr>…</tr> for the thead. */
  header: React.ReactNode;
  /** <tr>…</tr> rows for the visible page. */
  renderRows: (range: RowRange) => React.ReactNode;
  rowCount: number;
}) {
  const [page, setPage] = useState(0);
  const pageCount = Math.max(1, Math.ceil(rowCount / PAGE_SIZE));
  useEffect(() => {
    if (page > pageCount - 1) setPage(0);
  }, [pageCount, page]);
  const start = page * PAGE_SIZE;
  const end = Math.min(start + PAGE_SIZE, rowCount);

  return (
    <div className="results-table-block" data-testid={`${testId}-block`}>
      <div className="results-table-wrap" data-testid={`${testId}-wrap`}>
        <table className="results-table" data-testid={testId}>
          <thead>{header}</thead>
          <tbody>
            {renderRows({
              start,
              end,
              slice: (arr) => arr.slice(start, end),
            })}
          </tbody>
        </table>
      </div>
      {rowCount > PAGE_SIZE && (
        <div className="table-pager" data-testid={`${testId}-pager`}>
          <button
            data-testid={`${testId}-prev`}
            disabled={page === 0}
            onClick={() => setPage((p) => Math.max(0, p - 1))}
          >
            ‹ prev
          </button>
          <span className="table-pager-info">
            {start + 1}–{end} of {rowCount}
          </span>
          <button
            data-testid={`${testId}-next`}
            disabled={page >= pageCount - 1}
            onClick={() => setPage((p) => Math.min(pageCount - 1, p + 1))}
          >
            next ›
          </button>
        </div>
      )}
    </div>
  );
}
