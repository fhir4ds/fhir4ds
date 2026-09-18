/**
 * DemoAppWindow — chrome-less dark shell for the standalone /apps/* pages
 * (the "Open in new window ↗" pop-outs). Renders a slim title bar and a
 * main area that the demo fills. Shared by the scheduling demo app and the
 * web-component demos (CQL Playground, Quality Measures, SDC Forms, SMART).
 */

import Head from "@docusaurus/Head";
import type { ReactNode } from "react";
import styles from "./DemoAppWindow.module.css";

export default function DemoAppWindow({
  title,
  documentTitle,
  children,
}: {
  /** Shown in the slim header bar. */
  title: string;
  /** Browser/document title; defaults to "{title} · FHIR4DS". */
  documentTitle?: string;
  children: ReactNode;
}) {
  return (
    <div className={styles.window}>
      <Head>
        <title>{documentTitle ?? `${title} · FHIR4DS`}</title>
        <meta name="robots" content="noindex" />
      </Head>
      <header className={styles.header}>
        <span className={styles.title}>{title}</span>
      </header>
      <main className={styles.main}>{children}</main>
    </div>
  );
}
