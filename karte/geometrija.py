"""Kartes objekti: imports (KML/GeoJSON), mērījumi LKS-92 un eksports.

Objekts ir vienkārša vārdnīca, lai to var glabāt `st.session_state` un nodot
kartei kā GeoJSON:
    {"id", "nosaukums", "statuss", "krasa", "nogabals", "piezimes", "geometry"}
`geometry` ir GeoJSON ģeometrija WGS84 (lon, lat). Platības un garumus rēķina
LKS-92 / TM (EPSG:3059) — tajā pašā sistēmā, kurā strādā VMD un VZD.
"""
from __future__ import annotations

import json
import re
import uuid
import xml.etree.ElementTree as ET
from functools import lru_cache

from pyproj import Transformer
from shapely.geometry import shape
import numpy as np
import shapely
from shapely.ops import unary_union
from shapely.validation import make_valid

STATUSI: dict[str, str] = {          # statuss -> krāsa kartē
    "Kailcirte": "#e5484d",
    "Kopšanas cirte": "#f59e0b",
    "Izlases cirte": "#a855f7",
    "Krautuve / ceļš": "#3b82f6",
    "Neiekļaut": "#9ca3af",
    "Cits": "#14b8a6",
}
NOKLUSETAIS_STATUSS = "Kailcirte"

KML_NS = {"k": "http://www.opengis.net/kml/2.2"}


@lru_cache(maxsize=None)
def _uz_lks():
    return Transformer.from_crs(4326, 3059, always_xy=True).transform


@lru_cache(maxsize=None)
def _no_lks():
    return Transformer.from_crs(3059, 4326, always_xy=True).transform


def jauns_id() -> str:
    return uuid.uuid4().hex[:10]


def lks_geometrija(geometry: dict):
    """GeoJSON ģeometrija (WGS84) -> shapely ģeometrija LKS-92 metros."""
    g = shape(geometry)
    if not g.is_valid:
        g = make_valid(g)
    t = _uz_lks()
    return shapely.transform(g, lambda c: np.column_stack(t(c[:, 0], c[:, 1])))


def mervienibas(geometry: dict) -> dict:
    """Platība (ha), perimetrs / garums (m) un centra koordinātas LKS-92."""
    g = lks_geometrija(geometry)
    c = g.centroid
    if g.geom_type in ("Polygon", "MultiPolygon", "GeometryCollection") and g.area > 0:
        return {"platiba_ha": round(g.area / 10_000, 4), "garums_m": round(g.length, 1),
                "x": round(c.x), "y": round(c.y)}
    return {"platiba_ha": 0.0, "garums_m": round(g.length, 1), "x": round(c.x), "y": round(c.y)}


def ir_laukums(obj: dict) -> bool:
    return obj["geometry"]["type"] in ("Polygon", "MultiPolygon")


def jauns_objekts(geometry: dict, nosaukums: str, statuss: str | None = None,
                  krasa: str | None = None, piezimes: str = "") -> dict:
    statuss = statuss or (NOKLUSETAIS_STATUSS if geometry["type"] in ("Polygon", "MultiPolygon")
                          else "Cits")
    return {
        "id": jauns_id(), "nosaukums": nosaukums, "statuss": statuss,
        "krasa": krasa, "nogabals": None, "piezimes": piezimes, "geometry": geometry,
    }


def objekta_krasa(obj: dict) -> str:
    return STATUSI.get(obj.get("statuss"), STATUSI["Cits"])


# --- Imports ------------------------------------------------------------------

def _koord(teksts: str) -> list[list[float]]:
    punkti = []
    for p in teksts.split():
        dalas = p.split(",")
        if len(dalas) >= 2:
            punkti.append([round(float(dalas[0]), 6), round(float(dalas[1]), 6)])
    return punkti


