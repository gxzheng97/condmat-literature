"""Intake-window boundaries, delayed sources and previous-day publication."""
import contextlib
import copy
import datetime as dt
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

import intake_window as w
import update_daily as u
import test_pipeline as fixtures

def empty_listing(day):
    d=dt.date.fromisoformat(day)
    label=d.strftime("%a, %d %b %Y")
    return f"<h1>Catchup results for Condensed Matter on {label}</h1><p>Total of 0 entries for {label}</p><p>No updates for {label}.</p>"

class WindowTests(unittest.TestCase):
    def test_october_30_issue_uses_october_29_journal_publications(self):
        window=w.issue_window("2026-10-30")
        self.assertEqual(window["journal_publication_date"],"2026-10-29")
        self.assertEqual(window["arxiv_start"],"2026-10-29T13:00:00+00:00")
        self.assertEqual(window["arxiv_end"],"2026-10-30T13:00:00+00:00")

    def test_window_is_exactly_24_hours_across_both_dst_changes(self):
        for day in ("2026-03-08","2026-11-01"):
            window=w.issue_window(day)
            self.assertEqual(dt.datetime.fromisoformat(window["arxiv_end"])-dt.datetime.fromisoformat(window["arxiv_start"]),dt.timedelta(hours=24))
            self.assertEqual(dt.datetime.fromisoformat(window["arxiv_end"]).astimezone(ZoneInfo(w.TIMEZONE)).hour,6)

    def test_journal_calendar_day_crosses_month_and_year(self):
        self.assertEqual(w.issue_window("2027-01-01")["journal_publication_date"],"2026-12-31")

    def test_only_the_announcement_inside_the_window_is_eligible(self):
        window=w.issue_window("2026-10-30")
        self.assertFalse(w.announcement_in_window("2026-10-29",window))
        self.assertTrue(w.announcement_in_window("2026-10-30",window))
        self.assertFalse(w.announcement_in_window("2026-10-31",window))

    def test_winter_release_uses_eastern_daylight_saving_rules(self):
        self.assertEqual(w.announcement_time("2026-10-30").isoformat(),"2026-10-30T00:00:00+00:00")
        self.assertEqual(w.announcement_time("2026-11-03").isoformat(),"2026-11-03T01:00:00+00:00")

    def test_maintenance_empty_dated_batch_is_successful_zero(self):
        audit=[]
        with patch.object(u,"fetch",return_value=empty_listing("2026-10-29")) as fetch:
            self.assertEqual(u.arxiv(dt.datetime(2026,10,29,6),audit),[])
        self.assertEqual(fetch.call_args.args[0],"https://arxiv.org/catchup/cond-mat/2026-10-29")
        self.assertEqual(audit[0]["decision"],"no_announcements_in_window")

    def test_error_page_cannot_be_misreported_as_no_new_papers(self):
        bad='<h1>Catchup results for Condensed Matter on Thu, 29 Oct 2026</h1><p>Temporarily unavailable</p>'
        with patch.object(u,"fetch",return_value=bad):
            with self.assertRaisesRegex(ValueError,"sections"):
                u.arxiv(dt.datetime(2026,10,29,6))

    def test_eight_am_retry_requests_the_same_dated_batch(self):
        with patch.object(u,"fetch",return_value=empty_listing("2026-10-29")) as fetch:
            u.arxiv(dt.datetime(2026,10,29,6))
            u.arxiv(dt.datetime(2026,10,29,8))
        self.assertEqual(fetch.call_args_list[0],fetch.call_args_list[1])

    def test_old_v1_cross_listing_is_not_a_first_announcement(self):
        sample=fixtures.IntakeTests()
        # Original category has other new articles, but this ID is only cross-listed.
        with patch.object(u,"fetch",side_effect=[sample.listing(),sample.feed(),sample.listing()]):
            audit=[];found=u.arxiv(dt.datetime(2026,10,26,6),audit)
        self.assertEqual([p["arxiv_id"] for p in found],["2610.12341"])
        self.assertEqual(next(x["decision"] for x in audit if x.get("arxiv_id")=="2610.12345"),"not_first_announcement")

    def issue(self,publication_day):
        p=fixtures.FormalPublicationTests().journal(publication_date=publication_day,
            ai_in_scope=True,soft_matter=False,relevance_score=80,abstract_status="available")
        return {"date":"2026-10-30","intake_window":w.issue_window("2026-10-30"),
            "screening_version":u.SCREENING_VERSION,"sources_complete":True,"papers":[p],
            "stats":{"global_editorial":True,"scanned":1,"ai_assessed":1,"ai_unscored":0}}

    def test_release_validation_accepts_previous_day_formal_research(self):
        u.validate_issue(self.issue("2026-10-29"))

    def test_release_validation_rejects_current_day_and_older_journals(self):
        for day in ("2026-10-28","2026-10-30"):
            with self.assertRaisesRegex(AssertionError,"previous-day"):
                u.validate_issue(self.issue(day))

    def test_release_rejects_relabelled_window(self):
        issue=self.issue("2026-10-29")
        issue["intake_window"]["arxiv_end"]="2026-10-30T15:00:00+00:00"
        with self.assertRaisesRegex(AssertionError,"intake window"):
            u.validate_issue(issue)

    def test_main_passes_previous_publication_day_and_fixed_arxiv_cutoff(self):
        actual_datetime=dt.datetime
        class Morning(actual_datetime):
            @classmethod
            def now(cls,tz=None):
                value=cls(2026,10,30,8,tzinfo=ZoneInfo("America/Los_Angeles"))
                return value.astimezone(tz) if tz else value.replace(tzinfo=None)
        recorded={}
        def arxiv(cutoff,audit):
            recorded["arxiv"]=cutoff
            return []
        def journals(day,audit,skip,sources,pending):
            recorded["journals"]=day
            sources.extend({"source":name,"status":"ok","fetched":0} for name in u.ISSN)
            return []
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            root=Path(directory)
            with patch.object(u,"ROOT",root),patch.object(u.dt,"datetime",Morning),patch.object(u,"arxiv",side_effect=arxiv),patch.object(u,"journals",side_effect=journals),patch.object(u,"screen",side_effect=fixtures.RegenerationTests().screen),patch.object(u,"enrich"),contextlib.redirect_stdout(io.StringIO()):
                issue=u.main([])
            saved=json.loads((root/"audits"/"2026-10-30.json").read_text())
        self.assertEqual(recorded["arxiv"].hour,6)
        self.assertEqual(recorded["journals"].date().isoformat(),"2026-10-29")
        self.assertEqual(issue["intake_window"],saved["intake_window"])
        self.assertEqual(issue["date"],"2026-10-30")

    def test_existing_october_29_issue_is_preserved_under_its_original_policy(self):
        issue=self.issue("2026-10-29")
        issue["date"]="2026-10-29"
        issue["screening_version"]="quantum-materials-v1-formal-research-v4"
        issue.pop("intake_window")
        u.validate_issue(issue)

    def test_october_30_issue_cannot_reuse_the_old_same_day_policy(self):
        issue=self.issue("2026-10-30")
        issue["screening_version"]="quantum-materials-v1-formal-research-v4"
        with self.assertRaisesRegex(AssertionError,"outdated"):
            u.validate_issue(issue)

    def test_official_backup_feed_recovers_final_citation_from_stale_recent_feed(self):
        def feed(day,doi):
            return f'''<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns="http://purl.org/rss/1.0/" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:p="http://prismstandard.org/namespaces/basic/2.0/">
            <item><title>Quantum material</title><description>Published {day}</description><dc:type>article</dc:type><p:doi>{doi}</p:doi><p:volume>137</p:volume><p:startingPage>186302</p:startingPage><p:publicationDate>{day}</p:publicationDate></item></rdf:RDF>'''
        diagnostic={}
        with patch.object(u,"fetch",side_effect=[feed("2026-10-28","10.1103/older"),feed("2026-10-29","10.1103/final")]):
            result=u.aps_publications("PRL","2026-10-29",diagnostic)
        self.assertIn("10.1103/final",result)
        self.assertEqual(diagnostic["latest_formal_publication_date"],"2026-10-29")
        self.assertEqual(len(diagnostic["feed_urls"]),2)

if __name__=="__main__":
    unittest.main()
