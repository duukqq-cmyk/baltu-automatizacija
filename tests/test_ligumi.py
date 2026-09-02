"""Testi līgumu datu izvilkšanai (uz paraugu līgumiem)."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cirsma.ligumi import ekstrakcija_regex, epasta_kopsavilkums

MAPE = os.path.join(os.path.dirname(__file__), "..", "dati", "ligumi")
PIRKUMS = os.path.join(MAPE, "paraugs_pirkuma_ligums.pdf")
NOMA = os.path.join(MAPE, "paraugs_nomas_ligums.pdf")


@pytest.fixture(scope="module")
def pirkums():
    if not os.path.exists(PIRKUMS):
        pytest.skip("Nav parauga līguma")
    return ekstrakcija_regex(PIRKUMS, "pirkums.pdf")


@pytest.fixture(scope="module")
def noma():
    if not os.path.exists(NOMA):
        pytest.skip("Nav parauga līguma")
    return ekstrakcija_regex(NOMA, "noma.pdf")


def test_pirkuma_puses(pirkums):
    lomas = {p["loma"]: p for p in pirkums.puses}
    assert lomas["Pārdevējs"]["nosaukums"] == 'SIA "Piemēra Invest"'
    assert lomas["Pārdevējs"]["reg_nr"] == "40001234567"
    assert lomas["Pircējs"]["nosaukums"] == 'SIA "Demo Mežs"'


def test_pirkuma_summa_un_datums(pirkums):
    assert pirkums.summa_eur == 45000.0
    assert pirkums.summas_konteksts == "pirkuma maksa"
    assert pirkums.datums == "14.08.2026"


def test_pirkuma_ipasie_nosacijumi(pirkums):
    teksts = " ".join(pirkums.ipasie_nosacijumi).lower()
    assert "avans" in teksts
    assert "līgumsod" in teksts


def test_nomas_dati(noma):
    lomas = {p["loma"] for p in noma.puses}
    assert lomas == {"Iznomātājs", "Nomnieks"}
    assert noma.summa_eur == 1250.0
    assert "2028" in (noma.termins or "")


def test_validacija_tukss_pdf(tmp_path):
    from fpdf import FPDF
    tukss = tmp_path / "tukss.pdf"
    pdf = FPDF()
    pdf.add_page()
    pdf.output(str(tukss))
    d = ekstrakcija_regex(str(tukss), "tukss.pdf")
    assert any("maz teksta" in p for p in d.piezimes)


def test_kopsavilkums(pirkums, noma):
    teksts = epasta_kopsavilkums([pirkums, noma])
    assert "45 000.00 EUR" in teksts
    assert 'SIA "Testa Birojs"' in teksts
