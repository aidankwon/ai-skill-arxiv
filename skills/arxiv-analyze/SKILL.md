---
name: arxiv-analyze
description: Fetch and analyze an arXiv paper via tiered fallback (markdown -> arXiv HTML -> ar5iv -> PDF). Rate-limited for arxiv2md (28 req/min, deterministic). Produces a structured summary with citation, problem, key claims, method, results, limitations. Use when the user says "analyze arxiv paper", "summarize arxiv", "read paper", "what does this paper say", or provides an arXiv ID/URL to analyze.
license: MIT
compatibility: Requires Python 3.11+ (stdlib only) and internet access to arxiv.org, arxiv2md.org, and ar5iv.labs.arxiv.org
---

# arXiv Analyze

Fetch an arXiv paper in the most token-efficient format available, then analyze it.

## Fallback chain

The fetcher script tries formats in order of quality and token efficiency:

1. **arxiv2md** (markdown) — cleanest, LaTeX math preserved, refs/TOC/citations stripped by default; rate-limited client-side to 28 req/min
2. **arxiv.org/html** — official HTML, can be auto-converted to markdown
3. **ar5iv** — arXiv Labs HTML renderer, broader coverage for older papers
4. **arxiv.org/pdf** — last resort; URL returned, load with your PDF reader of choice

## Rate limiting (deterministic)

arxiv2md allows 30 requests/minute per IP. The script self-throttles at 28 via `scripts/arxiv2md_ratelimit.json` — an array of timestamps, pruned to the rolling 60-second window on every call, written atomically (temp file + `os.replace`). When the limit is reached, the script silently falls through to tier 2. Never edit that JSON by hand; to reset, delete the file.

Check state any time:

```bash
python3 scripts/arxiv_fetch.py --ratelimit-status
```

## Usage

```bash
# Auto-tier fallback (preferred)
python3 scripts/arxiv_fetch.py 2501.11120

# Full URLs are accepted too
python3 scripts/arxiv_fetch.py "https://arxiv.org/abs/2501.11120v1"

# Force a specific tier
python3 scripts/arxiv_fetch.py 2501.11120 --tier md
python3 scripts/arxiv_fetch.py 2501.11120 --tier html
python3 scripts/arxiv_fetch.py 2501.11120 --tier ar5iv
python3 scripts/arxiv_fetch.py 2501.11120 --tier pdf

# Metadata only (arXiv API Atom feed, ~200 tokens)
python3 scripts/arxiv_fetch.py 2501.11120 --metadata-only
```

The selected tier is printed to stderr (`[tier] md`); content goes to stdout. For the PDF tier, stdout is the URL — feed it to your PDF reader.

Exit codes: `0` success, `1` all-tiers-failed, `2` forced-tier-unavailable, `3` invalid-ID, `4` network-error.

## Analysis workflow

After fetching, produce a structured summary with these sections:

- **Citation** — authors, title, arXiv ID, year, primary category
- **Problem** — what question the paper answers; why it matters
- **Key claims** — 3-5 bullets, each a specific claim (not a heading)
- **Method** — how they approached it, in 2-4 sentences
- **Results** — what they found; include numbers that matter
- **Limitations** — what the authors admit + what you noticed
- **Open questions** — what's unresolved; what follow-up work would do

## Token budget

| Tier | Typical output | When to use |
|------|----------------|-------------|
| metadata-only | ~200 tokens | Preview before committing to a full fetch |
| md (arxiv2md) | 5K-15K | Default; most efficient |
| html (arxiv.org) | 8K-20K | arxiv2md unavailable or rate-limited |
| ar5iv | 8K-20K | Older papers without official HTML |
| pdf (via Read) | 10K-50K+ | Equations-heavy papers where HTML rendering is bad |

If you only need claims/results, dump the fetched content to a temp file and grep/head rather than passing the whole thing to context. The paper is on disk — don't re-fetch.

## Hard rules

- **Never fabricate results.** If a claim isn't in the paper, say so.
- **Respect the rate limit.** The script handles it automatically; don't loop `--tier md` manually.
- **PDFs are expensive.** Only use `--tier pdf` when HTML paths have all failed or the user explicitly requests it.

## Requirements

- Python 3.11+ (stdlib only, no pip install needed)

## Credits

- arxiv2md renderer: https://arxiv2md.org/ (`timf34/arxiv2md`)
- ar5iv Labs: https://ar5iv.labs.arxiv.org/
