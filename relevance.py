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
import time


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
      "You are screening a STRICT CONDENSED-MATTER PHYSICS literature digest "
      "covering ORIGINAL THEORETICAL AND EXPERIMENTAL research equally. "
      "Research primarily belonging to any OTHER discipline or branch of "
      "physics is OUT OF SCOPE, regardless of journal prestige, novelty, "
      "shared vocabulary, or score. Be an exacting research editor: "
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
      "Original condensed-matter theoretical classification of electronic "
      "or Bogoliubov-de Gennes phases, topology, symmetry indicators and "
      "topological invariants is genuine CM theory, NOT generic computing "
      "methodology; evaluate its scientific advance normally. "
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
      "Exclude AMO, ultracold atoms/gases and quantum simulators, quantum "
      "optics and photonics platforms, quantum computing/information, "
      "particle/high-energy/nuclear physics, astrophysics/cosmology/gravity, "
      "plasma physics, non-condensed-matter fluid dynamics, biology, "
      "chemistry and general engineering. A similar Hamiltonian or borrowed "
      "term (spin, topology, Hubbard, quantum, materials) does NOT make "
      "research in another field condensed-matter physics. Genuine "
      "condensed-matter theory of electrons, spins, lattices, defects, "
      "collective states, materials and phase transitions DOES qualify even "
      "without an experiment. Optical measurements of material physics "
      "qualify, but optics device engineering does not. Reviews, roadmaps "
      "and generic method benchmarks do not report original CM physics. "
      "For EVERY paper independently return in_scope true ONLY when the "
      "PRIMARY research question and contribution are themselves condensed-"
      "matter physics (theory OR experiment). Reject every superficially "
      "adjacent or non-CM paper even when the result sounds exciting. "
      "Provide a calibrated score: 85-100 landmark/broadly exciting new "
      "condensed-matter physics; 70-84 strong original CM result; 55-69 "
      "credible narrower CM physical advance; 40-54 tangential science; "
      "0-39 chiefly engineering/application/quantum information/general methods. "
      "Apply a STRICT and consistent scientific relevance standard: do not "
      "relax inclusion for merely adjacent subjects or weak novelty. "
      "Assign every paper a decisive 0-100 score, spanning the full scale "
      "when justified. Avoid reflexive middle scores, hedging, or artificially "
      "low scores for genuinely important discoveries. Score scientific merit "
      "and experimental interest, NOT how confidently the abstract is written. "
      "If the long-term impact or ideal journal is unknown, give a firm best-"
      "estimate score anyway; NEVER replace a score with uncertain or omit it. "
      "Do not interpret scientific uncertainty as automatic low quality. "
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
    payload={"model":"gpt-6-luna",
             "input":[{"role":"system","content":rubric},
                      {"role":"user","content":json.dumps(docs,ensure_ascii=False)}],
             "text":{"format":{"type":"json_schema","name":"paper_assessments","strict":True,
               "schema":{"type":"object","properties":{"assessments":{
                 "type":"array","items":{"type":"object","properties":{
                   "id":{"type":"string"},"in_scope":{"type":"boolean"},
                   "score":{"type":"integer"},"feature_candidate":{"type":"boolean"},
                   "reason":{"type":"string"},"physics_advance":{"type":"string"}},
                 "required":["id","in_scope","score","feature_candidate","reason","physics_advance"],
                 "additionalProperties":False}}},
                 "required":["assessments"],"additionalProperties":False}}},"max_output_tokens":8000}
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
    if response.get("status") != "completed":
        raise RuntimeError(f"AI response {response.get('status')}: {response.get('incomplete_details')}")
    print("AI assessment usage:",response.get("usage",{}))
    result=json.loads(raw)
    assessments = result.get("assessments", [])
    if not isinstance(assessments,list):
        raise ValueError("Missing AI assessments")
    found={}
    for x in assessments:
        if not isinstance(x,dict) or "id" not in x or not isinstance(x.get("in_scope"),bool):
            raise ValueError("AI must provide a binary in_scope decision for every paper")
        score=x.get("score")
        if isinstance(score,bool) or not isinstance(score,int) or not (0 <= score <= 100):
            continue  # Invalid scores are treated as missing and retried.
        found[str(x["id"])]=x
    expected={str(p["id"]) for p in papers}
    missing=expected-set(found)
    if missing:
        print(f"AI assessment partial: {len(found)}/{len(expected)} valid; missing={sorted(missing)}")
    return {pid:found[pid] for pid in expected if pid in found}


