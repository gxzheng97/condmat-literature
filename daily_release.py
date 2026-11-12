"""Plan and verify daily publication without repeating a completed release."""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import time
import urllib.request
from zoneinfo import ZoneInfo

from update_daily import validate_issue, ArxivListingParser, fetch
from report_assets import read_live_state, download as download_report
from report_state import LANGUAGES, report_is_current, report_path

ROOT=Path(__file__).resolve().parent
SITE_URL="https://gxzheng97.github.io/condmat-literature/"

def fingerprint(issue):
    body=json.dumps(issue,sort_keys=True,ensure_ascii=False,separators=(",",":"))
    return hashlib.sha256(body.encode("utf8")).hexdigest()

def read_published_issue(day,token=""):
    url=SITE_URL+("?release="+token if token else "?day="+day)
    req=urllib.request.Request(url,headers={"User-Agent":"CondMatPublicationCheck/1.0","Cache-Control":"no-cache"})
    with urllib.request.urlopen(req,timeout=20) as response:
        html=response.read().decode("utf8")
    match=re.search(r'<script\b[^>]*\bid=["\']issues-data["\'][^>]*>([\s\S]*?)</script>',html,re.I)
    if not match:
        raise ValueError("Live page does not contain issue data")
    issues=json.loads(match[1])
    for issue in issues:
        if issue.get("date")==day:
            return issue
    raise LookupError("The live website has no issue for "+day)

def load_issue(root,day,validator=None):
    issue=json.loads((Path(root)/"issues"/(day+".json")).read_text(encoding="utf8"))
    if issue.get("date")!=day:
        raise ValueError("Issue date does not match its filename")
    (validator or validate_issue)(issue)
    return issue

def pending_arxiv_announcement(root,day):
    path=Path(root)/"audits"/(day+".json")
    if not path.exists():
        return None
    audit=json.loads(path.read_text(encoding="utf8"))
    if audit.get("date")!=day:
        raise ValueError("Source audit date does not match the issue")
    for entry in audit.get("arxiv_candidates",[]):
        if entry.get("decision")=="no_new_announcement":
            announced=entry.get("announcement_date","")
            dt.date.fromisoformat(announced)
            if announced<day:
                return announced
    return None

def read_arxiv_announcement():
    listing=ArxivListingParser()
    listing.feed(fetch("https://arxiv.org/list/cond-mat/new?show=2000"))
    announced=listing.announcement_date()
    if not listing.entries:
        raise ValueError("arXiv announcement sections could not be parsed")
    return announced

def plan_release(root,day,event,force=False,reader=None,validator=None,announcement_reader=None,reuse_valid=False):
    dt.date.fromisoformat(day)
    if (event!="schedule" and not reuse_valid) or force:
        return {"mode":"generate","date":day,"reason":"explicit_trigger"}
    try:
        issue=load_issue(root,day,validator)
    except (OSError,ValueError,KeyError,AssertionError,TypeError):
        return {"mode":"generate","date":day,"reason":"no_valid_issue_for_today"}
    pending=pending_arxiv_announcement(root,day)
    if pending is not None:
        try:
            announced=(announcement_reader or read_arxiv_announcement)()
            dt.date.fromisoformat(announced)
        except Exception as exc:
            raise RuntimeError("Cannot verify the pending arXiv announcement; preserve the live issue and retry") from exc
        if announced==day:
            return {"mode":"generate","date":day,"reason":"current_arxiv_announcement_now_available"}
    try:
        live=(reader or read_published_issue)(day,fingerprint(issue)[:16])
        if fingerprint(live)==fingerprint(issue):
            if pending is not None:
                return {"mode":"current","date":day,"reason":"published_waiting_for_arxiv_announcement",
                    "pending_sources":["arXiv"],"observed_announcement_date":announced}
            return {"mode":"current","date":day,"reason":"already_published_and_verified"}
    except Exception as exc:
        return {"mode":"deploy","date":day,"reason":"live_issue_unavailable:"+type(exc).__name__}
    return {"mode":"deploy","date":day,"reason":"saved_issue_not_yet_published"}

