"""
01_consolidate.py
Merges usage_repos_for_review.csv + repo_readmes.json + cloned_repo_metadata.json
into BATCH_SIZE-repo batch JSON files ready for LLM classification.

Usage: python3 -I 01_consolidate.py
"""

import csv
import json
import math
import os

BATCH_SIZE = 50
BASE = os.path.dirname(os.path.abspath(__file__))
MT_BASE = os.path.join(BASE, "..", "metamorphic_testing")

USAGE_CSV      = os.path.join(MT_BASE, "sections_report", "usage_repos_for_review.csv")
READMES_JSON   = os.path.join(MT_BASE, "analysis", "repo_readmes.json")
METADATA_JSON  = os.path.join(MT_BASE, "analysis", "cloned_repo_metadata.json")
BATCHES_DIR    = os.path.join(BASE, "batches")
MANIFEST_PATH  = os.path.join(BASE, "batches", "manifest.json")

README_MAX_CHARS = 3000  # cap per repo to keep batch files manageable


def load_sources():
    with open(USAGE_CSV, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    with open(READMES_JSON, encoding="utf-8") as f:
        readmes = json.load(f)

    with open(METADATA_JSON, encoding="utf-8") as f:
        metadata = json.load(f)

    return rows, readmes, metadata


def enrich(row, readmes, metadata):
    repo = row["repo"]

    # README: prefer full (capped), fallback to 600-char excerpt
    full_readme = (readmes.get(repo) or "").strip()
    excerpt = (row.get("readme_excerpt") or "").strip()
    if full_readme:
        readme_text = full_readme[:README_MAX_CHARS]
        readme_source = "full"
    elif excerpt:
        readme_text = excerpt
        readme_source = "excerpt"
    else:
        readme_text = ""
        readme_source = "none"

    meta = metadata.get(repo) or {}
    topics = meta.get("topics") or []
    created_at = meta.get("created_at", "")

    sample_files = [
        p for p in (row.get("sample_technique_files") or "").split("|")
        if p.strip()
    ][:12]  # keep at most 12 file path hints

    return {
        "repo": repo,
        "url": row.get("url", f"https://github.com/{repo}"),
        "stars": int(row.get("stars") or 0),
        "language": row.get("language", ""),
        "created_at": created_at,
        "technique_test_files": int(row.get("technique_test_files") or 0),
        "technique_nontest_files": int(row.get("technique_nontest_files") or 0),
        "code_files": int(row.get("code_files") or 0),
        "sample_technique_files": sample_files,
        "description": (row.get("description") or "").strip(),
        "topics": topics,
        "readme": readme_text,
        "readme_source": readme_source,
    }


def write_batches(enriched):
    n_batches = math.ceil(len(enriched) / BATCH_SIZE)
    os.makedirs(BATCHES_DIR, exist_ok=True)
    manifest = {"total_repos": len(enriched), "batch_count": n_batches, "batch_size": BATCH_SIZE, "batches": []}

    for i in range(n_batches):
        batch = enriched[i * BATCH_SIZE : (i + 1) * BATCH_SIZE]
        fname = f"batch_{i:03d}.json"
        fpath = os.path.join(BATCHES_DIR, fname)
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(batch, f, ensure_ascii=False, indent=2)
        manifest["batches"].append({"index": i, "file": fname, "count": len(batch)})

    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    return n_batches


def main():
    print("Loading source data...")
    rows, readmes, metadata = load_sources()
    print(f"  {len(rows)} usage repos in CSV")
    print(f"  {len(readmes)} full READMEs available")
    print(f"  {len(metadata)} repo metadata entries")

    print("Enriching repos...")
    enriched = [enrich(r, readmes, metadata) for r in rows]

    readme_sources = {"full": 0, "excerpt": 0, "none": 0}
    for e in enriched:
        readme_sources[e["readme_source"]] += 1
    print(f"  README coverage: full={readme_sources['full']}, excerpt={readme_sources['excerpt']}, none={readme_sources['none']}")

    print("Writing batch files...")
    n_batches = write_batches(enriched)
    print(f"  Wrote {n_batches} batches of up to {BATCH_SIZE} repos to {BATCHES_DIR}/")
    print(f"  Manifest: {MANIFEST_PATH}")
    print("Done.")


if __name__ == "__main__":
    main()