# Independent, high-recall scope check: require evidence that the PAPER
# actually concerns an emergent physical property of condensed matter.
# This is not a topic blacklist or the main ranking mechanism; it is a
# sanity check to stop generic uses of "quantum"/"phase"/"transport"
# from admitting biology, fluid mechanics, optics engineering, etc.
CM_PHYSICS_TITLE = re.compile(
    r"superconduct|josephson|vort(ex|ices)|andreev|"
    r"(anti)?ferromagnet|ferrimagnet|altermagnet|magnetic order|"
    r"magnon|spin[- ]?(wave|liquid|order|splitt|polariz|excitat|resonan)|"
    r"kondo|mott|hubbard|strange metal|fermi|"
    r"quantum critical|chern|quantum (spin )?hall|topological (insulat|semimetal|phase|pump)|"
    r"flat[-. ]band|lieb lattice|electronic (band|structure)|orbital magnet|"
    r"magnetocaloric|magnetostructural|ferroelastic|coupled order paramet|"
    r"quantum (geometry|paramagnet)|kitaev|frustrat(ed|ion)|"
    r"charge[- ]density[- ]wave|moire|moiré|graphene|"
    r"ferroelectric|multiferroic|orbital order|"
    r"(anomalous|thermal|spin|quantum) hall|nernst|seebeck|"
    r"magnetoresist|magneto.?electric|elastocaloric|"
    r"electronic (transport|correlat|phase|state|structure)|"
    r"electron[- ]phonon|phonon|lattice dynamics|"
    r"quantum oscillat|valence (transit|fluctuat|instab)|"
    r"neutron scatter|quantum capacitance|"
    r"metal[- ]insulator transition|superfluid (phase|density)",
    re.I)
CM_ABSTRACT_EVIDENCE = re.compile(
    r"superconduct|magnetic order|magnon|spin excitation|"
    r"quantum hall|chern insulator|topological electronic|"
    r"strongly correlated electron|kondo|mott|hubbard|"
    r"charge density wave|orbital order|ferroelectric|"
    r"ferrimagnet|antiferromagnet|spin transport|"
    r"anomalous hall|thermal hall|nernst|seebeck|"
    r"neutron scatter|specific heat|heat capacity|"
    r"electronic band structure|first.principles electronic|"
    r"electron.phonon|spin.orbit|electron correlation|"
    r"flat[-. ]band|magnetostructural|magnetocaloric|"
    r"orbital magnet|spin splitting|order parameter|"
    r"valence bond|magnetic (phase|transition)|"
    r"lattice dynamics|magnetoresistance|"
    r"superconducting phase|quantum material",
    re.I)
CM_MATERIAL_SYSTEM = re.compile(
    r"crystal|semiconductor|solid.state|solid|bulk|lattice|"
    r"layered|monolayer|heterostructure|van der waals|"
    r"condensed.matter|electronic band|ferromagnet|"
    r"oxide|pnictide|chalcogenide|metal|ferroelectric|"
    r"spin.system|strongly.correlated|quantum material",
    re.I)

# Reject clearly non-CM primary research even if the title contains terms
# such as Hubbard, superconducting, magnetism, or topology. Unclear cases
# still receive a semantic judgment rather than relying on a keyword blacklist.
CLEAR_NON_CM_TITLE = re.compile(
    r"ultracold (atom|gas)|cold.atom|atomic gas|trapped.ion|"
    r"quantum error correction|quantum comput(ing|er)|"
    r"quantum algorithm|quantum cryptograph|quantum optics|"
    r"photonic (quantum|topological|circuit|crystal)|"
    r"lithograph|flat optics|optical lens|"
    r"astrophys|cosmolog|gravitational wave|"
    r"nuclear (reaction|decay|collis)|particle collider|"
    r"plasma (turbulence|physics|jet)|"
    r"protein|genom|neuroscien",
    re.I,
)

