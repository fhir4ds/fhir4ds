import { useEffect, useRef, useState } from "react";

// Initialize mermaid once with our dark theme. Colors match the app's CSS vars.
let initialized = false;
async function ensureMermaid() {
  if (initialized) return (await import("mermaid")).default;
  const mermaid = (await import("mermaid")).default;
  mermaid.initialize({
    startOnLoad: false,
    theme: "base",
    themeVariables: {
      background: "#0b1220",
      primaryColor: "#131c30",
      primaryTextColor: "#e6ecf5",
      primaryBorderColor: "#38bdf8",
      lineColor: "#5fed83",
      secondaryColor: "#1c2741",
      secondaryTextColor: "#94a3b8",
      secondaryBorderColor: "#2c3957",
      tertiaryColor: "#0f172a",
      tertiaryTextColor: "#64748b",
      tertiaryBorderColor: "#2c3957",
      fontSize: "13px",
      fontFamily: "ui-sans-serif, system-ui, sans-serif",
    },
    flowchart: {
      // Use SVG <text> for labels instead of HTML inside <foreignObject>.
      // foreignObject rendering is unreliable across browsers and harder to
      // style from outside (mermaid injects ID-prefixed CSS that beats
      // class-based overrides). SVG text just works.
      htmlLabels: false,
      curve: "basis",
      padding: 15,
    },
  });
  initialized = true;
  return mermaid;
}

/**
 * Renders a Mermaid diagram from a definition string. Lazy-loads the mermaid
 * library on first use so it doesn't block initial page render.
 *
 * The dark theme colors are configured to match the app's CSS variables.
 */
export function MermaidDiagram({ chart }: { chart: string }) {
  const [svg, setSvg] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const idRef = useRef(`mmd-${Math.random().toString(36).slice(2, 9)}`);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const mermaid = await ensureMermaid();
        const { svg } = await mermaid.render(idRef.current, chart);
        if (!cancelled) {
          setSvg(svg);
          setError(null);
        }
      } catch (e: any) {
        if (!cancelled) {
          setError(e?.message ?? "Diagram render failed");
          console.error("[Mermaid]", e);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [chart]);

  if (error) {
    return <pre className="mermaid-fallback">{chart}</pre>;
  }

  return (
    <div
      className="mermaid-container"
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  );
}
