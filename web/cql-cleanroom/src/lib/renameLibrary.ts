/**
 * WORKBENCH_REORG phase 3 — library rename.
 *
 * A library's CQL name appears in its own `library <Name>` header and in
 * every sibling `include <Name>` reference. Renaming rewrites both,
 * otherwise translation breaks. The new name must be a valid CQL
 * identifier; measure↔library links are by id, so they are unaffected.
 */

const IDENT_RE = /^[A-Za-z_][A-Za-z0-9_]*$/;

export function isValidLibraryName(name: string): boolean {
  return IDENT_RE.test(name);
}

/** Rewrite `library Old` (the header) in the renamed library's text. */
function renameHeader(text: string, from: string, to: string): string {
  return text.replace(
    new RegExp(`^(\\s*library\\s+)${identPattern(from)}`, "m"),
    (_m, head: string) => `${head}${to}`,
  );
}

/** Rewrite `include Old` references in OTHER libraries' texts. */
function renameIncludes(text: string, from: string, to: string): string {
  return text.replace(
    new RegExp(`^(\\s*include\\s+)${identPattern(from)}`, "m"),
    (_m, head: string) => `${head}${to}`,
  );
}

/** Identifier, not followed by a name character (avoids prefix hits). */
function identPattern(name: string): string {
  const esc = name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return `${esc}(?![A-Za-z0-9_])`;
}

export interface RenameLibrary {
  id: string;
  name: string;
  text: string;
}

/**
 * Rename library `id` to `to`. Returns updated libraries, or null when
 * the id is unknown or the name is invalid. Header + includes rewritten;
 * the WorkspaceLibrary.name mirror is updated to match.
 */
export function renameLibrary(
  libraries: RenameLibrary[],
  id: string,
  to: string,
): RenameLibrary[] | null {
  if (!isValidLibraryName(to)) return null;
  const target = libraries.find((l) => l.id === id);
  if (!target) return null;
  const from = target.name;
  if (from === to) return libraries;
  return libraries.map((l) => {
    if (l.id === id) {
      return { ...l, name: to, text: renameHeader(l.text, from, to) };
    }
    return { ...l, text: renameIncludes(l.text, from, to) };
  });
}
