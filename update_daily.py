#!/usr/bin/env python3
"""Daily condensed matter literature index, arXiv + Crossref."""
import datetime as dt, json, os, re, time, urllib.parse, urllib.request
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from html import unescape
from pathlib import Path
from zoneinfo import ZoneInfo
from relevance import screen, has_substantive_cm_evidence, CLEAR_NON_CM_TITLE

ROOT=Path(__file__).resolve().parent
NS={"a":"http://www.w3.org/2005/Atom","x":"http://arxiv.org/schemas/atom"}
ISSN={"Science":"0036-8075","Science Advances":"2375-2548","Nature":"0028-0836",
"Nature Physics":"1745-2473","Nature Materials":"1476-1122",
"Nature Communications":"2041-1723","PRL":"0031-9007","PRX":"2160-3308",
"PNAS":"0027-8424",
"Communications Materials":"2662-4443",
"Communications Physics":"2399-3650",
"npj Quantum Materials":"2397-4648"}
TOPICS=[("Superconductivity",r"superconduct|josephson|pairing|vortex"),
("Thermal & Thermoelectric",r"thermal|thermoelectric|seebeck|nernst|heat capacity|elastocaloric"),
("Magnetism",r"magnet|spin|magnon|skyrmion|kagome|altermagnet"),
("Materials & Growth",r"growth|synthes|crystal|structural|phase coexist|substitu"),
("Topology & Transport",r"topolog|hall|transport|semimetal|weyl|dirac"),
("Correlated Electrons",r"correlat|kondo|fermion|mott|valence|density wave")]
def fetch(url):
 req=urllib.request.Request(url,headers={"User-Agent":"CondMatLiteratureMonitor/1.0"})
 with urllib.request.urlopen(req,timeout=55) as r:return r.read().decode("utf8","replace")
def clean(s):return re.sub(r"\s+"," ",re.sub(r"<[^>]+>"," ",str(s or ""))).strip()
def topic(s):
 for name,pattern in TOPICS:
  if re.search(pattern,s,re.I):return name
 return "Other Condensed Matter"
def summary(s):return clean(s)[:400]
def arxiv_ids():
 from html.parser import HTMLParser
 class Collector(HTMLParser):
  def __init__(self):super().__init__();self.ids=[]
  def handle_starttag(self,tag,attrs):
   if tag!="a":return
   href=dict(attrs).get("href","")
   m=re.search(r"/abs/(\d{4}\.\d{4,5})(?:v\d+)?(?:\?.*)?$",href)
   if m and m[1] not in self.ids:self.ids.append(m[1])
 c=Collector();c.feed(fetch("https://arxiv.org/list/cond-mat/new"));return c.ids
def arxiv():
 ids=arxiv_ids();out=[]
 for start in range(0,len(ids),75):
  query=urllib.parse.urlencode({"id_list":",".join(ids[start:start+75]),"max_results":75})
  root=ET.fromstring(fetch("https://export.arxiv.org/api/query?"+query))
  for e in root.findall("a:entry",NS):
   raw=e.findtext("a:id","",NS).split("/abs/")[-1]
   pid=re.sub(r"v\d+$","",raw)
   if pid not in ids:continue
   categories={c.get("term","") for c in e.findall("a:category",NS)}
   if not any(c.startswith("cond-mat.") for c in categories):continue
   primary=e.find("x:primary_category",NS)
   if primary is not None and primary.get("term")=="cond-mat.quant-gas":continue
   title=clean(e.findtext("a:title","",NS));abstract=clean(e.findtext("a:summary","",NS))
   authors=[clean(a.findtext("a:name","",NS)) for a in e.findall("a:author",NS)]
   journal=clean(e.findtext("x:journal_ref","",NS))
   out.append({"id":"arxiv-"+pid.replace(".","-"),"arxiv_id":pid,"type":"arXiv",
   "journal":"arXiv:"+pid,"journal_ref":journal,"title":title,
   "authors":", ".join(authors[:3])+(" et al." if len(authors)>3 else ""),
   "corresponding":"","url":"https://arxiv.org/abs/"+pid,
   "topic":topic(title+" "+abstract),"level":"Brief",
   "summary_en":summary(abstract),"summary":summary(abstract),"abstract":abstract,
   "method":"","result":"","future":""})
  if start+75<len(ids):time.sleep(3)
 return out
