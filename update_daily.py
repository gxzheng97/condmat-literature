#!/usr/bin/env python3
"""Daily condensed matter literature index, arXiv + Crossref."""
import argparse, datetime as dt, json, os, re, time, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from html import unescape
from pathlib import Path
from zoneinfo import ZoneInfo
from relevance import screen, ARXIV_MIN_SCORE

ROOT=Path(__file__).resolve().parent
# Bump when screening criteria change substantially, so excluded-paper caches
# are reevaluated under new rules rather than becoming permanent blind spots.
SCREENING_VERSION="quantum-materials-v1-formal-research-v4"
ASSESSMENT_VERSION="quantum-materials-v1-only-no-soft-v3"
NS={"a":"http://www.w3.org/2005/Atom","x":"http://arxiv.org/schemas/atom"}
ISSN={"Science":"0036-8075","Science Advances":"2375-2548","Nature":"0028-0836",
"Nature Physics":"1745-2473","Nature Materials":"1476-1122",
"Nature Communications":"2041-1723","PRL":"0031-9007","PRX":"2160-3308",
"PNAS":"0027-8424"}
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
class ArxivListingParser(HTMLParser):
 """Track announcement sections so replacements never become new papers."""
 def __init__(self):
  super().__init__();self.section=None;self.heading=None;self.heading_parts=[]
  self.text=[];self.entries={};self.in_entry=False
 def handle_starttag(self,tag,attrs):
  attrs=dict(attrs)
  if tag=="dt":self.in_entry=True
  if tag in ("h1","h2","h3","h4"):
   self.heading=tag;self.heading_parts=[]
  if tag=="a" and self.section and self.in_entry:
   m=re.search(r"/abs/(\d{4}\.\d{4,5})(?:v\d+)?(?:\?.*)?$",attrs.get("href",""))
   if m:self.entries.setdefault(m[1],self.section)
 def handle_data(self,text):
  self.text.append(text)
  if self.heading:self.heading_parts.append(text)
 def handle_endtag(self,tag):
  if tag=="dt":self.in_entry=False
  if tag!=self.heading:return
  heading=clean(" ".join(self.heading_parts)).lower()
  for label,section in (("new submissions","new"),("cross submissions","cross"),("cross-lists","cross"),("replacement submissions","replacement"),("replacements","replacement")):
   if heading.startswith(label):self.section=section;break
  self.heading=None
 def announcement_date(self):
  m=re.search(r"Showing new listings for\s+\w+,\s+(\d{1,2}\s+\w+\s+\d{4})"," ".join(self.text))
  if not m:raise ValueError("arXiv announcement date unavailable; refusing an undated harvest")
  return dt.datetime.strptime(m[1],"%d %B %Y").date().isoformat()

