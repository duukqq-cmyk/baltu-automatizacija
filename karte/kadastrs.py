"""Zemes vienību meklēšana pēc kadastra apzīmējuma (VZD INSPIRE WFS).

Avots: VZD "Kadastrālie zemes gabali (INSPIRE)", licence CC BY 4.0, atjauno reizi
nedēļā (https://data.gov.lv/dati/dataset/kadastralie-zemes-gabali-inspire).
WFS pieejams caur Ģeoportāla (geolatvija.lv) DPPS starpniekservisu; rezerves
variants — tiešais VZD serviss. Objekta ID = "CP" + 11 ciparu apzīmējums.
"""
from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request

from .geometrija import mervienibas

WFS_ADRESES = [
    "https://geo-dpps.viss.gov.lv/api/DPPSPackage/client/Zemes_vien_423_0p2RBZ/"
    "5cc09e19-a238-4a2e-8eac-3a05cefa050e",
    "https://grafws.kadastrs.lv/geoserver/cp/wfs",
]
if os.environ.get("KADASTRS_WFS"):            # alternatīvs serviss (piem., testiem)
    WFS_ADRESES = [os.environ["KADASTRS_WFS"]]
ATRIBUCIJA = "Valsts zemes dienests, CC BY 4.0"


def _atvertajs() -> urllib.request.OpenerDirector:
    """VZD datu servisi atbild tikai Latvijas IP adresēm. Ja iestatīts VZD_PROXY
    (Streamlit Secrets saknes atslēga -> vides mainīgais), pieprasījumi iet caur
    starpniekserveri Latvijā, piem., "http://lietotajs:parole@185.72.86.90:38129"."""
    proxy = os.environ.get("VZD_PROXY", "").strip()
    if proxy:
        return urllib.request.build_opener(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    return urllib.request.build_opener()


def proxy_iestatits() -> bool:
    return bool(os.environ.get("VZD_PROXY", "").strip())


class KadastrsKluda(Exception):
    """Serviss nav sasniedzams vai atbilde nav nolasāma."""


def apzimejumi(teksts: str) -> list[str]:
    """Izvelk 11 ciparu kadastra apzīmējumus no brīva teksta ("8064 001 0066", "80640010066, ...")."""
    rez = []
    for dala in re.split(r"[,;\n]+", teksts or ""):
        cipari = re.sub(r"\D", "", dala)
        if len(cipari) == 11 and cipari not in rez:
            rez.append(cipari)
        elif len(cipari) > 11:                       # vairāki numuri bez atdalītāja
            for m in re.findall(r"\d{11}", cipari):
                if m not in rez:
                    rez.append(m)
    return rez


def _vaicajums(adrese: str, kodi: list[str]) -> str:
    q = {
        "service": "WFS", "version": "2.0.0", "request": "GetFeature",
        "typeNames": "cp:CadastralParcel", "outputFormat": "application/json",
        "srsName": "EPSG:4326", "featureID": ",".join(f"CP{k}" for k in kodi),
    }
    return adrese + "?" + urllib.parse.urlencode(q, safe=":,")


def parset_atbildi(dati: dict) -> list[dict]:
    """WFS GeoJSON -> [{kadastrs, platiba_ha, platiba_graf_ha, geometry, saite}]."""
    rez = []
    for f in dati.get("features", []):
        p = f.get("properties") or {}
        g = f.get("geometry")
        if not g:
            continue
        laukums = (p.get("areaValue") or {}).get("value")
        rez.append({
            "kadastrs": p.get("label") or str(f.get("id", "")).removeprefix("CP"),
            "platiba_ha": round(laukums / 10_000, 4) if laukums else None,   # reģistrētā
            "platiba_graf_ha": mervienibas(g)["platiba_ha"],                  # pēc robežām LKS-92
            "geometry": g,
            "saite": p.get("nationalCadastralReference")
                     or f"https://www.kadastrs.lv/parcels/search?cad_num={p.get('label')}",
        })
    return rez


def atrast(kodi: list[str], timeout: float = 20.0) -> list[dict]:
    """Zemes vienības pēc apzīmējumiem. Neatrastos vienkārši neatgriež."""
    if not kodi:
        return []
    pedeja_kluda = None
    atvertajs = _atvertajs()
    for adrese in WFS_ADRESES:
        try:
            pieprasijums = urllib.request.Request(_vaicajums(adrese, kodi),
                                                  headers={"User-Agent": "baltu-automatizacija/1.0"})
            with atvertajs.open(pieprasijums, timeout=timeout) as r:
                dati = json.loads(r.read().decode("utf-8"))
            atrasti = {z["kadastrs"]: z for z in parset_atbildi(dati)}
            return [atrasti[k] for k in kodi if k in atrasti]
        except Exception as e:  # noqa: BLE001 — mēģinām nākamo servisu
            pedeja_kluda = e
    kluda = str(pedeja_kluda)
    if proxy_iestatits():                       # nerādām paroli kļūdas tekstā
        kluda = kluda.replace(os.environ["VZD_PROXY"], "VZD_PROXY")
    raise KadastrsKluda(f"VZD kadastra serviss nav pieejams ({kluda})")
