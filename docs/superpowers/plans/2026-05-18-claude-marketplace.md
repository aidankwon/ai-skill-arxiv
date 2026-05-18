# Claude Marketplace Conversion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure the repo into a Claude Code marketplace so users can add it in Claude Desktop and install the `arxiv-skills` plugin from the UI.

**Architecture:** Add a `.claude-plugin/marketplace.json` at the repo root to make it a discoverable marketplace. Move all three skills into `plugins/arxiv-skills/skills/` (the plugin directory) and add a `plugin.json` there. No script logic changes — the `arxiv-monitor` → `arxiv-search` relative path is identical in the new location.

**Tech Stack:** JSON (marketplace/plugin manifests), git mv (preserve history on file moves)

---

## File Map

| Action | Path |
|--------|------|
| Create | `.claude-plugin/marketplace.json` |
| Create | `plugins/arxiv-skills/.claude-plugin/plugin.json` |
| Move   | `skills/arxiv-search/` → `plugins/arxiv-skills/skills/arxiv-search/` |
| Move   | `skills/arxiv-analyze/` → `plugins/arxiv-skills/skills/arxiv-analyze/` |
| Move   | `skills/arxiv-monitor/` → `plugins/arxiv-skills/skills/arxiv-monitor/` |
| Modify | `CLAUDE.md` — update script paths |

---

## Task 1: Create the marketplace manifest

**Files:**
- Create: `.claude-plugin/marketplace.json`

- [ ] **Step 1: Create the directory and file**

```bash
mkdir -p .claude-plugin
```

Create `.claude-plugin/marketplace.json` with this exact content:

```json
{
  "$schema": "https://anthropic.com/claude-code/marketplace.schema.json",
  "name": "arxiv-skills",
  "description": "Search, analyze, and monitor arXiv research papers. Stdlib Python only.",
  "owner": {
    "name": "aidankwon",
    "url": "https://github.com/aidankwon"
  },
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

- [ ] **Step 2: Verify it is valid JSON**

```bash
python3 -c "import json; json.load(open('.claude-plugin/marketplace.json')); print('valid')"
```

Expected output: `valid`

- [ ] **Step 3: Commit**

```bash
git add .claude-plugin/marketplace.json
git commit -m "feat: add Claude Code marketplace manifest"
```

---

## Task 2: Create the plugin manifest

**Files:**
- Create: `plugins/arxiv-skills/.claude-plugin/plugin.json`

- [ ] **Step 1: Create the directory and file**

```bash
mkdir -p plugins/arxiv-skills/.claude-plugin
```

Create `plugins/arxiv-skills/.claude-plugin/plugin.json` with this exact content:

```json
{
  "name": "arxiv-skills",
  "version": "1.0.0",
  "description": "Search, analyze, and monitor arXiv research papers. Stdlib Python only, no pip install.",
  "author": {
    "name": "aidankwon"
  },
  "homepage": "https://github.com/aidankwon/ai-skill-arxiv",
  "repository": "https://github.com/aidankwon/ai-skill-arxiv",
  "license": "MIT"
}
```

- [ ] **Step 2: Verify it is valid JSON**

```bash
python3 -c "import json; json.load(open('plugins/arxiv-skills/.claude-plugin/plugin.json')); print('valid')"
```

Expected output: `valid`

- [ ] **Step 3: Commit**

```bash
git add plugins/arxiv-skills/.claude-plugin/plugin.json
git commit -m "feat: add arxiv-skills plugin manifest"
```

---

## Task 3: Move skills into the plugin directory

**Files:**
- Move: `skills/arxiv-search/` → `plugins/arxiv-skills/skills/arxiv-search/`
- Move: `skills/arxiv-analyze/` → `plugins/arxiv-skills/skills/arxiv-analyze/`
- Move: `skills/arxiv-monitor/` → `plugins/arxiv-skills/skills/arxiv-monitor/`

Use `git mv` to preserve file history.

- [ ] **Step 1: Create the destination skills directory**

```bash
mkdir -p plugins/arxiv-skills/skills
```

- [ ] **Step 2: Move all three skills**

```bash
git mv skills/arxiv-search  plugins/arxiv-skills/skills/arxiv-search
git mv skills/arxiv-analyze plugins/arxiv-skills/skills/arxiv-analyze
git mv skills/arxiv-monitor plugins/arxiv-skills/skills/arxiv-monitor
```

- [ ] **Step 3: Remove the now-empty top-level skills directory**

```bash
rmdir skills
```

- [ ] **Step 4: Verify the new structure**

```bash
find plugins/arxiv-skills -type f | sort
```

Expected output (order may vary):
```
plugins/arxiv-skills/.claude-plugin/plugin.json
plugins/arxiv-skills/skills/arxiv-analyze/SKILL.md
plugins/arxiv-skills/skills/arxiv-analyze/scripts/arxiv2md_ratelimit.json  (if exists)
plugins/arxiv-skills/skills/arxiv-analyze/scripts/arxiv_fetch.py
plugins/arxiv-skills/skills/arxiv-monitor/SKILL.md
plugins/arxiv-skills/skills/arxiv-monitor/scripts/arxiv_monitor.py
plugins/arxiv-skills/skills/arxiv-search/SKILL.md
plugins/arxiv-skills/skills/arxiv-search/scripts/arxiv_search.py
```

- [ ] **Step 5: Verify the monitor → search relative path still resolves**

```bash
python3 -c "
from pathlib import Path
SCRIPT_DIR = Path('plugins/arxiv-skills/skills/arxiv-monitor/scripts').resolve()
SEARCH_SCRIPT = SCRIPT_DIR.parent.parent / 'arxiv-search' / 'scripts' / 'arxiv_search.py'
print('resolves to:', SEARCH_SCRIPT)
print('exists:', SEARCH_SCRIPT.exists())
"
```

Expected output:
```
resolves to: /Users/.../plugins/arxiv-skills/skills/arxiv-search/scripts/arxiv_search.py
exists: True
```

- [ ] **Step 6: Commit**

```bash
git add plugins/arxiv-skills/skills/
git commit -m "feat: move skills into plugin directory"
```

---

## Task 4: Update CLAUDE.md script paths

**Files:**
- Modify: `CLAUDE.md`

The "Running the scripts" section references the old `skills/` paths. Update them to the new location under `plugins/arxiv-skills/skills/`.

- [ ] **Step 1: Edit CLAUDE.md**

In the `## Running the scripts` section, replace every occurrence of:

