"""Editorial screening for an experimental condensed-matter literature digest.

Criterion: Does the paper advance understanding of a condensed-matter physical
phenomenon or open a credible experimental research direction? No topic-specific
blacklists. If an AI API key is available, consider the full abstract and the
scientific question; otherwise use a broader, explainable local scoring fallback.
"""
import json
import os
import re
import urllib.request
import urllib.error


# Signals represent physical QUESTIONS rather than generic publication keywords.
CONCEPTS = (
 (r"superconduct|josephson|cooper pair|vortex|meissner|andreev|shapiro", 3.0),
 (r"altermagnet|antiferromagnet|ferromagnet|ferrimagnet|magnetic (structure|order|phase|excitation|anisotrop)|spin order|spin excitation|spin wave|magnon|skyrmion|spin liquid|chirality|metamagnet", 2.9),
 (r"kondo|mott|heavy.fermion|strongly correlat|hubbard|flat.band|quantum critical|non.fermi|density.wave|excitonic insulat", 3.0),
 (r"anomalous hall|thermal hall|nernst|seebeck|thermoelectric (transport|effect|response)|quantum oscillat|magnetoresist|quantum transport|berry curvature|spin hall|magnetocaloric|elastocaloric", 2.8),
 (r"weyl|dirac semimetal|topological (phase|state|insulat|semimetal)|chern insulat|quantum hall|nontrivial topology", 2.8),
 (r"valence (transit|instab|fluctuat)|mixed valence|phase coexist|structural (phase )?transit|ferroelectric (order|transition|switch)|orbital order|nematic|symmetry break|spin.polarized", 2.6),
 (r"neutron scatter|muon spin|\bmuSR\b|torque magnet|heat capacity|specific heat|inelastic x.ray|angle.resolved photo|quantum capacit|spectroscop", 1.5),
 (r"spin.orbit (coupling|torque)|nonreciprocal|nonlinear hall|magneto.optical|kerr effect|strain.tuned|pressure.tuned|ferroelastic", 2.2),
 (r"quantum geometry|moire|moiré|landau level|exciton condens|valley polariz|polar chain|orbital magnet", 2.0),
 (r"thermal transport|thermal conduct|phonon transport|heat pulse|phonon hydrodynam|electron.phonon|thermal expansion", 1.4),
)

# Secondary signals of experimental relevance; insufficient by themselves.
METHODS = (
 r"transport|resistivit|magnetiz|hysteresis|diffraction|magnetic field|"
 r"critical temperature|critical field|heat capacity|single.crystal|"
 r"thermoelectric|angle.depend|spin dynamics|raman|scanning tunneling|"
 r"domain wall|strain|uniaxial|pressure|crystal growth|synthes|inelastic"
)
MATERIALS = r"\b[A-Z][a-z]?(?:[A-Z][a-z]?|[0-9]){2,}\b|\bkagome\b|\bvdW\b|\bvan der Waals\b|\btransition.metal\b"
NOVEL_PHYSICS = (
 r"phase transition|ground state|quantum phase|novel (state|phase|mechanism)|"
 r"emergent|first.observ|experimental evidence|observ(e|ed|ation)|"
 r"uncover|reveal|discover|spin texture|band inversion|magnetic ordering|"
 r"field.induced|structural transformation|critical behavior"
)
# Applied orientation is a weighting factor only, not an automatic exclusion.
APPLIED = (
 r"(device|circuit|sensor|computing|memory|lithograph|fabrication|"
 r"high.numerical.aperture|flat optics|lens|projection|sensing|"
 r"power efficiency|optoelectronic|high.electron.mobility transistor|"
 r"modulat|frequency converter|amplifier|engineering application)"
)
REVIEW = r"\b(review|perspective|tutorial|roadmap|overview|survey|benchmark|state.of.the.art)\b"


def _hits(pattern, text):
    return len(re.findall(pattern, text, flags=re.I))


