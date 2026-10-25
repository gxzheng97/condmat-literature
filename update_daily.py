#!/usr/bin/env python3
"""Daily condensed matter literature index, arXiv + Crossref."""
import datetime as dt, json, os, re, time, urllib.parse, urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from zoneinfo import ZoneInfo
from relevance import screen

ROOT=Path(__file__).resolve().parent
NS={"a":"http://www.w3.org/2005/Atom","x":"http://arxiv.org/schemas/atom"}
ISSN={"Science":"0036-8075","Science Advances":"2375-2548","Nature":"0028-0836",
"Nature Physics":"1745-2473","Nature Materials":"1476-1122",
"Nature Communications":"2041-1723","PRL":"0031-9007","PRX":"2160-3308",
"PNAS":"0027-8424"}
PAT=re.compile(r"superconduct|magnet|spin|kagome|quantum|fermi|hall|nematic|phonon|transport|thermo|electron|crystal|growth|synthe|correlat|topolog|excitat|seebeck|nernst|valence|diffraction|semimetal|structure|lattice|spectroscop|anisotrop|moire|strain|pressure|ferroelectric|oxide|thin film|materials|phase transi",re.I)
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
def journals(today):
 out=[];first=(today-dt.timedelta(days=1)).date().isoformat();last=today.date().isoformat()
 for name,issn in ISSN.items():
  query=urllib.parse.urlencode({"filter":f"from-online-pub-date:{first},until-online-pub-date:{last}",
    "rows":100,"select":"DOI,title,author,abstract,type"})
  try:items=json.loads(fetch("https://api.crossref.org/journals/"+issn+"/works?"+query))["message"]["items"]
  except Exception as ex:print("Crossref:",name,str(ex));continue
  for x in items:
   if x.get("type")!="journal-article":continue
   title=clean((x.get("title") or [""])[0]);ab=clean(x.get("abstract",""))
   if not title or not (name in ("PRL","PRX") or PAT.search(title+" "+ab)):continue
   authors=[clean((a.get("given","")+" "+a.get("family",""))) for a in x.get("author",[])]
   doi=x.get("DOI","").lower()
   out.append({"id":"doi-"+re.sub("[^a-z0-9-]","-",doi),"doi":doi,"type":"Journal",
     "journal":name,"title":title,"authors":", ".join(authors[:3])+(" et al." if len(authors)>3 else ""),
     "corresponding":"","url":"https://doi.org/"+doi,"topic":topic(title+" "+ab),
     "level":"Brief","summary_en":summary(ab or title),"summary":summary(ab or title),
     "abstract":ab,"method":"","result":"","future":""})
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
   "PRL, PRB/Physical Review Materials, Below PRB, or Uncertain, with a reason. "
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
 for fn in (arxiv,lambda:journals(today)):
  try:papers+=fn()
  except Exception as e:print("Source failure:",str(e));failures+=1
 seen=set();kept=[]
 for p in sorted(papers,key=lambda p:p["type"]!="Journal"):
  key=re.sub("[^a-z0-9]","",p["title"].lower())
  if p["id"] in old or key in seen:continue
  seen.add(key);kept.append(p)
 if not kept:
  print("No new papers from this run")
  return
 kept,stats=screen(kept)
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