```
skills/arxiv-search/scripts/
```
with:
```
plugins/arxiv-skills/skills/arxiv-search/scripts/
```

```
skills/arxiv-analyze/scripts/
```
with:
```
plugins/arxiv-skills/skills/arxiv-analyze/scripts/
```

```
skills/arxiv-monitor/scripts/
```
with:
```
plugins/arxiv-skills/skills/arxiv-monitor/scripts/
```

The updated section should read:

```markdown
## Running the scripts

​```bash
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
​```
```

- [ ] **Step 2: Verify paths in CLAUDE.md no longer reference the old `skills/` prefix**

```bash
grep -n "^python3 skills/" CLAUDE.md
```

Expected output: *(empty — no matches)*

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update script paths for new plugin directory layout"
```

---

## Task 5: Update README.md script paths

**Files:**
- Modify: `README.md`

The README's "Usage from the CLI" section (lines ~103–141) references the old `skills/` paths. The manual installation `cp` commands (lines ~62–64) and the `npx skills-ref validate` example (line ~74) also reference the old paths. Update all of them.

- [ ] **Step 1: Update the CLI usage examples**

Replace every occurrence of `python3 skills/arxiv-search/scripts/` with `python3 plugins/arxiv-skills/skills/arxiv-search/scripts/`, and likewise for `arxiv-analyze` and `arxiv-monitor`. The updated block (lines ~103–141) should read:

```markdown
### Search

​```bash
python3 plugins/arxiv-skills/skills/arxiv-search/scripts/arxiv_search.py "mechanistic interpretability" --max 20
python3 plugins/arxiv-skills/skills/arxiv-search/scripts/arxiv_search.py --category cs.LG --sort-by submittedDate
python3 plugins/arxiv-skills/skills/arxiv-search/scripts/arxiv_search.py "sparse autoencoders" \
    --from 2025-01-01 --to 2026-04-16
​```

### Analyze (fetch full text)

