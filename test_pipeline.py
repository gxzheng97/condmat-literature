"""Regression tests for v1-only intake, semantic scope and dated regeneration."""
import contextlib
import copy
import datetime as dt
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

import relevance as r
import update_daily as u

ABSTRACT="This original study resolves quantum correlations and magnetic excitations in a solid-state material. "*3

def assessment(score=80, **changes):
    obj=dict(id="p",in_scope=True,soft_matter=False,quantum_materials=True,
             research_type="theory",score=score,feature_candidate=False,
             reason="Original magnetic quantum-materials physics",physics_advance="A new magnetic mechanism")
    obj.update(changes)
    return obj

def paper(**changes):
    obj=dict(id="p",type="arXiv",arxiv_id="2610.12345",arxiv_version=1,
        primary_category="cond-mat.str-el",categories=["cond-mat.str-el"],
        title="Quantum magnetism in a correlated material",abstract=ABSTRACT,
        announcement_date=dt.datetime.now(ZoneInfo("America/Los_Angeles")).date().isoformat(),
        url="https://arxiv.org/abs/2610.12345v1",topic="Magnetism",level="Brief")
    obj.update(changes)
    return obj

class IntakeTests(unittest.TestCase):
    def listing(self,day="26 October 2026"):
        return f"""<h3>Showing new listings for Monday, {day}</h3>
        <h3>New submissions (showing 4 of 4 entries)</h3>
        <dt><a href="/abs/2610.12341">a</a></dt>
        <dd>Abstract cites <a href="/abs/2501.99999">another paper</a></dd>
        <dt><a href="/abs/2610.12342">b</a></dt>
        <dt><a href="/abs/2610.12343">c</a></dt>
        <dt><a href="/abs/2610.12344">d</a></dt>
        <h3>Cross submissions (showing 1 of 1 entries)</h3>
        <dt><a href="/abs/2610.12345">e</a></dt>
        <h3>Replacement submissions (showing 1 of 1 entries)</h3>
        <dt><a href="/abs/2501.12346">f</a></dt>"""
    def feed(self):
        entries=[]
        for number,version,category in [(1,1,"cond-mat.str-el"),(2,2,"cond-mat.str-el"),
                (3,1,"cond-mat.soft"),(4,None,"cond-mat.str-el"),(5,1,"cond-mat.mes-hall")]:
            pid=f"2610.1234{number}"+(f"v{version}" if version else "")
            entries.append(f"""<entry><id>https://arxiv.org/abs/{pid}</id>
            <title>Original material physics {number}</title><summary>{ABSTRACT}</summary>
            <published>2026-10-23T12:00:00Z</published><updated>2026-10-23T12:00:00Z</updated>
            <category term="{category}"/><x:primary_category term="{category}"/></entry>""")
        return '<feed xmlns="http://www.w3.org/2005/Atom" xmlns:x="http://arxiv.org/schemas/atom">'+"".join(entries)+"</feed>"
    def test_sections_versions_and_soft_category(self):
        audit=[]
        with patch.object(u,"fetch",side_effect=[self.listing(),self.feed()]) as fetch:
            found=u.arxiv(dt.datetime(2026,10,26),audit)
        self.assertEqual([p["arxiv_id"] for p in found],["2610.12341","2610.12345"])
        api_url=fetch.call_args_list[1].args[0]
        self.assertNotIn("2501.12346",api_url)
        self.assertNotIn("2501.99999",api_url)
        self.assertEqual({a["decision"] for a in audit},{"replacement_section","not_first_version","soft_matter_category","candidate"})
        self.assertEqual(found[0]["arxiv_version"],1)
        self.assertEqual(found[0]["announcement_date"],"2026-10-26")
        self.assertTrue(found[0]["submitted_at"])
        self.assertTrue(found[0]["url"].endswith("v1"))
    def test_old_announcement_is_not_republished(self):
        with patch.object(u,"fetch",return_value=self.listing("23 October 2026")) as fetch:
            self.assertEqual(u.arxiv(dt.datetime(2026,10,26)),[])
            self.assertEqual(fetch.call_count,1)
    def test_unparseable_date_fails(self):
        with patch.object(u,"fetch",return_value="<html>unavailable</html>"):
            with self.assertRaises(ValueError):u.arxiv(dt.datetime(2026,10,26))
    def test_api_omission_fails(self):
        with patch.object(u,"fetch",side_effect=[self.listing(),'<feed xmlns="http://www.w3.org/2005/Atom"/>']):
            with self.assertRaises(RuntimeError):u.arxiv(dt.datetime(2026,10,26))
    def test_journal_no_keyword_gate_and_abstract_first(self):
        title="Anderson localization in disordered two-dimensional conductors"
        def rows(*args):
            yield {"type":"journal-article","DOI":"10.1038/example","title":[title]}
        audit=[]
        with patch.object(u,"ISSN",{"Nature":"0028-0836"}),patch.object(u,"crossref_records",side_effect=rows),patch.object(u,"metadata_abstract",return_value=ABSTRACT) as metadata:
            found=u.journals(dt.datetime(2026,10,26),audit)
        metadata.assert_called_once_with("10.1038/example")
        self.assertEqual(len(found),1)
        self.assertEqual(found[0]["abstract"],ABSTRACT)
    def test_missing_abstract_deferred_then_retried(self):
        pending=[];audit=[]
        row={"type":"journal-article","DOI":"10.1038/example","title":["Anderson localization"]}
        with patch.object(u,"ISSN",{"Nature":"0028-0836"}),patch.object(u,"crossref_records",return_value=iter([row])),patch.object(u,"metadata_abstract",return_value=""),patch.object(u,"publisher_abstract",return_value=""):
            self.assertEqual(u.journals(dt.datetime(2026,10,26),audit,pending=pending),[])
        self.assertEqual(audit[0]["decision"],"pending_abstract")
        self.assertEqual(len(pending),1)
        with patch.object(u,"ISSN",{"Nature":"0028-0836"}),patch.object(u,"crossref_records",return_value=iter([])),patch.object(u,"metadata_abstract",return_value=ABSTRACT):
            self.assertEqual(len(u.journals(dt.datetime(2026,10,27),pending=pending)),1)

    def test_matching_preprint_requires_correct_doi_or_exact_title(self):
        def feed(doi,title):
            return '<feed xmlns="http://www.w3.org/2005/Atom" xmlns:x="http://arxiv.org/schemas/atom"><entry><id>https://arxiv.org/abs/2601.12345v2</id><title>'+title+'</title><x:doi>'+doi+'</x:doi><summary>'+ABSTRACT+'</summary></entry></feed>'
        with patch.object(u,"fetch",return_value=feed("10.1103/wrong","Exact paper title")):
            self.assertEqual(u.arxiv_metadata_abstract("10.1103/right","Exact paper title"),("",""))
        with patch.object(u,"fetch",return_value=feed("","Exact paper title")):
            abstract,source=u.arxiv_metadata_abstract("10.1103/right","Exact paper title")
            self.assertEqual(abstract,ABSTRACT.strip())
            self.assertTrue(source.endswith("v2"))  # Journal metadata, not arXiv intake.
        with patch.object(u,"fetch",return_value=feed("","A different paper")):
            self.assertEqual(u.arxiv_metadata_abstract("10.1103/right","Exact paper title"),("",""))

