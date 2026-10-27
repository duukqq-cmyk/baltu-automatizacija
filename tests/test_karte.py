"""Testi ĢIS kartes modulim: KML/GeoJSON imports, LKS-92 mērījumi, zīmējumu sinhronizācija, pārrēķins."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from karte.geometrija import (
    _no_lks, apvienot_ar_zimejumiem, jauns_objekts, kopplatiba_ha, lks_uz_wgs, mervienibas,
    nolasit_failu, nolasit_kml, parklasanas, uz_geojson, uz_kml,
)


def _kvadrats_lks(x0, y0, mala):
    """Kvadrāts LKS-92 metros -> GeoJSON poligons WGS84."""
    t = _no_lks()
    punkti = [(x0, y0), (x0 + mala, y0), (x0 + mala, y0 + mala), (x0, y0 + mala), (x0, y0)]
    return {"type": "Polygon", "coordinates": [[list(t(x, y)) for x, y in punkti]]}


# Struktūra kā lietotāju KML failos no tīmekļa kartes zīmēšanas rīka (ExtendedData COLOR/AREA)
KML_PARAUGS = """<kml xmlns="http://www.opengis.net/kml/2.2"><Document>
<Placemark id="a"><ExtendedData><Data name="AREA"><value>1.00 ha</value></Data>
<Data name="COLOR"><value>#eb144c</value></Data><Data name="DESCRIPTION"><value>Priedes</value></Data>
</ExtendedData><Polygon><outerBoundaryIs><LinearRing><coordinates>{a}</coordinates></LinearRing>
</outerBoundaryIs></Polygon></Placemark>
<Placemark><name>Krautuve</name><Style><LineStyle><color>ff00ff00</color></LineStyle></Style>
<LineString><coordinates>24.50,57.10 24.51,57.10</coordinates></LineString></Placemark>
<Placemark><name>Punkts</name><Point><coordinates>24.5,57.1,0</coordinates></Point></Placemark>
</Document></kml>"""


def _koord_teksts(geom):
    return " ".join(f"{x},{y}" for x, y in geom["coordinates"][0])


def test_platiba_lks92():
    g = _kvadrats_lks(500_000, 300_000, 100)            # 100 × 100 m = 1 ha
    m = mervienibas(g)
    assert m["platiba_ha"] == pytest.approx(1.0, abs=0.001)
    assert m["garums_m"] == pytest.approx(400, abs=0.5)
    assert (m["x"], m["y"]) == (500_050, 300_050)


def test_kml_imports():
    g = _kvadrats_lks(500_000, 300_000, 100)
    obj = nolasit_kml(KML_PARAUGS.format(a=_koord_teksts(g)).encode(), "GRIVAS.kml")
    assert [o["geometry"]["type"] for o in obj] == ["Polygon", "LineString", "Point"]
    assert obj[0]["nosaukums"] == "GRIVAS 1"           # bez <name> -> faila nosaukums
    assert obj[0]["krasa"] == "#eb144c"
    assert obj[0]["piezimes"] == "Priedes"
    assert obj[0]["statuss"] == "Kailcirte"
    assert obj[1]["nosaukums"] == "Krautuve" and obj[1]["krasa"] == "#00ff00"   # aabbggrr -> #rrggbb
    assert obj[1]["statuss"] == "Cits"
    assert mervienibas(obj[0]["geometry"])["platiba_ha"] == pytest.approx(1.0, abs=0.001)


def test_kml_eksports_un_atpakal():
    o = jauns_objekts(_kvadrats_lks(500_000, 300_000, 200), "Cirsma A")
    o["nogabals"] = "3.kv. 12"
    kml = uz_kml([o])
    atpakal = nolasit_kml(kml)
    assert atpakal[0]["nosaukums"] == "Cirsma A"
    assert mervienibas(atpakal[0]["geometry"])["platiba_ha"] == pytest.approx(4.0, abs=0.002)
    gj = json.dumps(uz_geojson([o]))
    no_gj = nolasit_failu(gj.encode(), "x.geojson")
    assert no_gj[0]["nogabals"] == "3.kv. 12" and no_gj[0]["statuss"] == "Kailcirte"


def test_parklasanas_un_kopplatiba():
    a = jauns_objekts(_kvadrats_lks(500_000, 300_000, 100), "A")
    b = jauns_objekts(_kvadrats_lks(500_050, 300_000, 100), "B")   # pārklājas 50 × 100 m
    p = parklasanas([a, b])
    assert len(p) == 1 and p[0][2] == pytest.approx(5000, rel=0.01)
    assert kopplatiba_ha([a, b]) == pytest.approx(1.5, abs=0.002)


def test_zimejumu_sinhronizacija():
    a = jauns_objekts(_kvadrats_lks(500_000, 300_000, 100), "A")
    b = jauns_objekts(_kvadrats_lks(501_000, 300_000, 100), "B")
    fa = {"type": "Feature", "properties": {"id": a["id"]}, "geometry": a["geometry"]}
    jauns = {"type": "Feature", "properties": {}, "geometry": _kvadrats_lks(502_000, 300_000, 50)}
    # B izdzēsts, pievienots jauns laukums, A nemainīts
    rez, mainits = apvienot_ar_zimejumiem([a, b], [fa, jauns])
    assert mainits
    assert [o["nosaukums"] for o in rez] == ["A", "Laukums 3"]
    assert rez[0]["id"] == a["id"]
    # Tas pats stāvoklis vēlreiz — nekas nemainās
    rez2, mainits2 = apvienot_ar_zimejumiem(rez, [fa, {**jauns, "properties": {"id": rez[1]["id"]}}])
    assert not mainits2 and rez2 == rez
    # Labota robeža -> ģeometrija atjaunojas, īpašības paliek
    rez[0]["statuss"] = "Kopšanas cirte"
    labots = {**fa, "geometry": _kvadrats_lks(500_000, 300_000, 120)}
    rez3, mainits3 = apvienot_ar_zimejumiem(rez[:1], [labots])
    assert mainits3 and rez3[0]["statuss"] == "Kopšanas cirte"
    assert mervienibas(rez3[0]["geometry"])["platiba_ha"] == pytest.approx(1.44, abs=0.002)


def test_lks_uz_wgs():
    lat, lon = lks_uz_wgs(500_000, 300_000)
    assert 56.5 < lat < 57.5 and 23.5 < lon < 25


VMD = os.path.join(os.path.dirname(__file__), "..", "dati",
                   "Nogabalu_raksturojosie_raditaji_64560020029.pdf")


@pytest.mark.skipif(not os.path.exists(VMD), reason="Nav parauga PDF")
def test_parrekins_pec_kartes():
    from cirsma.parser import parse_inventory_pdf
    from cirsma.rules import atlasit_kailcirtes
    from karte.parrekins import labojumi_no_kartes, nogabalu_saraksts, salidzinat

    inv = parse_inventory_pdf(VMD)
    cirtami = [v.nogabals for v in atlasit_kailcirtes(inv.nogabali) if v.atlauta_kailcirte]
    assert len(cirtami) >= 2
    n = cirtami[0]
    assert n.apzimejums in nogabalu_saraksts(inv)
    puse = (n.platiba_ha * 10_000 / 2) ** 0.5                       # puse no nogabala platības
    o = jauns_objekts(_kvadrats_lks(500_000, 300_000, puse), "Cirsma")
    o["nogabals"] = n.apzimejums

    lab = labojumi_no_kartes(inv, [o], tikai_atzimetie=True)
    assert sum(1 for l in lab.values() if l.kailcirte) == 1
    s = salidzinat(inv, [o], tikai_atzimetie=True)
    rinda = next(r for r in s.rindas if r["Nogabals"] == n.apzimejums)
    assert rinda["Uzmērīts kartē ha"] == pytest.approx(n.platiba_ha / 2, abs=0.01)
    assert rinda["Apjoms pēc m³"] == pytest.approx(rinda["Apjoms pirms m³"] / 2, rel=0.03)
    assert s.pec.kopejais_m3 == pytest.approx(rinda["Apjoms pēc m³"], abs=0.5)  # tikai šis nogabals
    assert s.pec.kopejais_m3 < s.pirms.kopejais_m3
    # Režīms "paturēt pārējos": pārējie cērtamie nogabali paliek cirsmā
    s2 = salidzinat(inv, [o], tikai_atzimetie=False)
    assert s2.pec.kopejais_m3 == pytest.approx(
        s.pirms.kopejais_m3 - rinda["Apjoms pirms m³"] + rinda["Apjoms pēc m³"], abs=1)


# --- Kadastra meklēšana (VZD INSPIRE WFS) ---------------------------------------

KAD_FIX = os.path.join(os.path.dirname(__file__), "dati", "kadastrs_64560020029.json")


def test_apzimejumi_no_teksta():
    from karte.kadastrs import apzimejumi
    assert apzimejumi("8064 001 0066") == ["80640010066"]
    assert apzimejumi("80640010066, 80440060026; 80640010066") == ["80640010066", "80440060026"]
    assert apzimejumi("8064001006680440060026") == ["80640010066", "80440060026"]
    assert apzimejumi("123") == []


def test_kadastrs_atbilde_un_platiba():
    from karte.kadastrs import parset_atbildi
    with open(KAD_FIX, encoding="utf-8") as f:
        zv = parset_atbildi(json.load(f))
    assert len(zv) == 1 and zv[0]["kadastrs"] == "64560020029"
    assert zv[0]["platiba_ha"] == pytest.approx(10.6)
    assert "kadastrs.lv" in zv[0]["saite"]
    # Grafiskā platība (LKS-92) var atšķirties no kadastrā reģistrētās — šeit 10.35 pret 10.6 ha
    assert zv[0]["platiba_graf_ha"] == pytest.approx(10.35, abs=0.01)


def test_kadastrs_rezerves_serviss(monkeypatch):
    import io
    import karte.kadastrs as k
    with open(KAD_FIX, "rb") as f:
        saturs = f.read()
    izsaukumi = []

    class Atbilde(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def urlopen(req, timeout):
        izsaukumi.append(req.full_url)
        if len(izsaukumi) == 1:
            raise OSError("nav savienojuma")
        return Atbilde(saturs)

    monkeypatch.setattr(k.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(k, "WFS_ADRESES", ["https://a.example/wfs", "https://b.example/wfs"])
    zv = k.atrast(["64560020029", "99999999999"])
    assert [z["kadastrs"] for z in zv] == ["64560020029"]
    assert "featureID=CP64560020029,CP99999999999" in izsaukumi[1]
    monkeypatch.setattr(k.urllib.request, "urlopen", lambda *a, **kw: (_ for _ in ()).throw(OSError("x")))
    with pytest.raises(k.KadastrsKluda):
        k.atrast(["64560020029"])


# --- MVR nogabali un automātiskā sadale pa nogabaliem -------------------------------

def _mvr_parquet():
    import io as _io
    import pandas as pd
    import shapely
    from shapely.geometry import shape
    t = _no_lks()
    rindas = []
    for nog, x0, plat in [(1, 500_000, 100), (2, 500_100, 100)]:     # divi blakus 1 ha nogabali
        g = shape(_kvadrats_lks(x0, 300_000, plat))
        rindas.append({"kadastrs": "64560020029", "kvart": "3", "nog": str(nog), "anog": "0",
                       "nog_plat": 1.0, "zkat": "10", "mt": "4", "izc": "1", "formula": "8P2B",
                       "a10": 101.0, "h10": 27.0, "d10": 32.0, "v_nog": 300.0, "bon": "1",
                       "p_darbv": "0", "p_cirp": "0", "plant_audz": "0", "geom": shapely.to_wkb(g)})
    rindas.append({**rindas[0], "kadastrs": "64560020030", "nog": "9"})
    buf = _io.BytesIO()
    pd.DataFrame(rindas).to_parquet(buf, index=False)
    return buf.getvalue()


def test_mvr_nogabali_un_vertejums():
    from cirsma.rules import novertet_nogabalu
    from karte.mvr import nogabali_no_faila, robezas, uz_inventarizaciju
    df = nogabali_no_faila(_mvr_parquet(), "64560020029")
    assert len(df) == 2
    inv = uz_inventarizaciju("64560020029", df)
    n = inv.nogabali[0]
    assert (n.apzimejums, n.bonitate, n.vecums, n.kraja_m3_ha, n.zemes_veids) == \
        ("3.kv. 1", "I", 101, 300.0, "Mežaudze")
    assert novertet_nogabalu(n).atlauta_kailcirte            # 101 g. priede, I bon.
    r = robezas(df)
    assert set(r) == {"3.kv. 1", "3.kv. 2"}
    assert mervienibas(r["3.kv. 1"])["platiba_ha"] == pytest.approx(1.0, abs=0.001)
    assert nogabali_no_faila(None, "1").empty


def test_cirsma_automatiski_sadalas_pa_nogabaliem():
    from karte.mvr import nogabali_no_faila, robezas, uz_inventarizaciju
    from karte.parrekins import salidzinat, uzmeritas_platibas
    df = nogabali_no_faila(_mvr_parquet(), "64560020029")
    inv, rob = uz_inventarizaciju("64560020029", df), robezas(df)
    # Cirsma: 60 m no 1. nogabala + 40 m no 2. (100 m augstumā) = 0.6 ha + 0.4 ha
    cirsma = jauns_objekts(_kvadrats_lks(500_040, 300_000, 100), "C")
    assert uzmeritas_platibas([cirsma], rob) == {"3.kv. 1": 0.6, "3.kv. 2": 0.4}
    # Sīka pārklāšanās ar kaimiņu (< 0.01 ha) tiek atmesta
    gandriz = jauns_objekts(_kvadrats_lks(500_000.5, 300_000, 99.6), "G")
    assert set(uzmeritas_platibas([gandriz], rob)) == {"3.kv. 1"}
    # Manuāla piesaiste ir noteicošā
    cirsma_p = dict(cirsma, nogabals="3.kv. 2")
    assert uzmeritas_platibas([cirsma_p], rob) == {"3.kv. 2": 1.0}
    s = salidzinat(inv, [cirsma], tikai_atzimetie=True, nogabalu_robezas=rob)
    assert s.pec.kopejais_m3 == pytest.approx(300 * 1.0, rel=0.01)   # 300 m³/ha × (0.6+0.4) ha
    assert s.pirms.kopejais_m3 == pytest.approx(600, rel=0.01)