​```bash
# Auto-tier fallback: markdown → HTML → ar5iv → PDF
python3 plugins/arxiv-skills/skills/arxiv-analyze/scripts/arxiv_fetch.py 2501.11120

# Force a specific tier
python3 plugins/arxiv-skills/skills/arxiv-analyze/scripts/arxiv_fetch.py 2501.11120 --tier html

# Metadata only
python3 plugins/arxiv-skills/skills/arxiv-analyze/scripts/arxiv_fetch.py 2501.11120 --metadata-only

# Check arxiv2md rate-limit state
python3 plugins/arxiv-skills/skills/arxiv-analyze/scripts/arxiv_fetch.py --ratelimit-status
​```

### Monitor

​```bash
python3 plugins/arxiv-skills/skills/arxiv-monitor/scripts/arxiv_monitor.py add "interp-ml" \
    --query "mechanistic interpretability" --category cs.LG --max 30
python3 plugins/arxiv-skills/skills/arxiv-monitor/scripts/arxiv_monitor.py check "interp-ml"
python3 plugins/arxiv-skills/skills/arxiv-monitor/scripts/arxiv_monitor.py check-all
python3 plugins/arxiv-skills/skills/arxiv-monitor/scripts/arxiv_monitor.py list
python3 plugins/arxiv-skills/skills/arxiv-monitor/scripts/arxiv_monitor.py reset "interp-ml"
python3 plugins/arxiv-skills/skills/arxiv-monitor/scripts/arxiv_monitor.py remove "interp-ml"
​```
```

- [ ] **Step 2: Update the manual install cp commands**

Replace (lines ~62–64):
```bash
cp -r ai-skill-arxiv/skills/arxiv-search  ~/.claude/skills/
cp -r ai-skill-arxiv/skills/arxiv-analyze ~/.claude/skills/
cp -r ai-skill-arxiv/skills/arxiv-monitor ~/.claude/skills/
```
with:
```bash
cp -r ai-skill-arxiv/plugins/arxiv-skills/skills/arxiv-search  ~/.claude/skills/
cp -r ai-skill-arxiv/plugins/arxiv-skills/skills/arxiv-analyze ~/.claude/skills/
cp -r ai-skill-arxiv/plugins/arxiv-skills/skills/arxiv-monitor ~/.claude/skills/
```

- [ ] **Step 3: Update the skills-ref validate example**

Replace (line ~74):
```bash
npx skills-ref validate ai-skill-arxiv/skills/arxiv-search
```
with:
```bash
npx skills-ref validate ai-skill-arxiv/plugins/arxiv-skills/skills/arxiv-search
```

- [ ] **Step 4: Verify no stale `skills/` path references remain in README**

```bash
grep -n "python3 skills/" README.md
grep -n "ai-skill-arxiv/skills/" README.md
```

Expected output: *(empty — no matches on either command)*

Note: References to `~/.claude/skills/` (the user's agent install directory) are intentionally kept — those are destination paths, not paths in this repo.

- [ ] **Step 5: Commit**

```bash
git add README.md
git commit -m "docs: update script paths for new plugin directory layout"
```

---

## Task 6: Final verification

- [ ] **Step 1: Confirm full repo structure**

```bash
find . -not -path './.git/*' -not -path './docs/*' -type f | sort
```

Expected output:
```
./.claude-plugin/marketplace.json
./CLAUDE.md
./LICENSE
./README.md
./plugins/arxiv-skills/.claude-plugin/plugin.json
./plugins/arxiv-skills/skills/arxiv-analyze/SKILL.md
./plugins/arxiv-skills/skills/arxiv-analyze/scripts/arxiv_fetch.py
./plugins/arxiv-skills/skills/arxiv-monitor/SKILL.md
./plugins/arxiv-skills/skills/arxiv-monitor/scripts/arxiv_monitor.py
./plugins/arxiv-skills/skills/arxiv-search/SKILL.md
./plugins/arxiv-skills/skills/arxiv-search/scripts/arxiv_search.py
```

(State files like `arxiv2md_ratelimit.json` and `watchlist.json` may appear if present; that is fine.)

- [ ] **Step 2: Run a quick smoke test — search script executes**

```bash
python3 plugins/arxiv-skills/skills/arxiv-search/scripts/arxiv_search.py "test" --max 1
```

Expected: JSON output with one result (or an empty results array if the query finds nothing), no Python errors.

- [ ] **Step 3: Confirm git log is clean**

```bash
git log --oneline -7
```

Expected: five new commits visible on top of the existing history.
