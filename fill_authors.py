#!/usr/bin/env python3
"""Restore full author bibliographies for the current curated issue."""
import concurrent.futures, datetime, json, re, time, urllib.parse, urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parent
NS={'a':'http://www.w3.org/2005/Atom'}
def get(url):
    req=urllib.request.Request(url,headers={'User-Agent':'CondMatJournalClub/1.1 (bibliography enrichment; academic research)'})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req,timeout=35) as response:return response.read()
        except Exception as exc:
            if attempt==2:raise
            time.sleep(2+attempt*3)
def normalize(s):
    return re.sub(r'\s+',' ',s or '').strip()
def crossref_authors(p):
    doi=p.get('doi')
    if not doi or 'et al.' not in p.get('authors',''):return None
    try:
        url='https://api.crossref.org/works/'+urllib.parse.quote(doi,safe='/')
        item=json.loads(get(url))['message']
        authors=[normalize(a.get('given','')+' '+a.get('family','')) for a in item.get('author',[])]
        return p['id'], ', '.join(x for x in authors if x)
    except Exception as exc:
        print('Crossref author fetch:',doi,str(exc)[:130]);return None
def arxiv_authors(papers):
    ids=[p['arxiv_id'] for p in papers if p.get('arxiv_id') and 'et al.' in p.get('authors','')]
    results={}
    for offset in range(0,len(ids),65):
        part=ids[offset:offset+65]
        query=urllib.parse.urlencode({'id_list':','.join(part),'max_results':len(part)})
        try:
            root=ET.fromstring(get('https://export.arxiv.org/api/query?'+query))
            for entry in root.findall('a:entry',NS):
                eid=entry.findtext('a:id','',NS).split('/abs/')[-1]
                eid=re.sub(r'v\d+$','',eid)
                authors=[normalize(x.findtext('a:name','',NS)) for x in entry.findall('a:author',NS)]
                if authors:results[eid]=', '.join(authors)
        except Exception as exc:print('arXiv author fetch:',str(exc)[:130])
    return results
def main():
    date=datetime.datetime.now(ZoneInfo('America/Los_Angeles')).date().isoformat()
    path=ROOT/'issues'/(date+'.json')
    if not path.exists():return
    issue=json.loads(path.read_text(encoding='utf8'))
    papers=issue['papers']
    byid={p['id']:p for p in papers}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for result in pool.map(crossref_authors,[p for p in papers if p['type']=='Journal']):
            if result and result[1]:byid[result[0]]['authors']=result[1]
    arxiv=arxiv_authors(papers)
    for p in papers:
        if p.get('arxiv_id') in arxiv:p['authors']=arxiv[p['arxiv_id']]
    path.write_text(json.dumps(issue,ensure_ascii=False,indent=2),encoding='utf8')
    print('Bibliography refreshed:',len(papers),'papers; arXiv records:',len(arxiv))
if __name__=='__main__':main()
