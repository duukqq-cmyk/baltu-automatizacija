"""Testi ciršu veidiem pēc darba uzdevuma "Automatizācijas rīka uzlabojumi" piemēriem."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cirsma.cirtes import (
    blakus_grupas, g_normativi, max_kailcirtes_platiba, meza_tipa_grupa, sadalit_kailcirtes,
    skerslaukuma_cirte, veidaugstums,
)
from cirsma.labojumi import Labojums, novertet_ar_labojumiem
from cirsma.parser import Inventarizacija, Nogabals
from cirsma.report import cirsmas_rindas
from cirsma.rules import novertet_nogabalu
from cirsma.sortiment import aprekinat


def _nog(**kw) -> Nogabals:
    d = dict(nr=1, platiba_ha=1.0, zemes_veids="Mežaudze", meza_tips="Dm", formula="10B75",
             bonitate="I", vid_augstums=24, vid_caurmers=26, vecums=75, kraja_m3_ha=250)
    d.update(kw)
    return Nogabals(**d)


# --- 1. Kailcirtes platības ------------------------------------------------

@pytest.mark.parametrize("tips,grupa,max_ha", [
    ("Dm", "sausieņi", 5), ("Damaksnis", "sausieņi", 5), ("Vr", "sausieņi", 5),
    ("Dms", "slapjaiņi", 2), ("Slapjais damaksnis", "slapjaiņi", 2),
    ("Db", "purvaiņi", 2), ("Ap", "āreņi", 2), ("Ks", "kūdreņi", 2),
])
def test_meza_tipi(tips, grupa, max_ha):
    assert meza_tipa_grupa(tips) == grupa
    assert max_kailcirtes_platiba(tips)[0] == max_ha


def test_nezinams_tips_stingrakais_limits():
    assert max_kailcirtes_platiba(None)[0] == 2
    assert max_kailcirtes_platiba("XYZ")[0] == 2


@pytest.mark.parametrize("platiba,max_ha,cirtes,josla", [
    (1.8, 2, [1.8], 0),
    (2.5, 2, [2.0], 0),        # 0,5 josla + 0 — otrā kailcirte neiznāk
    (2.8, 2, [2.0], 0),        # atlikums 0,3 < 0,5
    (3.0, 2, [2.0, 0.5], 0.5),
    (3.2, 2, [2.0, 0.7], 0.5),  # dokumenta piemērs
    (5.8, 5, [5.0], 0),
    (6.0, 5, [5.0, 0.5], 0.5),
    (7.0, 2, [2.0, 2.0, 2.0], 1.0),
])
def test_sadalit_kailcirtes(platiba, max_ha, cirtes, josla):
    c, j = sadalit_kailcirtes(platiba, max_ha)
    assert c == pytest.approx(cirtes)
    assert j == pytest.approx(josla)


def test_dokumenta_piemers_3_2ha_slapjais():
    """1.nog bērzs 75 g., 3,2 ha, Dms, 250 m³/ha -> 2,0 ha 500 m³ + 0,7 ha 175 m³ = 675 m³."""
    n = _nog(platiba_ha=3.2, meza_tips="Dms")
    v = novertet_nogabalu(n)
    v.indekss = 0
    assert v.cirtes_veids == "kailcirte"
    assert v.kailcirtes_ha == [2.0, 0.7]
    fin = aprekinat([v])
    assert fin.kopejais_m3 == pytest.approx(675)
    inv = Inventarizacija(zemes_vieniba=None, ipasums=None, nogabali=[n])
    rindas = cirsmas_rindas(inv, [v], fin)
    assert [(r["Platība ha"], r["Apjoms m³"]) for r in rindas] == [(2.0, 500.0), (0.7, 175.0)]


def test_sausais_5_8ha_tikai_5():
    v = novertet_nogabalu(_nog(platiba_ha=5.8, meza_tips="Sl", formula="10P105", vecums=105))
    assert v.kailcirtes_ha == [5.0]
    assert "neizcērtams atlikums 0.8" in v.pamatojums


def test_blakus_grupas():
    from shapely.geometry import box
    g = {"a": box(0, 0, 10, 10), "b": box(10, 0, 20, 10), "c": box(50, 50, 60, 60),
         "d": box(20.5, 0, 30, 10)}
    assert blakus_grupas(g) == [["a", "b", "d"]]


# --- 2. Kopšanas / izlases cirtes ------------------------------------------

def test_tabulas():
    assert g_normativi("A", 18) == (13, 7)     # apse
    assert g_normativi("B", 18) == (12, 6)
    assert g_normativi("Os", 32) is None       # osim virs 30 m nav normatīva
    assert g_normativi("P", 40) == (23, 10)    # 35 un vairāk
    assert g_normativi("P", 11) is None
    assert veidaugstums("A", 18)[0] == 8.8
    assert veidaugstums("E", 33)[0] == 14.49   # virs tabulas -> 32 m vērtība
    assert "ārpus" in veidaugstums("E", 33)[1]


def test_dokumenta_kopsanas_piemers():
    """8.nog: 4A4B2Bl24, H 18, G 21, 0,29 ha -> (21 − 14) × 8,8 × 0,29 = 17,86 m³."""
    k = skerslaukuma_cirte("kopsana", "A", 18, 21, 0.29)
    assert k.izcertamais_g == 7
    assert k.apjoms_m3 == pytest.approx(17.86, abs=0.01)
    assert k.atbilst


def test_kopsana_automatiski_tikai_ja_nav_kailcirtes():
    n = _nog(formula="4A4B2Bl24", vecums=24, vid_augstums=18, vid_caurmers=18,
             skerslaukums=21, platiba_ha=0.29)
    v = novertet_nogabalu(n)
    assert v.cirtes_veids == "kopsana"
    assert v.sk_cirte.apjoms_m3 == pytest.approx(17.86, abs=0.01)


def test_kopsana_min_4():
    """Gmin 16 (egle, 16 m: 15), G 18 -> izcērtams 2 < 4 -> necirst."""
    n = _nog(formula="10E40", vecums=40, vid_augstums=16, vid_caurmers=16, skerslaukums=18)
    v = novertet_nogabalu(n)
    assert v.cirtes_veids == "nav"
    n.skerslaukums = 20  # 20 − 16 = 4 -> kopšana
    assert novertet_nogabalu(n).cirtes_veids == "kopsana"


def test_izlases_tikai_manuali_ar_kritisko():
    n = _nog(formula="10B40", vecums=40, vid_augstums=20, vid_caurmers=18, skerslaukums=20,
             platiba_ha=1.0)
    auto = novertet_nogabalu(n)
    assert auto.cirtes_veids == "kopsana"          # 20 − (13+1) = 6
    v = novertet_ar_labojumiem([n], {"0": Labojums(cirtes_veids="izlases")})[0]
    assert v.cirtes_veids == "izlases"
    assert v.sk_cirte.izcertamais_g == 13          # 20 − (6+1)
    assert v.sk_cirte.apjoms_m3 == pytest.approx(13 * 9.09 * 1.0, abs=0.01)
    assert v.pamatojums.startswith("✎ Manuāli: Izlases cirte")


def test_izlases_bez_skerslaukuma_bridina():
    n = _nog(formula="10B40", vecums=40, skerslaukums=None)
    v = novertet_nogabalu(n, veids="izlases")
    assert v.sk_cirte is None
    assert any("nevar aprēķināt" in b for b in v.bridinajumi)


# --- 7. Baltalksnis --------------------------------------------------------

@pytest.mark.parametrize("vecums,caurmers,cert", [(24, 14, False), (25, 10, True), (20, 16, True)])
def test_baltalksnis(vecums, caurmers, cert):
    n = _nog(formula="10Ba" + str(vecums), vecums=vecums, vid_caurmers=caurmers, vid_augstums=14,
             skerslaukums=None)
    assert novertet_nogabalu(n).kailcirte_pec_kriterijiem is cert


def test_cenraza_varianti():
    from cirsma.cenradis import Cenradis, CenrazaVarianti
    v = CenrazaVarianti.no_cenradis(Cenradis())
    assert v.kompozicija().uz_json() == Cenradis().uz_json()
    v.izveidot("kailcirte", "Ziema")
    v.sadalas["kailcirte"]["varianti"]["Ziema"]["matrica"]["P"]["Zāģbaļķi"] = [130, 0.7]
    assert v.kompozicija().cena("P", "Zāģbaļķi") == 100                      # noklusējums — Pamata
    assert v.kompozicija({"kailcirte": "Ziema"}).cena("P", "Zāģbaļķi") == 130
    v.iestatit_noklusejumu("kailcirte", "Ziema")
    assert v.kompozicija().cena("P", "Zāģbaļķi") == 130
    assert CenrazaVarianti.no_json(v.uz_json()).uz_json() == v.uz_json()
    with pytest.raises(ValueError):
        v.dzest("kailcirte", "Ziema")                                        # noklusējumu nevar dzēst
    with pytest.raises(ValueError):
        v.izveidot("kailcirte", "Ziema")                                     # dublikāts
    v.parsaukt("kailcirte", "Ziema", "Ziema 2026")
    assert v.noklusejums("kailcirte") == "Ziema 2026"
    v.dzest("kailcirte", "Pamata")
    assert v.nosaukumi("kailcirte") == ["Ziema 2026"]
