"""Build the static site and an optional deployment package of public files only."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import tempfile

from report_state import LANGUAGES, report_is_available, report_path

ROOT = Path(__file__).resolve().parent
REPORT_NAME = re.compile(r"\d{4}-\d{2}-\d{2}\.(?:en|zh)\.pdf\Z")


def _atomic_text(path, text):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf8", dir=path.parent,
                                         prefix=path.name + ".", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(text)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _deployment_directory(root, output):
    path = Path(output)
    target = (path if path.is_absolute() else root / path).resolve()
    if target == root or not target.is_relative_to(root):
        raise ValueError("Deployment output must be a separate directory inside the project")
    if target.relative_to(root).parts[0] in ("issues", "reports", ".git"):
        raise ValueError("Deployment output must not overlap source data")
    target.mkdir(parents=True, exist_ok=True)
    # Do not silently package unrelated files from a reused directory.
    for entry in target.iterdir():
        if entry.is_symlink():
            raise ValueError("Deployment output must not contain symlinks")
        if entry.name == "index.html" and entry.is_file():
            continue
        if entry.name == "reports" and entry.is_dir():
            for report in entry.iterdir():
                if report.is_symlink() or not report.is_file() or not REPORT_NAME.fullmatch(report.name):
                    raise ValueError("Deployment reports directory contains an unexpected file")
            continue
        raise ValueError("Deployment output contains an unexpected file: " + entry.name)
    return target


def _copy_report(source, destination):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent, prefix=destination.name + ".",
                                         suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
        shutil.copyfile(source, temporary)
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def build_site(root, output=None):
    root = Path(root).resolve()
    issues = [json.loads(path.read_text(encoding="utf8"))
              for path in sorted((root / "issues").glob("????-??-??.json"), reverse=True)]
    reports = {}
    sources = {}
    for issue in issues:
        pair = {lang: report_path(root, issue["date"], lang) for lang in LANGUAGES}
        if not all(not path.is_symlink() and report_is_available(root, issue, lang)
                   for lang, path in pair.items()):
            continue
        # A partial rendering attempt is kept for retry, but both languages
        # must be complete before this issue exposes any download links.
        for lang, source in pair.items():
            relative = "reports/" + source.name
            reports.setdefault(issue["date"], {})[lang] = relative
            sources[source.name] = source
    payload = json.dumps(issues, ensure_ascii=False).replace("</", r"<\/")
    template = (root / "site_template.html").read_text(encoding="utf8")
    html = template.replace("__ISSUES__", payload).replace("__REPORTS__", json.dumps(reports))
    deployment = _deployment_directory(root, output) if output is not None else None
    _atomic_text(root / "index.html", html)
    if deployment is not None:
        report_directory = deployment / "reports"
        report_directory.mkdir(exist_ok=True)
        for name, source in sources.items():
            _copy_report(source, report_directory / name)
        for existing in report_directory.iterdir():
            if REPORT_NAME.fullmatch(existing.name) and existing.name not in sources:
                existing.unlink()
        _atomic_text(deployment / "index.html", html)
    count = sum(len(issue.get("papers", [])) for issue in issues)
    print(f"Built {len(issues)} issues with {count} papers and {len(sources)} verified PDF reports", flush=True)
    return {"issues": len(issues), "papers": count, "reports": reports,
            "output": str(deployment) if deployment is not None else str(root / "index.html")}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", help="Project-relative directory containing only public deployment files")
    args = parser.parse_args(argv)
    return build_site(ROOT, args.output)


if __name__ == "__main__":
    main()