def arxiv(today=None,audit=None):
 today=today or dt.datetime.now(ZoneInfo("America/Los_Angeles"))
 listing=ArxivListingParser();listing.feed(fetch("https://arxiv.org/list/cond-mat/new?show=2000"))
 announced=listing.announcement_date()
 if announced>today.date().isoformat():raise ValueError("arXiv listing is dated after the requested issue")
 if announced<today.date().isoformat():
  if audit is not None:audit.append({"decision":"no_new_announcement","announcement_date":announced})
  return []
 if not listing.entries:raise ValueError("arXiv announcement sections could not be parsed")
 ids=[];out=[]
 for pid,section in listing.entries.items():
  if section=="replacement":
   if audit is not None:audit.append({"arxiv_id":pid,"decision":"replacement_section","announcement_date":announced})
  else:ids.append(pid)
 for start in range(0,len(ids),75):
  query=urllib.parse.urlencode({"id_list":",".join(ids[start:start+75]),"max_results":75})
  root=ET.fromstring(fetch("https://export.arxiv.org/api/query?"+query))
  found=set()
  for e in root.findall("a:entry",NS):
   raw=e.findtext("a:id","",NS).split("/abs/")[-1]
   match=re.fullmatch(r"(\d{4}\.\d{4,5})v(\d+)",raw)
   pid=re.sub(r"v\d+$","",raw)
   if pid not in ids:continue
   found.add(pid)
   version=int(match[2]) if match else None
   categories={c.get("term","") for c in e.findall("a:category",NS)}
   primary=e.find("x:primary_category",NS)
   primary_category=primary.get("term","") if primary is not None else ""
   title=clean(e.findtext("a:title","",NS));abstract=clean(e.findtext("a:summary","",NS))
   reason=("non_original_article" if is_non_original({"title":title}) else
           "not_first_version" if version!=1 else
           "soft_matter_category" if primary_category=="cond-mat.soft" else
           "quantum_gas_category" if primary_category=="cond-mat.quant-gas" else
           "not_condensed_matter" if not any(c.startswith("cond-mat.") for c in categories) else "candidate")
   if audit is not None:audit.append({"arxiv_id":pid,"title":title,"version":version,
     "primary_category":primary_category,"categories":sorted(categories),
     "announcement_date":announced,"decision":reason})
   if reason!="candidate":continue
   authors=[clean(a.findtext("a:name","",NS)) for a in e.findall("a:author",NS)]
   journal=clean(e.findtext("x:journal_ref","",NS))
   out.append({"id":"arxiv-"+pid.replace(".","-"),"arxiv_id":pid,"type":"arXiv",
    "journal":"arXiv:"+pid,"journal_ref":journal,"journal_doi":clean(e.findtext("x:doi","",NS)).lower(),"title":title,
    "arxiv_version":version,"primary_category":primary_category,"categories":sorted(categories),
    "submitted_at":e.findtext("a:published","",NS),"updated_at":e.findtext("a:updated","",NS),
    "announcement_date":announced,"announcement_section":listing.entries[pid],
    "authors":", ".join(authors),"corresponding":"","url":"https://arxiv.org/abs/"+pid+"v1",
    "topic":topic(title+" "+abstract),"level":"Brief",
    "summary_en":summary(abstract),"summary":summary(abstract),"abstract":abstract,
    "method":"","result":"","future":""})
  missing=set(ids[start:start+75])-found
  if missing:raise RuntimeError("arXiv API omitted entries: "+", ".join(sorted(missing)))
  if start+75<len(ids):time.sleep(3)
 return out

def journal_candidate_scope(name,title,abstract=""):
 """Whitelist only: scientific judgment happens AFTER abstract recovery."""
 return name in ISSN and bool(clean(title))

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
    "select":"DOI,title,author,abstract,type,published-online"})
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
   if name in ("citation_abstract","dc.description","description","citation_article_type","dc.type",
               "og:description","citation_online_date","citation_publication_date","prism.publicationdate",
               "dc.date","citation_volume","citation_issue","citation_firstpage") and attrs.get("content"):
    self.metadata[name]=unescape(attrs["content"])
  if self.depth:
   self.depth+=1
  elif tag in ("div","section","article","span") and (
    "abstract" in (attrs.get("class") or "").lower().split()
    or (attrs.get("id") or "").lower() in ("abstract","article-abstract","abs1-content")):
   self.depth=1
 def handle_startendtag(self,tag,attrs):
  if tag=="meta":
   self.handle_starttag(tag,attrs)
 def handle_endtag(self,tag):
  if self.depth:self.depth-=1
 def handle_data(self,value):
  if self.depth:self.parts.append(value)
 def extract(self):
  for key in ("citation_abstract","dc.description"):
   candidate=clean(self.metadata.get(key,""))
   # Short generic SEO descriptions are not paper abstracts.
   if len(candidate)>=140 and not candidate.lower().startswith("physical review"):
    return candidate
  candidate=clean(" ".join(self.parts))
  return candidate if len(candidate)>=140 else ""