def _kml_geometrijas(pm) -> list[dict]:
    rez = []
    for poly in pm.iter("{%s}Polygon" % KML_NS["k"]):
        arejs = poly.find("k:outerBoundaryIs//k:coordinates", KML_NS)
        if arejs is None or not arejs.text:
            continue
        gredzeni = [_koord(arejs.text)]
        for iekss in poly.findall("k:innerBoundaryIs//k:coordinates", KML_NS):
            if iekss.text:
                gredzeni.append(_koord(iekss.text))
        for g in gredzeni:
            if g and g[0] != g[-1]:
                g.append(g[0])
        rez.append({"type": "Polygon", "coordinates": gredzeni})
    for ls in pm.iter("{%s}LineString" % KML_NS["k"]):
        c = ls.find("k:coordinates", KML_NS)
        if c is not None and c.text:
            rez.append({"type": "LineString", "coordinates": _koord(c.text)})
    for pt in pm.iter("{%s}Point" % KML_NS["k"]):
        c = pt.find("k:coordinates", KML_NS)
        if c is not None and c.text:
            rez.append({"type": "Point", "coordinates": _koord(c.text)[0]})
    return rez


def _kml_krasa(pm) -> str | None:
    """Krāsa no ExtendedData COLOR (piem., kartes zīmēšanas rīki) vai KML stila (aabbggrr)."""
    for d in pm.iter("{%s}Data" % KML_NS["k"]):
        if (d.get("name") or "").upper() == "COLOR":
            v = d.find("k:value", KML_NS)
            if v is not None and v.text and re.fullmatch(r"#?[0-9a-fA-F]{6}", v.text.strip()):
                return "#" + v.text.strip().lstrip("#").lower()
    c = pm.find(".//k:PolyStyle/k:color", KML_NS) or pm.find(".//k:LineStyle/k:color", KML_NS)
    if c is not None and c.text and len(c.text.strip()) == 8:
        aabbggrr = c.text.strip()
        return "#" + (aabbggrr[6:8] + aabbggrr[4:6] + aabbggrr[2:4]).lower()
    return None


def _kml_apraksts(pm) -> str:
    teksti = []
    d = pm.find("k:description", KML_NS)
    if d is not None and d.text and d.text.strip():
        teksti.append(d.text.strip())
    for dat in pm.iter("{%s}Data" % KML_NS["k"]):
        if (dat.get("name") or "").upper() == "DESCRIPTION":
            v = dat.find("k:value", KML_NS)
            if v is not None and v.text and v.text.strip():
                teksti.append(v.text.strip())
    return " · ".join(dict.fromkeys(teksti))


def nolasit_kml(saturs: bytes | str, faila_nosaukums: str = "KML") -> list[dict]:
    """KML -> objektu saraksts. Nosaukums no <name>, citādi '<fails> N'."""
    if isinstance(saturs, bytes):
        saturs = saturs.decode("utf-8-sig", errors="replace")
    root = ET.fromstring(saturs)
    if not root.tag.startswith("{"):          # KML bez nosaukumvietas
        saturs = saturs.replace("<kml", '<kml xmlns="http://www.opengis.net/kml/2.2"', 1)
        root = ET.fromstring(saturs)
    pamatnosaukums = re.sub(r"\.(kml|xml)$", "", faila_nosaukums, flags=re.I)
    objekti = []
    for pm in root.iter("{%s}Placemark" % KML_NS["k"]):
        n = pm.find("k:name", KML_NS)
        nosaukums = n.text.strip() if n is not None and n.text and n.text.strip() else None
        krasa = _kml_krasa(pm)
        apraksts = _kml_apraksts(pm)
        for geom in _kml_geometrijas(pm):
            objekti.append(jauns_objekts(
                geom, nosaukums or f"{pamatnosaukums} {len(objekti) + 1}",
                statuss=None, krasa=krasa, piezimes=apraksts))
    return objekti


