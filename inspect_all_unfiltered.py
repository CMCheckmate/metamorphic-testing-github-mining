"""
List ALL unfiltered words above a frequency threshold, grouped by band,
saved to inspect_unfiltered_words.txt for manual review.

Usage: python inspect_all_unfiltered.py
Edit FREQ_THRESHOLD below to change the cutoff.
"""
import json, re
from collections import Counter
from pathlib import Path
from wordcloud import STOPWORDS

SLUG            = "metamorphic_testing"
FREQ_THRESHOLD  = 50      # minimum cross-repo frequency to include
BAND_BREAKS     = [500, 300, 200, 100, 50]   # frequency band boundaries

BASE = Path(__file__).parent / "results" / SLUG / "analysis"

def load(p):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []

noncode = load(BASE / "noncode_results.json")
code    = load(BASE / "code_repos.json")

# --- build cross-repo frequency ---
repo_word_sets: dict[str, set] = {}
for r in noncode:
    repo = r.get("repo_full_name") or r.get("id", "unknown")
    repo_word_sets.setdefault(repo, set()).update(r.get("word_set", []))
for r in code:
    repo = r.get("full_name", "")
    if repo:
        repo_word_sets.setdefault(repo, set()).update(r.get("doc_word_set", []))

freq: Counter = Counter()
for words in repo_word_sets.values():
    for w in words:
        freq[w] += 1

total_repos = len(repo_word_sets)

# --- load current custom stopwords (copy from non_code_analysis._load_stopwords) ---
from non_code_analysis import _load_stopwords
all_stops = _load_stopwords() | STOPWORDS

# --- collect unfiltered words above threshold ---
unfiltered = [
    (w, c) for w, c in freq.most_common()
    if w not in all_stops and c >= FREQ_THRESHOLD
]

# --- write report ---
out_path = Path(__file__).parent / "inspect_unfiltered_words.txt"
lines = []
lines.append(f"Repos: {total_repos}  |  Unique words total: {len(freq)}")
lines.append(f"Unfiltered words >= {FREQ_THRESHOLD} freq: {len(unfiltered)}")
lines.append("")

band_starts = BAND_BREAKS + [FREQ_THRESHOLD]
band_ends   = [99999] + BAND_BREAKS

for lo, hi in zip(reversed(band_starts), reversed(band_ends)):
    band = [(w, c) for w, c in unfiltered if lo <= c <= hi]
    if not band:
        continue
    lines.append(f"{'='*60}")
    lines.append(f"  BAND {lo}–{hi} freq  ({len(band)} words)")
    lines.append(f"{'='*60}")
    lines.append(f"  {'Word':<22} {'Freq':>6}  {'%repos':>7}")
    lines.append(f"  {'-'*40}")
    for w, c in band:
        lines.append(f"  {w:<22} {c:>6}  {c/total_repos*100:>6.1f}%")
    lines.append("")

out_path.write_text("\n".join(lines), encoding="utf-8")
print(f"Written {len(unfiltered)} words to {out_path}")
print(f"\nQuick view — top 30 unfiltered:")
for w, c in unfiltered[:30]:
    print(f"  {w:<22} {c:>5}  {c/total_repos*100:.1f}%")
