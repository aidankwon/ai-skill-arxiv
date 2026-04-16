---
name: arxiv-monitor
description: Monitor arXiv for new papers matching saved queries/categories. Manages a watchlist with deterministic "seen" tracking so subsequent checks return only new material. Use when the user says "watch arxiv", "track arxiv", "new papers on", "arxiv monitor", "check my arxiv watches", or wants periodic discovery. Depends on arxiv-search (must be installed as a sibling skill).
license: MIT
compatibility: Requires Python 3.11+ (stdlib only), internet access to export.arxiv.org, and the arxiv-search skill installed as a sibling
---

# arXiv Monitor

Track queries and categories on arXiv over time. State lives in `scripts/watchlist.json` — each watch remembers which arXiv IDs it has already surfaced, so every `check` returns only new material.

## When to use

- User wants ongoing discovery in a specific research area
- User wants to be notified of new papers from a category
- Pairs naturally with cron, scheduled jobs, or `/loop` for automated discovery
- One-shot "what's new" checks across multiple saved topics

For one-off searches with no persistence, use `arxiv-search` directly.

## Dependency

`arxiv-monitor` invokes `arxiv-search` via subprocess to execute queries. When both skills are installed as siblings under the same `skills/` directory, the relative path resolves automatically. If you install only `arxiv-monitor`, it will fail on `check` — install `arxiv-search` alongside it.

## Architecture

The script is a thin wrapper around `arxiv-search`: it calls the search script with stored query parameters, then filters the response against the `seen_ids` list for that watch. New paper IDs are appended to `seen_ids` (capped at 500 per watch). State writes are atomic (temp file + `os.replace`).

## Commands

```bash
# Inspect
python3 scripts/arxiv_monitor.py list

# Add a watch (needs --query and/or --category)
python3 scripts/arxiv_monitor.py add "interp-ml" \
    --query "mechanistic interpretability" --category cs.LG --max 30

# Check one watch (returns new-only, updates state)
python3 scripts/arxiv_monitor.py check "interp-ml"

# Check everything (respects arXiv API's 1-req-per-3s soft limit)
python3 scripts/arxiv_monitor.py check-all

# Reset seen-ids (treat next check as first run)
python3 scripts/arxiv_monitor.py reset "interp-ml"

# Remove a watch entirely
python3 scripts/arxiv_monitor.py remove "interp-ml"
```

Output for `check`/`check-all` is JSON: `{"name", "total_returned", "new_count", "new": [...]}`.

## Workflow

### 1. Understand intent
- "watch X" / "track X" → `add`
- "what's new" → `check-all`
- "new papers for my <topic> watch" → `check <name>`
- "stop tracking X" → `remove`

### 2. For add: gather parameters
Ask the user only if unclear:
- **Name** — short slug, kebab-case. Required.
- **Query** — free text; multi-word is AND'd as separate clauses
- **Category** — arXiv code (cs.LG, cs.CL, stat.ML, etc.); optional
- **Max results per check** — default 30

Must provide at least one of query/category.

### 3. For check: run and filter
Run the command. If `new_count == 0`, just say "no new papers since last check" and the timestamp. If `new_count > 0`:

- Present new papers as a compact table (arXiv ID, title, authors, date, primary category)
- Offer to analyze any of them (→ `arxiv-analyze`)

### 4. For check-all: batch report
Print one summary line per watch, then drill into watches with new papers.

## State file

`scripts/watchlist.json` structure:

```json
{
  "watches": {
    "interp-ml": {
      "query": "mechanistic interpretability",
      "category": "cs.LG",
      "max": 30,
      "seen_ids": ["2501.11120v1", "..."],
      "last_checked": "2026-04-16T09:00:00Z",
      "created": "2026-04-16T09:00:00Z"
    }
  }
}
```

Do not edit by hand during a check run. Direct edits between runs are fine for debugging.

`seen_ids` is pruned to the 500 most recent per watch. If a watch goes untouched long enough that old papers drop out, they may re-appear on the next check — accepted as the trade-off for bounded state size.

## Hard rules

- **Never truncate the seen-ids list beyond what the script does.** It's load-bearing — truncation means false positives as "new."
- **One query per watch.** If a topic has multiple angles, create multiple watches.
- **Cap `--max` at 100.** Above that, arXiv API responses get slow and the signal-to-noise ratio drops.
- **arXiv API rate limit.** `check-all` sleeps 3 seconds between watches. Don't parallelise.

## Requirements

- Python 3.11+ (stdlib only, no pip install needed)
- `arxiv-search` skill installed as a sibling (under the same `skills/` directory)
