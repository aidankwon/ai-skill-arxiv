#!/usr/bin/env python3
"""Track arXiv categories/queries over time and surface only new papers.

State lives in watchlist.json alongside this script. Each watch entry
records the query, filters, and the set of arXiv IDs already seen so that
subsequent runs return only new material.

Usage:
    python arxiv_monitor.py list
    python arxiv_monitor.py add "<name>" --query "text" [--category cs.LG] [--max 30]
    python arxiv_monitor.py remove "<name>"
    python arxiv_monitor.py check "<name>"          # check one watch, mark seen
    python arxiv_monitor.py check-all               # check every watch
    python arxiv_monitor.py reset "<name>"          # clear seen-ids for a watch

Output for check/check-all: JSON with new-only results per watch.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import subprocess
import tempfile
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
WATCHLIST_FILE = SCRIPT_DIR / "watchlist.json"
SEARCH_SCRIPT = (
    SCRIPT_DIR.parent.parent
    / "arxiv-search"
    / "scripts"
    / "arxiv_search.py"
)
MAX_SEEN_PER_WATCH = 500  # prevent unbounded growth


def _load() -> dict:
    if not WATCHLIST_FILE.exists():
        return {"watches": {}}
    try:
        data = json.loads(WATCHLIST_FILE.read_text())
        data.setdefault("watches", {})
        return data
    except (json.JSONDecodeError, OSError):
        return {"watches": {}}


def _save(data: dict) -> None:
    fd, tmp_path = tempfile.mkstemp(
        dir=str(SCRIPT_DIR), prefix=".watchlist.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w") as fh:
            json.dump(data, fh, indent=2)
        os.replace(tmp_path, WATCHLIST_FILE)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def cmd_list(_args) -> int:
    data = _load()
    if not data["watches"]:
        print("(no watches configured)")
        return 0
    for name, watch in sorted(data["watches"].items()):
        seen = len(watch.get("seen_ids", []))
        last = watch.get("last_checked") or "never"
        query = watch.get("query") or ""
        cat = watch.get("category") or ""
        max_r = watch.get("max", 30)
        print(
            f"{name!r}  query={query!r} category={cat or '-'} max={max_r} "
            f"seen={seen} last_checked={last}"
        )
    return 0


def cmd_add(args) -> int:
    data = _load()
    if args.name in data["watches"]:
        print(f"error: watch {args.name!r} already exists (use remove then add)", file=sys.stderr)
        return 1
    if not args.query and not args.category:
        print("error: --query and/or --category required", file=sys.stderr)
        return 1
    data["watches"][args.name] = {
        "query": args.query,
        "category": args.category,
        "max": args.max,
        "seen_ids": [],
        "last_checked": None,
        "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    _save(data)
    print(f"added watch {args.name!r}")
    return 0


def cmd_remove(args) -> int:
    data = _load()
    if args.name not in data["watches"]:
        print(f"error: no watch named {args.name!r}", file=sys.stderr)
        return 1
    del data["watches"][args.name]
    _save(data)
    print(f"removed watch {args.name!r}")
    return 0


def cmd_reset(args) -> int:
    data = _load()
    if args.name not in data["watches"]:
        print(f"error: no watch named {args.name!r}", file=sys.stderr)
        return 1
    data["watches"][args.name]["seen_ids"] = []
    data["watches"][args.name]["last_checked"] = None
    _save(data)
    print(f"reset seen-ids for {args.name!r}")
    return 0


def _run_search(watch: dict) -> list[dict]:
    cmd = [sys.executable, str(SEARCH_SCRIPT)]
    if watch.get("query"):
        cmd.append(watch["query"])
    if watch.get("category"):
        cmd += ["--category", watch["category"]]
    cmd += [
        "--max", str(watch.get("max", 30)),
        "--sort-by", "submittedDate",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise RuntimeError(
            f"search script failed (exit {result.returncode}): {result.stderr.strip()}"
        )
    return json.loads(result.stdout)["results"]


def _check_one(name: str, watch: dict) -> dict:
    try:
        results = _run_search(watch)
    except Exception as e:
        return {"name": name, "error": str(e), "new": []}

    seen = set(watch.get("seen_ids", []))
    new_papers = [r for r in results if r["id"] not in seen]

    # Update state: add newly-seen IDs, keep bounded
    combined = list(seen) + [r["id"] for r in new_papers]
    if len(combined) > MAX_SEEN_PER_WATCH:
        combined = combined[-MAX_SEEN_PER_WATCH:]
    watch["seen_ids"] = combined
    watch["last_checked"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    return {
        "name": name,
        "total_returned": len(results),
        "new_count": len(new_papers),
        "new": new_papers,
    }


def cmd_check(args) -> int:
    data = _load()
    if args.name not in data["watches"]:
        print(f"error: no watch named {args.name!r}", file=sys.stderr)
        return 1
    report = _check_one(args.name, data["watches"][args.name])
    _save(data)
    print(json.dumps(report, indent=2))
    return 0


def cmd_check_all(_args) -> int:
    data = _load()
    reports = []
    for name in sorted(data["watches"]):
        reports.append(_check_one(name, data["watches"][name]))
        # Respect arXiv API soft-limit of 1 req / 3 sec
        time.sleep(3)
    _save(data)
    print(json.dumps({"checked": len(reports), "reports": reports}, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Monitor arXiv for new papers.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list")
    p_add = sub.add_parser("add")
    p_add.add_argument("name")
    p_add.add_argument("--query")
    p_add.add_argument("--category")
    p_add.add_argument("--max", type=int, default=30)
    p_rm = sub.add_parser("remove")
    p_rm.add_argument("name")
    p_reset = sub.add_parser("reset")
    p_reset.add_argument("name")
    p_check = sub.add_parser("check")
    p_check.add_argument("name")
    sub.add_parser("check-all")

    args = parser.parse_args()
    handlers = {
        "list": cmd_list,
        "add": cmd_add,
        "remove": cmd_remove,
        "reset": cmd_reset,
        "check": cmd_check,
        "check-all": cmd_check_all,
    }
    return handlers[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