def nolasit_geojson(saturs: bytes | str, faila_nosaukums: str = "GeoJSON") -> list[dict]:
    dati = json.loads(saturs)
    if dati.get("type") == "Feature":
        dati = {"type": "FeatureCollection", "features": [dati]}
    elif dati.get("type") != "FeatureCollection":
        dati = {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": dati,
                                                           "properties": {}}]}
    pamatnosaukums = re.sub(r"\.(geo)?json$", "", faila_nosaukums, flags=re.I)
    objekti = []
    for f in dati["features"]:
        g = f.get("geometry")
        if not g:
            continue
        p = f.get("properties") or {}
        geoms = ([{"type": "Polygon", "coordinates": c} for c in g["coordinates"]]
                 if g["type"] == "MultiPolygon" else [g])
        for geom in geoms:
            if geom["type"] not in ("Polygon", "LineString", "Point"):
                continue
            geom = {"type": geom["type"], "coordinates": _apalot(geom["coordinates"])}
            o = jauns_objekts(geom, p.get("nosaukums") or p.get("name")
                              or f"{pamatnosaukums} {len(objekti) + 1}",
                              statuss=p.get("statuss") if p.get("statuss") in STATUSI else None,
                              krasa=p.get("krasa"), piezimes=p.get("piezimes") or "")
            o["nogabals"] = p.get("nogabals")
            objekti.append(o)
    return objekti


def nolasit_failu(saturs: bytes, faila_nosaukums: str) -> list[dict]:
    if faila_nosaukums.lower().endswith((".geojson", ".json")):
        return nolasit_geojson(saturs, faila_nosaukums)
    return nolasit_kml(saturs, faila_nosaukums)


# --- Sinhronizācija ar kartē zīmēto -----------------------------------------

def _apalot(c):
    if isinstance(c, (list, tuple)):
        return [_apalot(x) for x in c]
    return round(float(c), 6)


def apvienot_ar_zimejumiem(objekti: list[dict], zimejumi: list[dict]) -> tuple[list[dict], bool]:
    """Kartes zīmēšanas rīka pilnais stāvoklis (`all_drawings`) -> atjaunots objektu saraksts.

    Kartē esošajiem objektiem ir `properties.id`; jauni zīmējumi to nesatur.
    Objekti, kuru vairs nav zīmējumos, ir izdzēsti ar kartes dzēšanas rīku.
    Atgriež (jaunais saraksts, vai kaut kas mainījās).
    """
    pec_id = {o["id"]: o for o in objekti}
    jauni, redzeti, mainits = [], set(), False
    nakamais = len(objekti) + 1
    for z in zimejumi or []:
        g = z.get("geometry")
        if not g or g.get("type") not in ("Polygon", "LineString", "Point", "MultiPolygon"):
            continue
        g = {"type": g["type"], "coordinates": _apalot(g["coordinates"])}
        oid = (z.get("properties") or {}).get("id")
        if oid in pec_id and oid not in redzeti:
            o = dict(pec_id[oid])
            if _apalot(o["geometry"]["coordinates"]) != g["coordinates"]:
                o["geometry"] = g
                mainits = True
            jauni.append(o)
            redzeti.add(oid)
        else:
            veids = {"Polygon": "Laukums", "MultiPolygon": "Laukums",
                     "LineString": "Līnija", "Point": "Punkts"}[g["type"]]
            jauni.append(jauns_objekts(g, f"{veids} {nakamais}"))
            nakamais += 1
            mainits = True
    if len(redzeti) != len(objekti):
        mainits = True
    return jauni, mainits


# --- Analīze -----------------------------------------------------------------

def parklasanas(objekti: list[dict], min_m2: float = 1.0) -> list[tuple[str, str, float]]:
    """Laukumu pāri, kas pārklājas (id1, id2, m²)."""
    laukumi = [(o["id"], lks_geometrija(o["geometry"])) for o in objekti if ir_laukums(o)]
    rez = []
    for i in range(len(laukumi)):
        for j in range(i + 1, len(laukumi)):
            a = laukumi[i][1].intersection(laukumi[j][1]).area
            if a >= min_m2:
                rez.append((laukumi[i][0], laukumi[j][0], round(a, 1)))
    return rez


def kopplatiba_ha(objekti: list[dict]) -> float:
    """Apvienotā platība (pārklāšanās netiek skaitītas divreiz)."""
    g = [lks_geometrija(o["geometry"]) for o in objekti if ir_laukums(o)]
    return round(unary_union(g).area / 10_000, 4) if g else 0.0