def has_substantive_cm_evidence(p):
    title=str(p.get("title") or "")
    abstract=str(p.get("abstract") or p.get("summary_en") or "")
    if CLEAR_NON_CM_TITLE.search(title):
        return False
    if CM_PHYSICS_TITLE.search(title):
        return True
    return bool(CM_ABSTRACT_EVIDENCE.search(abstract)
                and CM_MATERIAL_SYSTEM.search(title+" "+abstract))


def _ai_shortlist(papers, key, max_papers=30):
    """Comparative editorial choice across the *entire day's* candidates.

    Scores generated by independent small batches are not calibrated. An issue
    has to be composed as an issue, with one coherent relevance threshold.
    """
    instructions = (
      "You are the science editor preparing ONE compact daily literature index "
      "for a researcher of CONDENSED-MATTER PHYSICS, theory and experiment. "
      "Below is the pool passing a first condensed-matter assessment. "
      "Make one global and RELATIVE comparison, using the science of a paper "
      "rather than prestige or keyword overlap. "
      "Your readership studies emergent physical properties of SOLIDS, "
      "magnetism, superconductivity, electron correlations, quantum materials, "
      "topological electronic states, magnetic/transport/thermodynamic "
      "measurements, crystal growth with novel physical properties, symmetry "
      "and phase transitions, and original condensed-matter theory. "
      "Keep a broad range of new physical discoveries and original "
      "condensed-matter theory, including phase/topology classification "
      "and experimentally testable predictions; not only fashionable materials. "
      "Prefer specific new measurements or a well-defined unexpected physical "
      "effect to abstract algorithmic advances, generic computation, materials "
      "optimization, performance-only devices, optics-system design, applied "
      "quantum sensing without material physics, biology, biophysics, "
      "plasma astrophysics, classical fluids, purely stochastic mathematical "
      "physics, or chemical synthesis without electronic/magnetic properties. "
      "HARD DOMAIN BOUNDARY: select ONLY condensed-matter physics research. "
      "Reject all other physics, including AMO/ultracold gases, atom-based "
      "quantum simulations, photonic analogues, quantum computing, nuclear, "
      "particle, astrophysics and plasma research, even if they borrow "
      "condensed-matter concepts. Original condensed-matter theory and "
      "experimental papers are equally eligible. "
      "Reviews, quantum algorithm benchmarks and generic methodological "
      "improvements generally do not merit space here without new material "
      "physics. "
      "Keep selection criteria STRICT: scoring must be decisive, but high "
      "scores are not permission to include tangential papers. Do not pad "
      "the reading list to 30. "
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
    payload = {"model":"gpt-6-luna",
      "input":[{"role":"system","content":instructions},
               {"role":"user","content":json.dumps(docs,ensure_ascii=False)}],
      "text":{"format":{"type":"json_schema","name":"global_shortlist","strict":True,
             "schema":{"type":"object","properties":{
               "selected_ids":{"type":"array","items":{"type":"string"}},
               "featured_ids":{"type":"array","items":{"type":"string"}}},
               "required":["selected_ids","featured_ids"],
               "additionalProperties":False}}},"max_output_tokens":12000}
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
    if response.get("status") != "completed":
        raise RuntimeError(f"Global review response {response.get('status')}: {response.get('incomplete_details')}")
    print("AI global review usage:",response.get("usage",{}))
    decision=json.loads(raw)
    allowed={str(p["id"]) for p in papers}
    proposed=decision.get("selected_ids")
    if not isinstance(proposed,list):
        proposed=[]
    ids=[]
    seen=set()
    for value in proposed:
        pid=str(value)
        if pid in allowed and pid not in seen:
            ids.append(pid)
            seen.add(pid)
    if len(ids)!=len(proposed):
        print(f"WARNING: global review supplied {len(proposed)-len(ids)} invalid or repeated IDs; ignoring them")
    if not ids:
        # An imperfect LLM response must not crash the entire daily digest,
        # or invent a score. All fallback choices passed the AI CM-scope gate.
        print("WARNING: no valid global IDs; using highest-rated CM assessments")
        best=sorted(papers,key=lambda p:p.get("relevance_score",0),reverse=True)
        ids=[str(p["id"]) for p in best[:min(max_papers,20)]]
    if len(ids)>max_papers:
        print(f"Global editorial shortlist has {len(ids)} papers; retaining the top {max_papers}")
        ids=ids[:max_papers]
    proposed_features=decision.get("featured_ids",[])
    if not isinstance(proposed_features,list):
        proposed_features=[]
    features=[]
    for value in proposed_features:
        pid=str(value)
        if pid in ids and pid not in features:
            features.append(pid)
    if not features:
        features=ids[:min(3,len(ids))]
    return ids,features[:4]


def screen(papers, use_ai=True, max_papers=30):
    """Two-pass scientific selection with a global day-level reading budget.

    A model outage is an error, not permission to publish a 100+ paper index.
    """
    key=os.environ.get("OPENAI_API_KEY") if use_ai else None
    if use_ai and not key:
        raise RuntimeError("OpenAI API key missing: refusing to publish unreviewed issue")
    judged={}
    unscored=[]
    if key:
        for k in range(0,len(papers),5):
            subset=papers[k:k+5]
            pending=subset[:]
            # Retry only missing papers: never discard successful assessments.
            for attempt in range(3):
                if not pending:
                    break
                try:
                    completed=_ai_batch(pending,key)
                    judged.update(completed)
                    pending=[p for p in pending if str(p["id"]) not in completed]
                except Exception as exc:
                    print(f"AI batch {k//5+1} attempt {attempt+1}: {exc}")
                if pending and attempt<2:
                    time.sleep(2**attempt*4)
            # A failed batch is split into single-paper requests.
            for p in pending:
                pid=str(p["id"])
                for attempt in range(3):
                    try:
                        one=_ai_batch([p],key)
                        if pid in one:
                            judged[pid]=one[pid]
                            break
                    except Exception as exc:
                        print(f"AI single-paper retry for {pid}: {exc}")
                    if attempt<2:
                        time.sleep(2**attempt*4)
                if pid not in judged:
                    unscored.append(pid)
                    print(f"WARNING: paper {pid} could not be scored; excluding rather than fabricating a score")
        print(f"AI scored {len(judged)}/{len(papers)} candidates; unscored={unscored}")
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
        elif key:
            # API failure must not turn into a fabricated AI score or a failure for all papers.
            p["relevance_score"]=None
            p["relevance_method"]="unscored_api_failure"
            p["relevance_reason"]="AI score unavailable after targeted retries"
            continue
        else:
            score=fallback_score(p)
            ok=score>=3.0
            p["relevance_method"]="local"
            p["relevance_reason"]="Conservative local physics relevance screening"
        p["relevance_score"]=score
        p["feature_candidate"]=False
        if ok:initial.append(p)
    # Separate from the LLM's in_scope label. Generic scientific papers
    # should not enter the global shortlist solely on an inflated score.
    # The AI has already read the entire abstract and assigned a strict
    # in_scope=True decision. Do not reject it again by an incomplete keyword
    # vocabulary. Retain only the unmistakable non-CM subject safeguard.
    field_screened=[p for p in initial if not CLEAR_NON_CM_TITLE.search(
        str(p.get("title") or ""))]
    dropped_for_scope=len(initial)-len(field_screened)
    initial=field_screened
    if key and initial:
        ranked,features=_ai_shortlist(initial,key,max_papers=max_papers)
        byid={p["id"]:p for p in initial}
        for p in initial:p["feature_candidate"]=p["id"] in features
        kept=[byid[pid] for pid in ranked]
    else:
        kept=sorted(initial,key=lambda p:p["relevance_score"],reverse=True)[:max_papers]
        for p in kept[:min(3,len(kept))]:p["feature_candidate"]=True
    if len(kept)>max_papers:
        kept=sorted(kept,key=lambda p:p["relevance_score"],reverse=True)[:max_papers]
    return kept, {"scanned":len(papers),"first_pass_selected":len(initial),
                  "selected":len(kept),"rejected":len(papers)-len(kept),
                  "ai_assessed":len(judged),"ai_unscored":len(unscored),
                  "global_editorial":bool(key),
                  "field_scope_excluded":dropped_for_scope}
