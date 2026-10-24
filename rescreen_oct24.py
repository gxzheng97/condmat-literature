#!/usr/bin/env python3
"""One-time strict AI re-screen for the 2026-10-24 issue.

Starts from all 124 candidates visible in the mistakenly oversized archive.
No hidden fallbacks or partially screened reports are published.
"""
import json
from pathlib import Path
from relevance import screen
from update_daily import enrich

ROOT=Path(__file__).resolve().parent
ISSUE=ROOT/"issues"/"2026-10-24.json"

def main():
    issue=json.loads(ISSUE.read_text(encoding="utf-8"))
    original=issue["papers"]
    # Do not claim to re-review the ~77 discarded by the original screen.
    selected,stats=screen(original,use_ai=True,max_papers=30)
    if stats["ai_assessed"]!=len(original) or not stats["global_editorial"]:
        raise RuntimeError("Not all 124 paper records received completed two-pass AI review")
    if not 8<=len(selected)<=30:
        raise RuntimeError("Unexpected shortlist size: do not overwrite archive")
    feature=[p for p in selected if p.get("feature_candidate")]
    if not feature:
        feature=selected[:min(3,len(selected))]
    feature_ids={p["id"] for p in feature[:4]}
    for p in selected:
        p["level"]="Feature" if p["id"] in feature_ids else "Brief"
    # Supply actual paper notes for the newly featured articles.
    needs_notes=[p for p in selected if p["level"]=="Feature" and not p.get("method_en")]
    if needs_notes:
        enrich(needs_notes)
    issue["papers"]=selected
    issue["stats"]={
        "original_arxiv_journal_candidates":issue.get("stats",{}).get("scanned",201),
        "oversized_index_before":len(original),
        "ai_assessed":stats["ai_assessed"],
        "first_pass_selected":stats["first_pass_selected"],
        "selected_after_global_editorial":len(selected),
        "excluded_from_oversized_index":len(original)-len(selected),
        "featured":len(feature_ids),
        "global_editorial":True,
        "two_pass_review":True,
    }
    issue["note"]="October 24 archive re-screened by two-stage semantic review and global research-editor shortlist."
    temp=ISSUE.with_suffix(".json.tmp")
    temp.write_text(json.dumps(issue,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    temp.replace(ISSUE)
    print("AI RESCREEN SUCCESS:",json.dumps(issue["stats"]),flush=True)
    for p in selected:
        print(("FEATURE" if p["level"]=="Feature" else "INDEX"),
              p["relevance_score"],p["title"],flush=True)

if __name__=="__main__":
    main()
