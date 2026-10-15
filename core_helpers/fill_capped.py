"""
Re-collect search queries that hit GitHub's 1,000-result cap (--fill-capped)
============================================================================
search.py split each query by date until a piece had <900 results, but stopped at ~95-day
pieces (SLICE_MAX_DEPTH). Pieces that still had >1,000 results returned only 1,000. This step
finds those pieces in search.log ("<SURFACE> fetch q=…: total_count=T, retrieved=1000"),
re-runs them split into finer time ranges (down to minutes, with full timestamps) and merges
the new items into results/<slug>/search/<surface>.json exactly as search.py would.

Only kept search keywords are refilled (excluded ones, e.g. "@metamorphic", are skipped).
Resumable: finished pieces are recorded in search/capped_fill.json.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from core_helpers import config as cfg
from core_helpers.github_search import _dedup, _fetch_commits, _fetch_issues_prs, _probe_count
from core_helpers.technique_data import base_keyword, keyword_config
from core_helpers.utils import load_json, save_json, technique_dirs

_LINE = re.compile(r"(PR|ISSUE|COMMITS) fetch q='(.*)': total_count=(\d+), retrieved=(\d+)")
_RANGE = re.compile(r"\s(created|committer-date):(\d{4}-\d{2}-\d{2})\.\.(\d{4}-\d{2}-\d{2})")
_SURFACE = {"PR": "prs", "ISSUE": "issues", "COMMITS": "commits"}
_CAP = 1000
_MIN_SPAN = timedelta(minutes=1)


def capped_queries(slug: str) -> list[dict]:
    """Capped date-sliced queries of kept keywords, latest log line per query."""
    dirs = technique_dirs(slug)
    exclude = set(keyword_config(slug)["exclude"])
    found: dict[tuple, dict] = {}
    log = dirs["base"] / "search.log"
    if not log.exists():
        return []
    for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
        m = _LINE.search(line)
        if not m:
            continue
        kind, q, total, got = m.group(1), m.group(2), int(m.group(3)), int(m.group(4))
        r = _RANGE.search(q)
        if not r or got < _CAP or total <= got:
            continue
        q_kw = q[:r.start()].replace(" type:pr", "").replace(" type:issue", "").strip()
        if base_keyword(q_kw) in exclude:
            continue
        found[(kind, q_kw, r.group(2), r.group(3))] = {
            "surface": _SURFACE[kind], "keyword": q_kw, "qualifier": r.group(1),
            "start": r.group(2), "end": r.group(3), "total_before": total, "retrieved_before": got}
    return list(found.values())


def _ts(d: datetime) -> str:
    return d.strftime("%Y-%m-%dT%H:%M:%SZ")


def _fetch_piece(c: dict, a: datetime, b: datetime, logger, out: list, stats: dict) -> None:
    """Bisect [a, b] (inclusive, seconds) until each piece is under the cap, then fetch it."""
    rng = f"{c['qualifier']}:{_ts(a)}..{_ts(b)}"
    if c["surface"] == "commits":
        url, probe_q = f"{cfg.GITHUB_API_BASE}/search/commits", f"{c['keyword']} {rng}"
    else:
        kind = "pr" if c["surface"] == "prs" else "issue"
        url, probe_q = f"{cfg.GITHUB_API_BASE}/search/issues", f"{c['keyword']} type:{kind} {rng}"
    total = _probe_count(url, probe_q, logger)
    stats["requests"] += 1
    if total == 0:
        return
    if total > cfg.SLICE_THRESHOLD and b - a > _MIN_SPAN:
        mid = a + (b - a) / 2
        mid = mid.replace(microsecond=0)
        _fetch_piece(c, a, mid, logger, out, stats)
        _fetch_piece(c, mid + timedelta(seconds=1), b, logger, out, stats)
        return
    if c["surface"] == "commits":
        items, _ = _fetch_commits(f"{c['keyword']} {rng}", logger)
    else:
        items, _ = _fetch_issues_prs(f"{c['keyword']} {rng}", "pr" if c["surface"] == "prs" else "issue", logger)
    stats["requests"] += max(1, -(-len(items) // cfg.GITHUB_API_PER_PAGE))
    stats["pieces"] += 1
    if total > _CAP:
        stats["still_truncated"] += total - len(items)
        logger.warning(f"TRUNCATED SLICE (refill): {probe_q!r} | total={total} | got={len(items)}")
    out.extend(items)


def run(slug: str, logger) -> None:
    dirs = technique_dirs(slug)
    sdir = dirs["search"]
    state_path = sdir / "capped_fill.json"
    state = load_json(state_path, {}) or {}
    todo = capped_queries(slug)
    if not todo:
        print("No capped search queries of kept keywords found in search.log — nothing to refill.")
        return
    print(f"{len(todo)} capped search queries of kept keywords:")
    for c in todo:
        print(f"  {c['surface']:<8} {c['keyword']} {c['start']}..{c['end']}: {c['total_before']:,} results, "
              f"{c['retrieved_before']:,} collected")
    for c in todo:
        key = f"{c['surface']}|{c['keyword']}|{c['start']}|{c['end']}"
        if state.get(key, {}).get("done"):
            continue
        a = datetime.fromisoformat(c["start"]).replace(tzinfo=timezone.utc)
        b = datetime.fromisoformat(c["end"]).replace(tzinfo=timezone.utc) + timedelta(days=1, seconds=-1)
        stats = {"requests": 0, "pieces": 0, "still_truncated": 0}
        items: list[dict] = []
        print(f"Refilling {c['surface']} {c['keyword']} {c['start']}..{c['end']} …")
        _fetch_piece(c, a, b, logger, items, stats)
        # Same record format as search.py (matched_keyword = keyword + the original date range).
        for it in items:
            it["matched_keyword"] = f"{c['keyword']} {c['qualifier']}:{c['start']}..{c['end']}"
        path = sdir / f"{c['surface']}.json"
        data = load_json(path, []) or []
        data, added = _dedup(data, items)
        save_json(path, data)
        state[key] = {**c, **stats, "retrieved_now": len({str(i.get('id')) for i in items}), "new_items": added,
                      "done": True}
        save_json(state_path, state)
        logger.info(f"CAPPED REFILL {key}: retrieved {state[key]['retrieved_now']} (was {c['retrieved_before']}), "
                    f"new {added}, still truncated {stats['still_truncated']}")
        print(f"  retrieved {state[key]['retrieved_now']:,} (was {c['retrieved_before']:,}); {added:,} new items "
              f"added to {path.name}; {stats['requests']} requests"
              + (f"; still truncated: ~{stats['still_truncated']:,}" if stats["still_truncated"] else ""))
    print(f"Saved: {state_path}")
