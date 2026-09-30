/**
 * Dev-only COOP/COEP headers plugin.
 *
 * DuckDB-WASM (embedded demos: cql-cleanroom, wasm-app) needs
 * SharedArrayBuffer, which requires cross-origin isolation. In
 * production the coi-serviceworker injects the headers on GH Pages.
 * In dev the SW is intentionally not registered (a cached SW poisons
 * chunk fetches after every rebuild), so the dev server itself must
 * send COOP/COEP.
 *
 * Mechanism: Docusaurus (webpack bundler) builds the dev server config
 * in @docusaurus/core/lib/commands/start/webpack.js by merging the
 * client webpack config's `devServer` object into the defaults
 * (webpack-merge at :135-137). Setting `config.devServer.headers` from
 * the classic `configureWebpack` plugin lifecycle therefore lands the
 * headers on every dev-server response. No-op for SSR configs and in
 * production builds (`headers` only affects the dev server).
 */
export default function coiDevHeaders(context, _options) {
  return {
    name: 'coi-dev-headers',
    configureWebpack(config, isServer) {
      if (isServer) return;
      const devServer = config.devServer || {};
      config.devServer = {
        ...devServer,
        headers: {
          ...(devServer.headers || {}),
          'Cross-Origin-Opener-Policy': 'same-origin',
          'Cross-Origin-Embedder-Policy': 'require-corp',
          // Allow cross-origin subresources (the demos load none today,
          // but this keeps COEP from breaking future embeds).
          'Cross-Origin-Resource-Policy': 'cross-origin',
        },
      };
      return {
        devServer: config.devServer,
      };
    },
  };
}
