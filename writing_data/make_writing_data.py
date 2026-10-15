"""
Builds writing_data/shared_data.tex (+ writing_data/figures/) from the sections data of all
three techniques (results/<slug>/analysis/overall.json, written by specialised_report.py).

Run from the project root after `python specialised_report.py -t mt|pbt|fuzz`:
  python writing_data/make_writing_data.py

Everything is regenerated, so rerun it whenever the underlying data changes.
"""

from __future__ import annotations

import json
import math
import sys
from collections import Counter
from datetime import date
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(__file__).resolve().parent
FIG = OUT / "figures"
sys.path.insert(0, str(ROOT))

SLUGS = {"mt": "metamorphic_testing", "pbt": "property_based_testing", "fuzz": "fuzz_testing"}
NAMES = {"mt": "MT", "pbt": "PBT", "fuzz": "Fuzz"}
LONG = {"mt": "Metamorphic testing", "pbt": "Property-based testing", "fuzz": "Fuzz testing"}
SURFACES = ["code", "repos", "commits", "prs", "issues", "discussions"]
SURF_LABEL = {"code": "Code", "repos": "Repositories", "commits": "Commits", "prs": "Pull requests",
              "issues": "Issues", "discussions": "Discussions"}

# Okabe-Ito colour-blind-safe palette
C = {"mt": "#0072B2", "pbt": "#E69F00", "fuzz": "#009E73", "agent": "#D55E00", "grey": "#9A9A9A", "light": "#C9DDEE"}

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 8.5, "axes.titlesize": 9, "axes.labelsize": 8.5,
    "xtick.labelsize": 7.5, "ytick.labelsize": 7.5, "legend.fontsize": 7.5, "legend.frameon": False,
    "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "axes.grid.axis": "y",
    "grid.color": "#E3E3E3", "grid.linewidth": 0.6, "axes.axisbelow": True, "axes.edgecolor": "#555555",
    "axes.linewidth": 0.7, "xtick.color": "#333333", "ytick.color": "#333333", "savefig.dpi": 300,
    "pdf.fonttype": 42,
})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load(t: str) -> dict:
    return json.load(open(ROOT / "results" / SLUGS[t] / "analysis" / "overall.json", encoding="utf-8"))["sections"]


def g(d: dict | None, k, default=0):
    d = d or {}
    return d.get(str(k), d.get(k, default))


def n(x, dec: int = 0) -> str:
    if x is None:
        return "--"
    return f"{x:,.{dec}f}" if isinstance(x, float) and dec else f"{round(x):,}"


def pct(x, dec: int = 1) -> str:
    return "--" if x is None else f"{x:.{dec}f}\\%"


def esc(s: str) -> str:
    rep = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_",
           "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}
    return "".join(rep.get(c, c) for c in str(s))


def kw(s: str) -> str:
    return r"\texttt{" + esc(s.strip('"')) + "}"


def save(fig, name: str) -> str:
    FIG.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG / name, bbox_inches="tight", pad_inches=0.02)
    plt.close(fig)
    return f"figures/{name}"


def years_of(*dicts, lo: int | None = None) -> list[int]:
    ys = sorted({int(k) for d in dicts for k in (d or {})})
    return [y for y in ys if lo is None or y >= lo]


def year_range(*dicts) -> list[int]:
    """Every year from the first to the last with data (years without data count as 0)."""
    ys = years_of(*dicts)
    return list(range(ys[0], ys[-1] + 1)) if ys else []


# ---------------------------------------------------------------------------
# Data for the comparison (corrected where commit sampling exists)
# ---------------------------------------------------------------------------

def first_commit_series(s: dict) -> dict[int, dict]:
    """Repos by year of first technique commit: collected, corrected (exact or estimate ± CI)."""
    est = (s.get("timeline_estimates") or {}).get("adoption", {})
    out = {}
    for y in years_of(s["t8"]["adopting_repos"], est):
        e = g(est, y, None)
        out[y] = {"collected": g(s["t8"]["adopting_repos"], y),
                  "value": e["estimate"] if e else g(s["t8"]["adopting_repos"], y),
                  "ci": (e or {}).get("ci", 0.0), "corrected": bool(e), "exact": bool(e and e.get("exact"))}
    return out


def agent_share_series(s: dict) -> dict[int, dict]:
    est = (s.get("timeline_estimates") or {}).get("agent", {})
    out = {}
    for y in years_of(s["t9"]["relevant"], est):
        e = g(est, y, None)
        rel, ag = g(s["t9"]["relevant"], y), g(s["t9"]["agent_marked"], y)
        out[y] = {"collected": ag / rel if rel else None,
                  "value": e["share"] if e else (ag / rel if rel else None),
                  "ci": (e or {}).get("ci", 0.0), "corrected": bool(e), "exact": bool(e and e.get("exact")),
                  "relevant": (e or {}).get("relevant_est", rel)}
    return out


