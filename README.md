# ai-skill-arxiv

A suite of three Claude Code skills for working with arXiv research papers: search, analyze, and monitor — stdlib Python only, zero dependencies.

## What you get

| Skill | Purpose |
|---|---|
| `arxiv-search` | Search arXiv by topic, category, author, date. Returns structured JSON. |
| `arxiv-analyze` | Fetch a paper via tiered fallback (markdown → HTML → ar5iv → PDF). Rate-limited, deterministic. |
| `arxiv-monitor` | Track queries over time. Persistent watchlist returns only *new* papers on each check. |

Ask Claude things like:

- "Find papers on mechanistic interpretability from the last 3 months"
- "Analyze arxiv 2501.11120 and summarize the claims"
- "Watch cs.LG for papers on sparse autoencoders and check weekly"
- "What's new in my arxiv watches?"

## Why this exists

arXiv is the primary channel for new AI/ML research. Working with it from an LLM agent has three frictions:

1. **Search returns XML.** The official API is Atom feeds — not LLM-friendly.
2. **Full-text fetch is wasteful.** PDFs are equation-heavy and token-expensive; plain HTML is often fine, and markdown is better.
3. **"What's new since I last checked" is manual.** There's no built-in delta.

These three skills solve each problem and compose into a discovery → read → track pipeline.

## Installation

### Via the `skills` CLI (recommended — vercel-labs/skills)

The [vercel-labs/skills](https://github.com/vercel-labs/skills) CLI can install skills from any GitHub repo. Install all three:

```bash
npx skills add dsebastien/ai-skill-arxiv --skill '*'
```

Or pick just one:

```bash
npx skills add dsebastien/ai-skill-arxiv --skill arxiv-search
npx skills add dsebastien/ai-skill-arxiv --skill arxiv-analyze
npx skills add dsebastien/ai-skill-arxiv --skill arxiv-monitor
```

Preview what the repo offers without installing:

```bash
npx skills add dsebastien/ai-skill-arxiv --list
```

Note: `arxiv-monitor` invokes `arxiv-search` as a subprocess. If you install `arxiv-monitor` alone, `check`/`check-all` will fail — install `arxiv-search` alongside it.

### Manual install (Claude Code default location)

```bash
git clone https://github.com/dsebastien/ai-skill-arxiv.git
cp -r ai-skill-arxiv/skills/arxiv-search  ~/.claude/skills/
cp -r ai-skill-arxiv/skills/arxiv-analyze ~/.claude/skills/
cp -r ai-skill-arxiv/skills/arxiv-monitor ~/.claude/skills/
```

Skills are auto-discovered from their `SKILL.md` frontmatter.

## Requirements

- Python 3.11+
- Nothing else — all three scripts use stdlib only (no `pip install` step).

### Network access

The skills reach the following domains (HTTPS, no auth):

| Domain | Used by | Purpose |
|---|---|---|
| `export.arxiv.org` | search, monitor | arXiv public API |
| `arxiv.org` | analyze | HTML + PDF fallbacks |
| `arxiv2md.org` | analyze | Markdown rendering (tier 1) |
| `ar5iv.labs.arxiv.org` | analyze | HTML fallback (tier 3) |

If you're behind a corporate proxy or firewall that blocks any of these, the skill falls through to the next available tier. `arxiv-search` and `arxiv-monitor` only need `export.arxiv.org`.

## Usage from the CLI (without Claude)

Each skill's script is a normal CLI. You can use them directly.

### Search

```bash
python3 skills/arxiv-search/scripts/arxiv_search.py "mechanistic interpretability" --max 20
python3 skills/arxiv-search/scripts/arxiv_search.py --category cs.LG --sort-by submittedDate
python3 skills/arxiv-search/scripts/arxiv_search.py "sparse autoencoders" \
    --from 2025-01-01 --to 2026-04-16
```

### Analyze (fetch full text)

```bash
# Auto-tier fallback: markdown → HTML → ar5iv → PDF
python3 skills/arxiv-analyze/scripts/arxiv_fetch.py 2501.11120

# Force a specific tier
python3 skills/arxiv-analyze/scripts/arxiv_fetch.py 2501.11120 --tier html

# Metadata only
python3 skills/arxiv-analyze/scripts/arxiv_fetch.py 2501.11120 --metadata-only

# Check arxiv2md rate-limit state
python3 skills/arxiv-analyze/scripts/arxiv_fetch.py --ratelimit-status
```

### Monitor

```bash
# Add a watch
python3 skills/arxiv-monitor/scripts/arxiv_monitor.py add "interp-ml" \
    --query "mechanistic interpretability" --category cs.LG --max 30

# Check (returns only new papers since last check)
python3 skills/arxiv-monitor/scripts/arxiv_monitor.py check "interp-ml"

# Check everything
python3 skills/arxiv-monitor/scripts/arxiv_monitor.py check-all

# Inspect, reset, remove
python3 skills/arxiv-monitor/scripts/arxiv_monitor.py list
python3 skills/arxiv-monitor/scripts/arxiv_monitor.py reset "interp-ml"
python3 skills/arxiv-monitor/scripts/arxiv_monitor.py remove "interp-ml"
```

## Design notes

### Fetch fallback chain

`arxiv-analyze` tries formats in order of token efficiency:

1. [arxiv2md](https://arxiv2md.org/) — markdown with LaTeX math preserved, refs/TOC/citations stripped
2. `arxiv.org/html/<id>` — official HTML (post-2023 papers mostly)
3. [ar5iv](https://ar5iv.labs.arxiv.org/) — broader coverage for older papers
4. `arxiv.org/pdf/<id>` — last resort, URL returned for your PDF reader

### Deterministic rate limiting for arxiv2md

arxiv2md allows 30 requests/minute per IP. The script self-throttles at 28 (safety margin) via `scripts/arxiv2md_ratelimit.json` — an array of Unix timestamps. On every call:

1. Load timestamps, prune entries older than 60 seconds
2. If ≥ 28 in the rolling window → skip arxiv2md, fall through to tier 2
3. Else → append current timestamp, write atomically (`tempfile` + `os.replace`), make request

The JSON stays bounded at ~28 entries. Never edit by hand; delete the file to reset.

### Monitor's seen-ID store

Each watch in `watchlist.json` stores up to 500 recent arXiv IDs under `seen_ids`. When a search returns IDs not in that set, they're "new" — added to `seen_ids` (with bounded growth) and returned to the caller. State writes are atomic.

## Integration patterns

### Weekly digest (with Claude Code `/schedule` or cron)

```bash
# Every Monday at 9am, check all watches and summarize
0 9 * * 1 python3 ~/.claude/skills/arxiv-monitor/scripts/arxiv_monitor.py check-all > ~/arxiv-weekly.json
```

Then feed the JSON to Claude for a "here's what's new and why it matters" briefing.

### Discovery → analyze pipeline

```
arxiv-search "topic" → pick paper → arxiv-analyze <id> → save summary
```

Or monitor-driven:

```
arxiv-monitor check-all → LLM filters for relevance → arxiv-analyze on winners
```

## License

MIT. See `LICENSE`.

## Credits

- [arxiv2md](https://github.com/timf34/arxiv2md) — markdown rendering service
- [ar5iv](https://ar5iv.labs.arxiv.org/) — HTML renderer for arXiv papers
- [vercel-labs/skills](https://github.com/vercel-labs/skills) — the `skills add` CLI that makes multi-skill repos installable à la carte
