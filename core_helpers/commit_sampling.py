"""
Commit Sampling (PBT / fuzz): complete the COMMITS-surface timeline where the original
search hit GitHub's 1,000-result cap
=====================================================================================
The original search split each keyword's commit search into date ranges of ~95 days
(SLICE_MAX_DEPTH); ranges with more than 1,000 results returned only the first 1,000
("capped"). Outside the capped ranges the collected data is complete. Inside them this
script estimates — or, with --exhaustive, recounts exactly — two figures:

  agent     share of relevant commits with an AI-agent authorship line, per year
            (default 2025, 2026; target ±3 percentage points at 95% confidence)
  adoption  repositories whose FIRST relevant commit falls in each year (T8),
            per year (target ±10% relative at 95% confidence, --target to change)

Method (stratified random time-window sampling — the API cannot return random results):
  * strata = the capped date ranges of all kept search keywords (from search.log),
    merged and split at year boundaries;
  * each stratum is cut into equal time windows sized for ~250 results; windows are
    taken in a seeded random order and downloaded COMPLETELY with one query that ORs
    all kept phrases (a window with >1,000 results is split further);
  * results are de-duplicated by commit SHA (fork copies; the copy in the repository
    with the lowest ID is kept) and filtered with the technique phrase regexes;
  * adoption: a repository found in a window counts if no relevant commit exists in it
    before the window — checked with one repo-scoped search (`repo:owner/name …`);
    repositories whose first commit lies outside the capped ranges are checked on a
    random sample when an earlier capped range could hide an earlier commit;
  * estimates are stratified (Horvitz–Thompson) with 95% confidence intervals; the
    sample grows in rounds until the target precision is met, every window is taken,
    or --max-hours is reached. Everything is saved as it goes; rerun to continue.

Commands (search API, ~24 requests/min on one token) — via non_code_specialised_analysis.py:
  --commit-sampling estimate -t fuzz                     pilot + time projection (~5–15 min)
  --commit-sampling agent    -t fuzz                     agent share 2025–2026
  --commit-sampling adoption -t fuzz --target 0.2        first-commit repos per year
  --commit-sampling adoption -t pbt --exhaustive         exact recount of the capped ranges
  … --years 2020 2021  (limit years)   --max-hours 3  (stop after ~3 h; rerun continues)

Output: results/<slug>/commit_sample/ (strata.json, windows.jsonl, checks.jsonl,
estimates.json). `python specialised_report.py -t <x>` picks them up.
"""

from __future__ import annotations

import json
import math
import random
import re
import statistics
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from core_helpers import config as cfg
from core_helpers.keyword_matcher import TechniqueMatcher
from core_helpers.utils import resolve_technique, technique_dirs, load_json, save_json, setup_logging, gh_get

SEED              = 20261011
TARGET_RESULTS    = 250            # expected GitHub results per window
MIN_WINDOW        = timedelta(seconds=60)
CAP               = 1000
REQ_PER_MIN       = 60 / cfg.RATE_LIMIT_PAUSE
AGENT_YEARS       = [2025, 2026]
COMMITS_URL       = f"{cfg.GITHUB_API_BASE}/search/commits"

# One query per technique: all kept phrases ORed (GitHub allows ≤5 OR operators). For fuzz,
# the five "X fuzzing" concept phrases all contain "fuzzing", so they are covered by it.
QUERIES = {
    "property_based_testing": '"property-based testing" OR "property-based test" OR "property-based tests" OR '
                              '"property based testing" OR "property based test" OR "property based tests"',
    "fuzz_testing":           '"fuzzing" OR "fuzz test" OR "fuzz testing" OR "fuzz target" OR "fuzz harness" OR "fuzz corpus"',
}

_LOG_FETCH = re.compile(r"COMMITS fetch q='(.*?)': total_count=(\d+), retrieved=(\d+)")
_LOG_DATES = re.compile(r"committer-date:(\d{4}-\d\d-\d\d)\.\.(\d{4}-\d\d-\d\d)")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utc(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        d = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)


def _iso(d: datetime) -> str:
    return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _base_kw(q: str) -> str:
    m = re.match(r'\s*("[^"]+")', q or "")
    return m.group(1) if m else ""


