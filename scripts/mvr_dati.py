"""Meža valsts reģistra (MVR) atvērto datu sagatavošana kartes sadaļai.

Avots: VMD "Meža valsts reģistra meža dati" (data.gov.lv, CC0, atjauno reizi ceturksnī)
— SHP faili pa virsmežniecībām (7z). Skripts lejupielādē visas virsmežniecības,
atlasa vajadzīgos laukus, pārvērš ģeometriju uz WGS84 un sadala failos pēc kadastra
apzīmējuma pirmajiem 4 cipariem (kadastra teritorija): mvr_XXXX.parquet.
Aplikācija lejupielādē tikai vajadzīgo failu (parasti 0,1–3 MB).

Palaišana (GitHub Actions, sk. .github/workflows/mvr-dati.yml):
    python scripts/mvr_dati.py dist/
"""
from __future__ import annotations

import glob
import json
import os
import shutil
import subprocess
import sys
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone

import pandas as pd
import pyogrio
import shapely

DATU_KOPA = "https://data.gov.lv/dati/api/3/action/package_show?id=meza-valsts-registra-meza-dati"

# Lauki, ko saglabājam (pārējie aplikācijai nav vajadzīgi)
LAUKI = [
    "kadastrs", "kvart", "nog", "anog", "nog_plat", "zkat", "mt", "izc",
    *[f"{p}{i}" for i in range(10, 15) for p in ("s", "a", "h", "d", "g", "n", "k")],
    "formula", "v_nog", "bon", "vgr", "jakopj", "jaatjauno", "p_darbv", "p_darbg", "p_cirp",
    "p_cirg", "atj_gads", "plant_audz", "expl_mezs",
]


UA = {"User-Agent": "Mozilla/5.0 (baltu-automatizacija MVR datu sagatavošana)"}


def _atvert(url: str, timeout: float):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout)


def _lejupieladet(url: str, merkis: str) -> None:
    with _atvert(url, 900) as r, open(merkis, "wb") as f:
        shutil.copyfileobj(r, f, length=1 << 20)


def main(izvade: str) -> None:
    os.makedirs(izvade, exist_ok=True)
    pakete = json.load(_atvert(DATU_KOPA, 60))["result"]
    resursi = [r for r in pakete["resources"] if r["url"].endswith(".7z")]
    dalas: dict[str, list[pd.DataFrame]] = defaultdict(list)
    meta = {"izveidots": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "avots": "VMD Meža valsts reģistra meža dati (data.gov.lv, CC0)", "virsmeznieciba": {}}

    for r in resursi:
        nos = r["name"]
        print(f"== {nos}: {r['url']}", flush=True)
        _lejupieladet(r["url"], "tmp.7z")
        subprocess.run(["7z", "x", "-y", "-otmp", "tmp.7z"], check=True, stdout=subprocess.DEVNULL)
        os.remove("tmp.7z")
        skaits = 0
        for shp in sorted(glob.glob("tmp/**/*.shp", recursive=True)):
            info = pyogrio.read_info(shp)
            lauki = [f for f in LAUKI if f in set(info["fields"])]
            df = pyogrio.read_dataframe(shp, columns=lauki, use_arrow=True)
            df = df[df["kadastrs"].notna() & (df["kadastrs"].astype(str).str.len() >= 4)]
            df = df.to_crs(4326)
            geom = shapely.set_precision(df.geometry.values, 1e-6)
            out = pd.DataFrame(df.drop(columns="geometry"))
            out["kadastrs"] = out["kadastrs"].astype(str).str.strip()
            out["geom"] = shapely.to_wkb(geom)
            for pref, grupa in out.groupby(out["kadastrs"].str[:4]):
                dalas[pref].append(grupa)
            skaits += len(out)
            print(f"   {os.path.basename(shp)}: {len(out)}", flush=True)
        meta["virsmeznieciba"][nos] = {"nogabali": skaits, "datu_datums": r.get("last_modified")}
        shutil.rmtree("tmp")

    indekss = {}
    for pref, grupas in sorted(dalas.items()):
        df = pd.concat(grupas, ignore_index=True).sort_values(["kadastrs", "kvart", "nog"])
        df.to_parquet(os.path.join(izvade, f"mvr_{pref}.parquet"), index=False, compression="zstd")
        indekss[pref] = len(df)
    meta["faili"] = indekss
    with open(os.path.join(izvade, "mvr_meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    print(f"Gatavs: {len(indekss)} faili, {sum(indekss.values())} nogabali")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "dist")
