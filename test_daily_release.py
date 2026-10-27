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
    def plan(self,event="schedule",reader=None,validator=None,force=False):
        return release.plan_release(self.root,DAY,event,force,reader,validator or (lambda issue:None))
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