def fallback_score(paper):
    """A conservative offline surrogate for scientific editorial judgment.

    Title has greater weight than abstract: a term mentioned incidentally in
    applications should not outweigh the actual goal of the research.
    """
    title = str(paper.get("title") or "")
    abstract = str(paper.get("abstract") or paper.get("summary_en") or "")
    normalized = title + " " + abstract
    title_score = 0.0
    context_score = 0.0
    concepts_in_title = 0
    for pattern, weight in CONCEPTS:
        if re.search(pattern, title, re.I):
            title_score += weight
            concepts_in_title += 1
        elif re.search(pattern, abstract, re.I):
            context_score += weight * 0.47
    title_score = min(title_score, 10.0)
    context_score = min(context_score, 3.0)
    score = title_score + context_score
    if _hits(METHODS, normalized):
        score += 0.95
    if re.search(MATERIALS, title):
        score += 0.45
    if _hits(NOVEL_PHYSICS, normalized):
        score += 0.75

    title_applied = _hits(APPLIED, title)
    abstract_applied = _hits(APPLIED, abstract)
    if title_applied:
        score -= min(3.8, 2.0 + 0.65 * (title_applied-1))
    if abstract_applied >= 3:
        score -= 0.8

    if re.search(REVIEW, title, re.I):
        score -= 2.5
    elif re.search(REVIEW, abstract[:220], re.I):
        score -= 0.9

    # No science concept in the title, but the abstract discusses one:
    # possibly a technique, synthesis study or applied component. Be selective
    # without disqualifying an emerging experimental platform.
    if not concepts_in_title:
        score -= 1.0

    return round(score, 2)


def _ai_batch(papers, key):
    """Read and assess every candidate using its physical question and claims."""
    rubric = (
      "You are making INCLUSION decisions for a serious, broad experimental "
      "CONDENSED-MATTER PHYSICS journal club. Be an exacting research editor: "
      "judge the paper's PRIMARY SCIENTIFIC ADVANCE, not just the occurrence "
      "of physics terms, its journal prestige, novelty claims, or a clever device. "
      "Ask: What new thing does this paper TEACH US ABOUT THE PHYSICS OF MATTER "
      "(electrons, spins, lattices, collective states, low-dimensional solid-state "
      "materials, or their transport, thermodynamics, symmetry or excitations)? "
      "Why would a broadly curious condensed-matter experimental physicist want "
      "to read it? Include new experimentally evidenced states, distinctive "
      "mechanisms, phase diagrams, unusual materials with important physics "
      "or credible experimentally testable theoretical predictions. "
      "Do not require known material names or a fashionable subfield. "
      "Theory, optical probes, synthesis, and devices can qualify WHEN the "
      "central contribution is a new fundamental material phenomenon. "
      "In contrast, do NOT include studies primarily about higher optical "
      "resolution, device speed/efficiency, sensor sensitivity, fabrication or "
      "integration, conventional materials optimization, general-purpose "
      "computational methodology, or survey of applications, unless they also "
      "establish an independent substantial discovery about condensed-matter "
      "physics. Ordinary superconducting-qubit quantum error correction, "
      "quantum algorithms, and quantum-information protocols are not condensed-"
      "matter discoveries solely because they use superconductors. "
      "Optical-system engineering is not a condensed-matter discovery solely "
      "because it uses diffraction or a nanostructured material. "
      "Ultracold-gas demonstrations and continuum fluids may qualify for "
      "this broad physics digest when they answer a distinctly "
      "transferable condensed-matter question. Reviews and technology roadmaps "
      "generally do not report original physics and should not enter. "
      "Do not blacklist entire research areas: the fundamental-physics content "
      "overrides subject labels when compelling. "
      "For EVERY paper independently return in_scope true ONLY if a concrete "
      "new condensed-matter physical understanding or experimentally useful "
      "insight is central. Reject superficially adjacent papers. "
      "Provide a calibrated score: 85-100 landmark/broadly exciting new "
      "condensed-matter physics; 70-84 strong original CM result; 55-69 "
      "credible narrower CM physical advance; 40-54 tangential science; "
      "0-39 chiefly engineering/application/quantum information/general methods. "
      "There is no target number of inclusions; favor high recall when the "
      "candidate pool mixes many adjacent domains; retain borderline papers with substantive original condensed-matter physics. "
      "Set feature_candidate true ONLY for substantial research discoveries "
      "or readily actionable predictions, never mainly for technology performance. "
      "Reply JSON exactly: {assessments:[{id,in_scope,score,feature_candidate,"
      "reason,physics_advance}]}. Reason must say why relevant or not in "
      "one sentence. physics_advance names the concrete NEW physical insight "
      "established, or empty string if there is none. All decisions must be "
      "based only on the supplied title and abstract; do not invent claims."
    )
    docs = [
      {"id":p.get("id"),"title":p.get("title"),"abstract":(p.get("abstract") or p.get("summary_en") or "")[:3300]}
      for p in papers
    ]
    payload={"model":"gpt-4.1-mini",
             "input":[{"role":"system","content":rubric},
                      {"role":"user","content":json.dumps(docs,ensure_ascii=False)}],
             "text":{"format":{"type":"json_object"}},"max_output_tokens":4500}
    req=urllib.request.Request(
      "https://api.openai.com/v1/responses",
      data=json.dumps(payload).encode(),method="POST",
      headers={"Authorization":"Bearer "+key,"Content-Type":"application/json"})
    try:
        response=json.loads(urllib.request.urlopen(req,timeout=110).read())
    except urllib.error.HTTPError as exc:
        try:
            details=json.loads(exc.read().decode("utf-8","replace")).get("error",{})
            reason=details.get("code") or details.get("type") or "unknown"
        except Exception:
            reason="unknown"
        raise RuntimeError(f"OpenAI API HTTP {exc.code}: {reason}") from None
    raw="".join(part.get("text","") for msg in response.get("output",[])
                for part in msg.get("content",[]) if part.get("type")=="output_text")
    result=json.loads(raw)
    assessments = result.get("assessments", [])
    if not isinstance(assessments,list):
        raise ValueError("Missing AI assessments")
    found={}
    for x in assessments:
        if not isinstance(x,dict) or "id" not in x or not isinstance(x.get("in_scope"),bool):
            raise ValueError("AI must provide a binary in_scope decision for every paper")
        found[str(x["id"])]=x
    expected={str(p["id"]) for p in papers}
    if any(pid not in found for pid in expected):
        raise ValueError("Incomplete AI assessment; rejecting partial batch")
    # The model may emit an extra (hallucinated) identifier. Ignore extras:
    # only actual input paper IDs can enter the editorial pipeline.
    return {pid:found[pid] for pid in expected}


