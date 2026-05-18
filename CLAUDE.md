# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

Three [Agent Skills](https://agentskills.io) for arXiv: search, analyze, and monitor. Each skill is a self-contained directory under `skills/` with a `SKILL.md` spec and a single Python script under `scripts/`. No dependencies beyond Python 3.11+ stdlib — no pip install step ever.

## Running the scripts

```bash
# Search
python3 plugins/arxiv-skills/skills/arxiv-search/scripts/arxiv_search.py "mechanistic interpretability" --max 20
python3 plugins/arxiv-skills/skills/arxiv-search/scripts/arxiv_search.py --category cs.LG --sort-by submittedDate

# Analyze (auto-tier fallback)
python3 plugins/arxiv-skills/skills/arxiv-analyze/scripts/arxiv_fetch.py 2501.11120
python3 plugins/arxiv-skills/skills/arxiv-analyze/scripts/arxiv_fetch.py 2501.11120 --tier tex
python3 plugins/arxiv-skills/skills/arxiv-analyze/scripts/arxiv_fetch.py --ratelimit-status

# Monitor
python3 plugins/arxiv-skills/skills/arxiv-monitor/scripts/arxiv_monitor.py list
python3 plugins/arxiv-skills/skills/arxiv-monitor/scripts/arxiv_monitor.py add "name" --query "topic" --category cs.LG
python3 plugins/arxiv-skills/skills/arxiv-monitor/scripts/arxiv_monitor.py check-all
```

There is no build step, test suite, or linter configured in this repo.

## Architecture

### Skill layout

Each skill follows the Agent Skills spec: `SKILL.md` (frontmatter + instructions for the LLM) + `scripts/<script>.py` (the CLI the LLM invokes). The SKILL.md is what agents read; the Python script is what they run.

### Inter-skill dependency

`arxiv-monitor` shells out to `arxiv-search` via subprocess. The path is resolved at runtime relative to the script's location:

```
plugins/arxiv-skills/skills/arxiv-monitor/scripts/arxiv_monitor.py
  → SEARCH_SCRIPT = ../../arxiv-search/scripts/arxiv_search.py
```

This means the two skills must be installed as siblings. Installing only `arxiv-monitor` will break `check`/`check-all`.

### Persistent state (two files, both atomic)

- `plugins/arxiv-skills/skills/arxiv-analyze/scripts/arxiv2md_ratelimit.json` — rolling array of Unix timestamps for the arxiv2md 28 req/min cap. Pruned to the 60-second window on every call. Written via `tempfile` + `os.replace`.
- `plugins/arxiv-skills/skills/arxiv-monitor/scripts/watchlist.json` — watch configs + `seen_ids` per watch (capped at 500). Written via `tempfile` + `os.replace`.

Never edit either file during an active run. Delete `arxiv2md_ratelimit.json` to reset the rate-limit counter.

### Disk cache (`arxiv-analyze`)

Fetched paper content lands in `$XDG_CACHE_HOME/ai-skill-arxiv/<arxiv_id>/` (default `~/.cache/...`). Each tier writes its own file (`markdown.md`, `arxiv.html`, `ar5iv.html`, `src.tar.gz`, `tex/`). Cache hits skip both network and rate-limit budget. Use `--no-cache` to force a fresh fetch; `--cache-clear <id>` to wipe one paper.

### Fetch tier order (`arxiv-analyze`)

Auto-tier tries in order: arxiv2md (markdown) → arxiv.org/html → ar5iv → PDF URL. `--tier tex` is opt-in only (higher token cost, but always available and no third-party dependency). Tier label is printed to stderr; content goes to stdout.

Exit codes: `0` success, `1` all tiers failed, `2` forced tier unavailable, `3` invalid ID, `4` network error.
