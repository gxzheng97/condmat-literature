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
      "You are an editor of a broad experimental CONDENSED MATTER PHYSICS "
      "literature digest, not a specialist in the user's current projects. "
      "Judge the physical SCIENCE QUESTION and new understanding, not journal "
      "prestige or matching a few topics. Include original discoveries on "
      "electronic, magnetic, lattice, superconducting, topological, quantum "
      "and thermal behavior of solids, material-specific phase transitions, "
      "well-grounded experimentally actionable theory, and novel synthesis "
      "revealing physical phenomena. Include compelling low-dimensional or "
      "interdisciplinary condensed matter. Be open to unfamiliar materials "
      "and techniques, not just known fashionable subjects. "
      "Reject work whose central contribution is device performance, "
      "implementation, general application, generic engineering or a survey "
      "without substantial new condensed-matter physics. Device/optical "
      "research CAN qualify if it probes or demonstrates a new physical state "
      "or mechanism. Materials synthesis CAN qualify for novel accessible "
      "quantum matter, new electronic/magnetic state, or substantial experimental "
      "opportunity. Do NOT blacklist fields or named topics. "
      "Grade score 0-100: 80-100 exceptional strong fit, 65-79 substantive "
      "fit, 55-64 borderline but potentially useful, <55 mostly unrelated. "
      "Bias toward retaining borderline work with substantive physics; keep "
      "if score>=55. Select feature_candidate true for a few standout papers "
      "whose science is distinctive or experimentally promising; no requirement "
      "to distribute scores by journal. "
      "Return a JSON object: {assessments:[{id,score,feature_candidate,reason}]}. "
      "Keep reasons short, grounded in the supplied title/abstract, in English."
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
    response=json.loads(urllib.request.urlopen(req,timeout=110).read())
    raw="".join(part.get("text","") for msg in response.get("output",[])
                for part in msg.get("content",[]) if part.get("type")=="output_text")
    result=json.loads(raw)
    return {str(x.get("id")):x for x in result.get("assessments",[]) if "id" in x}


def screen(papers, use_ai=True):
    """Return kept records and accounting. Never silently discard uncertain results."""
    key = os.environ.get("OPENAI_API_KEY") if use_ai else None
    judged = {}
    if key:
        for k in range(0,len(papers),12):
            subset=papers[k:k+12]
            try:
                judged.update(_ai_batch(subset,key))
            except Exception as exc:
                print("Relevance model unavailable for batch; using local fallback:",str(exc))
    kept=[]
    rejected=[]
    for p in papers:
        ai=judged.get(str(p.get("id")))
        if ai is not None:
            try: score=max(0,min(100,int(ai.get("score",0))))
            except (TypeError,ValueError): score=None
        else:
            score=None
        if score is None:
            # Local scoring is deliberately calibrated for high recall.
            score=fallback_score(p)
            ok=score>=2.7
            feature=score>=7.5
            reason="Physics-focused local screening"
            method="local"
        else:
            ok=score>=55
            feature=bool(ai.get("feature_candidate")) and score>=65
            reason=str(ai.get("reason") or "")[:240]
            method="semantic"
        p["relevance_score"]=score
        p["relevance_method"]=method
        if reason: p["relevance_reason"]=reason
        p["feature_candidate"]=feature
        (kept if ok else rejected).append(p)
    return kept, {"scanned":len(papers),"selected":len(kept),
                  "rejected":len(rejected),"ai_assessed":len(judged)}
