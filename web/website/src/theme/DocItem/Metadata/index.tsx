import React from 'react';
import Head from '@docusaurus/Head';
import {useDoc} from '@docusaurus/plugin-content-docs/client';
import DocItemMetadata from '@theme-original/DocItem/Metadata';

/**
 * Adds TechArticle structured data to every docs page.
 *
 * Docusaurus already emits BreadcrumbList for docs pages (that is what drives
 * breadcrumb rich results); what was missing is the article-level entity, which
 * is what lets Google classify a page as documentation rather than a generic
 * WebPage. Site-level Organization/WebSite markup lives in docusaurus.config.ts
 * headTags; the homepage gets SoftwareSourceCode from src/pages/index.tsx.
 *
 * Swizzled as a WRAPPER around @theme-original/DocItem/Metadata: that component
 * renders the standard PageMetadata, so title/description/OpenGraph output is
 * unchanged.
 */
const SITE_URL = 'https://fhir4ds.com';

export default function DocItemMetadataWithStructuredData(): React.ReactElement {
  const {metadata} = useDoc();
  const url = `${SITE_URL}${metadata.permalink}`;

  const article: Record<string, unknown> = {
    '@context': 'https://schema.org',
    '@type': 'TechArticle',
    headline: metadata.title,
    url,
    mainEntityOfPage: {'@type': 'WebPage', '@id': url},
    inLanguage: 'en',
    isPartOf: {'@type': 'WebSite', name: 'FHIR4DS', url: `${SITE_URL}/`},
    author: {'@type': 'Organization', name: 'Montavon Informatics LLC'},
    publisher: {
      '@type': 'Organization',
      name: 'Montavon Informatics LLC',
      logo: {'@type': 'ImageObject', url: `${SITE_URL}/img/icon.svg`},
    },
  };
  if (metadata.description) {
    article.description = metadata.description;
  }

  return (
    <>
      <DocItemMetadata />
      <Head>
        <script type="application/ld+json">{JSON.stringify(article)}</script>
      </Head>
    </>
  );
}