def robezas(objekti: list[dict]) -> list[list[float]] | None:
    """[[lat_min, lon_min], [lat_max, lon_max]] kartes pietuvināšanai."""
    if not objekti:
        return None
    b = unary_union([shape(o["geometry"]) for o in objekti]).bounds
    return [[b[1], b[0]], [b[3], b[2]]]


def lks_uz_wgs(x: float, y: float) -> tuple[float, float]:
    lon, lat = _no_lks()(x, y)
    return lat, lon


# --- Eksports ----------------------------------------------------------------

def uz_geojson(objekti: list[dict], ar_merijumiem: bool = True) -> dict:
    features = []
    for o in objekti:
        p = {k: o.get(k) for k in ("id", "nosaukums", "statuss", "nogabals", "piezimes")}
        p["krasa"] = objekta_krasa(o)
        if ar_merijumiem:
            p.update(mervienibas(o["geometry"]))
        features.append({"type": "Feature", "geometry": o["geometry"], "properties": p})
    return {"type": "FeatureCollection", "features": features}


def _xml(s) -> str:
    return (str(s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _kml_koord(c) -> str:
    return " ".join(f"{p[0]},{p[1]}" for p in c)


def uz_kml(objekti: list[dict], dokuments: str = "Cirsmas") -> str:
    stili, vietas = {}, []
    for o in objekti:
        krasa = objekta_krasa(o).lstrip("#")
        stils = "s" + krasa
        abgr = krasa[4:6] + krasa[2:4] + krasa[0:2]
        stili[stils] = (f'<Style id="{stils}"><LineStyle><color>ff{abgr}</color><width>2</width>'
                        f'</LineStyle><PolyStyle><color>59{abgr}</color></PolyStyle></Style>')
        g = o["geometry"]
        if g["type"] == "Polygon":
            ieksas = "".join(f"<innerBoundaryIs><LinearRing><coordinates>{_kml_koord(r)}"
                             f"</coordinates></LinearRing></innerBoundaryIs>" for r in g["coordinates"][1:])
            geom = (f"<Polygon><outerBoundaryIs><LinearRing><coordinates>"
                    f"{_kml_koord(g['coordinates'][0])}</coordinates></LinearRing></outerBoundaryIs>"
                    f"{ieksas}</Polygon>")
        elif g["type"] == "LineString":
            geom = f"<LineString><coordinates>{_kml_koord(g['coordinates'])}</coordinates></LineString>"
        elif g["type"] == "Point":
            geom = f"<Point><coordinates>{g['coordinates'][0]},{g['coordinates'][1]}</coordinates></Point>"
        else:
            continue
        m = mervienibas(g)
        dati = {"STATUSS": o.get("statuss"), "NOGABALS": o.get("nogabals"),
                "PLATIBA_HA": m["platiba_ha"] or None, "GARUMS_M": m["garums_m"],
                "COLOR": "#" + krasa}
        ext = "".join(f'<Data name="{k}"><value>{_xml(v)}</value></Data>'
                      for k, v in dati.items() if v not in (None, ""))
        vietas.append(f"<Placemark><name>{_xml(o['nosaukums'])}</name>"
                      f"<description>{_xml(o.get('piezimes'))}</description>"
                      f"<styleUrl>#{stils}</styleUrl><ExtendedData>{ext}</ExtendedData>{geom}</Placemark>")
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<kml xmlns="http://www.opengis.net/kml/2.2">'
            f"<Document><name>{_xml(dokuments)}</name>{''.join(stili.values())}{''.join(vietas)}"
            "</Document></kml>")


__all__ = [
    "STATUSI", "apvienot_ar_zimejumiem", "ir_laukums", "jauns_objekts", "kopplatiba_ha",
    "lks_geometrija", "lks_uz_wgs", "mervienibas", "nolasit_failu", "nolasit_geojson",
    "nolasit_kml", "objekta_krasa", "parklasanas", "robezas", "uz_geojson", "uz_kml",
]
