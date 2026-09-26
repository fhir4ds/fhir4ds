import { useRef } from "react";

interface Props {
  value: number;
  onChange: (fr: number) => void;
  /** "vertical" splits columns (drag x, ratio to the col AFTER it);
   *  "horizontal" splits stacked panes (drag y). */
  orientation?: "vertical" | "horizontal";
  min?: number;
  max?: number;
  testid?: string;
  label?: string;
}

const MIN = 0.3;
const MAX = 2.5;

/**
 * Drag handle between grid tracks. The track AFTER the splitter is fixed
 * at 1fr, so a pixel delta converts directly: dFr = px / afterPx.
 */
export function Splitter({
  value,
  onChange,
  orientation = "vertical",
  min = MIN,
  max = MAX,
  testid = "col-splitter",
  label = "Resize editor and report columns",
}: Props) {
  const dragRef = useRef<{
    startPx: number;
    startFr: number;
    afterPx: number;
  } | null>(null);
  const horizontal = orientation === "horizontal";
  return (
    <div
      className={`splitter ${horizontal ? "horizontal" : ""}`}
      role="separator"
      aria-orientation={orientation}
      aria-label={label}
      data-testid={testid}
      onPointerDown={(e) => {
        const afterEl = e.currentTarget
          .nextElementSibling as HTMLElement | null;
        if (!afterEl) return;
        dragRef.current = {
          startPx: horizontal ? e.clientY : e.clientX,
          startFr: value,
          afterPx: afterEl.getBoundingClientRect()[horizontal ? "height" : "width"],
        };
        e.currentTarget.setPointerCapture(e.pointerId);
      }}
      onPointerMove={(e) => {
        const d = dragRef.current;
        if (!d || d.afterPx < 1) return;
        const px = horizontal ? e.clientY : e.clientX;
        const fr = d.startFr + (px - d.startPx) / d.afterPx;
        onChange(
          Math.min(max, Math.max(min, Math.round(fr * 100) / 100)),
        );
      }}
      onPointerUp={(e) => {
        dragRef.current = null;
        e.currentTarget.releasePointerCapture(e.pointerId);
      }}
    />
  );
}
