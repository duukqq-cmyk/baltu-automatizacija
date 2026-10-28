"""Testi cirsmas novērtējuma (Mežvērte) PDF nolasīšanai un summēšanai.

Paraugi ir izdomāti (vārdi, kadastrs), bet skaitļi un izkārtojums atbilst
īstam Mežvērtes "CIRSMAS NOVĒRTĒJUMS" PDF, kā to nolasa pdfplumber.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cirsma.novertejums import (
    dublikati,
    fmt,
    kartot,
    kopsummas,
    parse_novertejums_pdf,
    parse_novertejums_teksts,
    rindas_vertibas,
)

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def _paraugs(nog: str, platiba: str, koki: str, sugas: list[str], kopa: str,
             kraja: str, cirsm_v: str, bio: str, bio_v: str, kop_v: str) -> str:
    return "\n".join([
        "CIRSMAS NOVĒRTĒJUMS",
        "Saimniecība: Paraugmeži Īpašnieks: Uzmērīja: Jānis Paraugs",
        "Novads: Ludzas novads Kadastrs: 68840099999 Uzmērīšanas datums: 09.10.2026.",
        f"Pagasts: Pasienes pagasts Kvartāls: 1 Platība: {platiba} ha",
        f"Virsmežniecība: Austrumu Nogabals: {nog} Pievešanas attālums: m",
        f"Mežniecība: Ludzas mežniecība A.Nogabals: 0 Koku skaits: {koki} gab. nogabalā",
        "Meža izmantošanas veids: Kailcirte - pēc caurmēra",
        "G.C.vērt.korekc.koef.: 1",
        "Apjomi (m3) Saglabājamie koki",
        "Kopā Īp.kval. Resnā Vidējā Tievā P.malka Kopā Ekol. Sēkl. Kritala Kopā Ekol. Sēkl. Kritala",
        *sugas,
        f"Kopā: {kopa}",
        f"Cirsmas krāja, m3: {kraja}",
        f"Cirsmas vērtība, €: {cirsm_v}",
        f"Biomasas apjoms, ber.m3: {bio}",
        f"Biomasas vērtība, €: {bio_v}",
        f"Vērtība kopā, €: {kop_v}",
        "Koksnes apjomi noteikti ar LLU MF 2015g algoritmu.",
        "Mežvērte: 12.26",
    ])


NOG5 = _paraugs(
    "5", "0,90", "631",
    ["Priede 246 244,10 207,79 0,00 66,70 85,18 22,90 33,01 3,10 33,21 210,89 0,99 5 5",
     "Egle 372 71,25 60,29 0,00 3,94 11,92 15,16 29,27 0,57 10,39 60,86 0,19",
     "Bērzs 13 7,10 6,16 0,00 2,12 0,86 0,80 2,38 0,00 0,94 6,16 0,55 3 3"],
    "631 322,45 274,24 0,00 72,76 97,96 38,86 64,66 3,67 44,54 277,91 0.51 8 8",
    "322,45", "14 946,86", "256,75", "1 026,99", "15 973,85",
)
NOG8 = _paraugs(
    "8", "2,30", "1 453",
    ["Priede 401 400,56 338,01 0,00 104,82 142,69 39,19 51,31 8,60 53,95 346,61 1,00 12 12",
     "Egle 959 300,07 261,76 0,00 51,22 73,47 47,92 89,15 0,88 37,43 262,64 0,31",
     "Bērzs 88 44,68 38,62 0,00 13,52 7,80 7,52 9,78 0,00 6,06 38,62 0,51 6 6",
     "Apse 4 5,96 3,37 0,00 2,77 0,26 0,34 0,00 1,88 0,71 5,25 1,49 1 1",
     "Baltalksnis 1 0,25 0,00 0,00 0,00 0,00 0,00 0,00 0,22 0,03 0,22 0,25"],
    "1 453 751,52 641,76 0,00 172,33 224,22 94,97 150,24 11,58 98,18 653,34 0.52 19 19",
    "751,52", "35 038,99", "699,30", "2 797,19", "37 836,18",
)


def test_galvene_un_summas():
    n = parse_novertejums_teksts(NOG8, "nog8.pdf")
    assert (n.saimnieciba, n.kadastrs, n.kvartals, n.nogabals) == ("Paraugmeži", "68840099999", "1", "8")
    assert n.nosaukums == "1. kv. 8. nog."
    assert n.ipasnieks == ""
    assert n.uzmerija == "Jānis Paraugs"
    assert n.datums == "09.10.2026"
    assert n.platiba == pytest.approx(2.30)
    assert n.koku_skaits == 1453
    assert n.vertiba_kopa == pytest.approx(37836.18)
    assert n.cirsmas_vertiba == pytest.approx(35038.99)
    assert n.biomasas_vertiba == pytest.approx(2797.19)
    assert n.bridinajumi == []


def test_kopa_rinda_ar_tukstosu_atstarpi():
    n = parse_novertejums_teksts(NOG8)
    assert n.kopa["skaits"] == 1453
    assert n.kopa["kraja"] == pytest.approx(751.52)
    assert n.kopa["pardosanai"] == pytest.approx(653.34)
    assert n.kopa["vid_koks"] == pytest.approx(0.52)
    assert n.saglabajamie == 19


def test_sugas():
    n = parse_novertejums_teksts(NOG8)
    assert [s["suga"] for s in n.sugas] == ["Priede", "Egle", "Bērzs", "Apse", "Baltalksnis"]
    assert n.sugas[0]["saglabajamie"] == 12
    assert n.sugas[1]["saglabajamie"] == 0
    assert sum(s["kraja"] for s in n.sugas) == pytest.approx(751.52)


def test_kopsummas_un_atvasinatie():
    ns = kartot([parse_novertejums_teksts(NOG8, "b"), parse_novertejums_teksts(NOG5, "a")])
    assert [n.nogabals for n in ns] == ["5", "8"]
    kop = kopsummas([rindas_vertibas(n) for n in ns])
    assert kop["nogabali"] == 2
    assert kop["platiba"] == pytest.approx(3.20)
    assert kop["vertiba_kopa"] == pytest.approx(53810.03)
    assert kop["cirsmas_kraja"] == pytest.approx(1073.97)
    assert kop["eur_ha"] == pytest.approx(53810.03 / 3.20)


def test_dublikati():
    a = parse_novertejums_teksts(NOG5, "a.pdf")
    b = parse_novertejums_teksts(NOG5, "b.pdf")
    assert len(dublikati([a, b])) == 1


def test_bojats_kopsavilkums_dod_bridinajumu():
    n = parse_novertejums_teksts(NOG5.replace("15 973,85", "15 000,00"))
    assert any("nesakrīt" in b for b in n.bridinajumi)


def test_cits_dokuments():
    with pytest.raises(ValueError):
        parse_novertejums_teksts("Nogabalu raksturojošie rādītāji ...")


def test_fmt():
    assert fmt(37836.18) == "37 836,18"
    assert fmt(None) == "—"
    assert fmt(3, 0) == "3"


def test_no_pdf(tmp_path):
    """Pilns ceļš caur pdfplumber uz ģenerētu PDF."""
    fpdf = pytest.importorskip("fpdf")
    if not os.path.exists(FONT):
        pytest.skip("Nav DejaVu fonta")
    pdf = fpdf.FPDF()
    pdf.add_page()
    pdf.add_font("DejaVu", "", FONT)
    pdf.set_font("DejaVu", size=7)
    for rinda in NOG8.splitlines():
        pdf.cell(0, 4, rinda, new_x="LMARGIN", new_y="NEXT")
    cels = tmp_path / "nog8.pdf"
    pdf.output(str(cels))

    n = parse_novertejums_pdf(str(cels))
    assert n.nosaukums == "1. kv. 8. nog."
    assert n.platiba == pytest.approx(2.30)
    assert n.vertiba_kopa == pytest.approx(37836.18)
    assert len(n.sugas) == 5
    assert n.bridinajumi == []