def mt_surge_facts() -> dict:
    """Profile of the MT repositories whose first technique commit is in the peak year."""
    from core_helpers.keyword_matcher import TechniqueMatcher
    from report_helpers.sections_aggregate import strip_agent_lines, base_keyword
    base = ROOT / "results" / SLUGS["mt"]
    m, excl = TechniqueMatcher(SLUGS["mt"]), {'"@metamorphic"'}
    meta = json.load(open(base / "analysis" / "cloned_repo_metadata.json", encoding="utf-8"))
    rel = []
    for c in json.load(open(base / "search" / "commits.json", encoding="utf-8")):
        kws = {base_keyword(k) for k in (c.get("matched_keywords") or [c.get("matched_keyword")]) if k}
        if kws and kws <= excl:
            continue
        text, agent = strip_agent_lines(c.get("body") or "")
        if m.total(m.scan_text(text)[0]):
            rel.append((c.get("committer_date") or c.get("created_at") or "", c["repo_full_name"], agent))
    first: dict[str, tuple] = {}
    for ts, rn, ag in sorted(rel):
        first.setdefault(rn, (ts, ag))
    per_repo = Counter(rn for _, rn, _ in rel)
    peak = max(Counter(ts[:4] for ts, _ in first.values()).items(), key=lambda kv: kv[1])[0]
    rs = [rn for rn, (ts, _) in first.items() if ts[:4] == peak]
    created = Counter(((meta.get(rn) or {}).get("created_at") or "")[:4] for rn in rs)
    months = Counter(first[rn][0][:7] for rn in rs)
    return {"peak": int(peak), "repos": len(rs), "owners": len({rn.split("/")[0] for rn in rs}),
            "created_same_year": created.get(peak, 0), "single_commit": sum(per_repo[rn] == 1 for rn in rs),
            "months": dict(sorted(months.items()))}


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------

def fig_mt_first_commit(s: dict) -> str:
    t8 = s["t8"]
    ys = year_range(t8["adopting_repos"])
    tot = [g(t8["adopting_repos"], y) for y in ys]
    ag = [g(t8["adopting_with_agent_first_commit"], y) for y in ys]
    fig, ax = plt.subplots(figsize=(6.3, 2.6))
    x = range(len(ys))
    ax.bar(x, [a - b for a, b in zip(tot, ag)], 0.72, color=C["mt"], label="First technique commit, no agent mark")
    ax.bar(x, ag, 0.72, bottom=[a - b for a, b in zip(tot, ag)], color=C["agent"], label="First technique commit agent-marked")
    for i, v in enumerate(tot):
        if v:
            ax.text(i, v + max(tot) * 0.015, f"{v:,}", ha="center", va="bottom", fontsize=7)
    ax.set_xticks(list(x), [str(y) + ("*" if y == date.today().year else "") for y in ys])
    ax.set_ylabel("Repositories")
    ax.legend(loc="upper left")
    return save(fig, "mt_t8_first_commit.pdf")


def fig_mt_creation(s: dict) -> str:
    cr = s["t8"].get("creation", {}).get("by_year", {})
    ys = year_range(cr)
    fig, ax = plt.subplots(figsize=(6.3, 2.3))
    ax.bar(range(len(ys)), [g(cr, y) for y in ys], 0.72, color=C["grey"])
    for i, y in enumerate(ys):
        if g(cr, y):
            ax.text(i, g(cr, y) + max(g(cr, z) for z in ys) * 0.015, f"{g(cr, y):,}", ha="center", va="bottom", fontsize=7)
    ax.set_xticks(range(len(ys)), [str(y) + ("*" if y == date.today().year else "") for y in ys])
    ax.set_ylabel("Repositories")
    return save(fig, "mt_t8_creation_year.pdf")


def fig_mt_commits(s: dict) -> str:
    t9 = s["t9"]
    ys = year_range(t9["relevant"])
    rel = [g(t9["relevant"], y) for y in ys]
    ag = [g(t9["agent_marked"], y) for y in ys]
    fig, ax = plt.subplots(figsize=(6.3, 2.6))
    x = range(len(ys))
    ax.bar(x, [a - b for a, b in zip(rel, ag)], 0.72, color=C["mt"], label="Technique commits, no agent mark")
    ax.bar(x, ag, 0.72, bottom=[a - b for a, b in zip(rel, ag)], color=C["agent"], label="Agent-marked")
    for i, v in enumerate(rel):
        if v:
            ax.text(i, v + max(rel) * 0.015, f"{v:,}", ha="center", va="bottom", fontsize=7)
    ax.set_xticks(list(x), [str(y) + ("*" if y == date.today().year else "") for y in ys])
    ax.set_ylabel("Commits")
    ax.legend(loc="upper left")
    return save(fig, "mt_t9_commits.pdf")


def lower_bound_years(s: dict) -> set[int]:
    """Years whose collected commit counts were cut by the search cap and are not corrected."""
    by_year = (s.get("completeness") or {}).get("commits_by_year") or {}
    corrected = {int(y) for y in ((s.get("timeline_estimates") or {}).get("adoption") or {})}
    return {int(y) for y, c in by_year.items() if c.get("capped")} - corrected


