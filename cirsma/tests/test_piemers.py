"""Testi pret darba devēja pamācības piemēru (NĪ Mežpurvi, 64560020029)."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cirsma.formula import parse_formula, valdosa_suga
from cirsma.parser import parse_inventory_pdf
from cirsma.rules import atlasit_kailcirtes
from cirsma.sortiment import aprekinat

PDF = os.environ.get(
    "INVENTARIZACIJAS_PDF",
    os.path.join(os.path.dirname(__file__), "..", "dati",
                 "Nogabalu_raksturojosie_raditaji_64560020029.pdf"),
)


def test_formulas_parsesana():
    dalas = parse_formula("4Ba3B37 2Ba26 1A47")
    assert [(d.suga, d.ipatsvars, d.vecums) for d in dalas] == [
        ("Ba", 0.4, 37), ("B", 0.3, 37), ("Ba", 0.2, 26), ("A", 0.1, 47),
    ]
    assert valdosa_suga("4Ba3B37 2Ba26 1A47") == "Ba"


def test_formulas_parsesana_bez_atstarpem():
    """PDF ekstrakcija reizēm pazaudē atstarpes — parsētājam jātiek galā."""
    dalas = parse_formula("4Ba3B372Ba26 1A47")
    assert sum(d.ipatsvars for d in dalas) == pytest.approx(1.0)
    assert [(d.suga, d.ipatsvars) for d in dalas] == [
        ("Ba", 0.4), ("B", 0.3), ("Ba", 0.2), ("A", 0.1),
    ]


@pytest.fixture(scope="module")
def rezultats():
    if not os.path.exists(PDF):
        pytest.skip("Nav pieejams parauga PDF")
    inv = parse_inventory_pdf(PDF)
    vertejumi = atlasit_kailcirtes(inv.nogabali)
    return inv, vertejumi, aprekinat(vertejumi)


def test_kailcirtes_atlase(rezultats):
    _, vertejumi, _ = rezultats
    cirt = sorted(v.nogabals.nr for v in vertejumi if v.atlauta_kailcirte)
    assert cirt == [1, 3, 4, 7, 8, 12]


def test_kopejais_apjoms(rezultats):
    *_, fin = rezultats
    assert fin.kopejais_m3 == pytest.approx(1038.94, abs=0.5)


def test_apjoms_pa_sugam(rezultats):
    *_, fin = rezultats
    gaiditais = {"E": 34, "B": 499, "A": 102, "Ba": 391, "Bl": 13}
    for suga, m3 in gaiditais.items():
        assert fin.pa_sugam_m3[suga] == pytest.approx(m3, abs=1), suga


def test_finansu_aprekins(rezultats):
    *_, fin = rezultats
    assert fin.ienemumi_kopa == pytest.approx(56322.14, abs=2)
    assert fin.max_iegades_summa == pytest.approx(28249, abs=2)
    assert fin.cena_eur_m3 == pytest.approx(27.19, abs=0.01)


def test_melnalksnis_kods_m():
    """VMD formulās melnalksnis mēdz būt ar kodu "M" (piem., "6B3A1M77")."""
    dalas = parse_formula("6B3A1M77")
    assert [(d.suga, d.ipatsvars) for d in dalas] == [("B", 0.6), ("A", 0.3), ("M", 0.1)]


def test_formulas_turpinajums_ar_salipusam_grupam():
    """Turpinājuma rinda ar vairākām salipušām grupām ("1E911E131" = "1E91 1E131")."""
    from cirsma.parser import _formulas_turpinajums
    assert _formulas_turpinajums("1E911E131") == "1E911E131"
    assert _formulas_turpinajums("1A47") == "1A47"
    assert _formulas_turpinajums("2.stāvs:E45") is None
    assert _formulas_turpinajums("Plantācijasaudze") is None
    dalas = parse_formula("4P1312P912B81 1E911E131")
    assert sum(d.ipatsvars for d in dalas) == pytest.approx(1.0)
    assert dalas[0].suga == "P" and dalas[0].vecums == 131
