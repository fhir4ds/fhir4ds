/**
 * Monaco setup — locally bundled editor (no CDN loader), so its CSS is
 * part of the app stylesheet the web-component build inlines into the
 * shadow root. Cloned from web/cql-cleanroom.
 *
 * NDJSON doctrine: the resources editor holds one JSON document per LINE
 * — the built-in single-root JSON validator would flag every line past
 * the first ("Unexpected token" at each newline). Disable JSON schema
 * validation globally (the VD editor's syntax coloring is unaffected).
 */

import { loader } from "@monaco-editor/react";
import * as monaco from "monaco-editor/esm/vs/editor/editor.api";
import "monaco-editor/esm/vs/editor/editor.all.js";
// JSON language contribution: registers monaco.languages.json, required
// for the jsonDefaults call below (editor.all alone omits language services).
import "monaco-editor/esm/vs/language/json/monaco.contribution";
import EditorWorker from "monaco-editor/esm/vs/editor/editor.worker?worker";
import JsonWorker from "monaco-editor/esm/vs/language/json/json.worker?worker";

(self as any).MonacoEnvironment = {
  getWorker: (_workerId: string, label: string) =>
    label === "json" ? new JsonWorker() : new EditorWorker(),
};

loader.config({ monaco });

// Muse gate rec: JSON validation off (NDJSON is not a single JSON root).
monaco.languages.json.jsonDefaults.setDiagnosticsOptions({
  validate: false,
  allowComments: false,
  schemas: [],
});

export default monaco;
