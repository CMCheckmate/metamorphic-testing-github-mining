"""
Sections Aggregate
==================
Computes every number shown by sections_report.py and returns it as one dict stored
under overall.json["sections"] by analysis._aggregate_overall. sections_report.py only
renders it.

Sections (agreed scope, 2026-10-10):
  Search    S1 hits per surface · S2 distinct repos per surface · S3 size of analysed
            CODE repos (files / code files / lines of code) · S4 keywords with no results
  Analysis  A1 keyword hits (code + non-code) · A2 usage / non-usage / no hit · A3 code-file
            classification of usage repos · A4 non-usage file classification · A5 primary
            language (+ GitHub-wide normalisation) · A6 application domain · A7 word cloud
            from README + description
  Timeline  T8 repos adopting the technique per year · T9 commit activity (COMMITS surface
            only) incl. AI-agent checks

Population (agreed 2026-10-11): only VERIFIED results are reported. An item counts only if
  * it was found by a kept search keyword (inputs/comparison_keywords.json excludes e.g.
    "@metamorphic" = bare word "metamorphic"), and
  * non-CODE: its title/body contains a technique keyword; CODE: its repository's current
    snapshot has ≥1 technique hit.
Everything else is treated as not found and listed with the reason in
sections_excluded.md (build()["excluded"]). Raw GitHub hit counts (S1) cannot be filtered.

Non-code relevance is recomputed here from the raw search texts with the current
technique keywords (keyword_matcher.py), not taken from noncode_results.json.

Optional inputs (picked up when present, all in results/<slug>/analysis/):
  repo_readmes.json, github_language_baseline.json,
  commit_coverage_check.json (non_code_specialised_analysis.py), zero_hit_investigation.json
  (targeted_rescan.py --zero-hit, legacy records only).
"""

from __future__ import annotations

import bisect
import math
import random
import re
import statistics
from collections import Counter, defaultdict

from core_helpers import config as cfg
from core_helpers.keyword_matcher import TechniqueMatcher
from core_helpers.utils import load_json, load_search_keywords

SURFACES         = ["code", "repos", "commits", "prs", "issues", "discussions"]
NONCODE_SURFACES = ["repos", "commits", "prs", "issues", "discussions"]
SECTIONS_VERSION = 2
SAMPLE_SEED      = 20261010
README_MIN_DISTINCT = 3          # A6: distinct domain keywords a README needs to add that domain