def publisher_abstract(journal,doi,metadata=None):
 """Enrich APS papers whose Crossref records omit the scientific abstract."""
 if journal.startswith("Nature") and doi.startswith("10.1038/"):
  url="https://www.nature.com/articles/"+doi.split("/",1)[1]
 elif journal in ("Science","Science Advances"):
  url="https://www.science.org/doi/"+doi
 elif journal=="PNAS":
  url="https://www.pnas.org/doi/"+doi
 else:
  # APS HTML is blocked (403); use DOI/title-matched arXiv metadata below.
  return ""
 try:
  # A normal browser user-agent is more compatible with journal HTML.
  req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0"})
  with urllib.request.urlopen(req,timeout=18) as response:
   html=response.read(750000).decode("utf8","replace")
  parser=_PublisherAbstractParser()
  parser.feed(html)
  if metadata is not None:
   metadata["article_kind"]=parser.metadata.get("citation_article_type") or parser.metadata.get("dc.type","")
   raw_date=next((parser.metadata[k] for k in ("citation_online_date","citation_publication_date","prism.publicationdate","dc.date") if parser.metadata.get(k)), "")
   metadata["publication_date"]=publication_day(raw_date)
   accepted=bool(re.search(r">\s*(?:accepted paper|accepted manuscript|in press)\s*<",html,re.I))
   metadata["publication_status"]="accepted" if accepted else "published" if metadata["publication_date"] else "unverified"
   metadata["publication_evidence"]={"source":"publisher","url":url}
  return parser.extract()[:3300]
 except Exception as exc:
  print(f"NOTICE: Publisher abstract not available for {doi}: {type(exc).__name__}")
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
 defer the paper until a reliable abstract is available.
 """
 enc=urllib.parse.quote(doi,safe="")
 sources=[
   ("OpenAlex","https://api.openalex.org/works/https://doi.org/"+doi),
   ("SemanticScholar","https://api.semanticscholar.org/graph/v1/paper/DOI:"+enc+"?fields=title,abstract,externalIds")
 ]
 for name,url in sources:
  try:
   req=urllib.request.Request(url,headers={"User-Agent":"CondMatLiteratureMonitor/1.0"})
   with urllib.request.urlopen(req,timeout=6) as response:
    obj=json.loads(response.read())
   if name=="OpenAlex":
    if str(obj.get("doi","")).lower().removeprefix("https://doi.org/")!=doi.lower():continue
    abstract=_openalex_abstract(obj.get("abstract_inverted_index"))
   else:
    if str((obj.get("externalIds") or {}).get("DOI","")).lower()!=doi.lower():continue
    abstract=clean(obj.get("abstract",""))
   if len(abstract)>=140:
    return abstract[:3300]
  except Exception as exc:
   print(f"NOTICE: {name} abstract unavailable {doi}: {type(exc).__name__}")
 return ""

def arxiv_metadata_abstracts(papers):
 """Batch metadata lookup using documented title fields, then verify identity.

 Search results never become discoveries. A matching journal DOI is strongest;
 otherwise require the exact normalized title, never a fuzzy scientific guess.
 """
 matches={}
 fingerprint=lambda value:re.sub(r"[^a-z0-9]","",clean(value).lower())
 for offset in range(0,len(papers),8):
  batch=papers[offset:offset+8]
  clauses=[]
  for p in batch:
   words=re.findall(r"[A-Za-z]{4,}",p["title"])
   terms=list(dict.fromkeys(w.lower() for w in words if w.lower() not in ("with","from","their","under","between","using","into","through")))
   clauses.append("("+ " AND ".join("ti:"+w for w in terms[:5]) +")")
  query=" OR ".join(clauses)
  url="https://export.arxiv.org/api/query?"+urllib.parse.urlencode({"search_query":query,"max_results":100})
  try:
   root=ET.fromstring(fetch(url))
   for e in root.findall("a:entry",NS):
    related=clean(e.findtext("x:doi","",NS)).lower().removeprefix("https://doi.org/")
    title=fingerprint(e.findtext("a:title","",NS))
    abstract=clean(e.findtext("a:summary","",NS))
    if len(abstract)<140:continue
    for p in batch:
     same_doi=related==p["doi"].lower()
     if related and not same_doi:continue
     if same_doi or title==fingerprint(p["title"]):
      matches[p["doi"]]=(abstract[:3300],e.findtext("a:id","",NS))
  except Exception as exc:
   print(f"NOTICE: Matching preprint batch unavailable: {type(exc).__name__}",flush=True)
  if offset+8<len(papers):time.sleep(3)
 return matches

def arxiv_metadata_abstract(doi,title):
 return arxiv_metadata_abstracts([{"doi":doi,"title":title}]).get(doi,("",""))

ORIGINAL_ARTICLE_KINDS={
 "article","researcharticle","originalarticle","originalresearch","letter","researchletter",
 "research","report","researchreport","briefcommunication","briefreport","rapidcommunication"
}

def normalized_kind(p):
 return re.sub(r"[^a-z]","",str(p.get("article_kind","")).lower())

def is_non_original(p):
 # A positive document-type list prevents Essay/Books & Arts/new labels from
 # silently slipping through an ever-growing blacklist.
 kind=normalized_kind(p)
 if kind and kind not in ORIGINAL_ARTICLE_KINDS:return True
 return bool(re.match(r"^(?:reply\b|comment\s+on\b|author correction\s*:|publisher correction\s*:|correction\s*:|erratum\s*:|retraction\s*:)",str(p.get("title","")),re.I))

def publication_day(value):
 m=re.search(r"\b(\d{4})[-/](\d{1,2})[-/](\d{1,2})(?!\d)",str(value or ""))
 if not m:return ""
 try:return dt.date(*map(int,m.groups())).isoformat()
 except ValueError:return ""

def journal_eligibility(p,date):
 if p.get("publication_status") in ("accepted","in_press"):return "accepted_unpublished"
 if is_non_original(p):return "non_original_article"
 if p.get("publication_status")!="published" or (p.get("publication_evidence") or {}).get("source") not in ("publisher","APS RSS"):
  return "publication_not_verified"
 if normalized_kind(p) not in ORIGINAL_ARTICLE_KINDS:return "article_type_not_verified"
 if p.get("publication_date")!=date:return "not_published_today"
 return "candidate"

def aps_publications(journal):
 """Publisher RSS carries final volume/article number and the Published date.

 Crossref's online date may actually describe an accepted manuscript. It is
 discovery metadata, never sufficient proof of formal APS publication.
 """
 slug={"PRL":"prl","PRX":"prx"}[journal]
 url="https://feeds.aps.org/rss/recent/"+slug+".xml"
 root=ET.fromstring(fetch(url));ns={"r":"http://purl.org/rss/1.0/","dc":"http://purl.org/dc/elements/1.1/","p":"http://prismstandard.org/namespaces/basic/2.0/"}
 out={}
 for e in root.findall("r:item",ns):
  doi=clean(e.findtext("p:doi","",ns)).lower()
  volume=clean(e.findtext("p:volume","",ns))
  number=clean(e.findtext("p:startingPage","",ns))
  description=e.findtext("r:description","",ns)
  date=publication_day(e.findtext("p:publicationDate","",ns) or e.findtext("dc:date","",ns))
  if not doi or not volume or not number or not date or not re.search(r"\bPublished\b",clean(description)):continue
  out[doi]={"DOI":doi,"type":"journal-article","title":[clean(e.findtext("r:title","",ns))],
   "_authors_text":clean(e.findtext("dc:creator","",ns)),"abstract":"",
   "article_kind":clean(e.findtext("dc:type","",ns)),
   "publication_status":"published","publication_date":date,
   "publication_evidence":{"source":"APS RSS","url":url,"volume":volume,"article_number":number}}
 return out

def journals(today,audit=None,skip_ids=None,source_status=None,pending=None):
 """Only today's formally published original articles/letters reach AI."""
 skip_ids=skip_ids or {};audit=audit if audit is not None else []
 source_status=source_status if source_status is not None else []
 date=today.date().isoformat()
 work={}
 for name,issn in ISSN.items():
  total=0
  try:
   formal=aps_publications(name) if name in ("PRL","PRX") else {}
   records=list(crossref_records(issn,date,date))
   known={str(x.get("DOI","")).lower() for x in records}
   records.extend(x for doi,x in formal.items() if x["publication_date"]==date and doi not in known)
   for x in records:
    if x.get("type")!="journal-article":continue
    title=clean((x.get("title") or [""])[0]);doi=x.get("DOI","").lower().strip()
    if not doi or not journal_candidate_scope(name,title):continue
    total+=1
    pid="doi-"+re.sub("[^a-z0-9-]","-",doi)
    if pid in skip_ids:
     audit.append({"id":pid,"doi":doi,"title":title,"journal":name,"decision":skip_ids[pid]})
     continue
    paper={"id":pid,"doi":doi,"title":title,"type":"Journal","journal":name,
     "authors":x.get("_authors_text") or ", ".join(clean(a.get("given","")+" "+a.get("family","")) for a in x.get("author",[])),
     "abstract":clean(x.get("abstract","")),"crossref_online_date":x.get("published-online",{}).get("date-parts",[]),
     "corresponding":"","url":"https://doi.org/"+doi,"level":"Brief","method":"","result":"","future":""}
    if name in ("PRL","PRX"):
     verified=formal.get(doi,{})
     paper.update({k:verified[k] for k in ("article_kind","publication_status","publication_date","publication_evidence") if k in verified})
     paper.setdefault("publication_status","unverified")
    work[pid]=paper
   source_status.append({"source":name,"status":"ok","fetched":total,"window":[date,date],
     "publication_proof":"publisher RSS" if name in ("PRL","PRX") else "publisher article metadata"})
  except Exception as exc:
   source_status.append({"source":name,"status":"failed","fetched":total,"error":str(exc)})
  print(f"Journal harvesting {name}: fetched={total}, formal publication day={date}",flush=True)
 for p in pending or []:
  if p.get("journal") in ISSN and p.get("id") not in skip_ids:
   work.setdefault(p["id"],dict(p))
 def recover(p):
  # Known non-research types and Reply/Comment titles never enter an abstract queue.
  if is_non_original(p):
   p["abstract_status"]="non_original_article";return p
  publisher_meta={};publisher_ab=""
  if p["journal"] not in ("PRL","PRX"):
   publisher_ab=publisher_abstract(p["journal"],p["doi"],publisher_meta)
   p.update(publisher_meta)
  decision=journal_eligibility(p,date)
  if decision!="candidate":
   p["abstract_status"]=decision;return p
  p["abstract_source"]="Crossref" if len(p["abstract"])>=140 else "publisher"
  if len(p["abstract"])<140:p["abstract"]=publisher_ab
  if len(p["abstract"])<140:
   p["abstract"]=metadata_abstract(p["doi"]);p["abstract_source"]="DOI metadata"
  p["abstract_status"]="available" if len(p["abstract"])>=140 else "pending_abstract"
  p["topic"]=topic(p["title"]+" "+p["abstract"])
  p["summary_en"]=p["summary"]=summary(p["abstract"])
  return p
 with ThreadPoolExecutor(max_workers=8) as pool:recovered=list(pool.map(recover,work.values()))
 unresolved_aps=[p for p in recovered if p["abstract_status"]=="pending_abstract" and p["journal"] in ("PRL","PRX")]
 preprints=arxiv_metadata_abstracts(unresolved_aps)
 out=[]
 for p in recovered:
  if p["doi"] in preprints:
   abstract,source=preprints[p["doi"]]
   related=re.search(r"/abs/(\d{4}\.\d{4,5})",source)
   p.update(abstract=abstract,abstract_source=source,abstract_status="available",
     related_arxiv_id=related[1] if related else "",
     summary_en=summary(abstract),summary=summary(abstract),topic=topic(p["title"]+" "+abstract))
  available=p["abstract_status"]=="available"
  audit.append({"id":p["id"],"doi":p["doi"],"title":p["title"],"journal":p["journal"],
    "article_kind":p.get("article_kind",""),"publication_status":p.get("publication_status","unverified"),
    "publication_date":p.get("publication_date",""),"publication_evidence":p.get("publication_evidence",{}),
    "has_abstract":available,"decision":"candidate" if available else p["abstract_status"]})
  if available:out.append(p)
  if pending is not None:
   pending[:]=[q for q in pending if q.get("id")!=p["id"]]
   if p["abstract_status"]=="pending_abstract":pending.append(p)
 return out

