import type { ReactNode } from "react";

interface SectionProps {
  /** Section number for the "§N" indicator. */
  number: number;
  /** Short label that appears next to the number. */
  label: string;
  /** Section heading. */
  title: string;
  /** Everything below the heading: prose paragraphs + interactive widget. */
  children: ReactNode;
  /** Optional: id for anchor navigation. Defaults to `section-N`. */
  id?: string;
}

/**
 * A vertical section in the blog-post walkthrough. Heading on top, then
 * arbitrary content (prose + interactive widget) as children. Centered in the
 * page's max-width column.
 */
export function Section({ number, label, title, children, id }: SectionProps) {
  return (
    <section className="section" id={id ?? `section-${number}`}>
      <header className="section__header">
        <div className="section__eyebrow">
          <span className="section__number">§{number}</span>
          <span className="section__label">{label}</span>
        </div>
        <h2 className="section__title">{title}</h2>
      </header>
      <div className="section__body">{children}</div>
    </section>
  );
}
