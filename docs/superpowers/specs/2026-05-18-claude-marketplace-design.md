# Design: Convert ai-skill-arxiv to a Claude Code Marketplace Plugin

**Date:** 2026-05-18  
**Repo:** https://github.com/aidankwon/ai-skill-arxiv (forked from dsebastien/ai-skill-arxiv)

---

## Goal

Make the three arXiv skills (search, analyze, monitor) installable from within Claude Desktop via the marketplace browser, without changing how the skills or scripts work.

## Approach

Turn this repo into a Claude Code marketplace. A marketplace is a GitHub repo whose root contains `.claude-plugin/marketplace.json`. When a user adds the repo as a marketplace in Claude Desktop, they can browse and install its plugins from the UI.

All three skills are packaged as a single plugin (`arxiv-skills`) — not three separate plugins — because `arxiv-monitor` resolves `arxiv-search` by relative path at runtime and requires them to be siblings under the same `skills/` directory.

## Directory Structure

**Before:**
```
skills/
  arxiv-search/SKILL.md + scripts/
  arxiv-analyze/SKILL.md + scripts/
  arxiv-monitor/SKILL.md + scripts/
README.md
CLAUDE.md
```

**After:**
```
.claude-plugin/
  marketplace.json
plugins/
  arxiv-skills/
    .claude-plugin/
      plugin.json
    skills/
      arxiv-search/SKILL.md + scripts/    ← moved
      arxiv-analyze/SKILL.md + scripts/   ← moved
      arxiv-monitor/SKILL.md + scripts/   ← moved
README.md
CLAUDE.md                                 ← updated paths
```

## New Files

### `.claude-plugin/marketplace.json`
```json
{
  "$schema": "https://anthropic.com/claude-code/marketplace.schema.json",
  "name": "arxiv-skills",
  "description": "Search, analyze, and monitor arXiv research papers. Stdlib Python only.",
  "owner": { "name": "aidankwon", "url": "https://github.com/aidankwon" },
  "plugins": [
    {
      "name": "arxiv-skills",
      "description": "Three skills for arXiv: search papers, fetch and analyze full text, and track new papers over time.",
      "source": "./plugins/arxiv-skills",
      "category": "research",
      "tags": ["arxiv", "research", "papers", "ai", "ml"]
    }
  ]
}
```

### `plugins/arxiv-skills/.claude-plugin/plugin.json`
```json
{
  "name": "arxiv-skills",
  "version": "1.0.0",
  "description": "Search, analyze, and monitor arXiv research papers. Stdlib Python only, no pip install.",
  "author": { "name": "aidankwon" },
  "homepage": "https://github.com/aidankwon/ai-skill-arxiv",
  "repository": "https://github.com/aidankwon/ai-skill-arxiv",
  "license": "MIT"
}
```

## Script Path Impact

`arxiv-monitor` resolves `arxiv-search` via:
```python
SCRIPT_DIR.parent.parent / "arxiv-search" / "scripts" / "arxiv_search.py"
# SCRIPT_DIR = .../skills/arxiv-monitor/scripts/
# parent.parent = .../skills/
# result = .../skills/arxiv-search/scripts/arxiv_search.py
```

The relative structure inside the plugin is identical to the current repo structure, so this path continues to resolve correctly after the move. No script changes are needed.

State files (`arxiv2md_ratelimit.json`, `watchlist.json`) are written relative to `SCRIPT_DIR`, which also remains correct.

Disk cache (`~/.cache/ai-skill-arxiv/`) is at an absolute XDG path — unaffected.

## Files to Update

- `CLAUDE.md` — update script paths in the "Running the scripts" section to reflect the new location under `plugins/arxiv-skills/skills/`

## Out of Scope

- Submitting to `anthropics/claude-plugins-official` (that's a separate PR to a third-party repo)
- Any changes to skill behavior or script logic