def verify_release(root,day,attempts=6,delay=10,reader=None,validator=None):
    issue=load_issue(root,day,validator)
    expected=fingerprint(issue)
    last_error=None
    for attempt in range(attempts):
        try:
            live=(reader or read_published_issue)(day,expected[:16])
            if fingerprint(live)!=expected:
                raise ValueError("Live issue content differs from saved issue")
            return {"date":day,"papers":len(issue["papers"]),"verified":True,"url":SITE_URL}
        except Exception as exc:
            last_error=exc
            if attempt+1<attempts:
                time.sleep(delay)
    raise RuntimeError("Publication verification failed: "+str(last_error))

def plan_reports(root,day,reader=None,validator=None,downloader=None):
    """Report recovery is independent of paid screening and body freshness."""
    issue=load_issue(root,day,validator)
    missing=[lang for lang in LANGUAGES if not report_is_current(root,issue,lang)]
    if missing:
        return {"mode":"render","date":day,"reason":"missing_or_outdated_reports","languages":missing}
    try:
        state=(reader or read_live_state)()
        expected={lang:"reports/"+report_path(root,day,lang).name for lang in LANGUAGES}
        if (fingerprint(state["issues"].get(day))==fingerprint(issue)
                and state["reports"].get(day)==expected):
            # URLs do not change when a new renderer replaces an old PDF. A
            # failed second deployment must still be retried from the cache.
            for lang,relative in expected.items():
                data=(downloader or download_report)(SITE_URL+relative+"?release="+str(time.time_ns()))
                if hashlib.sha256(data).digest()!=hashlib.sha256(report_path(root,day,lang).read_bytes()).digest():
                    raise ValueError("Published PDF does not match the current report")
            return {"mode":"current","date":day,"reason":"reports_already_published"}
    except Exception:
        pass
    return {"mode":"deploy","date":day,"reason":"cached_reports_not_yet_published"}

def verify_reports(root,day,attempts=6,delay=10,reader=None,downloader=None,validator=None):
    issue=load_issue(root,day,validator)
    expected={lang:"reports/"+report_path(root,day,lang).name for lang in LANGUAGES}
    if not all(report_is_current(root,issue,lang) for lang in LANGUAGES):
        raise ValueError("Cannot publish an incomplete or outdated report pair")
    last_error=None
    for attempt in range(attempts):
        try:
            state=(reader or read_live_state)()
            if fingerprint(state["issues"].get(day))!=fingerprint(issue) or state["reports"].get(day)!=expected:
                raise ValueError("Published issue/report links differ from saved content")
            for lang,relative in expected.items():
                data=(downloader or download_report)(SITE_URL+relative+"?release="+str(time.time_ns()))
                local=report_path(root,day,lang).read_bytes()
                if hashlib.sha256(data).digest()!=hashlib.sha256(local).digest():
                    raise ValueError("Published PDF differs from the verified local report: "+lang)
            return {"date":day,"verified":True,"reports":expected}
        except Exception as exc:
            last_error=exc
            if attempt+1<attempts:
                time.sleep(delay)
    raise RuntimeError("Report publication verification failed: "+str(last_error))

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command",choices=("plan","verify","reports","verify-reports"))
    parser.add_argument("--date",default=os.getenv("ISSUE_DATE") or None)
    args=parser.parse_args(argv)
    day=args.date or dt.datetime.now(ZoneInfo("America/Los_Angeles")).date().isoformat()
    if args.command=="verify":
        result=verify_release(ROOT,day)
    elif args.command=="verify-reports":
        result=verify_reports(ROOT,day)
    elif args.command=="reports":
        result=plan_reports(ROOT,day)
    else:
        result=plan_release(ROOT,day,os.getenv("EVENT_NAME","workflow_dispatch"),
            force=os.getenv("RESCREEN","").lower()=="true",
            reuse_valid=os.getenv("REUSE_VALID_ISSUE","").lower()=="true")
    if args.command in ("plan","reports") and os.getenv("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"],"a",encoding="utf8") as stream:
            stream.write("mode="+result["mode"]+"\ndate="+day+"\n")
    print(json.dumps(result,ensure_ascii=True),flush=True)

if __name__=="__main__":
    main()