def paper_aliases(p):
 aliases=set()
 if p.get("id"):aliases.add("id:"+p["id"])
 title=re.sub(r"\W+","",unescape(clean(p.get("title",""))).casefold())
 if title:aliases.add("title:"+title)
 for key in ("doi","journal_doi","published_doi"):
  value=str(p.get(key) or "").lower().removeprefix("https://doi.org/").removeprefix("http://doi.org/")
  if value:aliases.add("doi:"+value)
 for key in ("arxiv_id","related_arxiv_id"):
  value=re.sub(r"v\d+$","",str(p.get(key) or ""))
  if value:aliases.add("arxiv:"+value)
 return aliases

def enrich(records):
 key=os.getenv("OPENAI_API_KEY")
 if not key:return
 def enrich_batch(batch):
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
  payload={"model":"gpt-6-luna",
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
 with ThreadPoolExecutor(max_workers=3) as pool:
  list(pool.map(enrich_batch,[records[k:k+5] for k in range(0,len(records),5)]))

def screening_config():
 return {"arxiv_min_score":ARXIV_MIN_SCORE,"journal_min_score":55,"max_papers":30,
   "arxiv_versions":[1],"exclude_soft_matter":True,"journals":list(ISSN),
   "journal_publication":"publisher-verified formal online publication on the issue date",
   "journal_document_types":"research article or research letter; no accepted papers, essays, replies or comments",
   "editorial_interest":"experimental quantum materials; original theory and experiment"}

def atomic_json(path,value):
 path.parent.mkdir(exist_ok=True,parents=True)
 temp=path.with_suffix(path.suffix+".tmp")
 temp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding="utf8")
 temp.replace(path)

