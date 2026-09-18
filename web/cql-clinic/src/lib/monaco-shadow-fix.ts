/**
 * fixMonacoInputArea — Monaco editor `onMount` handler for Shadow DOM.
 *
 * Monaco < 0.52 uses `.inputarea` for its hidden keyboard-capture textarea.
 * Monaco >= 0.52 renamed it to `.ime-text-area`.
 * Both are inside `.overflow-guard > .monaco-editor`.
 *
 * Problem: Monaco injects its CSS into document.head, not the shadow root, so
 * the textarea gets browser-default visible styling (gray box, top-left corner).
 *
 * Solution: use inline !important styles + a MutationObserver to keep the
 * element off-screen even when Monaco's FastDomNode resets inline styles.
 */

import type * as MonacoEditor from "monaco-editor";

// Covers both Monaco < 0.52 (.inputarea) and >= 0.52 (.ime-text-area)
const INPUT_AREA_SELECTOR = ".inputarea, .ime-text-area";

/**
 * Called on every Monaco editor mount (pass directly to `onMount` prop).
 * Sets up imperative style fixes for the hidden keyboard-capture textarea.
 */
export function fixMonacoInputArea(
  editor: MonacoEditor.editor.IStandaloneCodeEditor,
): void {
  const domNode = editor.getDomNode();
  if (!domNode) return;

  const applyFix = () => {
    const tas = domNode.querySelectorAll<HTMLElement>(INPUT_AREA_SELECTOR);
    tas.forEach((ta) => {
      // If our !important left is already applied, skip (prevents infinite loop)
      if (ta.style.getPropertyPriority("left") === "important") return;

      ta.style.setProperty("position", "absolute", "important");
      ta.style.setProperty("left", "-10000px", "important");
      ta.style.setProperty("top", "0", "important");
      ta.style.setProperty("width", "1px", "important");
      ta.style.setProperty("height", "1px", "important");
      ta.style.setProperty("min-width", "0", "important");
      ta.style.setProperty("min-height", "0", "important");
      ta.style.setProperty("opacity", "0", "important");
      ta.style.setProperty("color", "transparent", "important");
      ta.style.setProperty("background-color", "transparent", "important");
      ta.style.setProperty("border", "none", "important");
      ta.style.setProperty("outline", "none", "important");
      ta.style.setProperty("resize", "none", "important");
      ta.style.setProperty("overflow", "hidden", "important");
      ta.style.setProperty("z-index", "-10", "important");
    });
  };

  // Run immediately — textarea may already exist at mount time
  applyFix();

  // Watch for style changes (FastDomNode.setLeft etc.) AND new child elements
  // (in case the textarea is created asynchronously after mount)
  const observer = new MutationObserver(applyFix);
  observer.observe(domNode, {
    subtree: true,
    attributes: true,
    attributeFilter: ["style"],
    childList: true,  // catches late textarea creation
  });

  editor.onDidDispose(() => observer.disconnect());
}

/**
 * startMonacoStylePorting — copy Monaco's runtime-injected styles into the
 * Shadow DOM root.
 *
 * Monaco (loaded at runtime by @monaco-editor/react) injects its CSS as
 * <style> tags into document.head. Those rules do not cross the shadow
 * boundary, so inside the web component the editor runs essentially
 * unstyled: the plain Editor limps along (see fixMonacoInputArea), but the
 * DiffEditor renders an unclickable overlay. Port every head style that
 * looks like Monaco's (selectors mention .monaco-/​.codicon-) into the
 * shadow root, and keep watching head for late injections.
 *
 * Returns a stop function.
 */
export function startMonacoStylePorting(shadow: ShadowRoot): () => void {
  const isMonacoStyle = (s: HTMLStyleElement) =>
    /\.monaco-|\.codicon-/i.test(s.textContent ?? "");

  const portOne = (source: HTMLStyleElement) => {
    if (source.dataset.clinicPorted) return;
    source.dataset.clinicPorted = "1";
    const clone = document.createElement("style");
    clone.textContent = source.textContent;
    clone.setAttribute("data-clinic-monaco-port", "");
    shadow.appendChild(clone);
  };

  const sweep = () => {
    document.head
      .querySelectorAll<HTMLStyleElement>("style:not([data-clinic-monaco-port])")
      .forEach((s) => {
        if (isMonacoStyle(s)) portOne(s);
      });
  };

  sweep();
  const observer = new MutationObserver(() => sweep());
  observer.observe(document.head, { childList: true, subtree: false });

  return () => observer.disconnect();
}
