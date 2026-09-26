import { useRef } from "react";

interface Props {
  col1Fr: number;
  onChange: (fr: number) => void;
}

const MIN = 0.3;
const MAX = 2.5;

/**
 * Vertical drag handle between the editor column and the report column.
 * Col2 is fixed at 1fr, so a pixel delta converts directly: dFr = dx / col2px.
 */
export function Splitter({ col1Fr, onChange }: Props) {
  const dragRef = useRef<{
    startX: number;
    startFr: number;
    col2Px: number;
  } | null>(null);
  return (
    <div
      className="splitter"
      role="separator"
      aria-orientation="vertical"
      aria-label="Resize editor and report columns"
      data-testid="col-splitter"
      onPointerDown={(e) => {
        const main = e.currentTarget.parentElement;
        const col2 = main?.querySelector<HTMLElement>(".run-col");
        if (!col2) return;
        dragRef.current = {
          startX: e.clientX,
          startFr: col1Fr,
          col2Px: col2.getBoundingClientRect().width,
        };
        e.currentTarget.setPointerCapture(e.pointerId);
      }}
      onPointerMove={(e) => {
        const d = dragRef.current;
        if (!d || d.col2Px < 1) return;
        const fr = d.startFr + (e.clientX - d.startX) / d.col2Px;
        onChange(Math.min(MAX, Math.max(MIN, Math.round(fr * 100) / 100)));
      }}
      onPointerUp={(e) => {
        dragRef.current = null;
        e.currentTarget.releasePointerCapture(e.pointerId);
      }}
    />
  );
}
