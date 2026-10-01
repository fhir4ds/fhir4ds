/**
 * Client-side dependency graph for a measure's primary library (6f):
 * the include closure (mirrors the engine's `urn:cleanroom:lib:` includes)
 * plus the valueset declarations declared across that closure.
 */

export interface ValuesetDecl {
  name: string;
  url: string;
}

export interface LibraryClosure {
  /** BFS order, primary library first. */
  libraryNames: string[];
  valuesetDecls: ValuesetDecl[];
}

const INCLUDE_RE = /include\s+([A-Za-z][A-Za-z0-9_]*)/g;
const VALUESET_RE = /valueset\s+"([^"]+)"\s*[=:]\s*'([^']+)'/g;

export function libraryClosure(
  libraries: Array<{ name: string; text: string }>,
  mainName: string,
): LibraryClosure {
  const byName = new Map(libraries.map((l) => [l.name, l]));
  const libraryNames: string[] = [];
  const seen = new Set<string>();
  const queue = [mainName];
  while (queue.length) {
    const name = queue.shift()!;
    if (seen.has(name)) continue;
    const lib = byName.get(name);
    if (!lib) continue; // missing dependency — the engine reports it
    seen.add(name);
    libraryNames.push(name);
    for (const m of lib.text.matchAll(INCLUDE_RE)) {
      if (byName.has(m[1]) && !seen.has(m[1])) queue.push(m[1]);
    }
  }
  const valuesetDecls: ValuesetDecl[] = [];
  const urls = new Set<string>();
  for (const name of libraryNames) {
    for (const m of byName.get(name)!.text.matchAll(VALUESET_RE)) {
      if (!urls.has(m[2])) {
        urls.add(m[2]);
        valuesetDecls.push({ name: m[1], url: m[2] });
      }
    }
  }
  return { libraryNames, valuesetDecls };
}