class Store:
    """results/<slug>/commit_sample/: strata.json + append-only JSONL records (resumable)."""

    def __init__(self, slug: str) -> None:
        self.slug = slug
        self.dirs = technique_dirs(slug)
        self.dir = self.dirs["base"] / "commit_sample"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.requests = 0

    def path(self, name: str) -> Path:
        return self.dir / name

    def read_jsonl(self, name: str) -> list[dict]:
        p = self.path(name)
        out = []
        if p.exists():
            for line in p.read_text(encoding="utf-8").splitlines():
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    pass                                   # torn last line after a crash
        return out

    def append(self, name: str, rec: dict) -> None:
        with open(self.path(name), "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def get(self, params: dict, logger) -> dict:
        """Search request that never gives up on rate limits: gh_get raises after 5 attempts
        (e.g. repeated secondary-limit 403s); wait longer and try again instead of crashing."""
        self.requests += 1
        for attempt in range(30):
            try:
                return gh_get(COMMITS_URL, params=params, delay=cfg.RATE_LIMIT_PAUSE, logger=logger)
            except RuntimeError as exc:
                wait = min(60 * (attempt + 1), 900)
                logger.warning(f"{exc} — waiting {wait}s and retrying")
                print(f"  rate limited / API error — waiting {wait}s (attempt {attempt + 1}) …")
                time.sleep(wait)
        raise RuntimeError("GitHub search kept failing for ~4 hours — check the token / network, then rerun.")


# ---------------------------------------------------------------------------
# Strata (capped date ranges from search.log)
# ---------------------------------------------------------------------------

def capped_ranges(slug: str, dirs: dict) -> list[tuple[datetime, datetime]]:
    excl = set(((load_json(cfg.INPUTS_DIR / "comparison_keywords.json", {}) or {}).get(slug) or {})
               .get("exclude_search_keywords", []))
    last: dict[str, tuple[int, int]] = {}
    with open(dirs["base"] / "search.log", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            m = _LOG_FETCH.search(line)
            if m:
                last[m.group(1)] = (int(m.group(2)), int(m.group(3)))
    out = []
    for q, (tot, got) in last.items():
        d = _LOG_DATES.search(q)
        if d and _base_kw(q) not in excl and tot > got and got >= CAP - 10:
            a = datetime.fromisoformat(d.group(1)).replace(tzinfo=timezone.utc)
            b = datetime.fromisoformat(d.group(2)).replace(tzinfo=timezone.utc) + timedelta(days=1)
            out.append((a, b))
    return sorted(out)


def build_strata(store: Store, logger) -> dict:
    """Merge capped ranges, split at year boundaries, probe the combined query's total per
    stratum (1 request each) and cut each stratum into windows. Cached in strata.json."""
    cached = load_json(store.path("strata.json"), None)
    if cached:
        return cached
    merged: list[list[datetime]] = []
    for a, b in capped_ranges(store.slug, store.dirs):
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    pieces = []
    for a, b in merged:
        while a < b:
            ny = datetime(a.year + 1, 1, 1, tzinfo=timezone.utc)
            pieces.append((a, min(b, ny)))
            a = min(b, ny)
    q = QUERIES[store.slug]
    strata = []
    for i, (a, b) in enumerate(pieces):
        data = store.get({"q": f"{q} committer-date:{_iso(a)}..{_iso(b - timedelta(seconds=1))}", "per_page": 1}, logger)
        total = data.get("total_count", 0)
        n = max(1, math.ceil(total / TARGET_RESULTS))
        strata.append({"id": i, "start": _iso(a), "end": _iso(b), "year": a.year, "total": total,
                       "n_windows": n, "window_s": (b - a).total_seconds() / n})
        print(f"  stratum {i}: {_iso(a)[:10]} .. {_iso(b)[:10]}  GitHub total {total:,}  -> {n:,} windows")
    out = {"query": q, "created_at": _iso(datetime.now(timezone.utc)), "strata": strata}
    save_json(store.path("strata.json"), out)
    return out


def window_order(stratum: dict) -> list[int]:
    order = list(range(stratum["n_windows"]))
    random.Random(f"{SEED}-{stratum['id']}").shuffle(order)
    return order


def window_bounds(stratum: dict, idx: int) -> tuple[datetime, datetime]:
    a = _utc(stratum["start"])
    s = timedelta(seconds=stratum["window_s"])
    end = _utc(stratum["end"])
    return a + s * idx, min(a + s * (idx + 1), end)


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------

def fetch_range(store: Store, q: str, a: datetime, b: datetime, logger) -> tuple[list[dict], int, bool]:
    """All commits in [a, b): (items, GitHub total, truncated). Splits when > 1,000 results."""
    rng = f"committer-date:{_iso(a)}..{_iso(b - timedelta(seconds=1))}"
    items, page, total = [], 1, None
    while True:
        data = store.get({"q": f"{q} {rng}", "per_page": 100, "page": page}, logger)
        if total is None:
            total = data.get("total_count", 0)
            if total > CAP and (b - a) > MIN_WINDOW:
                mid = a + (b - a) / 2
                i1, t1, x1 = fetch_range(store, q, a, mid, logger)
                i2, t2, x2 = fetch_range(store, q, mid, b, logger)
                return i1 + i2, t1 + t2, x1 or x2
        got = data.get("items", [])
        items += got
        if not got or page * 100 >= min(total, CAP):
            break
        page += 1
    return items, total, total > CAP


def _digest(items: list[dict], matcher: TechniqueMatcher) -> tuple[list[dict], int]:
    """De-duplicate by SHA (keep the copy in the lowest repository ID); keep relevant commits."""
    from report_helpers.sections_aggregate import strip_agent_lines
    by_sha: dict[str, dict] = {}
    for it in items:
        repo = it.get("repository") or {}
        rid = repo.get("id") or 0
        sha = it.get("sha")
        if sha and (sha not in by_sha or rid < by_sha[sha]["repo_id"]):
            c = it.get("commit") or {}
            by_sha[sha] = {"sha": sha, "repo": repo.get("full_name"), "repo_id": rid,
                           "date": (c.get("committer") or {}).get("date") or (c.get("author") or {}).get("date"),
                           "message": c.get("message") or ""}
    rel = []
    for c in by_sha.values():
        text, agent = strip_agent_lines(c.pop("message"))
        if matcher.total(matcher.scan_text(text)[0]) > 0:
            c.update(agent=agent, msg=re.sub(r"\s+", " ", text)[:200])
            rel.append(c)
    return rel, len(by_sha)


def sample_windows(store: Store, strata: list[dict], target: dict[int, int], done: dict, matcher, logger,
                   budget: int) -> bool:
    """Take windows (seeded order) until each stratum has target[id] windows. False if out of budget."""
    q = QUERIES[store.slug]
    for s in strata:
        have = done.setdefault(s["id"], {})
        for idx in window_order(s)[:target.get(s["id"], 0)]:
            if idx in have:
                continue
            if store.requests >= budget:
                return False
            a, b = window_bounds(s, idx)
            r0 = store.requests
            items, total, trunc = fetch_range(store, q, a, b, logger)
            commits, distinct = _digest(items, matcher)
            rec = {"stratum": s["id"], "index": idx, "start": _iso(a), "end": _iso(b), "results": total,
                   "retrieved": len(items), "distinct": distinct, "truncated": trunc,
                   "requests": store.requests - r0, "commits": commits}
            store.append("windows.jsonl", rec)
            have[idx] = rec
    return True


def check_repo(store: Store, repo: str, before: datetime, matcher, logger) -> dict:
    """Does `repo` have a relevant commit before `before`? Repo-scoped search, messages verified."""
    from report_helpers.sections_aggregate import strip_agent_lines
    q = f"repo:{repo} {QUERIES[store.slug]} committer-date:<{_iso(before)}"
    r0, found, total, page = store.requests, False, 0, 1
    while not found:
        try:
            data = store.get({"q": q, "per_page": 100, "page": page}, logger)
        except Exception as exc:                            # e.g. 422 for a deleted / renamed repository
            rec = {"repo": repo, "before": _iso(before), "error": str(exc)[:200], "requests": store.requests - r0}
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status in (404, 422):
                # Permanent: record it so it is not re-asked every round (that kept the year
                # "not enough data" forever). Unverifiable → not counted as a first commit.
                rec["earlier"] = None
                store.append("checks.jsonl", rec)
                logger.info(f"check {repo}: HTTP {status}, treated as not verifiable")
            return rec
        total = data.get("total_count", 0)
        items = data.get("items", [])
        found = any(matcher.total(matcher.scan_text(strip_agent_lines((it.get("commit") or {}).get("message") or "")[0])[0]) > 0
                    for it in items)
        if not items or page * 100 >= min(total, CAP):
            break
        page += 1
    rec = {"repo": repo, "before": _iso(before), "earlier": found, "total": total, "requests": store.requests - r0}
    store.append("checks.jsonl", rec)
    return rec


# ---------------------------------------------------------------------------
# Existing (complete) data outside the capped ranges
# ---------------------------------------------------------------------------

def existing_outside(store: Store, strata: list[dict]) -> list[dict]:
    """Relevant commits from the original search that lie outside every capped range."""
    iv = [(_utc(s["start"]), _utc(s["end"])) for s in strata]
    out = []
    for it in load_json(store.dirs["base"] / "filtered" / "commits.json", []) or []:
        d = _utc(it.get("committer_date") or it.get("created_at"))
        if not it.get("_rel") or d is None or any(a <= d < b for a, b in iv):
            continue
        out.append({"sha": it.get("id"), "repo": it.get("repo_full_name"), "date": _iso(d), "year": d.year,
                    "agent": bool(it.get("_agent"))})
    return out


# ---------------------------------------------------------------------------
# Estimation
# ---------------------------------------------------------------------------

def _first_info(store: Store, strata: list[dict], done: dict, existing: list[dict]):
    """Per repository: earliest known relevant commit (existing data or sampled windows)."""
    first: dict[str, datetime] = {}
    for c in existing:
        d = _utc(c["date"])
        if c["repo"] not in first or d < first[c["repo"]]:
            first[c["repo"]] = d
    for wins in done.values():
        for w in wins.values():
            for c in w["commits"]:
                d = _utc(c["date"])
                if d and (c["repo"] not in first or d < first[c["repo"]]):
                    first[c["repo"]] = d
    return first


def _strata_complete_before(strata: list[dict], done: dict, t: datetime) -> bool:
    """True if every capped range starting before t has been downloaded completely."""
    return all(len(done.get(s["id"], {})) >= s["n_windows"] for s in strata if _utc(s["start"]) < t)


def _check_key(repo: str, before: datetime) -> str:
    return f"{repo}|{_iso(before)}"


def needed_checks(strata, done, existing, checks: dict, years: list[int], cand_frac: float) -> list[tuple[str, datetime]]:
    """Repo checks needed: every repo in a sampled window (unless provable from complete data),
    plus a seeded random fraction of the 'first commit outside capped ranges' candidates."""
    first = _first_info(None, strata, done, existing)
    need = []
    by_id = {s["id"]: s for s in strata}
    for sid, wins in done.items():
        if by_id[sid]["year"] not in years:
            continue
        for w in wins.values():
            a = _utc(w["start"])
            for repo in {c["repo"] for c in w["commits"]}:
                if first.get(repo) and first[repo] < a:
                    continue                                   # known earlier relevant commit
                if _strata_complete_before(strata, done, a):
                    continue                                   # complete data before → provably first
                if _check_key(repo, a) not in checks:
                    need.append((repo, a))
    for y, cands in candidates_by_year(strata, done, existing, years).items():
        n = math.ceil(len(cands) * cand_frac)
        for repo, t in cands[:n]:
            if _check_key(repo, t) not in checks:
                need.append((repo, t))
    return need


def existing_first(strata, done, existing) -> dict[str, datetime]:
    """Repos whose earliest known relevant commit is one from the original (complete) data."""
    first = _first_info(None, strata, done, existing)
    ex_first: dict[str, datetime] = {}
    for c in existing:
        d = _utc(c["date"])
        if first.get(c["repo"]) == d:
            ex_first[c["repo"]] = d
    return ex_first


def candidates_by_year(strata, done, existing, years) -> dict[int, list[tuple[str, datetime]]]:
    """Repos whose earliest known relevant commit is outside the capped ranges and preceded by a
    not-fully-downloaded capped range (so an earlier commit may be hidden). Seeded random order."""
    ex_first = existing_first(strata, done, existing)
    out: dict[int, list] = defaultdict(list)
    for repo, t in sorted(ex_first.items()):
        if t.year in years and not _strata_complete_before(strata, done, t):
            out[t.year].append((repo, t))
    for y in out:
        random.Random(f"{SEED}-cand-{y}").shuffle(out[y])
    return out


def compute_estimates(slug: str) -> dict:
    """Agent share and adopting repos per year with 95% CIs, from everything sampled so far."""
    store = Store(slug)
    sj = load_json(store.path("strata.json"), None)
    if not sj:
        return {}
    strata = sj["strata"]
    done: dict = defaultdict(dict)
    for w in store.read_jsonl("windows.jsonl"):
        done[w["stratum"]][w["index"]] = w
    checks = {_check_key(c["repo"], _utc(c["before"])): c for c in store.read_jsonl("checks.jsonl") if "earlier" in c}
    existing = existing_outside(store, strata)
    first = _first_info(store, strata, done, existing)
    years = sorted({s["year"] for s in strata} | {c["year"] for c in existing})
    by_year_strata = defaultdict(list)
    for s in strata:
        by_year_strata[s["year"]].append(s)

    def strat_total(y: int, val) -> tuple[float, float, bool]:
        """Σ_s M_s/m_s Σ val(w), variance, ok (every stratum has ≥2 windows or is complete)."""
        est = var = 0.0
        ok = True
        for s in by_year_strata[y]:
            ws = list(done.get(s["id"], {}).values())
            M, m = s["n_windows"], len(ws)
            if m == 0 or (m < 2 and m < M):
                ok = False
                continue
            vals = [val(w) for w in ws]
            est += M / m * sum(vals)
            if m < M:
                var += M * M * (1 - m / M) * statistics.variance(vals) / m
        return est, var, ok

    out = {"query": sj["query"], "strata": len(strata), "windows_sampled": sum(len(v) for v in done.values()),
           "windows_total": sum(s["n_windows"] for s in strata), "checks": len(checks),
           "requests": sum(w["requests"] for v in done.values() for w in v.values())
                       + sum(c.get("requests", 0) for c in checks.values()),
           "agent": {}, "adoption": {}}

    # ---- agent share --------------------------------------------------------------------
    for y in years:
        ex = [c for c in existing if c["year"] == y]
        R_e, A_e = len(ex), sum(c["agent"] for c in ex)
        if not by_year_strata[y]:
            if R_e:
                out["agent"][y] = {"share": A_e / R_e, "ci": 0.0, "relevant_est": R_e, "exact": True}
            continue
        R, vR, okR = strat_total(y, lambda w: len(w["commits"]))
        A, _, _ = strat_total(y, lambda w: sum(c["agent"] for c in w["commits"]))
        if not okR or (R + R_e) == 0:
            continue
        p = (A + A_e) / (R + R_e)
        _, vz, _ = strat_total(y, lambda w: sum(c["agent"] for c in w["commits"]) - p * len(w["commits"]))
        out["agent"][y] = {"share": p, "ci": 1.96 * math.sqrt(vz) / (R + R_e), "relevant_est": R + R_e,
                           "exact": vz == 0 and all(len(done.get(s["id"], {})) >= s["n_windows"] for s in by_year_strata[y])}

    # ---- adoption -----------------------------------------------------------------------
    def is_first(repo: str, a: datetime) -> bool | None:
        if first.get(repo) and first[repo] < a:
            return False
        if _strata_complete_before(strata, done, a):
            return True
        c = checks.get(_check_key(repo, a))
        return None if c is None else c["earlier"] is False

    cands = candidates_by_year(strata, done, existing, years)
    ex_first = existing_first(strata, done, existing)
    for y in years:
        # Part 1: repos whose earliest known commit is outside the capped ranges.
        ex_repos = {r for r, t in ex_first.items() if t.year == y}
        cy = cands.get(y, [])
        cset = {r for r, _ in cy}
        certain = len(ex_repos - cset)
        checked = [(r, t) for r, t in cy if _check_key(r, t) in checks]
        if cy and not checked:
            continue
        k = sum(checks[_check_key(r, t)]["earlier"] is False for r, t in checked)
        n, N = len(checked), len(cy)
        p1 = k / n if n else 0.0
        est1 = certain + N * p1
        var1 = N * N * (1 - n / N) * p1 * (1 - p1) / max(n - 1, 1) if N and n < N else 0.0

        # Part 2: sampled windows in capped ranges (repo's earliest relevant commit in the window).
        pending = False

        def adopters(w):
            nonlocal pending
            a = _utc(w["start"])
            cnt = 0
            for repo in {c["repo"] for c in w["commits"]}:
                f = is_first(repo, a)
                if f is None:
                    pending = True
                cnt += bool(f)
            return cnt
        est2, var2, ok2 = strat_total(y, adopters) if by_year_strata[y] else (0.0, 0.0, True)
        if not ok2 or pending:
            continue
        est, var = est1 + est2, var1 + var2
        out["adoption"][y] = {"estimate": est, "ci": 1.96 * math.sqrt(var), "rel_ci": (1.96 * math.sqrt(var) / est) if est else None,
                              "exact": var == 0, "outside_capped": est1, "inside_capped": est2}
    save_json(store.path("estimates.json"), {**out, "computed_at": _iso(datetime.now(timezone.utc))})
    return out


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def _year_met(est: dict, mode: str, y: int, target: float) -> bool:
    e = est[mode].get(y)
    if e is None:
        return False
    if mode == "agent":
        return e["ci"] <= target
    return not e["estimate"] or e["ci"] / e["estimate"] <= target


def _targets_met(est: dict, mode: str, years: list[int], target: float) -> bool:
    return all(_year_met(est, mode, y, target) for y in years)


def run(mode: str, slug: str, years: list[int] | None, target: float, exhaustive: bool, max_hours: float,
        start_frac: float = 0.02) -> None:
    logger = setup_logging(slug, f"commit_sampling_{mode}")
    store = Store(slug)
    matcher = TechniqueMatcher(slug)
    strata = build_strata(store, logger)["strata"]
    budget = int(max_hours * 60 * REQ_PER_MIN) if max_hours else 10 ** 9
    if mode == "agent":
        years = years or AGENT_YEARS
    else:
        years = years or sorted({s["year"] for s in strata} | set(range(min(s["year"] for s in strata), 2027)))
    scope = [s for s in strata if s["year"] in years]
    done: dict = defaultdict(dict)
    for w in store.read_jsonl("windows.jsonl"):
        done[w["stratum"]][w["index"]] = w
    print(f"{slug} {mode}: years {years}, {len(scope)} capped ranges, {sum(s['n_windows'] for s in scope):,} windows; "
          f"already sampled {sum(len(done.get(s['id'], {})) for s in scope):,}; budget "
          f"{'none' if budget >= 10 ** 9 else f'{budget:,} requests (~{max_hours} h)'}")
    # Sampling fraction per year: a year that already meets the target is not sampled further
    # (growing every year together wasted hours re-sampling years that were already precise).
    frac = {y: 1.0 if exhaustive else max(start_frac, max((len(done.get(s["id"], {})) / s["n_windows"]
                                                           for s in scope if s["year"] == y), default=0))
            for y in years}
    existing = existing_outside(store, strata)
    t0 = time.time()
    while True:
        tgt = {s["id"]: min(s["n_windows"], max(2, math.ceil(frac[s["year"]] * s["n_windows"]))) for s in scope}
        ok = sample_windows(store, scope, tgt, done, matcher, logger, budget)
        if ok and mode == "adoption":
            checks = {_check_key(c["repo"], _utc(c["before"])): c for c in store.read_jsonl("checks.jsonl") if "earlier" in c}
            top = max(frac.values())
            cand_frac = 1.0 if top >= 1.0 else min(1.0, max(0.05, top * 4))
            for repo, a in needed_checks(strata, done, existing, checks, years, cand_frac):
                if store.requests >= budget:
                    ok = False
                    break
                check_repo(store, repo, a, matcher, logger)
        est = compute_estimates(slug)
        _print(est, mode, years, store.requests, time.time() - t0)
        grow = [y for y in years if not _year_met(est, mode, y, target) and frac[y] < 1.0]
        if not grow:
            print("Target precision reached." if _targets_met(est, mode, years, target) else "All windows downloaded (exact).")
            break
        if not ok:
            print("Budget reached — rerun the same command to continue.")
            break
        for y in grow:
            # CI shrinks ~ 1/sqrt(windows): grow just enough to reach the target (+15% margin), at most x1.6.
            e = est[mode].get(y)
            rel = (e["ci"] / target if mode == "agent" else (e.get("rel_ci") or 0) / target) if e else 0
            frac[y] = min(1.0, frac[y] * (min(1.6, max(1.15, 1.15 * rel * rel)) if rel else 1.6))
        print(f"  next round samples more windows for: {', '.join(map(str, grow))}")
    print(f"Saved: {store.dir}. Next: python specialised_report.py -t {cfg.TECHNIQUE_INPUT_PREFIXES[slug]}")


def _print(est: dict, mode: str, years: list[int], req: int, secs: float) -> None:
    print(f"  [{req:,} requests this run, {secs / 60:.0f} min] windows {est['windows_sampled']:,}/{est['windows_total']:,}, "
          f"repo checks {est['checks']:,}")
    for y in years:
        e = est[mode].get(y)
        if e is None:
            print(f"    {y}: not enough data yet")
        elif mode == "agent":
            print(f"    {y}: agent share {e['share'] * 100:.1f}% ± {e['ci'] * 100:.1f} pp")
        else:
            print(f"    {y}: repos with first technique commit ~ {e['estimate']:,.0f} ± {e['ci']:,.0f}"
                  + (f" (±{e['rel_ci'] * 100:.0f}%)" if e.get("rel_ci") else ""))


def estimate_time(slug: str, pilot: int, target_agent: float, target_adopt: list[float],
                  only_years: list[int] | None = None) -> None:
    """Pilot: probe the capped ranges, sample `pilot` windows per year, check their repos, and
    project the requests (and hours) needed for each target. Pilot windows are reused later."""
    logger = setup_logging(slug, "commit_sampling_estimate")
    store = Store(slug)
    matcher = TechniqueMatcher(slug)
    strata = build_strata(store, logger)["strata"]
    done: dict = defaultdict(dict)
    for w in store.read_jsonl("windows.jsonl"):
        done[w["stratum"]][w["index"]] = w
    years = sorted({s["year"] for s in strata if not only_years or s["year"] in only_years})
    by_year = defaultdict(list)
    for s in strata:
        by_year[s["year"]].append(s)
    for y in years:                                  # ≥2 windows per stratum, ≥pilot per year
        tot = sum(s["n_windows"] for s in by_year[y])
        tgt = {s["id"]: min(s["n_windows"], max(2, math.ceil(pilot * s["n_windows"] / tot))) for s in by_year[y]}
        sample_windows(store, by_year[y], tgt, done, matcher, logger, 10 ** 9)
    existing = existing_outside(store, strata)
    checks = {_check_key(c["repo"], _utc(c["before"])): c for c in store.read_jsonl("checks.jsonl") if "earlier" in c}
    for repo, a in needed_checks(strata, done, existing, checks, years, 0.0):
        check_repo(store, repo, a, matcher, logger)
    checks = {_check_key(c["repo"], _utc(c["before"])): c for c in store.read_jsonl("checks.jsonl") if "earlier" in c}
    est = compute_estimates(slug)
    cands = candidates_by_year(strata, done, existing, sorted(set(years) | set(range(min(years), 2027))))
    req_check = statistics.mean([c.get("requests", 1) for c in checks.values()] or [1])

    first = _first_info(store, strata, done, existing)
    rows, tot = [], Counter()
    print(f"\n{slug}: pilot used {store.requests:,} requests. Projection at {REQ_PER_MIN:.0f} requests/min "
          "(one token). Rough: based on few windows per year.\n")
    head = f"{'Year':>5} {'windows':>8} {'req/win':>7} {'rel/win':>7} {'adopt/win':>9} | {'agent ±3pp':>10} | " + \
           " | ".join(f"{'adoption ±' + str(int(t * 100)) + '%':>15}" for t in target_adopt) + f" | {'exhaustive':>10}"
    print(head)
    for y in years:
        ws = [w for s in by_year[y] for w in done.get(s["id"], {}).values()]
        M = sum(s["n_windows"] for s in by_year[y])
        rpw = statistics.mean([w["requests"] for w in ws])
        rel = [len(w["commits"]) for w in ws]
        adopt = []
        chk = []
        for w in ws:
            a = _utc(w["start"])
            repos = {c["repo"] for c in w["commits"]}
            k = 0
            nchk = 0
            for r in repos:
                if first.get(r) and first[r] < a:
                    continue
                c = checks.get(_check_key(r, a))
                nchk += c is not None
                k += c is not None and c["earlier"] is False
            adopt.append(k)
            chk.append(nchk)
        cpw = statistics.mean(chk) * req_check
        mrel = statistics.mean(rel) or 1e-9
        # agent: n relevant commits for ±target at p=0.5 (worst case), design effect 1.5
        need_rel = 1.5 * Z(0.5, target_agent)
        w_agent = min(M, math.ceil(need_rel / mrel)) if y in AGENT_YEARS else 0
        r_agent = w_agent * rpw
        cols = []
        for t in target_adopt:
            ma, sa = statistics.mean(adopt), (statistics.stdev(adopt) if len(adopt) > 1 else 0)
            if ma <= 0:
                cols.append(None)
                continue
            n = min(M, math.ceil((1.96 * max(sa, math.sqrt(ma)) / (t * ma)) ** 2))
            r = n * (rpw + cpw) + _cand_checks(len(cands.get(y, [])), t) * req_check
            cols.append(r)
            tot[t] += r
        r_ex = M * rpw                     # exhaustive: complete data, first commits need no repo checks
        tot["agent"] += r_agent
        tot["exhaustive"] += r_ex
        fmt = lambda r: "n/a" if r is None else f"{r / REQ_PER_MIN / 60:.1f} h"
        print(f"{y:>5} {M:>8,} {rpw:>7.1f} {mrel:>7.1f} {statistics.mean(adopt):>9.2f} | "
              f"{(fmt(r_agent) if y in AGENT_YEARS else '-'):>10} | " + " | ".join(f"{fmt(r):>15}" for r in cols)
              + f" | {fmt(r_ex):>10}")
    for y in sorted(set(cands) - set(years)):               # years without capped ranges: checks only
        for t in target_adopt:
            tot[t] += _cand_checks(len(cands[y]), t) * req_check
    print(f"{'TOTAL':>5} {'':>8} {'':>7} {'':>7} {'':>9} | {tot['agent'] / REQ_PER_MIN / 60:>8.1f} h | "
          + " | ".join(f"{tot[t] / REQ_PER_MIN / 60:>13.1f} h" for t in target_adopt)
          + f" | {tot['exhaustive'] / REQ_PER_MIN / 60:>8.1f} h")
    print("\n'n/a' = no adopting repository in the pilot windows for that year (cannot project; run more windows "
          "with `adoption --max-hours 0.5 --years Y`). Years without capped ranges need only repo checks for the "
          "earlier-commit test, included in the totals of the years above.")
    save_json(store.path("projection.json"), {"total_hours": {str(k): v / REQ_PER_MIN / 60 for k, v in tot.items()},
                                               "pilot_requests": store.requests, "estimates": est})


def _cand_checks(n_cand: int, rel: float, p: float = 0.8) -> int:
    """Checks needed so the 'really first' share p of n_cand candidates has ±rel relative precision."""
    if not n_cand:
        return 0
    n0 = 1.96 ** 2 * (1 - p) / (p * rel ** 2)
    return min(n_cand, math.ceil(n0 / (1 + (n0 - 1) / n_cand)))


def Z(p: float, moe: float) -> float:
    return 1.96 ** 2 * p * (1 - p) / moe ** 2
