#!/usr/bin/env python3
"""Search the arXiv API and return structured results.

The arXiv API is generous (soft limit: 1 request per 3 seconds per IP).
Results come back as Atom XML; this script parses them into JSON so the
LLM never has to touch the raw XML.

Usage:
    python arxiv_search.py "query terms" [--max 20] [--category cs.LG] \
        [--sort-by relevance|lastUpdatedDate|submittedDate] \
        [--from YYYY-MM-DD] [--to YYYY-MM-DD]

Output: JSON array of {id, title, authors, abstract, categories,
published, updated, pdf_url, abs_url, primary_category} on stdout.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime

ATOM_NS = {
    "a": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
    "os": "http://a9.com/-/spec/opensearch/1.1/",
}
USER_AGENT = "ai-skill-arxiv-search/1.0"
API_URL = "http://export.arxiv.org/api/query"


def build_query(
    terms: str | None,
    category: str | None,
    date_from: str | None,
    date_to: str | None,
) -> str:
    """Build the arXiv search_query string. Spaces become '+' per arXiv syntax."""
    parts: list[str] = []
    if terms:
        # Wrap multi-word terms in quotes for phrase matching; single terms as-is.
        cleaned = terms.strip()
        if " " in cleaned and not (cleaned.startswith('"') and cleaned.endswith('"')):
            # Split into word AND-clauses rather than forcing phrase match
            words = [w for w in cleaned.split() if w]
            parts.append("+AND+".join(f"all:{w}" for w in words))
        else:
            parts.append(f"all:{cleaned}")
    if category:
        parts.append(f"cat:{category}")
    if date_from or date_to:
        lo = _date_stamp(date_from, start=True) if date_from else "197001010000"
        hi = _date_stamp(date_to, start=False) if date_to else "999912312359"
        parts.append(f"submittedDate:[{lo}+TO+{hi}]")
    return "+AND+".join(parts) if parts else "all:*"


def _date_stamp(date_str: str, start: bool) -> str:
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return dt.strftime("%Y%m%d") + ("0000" if start else "2359")


def fetch(query: str, max_results: int, sort_by: str) -> str:
    # `query` already uses '+' as word/clause separator per arXiv syntax.
    # Everything else gets standard urlencoding.
    rest = urllib.parse.urlencode({
        "start": "0",
        "max_results": str(max_results),
        "sortBy": sort_by,
        "sortOrder": "descending",
    })
    url = f"{API_URL}?search_query={query}&{rest}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def parse(xml_text: str) -> list[dict]:
    root = ET.fromstring(xml_text)
    results = []
    for entry in root.findall("a:entry", ATOM_NS):
        abs_url = _text(entry, "a:id") or ""
        arxiv_id = abs_url.rsplit("/abs/", 1)[-1] if "/abs/" in abs_url else abs_url
        pdf_url = ""
        for link in entry.findall("a:link", ATOM_NS):
            if link.get("title") == "pdf":
                pdf_url = link.get("href", "")
                break
        primary = entry.find("arxiv:primary_category", ATOM_NS)
        results.append({
            "id": arxiv_id,
            "title": _clean(_text(entry, "a:title")),
            "authors": [
                _text(a, "a:name") or ""
                for a in entry.findall("a:author", ATOM_NS)
            ],
            "abstract": _clean(_text(entry, "a:summary")),
            "categories": [c.get("term", "") for c in entry.findall("a:category", ATOM_NS)],
            "primary_category": primary.get("term") if primary is not None else None,
            "published": _text(entry, "a:published"),
            "updated": _text(entry, "a:updated"),
            "abs_url": abs_url,
            "pdf_url": pdf_url,
            "doi": _text(entry, "arxiv:doi"),
            "journal_ref": _text(entry, "arxiv:journal_ref"),
            "comment": _clean(_text(entry, "arxiv:comment") or ""),
        })
    return results


def _text(parent, path: str) -> str | None:
    el = parent.find(path, ATOM_NS)
    return el.text if el is not None and el.text else None


def _clean(s: str | None) -> str:
    if not s:
        return ""
    return " ".join(s.split())


def main() -> int:
    parser = argparse.ArgumentParser(description="Search arXiv via the public API.")
    parser.add_argument("query", nargs="?", default=None, help="Free-text search terms")
    parser.add_argument("--max", type=int, default=20, help="Max results (default 20)")
    parser.add_argument("--category", help="arXiv category (e.g. cs.LG, stat.ML)")
    parser.add_argument(
        "--sort-by",
        choices=["relevance", "lastUpdatedDate", "submittedDate"],
        default="relevance",
    )
    parser.add_argument("--from", dest="date_from", help="Earliest submission date (YYYY-MM-DD)")
    parser.add_argument("--to", dest="date_to", help="Latest submission date (YYYY-MM-DD)")
    args = parser.parse_args()

    if not args.query and not args.category:
        parser.error("provide query terms and/or --category")

    try:
        query = build_query(args.query, args.category, args.date_from, args.date_to)
        xml_text = fetch(query, args.max, args.sort_by)
        results = parse(xml_text)
    except urllib.error.HTTPError as e:
        print(f"error: arXiv API returned HTTP {e.code}", file=sys.stderr)
        return 4
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        print(f"error: network error: {e}", file=sys.stderr)
        return 4
    except ET.ParseError as e:
        print(f"error: malformed arXiv response: {e}", file=sys.stderr)
        return 5

    print(json.dumps({"query": query, "count": len(results), "results": results}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
