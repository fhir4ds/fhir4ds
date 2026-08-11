import { useEffect, useState } from "react";

interface SectionNavProps {
  sections: Array<{ number: number; label: string; title: string }>;
}

/**
 * Sticky right-side section navigation. Each item is an anchor link to the
 * section's `id`. The currently-visible section is highlighted via
 * IntersectionObserver — set up to fire when a section's top crosses the
 * upper third of the viewport.
 *
 * Hidden below 1100px viewport width (see styles.css).
 */
export function SectionNav({ sections }: SectionNavProps) {
  const [active, setActive] = useState<number>(sections[0]?.number ?? 1);

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        // Pick the entry closest to the top of the viewport that's currently
        // intersecting. The simplest correct heuristic: track entries with
        // isIntersecting=true and choose the one with the smallest
        // boundingClientRect.top.
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (visible.length > 0) {
          const id = visible[0].target.id;
          const m = id.match(/^section-(\d+)$/);
          if (m) setActive(Number(m[1]));
        }
      },
      {
        // The "active" zone: upper 40% of the viewport. Sections in this zone
        // are considered "current".
        rootMargin: "-20% 0px -60% 0px",
        threshold: 0,
      },
    );

    for (const s of sections) {
      const el = document.getElementById(`section-${s.number}`);
      if (el) observer.observe(el);
    }
    return () => observer.disconnect();
  }, [sections]);

  return (
    <nav className="app__nav" aria-label="Section navigation">
      <div className="app__nav__title">Walkthrough</div>
      <ol>
        {sections.map((s) => (
          <li key={s.number}>
            <a
              href={`#section-${s.number}`}
              className={active === s.number ? "is-active" : ""}
            >
              <span className="app__nav__number">§{s.number}</span>
              {s.label}
            </a>
          </li>
        ))}
      </ol>
    </nav>
  );
}
