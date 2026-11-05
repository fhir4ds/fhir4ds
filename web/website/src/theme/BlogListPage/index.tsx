import Head from '@docusaurus/Head';
import type {Props} from '@theme/BlogListPage';
import React, {useEffect} from 'react';

/**
 * `/blog` shows the LATEST post as a full article (consistent with the
 * article layout: timeline left, TOC right) instead of a post list.
 * Other posts remain reachable via the timeline sidebar, the paginator
 * archive (/blog/archive), and tags.
 */
export default function BlogListPage({items}: Props): JSX.Element {
  const first: any = items[0];
  const latest =
    first?.permalink ??
    first?.content?.metadata?.permalink ??
    first?.metadata?.permalink ??
    '/blog/archive';
  useEffect(() => {
    window.location.replace(latest);
  }, [latest]);
  return (
    <>
      <Head>
        <meta httpEquiv="refresh" content={`0;url=${latest}`} />
        <link rel="canonical" href={latest} />
        <title>Blog — FHIR4DS</title>
      </Head>
      <p style={{padding: '2rem', textAlign: 'center'}}>
        Redirecting to the latest post… <a href={latest}>Continue</a>
      </p>
    </>
  );
}
