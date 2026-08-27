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

  organizationName: 'fhir4ds',
  projectName: 'fhir4ds',

  onBrokenLinks: 'warn',
  markdown: {
    mermaid: true,
  },

  i18n: {
    defaultLocale: 'en',
    locales: ['en'],
  },

  headTags: [
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
    image: 'img/fhir4ds-social-card.png',
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
          title: 'Product',
          items: [
            {label: 'Live Demo', to: '/docs/examples/cql-playground'},
            {label: 'Documentation', to: '/docs/user-guide/index'},
            {label: 'Whitepaper', to: '/docs/getting-started/whitepaper'},
          ],
        },
        {
          title: 'Standards',
          items: [
            {label: 'FHIRPath Spec', href: 'https://hl7.org/fhirpath/'},
            {label: 'CQL Spec', href: 'https://cql.hl7.org/'},
            {label: 'SQL-on-FHIR v2', href: 'https://github.com/FHIR/sql-on-fhir-v2'},
          ],
        },
        {
          title: 'Licensing & Support',
          items: [
            {label: 'Dual Licensing', to: '/docs/getting-started/licensing'},
            {label: 'Commercial Inquiries', href: 'mailto:contact@fhir4ds.com'},
          ],
        },
        {
          title: 'Resources',
          items: [
            {label: 'GitHub', href: 'https://github.com/fhir4ds/fhir4ds'},
            {label: 'API Reference', to: '/docs/api-reference/fhir4ds'},
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
