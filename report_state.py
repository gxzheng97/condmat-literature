"""Validate cached PDFs without importing the optional rendering dependencies."""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import tempfile

LANGUAGES = ("en", "zh")
STATE_SCHEMA = 1


def issue_fingerprint(issue):
    body = json.dumps(issue, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(body.encode("utf8")).hexdigest()


def report_path(root, day, lang):
    if dt.date.fromisoformat(day).isoformat() != day or lang not in LANGUAGES:
        raise ValueError("Invalid report date or language")
    return Path(root) / "reports" / f"{day}.{lang}.pdf"


def report_metadata_path(root, day, lang):
    return report_path(root, day, lang).with_suffix(".json")


def _renderer_fingerprint(root=None):
    base = Path(root) if root is not None else Path(__file__).parent
    digest = hashlib.sha256()
    for filename in ("make_reports.py", "requirements-reports.txt", "prepare_reports.py"):
        source = base / filename
        if not source.is_file():
            source = Path(__file__).with_name(filename)
        digest.update(filename.encode("utf8") + b"\0")
        digest.update(source.read_bytes() if source.is_file() else b"missing")
        digest.update(b"\0")
    return digest.hexdigest()


def renderer_fingerprint(root=None):
    return _renderer_fingerprint(root)

def pdf_fingerprint(path):
    """Reject incomplete files before they become cached reports or public links."""
    data = Path(path).read_bytes()
    if not data.startswith(b"%PDF-") or b"%%EOF" not in data[-1024:]:
        raise ValueError("Report is not a complete PDF")
    return hashlib.sha256(data).hexdigest(), len(data)


def record_report(root, issue, lang, renderer_fingerprint=None):
    destination = report_path(root, issue["date"], lang)
    digest, size = pdf_fingerprint(destination)
    renderer = renderer_fingerprint
    if renderer is None:
        renderer = _renderer_fingerprint(root)
    state = {"schema": STATE_SCHEMA, "date": issue["date"], "language": lang,
             "issue_fingerprint": issue_fingerprint(issue),
             "renderer_fingerprint": renderer, "pdf_sha256": digest, "bytes": size}
    metadata = report_metadata_path(root, issue["date"], lang)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf8", dir=metadata.parent,
                                         prefix=metadata.name + ".", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(state, stream, sort_keys=True, ensure_ascii=False)
            stream.write("\n")
        os.replace(temporary, metadata)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return state


def _available_state(root, issue, lang):
    try:
        path = report_path(root, issue["date"], lang)
        state = json.loads(report_metadata_path(root, issue["date"], lang).read_text(encoding="utf8"))
        if (state.get("schema") != STATE_SCHEMA or state.get("date") != issue["date"]
                or state.get("language") != lang
                or state.get("issue_fingerprint") != issue_fingerprint(issue)):
            return None
        digest, size = pdf_fingerprint(path)
        if state.get("pdf_sha256") != digest or state.get("bytes") != size:
            return None
        return state
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return None


def report_is_available(root, issue, lang):
    """A matching, complete PDF remains usable when renderer code changes."""
    return _available_state(root, issue, lang) is not None


def report_is_current(root, issue, lang):
    state = _available_state(root, issue, lang)
    return state is not None and state.get("renderer_fingerprint") == renderer_fingerprint(root)