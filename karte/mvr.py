"""Meža valsts reģistra (MVR) nogabali pēc kadastra apzīmējuma.

Dati: VMD "Meža valsts reģistra meža dati" (data.gov.lv, CC0, atjauno reizi ceturksnī),
ko GitHub Actions (scripts/mvr_dati.py) sagatavo kā failus mvr_XXXX.parquet
(XXXX = kadastra apzīmējuma pirmie 4 cipari) šī repozitorija Release "mvr-dati".
Katram nogabalam: robeža (WGS84), kvartāls, numurs, platība, formula, vecums,
augstums, caurmērs, bonitāte, krāja, plānotā darbība u.c. — no tiem veido tos
pašus `Nogabals` objektus, ko PDF parsētājs, tāpēc vērtēšana strādā bez PDF.
"""
from __future__ import annotations

import io
import os
import urllib.request

import pandas as pd
import shapely
from shapely.geometry import mapping

from cirsma.parser import Inventarizacija, Nogabals

MVR_URL = os.environ.get(
    "MVR_URL",
    "https://github.com/duukqq-cmyk/baltu-automatizacija/releases/download/mvr-dati/mvr_{}.parquet",
)
AVOTS = "MVR (VMD atvērtie dati)"

# --- Klasifikatori (VMD kodi -> teksts kā inventarizācijas PDF) -----------------
# Bonitāte un meža tipi pārbaudīti pret VMD un gabali.lv inventarizācijas PDF paraugiem
# (64560020029: visi 11 nogabali sakrīt; 42980010013: 12 nogabali sakrīt).
BONITATE = {"0": "Ia", "1": "I", "2": "II", "3": "III", "4": "IV", "5": "V", "6": "Va"}
ZEMES_KATEGORIJA = {"10": "Mežaudze"}
MEZA_TIPS = {
    "1": "Sils", "2": "Mētrājs", "3": "Lāns", "4": "Damaksnis", "5": "Vēris", "6": "Gārša",
    "7": "Grīnis", "8": "Slapjais mētrājs", "9": "Slapjais damaksnis", "10": "Slapjais vēris",
    "11": "Slapjā gārša", "12": "Purvājs", "14": "Niedrājs", "15": "Dumbrājs", "16": "Liekņa",
    "17": "Viršu ārenis", "18": "Mētru ārenis", "19": "Šaurlapju ārenis", "21": "Platlapju ārenis",
    "22": "Viršu kūdrenis", "23": "Mētru kūdrenis", "24": "Šaurlapju kūdrenis",
    "25": "Platlapju kūdrenis",
}


class MvrKluda(Exception):
    """MVR datu fails nav pieejams."""


def lejupieladet_teritoriju(prefikss: str, timeout: float = 60) -> bytes | None:
    """Vienas kadastra teritorijas fails (None — teritorijā nav meža nogabalu)."""
    try:
        with urllib.request.urlopen(MVR_URL.format(prefikss), timeout=timeout) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise MvrKluda(f"MVR dati nav pieejami ({e})") from e
    except Exception as e:  # noqa: BLE001
        raise MvrKluda(f"MVR dati nav pieejami ({e})") from e


def nogabali_no_faila(saturs: bytes | None, kadastrs: str) -> pd.DataFrame:
    if not saturs:
        return pd.DataFrame()
    df = pd.read_parquet(io.BytesIO(saturs))
    return df[df["kadastrs"] == kadastrs].reset_index(drop=True)


def _sk(v, tips=float):
    try:
        if v is None or pd.isna(v):
            return None
        x = tips(v)
        return x if x != 0 else None
    except (TypeError, ValueError):
        return None


def _kods(v) -> str | None:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    s = str(v).strip()
    return None if s in ("", "0", "0.0") else s.removesuffix(".0")


def apzimejums(rinda) -> str:
    return f"{_kods(rinda['kvart']) or '?'}.kv. {int(float(rinda['nog']))}"


def uz_nogabalu(rinda) -> Nogabals:
    zkat = _kods(rinda.get("zkat"))
    mezaudze = zkat == "10"
    n = Nogabals(
        nr=int(float(rinda["nog"])),
        platiba_ha=float(rinda.get("nog_plat") or 0),
        zemes_veids=ZEMES_KATEGORIJA.get(zkat, f"Cita zeme (kods {zkat})") if zkat else "Nav datu",
        kvartals=_kods(rinda.get("kvart")),
        avots="MVR",
    )
    if mezaudze:
        n.meza_tips = MEZA_TIPS.get(_kods(rinda.get("mt")) or "", _kods(rinda.get("mt")))
        n.formula = (rinda.get("formula") or "").strip() or None
        n.izcelsanas = _kods(rinda.get("izc"))
        bon = rinda.get("bon")                      # kods "0" = Ia (nevis "nav datu")
        n.bonitate = BONITATE.get(str(bon).strip().removesuffix(".0")) if bon is not None else None
        n.vid_augstums = _sk(rinda.get("h10"), int)
        n.vid_caurmers = _sk(rinda.get("d10"), int)
        n.vecums = _sk(rinda.get("a10"), int)
        n.kraja_m3_ha = _sk(rinda.get("v_nog"))
        n.plantacija = _kods(rinda.get("plant_audz")) == "1"
    darb = _kods(rinda.get("p_darbv"))
    if darb:
        gads = _sk(rinda.get("p_darbg"), int)
        n.piezimes.append(f"VMD darbības kods {darb}" + (f" ({gads})" if gads else ""))
    cirte = _kods(rinda.get("p_cirp"))
    if cirte:
        gads = _sk(rinda.get("p_cirg"), int)
        n.pedeja_cirte = f"kods {cirte}" + (f", {gads}" if gads else "")
    return n


def uz_inventarizaciju(kadastrs: str, df: pd.DataFrame) -> Inventarizacija:
    df = df.sort_values(["kvart", "nog"], key=lambda s: pd.to_numeric(s, errors="coerce"))
    return Inventarizacija(zemes_vieniba=kadastrs, ipasums=None,
                           nogabali=[uz_nogabalu(r) for _, r in df.iterrows()], avots=AVOTS)


def robezas(df: pd.DataFrame) -> dict[str, dict]:
    """Nogabala apzīmējums -> GeoJSON ģeometrija (WGS84). Vienāda nr. daļas apvieno."""
    grupas: dict[str, list] = {}
    for _, r in df.iterrows():
        grupas.setdefault(apzimejums(r), []).append(shapely.from_wkb(r["geom"]))
    return {apz: mapping(g[0] if len(g) == 1 else shapely.union_all(g)) for apz, g in grupas.items()}
