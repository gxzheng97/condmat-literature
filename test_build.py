"""Public site packaging excludes incomplete, obsolete and private report files."""
import contextlib
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest

from build import build_site
from report_state import record_report, report_path

PDF = b"%PDF-1.7\ncomplete report\n%%EOF\n"


class BuildTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "issues").mkdir()
        (self.root / "site_template.html").write_text('<script id="issues-data">__ISSUES__</script><script>const AVAILABLE_REPORTS=__REPORTS__;</script>', encoding="utf8")
        (self.root / "make_reports.py").write_text("renderer", encoding="utf8")
        self.issue = {"date": "2026-11-12", "papers": [{"title": "Quantum material"}]}
        self.save(self.issue)

    def save(self, issue):
        (self.root / "issues" / (issue["date"] + ".json")).write_text(json.dumps(issue), encoding="utf8")

    def report(self, issue=None, lang="en", renderer=None):
        issue = issue or self.issue
        path = report_path(self.root, issue["date"], lang)
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(PDF)
        record_report(self.root, issue, lang, renderer_fingerprint=renderer)
        return path

    def pair(self, issue=None, renderer=None):
        return [self.report(issue, lang, renderer) for lang in ("en", "zh")]
    def build(self, output=None):
        with contextlib.redirect_stdout(io.StringIO()):
            return build_site(self.root, output)

    def test_complete_report_is_linked_without_rendering_dependencies(self):
        self.pair()
        result = self.build()
        self.assertEqual(result["reports"], {"2026-11-12": {"en": "reports/2026-11-12.en.pdf", "zh": "reports/2026-11-12.zh.pdf"}})
        self.assertIn('reports/2026-11-12.en.pdf', (self.root / "index.html").read_text())

    def test_one_complete_language_is_kept_for_retry_without_public_links(self):
        self.report(lang="en")
        result = self.build("_site")
        self.assertEqual(result["reports"], {})
        self.assertFalse(list((self.root / "_site" / "reports").glob("*.pdf")))
        self.assertTrue(report_path(self.root, self.issue["date"], "en").exists())
    def test_partial_and_unrecorded_reports_are_not_linked(self):
        complete = self.report()
        complete.write_bytes(b"%PDF-truncated")
        report_path(self.root, self.issue["date"], "zh").write_bytes(PDF)
        self.assertEqual(self.build()["reports"], {})

    def test_report_from_older_issue_content_is_not_linked(self):
        self.pair()
        self.issue["papers"][0]["title"] = "Corrected findings"
        self.save(self.issue)
        self.assertEqual(self.build()["reports"], {})

    def test_valid_historical_pdf_remains_linked_after_renderer_change(self):
        older = copy.deepcopy(self.issue)
        older["date"] = "2026-11-11"
        self.save(older)
        self.pair(older, renderer="legacy")
        self.pair()
        (self.root / "make_reports.py").write_text("changed renderer", encoding="utf8")
        self.assertEqual(set(self.build()["reports"]), {"2026-11-11", "2026-11-12"})

    def test_deployment_contains_only_index_and_verified_pdfs(self):
        self.pair()
        (self.root / "private.py").write_text("private source", encoding="utf8")
        (self.root / "reports" / "internal.txt").write_text("internal metadata", encoding="utf8")
        self.build("_site")
        actual = {p.relative_to(self.root / "_site").as_posix() for p in (self.root / "_site").rglob("*") if p.is_file()}
        self.assertEqual(actual, {"index.html", "reports/2026-11-12.en.pdf", "reports/2026-11-12.zh.pdf"})
        self.assertEqual((self.root / "index.html").read_bytes(), (self.root / "_site" / "index.html").read_bytes())

    def test_second_build_removes_pdf_that_no_longer_matches_issue(self):
        self.pair()
        self.build("_site")
        self.issue["papers"][0]["title"] = "Updated article"
        self.save(self.issue)
        self.build("_site")
        self.assertFalse((self.root / "_site" / "reports" / "2026-11-12.en.pdf").exists())
        self.assertTrue(report_path(self.root, self.issue["date"], "en").exists())
        self.assertNotIn("reports/2026-11-12.en.pdf", (self.root / "_site" / "index.html").read_text())

    def test_unexpected_file_in_output_is_rejected_and_preserved(self):
        output = self.root / "_site"
        (output / "reports").mkdir(parents=True)
        unexpected = output / "reports" / "keep.txt"
        unexpected.write_text("unrelated", encoding="utf8")
        with self.assertRaisesRegex(ValueError, "unexpected"):
            self.build(output)
        self.assertEqual(unexpected.read_text(), "unrelated")

    def test_source_tree_cannot_be_used_as_deployment_output(self):
        for output in (self.root, "issues", "reports"):
            with self.assertRaises(ValueError):
                self.build(output)
        self.assertTrue((self.root / "site_template.html").is_file())

    def test_script_closing_text_is_escaped_in_json_payload(self):
        self.issue["papers"][0]["title"] = "</script><script>untrusted</script>"
        self.save(self.issue)
        self.build()
        html = (self.root / "index.html").read_text()
        self.assertNotIn("</script><script>untrusted", html)
        self.assertIn(r"<\/script>", html)


if __name__ == "__main__":
    unittest.main()