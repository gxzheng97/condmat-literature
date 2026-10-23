"""Regression checks for broad relevance without hand-made title blacklists."""
import unittest
from relevance import fallback_score

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

if __name__=="__main__":
    unittest.main()
