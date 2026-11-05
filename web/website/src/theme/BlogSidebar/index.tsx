import type {Props} from '@theme/BlogSidebar';
import Link from '@docusaurus/Link';
import {useLocation} from '@docusaurus/router';
import React from 'react';

/**
 * Blog sidebar as a chronological timeline — rendered ONLY on the blog
 * index (list) pages, where "which post should I read?" is the live
 * question. Article pages keep their in-article TOC instead (one nav
 * rail per page); cross-post discovery on articles is handled by the
 * "More posts" footer in the BlogPostItem wrapper.
 */
interface SidebarItem {
  title: string;
  permalink: string;
  date: string;
}

export default function BlogSidebarTimeline({sidebar}: Props): JSX.Element {
  const {pathname} = useLocation();
  const items = (sidebar.items ?? []) as unknown as SidebarItem[];

  const groups: Array<{year: string; posts: Array<{month: string; item: SidebarItem}>}> = [];
  for (const item of items) {
    const date = new Date(item.date);
    if (Number.isNaN(date.getTime())) continue;
    const year = String(date.getFullYear());
    const month = date.toLocaleDateString('en-US', {month: 'short'});
    let group = groups.find((g) => g.year === year);
    if (!group) {
      group = {year, posts: []};
      groups.push(group);
    }
    group.posts.push({month, item});
  }

  return (
    <nav className="blog-timeline col col--3" aria-label="Blog posts timeline">
      <div className="blog-timeline-inner">
        <h3 className="blog-timeline-heading">Posts</h3>
      {groups.map((group) => (
        <section key={group.year} className="blog-timeline-year">
          <div className="blog-timeline-year-label">{group.year}</div>
          {group.posts.map(({month, item}) => {
            const active = pathname === item.permalink;
            return (
              <Link
                key={item.permalink}
                to={item.permalink}
                className={`blog-timeline-item${active ? ' active' : ''}`}
                aria-current={active ? 'page' : undefined}>
                <span className="blog-timeline-month">{month}</span>
                <span className="blog-timeline-title">{item.title}</span>
              </Link>
            );
          })}
        </section>
      ))}
      </div>
    </nav>
  );
}