def validate_issue(issue):
 assert issue.get("screening_version")==SCREENING_VERSION,"Issue uses outdated screening rules"
 assert issue.get("sources_complete") is True,"Source harvest incomplete"
 assert len(issue.get("papers",[]))<=30,"More than 30 articles"
 stats=issue.get("stats",{})
 assert stats.get("global_editorial"),"AI editorial screening incomplete"
 assert stats.get("ai_unscored")==0 and stats.get("ai_assessed")==stats.get("scanned"),"Missing AI assessments"
 ids=set()
 for p in issue.get("papers",[]):
  assert not is_non_original(p),"Non-original article"
  assert p["id"] not in ids,"Duplicate paper ID"
  ids.add(p["id"])
  assert p.get("ai_in_scope") is True and p.get("soft_matter") is False,"Scope decision missing or excluded"
  if p["type"]=="arXiv":
   assert p.get("arxiv_version")==1,"Revised arXiv paper"
   assert p.get("announcement_date")==issue["date"],"Stale arXiv announcement"
   assert p.get("primary_category") not in ("cond-mat.soft","cond-mat.quant-gas"),"Excluded arXiv category"
   assert p.get("quantum_materials") is True and p["relevance_score"]>=ARXIV_MIN_SCORE,"arXiv focus/score failed"
  else:
   assert p["type"]=="Journal" and p["journal"] in ISSN,"Source outside whitelist"
   assert journal_eligibility(p,issue["date"])=="candidate","Journal not verified as today's formally published research"
   assert p.get("abstract_status")=="available","Journal abstract unavailable"
   assert p["relevance_score"]>=55,"Journal score failed"