# Lines that identify AI-coding-agent authorship (lower bound: some agents leave no trace).
_AGENT_LINE_RE = re.compile(
    r"co-authored-by:.*\b(?:claude|copilot|codex|cursor|devin|gemini|openai|anthropic|chatgpt|aider|"
    r"windsurf|cline|jules|openhands|amazon q)\b"
    r"|generated (?:with|by) \[?(?:claude|codex|cursor|copilot|gemini|aider)"
    r"|claude\.(?:ai|com)/(?:code|claude-code)|noreply@anthropic\.com|copilot-swe-agent|🤖",
    re.I,
)
# Agent/process vocabulary used to measure word-cloud noise (A7 verification).
PROCESS_WORDS = {"claude", "anthropic", "codex", "copilot", "cursor", "gate", "gates", "deterministic",
                 "contract", "contracts", "invariant", "invariants", "boundary", "fixture", "fixtures",
                 "baseline", "drift", "policy", "acceptance", "state", "shape", "canonical", "identical",
                 "unchanged", "bounded"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def base_keyword(kw: str) -> str:
    """'"metamorphic testing" size:0..781' -> '"metamorphic testing"'."""
    m = re.match(r'\s*("[^"]+")', kw or "")
    return m.group(1) if m else (kw or "").split(" ")[0]


def _ranked(counter, n: int | None = None) -> list[tuple]:
    """Counter.most_common with ties broken by key, so identical data gives identical reports
    (most_common keeps insertion order, which follows Python's randomised set iteration)."""
    items = sorted(counter.items(), key=lambda kv: (-kv[1], str(kv[0])))
    return items[:n] if n is not None else items


def stats(vals: list[float]) -> dict:
    if not vals:
        return {"n": 0}
    if len(vals) >= 2:
        q1, _, q3 = statistics.quantiles(vals, n=4, method="inclusive")
    else:
        q1 = q3 = vals[0]
    return {"n": len(vals), "min": min(vals), "p25": q1, "median": statistics.median(vals),
            "mean": statistics.mean(vals), "p75": q3, "max": max(vals),
            "stdev": statistics.stdev(vals) if len(vals) >= 2 else 0.0, "sum": sum(vals)}


def strip_agent_lines(text: str) -> tuple[str, bool]:
    kept, agent = [], False
    for line in (text or "").splitlines():
        if _AGENT_LINE_RE.search(line):
            agent = True
        else:
            kept.append(line)
    return "\n".join(kept), agent


_URL_RE = re.compile(r"https?://\S+|www\.\S+|\b\S+@\S+\.\w+")
# Word endings a domain keyword may take (cryptograph → cryptography/cryptographic,
# simulation → simulations) without matching unrelated longer words (express ↛ expression).
_DOMAIN_SUFFIX = r"(?:s|es|ing|ed|er|ers|y|ies|ic|ics|al|ally)?"


def domain_patterns() -> dict[str, re.Pattern]:
    """Whole-word matching with a small set of inflections; apply to text passed through strip_urls()."""
    pats = {}
    for dom, kws in cfg.DOMAIN_KEYWORDS.items():
        parts = [rf"\b{re.escape(k.lower())}{_DOMAIN_SUFFIX}\b" for k in kws]
        pats[dom] = re.compile("|".join(parts), re.I)
    return pats


def strip_urls(text: str) -> str:
    """URLs and e-mail addresses contain words like 'http', 'api' or 'docs' that are not domain evidence."""
    return _URL_RE.sub(" ", text or "")


def _year(ts) -> int | None:
    return int(ts[:4]) if isinstance(ts, str) and len(ts) >= 4 and ts[:4].isdigit() else None


def _item_kws(it: dict) -> set[str]:
    return {base_keyword(k) for k in (it.get("matched_keywords") or [it.get("matched_keyword", "")]) if k}


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def build(slug: str, dirs: dict, summaries: list[dict], noncode: list[dict], meta: dict, rctx,
          code_status: dict | None = None) -> dict:
    sd, ad = dirs["search"], dirs["analysis"]
    items   = {s: load_json(sd / f"{s}.json", []) or [] for s in SURFACES}
    summary = load_json(sd / "summary.json", {}) or {}
    excl    = set(((load_json(cfg.INPUTS_DIR / "comparison_keywords.json", {}) or {}).get(slug) or {})
                  .get("exclude_search_keywords", []))
    matcher = TechniqueMatcher(slug)
    all_summaries = summaries
    summaries = [r for r in all_summaries if r["total_specific"] > 0]     # verified CODE repos only
    code_ok = {r["full_name"] for r in summaries}

    # Per-item flags: found (by ≥1 kept search keyword); relevant (title/body contains a technique
    # keyword); comparable = found AND verified (non-CODE: relevant; CODE: repo has hits now).
    # Every section uses `comparable`, so unverified results are treated as not found.
    flags: dict[tuple[str, str], dict] = {}
    for s in SURFACES:
        for it in items[s]:
            kws  = _item_kws(it)
            found = not (excl and kws and kws <= excl)
            f = {"found": found, "kws": kws}
            if s != "code":
                text, agent = strip_agent_lines(f"{it.get('title') or ''}\n{it.get('body') or ''}")
                hits, _ = matcher.scan_text(text)
                f.update(relevant=matcher.total(hits) > 0, hits=hits, agent=agent, text=text)
                f["comparable"] = found and f["relevant"]
            else:
                f["comparable"] = found and it.get("repo_full_name") in code_ok
            flags[(s, str(it.get("id")))] = f
    fl = lambda s, it: flags[(s, str(it.get("id")))]

    out: dict = {"version": SECTIONS_VERSION, "exclude_keywords": sorted(excl)}
    out["s1"] = _s1(summary, items, fl, excl)
    out["s2"] = _s2(items, fl, summaries)
    out["s3"] = _s3(summaries)
    out["s4"] = _s4(slug, summary, items, excl, fl)
    out["a1"] = _a1(summaries, items, fl, matcher)
    out["a2"] = _a2(all_summaries, code_status or {}, load_json(ad / "zero_hit_investigation.json", {}) or {})
    out["a3"] = _a3(summaries, rctx)
    out["a4"] = _a4(summaries)
    out["a5"] = _a5(summaries, items, fl, meta, load_json(ad / "github_language_baseline.json", {}) or {},
                    set((code_status or {}).get("gone_repos", [])))
    out["a6"], out["a7"] = _a6_a7(slug, items, fl, meta, load_json(ad / "repo_readmes.json", {}) or {})
    out["t8"], out["t9"] = _timeline(items["commits"], fl)
    out["t8"]["creation"] = repo_creation_years(items["commits"], fl, meta)
    out["coverage"] = _commit_coverage(load_json(ad / "commit_coverage_check.json", {}) or {})
    out["bias"]     = _creation_bias(items, fl, meta)
    out["excluded"] = excluded_results(items, fl, all_summaries, code_status or {})
    out["extras_present"] = {k: (ad / f).exists() for k, f in (
        ("repo_readmes", "repo_readmes.json"), ("language_baseline", "github_language_baseline.json"),
        ("commit_coverage", "commit_coverage_check.json"),
        ("specialised", "specialised_repos.json"))}
    return out


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

def _s1(summary: dict, items: dict, fl, excl: set) -> dict:
    surf, anomalies = {}, []
    for s in SURFACES:
        kd = summary.get(s, {}).get("keywords", {})
        raw_all  = sum(d.get("api_hit_count", 0) for d in kd.values())
        raw_comp = sum(d.get("api_hit_count", 0) for k, d in kd.items() if base_keyword(k) not in excl)
        surf[s] = {"raw_all": raw_all, "raw_comparable": raw_comp, "unique_all": len(items[s]),
                   "unique_comparable": sum(1 for it in items[s] if fl(s, it)["comparable"])}
        for k, d in kd.items():
            if d.get("unique_results", 0) > d.get("api_hit_count", 0):
                anomalies.append({"surface": s, "keyword": k, "api_hit_count": d["api_hit_count"],
                                  "new_unique": d["unique_results"]})
    return {"surfaces": surf, "unique_gt_raw": anomalies}


def _s2(items: dict, fl, summaries: list[dict]) -> dict:
    """Verified = repository confirmed to mention the technique: non-CODE — ≥1 item whose
    title/body contains a technique keyword; CODE — analysed snapshot has ≥1 technique hit."""
    repos_all  = {s: {i.get("repo_full_name") for i in items[s] if i.get("repo_full_name")} for s in SURFACES}
    repos_comp = {s: {i.get("repo_full_name") for i in items[s] if i.get("repo_full_name") and fl(s, i)["comparable"]}
                  for s in SURFACES}
    ver_sets   = {s: {i.get("repo_full_name") for i in items[s]
                      if i.get("repo_full_name") and fl(s, i)["comparable"] and fl(s, i)["relevant"]}
                  for s in NONCODE_SURFACES}
    ver_sets["code"] = {r["full_name"] for r in summaries if r["total_specific"] > 0}
    union = set().union(*repos_comp.values())
    overlap = Counter(sum(rn in repos_comp[s] for s in SURFACES) for rn in union)
    return {"repos_all": {s: len(v) for s, v in repos_all.items()},
            "repos": {s: len(v) for s, v in repos_comp.items()},
            "union": len(union), "union_all": len(set().union(*repos_all.values())),
            "verified_repos": {s: len(v) for s, v in ver_sets.items()},
            "verified_union": len(set().union(*ver_sets.values())),
            "code_analysed": len(summaries),
            "overlap": {str(k): v for k, v in sorted(overlap.items())}}


def _s3(summaries: list[dict]) -> dict:
    return {"repos": len(summaries),
            "by_source": dict(Counter(r["source"] for r in summaries)),
            "files": stats([r["total_files"] for r in summaries]),
            "code_files": stats([r["code_files"] for r in summaries]),
            "code_loc": stats([r["code_loc"] for r in summaries])}


def _s4(slug: str, summary: dict, items: dict, excl: set | None = None, fl=None) -> dict:
    # Excluded search keywords (e.g. "@metamorphic") are not part of the reported keyword set.
    kws = [k for k in (base_keyword(k) for k in load_search_keywords(slug)) if k not in (excl or set())]
    out = {}
    for s in SURFACES:
        kd = {base_keyword(k): d for k, d in summary.get(s, {}).get("keywords", {}).items()}
        matched = Counter(k for it in items[s] if fl is None or fl(s, it)["comparable"] for k in _item_kws(it))
        out[s] = {"no_api_hits": [k for k in kws if kd.get(k, {}).get("api_hit_count", 0) == 0],
                  "no_collected_items": [k for k in kws if matched.get(k, 0) == 0]}
    return {"keywords": kws, "by_surface": out}


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

def _a1(summaries: list[dict], items: dict, fl, matcher: TechniqueMatcher) -> dict:
    hits, files, repos = Counter(), Counter(), Counter()
    for r in summaries:
        for k, v in r["kw_hits"].items():
            hits[k] += v
            repos[k] += v > 0
        for k, v in r["kw_files"].items():
            files[k] += v
    labels = matcher.labels
    code_rows = [{"id": k, "label": labels.get(k, k), "hits": v, "files": files[k], "repos": repos[k],
                  "subset_of": labels.get(matcher.subset[k]) if k in matcher.subset else None}
                 for k, v in _ranked(hits)]
    nc = {s: Counter() for s in NONCODE_SURFACES}
    nc_items, coverage = Counter(), {}
    for s in NONCODE_SURFACES:
        comp = [it for it in items[s] if fl(s, it)["comparable"]]
        coverage[s] = {"items": len(comp), "relevant": sum(1 for it in comp if fl(s, it)["relevant"])}
        for it in comp:
            for k, v in fl(s, it)["hits"].items():
                nc[s][k] += v
                nc_items[k] += 1
    total = Counter()
    for s in NONCODE_SURFACES:
        total.update(nc[s])
    nc_rows = [{"id": k, "label": labels.get(k, k), "by_surface": {s: nc[s].get(k, 0) for s in NONCODE_SURFACES},
                "hits": v, "items": nc_items[k],
                "subset_of": labels.get(matcher.subset[k]) if k in matcher.subset else None}
               for k, v in _ranked(total)]
    return {"code": code_rows, "code_repos": len(summaries), "noncode": nc_rows,
            "noncode_items": sum(c["items"] for c in coverage.values()), "coverage": coverage}


_ZERO_CAUSE_PRIORITY = ["has_hits_but_was_not_scanned", "file_not_scannable", "phrase_split_across_lines",
                        "identifier_with_prefix", "phrase_regex_gap", "bare_word_metamorphic",
                        "match_in_path_only", "no_technique_word_in_file", "missing_at_snapshot",
                        "missing_at_analysed_commit"]


def _a2(summaries: list[dict], status: dict, investigation: dict) -> dict:
    n_pop = status.get("population") or len(summaries)
    n = len(summaries)
    moe = (1.96 * math.sqrt(0.25 / n) * math.sqrt((n_pop - n) / max(n_pop - 1, 1))) if n and n < n_pop else 0.0
    zero = [r for r in summaries if r["total_specific"] == 0]
    rows = []
    for r in zero:
        causes = dict(r.get("matched_causes") or {})
        files  = {}
        if not causes and r["full_name"] in investigation:             # legacy record, investigated earlier
            files  = investigation[r["full_name"]].get("files", {})
            causes = {p: f.get("cause") for p, f in files.items()}
        cause = next((c for c in _ZERO_CAUSE_PRIORITY if c in causes.values()), None)
        rows.append({"repo": r["full_name"], "source": r["source"], "matched_paths": r.get("matched_paths", []),
                     "causes": causes, "cause": cause or r.get("zero_hit_reason"), "total_files": r["total_files"],
                     "snippets": {p: (f.get("snippets") or [])[:2] for p, f in files.items()}})
    return {
        "status": status, "analysed": n,
        "sample": {"population": n_pop, "moe_95_pct": moe * 100,
                   "cochran_required": math.ceil(384.16 / (1 + 383.16 / n_pop)) if n_pop else 0},
        "usage": sum(r["is_usage"] for r in summaries),
        "non_usage": sum(not r["is_usage"] and r["total_specific"] > 0 for r in summaries),
        "zero_hit": len(zero),
        "zero_hit_causes": dict(Counter(x["cause"] for x in rows)),
        "zero_hit_repos": rows,
        "by_source": {src: {"usage": sum(r["is_usage"] for r in summaries if r["source"] == src),
                            "repos": sum(1 for r in summaries if r["source"] == src)}
                      for src in ("specialised", "legacy")},
    }


def _bucket_stats(repos: list[dict], key: str, order: list[str]) -> dict:
    per = {b: [] for b in order}
    pooled = Counter()
    for r in repos:
        b = r[key]
        tot = sum(b.get(k, 0) for k in order)
        if not tot:
            continue
        for k in order:
            per[k].append(b.get(k, 0) / tot * 100)
            pooled[k] += b.get(k, 0)
    return {"repos": len(repos), "repos_with_files": len(per[order[0]]),
            "buckets": {k: {"avg_pct": statistics.mean(per[k]) if per[k] else 0,
                            "median_pct": statistics.median(per[k]) if per[k] else 0,
                            "files": pooled[k]} for k in order}}


def _a3(summaries: list[dict], rctx) -> dict:
    usage = [r for r in summaries if r["is_usage"]]
    rows = [{"repo": r["full_name"], "stars": r["stars"], "language": r["language"], "source": r["source"],
             "technique_test_files": r["test_tech_files"], "technique_source_files": r["src_tech_files"],
             "code_files": r["code_files"], "sample_technique_files": r["tech_paths"],
             "description": (r["description"] or "").replace("\n", " "),
             "readme_excerpt": re.sub(r"\s+", " ", re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", r.get("readme_snippet") or ""))[:600]}
            for r in sorted(usage, key=lambda x: x["full_name"].lower())]
    return {"usage": _bucket_stats(usage, "code_buckets", ["tech_test", "gen_test", "tech_nontest", "nontest"]),
            "repair_totals": {k: v for k, v in rctx.totals.items() if not k.startswith("dropped.")},
            "dropped_by_ext": {k[len("dropped"):]: v for k, v in rctx.totals.items() if k.startswith("dropped.")},
            "manual_rows": rows}


def _a4(summaries: list[dict]) -> dict:
    nu = [r for r in summaries if not r["is_usage"] and r["total_specific"] > 0]
    return _bucket_stats(nu, "doc_buckets", ["tech_doc", "gen_doc", "nondoc_tech", "nondoc_general"])


def _a5(summaries, items, fl, meta: dict, baseline: dict, gone: set | None = None) -> dict:
    # Comparable CODE-surface repositories that still exist (gone = deleted/private since the search).
    code_repos = {i.get("repo_full_name") for i in items["code"] if i.get("repo_full_name") and fl("code", i)["comparable"]}
    code_repos -= gone or set()
    primary = Counter((meta.get(rn) or {}).get("language") for rn in code_repos)
    missing = primary.pop(None, 0)
    n_known = sum(primary.values())
    rows = []
    bl_langs, bl_total = baseline.get("languages", {}), baseline.get("total")
    for lang, c in _ranked(primary):
        share = c / n_known * 100 if n_known else 0
        row = {"language": lang, "repos": c, "share_pct": share}
        if bl_total and lang in bl_langs and bl_langs[lang]:
            gh = bl_langs[lang] / bl_total * 100
            row.update(github_share_pct=gh, lift=share / gh if gh else None)
        rows.append(row)
    return {"code_repos": len(code_repos), "missing": missing, "rows": rows,
            "baseline": {k: baseline.get(k) for k in ("pushed_since", "total", "fetched_at")} if baseline else {}}


def _a6_a7(slug: str, items: dict, fl, meta: dict, readmes: dict) -> tuple[dict, dict]:
    from full_analysis.analysis import _load_custom_stopwords
    from full_analysis.non_code_analysis import _clean_text, _word_set, _load_stopwords, _build_technique_stopwords

    pats = domain_patterns()
    base, tech, custom = _load_stopwords(), _build_technique_stopwords(slug), _load_custom_stopwords()
    verified: set[str] = set()
    item_words: dict[str, set[str]] = defaultdict(set)          # old A7 method, for the noise comparison
    for s in NONCODE_SURFACES:
        for it in items[s]:
            rn, f = it.get("repo_full_name"), fl(s, it)
            if not rn or not f["comparable"] or not f["relevant"]:
                continue
            verified.add(rn)
            item_words[rn] |= _word_set(_clean_text(f["text"]), base, tech)

    # Domains: description + topics count on any keyword match. README text is long and full of
    # generic words (api, http, rest, react…), so a README only adds a domain when it contains
    # ≥ README_MIN_DISTINCT different keywords of that domain.
    dt_dom, rd_dom, hits_of = {}, {}, {}
    new_words: dict[str, set[str]] = {}
    with_readme = 0
    for rn in verified:
        m = meta.get(rn) or {}
        rd_raw = readmes.get(rn) if isinstance(readmes.get(rn), str) else ""
        with_readme += bool(rd_raw)
        rd = strip_urls(rd_raw)
        desc = strip_urls(m.get("description") or "")
        topics = " ".join(t.replace("-", " ") for t in m.get("topics") or [])
        dt, rdd, hits = set(), set(), {}
        for d, p in pats.items():
            m1 = [x.group(0) for x in p.finditer(f"{desc} {topics}")]
            m2 = {x.group(0).lower() for x in p.finditer(rd)} if rd else set()
            if m1:
                dt.add(d)
            if len(m2) >= README_MIN_DISTINCT:
                rdd.add(d)
            if m1 or len(m2) >= README_MIN_DISTINCT:
                hits[d] = (m1 + sorted(m2))[:4]
        dt_dom[rn], rd_dom[rn], hits_of[rn] = dt, rdd, hits
        # A7 (agreed): README + project description only.
        new_words[rn] = _word_set(_clean_text(f"{desc}\n{rd}"), base, tech)
        item_words[rn] |= _word_set(_clean_text(f"{desc} {topics}"), base, tech)

    c_dt, c_all = Counter(), Counter()
    for rn in verified:
        c_dt.update(dt_dom[rn])
        c_all.update(dt_dom[rn] | rd_dom[rn])
    rnd = random.Random(SAMPLE_SEED)
    samples = {}
    for d in cfg.DOMAIN_KEYWORDS:
        pool = sorted(rn for rn in verified if d in (dt_dom[rn] | rd_dom[rn]))
        pick = rnd.sample(pool, min(10, len(pool)))
        samples[d] = [{"repo": rn, "description": ((meta.get(rn) or {}).get("description") or "")[:200],
                       "topics": (meta.get(rn) or {}).get("topics") or [], "matched": hits_of[rn][d],
                       "source": "description/topics" if d in dt_dom[rn] else "README",
                       "other_domains": sorted((dt_dom[rn] | rd_dom[rn]) - {d})} for rn in pick]
    a6 = {"repos_verified": len(verified), "readme_coverage": with_readme, "readme_min_distinct": README_MIN_DISTINCT,
          "desc_topics": dict(c_dt), "with_readme": dict(c_all),
          "no_match_desc_topics": sum(1 for rn in verified if not dt_dom[rn]),
          "no_match_with_readme": sum(1 for rn in verified if not (dt_dom[rn] | rd_dom[rn])),
          "samples": samples, "verified_repos": sorted(verified)}
    a6["domain_counts"] = dict(_ranked(c_all))

    vocab = {k.lower() for kws in cfg.DOMAIN_KEYWORDS.values() for k in kws if re.fullmatch(r"[a-z]{3,}", k.lower())}

    def freq_of(word_sets: dict[str, set[str]]) -> Counter:
        c = Counter()
        for ws in word_sets.values():
            c.update(w for w in ws if w not in custom)
        return c

    def noise(c: Counter) -> dict:
        top = [w for w, _ in _ranked(c, 50)]
        return {"top50_process_pct": sum(w in PROCESS_WORDS for w in top) / max(len(top), 1) * 100,
                "top50_domain_vocab_pct": sum(w in vocab for w in top) / max(len(top), 1) * 100,
                "top10": top[:10]}

    freq, old = freq_of(new_words), freq_of(item_words)
    wl = Counter({w: c for w, c in freq.items() if w in vocab})
    a7 = {"repos": len(new_words), "with_readme": with_readme, "freq": dict(_ranked(freq, 400)),
          "whitelist_freq": dict(_ranked(wl, 400)), "whitelist_vocab_size": len(vocab),
          "noise_new": noise(freq), "noise_old": noise(old)}
    return a6, a7


# ---------------------------------------------------------------------------
# Timeline (COMMITS surface only)
# ---------------------------------------------------------------------------

def _timeline(commits: list[dict], fl) -> tuple[dict, dict]:
    rel = []
    all_by_year: Counter = Counter()
    for c in commits:
        ts = c.get("committer_date") or c.get("created_at") or c.get("author_date")
        y = _year(ts)
        if y is None:
            continue
        f = fl("commits", c)
        if f["comparable"]:
            all_by_year[y] += 1
        if f["comparable"] and f["relevant"]:
            rel.append({"repo": c.get("repo_full_name", ""), "ts": ts, "year": y, "month": ts[:7],
                        "agent": f["agent"], "body": c.get("body") or "", "url": c.get("html_url", "")})

    # T8 — repos adopting the technique: year of each repo's first relevant commit.
    first: dict[str, str] = {}
    for r in rel:
        if r["repo"] not in first or r["ts"] < first[r["repo"]]:
            first[r["repo"]] = r["ts"]
    adopt = Counter(_year(ts) for ts in first.values())
    first_agent = Counter()
    for r in rel:
        if first.get(r["repo"]) == r["ts"] and r["agent"]:
            first_agent[r["year"]] += 1
    years = sorted(set(all_by_year) | set(adopt))
    t8 = {"years": years, "adopting_repos": {y: adopt.get(y, 0) for y in years},
          "adopting_with_agent_first_commit": {y: first_agent.get(y, 0) for y in years},
          "repos_total": len(first)}

    # T9 — commit activity.
    by_year, agent_year, capped, rel_repos = Counter(), Counter(), Counter(), defaultdict(set)
    by_month, agent_month = Counter(), Counter()
    per_repo_month, repo_total = Counter(), Counter()
    for r in sorted(rel, key=lambda x: x["ts"]):
        by_year[r["year"]] += 1
        by_month[r["month"]] += 1
        rel_repos[r["year"]].add(r["repo"])
        repo_total[r["repo"]] += 1
        per_repo_month[(r["repo"], r["month"])] += 1
        if per_repo_month[(r["repo"], r["month"])] <= 5:
            capped[r["year"]] += 1
        if r["agent"]:
            agent_year[r["year"]] += 1
            agent_month[r["month"]] += 1
    top10 = {rn for rn, _ in _ranked(repo_total, 10)}
    no_top = Counter(r["year"] for r in rel if r["repo"] not in top10)
    agent_repos = defaultdict(set)
    for r in rel:
        if r["agent"]:
            agent_repos[r["year"]].add(r["repo"])
    peak = max(by_year, key=by_year.get) if by_year else None
    rnd = random.Random(SAMPLE_SEED)
    pool = [r for r in rel if r["year"] == peak]
    manual = [{"repo": r["repo"], "date": r["ts"][:10], "agent_marked": r["agent"], "url": r["url"],
               "message": re.sub(r"\s+", " ", r["body"])[:300]} for r in rnd.sample(pool, min(50, len(pool)))]

    t9 = {"years": years,
          "all": {y: all_by_year.get(y, 0) for y in years},
          "relevant": {y: by_year.get(y, 0) for y in years},
          "relevant_capped": {y: capped.get(y, 0) for y in years},
          "relevant_without_top10_repos": {y: no_top.get(y, 0) for y in years},
          "agent_marked": {y: agent_year.get(y, 0) for y in years},
          "repos": {y: len(rel_repos[y]) for y in years},
          "repos_with_agent_commit": {y: len(agent_repos[y]) for y in years},
          "relevant_by_month": dict(sorted(by_month.items())),
          "agent_by_month": dict(sorted(agent_month.items())),
          "relevant_total": len(rel), "all_total": sum(all_by_year.values()),
          "peak_year": peak, "top10_repos": _ranked(repo_total, 10),
          "manual_sample": manual,
          "window": [cfg.SLICE_START_DATE, cfg.SLICE_END_DATE]}
    return t8, t9


def id_year_reference() -> list[tuple[int, str]]:
    """(repository ID, created_at) pairs from every technique's REPOS-surface search results.
    GitHub assigns repository IDs in creation order, so these calibrate ID → creation date."""
    pairs: dict[int, str] = {}
    for p in sorted(cfg.RESULTS_DIR.glob("*/search/repos.json")):
        for it in load_json(p, []) or []:
            try:
                rid = int(it.get("id"))
            except (TypeError, ValueError):
                continue
            if isinstance(it.get("created_at"), str):
                pairs[rid] = it["created_at"]
    return sorted(pairs.items())


def _estimate_created(rid: int, ids: list[int], ref: list[tuple[int, str]], skip: int | None = None) -> str | None:
    """Creation timestamp for a repository ID, interpolated between the nearest reference IDs."""
    from datetime import datetime
    i = bisect.bisect_left(ids, rid)
    lo, hi = i - 1, i
    if skip is not None:                                   # leave-one-out validation
        lo, hi = (skip - 1, skip + 1) if i == skip else (lo, hi)
    elif i < len(ids) and ids[i] == rid:
        return ref[i][1]
    if lo < 0 or hi >= len(ref):
        return None                                        # outside the calibrated range
    (a_id, a_ts), (b_id, b_ts) = ref[lo], ref[hi]
    ta = datetime.fromisoformat(a_ts.replace("Z", "+00:00"))
    tb = datetime.fromisoformat(b_ts.replace("Z", "+00:00"))
    f = (rid - a_id) / (b_id - a_id) if b_id != a_id else 0.0
    return (ta + (tb - ta) * f).isoformat()


def repo_creation_years(commits: list[dict], fl, meta: dict) -> dict:
    """GitHub creation year of every repository with ≥1 relevant commit: from repository metadata
    when present, otherwise estimated from the repository ID (no API calls)."""
    repos: dict[str, int | None] = {}
    for c in commits:
        rn = c.get("repo_full_name")
        f = fl("commits", c)
        if rn and f["comparable"] and f["relevant"]:
            try:
                repos.setdefault(rn, int(c.get("repo_id")))
            except (TypeError, ValueError):
                repos.setdefault(rn, None)
    ref = id_year_reference()
    ids = [r for r, _ in ref]
    by_year, n_meta, n_est, n_none = Counter(), 0, 0, 0
    for rn, rid in repos.items():
        ts = (meta.get(rn) or {}).get("created_at")
        if ts:
            n_meta += 1
        elif rid is not None and ids:
            ts = _estimate_created(rid, ids, ref)
            n_est += ts is not None
        y = _year(ts)
        if y is None:
            n_none += 1
        else:
            by_year[y] += 1
    # Validation of the estimate: leave-one-out on (a seeded sample of) the reference repositories.
    rnd = random.Random(SAMPLE_SEED)
    idx = rnd.sample(range(1, len(ref) - 1), min(3000, max(len(ref) - 2, 0)))
    ok = sum(_year(_estimate_created(ref[i][0], ids, ref, skip=i)) == _year(ref[i][1]) for i in idx)
    return {"repos": len(repos), "by_year": dict(sorted(by_year.items())), "from_metadata": n_meta,
            "estimated": n_est, "unknown": n_none, "reference_repos": len(ref),
            "validation": {"checked": len(idx), "exact_year_pct": ok / len(idx) * 100 if idx else None}}


def excluded_results(items: dict, fl, all_summaries: list[dict], status: dict,
                     code_scope: set[str] | None = None) -> dict:
    """Every result treated as not found, per repository and surface, with the reason.
    code_scope limits the CODE list (PBT/fuzz: only the scanned sample is known)."""
    zero = {r["full_name"]: r for r in all_summaries if r["total_specific"] == 0}
    ok = {r["full_name"] for r in all_summaries if r["total_specific"] > 0}
    gone, failed = set(status.get("gone_repos", [])), status.get("failed_repos", {}) or {}
    not_scanned = set(status.get("not_scanned_repos", []))
    code_found = {it.get("repo_full_name") for it in items["code"] if it.get("repo_full_name") and fl("code", it)["found"]}
    if code_scope is not None:
        code_found &= code_scope
    code_rows = []
    for rn in sorted(code_found - ok, key=str.lower):
        if rn in gone:
            reason, detail = "no longer available", "deleted, private or disabled since the search"
        elif rn in zero:
            reason = "no technique hit now"
            causes = zero[rn].get("matched_causes") or {}
            detail = "; ".join(f"{p}: {c}" for p, c in list(causes.items())[:3]) or zero[rn].get("zero_hit_reason") or ""
        elif rn in failed:
            reason, detail = "scan failed", failed[rn]
        elif rn in not_scanned:
            reason, detail = "not scanned yet", ""
        else:
            reason, detail = "not scanned", ""
        code_rows.append({"repo": rn, "reason": reason, "detail": detail})

    nc_rows, dropped = [], {}
    for s in NONCODE_SURFACES:
        per: dict[str, dict] = {}
        n_drop = 0
        for it in items[s]:
            rn, f = it.get("repo_full_name"), fl(s, it)
            if not rn or not f["found"]:
                continue
            r = per.setdefault(rn, {"items": 0, "verified": 0, "example": None})
            r["items"] += 1
            if f["comparable"]:
                r["verified"] += 1
            else:
                n_drop += 1
                if r["example"] is None:
                    r["example"] = {"title": re.sub(r"\s+", " ", (it.get("title") or it.get("body") or ""))[:120],
                                    "url": it.get("html_url") or it.get("url") or ""}
        dropped[s] = n_drop
        for rn, r in sorted(per.items(), key=lambda x: x[0].lower()):
            if not r["verified"]:
                nc_rows.append({"repo": rn, "surface": s, "items": r["items"], "example": r["example"]})
    included = set(ok)
    for s in NONCODE_SURFACES:
        included |= {it.get("repo_full_name") for it in items[s] if fl(s, it)["comparable"]}
    return {"code": code_rows, "noncode": nc_rows, "items_dropped": dropped,
            "code_reasons": dict(Counter(r["reason"] for r in code_rows)),
            "repos_excluded_everywhere": sorted(({r["repo"] for r in code_rows} | {r["repo"] for r in nc_rows}) - included,
                                                key=str.lower)}


def _commit_coverage(cc: dict) -> dict:
    if not cc.get("repos"):
        return {}
    rows = cc["repos"]
    ok = [r for r in rows if r.get("status") == "ok"]
    inactive = [r for r in ok if r.get("inactive_1y")]
    return {"sampled": len(rows), "ok": len(ok), "inactive_1y": len(inactive),
            "archived": sum(1 for r in ok if r.get("archived")), "cutoff": cc.get("cutoff"),
            "examples": inactive[:10]}


def _creation_bias(items: dict, fl, meta: dict) -> dict:
    """Share of each surface's (comparable) repos created in each year — evidence for the
    code-search index bias (only repos active in the last year are code-searchable)."""
    out = {}
    for s in SURFACES:
        names = {i.get("repo_full_name") for i in items[s] if i.get("repo_full_name") and fl(s, i)["comparable"]}
        c = Counter(_year((meta.get(rn) or {}).get("created_at")) for rn in names)
        c.pop(None, None)
        out[s] = {"repos": sum(c.values()), "by_year": dict(sorted(c.items()))}
    return out
