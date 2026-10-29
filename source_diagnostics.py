"""Read-only public-source diagnostics; no model calls or publication."""
import json
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter
import update_daily as u

audit=json.loads(open("audits/2026-10-29.json",encoding="utf8").read())
for journal,slug in [("PRL","prl"),("PRX","prx")]:
    url="https://feeds.aps.org/rss/recent/"+slug+".xml"
    try:
        req=urllib.request.Request(url,headers={"User-Agent":"CondMatLiteratureMonitor/1.0"})
        with urllib.request.urlopen(req,timeout=30) as response:
            body=response.read().decode("utf8","replace")
            print("FEED_HTTP",journal,response.status,{k:response.headers.get(k) for k in ["Date","Last-Modified","Age","Content-Type"]},flush=True)
        root=ET.fromstring(body)
        items=root.findall(".//{*}item")
        print("FEED_SHAPE",journal,root.tag,"items",len(items),flush=True)
        print("FIRST_ITEM",journal,ET.tostring(items[0],encoding="unicode")[:7500] if items else body[:3500],flush=True)
        print("FIELD_NAMES",journal,dict(Counter(child.tag for item in items for child in item)),flush=True)
        verified=u.aps_publications(journal)
        print("EXISTING_PARSER",journal,len(verified),"dates",dict(Counter(x["publication_date"] for x in verified.values())),flush=True)
        for candidate in audit["journal_candidates"]:
            if candidate["journal"]==journal:
                matches=[e for e in items if candidate["doi"] in ET.tostring(e,encoding="unicode")]
                if matches:
                    print("MATCHED_ITEM",candidate["doi"],ET.tostring(matches[0],encoding="unicode")[:6500],flush=True)
                    break
    except Exception as exc:
        print("SOURCE_ERROR",journal,type(exc).__name__,str(exc),flush=True)

for url in [
 "https://feeds.aps.org/rss/recent/prl.xml?release_date=2026-10-30",
 "https://arxiv.org/catchup/cond-mat/2026-10-28",
 "https://arxiv.org/catchup/cond-mat/2026-10-29",
]:
    try:
        req=urllib.request.Request(url,headers={"User-Agent":"CondMatLiteratureMonitor/1.0","Cache-Control":"no-cache"})
        with urllib.request.urlopen(req,timeout=30) as response:
            body=response.read().decode("utf8","replace")
            print("DATED_SOURCE",url,response.status,{k:response.headers.get(k) for k in ["Date","Last-Modified","Age"]},flush=True)
        if "aps.org" in url:
            parsed=ET.fromstring(body)
            print("DATED_APS_DATES",dict(Counter(x.text for x in parsed.findall(".//{http://prismstandard.org/namespaces/basic/2.0/}publicationDate"))),flush=True)
        else:
            print("DATED_ARXIV_HTML",body[body.find("<h1"):body.find("<h1")+20000],flush=True)
    except Exception as exc:
        print("DATED_SOURCE_ERROR",url,type(exc).__name__,str(exc),flush=True)

for url in [
 "https://journals.aps.org/prl/recent",
 "https://journals.aps.org/prl/abstract/10.1103/3x42-zb9r",
 "https://feeds.aps.org/rss/prl.xml",
 "https://feeds.aps.org/rss/recent/prl.xml?rss=1",
]:
    try:
        req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0","Cache-Control":"no-cache"})
        with urllib.request.urlopen(req,timeout=20) as response:
            body=response.read(1000000).decode("utf8","replace")
            print("FALLBACK_HTTP",url,response.status,{k:response.headers.get(k) for k in ["Date","Last-Modified","Age"]},flush=True)
        if "feeds.aps" in url:
            parsed=ET.fromstring(body)
            print("FALLBACK_APS_DATES",dict(Counter(x.text for x in parsed.findall(".//{http://prismstandard.org/namespaces/basic/2.0/}publicationDate"))),flush=True)
        else:
            marker=body.find("Odd-Even")
            print("FALLBACK_HTML",url,body[max(0,marker-1500):marker+7500] if marker>=0 else body[:3500],flush=True)
    except Exception as exc:
        print("FALLBACK_SOURCE_ERROR",url,type(exc).__name__,str(exc),flush=True)