def main(argv=None):
 parser=argparse.ArgumentParser(description="Generate or explicitly re-screen a dated daily issue")
 parser.add_argument("--date",default=os.getenv("ISSUE_DATE") or None)
 parser.add_argument("--rescreen",action="store_true",default=os.getenv("RESCREEN","").lower()=="true")
 args=parser.parse_args(argv)
 now=dt.datetime.now(ZoneInfo("America/Los_Angeles"))
 date=args.date or now.date().isoformat()
 requested=dt.date.fromisoformat(date)
 if requested>now.date():raise ValueError("Cannot generate a future issue")
 dest=ROOT/"issues"/(date+".json")
 audit_path=ROOT/"audits"/(date+".json")
 saved={}
 if audit_path.exists():
  candidate=json.loads(audit_path.read_text(encoding="utf8"))
  # Raw evidence survives policy changes; only AI assessment caches expire.
  if isinstance(candidate.get("candidates"),list):saved=candidate
 historical=requested!=now.date()
 if historical and not saved:
  raise RuntimeError("Historical re-screen requires a saved candidate snapshot for that date; the live arXiv list is not a historical feed")
 old=set();old_aliases=set()
 for path in (ROOT/"issues").glob("*.json"):
  if path.stem>=date:continue
  for p in json.loads(path.read_text(encoding="utf8")).get("papers",[]):
   old.add(p["id"]);old_aliases.update(paper_aliases(p))
 cache={};pending=[]
 for path in sorted((ROOT/"audits").glob("????-??-??.json")):
  if path.stem>date:continue
  previous=json.loads(path.read_text(encoding="utf8"))
  for p in previous.get("pending_journal_records",[]):
   if p.get("id") not in old:pending.append(p)
  assessment_version=previous.get("assessment_version") or previous.get("screening_version")
  if not args.rescreen and assessment_version==ASSESSMENT_VERSION:
   for p in previous.get("candidates",[]):
    if p.get("_ai_assessment"):cache[p["id"]]=p
 journal_audit=[];arxiv_audit=[];sources=[]
 if historical:
  papers=saved.get("candidates",[])
  journal_audit=saved.get("journal_candidates",[])
  arxiv_audit=saved.get("arxiv_candidates",[])
  sources=saved.get("sources",[])
 else:
  papers=[]
  try:
   papers+=arxiv(now,arxiv_audit)
   sources.append({"source":"arXiv","status":"ok","eligible_v1":len(papers)})
  except Exception as exc:
   sources.append({"source":"arXiv","status":"failed","error":str(exc)})
  papers+=journals(now,journal_audit,{pid:"previous_issue" for pid in old},sources,pending)
  blocked={a["id"] for a in journal_audit if a.get("decision") not in ("candidate","pending_abstract")}
  for p in saved.get("candidates",[]):
   if p.get("type")=="Journal" and p["id"] not in blocked and journal_eligibility(p,date)=="candidate":papers.append(p)
 complete=len(sources)==10 and all(x["status"]=="ok" for x in sources)
 if not complete:
  atomic_json(ROOT/"audits"/(date+".failed.json"),{"date":date,"screening_version":SCREENING_VERSION,"sources":sources})
  raise RuntimeError("A source could not be harvested; previous published issue preserved")
 pool={};seen_aliases=set();duplicates={}
 for p in sorted(papers,key=lambda p:p["type"]!="Journal"):
  if is_non_original(p):continue
  if p["type"]=="Journal" and journal_eligibility(p,date)!="candidate":continue
  aliases=paper_aliases(p)
  if p["id"] in old or aliases & (old_aliases|seen_aliases):
   p["screening_decision"]="duplicate_work"
   duplicates[p["id"]]=p
   continue
  seen_aliases.update(aliases);pool[p["id"]]=p
 candidates=list(pool.values())
 valid_cache={}
 for p in candidates:
  previous=cache.get(p["id"],{})
  if all(previous.get(k)==p.get(k) for k in ("title","abstract","type","arxiv_version","primary_category")) and previous.get("_ai_assessment"):
   valid_cache[p["id"]]=previous["_ai_assessment"]
 print(f"Screening {date}: {len(candidates)} candidates; rules={SCREENING_VERSION}; force={args.rescreen}",flush=True)
 kept,stats=screen(candidates,cached_assessments=valid_cache)
 for a in journal_audit:
  if a.get("id") in duplicates:a["decision"]="duplicate_work"
 duplicate_arxiv={p.get("arxiv_id") for p in duplicates.values() if p.get("arxiv_id")}
 for a in arxiv_audit:
  if a.get("arxiv_id") in duplicate_arxiv:a["decision"]="duplicate_work"
 by_arxiv={p.get("arxiv_id"):p for p in candidates if p["type"]=="arXiv"}
 for rows,lookup,key in ((journal_audit,pool,"id"),(arxiv_audit,by_arxiv,"arxiv_id")):
  for a in rows:
   p=lookup.get(a.get(key))
   if p:
    a.update({"decision":p.get("screening_decision"),"score":p.get("relevance_score"),
     "in_scope":p.get("ai_in_scope"),"soft_matter":p.get("soft_matter"),
     "quantum_materials":p.get("quantum_materials"),"reason":p.get("relevance_reason","")})
 selected_ids={p["id"] for p in kept}
 pending_by_id={p["id"]:p for p in pending}
 unresolved=[p for p in pending_by_id.values() if p["id"] not in pool and p["id"] not in old]
 stats.update({"duplicate_work_excluded":len(duplicates),"arxiv_selected":sum(p["type"]=="arXiv" for p in kept),
   "journal_selected":sum(p["type"]=="Journal" for p in kept),
   "arxiv_harvest_excluded":sum(a.get("decision") in ("replacement_section","not_first_version","soft_matter_category","quantum_gas_category") for a in arxiv_audit),
   "pending_journal_abstracts":len(unresolved),
   "non_original_excluded":sum(a.get("decision")=="non_original_article" for a in journal_audit),
   "publication_not_eligible":sum(a.get("decision") in ("accepted_unpublished","publication_not_verified","article_type_not_verified","not_published_today") for a in journal_audit)})
 audit={"date":date,"generated_at":now.isoformat(),"screening_version":SCREENING_VERSION,
   "assessment_version":ASSESSMENT_VERSION,"screening_config":screening_config(),"sources":sources,"journal_candidates":journal_audit,
   "arxiv_candidates":arxiv_audit,"candidates":candidates,
   "pending_journal_records":unresolved,"selected_ids":sorted(selected_ids),"stats":stats}
 atomic_json(audit_path,audit)
 for p in kept:p["level"]="Feature" if p.get("feature_candidate") else "Brief"
 enrich(kept)
 public_papers=[{k:v for k,v in p.items() if not k.startswith("_")} for p in kept]
 public_papers.sort(key=lambda p:(p["type"]!="Journal",p["topic"],p["title"]))
 issue={"date":date,"title":"Daily Condensed Matter Literature","generated_at":now.isoformat(),
   "screening_version":SCREENING_VERSION,"screening_config":screening_config(),
   "sources_complete":complete,"papers":public_papers,"stats":stats}
 validate_issue(issue)
 atomic_json(dest,issue)
 print(f"Saved {date}: {len(kept)} papers under {SCREENING_VERSION}: {stats}",flush=True)
 return issue

if __name__=="__main__":main()
