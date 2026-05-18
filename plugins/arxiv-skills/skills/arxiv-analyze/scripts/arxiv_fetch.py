#!/usr/bin/env python3
"""Fetch arXiv papers via tiered fallback: markdown -> HTML -> ar5iv -> PDF (+ TeX source).

Handles deterministic rate limiting for arxiv2md (30 req/min; throttled to 28
with a safety margin). Rate limit state persists in arxiv2md_ratelimit.json
alongside this script. Stale entries are pruned on every call so the file
stays bounded at roughly RATE_LIMIT_MAX entries.

Fetched content is cached on disk at $XDG_CACHE_HOME/ai-skill-arxiv/<id>/
(or ~/.cache/ai-skill-arxiv/<id>/) across tiers, so repeat fetches are free
and offline-friendly. Use --no-cache to force a fresh fetch.

Exit codes:
    0 = success (content on stdout, tier label on stderr)
    1 = all tiers failed
    2 = forced tier was rate-limited or unavailable (with --tier)
    3 = invalid arXiv ID format
    4 = network/fetch error on metadata-only path

Usage:
    python arxiv_fetch.py <arxiv_id>                          # auto-tier fallback
    python arxiv_fetch.py <arxiv_id> --tier md|html|ar5iv|pdf|tex
    python arxiv_fetch.py <arxiv_id> --metadata-only          # arXiv API metadata
    python arxiv_fetch.py <arxiv_id> --no-cache               # skip cache, refetch
    python arxiv_fetch.py --ratelimit-status                  # show current counter
    python arxiv_fetch.py --cache-clear <arxiv_id>            # clear cache for one id
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tarfile
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


def _cache_root() -> Path:
    """Honor XDG_CACHE_HOME; default to ~/.cache. Created lazily."""
    xdg = os.environ.get("XDG_CACHE_HOME")
    base = Path(xdg) if xdg else Path.home() / ".cache"
    return base / "ai-skill-arxiv"


# Canonical cache filenames per tier. Contents are text (or binary for PDF/tarball).
_CACHE_FILES = {
    "md": "markdown.md",
    "html": "arxiv.html",
    "ar5iv": "ar5iv.html",
    # "pdf" stores the URL in pdf_url.txt; the binary is not cached here.
    # "tex" extracts into a tex/ subdir and flattens on demand.
}

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
# TeX source tier
# --------------------------------------------------------------------------- #

# Resolves \input{x}, \include{x}, \import{dir}{x}, \subimport{dir}{x}
_INPUT_RE = re.compile(
    r"\\(?:input|include|import|subimport)(?:\s*\{([^}]*)\}){1,2}"
)


def fetch_tex(arxiv_id: str, cache_dir: Path) -> str | None:
    """Tier 5 (opt-in): arxiv.org/src tarball, flattened TeX source.

    arXiv's /src/<id> endpoint returns the original submitted source (tar.gz
    for most papers, single .tex or .gz otherwise). Returns flattened TeX
    content or None if unavailable.
    """
    tex_dir = cache_dir / "tex"
    src_path = cache_dir / "src.tar.gz"

    if not tex_dir.exists():
        if not src_path.exists():
            url = f"https://arxiv.org/src/{urllib.parse.quote(arxiv_id)}"
            status, body = _http_get(url)
            if status != 200 or not body:
                print(f"[tex] failed to download src (HTTP {status})", file=sys.stderr)
                return None
            cache_dir.mkdir(parents=True, exist_ok=True)
            src_path.write_bytes(body)
        try:
            _safe_extract(src_path, tex_dir)
        except (tarfile.TarError, OSError) as e:
            # Some "tarballs" are actually a single gzipped .tex.
            print(f"[tex] tarball extract failed ({e}); attempting gzip fallback", file=sys.stderr)
            tex_dir.mkdir(parents=True, exist_ok=True)
            try:
                import gzip
                data = gzip.decompress(src_path.read_bytes())
                (tex_dir / "main.tex").write_bytes(data)
            except Exception as e2:
                print(f"[tex] gzip fallback failed: {e2}", file=sys.stderr)
                return None

    flat = _flatten_tex(tex_dir)
    if not flat:
        print("[tex] no entrypoint found in source", file=sys.stderr)
        return None
    return flat


def _safe_extract(tar_path: Path, dest: Path) -> None:
    """Extract with the 'data' filter where available (Python 3.11.4+)."""
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(tar_path) as tar:
        try:
            tar.extractall(dest, filter="data")
        except TypeError:
            # Older Python without filter support — still fine for our use
            tar.extractall(dest)  # noqa: S202


def _find_entrypoint(tex_dir: Path) -> Path | None:
    """Locate the main .tex file: prefer main.tex, else the one with \\documentclass."""
    tex_files = sorted(tex_dir.rglob("*.tex"))
    if not tex_files:
        return None
    # Prefer conventional names
    for name in ("main.tex", "paper.tex", "ms.tex", "arxiv.tex"):
        for p in tex_files:
            if p.name == name:
                return p
    # Else find files containing \documentclass
    candidates = []
    for p in tex_files:
        try:
            head = p.read_text(errors="replace")[:4096]
        except OSError:
            continue
        if r"\documentclass" in head:
            candidates.append((p, len(p.read_bytes())))
    if candidates:
        # Largest such file (usually the most complete entry point)
        return max(candidates, key=lambda x: x[1])[0]
    # Last resort: largest .tex
    return max(tex_files, key=lambda p: p.stat().st_size)


def _flatten_tex(tex_dir: Path, max_depth: int = 8) -> str | None:
    """Resolve \\input / \\include / \\import / \\subimport recursively."""
    entry = _find_entrypoint(tex_dir)
    if entry is None:
        return None
    seen: set[Path] = set()

    def resolve(path: Path, depth: int) -> str:
        if depth > max_depth or path in seen or not path.exists():
            return ""
        seen.add(path)
        try:
            text = path.read_text(errors="replace")
        except OSError:
            return ""

        def repl(m: re.Match) -> str:
            groups = [g for g in m.groups() if g]
            if not groups:
                return m.group(0)
            # Last non-None group is the file name; earlier ones are dirs (import)
            rel = Path(*groups)
            candidate = (path.parent / rel)
            if candidate.suffix == "":
                # TeX convention: omitted extension = .tex
                candidate = candidate.with_suffix(".tex")
            if not candidate.exists():
                # Also try relative to tex_dir root
                alt = (tex_dir / rel)
                if alt.suffix == "":
                    alt = alt.with_suffix(".tex")
                if alt.exists():
                    candidate = alt
                else:
                    return m.group(0)  # leave unresolved ref in place
            return resolve(candidate, depth + 1)

        return _INPUT_RE.sub(repl, text)

    return resolve(entry, 0)


# --------------------------------------------------------------------------- #
# Cache layer
# --------------------------------------------------------------------------- #

def _cache_path(arxiv_id: str, tier: str) -> Path:
    return _cache_root() / arxiv_id / _CACHE_FILES[tier]


def _cache_read(arxiv_id: str, tier: str) -> str | None:
    if tier not in _CACHE_FILES:
        return None
    p = _cache_path(arxiv_id, tier)
    if p.is_file():
        try:
            return p.read_text(errors="replace")
        except OSError:
            return None
    return None


def _cache_write(arxiv_id: str, tier: str, content: str) -> None:
    if tier not in _CACHE_FILES:
        return
    p = _cache_path(arxiv_id, tier)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    except OSError as e:
        print(f"[cache] write failed: {e}", file=sys.stderr)


def cache_clear(arxiv_id: str) -> bool:
    """Remove the cache directory for a single arxiv id. Returns True if removed."""
    d = _cache_root() / arxiv_id
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)
        return True
    return False


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

# Auto-fallback chain. `tex` is opt-in via --tier tex; not in auto chain because
# raw LaTeX is token-expensive and less LLM-readable than rendered markdown.
TIERS = ["md", "html", "ar5iv", "pdf"]
ALL_TIERS = ["md", "html", "ar5iv", "pdf", "tex"]


def run_tier(tier: str, arxiv_id: str, use_cache: bool = True) -> str | None:
    """Fetch one tier, with disk-cache read-through when use_cache is True.

    Order per tier: cache hit -> fresh fetch -> cache write on success.
    Rate limiting (arxiv2md) is only consulted for fresh fetches.
    """
    if tier == "pdf":
        # PDFs aren't fetched here; we return the URL for the caller to Read.
        return pdf_url(arxiv_id)

    if use_cache:
        cached = _cache_read(arxiv_id, tier)
        if cached:
            print(f"[{tier}] cache hit", file=sys.stderr)
            return cached

    if tier == "md":
        content = fetch_markdown(arxiv_id)
    elif tier == "html":
        content = fetch_arxiv_html(arxiv_id)
    elif tier == "ar5iv":
        content = fetch_ar5iv(arxiv_id)
    elif tier == "tex":
        # TeX has its own on-disk layout (tex/ subdir). fetch_tex handles caching.
        return fetch_tex(arxiv_id, _cache_root() / arxiv_id)
    else:
        raise ValueError(f"unknown tier: {tier}")

    if content and use_cache:
        _cache_write(arxiv_id, tier, content)
    return content


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fetch an arXiv paper via tiered fallback."
    )
    parser.add_argument("arxiv_id", nargs="?", help="arXiv ID or full URL")
    parser.add_argument(
        "--tier",
        choices=ALL_TIERS,
        help="Force a specific tier (skip fallback chain). 'tex' is opt-in only.",
    )
    parser.add_argument(
        "--metadata-only",
        action="store_true",
        help="Fetch arXiv API metadata only (no full text).",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Skip disk cache (force fresh fetch). Successful fetches are still cached.",
    )
    parser.add_argument(
        "--ratelimit-status",
        action="store_true",
        help="Print current arxiv2md rate-limit state and exit.",
    )
    parser.add_argument(
        "--cache-clear",
        metavar="ARXIV_ID",
        help="Clear the disk cache for a single arxiv id and exit.",
    )
    args = parser.parse_args(argv)

    if args.ratelimit_status:
        print(json.dumps(ratelimit_status(), indent=2))
        return 0

    if args.cache_clear:
        try:
            cid = normalize_arxiv_id(args.cache_clear)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 3
        removed = cache_clear(cid)
        print(f"[cache] {'cleared' if removed else 'nothing to clear'} for {cid}", file=sys.stderr)
        return 0

    if not args.arxiv_id:
        parser.error("arxiv_id is required unless --ratelimit-status or --cache-clear is used")

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
    use_cache = not args.no_cache
    for tier in tiers:
        content = run_tier(tier, arxiv_id, use_cache=use_cache)
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
