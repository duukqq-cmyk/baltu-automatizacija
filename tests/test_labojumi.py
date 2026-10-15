"""Testi manuālajiem labojumiem nogabalu tabulā (abi avoti: VMD un gabali.lv)."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cirsma.labojumi import Labojums, novertet_ar_labojumiem
from cirsma.parser import parse_inventory_pdf
from cirsma.rules import atlasit_kailcirtes
from cirsma.sortiment import aprekinat

VMD = os.path.join(os.path.dirname(__file__), "..", "dati",
                   "Nogabalu_raksturojosie_raditaji_64560020029.pdf")
RUDINI = os.path.join(os.path.dirname(__file__), "..", "dati", "gabali",
                      "42980010013_Nogabalu_dati_zv_4.pdf")


@pytest.fixture(scope="module", params=[VMD, RUDINI], ids=["VMD", "gabali"])
def inv(request):
    if not os.path.exists(request.param):
        pytest.skip("Nav parauga PDF")
    return parse_inventory_pdf(request.param)


def _idx(inv, kv, nr):
    return str(next(i for i, n in enumerate(inv.nogabali) if n.kvartals == kv and n.nr == nr))


def _v(vertejumi, atsl):
    return next(v for v in vertejumi if str(v.indekss) == atsl)


def _apjoms(fin, v):
    return next((a.kopejais_m3 for a in fin.apjomi if a.nogabals is v.nogabals), None)


def test_bez_labojumiem_rezultats_nemainas(inv):
    a = aprekinat(atlasit_kailcirtes(inv.nogabali))
    b = aprekinat(novertet_ar_labojumiem(inv.nogabali, {}))
    assert a.max_iegades_summa == b.max_iegades_summa
    assert a.kopejais_m3 == b.kopejais_m3


def test_kailcirtes_kekss(inv):
    base = novertet_ar_labojumiem(inv.nogabali)
    cirt = next(v for v in base if v.atlauta_kailcirte)
    atsl = str(cirt.indekss)
    fin0 = aprekinat(base)
    vs = novertet_ar_labojumiem(inv.nogabali, {atsl: Labojums(kailcirte=False)})
    fin1 = aprekinat(vs)
    assert not _v(vs, atsl).atlauta_kailcirte
    assert _v(vs, atsl).pamatojums.startswith("✎ Manuāli izķeksēts")
    assert fin1.kopejais_m3 == pytest.approx(fin0.kopejais_m3 - _apjoms(fin0, cirt), abs=0.05)
    # atpakaļ ieķeksēts = sakrīt ar sistēmu -> nav labojuma karoga
    vs2 = novertet_ar_labojumiem(inv.nogabali, {atsl: Labojums(kailcirte=True)})
    assert not any(b.startswith("✎") for b in _v(vs2, atsl).bridinajumi)


def test_platiba_parrekina_apjomu(inv):
    base = novertet_ar_labojumiem(inv.nogabali)
    v0 = next(v for v in base if v.atlauta_kailcirte)
    atsl = str(v0.indekss)
    vs = novertet_ar_labojumiem(inv.nogabali, {atsl: Labojums(platiba_ha=v0.nogabals.platiba_ha * 2)})
    fin0, fin1 = aprekinat(base), aprekinat(vs)
    assert _apjoms(fin1, _v(vs, atsl)) == pytest.approx(2 * _apjoms(fin0, v0), rel=0.01)


def test_kraja_parrekina_apjomu(inv):
    v0 = next(v for v in novertet_ar_labojumiem(inv.nogabali) if v.atlauta_kailcirte)
    atsl = str(v0.indekss)
    vs = novertet_ar_labojumiem(inv.nogabali, {atsl: Labojums(kraja_m3_ha=100)})
    assert _apjoms(aprekinat(vs), _v(vs, atsl)) == pytest.approx(100 * v0.nogabals.platiba_ha, abs=0.01)


def test_manualais_apjoms_saglaba_sugu_proporcijas(inv):
    v0 = next(v for v in novertet_ar_labojumiem(inv.nogabali) if v.atlauta_kailcirte)
    atsl = str(v0.indekss)
    vs = novertet_ar_labojumiem(inv.nogabali, {atsl: Labojums(apjoms_m3=500)})
    a = next(a for a in aprekinat(vs).apjomi if a.nogabals is _v(vs, atsl).nogabals)
    assert a.kopejais_m3 == 500 and a.metode == "manuāli"
    assert sum(a.pa_sugam.values()) == pytest.approx(500, abs=0.05)


def test_vecums_un_bonitate_parverte_kailcirti():
    if not os.path.exists(RUDINI):
        pytest.skip("Nav parauga PDF")
    inv = parse_inventory_pdf(RUDINI)
    atsl = _idx(inv, "1", 4)  # 7B69..., bonitāte II, 69 g. < 71 g. -> necērtams
    assert not _v(novertet_ar_labojumiem(inv.nogabali), atsl).atlauta_kailcirte
    assert _v(novertet_ar_labojumiem(inv.nogabali, {atsl: Labojums(vecums=75)}), atsl).atlauta_kailcirte
    # bonitāte IV -> bērza ciršanas vecums 51 g.
    assert _v(novertet_ar_labojumiem(inv.nogabali, {atsl: Labojums(bonitate="IV")}), atsl).atlauta_kailcirte
    # oriģinālie dati netiek mainīti
    assert inv.nogabali[int(atsl)].vecums == 69 and inv.nogabali[int(atsl)].bonitate == "II"


def test_labojumu_izmainas_uzskaita_tikai_lietotaja_vertibas(inv):
    from cirsma.labojumi import labojumu_izmainas
    bazes = novertet_ar_labojumiem(inv.nogabali, {})
    v0 = bazes[0]
    atsl = str(v0.indekss)
    n = inv.nogabali[v0.indekss]
    lab = {atsl: Labojums(platiba_ha=(n.platiba_ha or 0) + 1, kailcirte=not v0.atlauta_kailcirte)}
    izm = labojumu_izmainas(inv.nogabali, lab)
    rindas = izm[v0.indekss]
    assert any(r.startswith("Platība:") and "→" in r for r in rindas)
    assert any(r.startswith("Kailcirte:") for r in rindas)
    assert not any(r.startswith("Apjoms:") for r in rindas)  # pārrēķinātais apjoms nav labojums


def test_labojumu_izmainas_ignore_nemainitu_vertibu(inv):
    from cirsma.labojumi import labojumu_izmainas
    v0 = novertet_ar_labojumiem(inv.nogabali, {})[0]
    lab = {str(v0.indekss): Labojums(kailcirte=v0.atlauta_kailcirte)}
    assert labojumu_izmainas(inv.nogabali, lab) == {}
