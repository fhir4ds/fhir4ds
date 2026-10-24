/**
 * Monaco runtime-injected head styles never cross the shadow boundary —
 * port them into the shadow root as they appear. Cloned from
 * web/cql-cleanroom (which cloned it from cql-clinic).
 */

const MONACO_STYLE_ANCHORS = [
  "monaco-colors",
  "monaco-tokens",
  ".monaco-editor",
];

function isMonacoStyle(style: HTMLStyleElement | HTMLLinkElement): boolean {
  if (style.tagName === "LINK") {
    const href = (style as HTMLLinkElement).getAttribute("href") ?? "";
    return /monaco|codicon/i.test(href);
  }
  const el = style as HTMLStyleElement;
  const id = el.id ?? "";
  if (MONACO_STYLE_ANCHORS.some((a) => id.includes(a))) return true;
  return /monaco-editor|codicon|\.monaco-/.test(el.textContent ?? "");
}

export function startMonacoStylePorting(shadow: ShadowRoot): () => void {
  const ported = new Set<Node>();

  function portNode(node: Node) {
    if (ported.has(node)) return;
    if (!(node instanceof HTMLStyleElement || node instanceof HTMLLinkElement)) return;
    if (!isMonacoStyle(node)) return;
    const clone = node.cloneNode(true) as HTMLStyleElement;
    clone.setAttribute("data-monaco-ported", "");
    shadow.appendChild(clone);
    ported.add(node);
  }

  function sweep() {
    const head = document.head;
    if (!head) return;
    for (const node of Array.from(head.children)) {
      portNode(node);
    }
  }

  const observer = new MutationObserver(() => sweep());
  observer.observe(document.head, { childList: true, subtree: true });
  sweep();

  return () => observer.disconnect();
}
