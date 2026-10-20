"""Testi monday leadu atskaitēm: lead definīcija, mērķa kritēriji, metriki, API klients."""
import json
import os
import sys
from datetime import date

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from atskaites.demo import demo_boardi
from atskaites.eksports import excel_atskaite
from atskaites.metrikas import aprekinat, menesis, merka, proaktivs, teksta_kopsavilkums
from atskaites.modelis import (
    auto_karte, norm_kadastrs, norm_telefons, parse_skaitlis, sagatavot,
)
from atskaites.monday import Boards, Kolonna, MondayKlients, MondayKluda, Rinda

KOL = [Kolonna("c1", "Lead Datums", "date"), Kolonna("c2", "Tel.Nr", "phone"),
       Kolonna("c3", "Īpašuma kad. Nr.", "text"), Kolonna("c4", "Zemes vienības kad. apz.", "text"),
       Kolonna("c5", "Meža platība, ha", "numbers"), Kolonna("c6", "1. piegājiena apjoms, m³", "numbers"),
       Kolonna("c7", "Pied. veids", "status"), Kolonna("c8", "Lauks. zeme, %", "numbers"),
       Kolonna("c9", "Kailcirte sausie, ha", "numbers"), Kolonna("c10", "Aktualiz. dat.", "last_updated")]


def _boards(rindas: list[tuple[str, dict]], grupa="Jauns") -> Boards:
    b = Boards("1", "Agents_A", KOL, [], grupas=[grupa])
    for i, (nos, v) in enumerate(rindas):
        b.rindas.append(Rinda("1", "Agents_A", str(i), nos, grupa, None, v))
    return b


# --- Lead definīcija (CEO e-pasts 15.10.2026) -------------------------------
def test_viens_ipasums_vairakas_zemes_vienibas_ir_viens_lead():
    b = _boards([(f"Pētera mežs {i}", {"Lead Datums": "2026-10-05", "Tel.Nr": "28000000",
                                        "Īpašuma kad. Nr.": "112233445566",
                                        "Zemes vienības kad. apz.": zv, "Meža platība, ha": ha,
                                        "1. piegājiena apjoms, m³": m3})
                 for i, (zv, ha, m3) in enumerate([("112233445566", "3", "300"),
                                                   ("112233445567", "2.5", "250"),
                                                   ("112233445568", "1", "200")])])
    d = sagatavot([b])
    assert len(d.rindas) == 3
    assert len(d.leadi) == 1
    lead = d.leadi[0]
    assert lead.get("meza_ha") == pytest.approx(6.5)        # platības summa
    assert lead.get("m3_1_piegajiens") == pytest.approx(750)


def test_viens_ipasnieks_divi_ipasumi_ir_divi_leadi():
    b = _boards([("A", {"Lead Datums": "2026-10-05", "Tel.Nr": "28000000", "Īpašuma kad. Nr.": "11111111111"}),
                 ("B", {"Lead Datums": "2026-10-05", "Tel.Nr": "28000000", "Īpašuma kad. Nr.": "22222222222"})])
    assert len(sagatavot([b]).leadi) == 2


def test_viens_ipasums_divi_ipasnieki_ir_viens_lead():
    b = _boards([("A", {"Lead Datums": "2026-10-05", "Tel.Nr": "28000000", "Īpašuma kad. Nr.": "11111111111"}),
                 ("B", {"Lead Datums": "2026-10-06", "Tel.Nr": "29999999", "Īpašuma kad. Nr.": "11111111111"})])
    assert len(sagatavot([b]).leadi) == 1


def test_rinda_bez_kadastra_pievienojas_pec_talruna_vai_zemes_vienibas():
    b = _boards([("A", {"Lead Datums": "2026-10-05", "Tel.Nr": "+371 28000000", "Īpašuma kad. Nr.": "11111111111",
                        "Zemes vienības kad. apz.": "11111111112"}),
                 ("B", {"Lead Datums": "2026-10-06", "Tel.Nr": "28000000"}),
                 ("C", {"Lead Datums": "2026-10-06", "Zemes vienības kad. apz.": "11111111112"})])
    d = sagatavot([b])
    assert len(d.leadi) == 1
    assert len(d.leadi[0].rindas) == 3


def test_atjaunots_lead_pec_gada():
    b = _boards([("Vecs", {"Lead Datums": "2024-09-01", "Īpašuma kad. Nr.": "11111111111"}),
                 ("Jauns", {"Lead Datums": "2026-10-02", "Īpašuma kad. Nr.": "11111111111"}),
                 ("Turpinājums", {"Lead Datums": "2026-10-10", "Īpašuma kad. Nr.": "11111111111"})])
    d = sagatavot([b])
    assert sorted(l.epizode for l in d.leadi) == [1, 2]
    a = aprekinat(d, menesis(2026, 10), date(2026, 10, 20))
    assert a.metriks("Leadi kopā") == 1
    assert a.metriks("t.sk. atjaunoti") == 1