def fig_cmp_first_commit(S: dict) -> str:
    import numpy as np
    fig, ax = plt.subplots(figsize=(6.3, 3.0))
    handles = []
    for t in ("mt", "pbt", "fuzz"):
        ser = first_commit_series(S[t])
        ys = [y for y in range(2012, date.today().year + 1)]
        lb = lower_bound_years(S[t])
        val = [ser[y]["value"] if y in ser and ser[y]["value"] else np.nan for y in ys]
        col = [ser[y]["collected"] if y in ser and ser[y]["collected"] else np.nan for y in ys]
        solid = [v if (y not in lb) else np.nan for y, v in zip(ys, val)]
        ax.plot(ys, solid, color=C[t], lw=1.8, marker="o", ms=3)
        if any(not np.isnan(c) and (y in lb or c != v) for y, c, v in zip(ys, col, val) if not np.isnan(v)):
            ax.plot(ys, col, color=C[t], lw=1.1, ls=":", marker="o", ms=2.5, mfc="white", mew=0.8)
        est = [y for y in ys if y in ser and ser[y]["corrected"] and not ser[y]["exact"]]
        if est:
            ax.errorbar(est, [ser[y]["value"] for y in est], yerr=[ser[y]["ci"] for y in est], fmt="D", ms=4,
                        color=C[t], ecolor=C[t], elinewidth=1.1, capsize=3)
        handles.append(plt.Line2D([], [], color=C[t], lw=1.8, marker="o", ms=3, label=NAMES[t]))
    handles += [plt.Line2D([], [], color="#555555", lw=1.1, ls=":", marker="o", ms=2.5, mfc="white",
                           label="as collected (lower bound where the search was capped)"),
                plt.Line2D([], [], color="#555555", lw=0, marker="D", ms=4, label="cap-corrected estimate (95% CI)")]
    ax.set_yscale("log")
    ax.set_ylabel("Repositories (log scale)")
    ax.set_xticks(range(2012, date.today().year + 1, 2))
    ax.legend(handles=handles, loc="upper left", fontsize=7)
    return save(fig, "cmp_first_commit_per_year.pdf")


def fig_cmp_agent_share(S: dict) -> str:
    years = [2025, 2026]
    fig, ax = plt.subplots(figsize=(4.2, 2.5))
    w = 0.26
    for i, t in enumerate(("mt", "pbt", "fuzz")):
        ser = agent_share_series(S[t])
        vals = [(ser.get(y) or {}).get("value") or 0 for y in years]
        cis = [(ser.get(y) or {}).get("ci") or 0 for y in years]
        xs = [j + (i - 1) * w for j in range(len(years))]
        ax.bar(xs, [v * 100 for v in vals], w * 0.92, color=C[t], label=NAMES[t])
        if any(cis):
            ax.errorbar([x for x, c in zip(xs, cis) if c], [v * 100 for v, c in zip(vals, cis) if c],
                        yerr=[c * 100 for c in cis if c], fmt="none", ecolor="#222222", elinewidth=0.9, capsize=2.5)
        for xx, v, c in zip(xs, vals, cis):
            ax.text(xx, v * 100 + c * 100 + 1.2, f"{v * 100:.0f}%", ha="center", va="bottom", fontsize=7)
    ax.set_xticks(range(len(years)), [str(y) + ("*" if y == date.today().year else "") for y in years])
    ax.set_ylabel("Agent-marked commits (%)")
    ax.set_ylim(0, max(70, ax.get_ylim()[1]))
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.0), ncol=3)
    return save(fig, "cmp_agent_share.pdf")


def fig_cmp_surfaces(S: dict) -> str:
    fig, ax = plt.subplots(figsize=(6.3, 2.7))
    w = 0.26
    for i, t in enumerate(("mt", "pbt", "fuzz")):
        s2 = S[t]["s2"]
        vals, errs = [], []
        for srf in SURFACES:
            if srf == "code" and s2.get("code_verified_est"):
                ce = s2["code_verified_est"]
                vals.append(ce["estimate"] if ce["known"] else 0)
                errs.append(ce["ci"] or 0)
            else:
                vals.append(g(s2["repos"], srf))
                errs.append(0)
        xs = [j + (i - 1) * w for j in range(len(SURFACES))]
        ax.bar(xs, vals, w * 0.92, color=C[t], label=NAMES[t])
        if any(errs):
            ax.errorbar([x for x, e in zip(xs, errs) if e], [v for v, e in zip(vals, errs) if e],
                        yerr=[e for e in errs if e], fmt="none", ecolor="#222222", elinewidth=0.8, capsize=2)
        for x, v, srf in zip(xs, vals, SURFACES):
            if not v:
                ax.text(x, 12, "pending", rotation=90, ha="center", va="bottom", fontsize=6.5, color="#777777")
    ax.set_yscale("log")
    ax.set_xticks(range(len(SURFACES)), [SURF_LABEL[x] for x in SURFACES])
    ax.set_ylabel("Verified repositories (log scale)")
    ax.set_ylim(bottom=5)
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.0), ncol=3)
    return save(fig, "cmp_repos_per_surface.pdf")


def fig_wordcloud(freq: dict, name: str, colour: str) -> str | None:
    if not freq:
        return None
    from wordcloud import WordCloud
    from matplotlib.colors import LinearSegmentedColormap
    from matplotlib.colors import to_rgb
    rgb = to_rgb(colour)
    light = tuple(0.7 * c + 0.3 for c in rgb)                  # tint and shade of the technique colour
    dark = tuple(0.45 * c for c in rgb)
    cmap = LinearSegmentedColormap.from_list("c", [light, colour, dark])
    wc = WordCloud(width=1800, height=800, background_color="white", max_words=120, colormap=cmap,
                   prefer_horizontal=0.95, relative_scaling=0.5, random_state=20261010, margin=2)
    wc.generate_from_frequencies({w: math.sqrt(c) for w, c in freq.items()})
    FIG.mkdir(parents=True, exist_ok=True)
    wc.to_file(str(FIG / name))
    return f"figures/{name}"


# ---------------------------------------------------------------------------
# LaTeX
# ---------------------------------------------------------------------------