def _ai_shortlist(papers, key, max_papers=30):
    """Comparative editorial choice across the *entire day's* candidates.

    Scores generated by independent small batches are not calibrated. An issue
    has to be composed as an issue, with one coherent relevance threshold.
    """
    instructions = (
      "You are the science editor preparing ONE compact daily literature index "
      "for a working EXPERIMENTAL CONDENSED-MATTER / QUANTUM MATERIALS physicist. "
      "Below is the complete candidate pool surviving a loose first assessment. "
      "Make one global and RELATIVE comparison, using the science of a paper "
      "rather than prestige or keyword overlap. "
      "Your readership studies emergent physical properties of SOLIDS, "
      "magnetism, superconductivity, electron correlations, quantum materials, "
      "topological electronic states, magnetic/transport/thermodynamic "
      "measurements, crystal growth with novel physical properties, symmetry "
      "and phase transitions, and experimentally actionable theory. "
      "Keep a broad range of new physical discoveries and valuable "
      "experimentally testable theory, not only fashionable materials. "
      "Prefer specific new measurements or a well-defined unexpected physical "
      "effect to abstract algorithmic advances, generic computation, materials "
      "optimization, performance-only devices, optics-system design, applied "
      "quantum sensing without material physics, biology, biophysics, "
      "plasma astrophysics, classical fluids, purely stochastic mathematical "
      "physics, or chemical synthesis without electronic/magnetic properties. "
      "A traditionally adjacent discipline CAN be kept when the central "
      "discovery has a clear new quantum-materials/condensed-matter phenomenon. "
      "Reviews, quantum algorithm benchmarks and generic methodological "
      "improvements generally do not merit space here without new material "
      "physics. "
      "Select only those papers a broad experimental quantum-materials "
      "researcher would reasonably want to CLICK to learn the physical "
      "result. Avoid filling the index: it is fine to have 15-25 papers "
      "from a large pool. A daily issue should normally be concise. "
      "NEVER select more than " + str(max_papers) + " articles. "
      "Provide JSON exactly: {selected_ids:[...],featured_ids:[...]}. "
      "Selected_ids must be in descending SCIENTIFIC RELEVANCE order. "
      "Featured_ids must be 2-4 papers chosen from selected_ids. "
      "Do not rank by impact factor or favor a subfield based on familiarity. "
      "Use only the paper titles and supplied abstracts. "
    )
    # Compact text preserves a comprehensive view without sending many long
    # repeated abstracts for this comparative second pass.
    docs = [{"id":p.get("id"),"title":p.get("title"),
             "abstract":(p.get("abstract") or p.get("summary_en") or "")[:1800],
             "journal":p.get("journal")} for p in papers]
    payload = {"model":"gpt-4.1-mini",
      "input":[{"role":"system","content":instructions},
               {"role":"user","content":json.dumps(docs,ensure_ascii=False)}],
      "text":{"format":{"type":"json_object"}},"max_output_tokens":3500}
    req = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode(),method="POST",
        headers={"Authorization":"Bearer "+key,"Content-Type":"application/json"})
    try:
        response=json.loads(urllib.request.urlopen(req,timeout=165).read())
    except urllib.error.HTTPError as exc:
        try:
            details=json.loads(exc.read().decode("utf-8","replace")).get("error",{})
            reason=details.get("code") or details.get("type") or "unknown"
        except Exception: reason="unknown"
        raise RuntimeError(f"OpenAI global editorial review HTTP {exc.code}: {reason}") from None
    raw="".join(c.get("text","") for o in response.get("output",[])
                for c in o.get("content",[]) if c.get("type")=="output_text")
    decision=json.loads(raw)
    allowed={str(p["id"]) for p in papers}
    ids=decision.get("selected_ids")
    if not isinstance(ids,list) or not ids:
        raise RuntimeError("Global editorial review returned no selection list")
    ids=[str(x) for x in ids]
    if len(ids)!=len(set(ids)) or any(x not in allowed for x in ids):
        raise RuntimeError("Global editorial review returned invalid identifiers")
    if len(ids)>max_papers:
        raise RuntimeError(f"Global review ignored maximum {max_papers} articles")
    features=decision.get("featured_ids",[])
    if not isinstance(features,list) or any(str(x) not in ids for x in features):
        raise RuntimeError("Global review returned invalid featured identifiers")
    return ids, [str(x) for x in features][:4]