# A broad collection gate, NOT an inclusion decision. All papers entering
# the digest still need an explicit AI in_scope and relevance score.
def journal_candidate_scope(name, title, abstract=""):
 if CLEAR_NON_CM_TITLE.search(title):
  return False
 # PRL and PRX publish across physics. Let the AI inspect every original
 # research paper: title keywords alone miss real condensed-matter theory.
 if name in ("PRL", "PRX"):
  return True
 return has_substantive_cm_evidence({"title":title,"abstract":abstract})

def crossref_records(issn, first, last, page_size=200):
 """Return all Crossref pages, not merely the first 100 records.

 Use cursor pagination for journals that publish >100 papers in a week.
 If a later page fails, propagate the failure rather than silently calling
 a truncated partial harvest complete.
 """
 cursor="*"
 seen_cursors=set()
 while cursor and cursor not in seen_cursors:
  seen_cursors.add(cursor)
  query=urllib.parse.urlencode({
    "filter":f"from-online-pub-date:{first},until-online-pub-date:{last}",
    "rows":page_size,"cursor":cursor,
    "select":"DOI,title,author,abstract,type"})
  url="https://api.crossref.org/journals/"+issn+"/works?"+query
  for attempt in range(3):
   try:
    response=json.loads(fetch(url))["message"]
    break
   except Exception:
    if attempt==2:raise
    time.sleep(2**attempt*2)
  items=response.get("items",[])
  yield from items
  if len(items)<page_size:
   return
  cursor=response.get("next-cursor")
 if cursor in seen_cursors:
  raise RuntimeError("Crossref pagination repeated cursor")

class _PublisherAbstractParser(HTMLParser):
 """Extract an article abstract from scholarly HTML without extra packages."""
 def __init__(self):
  super().__init__()
  self.metadata={}
  self.depth=0
  self.parts=[]
 def handle_starttag(self,tag,attrs):
  attrs=dict(attrs)
  if tag=="meta":
   name=(attrs.get("name") or attrs.get("property") or "").lower()
   if name in ("citation_abstract","dc.description","description",
               "og:description") and attrs.get("content"):
    self.metadata[name]=unescape(attrs["content"])
  if self.depth:
   self.depth+=1
  elif tag in ("div","section","article","span") and (
    "abstract" in (attrs.get("class") or "").lower().split()
    or (attrs.get("id") or "").lower() in ("abstract","article-abstract")):
   self.depth=1
 def handle_startendtag(self,tag,attrs):
  if tag=="meta":
   self.handle_starttag(tag,attrs)
 def handle_endtag(self,tag):
  if self.depth:self.depth-=1
 def handle_data(self,value):
  if self.depth:self.parts.append(value)
 def extract(self):
  for key in ("citation_abstract","dc.description","description","og:description"):
   candidate=clean(self.metadata.get(key,""))
   # Short generic SEO descriptions are not paper abstracts.
   if len(candidate)>=140 and not candidate.lower().startswith("physical review"):
    return candidate
  candidate=clean(" ".join(self.parts))
  return candidate if len(candidate)>=140 else ""

