"""PDF caching and failures without native rendering dependencies or network calls."""
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import make_reports as reports
import report_state as state

PDF = b"%PDF-1.7\ncomplete test content\n%%EOF\n"


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "issues").mkdir()
        (self.root / "make_reports.py").write_text("renderer source", encoding="utf8")
        (self.root / "requirements-reports.txt").write_text("weasyprint==70.0\n", encoding="utf8")
        (self.root / "prepare_reports.py").write_text("font configuration", encoding="utf8")
        self.issue = {"date": "2026-11-12", "papers": [{"id": "one", "title": "Quantum material", "summary_en": "Original summary"}]}
        self.save_issue()
        self.rendered = []

    def save_issue(self, issue=None):
        issue = issue or self.issue
        (self.root / "issues" / (issue["date"] + ".json")).write_text(json.dumps(issue), encoding="utf8")

    def renderer(self, html, destination, root):
        self.rendered.append(html)
        destination.write_bytes(PDF)

    def generate(self, **kwargs):
        with contextlib.redirect_stdout(io.StringIO()):
            return reports.generate_reports(self.root, renderer=self.renderer, **kwargs)

    def test_current_cache_skips_rendering_both_languages(self):
        first = self.generate()
        second = self.generate()
        self.assertEqual(len(first["generated"]), 2)
        self.assertEqual(len(second["skipped"]), 2)
        self.assertEqual(len(self.rendered), 2)
        self.assertTrue(state.report_is_current(self.root, self.issue, "en"))

    def test_changed_notes_require_new_pdf_and_hide_old_matching_links(self):
        self.generate()
        self.issue["papers"][0]["summary_en"] = "Revised findings"
        self.save_issue()
        self.assertFalse(state.report_is_available(self.root, self.issue, "en"))
        self.generate()
        self.assertEqual(len(self.rendered), 4)
        self.assertTrue(state.report_is_current(self.root, self.issue, "en"))

    def test_renderer_change_keeps_pdf_available_but_requires_rebuild(self):
        self.generate()
        (self.root / "make_reports.py").write_text("new renderer", encoding="utf8")
        self.assertTrue(state.report_is_available(self.root, self.issue, "en"))
        self.assertFalse(state.report_is_current(self.root, self.issue, "en"))

    def test_dependency_change_requires_rebuild_without_hiding_existing_pdf(self):
        self.generate()
        (self.root / "requirements-reports.txt").write_text("weasyprint==71.0\n", encoding="utf8")
        self.assertTrue(state.report_is_available(self.root, self.issue, "zh"))
        self.assertFalse(state.report_is_current(self.root, self.issue, "zh"))

    def test_font_preparation_change_requires_rebuild(self):
        self.generate()
        (self.root / "prepare_reports.py").write_text("new pinned fonts", encoding="utf8")
        self.assertTrue(state.report_is_available(self.root, self.issue, "en"))
        self.assertFalse(state.report_is_current(self.root, self.issue, "en"))
    def test_damaged_pdf_is_neither_available_nor_current(self):
        self.generate()
        state.report_path(self.root, self.issue["date"], "en").write_bytes(PDF + b"modified")
        self.assertFalse(state.report_is_available(self.root, self.issue, "en"))
        self.assertFalse(state.report_is_current(self.root, self.issue, "en"))

    def test_failed_render_preserves_prior_complete_pdf_and_cleans_temporary_file(self):
        self.generate()
        prior = state.report_path(self.root, self.issue["date"], "en").read_bytes()
        def failing(html, destination, root):
            destination.write_bytes(b"%PDF-incomplete")
            raise RuntimeError("renderer unavailable")
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaisesRegex(RuntimeError, "renderer unavailable"):
            reports.generate_reports(self.root, force=True, renderer=failing)
        self.assertEqual(state.report_path(self.root, self.issue["date"], "en").read_bytes(), prior)
        self.assertTrue(state.report_is_available(self.root, self.issue, "en"))
        self.assertFalse(list((self.root / "reports").glob("*.tmp")))

    def test_partial_success_is_reused_when_failed_language_is_retried(self):
        def partial(html, destination, root):
            if 'lang="zh"' in html:
                destination.write_bytes(b"%PDF-broken")
                raise RuntimeError("Chinese renderer failed")
            self.renderer(html, destination, root)
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaisesRegex(RuntimeError, "Chinese renderer failed"):
            reports.generate_reports(self.root, renderer=partial)
        self.assertTrue(state.report_is_available(self.root, self.issue, "en"))
        self.assertFalse(state.report_is_available(self.root, self.issue, "zh"))
        self.assertFalse(state.report_path(self.root, self.issue["date"], "zh").exists())
        retried = self.generate()
        self.assertEqual(len(retried["skipped"]), 1)
        self.assertEqual(len(retried["generated"]), 1)
        self.assertEqual(len(self.rendered), 2)

    def test_incomplete_pdf_is_not_recorded_even_if_renderer_returns_success(self):
        def incomplete(html, destination, root):
            destination.write_bytes(b"%PDF-incomplete")
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaisesRegex(RuntimeError, "complete PDF"):
            reports.generate_reports(self.root, renderer=incomplete)
        self.assertFalse(list((self.root / "reports").glob("*.pdf")))
        self.assertFalse(list((self.root / "reports").glob("*.json")))

    def test_legacy_restore_is_available_but_will_be_rendered_again(self):
        path = state.report_path(self.root, self.issue["date"], "en")
        path.parent.mkdir()
        path.write_bytes(PDF)
        state.record_report(self.root, self.issue, "en", renderer_fingerprint="legacy")
        self.assertTrue(state.report_is_available(self.root, self.issue, "en"))
        self.assertFalse(state.report_is_current(self.root, self.issue, "en"))

    def test_pdf_without_matching_sidecar_never_becomes_a_link(self):
        path = state.report_path(self.root, self.issue["date"], "en")
        path.parent.mkdir()
        path.write_bytes(PDF)
        self.assertFalse(state.report_is_available(self.root, self.issue, "en"))

    def test_default_renders_latest_issue_only_but_all_is_explicit(self):
        older = copy.deepcopy(self.issue)
        older["date"] = "2026-11-11"
        self.save_issue(older)
        self.generate()
        self.assertFalse(state.report_path(self.root, older["date"], "en").exists())
        all_result = self.generate(all_issues=True)
        self.assertEqual(len(all_result["generated"]), 2)
        self.assertEqual(len(all_result["skipped"]), 2)

    def test_environment_date_is_respected_and_all_overrides_it(self):
        with patch.object(reports, "ROOT", self.root), patch.dict(os.environ, {"ISSUE_DATE": "2026-11-11"}), patch.object(reports, "generate_reports") as generate:
            reports.main([])
            self.assertEqual(generate.call_args.kwargs["day"], "2026-11-11")
            reports.main(["--all"])
            self.assertIsNone(generate.call_args.kwargs["day"])
            self.assertTrue(generate.call_args.kwargs["all_issues"])
            reports.main(["--date", "2026-11-12", "--force"])
            self.assertEqual(generate.call_args.kwargs["day"], "2026-11-12")
            self.assertTrue(generate.call_args.kwargs["force"])

    def test_report_paths_validate_date_and_language(self):
        for day, lang in (("../outside", "en"), ("2026-11-12", "../outside"), ("2026-1-2", "en")):
            with self.assertRaises(ValueError):
                state.report_path(self.root, day, lang)

    def test_sidecar_does_not_modify_issue_fingerprint(self):
        before = state.issue_fingerprint(self.issue)
        self.generate()
        self.assertEqual(before, state.issue_fingerprint(self.issue))


if __name__ == "__main__":
    unittest.main()