"""Regression checks for broad relevance without hand-made title blacklists."""
import unittest
from relevance import fallback_score, has_substantive_cm_evidence

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

if __name__=="__main__":
    unittest.main()