def publisher_abstract(journal,doi):
 """Enrich APS papers whose Crossref records omit the scientific abstract."""
 slug={"PRL":"prl","PRX":"prx"}.get(journal)
 if not slug or not doi.startswith("10.1103/"):
  return ""
 url="https://journals.aps.org/"+slug+"/abstract/"+doi
 try:
  # A normal browser user-agent is more compatible with journal HTML.
  req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0"})
  with urllib.request.urlopen(req,timeout=18) as response:
   html=response.read(750000).decode("utf8","replace")
  parser=_PublisherAbstractParser()
  parser.feed(html)
  return parser.extract()[:3300]
 except Exception as exc:
  print(f"NOTICE: APS abstract not available for {doi}: {type(exc).__name__}")
  return ""

def _openalex_abstract(inverted):
 """Reconstruct an abstract supplied as OpenAlex word->position arrays."""
 if not isinstance(inverted,dict):
  return ""
 tokens={}
 for word,places in inverted.items():
  if not isinstance(places,list):continue
  for i in places:
   if isinstance(i,int) and 0<=i<5000:
    tokens[i]=word
 if len(tokens)<25:
  return ""
 words=[tokens.get(i,"") for i in range(max(tokens)+1)]
 return clean(" ".join(words))[:3300]

def metadata_abstract(doi):
 """Use other free scholarly metadata sources when Crossref has no abstract.

 Never synthesize one: if none is available, leave the field empty and
 record that AI only evaluated the title.
 """
 enc=urllib.parse.quote(doi,safe="")
 sources=[
   ("OpenAlex","https://api.openalex.org/works/https://doi.org/"+doi),
   ("SemanticScholar","https://api.semanticscholar.org/graph/v1/paper/DOI:"+enc+"?fields=title,abstract")
 ]
 for name,url in sources:
  try:
   req=urllib.request.Request(url,headers={"User-Agent":"CondMatLiteratureMonitor/1.0"})
   with urllib.request.urlopen(req,timeout=12) as response:
    obj=json.loads(response.read())
   if name=="OpenAlex":
    abstract=_openalex_abstract(obj.get("abstract_inverted_index"))
   else:
    abstract=clean(obj.get("abstract",""))
   if len(abstract)>=140:
    return abstract[:3300]
  except Exception as exc:
   print(f"NOTICE: {name} abstract unavailable {doi}: {type(exc).__name__}")
 return ""

def journals(today, audit=None):
 out=[]
 # The previous midnight-only window missed Friday and delayed indexing.
 # A rolling week rescans recent journal publications; prior published DOIs
 # are excluded in main(), but arXiv->journal duplicates remain eligible.
 first=(today-dt.timedelta(days=7)).date().isoformat()
 last=today.date().isoformat()
 for name,issn in ISSN.items():
  total=0
  candidates=0
  excluded=0
  try:
   for x in crossref_records(issn,first,last):
    if x.get("type")!="journal-article":continue
    title=clean((x.get("title") or [""])[0])
    ab=clean(x.get("abstract",""))
    doi=x.get("DOI","").lower().strip()
    if not title or not doi:continue
    total+=1
    scope_ok=journal_candidate_scope(name,title,ab)
    # Missing Crossref abstracts are common for APS and some publishers.
    # Prefer DOI-keyed academic records, then publisher HTML as a fallback.
    # All failed lookups stay explicitly title-only; do not invent abstracts.
    if scope_ok and not ab:
     ab=metadata_abstract(doi)
     if not ab and name in ("PRL","PRX"):
      ab=publisher_abstract(name,doi)
    if audit is not None:
     audit.append({"doi":doi,"title":title,"journal":name,
                   "prefilter":"candidate" if scope_ok else "excluded",
                   "has_abstract":bool(ab)})
    if not scope_ok:
     excluded+=1
     continue
    candidates+=1
    authors=[clean((a.get("given","")+" "+a.get("family",""))) for a in x.get("author",[])]
    out.append({"id":"doi-"+re.sub("[^a-z0-9-]","-",doi),"doi":doi,"type":"Journal",
      "journal":name,"title":title,
      "authors":", ".join(authors[:3])+(" et al." if len(authors)>3 else ""),
      "corresponding":"","url":"https://doi.org/"+doi,
      "topic":topic(title+" "+ab),"level":"Brief",
      "summary_en":summary(ab or title),"summary":summary(ab or title),
      "abstract":ab,"method":"","result":"","future":""})
  except Exception as ex:
   print(f"WARNING: Crossref {name} retrieval failed; journal results incomplete: {ex}")
  print(f"Journal harvesting {name}: fetched={total}, preselected={candidates}, "
        f"excluded_by_scope={excluded}, window={first}..{last}")
 return out