def table(caption: str, label: str, cols: str, head: list[str], rows: list[list[str]], note: str = "",
          size: str = r"\small", prehead: str = "") -> str:
    out = [r"\begin{table}[htbp]", r"\centering", size, rf"\caption{{{caption}}}", rf"\label{{{label}}}",
           rf"\begin{{tabular}}{{{cols}}}", r"\toprule"] + ([prehead] if prehead else []) + \
          [" & ".join(head) + r" \\", r"\midrule"]
    for r in rows:
        if r == "MID":
            out.append(r"\midrule")
        else:
            out.append(" & ".join(r) + r" \\")
    out += [r"\bottomrule", r"\end{tabular}"]
    if note:
        out.append(rf"\par\smallskip\parbox{{0.94\linewidth}}{{\footnotesize {note}}}")
    out.append(r"\end{table}")
    return "\n".join(out) + "\n"


def figure(path: str, caption: str, label: str, width: str = r"\linewidth") -> str:
    return (r"\begin{figure}[htbp]" "\n" r"\centering" "\n" rf"\includegraphics[width={width}]{{{path}}}" "\n"
            rf"\caption{{{caption}}}" "\n" rf"\label{{{label}}}" "\n" r"\end{figure}" "\n")


def build() -> str:
    S = {t: load(t) for t in SLUGS}
    mt = S["mt"]
    yr = date.today().year
    L: list[str] = []
    add = L.append

    add(r"""\documentclass[11pt,a4paper]{article}
\usepackage[T1]{fontenc}
\usepackage{lmodern}
\usepackage[margin=2.2cm]{geometry}
\usepackage{microtype}
\usepackage{booktabs}
\usepackage{graphicx}
\usepackage[font=small,labelfont=bf,skip=4pt]{caption}
\usepackage{subcaption}
\usepackage{xcolor}
\usepackage{float}
\usepackage{enumitem}
\usepackage[colorlinks=true,linkcolor=blue!50!black,urlcolor=blue!50!black]{hyperref}
\setlength{\parskip}{0.45em}
\setlength{\parindent}{0pt}
\renewcommand{\arraystretch}{1.12}
\newcommand{\note}[1]{\textcolor{black!60}{\small #1}}

\title{Mining GitHub for Metamorphic Testing:\\ Shared Data for the Final Report}
\date{""" + date.today().strftime("%d %B %Y") + r"""}
\author{}
\begin{document}
\maketitle
\vspace{-2em}
""")

    # ---- Data notes -----------------------------------------------------------------------
    pbt_n, fuzz_n = S["pbt"]["a2"]["analysed"], S["fuzz"]["a2"]["analysed"]
    add(r"""\section*{About the data}
\begin{itemize}[leftmargin=1.2em,itemsep=1pt]
\item \textbf{Search.} GitHub search on six surfaces (code, repositories, commits, pull requests, issues, discussions), """
        r"""""" + esc(f"{mt['t9']['window'][0]} to {mt['t9']['window'][1]}") + r""". Only explicit technique phrases count; for MT the keyword \texttt{"@metamorphic"} is excluded (GitHub ignores the \texttt{@} and searches the bare word).
\item \textbf{Verified results only.} A non-code result counts only if its title or body contains a technique phrase; a code-surface repository counts only if its current snapshot contains one. Everything else is treated as not found.
\item \textbf{Current state.} Repositories were re-scanned on their current default-branch snapshot (October """ + str(yr) + r"""); repositories deleted or made private since the search are excluded.
\item \textbf{PBT and fuzz} have """ + n(S["pbt"]["s2"]["repos"]["code"]) + r""" and """ + n(S["fuzz"]["s2"]["repos"]["code"]) + r""" code-surface repositories, so their cloning-based figures use seeded random samples sized for $\pm$3\% at 95\% confidence (PBT: """ + n(pbt_n) + r""" analysed""" + (r"""; fuzz: """ + n(fuzz_n) + r""" analysed""" if fuzz_n else r"""; fuzz: scan in progress""") + r"""). Their commit searches hit GitHub's 1{,}000-results-per-query cap; the timeline figures use the corrected counts (exact for PBT, estimated with 95\% confidence intervals for fuzz).
\item \textbf{""" + str(yr) + r"""} covers January--August only (search ended """ + esc(mt["t9"]["window"][1]) + r"""), marked with * in the figures.
\end{itemize}
""")

    # ======================= RQ1 ===========================================================
    add(r"\section{RQ1 -- Adoption: how much is metamorphic testing used?}" "\n")
    s1, s2 = mt["s1"]["surfaces"], mt["s2"]
    rows = [[SURF_LABEL[x], n(s1[x]["raw_comparable"]), n(s1[x]["unique_comparable"]), n(g(s2["repos"], x))] for x in SURFACES]
    rows += ["MID", [r"\textbf{All surfaces}", "", "", r"\textbf{" + n(s2["union"]) + "}"]]
    add(table("Metamorphic testing on GitHub: search hits and distinct repositories per search surface (S1, S2).",
              "tab:mt-search", "@{}lrrr@{}",
              ["Surface", "Search hits", "Verified results", "Distinct repositories"], rows,
              r"Search hits: GitHub's reported \texttt{total\_count} summed over the search keywords (before de-duplication). "
              r"Verified results: distinct items whose text (non-code) or repository snapshot (code) contains an MT phrase. "
              r"A repository found on several surfaces is counted once in the total."))

    s3 = mt["s3"]
    add(r"\paragraph{Size of the code-surface repositories (S3).} The " + n(s3["repos"]) + r" verified code-surface repositories contain "
        + n(s3["files"]["sum"]) + r" files in total, of which " + n(s3["code_files"]["sum"]) + r" are code files with "
        + n(s3["code_loc"]["sum"] / 1e6, 0) + r"~million lines of code (median per repository: " + n(s3["code_files"]["median"])
        + r" code files, " + n(s3["code_loc"]["median"]) + r" lines of code)." "\n")

    s4 = mt["s4"]["by_surface"]
    parts = []
    for x in SURFACES:
        miss = s4[x]["no_collected_items"]
        if miss:
            parts.append(f"on the {SURF_LABEL[x].lower()} surface " + ", ".join(kw(k) for k in miss))
    full = [SURF_LABEL[x].lower() for x in SURFACES if not s4[x]["no_collected_items"]]
    add(r"\paragraph{Keywords without results (S4).} All " + str(len(mt["s4"]["keywords"])) + r" search keywords returned results on the "
        + " and ".join(full) + r" surfaces. Interestingly, some keyword forms are never seen elsewhere: " + "; ".join(parts)
        + r". The identifier forms (e.g.\ \texttt{metamorphic\_relation}) are essentially code-only." "\n")

    a1 = mt["a1"]
    top_c = [r for r in a1["code"] if not r["subset_of"]][:3]
    top_n = [r for r in a1["noncode"] if not r["subset_of"]][:3]
    add(r"\paragraph{Technique keywords (A1).} In the code of the " + n(a1["code_repos"]) + r" repositories, the most frequent forms are "
        + ", ".join(rf"\emph{{{esc(r['label'])}}} ({n(r['hits'])} lines in {n(r['repos'])} repositories)" for r in top_c)
        + r". In the " + n(a1["noncode_items"]) + r" verified issues, pull requests, commits, discussions and repository descriptions, the leading forms are "
        + ", ".join(rf"\emph{{{esc(r['label'])}}} ({n(r['items'])} items)" for r in top_n) + "." "\n")

    # ======================= RQ2 ===========================================================
    add(r"\section{RQ2 -- Usage and classification}" "\n")
    a2 = mt["a2"]
    inc = a2["usage"] + a2["non_usage"]
    ex = (mt.get("excluded") or {}).get("code_reasons", {})
    add(r"\paragraph{Usage vs.\ non-usage (A2).} Of the " + n(a2["status"]["searched"]) + r" code-surface repositories found by the search, "
        + n(inc) + r" still contain an MT phrase today (excluded: " + n(ex.get("no longer available", 0)) + r" deleted or private, "
        + n(ex.get("no technique hit now", 0)) + r" no longer containing a phrase, "
        + n(ex.get("scan failed", 0) + ex.get("not scanned yet", 0)) + r" could not be scanned). "
        + r"\textbf{" + n(a2["usage"]) + r" (" + pct(a2["usage"] / inc * 100) + r") are \emph{usage} repositories}, with a technique phrase in at least one code file; "
        + n(a2["non_usage"]) + r" (" + pct(a2["non_usage"] / inc * 100) + r") mention MT only outside code (documentation, configuration, data)." "\n")

    b = mt["a3"]["usage"]["buckets"]
    pooled = sum(v["files"] for v in b.values()) or 1
    lab = [("tech_test", "Technique test files"), ("gen_test", "Other test files"),
           ("tech_nontest", "Technique non-test code files"), ("nontest", "Other non-test code files")]
    add(table(rf"Code files of the {n(mt['a3']['usage']['repos'])} MT usage repositories (A3).", "tab:mt-a3", "@{}lrrrr@{}",
              ["Code-file category", "Mean \\% per repo", "Median \\%", "Files", "\\% of all files"],
              [[l, pct(b[k]["avg_pct"]), pct(b[k]["median_pct"]), n(b[k]["files"]), pct(b[k]["files"] / pooled * 100)] for k, l in lab],
              r"\emph{Technique} = the file contains an MT phrase or identifier. Test files: test-file naming conventions "
              r"(e.g.\ \texttt{test\_*.py}, \texttt{*Test.java}, \texttt{*.spec.ts}), pytest/JUnit imports or \texttt{@Test}, or a "
              r"test/spec directory. Mean and median are taken over repositories."))

    b4 = mt["a4"]["buckets"]
    add(r"\paragraph{Non-usage repositories (A4).} In the " + n(mt["a4"]["repos"]) + r" non-usage repositories, MT appears in "
        + pct(b4["tech_doc"]["avg_pct"]) + r" of documentation files and " + pct(b4["nondoc_tech"]["avg_pct"])
        + r" of other non-code files on average, i.e.\ typically in a handful of README, notes or data files." "\n")

    a5 = mt["a5"]
    rows = [[esc(r["language"]), n(r["repos"]),
             pct(r.get("share_base_pct")) if r.get("share_base_pct") is not None else "--",
             pct(r.get("github_share_pct"), 2) if r.get("github_share_pct") is not None else "--",
             (rf"\textbf{{{r['lift']:.2f}}}" if r.get("lift") and r["lift"] >= 2 else (f"{r['lift']:.2f}" if r.get("lift") else "--"))]
            for r in a5["rows"][:15]]
    bl = a5["baseline"]
    add(table("Primary language of the MT code-surface repositories, normalised by GitHub-wide popularity (A5).", "tab:mt-a5",
              "@{}lrrrr@{}", ["Language", "Repositories", "MT share", "GitHub share", "Lift"], rows,
              r"Both shares are taken over the " + str(bl.get("languages")) + r" languages with a GitHub-wide count: MT share = of the "
              + n(bl.get("repos") or 0) + r" MT repositories in those languages; GitHub share = of the " + n(bl.get("github_repos") or 0)
              + r" public repositories in those languages pushed since " + esc(bl.get("pushed_since") or "") +
              r" (GitHub repository search). Lift = MT share $\div$ GitHub share; values above 1 mean the "
              r"language is over-represented among MT repositories (bold: $\geq 2$)."))

    a6 = mt["a6"]
    nn = a6["repos_verified"] or 1
    from core_helpers import config as cfg
    doms = sorted(cfg.DOMAIN_KEYWORDS, key=lambda d: -g(a6["with_readme"], d))
    dname = {"machine_learning": "Machine learning", "web_api": "Web / APIs", "database": "Databases",
             "compiler_pl": "Compilers / programming languages", "security_crypto": "Security / cryptography",
             "operating_systems": "Operating systems", "scientific_computing": "Scientific computing",
             "finance": "Finance", "autonomous_robotics": "Autonomous systems / robotics",
             "distributed_systems": "Distributed systems", "embedded_iot": "Embedded / IoT", "bioinformatics": "Bioinformatics"}
    rows = [[dname.get(d, esc(d)), n(g(a6["desc_topics"], d)), pct(g(a6["desc_topics"], d) / nn * 100),
             n(g(a6["with_readme"], d)), pct(g(a6["with_readme"], d) / nn * 100)] for d in doms]
    rows += ["MID", [r"\emph{No domain matched}", n(a6["no_match_desc_topics"]), pct(a6["no_match_desc_topics"] / nn * 100),
                     n(a6["no_match_with_readme"]), pct(a6["no_match_with_readme"] / nn * 100)]]
    add(table(rf"Application domain of the {n(a6['repos_verified'])} repositories with a verified non-code MT result (A6).",
              "tab:mt-a6", "@{}lrrrr@{}",
              ["Domain", r"\shortstack{Description\\+ topics}", "\\%", r"\shortstack{+ README}", "\\%"], rows,
              r"Keyword matching against an ACM CCS-based domain vocabulary (whole words). Description + topics: any domain keyword; "
              r"+ README: the README adds a domain only if it contains at least three different keywords of that domain. A repository "
              r"can have several domains. Heuristic; ten random repositories per domain are listed for manual checking."))

    a7 = mt["a7"]
    wc1 = fig_wordcloud(a7["whitelist_freq"], "mt_a7_wordcloud_domain.png", C["mt"])
    wc2 = fig_wordcloud(a7["freq"], "mt_a7_wordcloud_all.png", "#3F3F3F")
    if wc1 and wc2:
        add(r"""\begin{figure}[htbp]
\centering
\begin{subfigure}{\linewidth}\centering\includegraphics[width=0.92\linewidth]{""" + wc1 + r"""}\caption{Domain vocabulary only}\end{subfigure}
\par\medskip
\begin{subfigure}{\linewidth}\centering\includegraphics[width=0.92\linewidth]{""" + wc2 + r"""}\caption{All words (stopwords removed)}\end{subfigure}
\caption{Word clouds of the README and project description of the """ + n(a7["repos"]) + r""" repositories with a verified non-code MT result (A7; """ + n(a7["with_readme"]) + r""" with a README). Each word counts once per repository; size $\propto \sqrt{\text{repositories}}$.}
\label{fig:mt-a7}
\end{figure}
""")

    add(r"\paragraph{Repository classification.} \note{Manual classification of the " + n(a2["usage"]) + r" usage repositories "
        r"(actual usage / framework / research artifact / unknown) is in progress (\texttt{usage\_repos\_for\_review.csv}); results to be added.}" "\n")

    # ======================= RQ3 ===========================================================
    add(r"\section{RQ3 -- Timeline (commit search)}" "\n")
    t8, t9 = mt["t8"], mt["t9"]
    f = mt_surge_facts()
    peak, prev = f["peak"], f["peak"] - 1
    ag_first = g(t8["adopting_with_agent_first_commit"], peak)
    add(r"Commits are taken from GitHub's commit search (default branches; the whole history is searchable: "
        + n((mt.get("coverage") or {}).get("inactive_1y")) + r" of " + n((mt.get("coverage") or {}).get("ok"))
        + r" sampled repositories had been inactive for over a year). A commit is a \emph{technique commit} if its message contains an MT phrase. "
        r"Each repository is counted once, in the year of its first technique commit (Figure~\ref{fig:mt-t8}); a commit message "
        r"mentioning MT does not necessarily mean MT is in the code." "\n")
    add(figure(fig_mt_first_commit(mt), r"Metamorphic testing: repositories by year of their first commit mentioning the technique (T8), "
               r"split by whether that commit carries an AI-agent authorship line (e.g.\ \texttt{Co-Authored-By: Claude}; a lower bound). "
               rf"* {yr}: January--August.", "fig:mt-t8"))
    add(r"\paragraph{The " + str(peak) + r" surge.} " + n(g(t8["adopting_repos"], peak)) + r" repositories made their first MT commit in "
        + str(peak) + r" (to the end of August), against " + n(g(t8["adopting_repos"], prev)) + r" in " + str(prev)
        + r" and about 20 per year before that. They belong to " + n(f["owners"]) + r" different owners, "
        + pct(f["created_same_year"] / f["repos"] * 100, 0) + r" were created in " + str(peak) + r", and "
        + pct(f["single_commit"] / f["repos"] * 100, 0) + r" have a single technique commit. " + pct(ag_first / f["repos"] * 100, 0)
        + r" of these first commits, and " + pct(g(t9["agent_marked"], peak) / g(t9["relevant"], peak) * 100, 0)
        + r" of all " + n(g(t9["relevant"], peak)) + r" technique commits in " + str(peak)
        + r", carry an AI-agent authorship line (a lower bound, since several agents leave no trace). The rise is gradual "
        r"from late " + str(prev) + r" rather than a single burst, and no search artefact explains it (complete search, no "
        r"concentration in a few accounts, no copied commit messages)." "\n")
    add(figure(fig_mt_commits(mt), r"Metamorphic testing: technique commits per year (T9), with the AI-agent-marked share. "
               rf"* {yr}: January--August.", "fig:mt-t9"))
    add(figure(fig_mt_creation(mt), r"Creation year of the " + n(t8.get("creation", {}).get("repos")) + r" repositories with at least one "
               rf"MT commit. * {yr}: January--August.", "fig:mt-creation"))
    ys = [y for y in years_of(t9["relevant"]) if y >= 2018]
    rows = [[str(y), n(g(t8["adopting_repos"], y)), n(g(t8["adopting_with_agent_first_commit"], y)), n(g(t9["relevant"], y)),
             n(g(t9["agent_marked"], y)),
             pct(g(t9["agent_marked"], y) / g(t9["relevant"], y) * 100, 0) if g(t9["relevant"], y) else "--", n(g(t9["repos"], y))]
            for y in ys]
    add(table("Metamorphic testing timeline from the commit search (T8, T9), " + str(ys[0]) + "--" + str(ys[-1]) + ".", "tab:mt-timeline",
              "@{}lrrrrrr@{}", ["Year", r"\shortstack{First-commit\\repos}", r"\shortstack{...agent-\\marked}",
                                r"\shortstack{Technique\\commits}", r"\shortstack{Agent-\\marked}", "Agent \\%", r"\shortstack{Repos with\\commits}"],
              rows, rf"{yr}: January--August. Agent-marked: commit message carries an AI-agent authorship line (lower bound)."))

    # ======================= Comparison ====================================================
    add(r"\section{Comparison with property-based testing and fuzz testing}" "\n")
    add(r"The same pipeline was run for property-based testing (PBT) and fuzz testing, with explicit technique phrases only "
        r"(no tool or library names). Adoption and timeline are compared below." "\n")
    rows = []
    for x in SURFACES:
        r = [SURF_LABEL[x]]
        for t in ("mt", "pbt", "fuzz"):
            s2t = S[t]["s2"]
            if x == "code" and s2t.get("code_verified_est"):
                ce = s2t["code_verified_est"]
                r.append(rf"$\approx${n(ce['estimate'])} $\pm$ {n(ce['ci'])}" if ce["known"] else r"\note{pending}")
            else:
                r.append(n(g(s2t["repos"], x)))
        rows.append(r)
    rows += ["MID", ["Code-surface repositories found by search"] + [n(S[t]["s2"]["repos"]["code"]) if t != "mt" else n(S["mt"]["a2"]["status"]["searched"]) for t in ("mt", "pbt", "fuzz")]]
    add(table("Adoption: verified repositories per search surface for the three techniques.", "tab:cmp-adoption", "@{}lrrr@{}",
              ["Surface", "MT", "PBT", "Fuzz"], rows,
              r"MT: every repository verified. PBT, fuzz: code-surface count estimated from the random sample (share of sampled "
              r"repositories whose current snapshot contains a phrase $\times$ repositories found; $\pm$ 95\% CI). Non-code surfaces of PBT "
              r"and fuzz are lower bounds: GitHub's 1{,}000-result cap truncated parts of their commit, pull-request and issue searches."))
    add(figure(fig_cmp_surfaces(S), r"Verified repositories per search surface (log scale). Code surface of PBT and fuzz: sample estimate with 95\% CI.",
               "fig:cmp-surfaces"))

    # ---- A7 across techniques ---------------------------------------------------------------
    A7 = {t: S[t].get("a7") or {} for t in SLUGS}
    if all(A7[t].get("whitelist_freq") for t in SLUGS):
        add(r"\subsection{Project descriptions (A7)}" "\n")
        add(r"README and project description of repositories with a verified non-code result: all " + n(A7["mt"]["repos"])
            + r" for MT, and the random samples of " + n(A7["pbt"]["repos"]) + r" (PBT) and " + n(A7["fuzz"]["repos"])
            + r" (fuzz) repositories. Each word counts once per repository. The domain vocabulary ("
            + n(A7["mt"]["whitelist_vocab_size"]) + r" words) is the same for all three techniques, so its word clouds and "
            r"shares are directly comparable (Table~\ref{tab:cmp-a7}, Figures~\ref{fig:cmp-a7-domain} and~\ref{fig:cmp-a7-all})." "\n")
        TOP = 15
        top = {t: sorted(A7[t]["whitelist_freq"].items(), key=lambda kv: (-kv[1], kv[0]))[:TOP] for t in SLUGS}
        tops = {t: {w for w, _ in top[t]} for t in SLUGS}
        common = tops["mt"] & tops["pbt"] & tops["fuzz"]

        def cell(t: str, i: int) -> str:
            if i >= len(top[t]):
                return "-- & --"
            w, c = top[t][i]
            word = esc(w)
            if not any(w in tops[o] for o in SLUGS if o != t):
                word = rf"\textbf{{{word}}}"
            return rf"{word} & {pct(c / A7[t]['repos'] * 100, 0)}"
        rows = [[str(i + 1)] + [cell(t, i) for t in ("mt", "pbt", "fuzz")] for i in range(TOP)]
        add(table(rf"Top {TOP} domain-vocabulary words in the README and description, as a share of repositories (A7).",
                  "tab:cmp-a7", "@{}rlrlrlr@{}", [r"\#", "MT", r"\%", "PBT", r"\%", "Fuzz", r"\%"], rows,
                  r"\% = share of the technique's repositories whose README or description contains the word. "
                  rf"\textbf{{Bold}}: in the top {TOP} of this technique only. In the top {TOP} of all three: "
                  + (", ".join(esc(w) for w in sorted(common)) or "none") + "."))

        def cloud_fig(kind: str, title: str, label: str) -> None:
            paths = {t: fig_wordcloud(A7[t][kind], f"cmp_a7_{kind}_{t}.png", C[t]) for t in SLUGS}
            subs = "\n\\par\\medskip\n".join(
                r"\begin{subfigure}{\linewidth}\centering\includegraphics[width=0.86\linewidth]{" + paths[t]
                + r"}\caption{" + LONG[t] + " (" + n(A7[t]["repos"]) + r" repositories)}\end{subfigure}" for t in SLUGS)
            add(r"\begin{figure}[p]" "\n" r"\centering" "\n" + subs + "\n"
                + r"\caption{" + title + r" Size $\propto \sqrt{\text{repositories}}$.}" "\n"
                + r"\label{" + label + "}\n" + r"\end{figure}" "\n")
        cloud_fig("whitelist_freq", "Word clouds of the README and description, domain vocabulary only (A7).", "fig:cmp-a7-domain")
        cloud_fig("freq", "Word clouds of the README and description, all words (stopwords removed; A7).", "fig:cmp-a7-all")

    add(figure(fig_cmp_first_commit(S), r"Repositories by year of their first commit mentioning the technique (log scale). Solid: "
               r"counts corrected for GitHub's 1{,}000-result cap (PBT: exact recount; fuzz: random-window estimate with 95\% CI where "
               r"available); dotted: as collected. " + rf"{yr}: January--August.", "fig:cmp-first-commit"))
    ser = {t: first_commit_series(S[t]) for t in SLUGS}
    ash = {t: agent_share_series(S[t]) for t in SLUGS}
    ys = [y for y in range(2020, yr + 1)]

    def cell_fc(t, y):
        e = ser[t].get(y)
        if not e:
            return "--"
        if e["corrected"] and not e["exact"]:
            return rf"{n(e['value'])} $\pm$ {n(e['ci'])}"
        mark = "" if (t == "mt" or e["corrected"]) else r"$^{\dagger}$"
        return n(e["value"]) + mark

    def cell_ag(t, y):
        e = ash[t].get(y)
        if not e or e["value"] is None:
            return "--"
        if e["corrected"] and not e["exact"]:
            return rf"{e['value'] * 100:.0f}\% $\pm$ {e['ci'] * 100:.0f}"
        return f"{e['value'] * 100:.0f}\\%" + ("" if (t == "mt" or e["corrected"]) else r"$^{\dagger}$")
    rows = [[str(y)] + [cell_fc(t, y) for t in ("mt", "pbt", "fuzz")] + [cell_ag(t, y) for t in ("mt", "pbt", "fuzz")] for y in ys]
    add(table("Timeline comparison: repositories by year of first technique commit, and AI-agent-marked share of technique commits.",
              "tab:cmp-timeline", "@{}lrrrrrr@{}",
              ["Year", "MT", "PBT", "Fuzz", "MT", "PBT", "Fuzz"], rows,
              rf"{yr}: January--August. PBT: exact recount of the capped commit-search ranges. Fuzz: $\pm$ = 95\% CI of the random-window "
              r"estimate; $^{\dagger}$ as collected, a lower bound for fuzz (its commit search was capped in every year).",
              prehead=r" & \multicolumn{3}{c}{First-commit repositories} & \multicolumn{3}{c}{Agent-marked share} \\ "
                      r"\cmidrule(lr){2-4}\cmidrule(lr){5-7}"))
    add(figure(fig_cmp_agent_share(S), r"Share of technique commits with an AI-agent authorship line (lower bound), 2025 and " + str(yr)
               + r" (January--August). Fuzz: estimate with 95\% CI.", "fig:cmp-agent", width=r"0.68\linewidth"))

    add(r"\end{document}" "\n")
    return "\n".join(L)


def main() -> None:
    FIG.mkdir(parents=True, exist_ok=True)
    for p in FIG.glob("*"):
        p.unlink()
    tex = build()
    (OUT / "shared_data.tex").write_text(tex, encoding="utf-8")
    print(f"Written: {OUT / 'shared_data.tex'} and {len(list(FIG.glob('*')))} figures in {FIG}")


if __name__ == "__main__":
    main()
