---
name: arxiv-search
description: Search arXiv for research papers by topic, category, author, or date range. Returns structured JSON with titles, authors, abstracts, and links - no full text (pair with arxiv-analyze for that). Use when the user says "search arxiv", "find arxiv papers", "arxiv papers on", "latest papers about", or "arxiv research".
license: MIT
compatibility: Requires Python 3.11+ (stdlib only) and internet access to export.arxiv.org
---

# arXiv Search

Search the arXiv public API for research papers. Returns structured metadata (title, authors, abstract, arXiv ID, categories, dates, PDF/HTML links) as JSON. For full-text analysis of a specific paper, pair with `arxiv-analyze`.

## When to use

- User wants to discover papers on a topic
- User wants recent submissions in an arXiv category
- User wants to check what an author has published
- Starting point before analyzing a specific paper

## Usage

The script is at `scripts/arxiv_search.py`. It hits the arXiv API directly and parses the Atom XML into JSON so the model never has to touch XML.

```bash
# Topic search
python3 scripts/arxiv_search.py "mechanistic interpretability" --max 20

# Category filter (see arXiv taxonomy: cs.LG, cs.CL, stat.ML, etc.)
python3 scripts/arxiv_search.py --category cs.LG --max 30 --sort-by submittedDate

# Topic + category + date range
python3 scripts/arxiv_search.py "sparse autoencoders" --category cs.LG \
    --from 2025-01-01 --to 2026-04-16 --max 50

# Recency-focused (newest first)
python3 scripts/arxiv_search.py "LLM agents" --sort-by submittedDate --max 20
```

**Flags:**
- `--max N` — max results (default 20; arXiv API caps at 2000)
- `--category CAT` — arXiv category code
- `--from YYYY-MM-DD` / `--to YYYY-MM-DD` — submission date filter
- `--sort-by relevance|lastUpdatedDate|submittedDate` — default relevance

**Output:** JSON on stdout. Each result has `id`, `title`, `authors[]`, `abstract`, `categories[]`, `primary_category`, `published`, `updated`, `abs_url`, `pdf_url`, `doi`, `journal_ref`, `comment`.

## Workflow

### 1. Parse intent
- **Topic search:** "find papers on X" → use `"X"` as query
- **Recent in field:** "what's new in cs.LG" → `--category cs.LG --sort-by submittedDate`
- **Author search:** "papers by <name>" → query the name; arXiv indexes author names in `all:`
- **Combined:** topic + time window + category

### 2. Run the search
Invoke the script. Default `--max 20` is a good starting point. Bump to 50 for broad surveys.

### 3. Present results
Format as a compact table. For each paper:
- arXiv ID (with `abs_url` for the link)
- Title
- Authors (first 2 + "et al." if more)
- Published date
- Primary category
- 1-sentence abstract summary (don't dump the full abstract)

### 4. Offer handoffs
Ask if the user wants to:
- Analyze a specific paper (→ `arxiv-analyze`)
- Create a watch for this query (→ `arxiv-monitor add`)

## Output format

```
### arXiv Search: <query>

| # | arXiv ID | Title | Authors | Date |
|---|----------|-------|---------|------|
| 1 | 2501.11120v1 | Tell me about yourself... | Betley et al. | 2025-01-19 |

**Next:**
- analyze <id> to fetch full text
- watch <name> to track this query ongoingly
```

## Token efficiency

- 20 results = ~5K tokens (abstracts are the bulk)
- Ask the user to narrow the query rather than dumping 50 results
- For briefing only, pipe through `jq '.results | map({id, title, authors, published})'` before sending to context

## arXiv taxonomy quick reference

Common categories (see https://arxiv.org/category_taxonomy for full list):
- `cs.CL` — Computation and Language (NLP)
- `cs.LG` — Machine Learning
- `cs.AI` — Artificial Intelligence
- `cs.CR` — Cryptography and Security
- `cs.CY` — Computers and Society
- `stat.ML` — Statistics: Machine Learning
- `cs.IR` — Information Retrieval
- `cs.HC` — Human-Computer Interaction

## Rate limits

arXiv API: soft limit of 1 request per 3 seconds per IP. This skill issues one request per invocation — well within limits.

## Error handling

- Invalid category or bad query → empty `results` array. Report "no papers found" and suggest broadening the query.
- Network error → exit 4, message on stderr.
- Malformed response → exit 5 (extremely rare; would signal arXiv API changes).

## Requirements

- Python 3.11+ (stdlib only, no pip install needed)
