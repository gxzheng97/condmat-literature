#!/usr/bin/env python3
"""One-time AI editorial re-screen of the October 23, 2026 issue.

Reconsider ALL candidates from the original collected issue, but only those
from the nine agreed journals or arXiv. Preserve existing curated metadata for
retained papers. Abort rather than publish a partially AI-screened result.
"""
import json
import subprocess
from pathlib import Path
from relevance import screen
from update_daily import enrich

ROOT=Path(__file__).resolve().parent
ISSUE=ROOT/"issues"/"2026-10-23.json"
ORIGINAL_COMMIT="6817bab14476896"
ALLOWED_JOURNALS=("science", "science advances", "nature", "nature physics",
                  "nature materials", "nature communications", "prl",
                  "physical review letters", "prx", "physical review x", "pnas")

def is_allowed(p):
    if p.get("type")=="arXiv" or str(p.get("journal","")).lower().startswith("arxiv:"):
        return True
    if p.get("type")!="Journal":
        return False
    journal=str(p.get("journal","")).strip().lower()
    # Match journal names exactly, apart from article number/citation suffixes.
    for name in ALLOWED_JOURNALS:
        if journal==name or journal.startswith(name+" "):
            return True
    return False

def main():
    original=json.loads(subprocess.check_output(
      ["git","show", ORIGINAL_COMMIT+":issues/2026-10-23.json"],
      cwd=ROOT,text=True))
    existing=json.loads(ISSUE.read_text(encoding="utf-8"))
    existing_by_id={p["id"]:p for p in existing["papers"]}
    unique={}
    for p in original["papers"]:
        if is_allowed(p):
            unique.setdefault(p["id"],p)
    candidates=list(unique.values())
    # Keep the bibliography, bilingual notes and original-figure commentary
    # already curated for any article that survives the new screen.
    for p in candidates:
        if p["id"] in existing_by_id:
            p.update(existing_by_id[p["id"]])
    print(f"RE-SCREEN original={len(original['papers'])}, eligible_sources={len(candidates)}, curated_before={len(existing_by_id)}",flush=True)
    kept,stats=screen(candidates,use_ai=True)
    print("RE-SCREEN assessment",json.dumps(stats,sort_keys=True),flush=True)
    if stats["ai_assessed"]!=len(candidates):
        raise RuntimeError("Not all candidates received an AI assessment. No archive files changed.")
    if not kept:
        raise RuntimeError("AI screening returned no papers. Not modifying issue.")
    # Choose featured articles by scientific distinctiveness/relevance,
    # not by the host journal's impact factor.
    ranked=sorted(kept,key=lambda p:float(p.get("relevance_score") or 0),reverse=True)
    proposed=[p for p in ranked if p.get("feature_candidate")]
    chosen=(proposed+[p for p in ranked if p not in proposed])[:min(3,len(kept))]
    feature_ids={p["id"] for p in chosen}
    for p in kept:
        p["level"]="Feature" if p["id"] in feature_ids else "Brief"
    # Add bilingual notes to newly included entries.
    new_entries=[p for p in kept if p["id"] not in existing_by_id]
    if new_entries:
        enrich(new_entries)
    # Source order is applied in web rendering and PDF creation.
    kept.sort(key=lambda p:(p["level"]!="Feature",p.get("type")!="Journal",
                            -float(p.get("relevance_score") or 0),p.get("title","")))
    revised=dict(existing)
    revised["papers"]=kept
    revised["stats"]={
       **existing.get("stats",{}),
       "ai_rescreened":True,
       "ai_rescreen_source":"original Oct 23 candidates from nine journals + arXiv",
       "original_candidates":len(original["papers"]),
       "within_source_scope":len(candidates),
       "ai_assessed":stats["ai_assessed"],
       "selected_after_ai":len(kept),
       "rejected_after_ai":stats["rejected"],
       "featured":len(feature_ids)
    }
    revised["note"]="October 23 issue re-screened using API-based semantic assessment; retained original reports where applicable."
    temp=ISSUE.with_suffix(".json.new")
    temp.write_text(json.dumps(revised,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    temp.replace(ISSUE)
    print(f"RE-SCREEN SUCCESS: {len(candidates)} AI-assessed, {len(kept)} retained, {len(feature_ids)} featured",flush=True)
    for p in chosen:
        print("FEATURED:",p["title"],"| score",p.get("relevance_score"),flush=True)

if __name__=="__main__":
    main()
