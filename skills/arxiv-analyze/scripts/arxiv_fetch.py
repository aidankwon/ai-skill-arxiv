#!/usr/bin/env python3
"""Fetch arXiv papers via tiered fallback: markdown -> HTML -> ar5iv -> PDF.

Handles deterministic rate limiting for arxiv2md (30 req/min; throttled to 28
with a safety margin). Rate limit state persists in arxiv2md_ratelimit.json
alongside this script. Stale entries are pruned on every call so the file
stays bounded at roughly RATE_LIMIT_MAX entries.

Exit codes:
    0 = success (content on stdout, tier label on stderr)
    1 = all tiers failed
    2 = forced tier was rate-limited or unavailable (with --tier)
    3 = invalid arXiv ID format
    4 = network/fetch error on metadata-only path

Usage:
    python arxiv_fetch.py <arxiv_id>                    # auto-tier fallback
    python arxiv_fetch.py <arxiv_id> --tier md|html|ar5iv|pdf
    python arxiv_fetch.py <arxiv_id> --metadata-only    # arXiv API metadata
    python arxiv_fetch.py --ratelimit-status            # show current counter
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
RATELIMIT_FILE = SCRIPT_DIR / "arxiv2md_ratelimit.json"
RATE_LIMIT_MAX = 28          # arxiv2md allows 30/min; 28 = safety margin
RATE_LIMIT_WINDOW = 60       # seconds
HTTP_TIMEOUT = 60
USER_AGENT = "ai-skill-arxiv-fetch/1.0"

# Matches both new-style (YYMM.NNNNN[vN]) and old-style (archive/YYMMNNN[vN]) IDs.
ARXIV_ID_RE = re.compile(
    r"^(?:\d{4}\.\d{4,5}(v\d+)?|[a-z\-]+(?:\.[A-Z]{2})?/\d{7}(v\d+)?)$"
)


# --------------------------------------------------------------------------- #
# ID normalisation
# --------------------------------------------------------------------------- #

def normalize_arxiv_id(raw: str) -> str:
    """Extract a canonical arXiv ID from a URL or raw string.

    Raises ValueError on anything that doesn't look like an arXiv ID.
    """
    s = raw.strip()
    m = re.search(r"arxiv\.org/(?:abs|pdf|html)/([^\s?#]+)", s)
    if m:
        s = m.group(1)
    if s.endswith(".pdf"):
        s = s[:-4]
    s = s.rstrip("/")
    if not ARXIV_ID_RE.match(s):
        raise ValueError(f"not a valid arXiv ID: {raw!r}")
    return s


# --------------------------------------------------------------------------- #
# Rate limit persistence (deterministic)
# --------------------------------------------------------------------------- #

def _load_timestamps() -> list[float]:
    """Load the timestamp list. Missing/corrupt files are treated as empty."""
    if not RATELIMIT_FILE.exists():
        return []
    try:
        data = json.loads(RATELIMIT_FILE.read_text())
        ts = data.get("requests", [])
        return [float(t) for t in ts if isinstance(t, (int, float))]
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        return []


def _prune(timestamps: list[float], now: float) -> list[float]:
    """Drop entries outside the rate-limit window."""
    return [t for t in timestamps if now - t < RATE_LIMIT_WINDOW]


def _atomic_write(timestamps: list[float]) -> None:
    """Atomically persist timestamps to disk."""
    fd, tmp_path = tempfile.mkstemp(
        dir=str(SCRIPT_DIR), prefix=".ratelimit.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w") as fh:
            json.dump({"requests": timestamps}, fh)
        os.replace(tmp_path, RATELIMIT_FILE)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def ratelimit_check_and_reserve() -> tuple[bool, int]:
    """Prune stale entries; reserve a slot if available.

    Returns (granted, current_count_in_window). When granted, the current
    timestamp has already been written to the JSON file.
    """
    now = time.time()
    pruned = _prune(_load_timestamps(), now)
    if len(pruned) >= RATE_LIMIT_MAX:
        _atomic_write(pruned)  # still persist the pruning
        return False, len(pruned)
    pruned.append(now)
    _atomic_write(pruned)
    return True, len(pruned)


def ratelimit_status() -> dict:
    now = time.time()
    pruned = _prune(_load_timestamps(), now)
    return {
        "count_in_window": len(pruned),
        "max": RATE_LIMIT_MAX,
        "window_seconds": RATE_LIMIT_WINDOW,
        "slots_remaining": max(0, RATE_LIMIT_MAX - len(pruned)),
        "oldest_in_window": min(pruned) if pruned else None,
    }


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #

def _http_get(url: str) -> tuple[int, bytes]:
    """GET url. Returns (status_code, body). Status 0 indicates network error."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, b""
    except (urllib.error.URLError, TimeoutError, OSError):
        return 0, b""