def enrich(records):
 key=os.getenv("OPENAI_API_KEY")
 if not key:return
 for k in range(0,len(records),5):
  batch=records[k:k+5]
  docs=[{"id":p["id"],"title":p["title"],"abstract":p["abstract"][:2400],"featured":p.get("level")=="Feature","type":p["type"],
         "journal":p["journal"],"published":bool(p.get("journal_ref"))} for p in batch]
  instructions=("Create faithful bilingual scholarly literature notes using only titles and abstracts. "
   "Return JSON object {papers:[{id,summary_en,summary_zh,method_en,method_zh,result_en,"
   "result_zh,future_en,future_zh,tier,tier_reason_en,tier_reason_zh}]}. "
   "Write 1-2 precise sentences per summary. For featured papers write 3-5 substantive "
   "sentences in the findings, 2-3 in methods and 2-3 in experimental follow-up; "
   "for other papers use one accurate sentence per field. Preserve quantitative "
   "claims from abstracts. Do not invent figure numbers, data, or mechanisms. "
   "For UNPUBLISHED arXiv only, assess possible journal tier: Nature/Science, "
   "Nature Physics/Nature Materials, Nature Communications/Science Advances/PRX, "
   "PRL, PRB/Physical Review Materials, or Below PRB, with a reason. "
   "For every unpublished arXiv paper, choose ONE concrete tier even when "
   "the evidence is incomplete: make your best scientific judgment, do NOT "
   "abstain, hedge with Uncertain, or leave tier blank. Be willing to assign "
   "high tiers when the work is genuinely strong, without inflating weak work. "
   "This is a subjective quality assessment, NOT a literal venue prediction. "
   "Already published papers must have empty tier.")
  schema={"type":"object","properties":{"papers":{"type":"array","items":{
   "type":"object","properties":{name:{"type":"string"} for name in
   ("id","summary_en","summary_zh","method_en","method_zh",
    "result_en","result_zh","future_en","future_zh","tier",
    "tier_reason_en","tier_reason_zh")},
   "required":["id","summary_en","summary_zh","method_en","method_zh",
    "result_en","result_zh","future_en","future_zh","tier",
    "tier_reason_en","tier_reason_zh"],"additionalProperties":False}}},
   "required":["papers"],"additionalProperties":False}
  payload={"model":"gpt-6-luna","reasoning":{"effort":"medium"},
     "input":[{"role":"system","content":instructions},
     {"role":"user","content":json.dumps(docs,ensure_ascii=False)}],
     "text":{"format":{"type":"json_schema","name":"paper_notes","strict":True,
     "schema":schema}},"max_output_tokens":10000}
  req=urllib.request.Request("https://api.openai.com/v1/responses",
    data=json.dumps(payload).encode(),method="POST",
    headers={"Authorization":"Bearer "+key,"Content-Type":"application/json"})
  try:
   response=json.loads(urllib.request.urlopen(req,timeout=120).read())
   raw="".join(c.get("text","") for o in response.get("output",[]) for c in o.get("content",[]) if c.get("type")=="output_text")
   if response.get("status") != "completed":
    raise RuntimeError(f"Enrichment response {response.get('status')}: {response.get('incomplete_details')}")
   print("AI enrichment usage:",response.get("usage",{}))
   byid={p["id"]:p for p in batch}
   for obj in json.loads(raw).get("papers",[]):
    p=byid.get(obj.get("id"))
    if not p:continue
    for field in ("summary_en","summary_zh","method_en","method_zh","result_en","result_zh","future_en","future_zh"):
     if obj.get(field):p[field]=obj[field]
    if p["type"]=="arXiv" and not p.get("journal_ref") and obj.get("tier"):
     p["tier"]=obj["tier"]
     for field in ("tier_reason_en","tier_reason_zh"):p[field]=obj.get(field,"")
  except Exception as ex:print("AI enrichment:",str(ex))