def screen(papers, use_ai=True, max_papers=30):
    """Two-pass scientific selection with a global day-level reading budget.

    A model outage is an error, not permission to publish a 100+ paper index.
    """
    key=os.environ.get("OPENAI_API_KEY") if use_ai else None
    if use_ai and not key:
        raise RuntimeError("OpenAI API key missing: refusing to publish unreviewed issue")
    judged={}
    if key:
        for k in range(0,len(papers),10):
            subset=papers[k:k+10]
            # Retry only transient model failures; never quietly use local
            # scores as if they were the model's editorial judgment.
            last_error=None
            for attempt in range(3):
                try:
                    judged.update(_ai_batch(subset,key))
                    last_error=None
                    break
                except Exception as exc:
                    last_error=exc
                    if attempt<2:
                        import time
                        time.sleep(2**attempt*4)
            if last_error is not None:
                raise RuntimeError(f"AI assessment failed for batch {k//10+1}: {last_error}")
        if len(judged)!=len(papers):
            raise RuntimeError(f"Only {len(judged)}/{len(papers)} papers assessed: aborting")
    initial=[]
    for p in papers:
        ai=judged.get(str(p.get("id")))
        if ai is not None:
            try:score=max(0,min(100,int(ai["score"])))
            except (TypeError,ValueError,KeyError):
                raise ValueError("Missing AI score for "+str(p.get("id")))
            ok=(ai.get("in_scope") is True and score>=55)
            p["physics_advance"]=str(ai.get("physics_advance") or "")[:260]
            p["ai_in_scope"]=ai.get("in_scope") is True
            p["relevance_reason"]=str(ai.get("reason") or "")[:240]
            p["relevance_method"]="semantic"
        else:
            score=fallback_score(p)
            ok=score>=3.0
            p["relevance_method"]="local"
            p["relevance_reason"]="Conservative local physics relevance screening"
        p["relevance_score"]=score
        p["feature_candidate"]=False
        if ok:initial.append(p)
    if key and initial:
        ranked,features=_ai_shortlist(initial,key,max_papers=max_papers)
        byid={p["id"]:p for p in initial}
        for p in initial:p["feature_candidate"]=p["id"] in features
        kept=[byid[pid] for pid in ranked]
    else:
        kept=sorted(initial,key=lambda p:p["relevance_score"],reverse=True)[:max_papers]
        for p in kept[:min(3,len(kept))]:p["feature_candidate"]=True
    if len(kept)>max_papers:
        raise RuntimeError("Issue exceeds editorial size limit")
    return kept, {"scanned":len(papers),"first_pass_selected":len(initial),
                  "selected":len(kept),"rejected":len(papers)-len(kept),
                  "ai_assessed":len(judged),"global_editorial":bool(key)}