class ScopeTests(unittest.TestCase):
    def run_screen(self,p,ai):
        with patch.dict(os.environ,{"OPENAI_API_KEY":"test"}),patch.object(r,"_ai_batch",return_value={p["id"]:ai}),patch.object(r,"_ai_shortlist",side_effect=lambda ps,*a,**kw:([p["id"] for p in ps],[])):
            return r.screen([p])[0]
    def test_arxiv_threshold(self):
        self.assertFalse(self.run_screen(paper(),assessment(69)))
        self.assertTrue(self.run_screen(paper(),assessment(70)))
    def test_arxiv_requires_quantum_materials(self):
        self.assertFalse(self.run_screen(paper(),assessment(95,quantum_materials=False)))
    def test_theory_preserved(self):
        self.assertTrue(self.run_screen(paper(),assessment(80,research_type="theory")))
    def test_semantic_soft_matter_rejected(self):
        self.assertFalse(self.run_screen(paper(),assessment(99,soft_matter=True)))
    def test_bad_metadata_cannot_bypass_scope(self):
        for changes in ({"arxiv_version":2},{"arxiv_version":None},{"primary_category":"cond-mat.soft"}):
            self.assertFalse(self.run_screen(paper(**changes),assessment(99)))
    def test_journal_threshold_unchanged(self):
        self.assertTrue(self.run_screen(paper(type="Journal",journal="Nature"),assessment(60,quantum_materials=False)))
    def test_global_empty_stays_empty(self):
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self):
                return json.dumps({"status":"completed","output":[{"content":[{"type":"output_text","text":json.dumps({"selected_ids":[],"featured_ids":[]})}]}]}).encode()
        with patch.object(r.urllib.request,"urlopen",return_value=Response()):
            self.assertEqual(r._ai_shortlist([paper(relevance_score=80)],"test"),([],[]))
    def test_cached_assessment_avoids_paid_batch(self):
        p=paper()
        with patch.dict(os.environ,{"OPENAI_API_KEY":"test"}),patch.object(r,"_ai_batch") as batch,patch.object(r,"_ai_shortlist",return_value=(["p"],[])):
            kept,stats=r.screen([p],cached_assessments={"p":assessment()})
        batch.assert_not_called()
        self.assertEqual(stats["ai_cached"],1)
        self.assertEqual(len(kept),1)

    def test_parallel_batches_preserve_all_individual_assessments(self):
        papers=[paper(id="p"+str(i)) for i in range(12)]
        def assess(ps,key):
            return {p["id"]:assessment(id=p["id"]) for p in ps}
        with patch.dict(os.environ,{"OPENAI_API_KEY":"test"}),patch.object(r,"_ai_batch",side_effect=assess) as batch,patch.object(r,"_ai_shortlist",side_effect=lambda ps,*a,**kw:([p["id"] for p in ps],[])):
            kept,stats=r.screen(papers)
        self.assertEqual([p["id"] for p in kept],[p["id"] for p in papers])
        self.assertEqual(sorted(len(c.args[0]) for c in batch.call_args_list),[2,5,5])
        self.assertEqual(stats["ai_assessed"],12)
        self.assertEqual(stats["ai_unscored"],0)

