"""Testi gabali.lv formātam (LaTeX PDF ar sugu krāju, aizsargjoslām u.c.)."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cirsma.formula import parse_formula, piejaukums
from cirsma.parser import parse_inventory_pdf
from cirsma.rules import atlasit_kailcirtes
from cirsma.sortiment import aprekinat, nogabala_apjoms

DIR = os.path.join(os.path.dirname(__file__), "..", "dati", "gabali")
SMECERENE = os.path.join(DIR, "36560010002_Nogabalu_dati_zv_2.pdf")
RUDINI = os.path.join(DIR, "42980010013_Nogabalu_dati_zv_4.pdf")
ZIGURI = os.path.join(DIR, "76560040108_Nogabalu_dati_zv.pdf")
VMD = os.path.join(os.path.dirname(__file__), "..", "dati",
                   "Nogabalu_raksturojosie_raditaji_64560020029.pdf")


def _ielade(cels):
    if not os.path.exists(cels):
        pytest.skip(f"Nav parauga {cels}")
    return parse_inventory_pdf(cels)


def _nog(inv, kv, nr):
    return next(n for n in inv.nogabali if n.kvartals == kv and n.nr == nr)


def test_formula_ar_piejaukumu():
    """Daļa pēc "+" = sugas zem 5%, koeficientu summā neietilpst."""
    dalas = parse_formula("7B2E1P75+M75")
    assert sum(d.ipatsvars for d in dalas) == pytest.approx(1.0)
    assert piejaukums("7B2E1P75+M75") == [("M", 75)]
    assert piejaukums("4B3E94 2P124 1Ba54 +Ba54M54") == [("Ba", 54), ("M", 54)]
    assert piejaukums("10B29") == []


def test_formata_atpazisana():
    assert _ielade(RUDINI).avots == "gabali.lv"
    assert _ielade(VMD).avots == "VMD"


def test_garumzimes_apvienotas():
    inv = _ielade(RUDINI)
    assert inv.ipasums == "Rudiņi"
    assert inv.zemes_vieniba == "42980010013"
    assert _nog(inv, "1", 4).meza_tips == "Slapjais vēris"
    assert _ielade(ZIGURI).ipasums == "Žīguri"


@pytest.mark.parametrize("cels, skaits", [(SMECERENE, 42), (RUDINI, 25), (ZIGURI, 12)])
def test_visi_nogabali_nolasiti(cels, skaits):
    inv = _ielade(cels)
    assert len(inv.nogabali) == skaits
    for n in inv.nogabali:
        if n.ir_mezaudze:
            assert sum(d.ipatsvars for d in parse_formula(n.formula)) == pytest.approx(1.0)


def test_nogabala_atributi():
    n = _nog(_ielade(RUDINI), "1", 1)
    assert (n.platiba_ha, n.formula, n.bonitate, n.vecums) == (0.5, "5E3B1A1P99", "I", 99)
    assert (n.kraja_m3_ha, n.kopeja_kraja_m3, n.skerslaukums) == (252.0, 126.0, 20.0)
    assert [(s.suga, s.kraja_m3) for s in n.sugu_kraja] == [
        ("E", 58), ("B", 34), ("A", 20), ("P", 12)]


def test_sugu_tabula_parlauzta_pa_lapam():
    """3.kv. 13. nogabala sugu tabula sākas 3. lapas apakšā un turpinās 4. lapā."""
    n = _nog(_ielade(RUDINI), "3", 13)
    assert [s.suga for s in n.sugu_kraja] == ["E", "E", "B", "A"]
    assert len(n.bojajumi) == 2


def test_ne_meza_nogabals():
    n = _nog(_ielade(RUDINI), "3", 3)
    assert not n.ir_mezaudze
    assert "Bebru" in n.zemes_veids


def test_apjoms_pec_sugu_tabulas():
    """Faktiskās sugu proporcijas, kopsumma = kopējā krāja."""
    n = _nog(_ielade(SMECERENE), "1", 1)  # 5Ba3B2E26; tabulā Ba51 B35 E15
    kopa, sugas, metode = nogabala_apjoms(n)
    assert metode == "sugu tabula"
    assert kopa == pytest.approx(103.09)
    assert sum(sugas.values()) == pytest.approx(103.09, abs=0.05)
    assert sugas["B"] == pytest.approx(103.09 * 35 / 101, abs=0.01)  # pēc formulas būtu 30.93


def test_atributi_un_karogi():
    inv = _ielade(SMECERENE)
    n = _nog(inv, "1", 1)
    assert n.plantacija
    assert n.planots == "Koku ciršana, Citas vienlaidus cirtes"
    assert n.aizsargjoslas and n.aizsargjoslas[0].startswith("40024000")
    v = next(v for v in atlasit_kailcirtes(inv.nogabali) if v.nogabals is n)
    teksts = " ".join(v.bridinajumi)
    assert "aizsargjosla" in teksts and "VMD plānotā darbība" in teksts and "Plantācijas" in teksts
    assert "plānojas caurmēra cirte" in (_nog(inv, "1", 22).komentari or "")


def test_vairaki_kvartali_netiek_jaukti():
    inv = _ielade(RUDINI)
    assert inv.vairaki_kvartali
    vertejumi = atlasit_kailcirtes(inv.nogabali)
    fin = aprekinat(vertejumi)
    cirt = [v for v in vertejumi if v.atlauta_kailcirte]
    assert len(fin.apjomi) == len(cirt)
    assert {a.nogabals.apzimejums for a in fin.apjomi} == {v.nogabals.apzimejums for v in cirt}
    assert fin.kopejais_m3 == pytest.approx(sum(a.kopejais_m3 for a in fin.apjomi), abs=0.1)


def test_pdf_papildu_info_zem_nogabala():
    """Teksts zem nogabala rindas PDF: inventarizācijas gads + apraksta rindas."""
    inv = _ielade(RUDINI)
    assert _nog(inv, "1", 2).pdf_apraksts == [
        "Nogabala meža inventarizācija veikta 2026. gadā.",
        "2. stāvs: 10E69",
        "Platību sadalījums: t.sk. mežs 0.41 ha, t.sk. ceļi 0.0 ha, t.sk. grāvji 0.01 ha",
    ]
    # Kvartāla/īpašuma kopsavilkuma rindas netiek pievienotas pēdējam nogabalam
    for n in inv.nogabali:
        assert sum(r.startswith("Platību sadalījums") for r in n.pdf_apraksts) == 1, n.apzimejums
    # VMD avotam šī informācija netiek rādīta
    assert _ielade(VMD).nogabali[0].pdf_apraksts == []
