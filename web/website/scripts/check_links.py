#!/usr/bin/env python3
"""AMUX-51 CI guard: internal-link + sitemap consistency for the website.

Fails (exit 1) when:
  1. any internal link (markdown `](...)`, `to=`/`href=` attrs, docusaurus
     config) targets a slashless path — the site sets trailingSlash:true,
     so slashless links generate a 301 on every click and pollute Search
     Console with "Page with redirect";
  2. any internal link target is absent from the built sitemap.xml
     (broken link -> future 404 report).

Run from web/website AFTER `npm run build` (needs build/sitemap.xml):
  python3 scripts/check_links.py
"""
from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build"

LINK_PATTERNS = [
    re.compile(r'(\]\()(?:' + ROOT.name + r')?(/[^)#\s]+?)(?:#[^)\s]*)?\)'),
    re.compile(r'((?:to|href)=["\'])(/[^"\'#]+?)(?:#[^"\']*)?["\']'),
]
# targets that intentionally live outside the sitemap (assets, demo apps)
EXCLUDE_PREFIXES = ("/img/", "/wasm-app/", "/cql-cleanroom/", "/viewing-room-app/",
                    "/bulk-publisher-app/", "/cql-clinic-app/", "/coi-",
                    "/robots.txt", "/llms.txt", "/sitemap", "/favicon", "/404")


def main() -> int:
    sitemap_urls = set()
    sitemap = BUILD / "sitemap.xml"
    if not sitemap.exists():
        print("FAIL: build/sitemap.xml missing — run `npm run build` first")
        return 1
    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    for loc in ET.parse(sitemap).getroot().findall("s:url/s:loc", ns):
        u = loc.text or ""
        u = u.split("fhir4ds.com", 1)[-1]  # strip scheme+host
        sitemap_urls.add(u)

    files = [p for base in ("docs", "src", "blog") for p in
             (ROOT / base).rglob("*") if p.suffix in (".md", ".mdx",
                                                      ".ts", ".tsx", ".js")]
    files += [ROOT / "docusaurus.config.ts", ROOT / "sidebars.ts"]

    slashless, broken = [], []
    seen: set[tuple[str, str]] = set()
    for p in files:
        if not p.exists() or "node_modules" in str(p):
            continue
        text = p.read_text(errors="ignore")
        for pat in LINK_PATTERNS:
            for m in pat.finditer(text):
                url = m.group(2) if m.lastindex and m.lastindex >= 2 else None
                if not url or not url.startswith("/"):
                    continue
                if any(url.startswith(x) for x in EXCLUDE_PREFIXES):
                    continue
                if "." in url.rsplit("/", 1)[-1]:
                    continue  # file asset
                if (str(p), url) in seen:
                    continue
                seen.add((str(p), url))
                # docusaurus.config.ts `to:` values are ROUTE paths that
                # Docusaurus normalizes under trailingSlash:true — only
                # markdown/HTML links (rendered verbatim) must carry the
                # slash. Existence is checked for both.
                is_config = p.name == "docusaurus.config.ts"
                if not url.endswith("/") and not is_config:
                    slashless.append((str(p.relative_to(ROOT)), url))
                elif (url if url.endswith("/") else url + "/") \
                        not in sitemap_urls:
                    broken.append((str(p.relative_to(ROOT)), url))

    rc = 0
    if slashless:
        rc = 1
        print(f"FAIL: {len(slashless)} slashless internal link(s) "
              "(site uses trailingSlash:true — add the slash):")
        for f, u in slashless:
            print(f"  {f}: {u}")
    if broken:
        rc = 1
        print(f"FAIL: {len(broken)} internal link(s) not in built sitemap "
              "(broken targets):")
        for f, u in broken:
            print(f"  {f}: {u}")
    if rc == 0:
        print(f"OK: all internal links slashed and present in sitemap "
              f"({len(seen)} distinct targets checked)")
    return rc


if __name__ == "__main__":
    sys.exit(main())