class RegenerationTests(unittest.TestCase):
    def successful_sources(self,today,audit,skip,sources,pending):
        sources.extend({"source":name,"status":"ok","fetched":0} for name in u.ISSN)
        return []
    def screen(self,ps,**kwargs):
        for p in ps:
            p.update(ai_in_scope=True,soft_matter=False,quantum_materials=True,
                research_type="theory",relevance_score=80,feature_candidate=True,
                screening_decision="selected",_ai_assessment=assessment())
        return ps,dict(scanned=len(ps),selected=len(ps),ai_assessed=len(ps),
            ai_unscored=0,global_editorial=True)
    def test_existing_issue_rebuilt_and_force_rescreens(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            root=Path(folder);(root/"issues").mkdir()
            day=dt.datetime.now(ZoneInfo("America/Los_Angeles")).date().isoformat()
            dest=root/"issues"/(day+".json");dest.write_text('{"stale":true}',encoding="utf8")
            with patch.object(u,"ROOT",root),patch.object(u,"arxiv",return_value=[paper()]),patch.object(u,"journals",side_effect=self.successful_sources),patch.object(u,"screen",side_effect=self.screen) as screen,patch.object(u,"enrich"):
                first=u.main([])
                self.assertEqual(first["screening_version"],u.SCREENING_VERSION)
                self.assertTrue(dest.exists())
                u.main([])
                self.assertIn("p",screen.call_args.kwargs["cached_assessments"])
                u.main(["--rescreen"])
                self.assertEqual(screen.call_args.kwargs["cached_assessments"],{})
            self.assertTrue((root/"audits"/(day+".json")).exists())
            self.assertNotIn("_ai_assessment",json.loads(dest.read_text())["papers"][0])
    def test_failed_harvest_preserves_existing_issue(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            root=Path(folder);(root/"issues").mkdir()
            day=dt.datetime.now(ZoneInfo("America/Los_Angeles")).date().isoformat()
            dest=root/"issues"/(day+".json");dest.write_text('{"original":true}',encoding="utf8")
            with patch.object(u,"ROOT",root),patch.object(u,"arxiv",side_effect=RuntimeError("source unavailable")),patch.object(u,"journals",side_effect=self.successful_sources),patch.object(u,"screen") as screen:
                with self.assertRaises(RuntimeError):u.main([])
                screen.assert_not_called()
            self.assertEqual(json.loads(dest.read_text()),{"original":True})
    def test_validation_rejects_revisions(self):
        p=paper(arxiv_version=2,ai_in_scope=True,soft_matter=False,quantum_materials=True,relevance_score=99)
        issue=dict(date=p["announcement_date"],screening_version=u.SCREENING_VERSION,
            sources_complete=True,papers=[p],stats=dict(global_editorial=True,scanned=1,ai_assessed=1,ai_unscored=0))
        with self.assertRaises(AssertionError):u.validate_issue(issue)

if __name__=="__main__":
    unittest.main()


