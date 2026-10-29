"""Release recovery scenarios; no network or paid model calls."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import daily_release as release

DAY="2026-10-27"

class DailyReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        (self.root/"issues").mkdir()
        self.issue={"date":DAY,"screening_version":"test","generated_at":"2026-10-27T08:00:00-07:00","papers":[{"id":"one","summary":"verified notes"}]}
    def save(self,issue=None):
        (self.root/"issues"/(DAY+".json")).write_text(json.dumps(issue or self.issue),encoding="utf8")
    def save_stale_arxiv_audit(self):
        (self.root/"audits").mkdir(exist_ok=True)
        audit={"date":DAY,"arxiv_candidates":[{"decision":"no_new_announcement","announcement_date":"2026-10-26"}]}
        (self.root/"audits"/(DAY+".json")).write_text(json.dumps(audit),encoding="utf8")
    def test_stale_arxiv_snapshot_reopens_after_current_feed_arrives(self):
        self.save()
        self.save_stale_arxiv_audit()
        listing='<h3>Showing new listings for Tuesday, 27 October 2026</h3><h3>New submissions</h3><dt><a href="/abs/2610.12345">paper</a></dt>'
        with patch.object(release,"fetch",return_value=listing,create=True):
            result=self.plan(reader=lambda *args:copy.deepcopy(self.issue))
        self.assertEqual(result["mode"],"generate","A partial issue must not freeze out a later current announcement")
    def plan(self,event="schedule",reader=None,validator=None,force=False,announcement_reader=None):
        return release.plan_release(self.root,DAY,event,force,reader,validator or (lambda issue:None),announcement_reader)
    def test_unchanged_pending_feed_skips_paid_screening_but_is_not_final(self):
        self.save()
        self.save_stale_arxiv_audit()
        result=self.plan(reader=lambda *args:self.issue,announcement_reader=lambda:"2026-10-26")
        self.assertEqual(result["mode"],"current")
        self.assertEqual(result["pending_sources"],["arXiv"])
        self.assertNotEqual(result["reason"],"already_published_and_verified")
    def test_pending_feed_network_failure_does_not_report_complete(self):
        self.save()
        self.save_stale_arxiv_audit()
        def unavailable():raise TimeoutError("feed unavailable")
        with self.assertRaisesRegex(RuntimeError,"pending arXiv"):
            self.plan(reader=lambda *args:self.issue,announcement_reader=unavailable)
    def test_future_announcement_is_never_ingested_into_today(self):
        self.save()
        self.save_stale_arxiv_audit()
        result=self.plan(reader=lambda *args:self.issue,announcement_reader=lambda:"2026-10-28")
        self.assertEqual(result["mode"],"current")
        self.assertEqual(result["pending_sources"],["arXiv"])
    def test_current_source_snapshot_does_not_probe_or_repeat_screening(self):
        self.save()
        (self.root/"audits").mkdir()
        (self.root/"audits"/(DAY+".json")).write_text(json.dumps({"date":DAY,"arxiv_candidates":[{"decision":"candidate","announcement_date":DAY}]}),encoding="utf8")
        result=self.plan(reader=lambda *args:self.issue,announcement_reader=lambda:self.fail("Complete source snapshots need no probe"))
        self.assertEqual(result["reason"],"already_published_and_verified")
    def test_pending_source_check_still_resumes_missing_deployment(self):
        self.save()
        self.save_stale_arxiv_audit()
        def missing(*args):raise LookupError("no live issue")
        result=self.plan(reader=missing,announcement_reader=lambda:"2026-10-26")
        self.assertEqual(result["mode"],"deploy")
    def test_arxiv_error_page_with_date_is_not_treated_as_valid_listing(self):
        with patch.object(release,"fetch",return_value='<h3>Showing new listings for Tuesday, 27 October 2026</h3>'):
            with self.assertRaisesRegex(ValueError,"sections"):
                release.read_arxiv_announcement()
    def test_missing_today_generates(self):
        result=self.plan(reader=lambda *args:self.fail("No live call is needed before generation"))
        self.assertEqual(result["mode"],"generate")
    def test_invalid_saved_issue_generates(self):
        self.save()
        def invalid(issue):raise AssertionError("Old screening rules")
        self.assertEqual(self.plan(validator=invalid)["mode"],"generate")
    def test_wrong_date_file_generates(self):
        self.save({**self.issue,"date":"2026-10-26"})
        self.assertEqual(self.plan()["mode"],"generate")
    def test_saved_issue_and_stale_website_resume_deployment(self):
        self.save()
        self.assertEqual(self.plan(reader=lambda *args:{**self.issue,"date":"2026-10-26"})["mode"],"deploy")
    def test_identical_live_issue_skips_all_release_work(self):
        self.save()
        self.assertEqual(self.plan(reader=lambda *args:copy.deepcopy(self.issue))["mode"],"current")
    def test_same_ids_but_changed_notes_require_deployment(self):
        self.save()
        live=copy.deepcopy(self.issue);live["papers"][0]["summary"]="older notes"
        self.assertEqual(self.plan(reader=lambda *args:live)["mode"],"deploy")
    def test_unreadable_website_resumes_saved_issue_without_new_scoring(self):
        self.save()
        def unavailable(*args):raise TimeoutError("HTTP timeout")
        self.assertEqual(self.plan(reader=unavailable)["mode"],"deploy")
    def test_explicit_push_or_manual_rescreen_still_generate(self):
        self.save()
        reader=lambda *args:self.fail("Explicit regeneration must not be skipped")
        self.assertEqual(self.plan(event="push",reader=reader)["mode"],"generate")
        self.assertEqual(self.plan(event="workflow_dispatch",reader=reader)["mode"],"generate")
        self.assertEqual(self.plan(force=True,reader=reader)["mode"],"generate")
    def test_verification_retries_stale_content_and_succeeds(self):
        self.save()
        values=iter([{"date":DAY,"papers":[]} ,self.issue])
        with patch.object(release.time,"sleep") as sleep:
            result=release.verify_release(self.root,DAY,attempts=2,reader=lambda *args:next(values),validator=lambda issue:None)
        self.assertTrue(result["verified"]);sleep.assert_called_once()
    def test_verification_fails_instead_of_claiming_success(self):
        self.save()
        with self.assertRaises(RuntimeError):
            release.verify_release(self.root,DAY,attempts=1,reader=lambda *args:{"date":"2026-10-26"},validator=lambda issue:None)

if __name__=="__main__":
    unittest.main()

