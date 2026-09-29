/**
 * Monaco setup — use a locally bundled editor instead of the CDN copy.
 *
 * Why: @monaco-editor/react's default loader fetches monaco from jsdelivr at
 * runtime and injects its CSS into document.head. Inside the web component
 * that CSS never crosses the shadow boundary (part of it also lands in
 * constructed stylesheets that tag-sweeping can't see), leaving the diff
 * editor unstyled — no gutter, no red/green bands, stray overlay boxes.
 * Bundling monaco here makes its CSS part of the app's own stylesheet,
 * which the WC build inlines into the shadow root.
 */

import { loader } from "@monaco-editor/react";
import * as monaco from "monaco-editor/esm/vs/editor/editor.api";
// editor.api is the bare core (no suggest/hover/find widgets at all) —
// editor.all registers the contributions on the same API singleton.
// The visual editor needs suggest + hover; pull everything.
import "monaco-editor/esm/vs/editor/editor.all.js";
import EditorWorker from "monaco-editor/esm/vs/editor/editor.worker?worker";

(self as any).MonacoEnvironment = {
  getWorker: () => new EditorWorker(),
};

loader.config({ monaco });

export default monaco;
