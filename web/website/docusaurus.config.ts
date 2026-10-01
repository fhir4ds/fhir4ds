import {themes as prismThemes} from 'prism-react-renderer';
import type {Config} from '@docusaurus/types';
import type * as Preset from '@docusaurus/preset-classic';

const baseUrl = process.env.BASE_URL || '/';

const config: Config = {
  title: 'FHIR for Data Science',
  tagline: 'SQL-Native CQL Evaluation — Production-Accurate, In-Browser, Auditable',
  favicon: 'img/icon.svg',

  future: {
    v4: true,
  },

  url: 'https://fhir4ds.com',
  baseUrl: baseUrl,

  // GH Pages serves directories with trailing slashes and 301s the
  // non-slash form; emitting slash URLs in sitemap/canonicals/links
  // avoids every page registering as "Page with redirect" in Search
  // Console. Dev BASE_URL=/ builds are unaffected.
  trailingSlash: true,

  organizationName: 'fhir4ds',
  projectName: 'fhir4ds',

  onBrokenLinks: 'warn',

  // Search Console 404 remediation: meta-refresh client redirects for
  // docs routes that were renamed or deleted (GH Pages artifact
  // deploys cannot serve server-side redirect files).
  plugins: [
    // Dev-only COOP/COEP headers so DuckDB-WASM demos are cross-origin
    // isolated on localhost (production uses the coi-serviceworker).
    './coi-dev-headers-plugin.js',
    [
      '@docusaurus/plugin-client-redirects',
      {
        redirects: [
          { from: '/docs/user-guide/ci', to: '/docs/user-guide/interfaces/cli'},
          { from: '/docs/user-guide/data-ingestion', to: '/docs/user-guide/data-sources' },
          { from: '/docs/user-guide/quality/hapi-materialization', to: '/docs/integrations/hapi-fhir' },
          { from: '/docs/user-guide/extraction/duckdb', to: '/docs/user-guide/duckdb' },
          { from: '/docs/user-guide/quality/dqm-recipes', to: '/docs/examples/dqm-recipes' },
          { from: '/docs/user-guide/cli', to: '/docs/user-guide/interfaces/cli' },
        ],
      },
    ],
  ],
  markdown: {
    mermaid: true,
  },

  i18n: {
    defaultLocale: 'en',
    locales: ['en'],
  },

  headTags: [
    // Suppress Monaco's benign "ResizeObserver loop" errors in CAPTURE phase,
    // before webpack-dev-server's overlay listener can see them.
    {
      tagName: 'script',
      attributes: {},
      innerHTML: `
        (function () {
          window.addEventListener(
            'error',
            function (e) {
              if (e && e.message && e.message.indexOf('ResizeObserver loop') !== -1) {
                e.stopImmediatePropagation();
                e.preventDefault();
              }
            },
            { capture: true }
          );
        })();
      `,
    },
    // COI service worker registration for SharedArrayBuffer (DuckDB-WASM on GitHub Pages).
    // The document must be loaded through the service worker before
    // crossOriginIsolated becomes true, so reload once after activation.
    {
      tagName: 'script',
      attributes: {},
      innerHTML: `
        (function () {
          if (typeof window === 'undefined' || !('serviceWorker' in navigator)) {
            return;
          }

          // Dev guard: the COI service worker exists to add COOP/COEP headers
          // on GitHub Pages. In dev the server config already serves headers
          // where needed, and a cached SW poisons every chunk fetch after a
          // rebuild (chunk hashes change per build). Register in prod only.
          var isDev =
            window.location.hostname === 'localhost' ||
            window.location.hostname === '127.0.0.1' ||
            window.location.port === '3000';
          if (isDev) {
            return;
          }

          var reloadKey = 'fhir4ds-coi-reload-attempted';

          if (window.crossOriginIsolated) {
            sessionStorage.removeItem(reloadKey);
            return;
          }

          function reloadOnce() {
            if (sessionStorage.getItem(reloadKey) === '1') {
              return;
            }
            sessionStorage.setItem(reloadKey, '1');
            window.location.reload();
          }

          navigator.serviceWorker
            .register('${baseUrl}coi-serviceworker.js')
            .then(function (registration) {
              navigator.serviceWorker.addEventListener('controllerchange', reloadOnce, {
                once: true,
              });

              if (navigator.serviceWorker.controller || registration.active) {
                navigator.serviceWorker.ready.then(reloadOnce);
              }
            })
            .catch(function (error) {
              console.error('[FHIR4DS] COI service worker registration failed:', error);
            });
        })();
      `,
    },
  ],

  themes: ['@docusaurus/theme-mermaid'],

  presets: [
    [
      'classic',
      {
        docs: {
          sidebarPath: './sidebars.ts',
          editUrl: 'https://github.com/fhir4ds/fhir4ds/edit/main/web/website/',
        },
        blog: false,
        theme: {
          customCss: './src/css/custom.css',
        },
      } satisfies Preset.Options,
    ],
  ],

  themeConfig: {
    image: 'img/docusaurus-social-card.jpg',
    metadata: [
      {name: 'description', content: 'High-performance FHIR analytics on DuckDB: CQL quality measures, FHIRPath queries, and SQL-on-FHIR v2 ViewDefinitions translated to SQL — in Python or fully in the browser via WebAssembly.'},
      {name: 'keywords', content: 'FHIR, FHIR analytics, CQL, FHIRPath, SQL-on-FHIR, ViewDefinition, DuckDB, quality measures, eCQM, healthcare data science'},
    ],
    colorMode: {
      defaultMode: 'dark',
      disableSwitch: true,
      respectPrefersColorScheme: false,
    },
    mermaid: {
      theme: {light: 'base', dark: 'base'},
    },
    navbar: {
      title: 'FHIR4DS',
      logo: {
        alt: 'FHIR4DS Logo',
        src: 'img/icon.svg',
        srcDark: 'img/icon.svg',
      },
      items: [
        {to: '/docs/getting-started/installation', label: 'Getting Started', position: 'left'},
        {to: '/docs/user-guide/index', label: 'User Guide', position: 'left'},
        {to: '/docs/integrations/wasm-engine', label: 'Integrations', position: 'left'},
        {to: '/docs/api-reference/fhir4ds', label: 'API', position: 'left'},
        {to: '/docs/examples/dqm-recipes', label: 'Examples', position: 'left'},
        {
          href: 'https://github.com/fhir4ds/fhir4ds',
          position: 'right',
          className: 'navbar-github-link',
          'aria-label': 'GitHub repository',
        },
      ],
    },
    footer: {
      style: 'dark',
      links: [
        {
          title: 'Learn More',
          items: [
            {label: 'Live Demo', to: '/docs/examples/cql-playground'},
            {label: 'Documentation', to: '/docs/user-guide/index'},
            {label: 'Whitepaper', to: '/docs/getting-started/whitepaper'},
          ],
        },
        {
          title: 'Standards',
          items: [
            {label: 'FHIRPath', href: 'https://hl7.org/fhirpath/'},
            {label: 'CQL', href: 'https://cql.hl7.org/'},
            {label: 'SQL-on-FHIR v2', href: 'https://github.com/FHIR/sql-on-fhir-v2'},
          ],
        },
        {
          title: 'Licensing & Support',
          items: [
            {label: 'Dual Licensing', to: '/docs/getting-started/licensing'},
            {label: 'Commercial Inquiries', href: 'mailto:contact@fhir4ds.com'},
            {label: 'GitHub', href: 'https://github.com/fhir4ds/fhir4ds'},
          ],
        },
        {
          title: 'Projects',
          items: [
            {label: 'fhir4ds', href: 'https://fhir4ds.com/'},
            {label: 'medterm4ds', href: 'https://terminology.fhir4ds.com/'},
          ],
        },
      ],
      copyright: `Copyright © ${new Date().getFullYear()} FHIR4DS. Built with Docusaurus.`,
    },
    prism: {
      theme: prismThemes.oneDark,
      darkTheme: prismThemes.oneDark,
      additionalLanguages: ['python', 'sql', 'bash'],
    },
  } satisfies Preset.ThemeConfig,
};

export default config;
