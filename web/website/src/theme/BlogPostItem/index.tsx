import BlogPostItem from '@theme-original/BlogPostItem';
import type {Props} from '@theme/BlogPostItem';
import {useLocation} from '@docusaurus/router';
import React, {useRef, useState} from 'react';

/**
 * Wrap blog post items with a direct "Save as PDF" affordance on ARTICLE
 * pages (index cards stay clean). The click renders the article element
 * to a paginated PDF client-side (html2pdf.js, lazily loaded from CDN on
 * first use) and downloads it — no print dialog.
 */

const HTML2PDF_URL =
  'https://cdn.jsdelivr.net/npm/html2pdf.js@0.10.2/dist/html2pdf.bundle.min.js';

let html2pdfPromise: Promise<any> | null = null;
function loadHtml2Pdf(): Promise<any> {
  if (!html2pdfPromise) {
    html2pdfPromise = new Promise((resolve, reject) => {
      const s = document.createElement('script');
      s.src = HTML2PDF_URL;
      s.onload = () => resolve((window as any).html2pdf);
      s.onerror = () => {
        html2pdfPromise = null;
        reject(new Error('failed to load the PDF engine'));
      };
      document.head.appendChild(s);
    });
  }
  return html2pdfPromise;
}

export default function BlogPostItemWrapper(props: Props): JSX.Element {
  const {pathname} = useLocation();
  const isListPage = /^\/blog(\/page\/\d+)?\/?$/.test(pathname);
  const [state, setState] = useState<'idle' | 'working'>('idle');
  const rootRef = useRef<HTMLDivElement>(null);

  async function saveAsPdf(): Promise<void> {
    const article = rootRef.current?.querySelector('article');
    if (!article) return;
    setState('working');
    // Capture a light-styled CLONE parked off-screen, so the visible page
    // never flashes. The clone lives in the DOM (layout + computed styles
    // are real) but sits far off-canvas.
    const clone = article.cloneNode(true) as HTMLElement;
    clone.classList.add('pdf-light-capture');
    clone.style.width = `${article.getBoundingClientRect().width}px`;
    clone.style.margin = '0';
    // In-flow, right after the article (same layout context html2canvas
    // captured successfully); the opaque cover below hides it from the user.
    article.after(clone);
    // Opaque cover above the clone: no visible style-flash or layout
    // shift; a calm progress screen while the PDF renders.
    const cover = document.createElement('div');
    cover.textContent = 'Building PDF…';
    Object.assign(cover.style, {
      position: 'fixed',
      inset: '0',
      zIndex: '9999',
      background: 'var(--ifm-background-color, #fff)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      fontSize: '1.1rem',
    });
    document.body.appendChild(cover);
    try {
      await new Promise((r) => setTimeout(r, 120));
      const html2pdf = await loadHtml2Pdf();
      const title =
        (document.querySelector('article header h1')?.textContent ??
          'fhir4ds-blog-post').trim();
      await html2pdf().set({
        margin: [12, 14, 14, 14],
        filename: `${title.replace(/[^\w\s-]/g, '').replace(/\s+/g, '-').toLowerCase()}.pdf`,
        image: {type: 'jpeg', quality: 0.95},
        html2canvas: {
          scale: 2,
          useCORS: true,
          backgroundColor: '#ffffff',
        },
        jsPDF: {unit: 'mm', format: 'a4', orientation: 'portrait'},
        pagebreak: {mode: ['avoid-all', 'css', 'legacy']},
      }).from(clone).save();
    } catch (err) {
      console.error('[blog PDF]', err);
    } finally {
      clone.remove();
      cover.remove();
      setState('idle');
    }
  }

  return (
    <div ref={rootRef}>
      {!isListPage && (
        <div className="blog-pdf-bar">
          <button
            type="button"
            className="blog-pdf-btn"
            onClick={() => void saveAsPdf()}
            disabled={state === 'working'}
            title="Download this post as a PDF">
            <svg
              aria-hidden="true"
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.2"
              strokeLinecap="round"
              strokeLinejoin="round">
              <path d="M12 3v12" />
              <path d="m7 11 5 5 5-5" />
              <path d="M4 19h16" />
            </svg>
            {state === 'working' ? 'Building PDF…' : 'Save as PDF'}
          </button>
        </div>
      )}
      <BlogPostItem {...props} />
    </div>
  );
}
