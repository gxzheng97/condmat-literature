"""Regression checks for broad relevance without hand-made title blacklists."""
import unittest
from relevance import fallback_score, has_substantive_cm_evidence
from update_daily import journal_candidate_scope, crossref_records, journals, _PublisherAbstractParser, _openalex_abstract
from unittest.mock import patch
import datetime as dt
import json
import urllib.parse

def record(title, abstract=""):
    return {"title":title, "abstract":abstract}

class EditorialScreenTests(unittest.TestCase):
    def check(self, title, abstract, expected):
        value=fallback_score(record(title, abstract))
        self.assertEqual(value>=2.7,expected,msg=f"{value}: {title}")

    def test_physical_discoveries(self):
        self.check(
            "Spin order and excitations in the collinear kagome antiferromagnet Y0.5Fe3Sn3",
            "Elastic and inelastic neutron scattering determine magnetic order, anisotropic spin excitations and anomalous Hall response.",True)
        self.check(
            "Valence-Driven Structural Transformation and Phase Coexistence in Chemically Substituted EuPd2Si2",
            "Valence transition revealed by synchrotron diffraction and structural phase coexistence.",True)
        self.check(
            "Anisotropic thermoelectric transport in the Sr2RuO4-Ru eutectic system",
            "Seebeck and Nernst measurements of quantum-material crystals.",True)
        self.check(
            "Ferroelastic Reversal Magnon Thermal Hall Effect in a Fully Compensated Ferrimagnet",
            "Thermal Hall measurements and magnon band topology.",True)
        self.check(
            "Extreme competition between stripes and superconductivity in the hole-doped Hubbard model",
            "Correlated electrons and a model for high temperature superconductors.",True)
        self.check(
            "Field-induced metal-insulator transition, Chern insulators, and topological semimetals in the magnetic semiconductor GdGaI",
            "Electronic transport and magnetic field phase diagram.",True)
    def test_not_automatically_relevant_just_because_in_a_famous_journal(self):
        self.check(
            "High-numerical-aperture extreme ultraviolet flat optics via a cascaded momentum relay",
            "Flat optics, lithographic projection, numerical apertures, and diffraction efficiency.",False)
        self.check(
            "Aluminum Scandium Nitride (AlScN) for Advanced Devices: Physical Mechanisms and Emerging Applications",
            "This review surveys fabrication, integration, piezoelectric devices, optoelectronic memories and radio frequency circuits.",False)
        self.check(
            "Beating the break-even point with autonomous quantum error correction",
            "Quantum circuit error correction with superconducting qubits and long-lived logical memories.",False)
        self.check(
            "How good are universal MLIPs for alloys? A benchmark is only as trustworthy as its controls",
            "Assessment of computational metrics for atomic machine-learning interatomic potentials.",False)

class IndependentScopeTests(unittest.TestCase):
    def test_condensed_matter_discoveries_pass(self):
        for title,abstract in [
            ("Magnetic order, magnons, and crystal fields in van der Waals CeSiI",""),
            ("Optical switching of two-dimensional charge-density-wave chirality",""),
            ("High-resolution search for thermal Hall in La2CuO4",""),
            ("Kondo screening and random-singlet formation in disordered systems",""),
            ("Selective strain tuning of multiferroic dynamics in BiFeO3",""),
            ("Unexpected synthesis of a new electronic phase",
             "Single crystal structure and strongly correlated electrons reveal a new quantum material."),
        ]:
            self.assertTrue(has_substantive_cm_evidence(record(title,abstract)),title)
    def test_non_condensed_matter_does_not_pass(self):
        for title,abstract in [
            ("Ultracold atom quantum simulation of the Hubbard model",
             "Atomic gases in an optical lattice reproduce magnetic correlations."),
            ("Topological photonic crystal for robust optical guiding",
             "A topological photonic bandgap supports an edge mode."),
            ("Superconducting quantum computing with error correction",
             "Scalable superconducting circuits demonstrate a quantum algorithm."),
            ("Magnetic structure of an astrophysical plasma jet",
             "Magnetized plasma turbulence is observed in an astrophysical jet."),
            ("A functional two-pore-domain K+ channel from a large DNA virus",
             "Virology reveals cellular transport pathways for viral proteins."),
            ("Supercoiling Drives DNA-Protein Co-Condensation","Protein condensation."),
            ("Local growth laws determine global shape of molluscan shells","Shell growth physics."),
            ("Entropy-production cost limits hierarchical decision-making in homing pigeon flocks","Biological flock decision-making."),
            ("High-numerical-aperture extreme ultraviolet flat optics","Two cascaded lenses increase optical resolution."),
            ("A new quantum feedback algorithm for error correction","Logical qubit fidelity increases."),
        ]:
            self.assertFalse(has_substantive_cm_evidence(record(title,abstract)),title)

