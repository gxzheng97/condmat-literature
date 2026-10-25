"""Live diagnostics for weekly journal coverage. No AI calls."""
import datetime as dt
import urllib.parse
from zoneinfo import ZoneInfo
from update_daily import crossref_records, journal_candidate_scope, clean, publisher_abstract

now=dt.datetime.now(ZoneInfo("America/Los_Angeles"))
first=(now-dt.timedelta(days=7)).date().isoformat()
last=now.date().isoformat()
targets={
    "PRL":("0031-9007",{
        "10.1103/6327-7256","10.1103/wh99-b81w","10.1103/rm6q-k54p"}),
    "PRX":("2160-3308",{"10.1103/2rw7-bzl4"}),
    "Communications Materials":("2662-4443",
        {"10.1038/s43246-026-01390-9"})
}
print("Live journal recall probe: online publication window",first,"through",last)
for name,(issn,expected) in targets.items():
    found={}
    try:
        for x in crossref_records(issn,first,last):
            doi=str(x.get("DOI","")).lower()
            if doi in expected:
                title=clean((x.get("title") or [""])[0])
                abstract=clean(x.get("abstract",""))
                if not abstract and name in ("PRL","PRX"):
                    abstract=publisher_abstract(name,doi)
                found[doi]={"title":title,"has_abstract":bool(abstract),
                            "abstract_preview":abstract[:120],
                            "passes_source_gate":journal_candidate_scope(name,title,abstract)}
        for doi in sorted(expected):
            if doi in found:
                print("FOUND",name,doi,found[doi])
            else:
                print("NOT_IN_CROSSREF_DATE_WINDOW",name,doi)
    except Exception as exc:
        print("SOURCE_ERROR",name,str(exc))
