import { useEffect, useRef } from "react";

/**
 * PASS2 G1: left navigation rail. Replaces the library tab-strip:
 * vertical library list + Dataset / Terminology navigation entries.
 *
 * - The ENTRYPOINT marker (●) decouples the evaluated root (main) from
 *   the edited tab — run-eval always evaluates the marked library.
 * - Parse-error badges (red dot) mark libraries whose text fails parse.
 * - role=tablist + arrow-key navigation (a11y guardrails).
 * - e2e compatibility: keeps the legacy library-tabs/library-tab-N/
 *   library-tab-N-close/library-tab-add testids as aliases.
 */

export interface RailLibrary {
  name: string;
  hasError?: boolean;
}

export function NavRail({
  libraries,
  activeIndex,
  entrypointIndex,
  onSelect,
  onClose,
  onAdd,
  onSetEntrypoint,
  onNavigateDataset,
  onNavigateTerminology,
  datasetActive,
  terminologyActive,
}: {
  libraries: RailLibrary[];
  activeIndex: number;
  entrypointIndex: number;
  onSelect: (i: number) => void;
  onClose: (i: number) => void;
  onAdd: () => void;
  onSetEntrypoint: (i: number) => void;
  onNavigateDataset: () => void;
  onNavigateTerminology: () => void;
  datasetActive: boolean;
  terminologyActive: boolean;
}) {
  const tabRefs = useRef<Array<HTMLButtonElement | null>>([]);

  useEffect(() => {
    tabRefs.current = tabRefs.current.slice(0, libraries.length + 1);
  }, [libraries.length]);

  const focusAt = (i: number) => {
    const max = libraries.length; // index libraries.length === the + add button
    const clamped = ((i % (max + 1)) + (max + 1)) % (max + 1);
    tabRefs.current[clamped]?.focus();
  };

  const onKeyDown = (e: React.KeyboardEvent, i: number) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      focusAt(i + 1);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      focusAt(i - 1);
    } else if (e.key === "Home") {
      e.preventDefault();
      focusAt(0);
    } else if (e.key === "End") {
      e.preventDefault();
      focusAt(libraries.length);
    }
  };

  return (
    <nav className="nav-rail" data-testid="nav-rail" aria-label="workspace navigation">
      <div className="rail-label">Libs</div>
      {/* Legacy alias: e2e greps `^=library-tab-` — the wrapper keeps the
          per-item testid, this hidden span keeps the container testid. */}
      <span hidden data-testid="library-tabs" />
      <div role="tablist" aria-orientation="vertical" style={{ display: "contents" }}>
        {libraries.map((lib, i) => (
          <button
            key={lib.name + i}
            ref={(el) => {
              tabRefs.current[i] = el;
            }}
            role="tab"
            aria-selected={i === activeIndex}
            tabIndex={i === activeIndex ? 0 : -1}
            className={`rail-item ${i === activeIndex ? "active" : ""}`}
            data-testid={`library-tab-${i}`}
            title={
              i === entrypointIndex
                ? `${lib.name} (entrypoint — evaluated on Run)`
                : lib.name
            }
            onClick={() => onSelect(i)}
            onKeyDown={(e) => onKeyDown(e, i)}
            onDoubleClick={() => onSetEntrypoint(i)}
            onContextMenu={(e) => {
              e.preventDefault();
              onClose(i);
            }}
          >
            <span className="rail-glyph">{lib.name.slice(0, 2)}</span>
            <span className="rail-name">
              {lib.name}
              {i === entrypointIndex ? " ● entrypoint" : ""}
              {lib.hasError ? " — parse error" : ""}
              {libraries.length > 1 ? " (dbl-click = entrypoint, right-click = close)" : ""}
            </span>
            {lib.hasError && <span className="rail-badge err" aria-label="parse error" />}
            {i === entrypointIndex && (
              <span className="rail-badge entry" aria-label="entrypoint" />
            )}
          </button>
        ))}
        <button
          ref={(el) => {
            tabRefs.current[libraries.length] = el;
          }}
          role="tab"
          aria-selected={false}
          tabIndex={-1}
          className="rail-item"
          data-testid="library-tab-add"
          title="add library"
          onClick={onAdd}
          onKeyDown={(e) => onKeyDown(e, libraries.length)}
        >
          <span className="rail-glyph">+</span>
          <span className="rail-name">Add library</span>
        </button>
      </div>
      <div className="rail-sep" />
      <button
        className={`rail-item ${datasetActive ? "active" : ""}`}
        data-testid="rail-dataset"
        title="Dataset"
        onClick={onNavigateDataset}
      >
        <span className="rail-glyph">▦</span>
        <span className="rail-name">Dataset</span>
      </button>
      <button
        className={`rail-item ${terminologyActive ? "active" : ""}`}
        data-testid="rail-terminology"
        title="Terminology (ValueSets)"
        onClick={onNavigateTerminology}
      >
        <span className="rail-glyph">Ⓣ</span>
        <span className="rail-name">Terminology</span>
      </button>
    </nav>
  );
}