class JournalRecallTests(unittest.TestCase):
    def test_openalex_inverted_index_recovery(self):
        words="The magnetic order reveals unexpectedly large thermal Hall response in this correlated material and provides a microscopic explanation of the signal".split()
        inverted={}
        for i,w in enumerate(words*3):inverted.setdefault(w,[]).append(i)
        self.assertIn("thermal Hall",_openalex_abstract(inverted))
        self.assertEqual(_openalex_abstract({}),"")

    def test_publisher_metadata_abstract_recovery(self):
        parser=_PublisherAbstractParser()
        parser.feed('<html><head><meta name="citation_abstract" content="' +
                    'This is an original condensed-matter study of flat bands. '*5 +
                    '"></head></html>')
        self.assertIn("condensed-matter study",parser.extract())

    def test_theory_and_flat_band_not_killed_by_premature_keyword_gate(self):
        self.assertTrue(journal_candidate_scope("PRX",
            "Toward Complete Characterization of Topological Insulators and Superconductors"))
        self.assertTrue(journal_candidate_scope("PRL",
            "Cluster-Decorated Lieb Lattice: A Convenient Platform for Tuning Flat-Band Energy"))
        self.assertTrue(journal_candidate_scope("Nature Materials",
            "Strain-driven magnetostructural relaxation revealed in Heusler alloys"))
        self.assertTrue(journal_candidate_scope("Nature Materials",
            "High numerical aperture flat optics for lithography"))
        self.assertTrue(journal_candidate_scope("PRL",
            "Quantum error correction on a superconducting processor"))

    def test_cursor_pagination_reads_all_results(self):
        calls=[]
        def fake_fetch(url):
            q=urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
            calls.append(q)
            return json.dumps({"message":{
                "items":[{"DOI":"a"},{"DOI":"b"}] if len(calls)==1 else [{"DOI":"c"}],
                "next-cursor":"page2"}})
        with patch("update_daily.fetch", side_effect=fake_fetch):
            found=list(crossref_records("0031-9007","2026-10-24","2026-10-25",page_size=2))
        self.assertEqual([x["DOI"] for x in found],["a","b","c"])
        self.assertEqual(len(calls),2)
        self.assertEqual(calls[0]["cursor"],["*"])
        self.assertEqual(calls[1]["cursor"],["page2"])
        self.assertEqual(calls[0]["rows"],["2"])

    def test_archive_skips_old_journal_before_abstract_requests(self):
        original="10.1103/rm6q-k54p"
        def fake_records(issn,first,last):
            if issn=="0031-9007":
                yield {"type":"journal-article","DOI":original,
                       "title":["Cluster-Decorated Lieb Lattice: Tuning Flat Band"],
                       "abstract":"This original condensed-matter study resolves the magnetic mechanism and its thermal Hall response in a solid-state quantum material. The abstract contains sufficient scientific information for assessment."}
        pid="doi-"+original.replace("/","-").replace(".","-")
        audit=[]
        with patch("update_daily.crossref_records",side_effect=fake_records), \
             patch("update_daily.aps_publications",return_value={}), \
             patch("update_daily.metadata_abstract") as metadata:
            found=journals(dt.datetime(2026,10,25),audit,{pid:"previous_issue"})
        self.assertFalse(found)
        metadata.assert_not_called()
        self.assertEqual(audit[0]["decision"],"previous_issue")

    def test_today_only_publication_window_and_per_journal_audit(self):
        seen=[]
        def fake_records(issn,first,last):
            seen.append((issn,first,last))
            if issn=="0031-9007":
                yield {"type":"journal-article",
                       "DOI":"10.1103/formal-example",
                       "title":["Strain-driven magnetostructural relaxation revealed in Heusler alloys"],
                       "abstract":"This original condensed-matter study resolves the magnetic mechanism and its thermal Hall response in a solid-state quantum material. The abstract contains sufficient scientific information for assessment."}
        audit=[]
        formal={"10.1103/formal-example":{"article_kind":"Letter","publication_status":"published",
            "publication_date":"2026-10-25","publication_evidence":{"source":"APS RSS","volume":"137","article_number":"186001"}}}
        with patch("update_daily.crossref_records",side_effect=fake_records), \
             patch("update_daily.aps_publications",side_effect=lambda name:formal if name=="PRL" else {}):
            found=journals(dt.datetime(2026,10,25),audit)
        self.assertEqual(len(found),1)
        self.assertEqual(len(seen),9)
        self.assertTrue(all(x[1]=="2026-10-25" and x[2]=="2026-10-25" for x in seen))
        self.assertEqual(audit[0]["decision"],"candidate")

if __name__=="__main__":
    unittest.main()


