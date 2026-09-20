"""
Deeper inspection: compute actual cross-repo word frequencies from
noncode_results.json and code_repos.json, then classify each top word.
"""
import json, re
from collections import Counter
from pathlib import Path
from wordcloud import STOPWORDS

SLUG = "metamorphic_testing"   # change if needed
BASE = Path(__file__).parent / "results" / SLUG / "analysis"

# --- load data ---
def load(p):
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    print(f"  MISSING: {p}")
    return []

noncode = load(BASE / "noncode_results.json")
code    = load(BASE / "code_repos.json")

# --- cross-repo binary counting (same logic as analysis.py) ---
repo_word_sets: dict[str, set] = {}

for r in noncode:
    repo = r.get("repo_full_name") or r.get("id", "unknown")
    ws   = set(r.get("word_set", []))
    repo_word_sets.setdefault(repo, set()).update(ws)

for r in code:
    repo = r.get("full_name", "")
    ws   = set(r.get("doc_word_set", []))
    if repo and ws:
        repo_word_sets.setdefault(repo, set()).update(ws)

freq: Counter = Counter()
for words in repo_word_sets.values():
    for w in words:
        freq[w] += 1

total_repos = len(repo_word_sets)
print(f"Repos contributing words: {total_repos}")
print(f"Unique words: {len(freq)}")

# --- current custom additions (from _load_stopwords) ---
custom_stops = {
    "com","org","net","github","http","https","www","html",
    "blob","tree","main","master","refs","head","raw","git",
    "repo","repos","repository","repositories",
    "issue","issues","pull","request","requests",
    "commit","commits","branch","branches",
    "merge","merged","release","releases",
    "bug","bugs","error","errors","fix","fixed","fixes",
    "build","built","update","updated","change","changes",
    "file","files","line","lines","path","paths",
    "version","feature","support","implement","implementation",
    "function","method","class","module","package",
    "import","return","value","type","string","object",
    "true","false","none","null","bool","int","str",
    "var","val","arg","param","config","option","default",
    "data","result","output","input","user","name","number",
    "project","work","step","note","example","open","close",
}
all_stops = STOPWORDS | custom_stops

print("\n=== TOP 100 words by cross-repo frequency ===")
print(f"{'Rank':<5} {'Word':<20} {'Freq':>6}  {'%repos':>7}  Status")
print("-" * 60)
for rank, (word, cnt) in enumerate(freq.most_common(100), 1):
    pct = cnt / total_repos * 100
    if word in STOPWORDS:
        status = "STOPWORDS (built-in)"
    elif word in custom_stops:
        status = "STOPWORDS (custom)"
    else:
        status = "*** NOT FILTERED ***"
    print(f"{rank:<5} {word:<20} {cnt:>6}  {pct:>6.1f}%  {status}")

# --- words in top 100 that are not filtered at all ---
unfiltered = [(w, c) for w, c in freq.most_common(100) if w not in all_stops]
print(f"\n=== Unfiltered words in top 100 ({len(unfiltered)}) ===")
print("These are candidates to add to custom stopwords OR keep as meaningful signal:")
for w, c in unfiltered:
    pct = c / total_repos * 100
    print(f"  {w:<20} freq={c:>5}  {pct:.1f}% of repos")
