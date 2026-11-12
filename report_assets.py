"""Preserve published PDFs across fresh runners and inspect public report links."""
import concurrent.futures
import json
import os
from pathlib import Path
import re
import tempfile
import time
import urllib.error
import urllib.request

from report_state import (issue_fingerprint, pdf_fingerprint, record_report,
                          report_is_available, report_path)

ROOT = Path(__file__).resolve().parent
SITE_URL = "https://gxzheng97.github.io/condmat-literature/"
MAX_BYTES = 30 * 1024 * 1024


def parse_live_state(html):
    match = re.search(r'<script\b[^>]*\bid=["\']issues-data["\'][^>]*>([\s\S]*?)</script>', html, re.I)
    if not match:
        raise ValueError("Published page has no issue data")
    issues = json.loads(match[1])
    marker = re.search(r'\bconst\s+AVAILABLE_REPORTS\s*=\s*', html)
    if not marker:
        raise ValueError("Published page has no report index")
    reports, _ = json.JSONDecoder().raw_decode(html[marker.end():])
    if not isinstance(issues, list) or not isinstance(reports, dict):
        raise ValueError("Malformed published issue/report index")
    return {"issues": {issue["date"]: issue for issue in issues}, "reports": reports}


def download(url):
    for attempt in range(3):
        try:
            request = urllib.request.Request(url, headers={
                "User-Agent": "CondMatReportRecovery/1.0", "Cache-Control": "no-cache"})
            with urllib.request.urlopen(request, timeout=20) as response:
                data = response.read(MAX_BYTES + 1)
            if len(data) > MAX_BYTES:
                raise ValueError("Published asset exceeds the size limit")
            return data
        except (OSError, urllib.error.URLError):
            if attempt == 2:
                raise
            time.sleep(1 + attempt * 2)


def read_live_state():
    try:
        return parse_live_state(download(SITE_URL + "?reports=" + str(time.time_ns())).decode("utf8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return {"issues": {}, "reports": {}}
        raise


def restore_reports(root, reader=None, downloader=None):
    """Cache misses recover only known PDFs from the preceding live publication.

    A known asset that cannot be recovered aborts before deployment: publishing a
    fresh checkout must never silently delete the existing PDF archive.
    """
    root = Path(root)
    state = (reader or read_live_state)()
    pending = []
    for day, links in state["reports"].items():
        if not isinstance(links, dict) or day not in state["issues"]:
            raise ValueError("Malformed published report entry")
        path = root / "issues" / (day + ".json")
        # Validate the date before any local path can be opened.
        report_path(root, day, "en")
        if not path.exists():
            continue
        issue = json.loads(path.read_text(encoding="utf8"))
        if issue_fingerprint(issue) != issue_fingerprint(state["issues"][day]):
            continue  # A deliberate issue edit must not acquire a stale PDF.
        for lang, relative in links.items():
            destination = report_path(root, day, lang)
            if relative != "reports/" + destination.name:
                raise ValueError("Unexpected published report URL")
            if not report_is_available(root, issue, lang):
                pending.append((issue, lang, relative))

    def recover(item):
        issue, lang, relative = item
        destination = report_path(root, issue["date"], lang)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            data = (downloader or download)(SITE_URL + relative)
            if len(data) > MAX_BYTES:
                raise ValueError("Report exceeds the size limit")
            with tempfile.NamedTemporaryFile(dir=destination.parent, suffix=".tmp", delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(data)
            pdf_fingerprint(temporary)
            os.replace(temporary, destination)
            record_report(root, issue, lang, renderer_fingerprint="legacy")
            return relative
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        restored = list(pool.map(recover, pending))
    print(f"Recovered {len(restored)} published PDFs; existing valid cached reports were retained", flush=True)
    return restored


if __name__ == "__main__":
    restored = restore_reports(ROOT)
    if os.getenv("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf8") as stream:
            stream.write(f"restored={len(restored)}\n")