# --- Mērķa lead un proaktivitāte -------------------------------------------
@pytest.mark.parametrize("sausie, m3, ha, lauks, gaid", [
    ("8", "800", "10", "10", True),     # 8 ha ≥ 1,5×5 ha
    ("6", "800", "10", "10", False),    # 6 ha < 7,5 ha
    ("8", "650", "10", "10", False),    # < 700 m³
    ("8", "800", "4", "10", False),     # < 5 ha mežs
    ("8", "800", "10", "25", False),    # lauks > 20%
    ("8", "", "10", "10", None),        # trūkst datu
])
def test_merka_kriteriji(sausie, m3, ha, lauks, gaid):
    b = _boards([("X", {"Lead Datums": "2026-10-05", "Īpašuma kad. Nr.": "11111111111",
                        "Kailcirte sausie, ha": sausie, "1. piegājiena apjoms, m³": m3,
                        "Meža platība, ha": ha, "Lauks. zeme, %": lauks})])
    assert merka(sagatavot([b]).leadi[0])[0] is gaid


def test_proaktivs_avots():
    d = sagatavot(demo_boardi(date(2026, 10, 20)))
    for l in d.leadi:
        avots = (l.get("avots") or "").lower()
        if "ss.com" in avots or "facebook" in avots:
            assert proaktivs(l) is False
        if "aukst" in avots or "kaimiņ" in avots:
            assert proaktivs(l) is True


# --- Kolonnu atpazīšana un parsēšana -----------------------------------------
def test_kolonnu_atpazisana_no_screenshot_nosaukumiem():
    karte = auto_karte(KOL)
    assert karte["lead_datums"] == "Lead Datums"
    assert karte["telefons"] == "Tel.Nr"
    assert karte["ipasuma_kad"] == "Īpašuma kad. Nr."
    assert karte["zv_kad"] == "Zemes vienības kad. apz."
    assert karte["pied_veids"] == "Pied. veids"
    assert "Aktualiz. dat." not in karte.values()


def test_parsesana():
    assert norm_telefons("+371 28 000 000") == "28000000"
    assert norm_telefons("0037128000000") == "28000000"
    assert norm_kadastrs("1122 334 4556") == "11223344556"
    assert parse_skaitlis("12 345,6 €") == pytest.approx(12345.6)
    assert parse_skaitlis("1,234.5") == pytest.approx(1234.5)


# --- Pilna atskaite uz demo datiem --------------------------------------------
def test_demo_atskaite_un_excel(tmp_path):
    sod = date(2026, 10, 20)
    d = sagatavot(demo_boardi(sod))
    a = aprekinat(d, menesis(2026, 10), sod)
    assert a.metriks("Leadi kopā") > 0
    assert a.metriks("Leadi kopā") == a.metriks("t.sk. unikāli") + a.metriks("t.sk. atjaunoti")
    assert len(d.leadi) < len(d.rindas)                     # rindas apvienotas leados
    assert "Iepirkumi_Gatis" in a.trukstosas_kolonnas and a.trukstosas_kolonnas["Iepirkumi_Gatis"]
    assert "LEADU ATSKAITE" in teksta_kopsavilkums(a)
    cels = tmp_path / "a.xlsx"
    excel_atskaite(str(cels), a, d)
    assert cels.stat().st_size > 5000


# --- monday API klients (bez tīkla) --------------------------------------------
def test_klients_lapo_un_parse_rindas():
    def item(i, teksts):
        return {"id": str(i), "name": f"LEAD - {i}", "created_at": "2026-10-01T10:00:00Z",
                "group": {"title": "Jauns"},
                "column_values": [{"id": "c1", "text": teksts, "type": "date", "value": None},
                                  {"id": "c2", "text": "", "type": "checkbox", "value": json.dumps({"checked": True})}]}
    atbildes = [
        {"data": {"boards": [{"id": "1", "name": "Agents_A", "workspace": {"name": "IEPIRKUMS"},
                              "groups": [{"title": "Jauns"}],
                              "columns": [{"id": "c1", "title": "Lead Datums", "type": "date"},
                                          {"id": "c2", "title": "Sazvanāms", "type": "checkbox"}],
                              "items_page": {"cursor": "abc", "items": [item(1, "2026-10-01")]}}]}},
        {"data": {"next_items_page": {"cursor": None, "items": [item(2, "2026-10-02")]}}},
    ]
    vaicajumi = []

    def transport(payload):
        vaicajumi.append(payload)
        return atbildes.pop(0)

    b = MondayKlients("", transport=transport).ieladet_boardu("1")
    assert [r.nosaukums for r in b.rindas] == ["LEAD - 1", "LEAD - 2"]
    assert b.rindas[0].vertibas == {"Lead Datums": "2026-10-01", "Sazvanāms": "v"}
    assert vaicajumi[1]["variables"]["cursor"] == "abc"


def test_klients_kluda():
    k = MondayKlients("", transport=lambda p: {"errors": [{"message": "Board not found"}]})
    with pytest.raises(MondayKluda, match="Board not found"):
        k.ieladet_boardu("1")