# --------------------------------------------------------------------------- #
# Tiers
# --------------------------------------------------------------------------- #

def fetch_metadata(arxiv_id: str) -> str | None:
    """arXiv API Atom feed (metadata only)."""
    url = (
        "http://export.arxiv.org/api/query?"
        + urllib.parse.urlencode({"id_list": arxiv_id})
    )
    status, body = _http_get(url)
    if status == 200 and body:
        return body.decode("utf-8", errors="replace")
    return None


def fetch_markdown(arxiv_id: str) -> str | None:
    """Tier 1: arxiv2md (rate-limited, 28 req/min client-side)."""
    granted, count = ratelimit_check_and_reserve()
    if not granted:
        print(
            f"[arxiv2md] rate-limit reached ({count}/{RATE_LIMIT_MAX} in "
            f"{RATE_LIMIT_WINDOW}s) - skipping tier",
            file=sys.stderr,
        )
        return None
    url = (
        "https://arxiv2md.org/api/markdown?"
        + urllib.parse.urlencode({"url": arxiv_id})
    )
    status, body = _http_get(url)
    if status == 200 and body:
        return body.decode("utf-8", errors="replace")
    print(f"[arxiv2md] failed (HTTP {status})", file=sys.stderr)
    return None


def fetch_arxiv_html(arxiv_id: str) -> str | None:
    """Tier 2: arxiv.org/html (official, post-2023 papers mostly)."""
    url = f"https://arxiv.org/html/{urllib.parse.quote(arxiv_id)}"
    status, body = _http_get(url)
    if status == 200 and body:
        return body.decode("utf-8", errors="replace")
    print(f"[arxiv-html] failed (HTTP {status})", file=sys.stderr)
    return None


def fetch_ar5iv(arxiv_id: str) -> str | None:
    """Tier 3: ar5iv (broader HTML coverage, older papers)."""
    url = f"https://ar5iv.labs.arxiv.org/html/{urllib.parse.quote(arxiv_id)}"
    status, body = _http_get(url)
    if status == 200 and body:
        return body.decode("utf-8", errors="replace")
    print(f"[ar5iv] failed (HTTP {status})", file=sys.stderr)
    return None


def pdf_url(arxiv_id: str) -> str:
    """Tier 4: the PDF URL, to be consumed by the Read tool."""
    return f"https://arxiv.org/pdf/{urllib.parse.quote(arxiv_id)}"


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

TIERS = ["md", "html", "ar5iv", "pdf"]


def run_tier(tier: str, arxiv_id: str) -> str | None:
    if tier == "md":
        return fetch_markdown(arxiv_id)
    if tier == "html":
        return fetch_arxiv_html(arxiv_id)
    if tier == "ar5iv":
        return fetch_ar5iv(arxiv_id)
    if tier == "pdf":
        return pdf_url(arxiv_id)
    raise ValueError(f"unknown tier: {tier}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fetch an arXiv paper via tiered fallback."
    )
    parser.add_argument("arxiv_id", nargs="?", help="arXiv ID or full URL")
    parser.add_argument(
        "--tier",
        choices=TIERS,
        help="Force a specific tier (skip fallback chain).",
    )
    parser.add_argument(
        "--metadata-only",
        action="store_true",
        help="Fetch arXiv API metadata only (no full text).",
    )
    parser.add_argument(
        "--ratelimit-status",
        action="store_true",
        help="Print current arxiv2md rate-limit state and exit.",
    )
    args = parser.parse_args(argv)

    if args.ratelimit_status:
        print(json.dumps(ratelimit_status(), indent=2))
        return 0

    if not args.arxiv_id:
        parser.error("arxiv_id is required unless --ratelimit-status is used")

    try:
        arxiv_id = normalize_arxiv_id(args.arxiv_id)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3

    if args.metadata_only:
        meta = fetch_metadata(arxiv_id)
        if not meta:
            print("error: metadata fetch failed", file=sys.stderr)
            return 4
        print(meta)
        return 0

    tiers = [args.tier] if args.tier else TIERS
    for tier in tiers:
        content = run_tier(tier, arxiv_id)
        if content:
            print(f"[tier] {tier}", file=sys.stderr)
            print(content)
            return 0

    if args.tier:
        print(f"error: tier {args.tier!r} unavailable", file=sys.stderr)
        return 2

    print("error: all tiers failed", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
