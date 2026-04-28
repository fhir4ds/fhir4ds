import {SidebarsConfig} from '@docusaurus/plugin-content-docs';

const sidebars: SidebarsConfig = {
  mainSidebar: [
    {
      type: 'category',
      label: 'Getting Started',
      link: {type: 'doc', id: 'getting-started/installation'},
      items: [
        'getting-started/quickstart',
        'getting-started/architecture',
        'getting-started/benchmarking',
        'getting-started/whitepaper',
        'getting-started/releases',
        'getting-started/licensing',
      ],
    },
    {
      type: 'category',
      label: 'User Guide',
      link: {type: 'doc', id: 'user-guide/engine'},
      items: [
        'user-guide/engine',
        {
          type: 'category',
          label: 'Data Sources',
          link: {type: 'doc', id: 'user-guide/data-sources'},
          items: [
            'user-guide/sources/filesystem',
            'user-guide/sources/relational',
            'user-guide/sources/csv',
            'user-guide/sources/existing',
          ],
        },
        {
          type: 'category',
          label: 'Data Extraction',
          items: [
            {
              type: 'doc',
              id: 'user-guide/extraction/fhirpath',
              label: 'FHIRPath',
            },
            'user-guide/extraction/duckdb',
          ],
        },
        {
          type: 'category',
          label: 'Flattening & Modeling',
          items: ['user-guide/modeling/viewdef'],
        },
        {
          type: 'category',
          label: 'Clinical Logic',
          items: ['user-guide/analytics/cql'],
        },
        {
          type: 'category',
          label: 'Quality Measurement',
          items: ['user-guide/quality/dqm'],
        },
      ],
    },
    {
      type: 'category',
      label: 'Integrations',
      items: [
        {
          type: 'doc',
          id: 'integrations/wasm-engine',
          label: 'WASM Engine',
        },
        {
          type: 'doc',
          id: 'integrations/web-component',
          label: 'Web Components',
        },
      ],
    },
    {
      type: 'category',
      label: 'API Reference',
      link: {type: 'doc', id: 'api-reference/fhir4ds'},
      items: [
        {
          type: 'category',
          label: 'fhir4ds',
          link: {type: 'doc', id: 'api-reference/fhir4ds'},
          collapsed: false,
          items: [
            {
              type: 'doc',
              id: 'api-reference/fhirpath/fhirpath',
              label: 'fhirpath',
            },
            {
              type: 'doc',
              id: 'api-reference/cql/cql',
              label: 'cql',
            },
            {
              type: 'doc',
              id: 'api-reference/viewdef/viewdef',
              label: 'viewdef',
            },
            {
              type: 'doc',
              id: 'api-reference/dqm/dqm',
              label: 'dqm',
            },
            {
              type: 'doc',
              id: 'api-reference/sources/sources',
              label: 'sources',
            },
          ],
        },
      ],
    },
    {
      type: 'category',
      label: 'Examples',
      items: [
        {
          type: 'doc',
          id: 'examples/cql-playground',
          label: 'CQL Playground',
        },
        {
          type: 'doc',
          id: 'examples/cms-measures',
          label: 'Quality Measures',
        },
        {
          type: 'doc',
          id: 'examples/sdc-playground',
          label: 'SDC Forms',
        },
        {
          type: 'doc',
          id: 'examples/smart-demo',
          label: 'SMART on FHIR',
        },
        {
          type: 'doc',
          id: 'examples/notebooks',
          label: 'Notebooks',
        },
      ],
    },
  ],
};

export default sidebars;