def main():
 today=dt.datetime.now(ZoneInfo("America/Los_Angeles"));date=today.date().isoformat()
 dest=ROOT/"issues"/(date+".json")
 if dest.exists():print("Issue exists",date);return
 previous=list((ROOT/"issues").glob("*.json"));old=set()
 for p in previous:
  try:
   for x in json.loads(p.read_text()).get("papers",[]):old.add(x["id"])
  except Exception:pass
 papers=[];failures=0
 journal_audit=[]
 for fn in (arxiv,lambda:journals(today,journal_audit)):
  try:papers+=fn()
  except Exception as e:print("Source failure:",str(e));failures+=1
 print(f"Initial subject-filtered sources: {sum(p['type']=='arXiv' for p in papers)} arXiv, "
       f"{sum(p['type']=='Journal' for p in papers)} journal papers")
 seen=set();kept=[]
 for p in sorted(papers,key=lambda p:p["type"]!="Journal"):
  key=re.sub("[^a-z0-9]","",p["title"].lower())
  if p["id"] in old or key in seen:continue
  seen.add(key);kept.append(p)
 if not kept:
  print("No new papers from this run")
  return
 screened_candidates=kept[:]
 kept,stats=screen(kept)
 # Record all discovered journal candidates, including scope exclusions and
 # AI rejections, so a later manual-vs-automatic comparison has an audit trail.
 input_by_id={p["id"]:p for p in screened_candidates}
 selected_ids={p["id"] for p in kept}
 old_ids=set(old)
 for a in journal_audit:
  pid="doi-"+re.sub("[^a-z0-9-]","-",a["doi"])
  p=input_by_id.get(pid)
  if pid in selected_ids:a["decision"]="selected"
  elif pid in old_ids:a["decision"]="previous_issue"
  elif a["prefilter"]=="excluded":a["decision"]="prefilter_excluded"
  elif p is not None:
   a["decision"]="AI_or_global_rejected"
   a["score"]=p.get("relevance_score")
   a["in_scope"]=p.get("ai_in_scope")
   a["reason"]=p.get("relevance_reason","")
  else:a["decision"]="duplicate_or_unprocessed"
 (ROOT/"audits").mkdir(exist_ok=True)
 (ROOT/"audits"/(date+".json")).write_text(
    json.dumps({"date":date,"journal_candidates":journal_audit},
               ensure_ascii=False,indent=1),encoding="utf8")
 if not kept:
  print("Screening found no sufficiently relevant new papers:",stats)
  return
 # Select Featured Reading by global editorial judgment, not local
 # uncalibrated relevance scores or impact factor.
 featured=[p for p in kept if p.get("feature_candidate")]
 if not featured:
  featured=kept[:min(3,len(kept))]
 feature_ids={p["id"] for p in featured[:4]}
 for p in kept:
  p["level"]="Feature" if p["id"] in feature_ids else "Brief"
 enrich(kept)
 kept.sort(key=lambda p:(p["type"]!="Journal",p["topic"],p["title"]))
 dest.parent.mkdir(exist_ok=True)
 dest.write_text(json.dumps({"date":date,"title":"Daily Condensed Matter Literature",
    "papers":kept,"stats":stats},ensure_ascii=False,indent=2),encoding="utf8")
 print("Saved",date,len(kept),"papers after physics-relevance screening:",stats)
if __name__=="__main__":main()
