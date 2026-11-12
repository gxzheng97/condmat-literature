"""A fresh runner must preserve the already-published PDF archive."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

import report_assets as assets
from report_state import record_report, report_is_available, report_is_current, report_path

DAY = "2026-11-11"
PDF = b"%PDF-1.7\ncomplete archived report\n%%EOF\n"


class ReportAssetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "issues").mkdir()
        self.issue = {"date": DAY, "papers": [{"id": "one", "authors": "A, B"}]}
        (self.root / "issues" / f"{DAY}.json").write_text(json.dumps(self.issue), encoding="utf8")
        self.state = {"issues": {DAY: self.issue}, "reports": {
            DAY: {lang: f"reports/{DAY}.{lang}.pdf" for lang in ("en", "zh")}}}

    def test_published_archive_is_restored_on_cache_miss(self):
        restored = assets.restore_reports(self.root, reader=lambda: self.state, downloader=lambda url: PDF)
        self.assertEqual(len(restored), 2)
        for lang in ("en", "zh"):
            self.assertTrue(report_is_available(self.root, self.issue, lang))
            self.assertFalse(report_is_current(self.root, self.issue, lang))

    def test_valid_cache_needs_no_pdf_downloads(self):
        for lang in ("en", "zh"):
            path = report_path(self.root, DAY, lang)
            path.parent.mkdir(exist_ok=True)
            path.write_bytes(PDF)
            record_report(self.root, self.issue, lang)
        downloader = Mock(side_effect=AssertionError("Cached PDFs must not be downloaded again"))
        self.assertEqual(assets.restore_reports(self.root, reader=lambda: self.state, downloader=downloader), [])
        downloader.assert_not_called()

    def test_changed_issue_does_not_acquire_an_old_pdf(self):
        live = copy.deepcopy(self.state)
        live["issues"][DAY]["papers"][0]["authors"] = "A et al."
        downloader = Mock(side_effect=AssertionError("Stale report"))
        self.assertEqual(assets.restore_reports(self.root, reader=lambda: live, downloader=downloader), [])
        self.assertFalse(report_is_available(self.root, self.issue, "en"))

    def test_corrupt_download_preserves_the_existing_file(self):
        self.state["reports"][DAY] = {"en": f"reports/{DAY}.en.pdf"}
        destination = report_path(self.root, DAY, "en")
        destination.parent.mkdir()
        destination.write_bytes(PDF)
        with self.assertRaisesRegex(ValueError, "complete PDF"):
            assets.restore_reports(self.root, reader=lambda: self.state, downloader=lambda url: b"%PDF-partial")
        self.assertEqual(destination.read_bytes(), PDF)
        self.assertFalse(list(destination.parent.glob("*.tmp")))

    def test_known_asset_download_failure_prevents_archive_deletion(self):
        def unavailable(url):
            raise TimeoutError("Published PDF temporarily unavailable")
        with self.assertRaises(TimeoutError):
            assets.restore_reports(self.root, reader=lambda: self.state, downloader=unavailable)

    def test_published_index_cannot_redirect_downloads_to_another_host(self):
        self.state["reports"][DAY]["en"] = "https://example.org/untrusted.pdf"
        downloader = Mock()
        with self.assertRaisesRegex(ValueError, "Unexpected published report URL"):
            assets.restore_reports(self.root, reader=lambda: self.state, downloader=downloader)
        downloader.assert_not_called()

    def test_invalid_date_cannot_escape_report_directory(self):
        self.state = {"issues": {"../escape": self.issue}, "reports": {"../escape": {"en": "anything"}}}
        with self.assertRaises(ValueError):
            assets.restore_reports(self.root, reader=lambda: self.state)

    def test_bootstrap_has_no_archive_to_restore(self):
        self.assertEqual(assets.restore_reports(self.root, reader=lambda: {"issues": {}, "reports": {}}), [])

    def test_parse_existing_page_without_executing_javascript(self):
        html = '<script id="issues-data" type="application/json">' + json.dumps([self.issue]) + '</script>'
        html += '<script>const AVAILABLE_REPORTS=' + json.dumps(self.state["reports"]) + ';alert("never executed");</script>'
        self.assertEqual(assets.parse_live_state(html), self.state)

    def test_unrecognized_page_is_not_treated_as_an_empty_archive(self):
        with self.assertRaises(ValueError):
            assets.parse_live_state("<html>Temporary error</html>")


if __name__ == "__main__":
    unittest.main()
