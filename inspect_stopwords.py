"""
Print the wordcloud library's built-in STOPWORDS and demonstrate
what _word_set filters vs keeps on a sample sentence.
"""
from wordcloud import STOPWORDS
import re

# --- 1. Print all built-in stopwords, sorted ---
sw = sorted(STOPWORDS)
print(f"=== wordcloud built-in STOPWORDS ({len(sw)} words) ===")
for i in range(0, len(sw), 10):
    print("  ", "  ".join(sw[i:i+10]))

# --- 2. Show which 3-letter words are NOT covered (would slip through) ---
sample = (
    "non per add run use set now end key top pre via two one new old "
    "all any but can did for get has its may not out was way yet ago "
    "few got had let lot own say see too put big bit cut due far hit "
    "low ten yes nor pro sub ref src tmp foo bar baz env cmd log llm "
    "api cnn rnn gan dnn svm knn mlp gpt gnn rag"
)
words_3 = re.findall(r"[a-z]{3,}", sample.lower())
not_covered = [w for w in words_3 if w not in STOPWORDS]
covered     = [w for w in words_3 if w in STOPWORDS]

print(f"\n=== 3-letter sample words NOT in built-in STOPWORDS ({len(not_covered)}) ===")
print("  ", "  ".join(sorted(not_covered)))

print(f"\n=== 3-letter sample words COVERED by built-in STOPWORDS ({len(covered)}) ===")
print("  ", "  ".join(sorted(covered)))

# --- 3. Show what survives the current _word_set (min 3, no custom adds) ---
print("\n=== Domain acronyms that SHOULD survive ===")
domain = ["llm", "api", "cnn", "rnn", "gan", "dnn", "svm", "knn", "mlp", "gpt", "gnn", "rag"]
for w in domain:
    status = "FILTERED (in STOPWORDS)" if w in STOPWORDS else "KEPT (not in STOPWORDS)"
    print(f"  {w:6s} -> {status}")
