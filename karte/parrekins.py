"""Cirsmas pārrēķins pēc kartē uzmērītajām platībām.

Kartes laukumu piesaista inventarizācijas nogabalam (pēc apzīmējuma, piem.
"3.kv. 12"). Laukumi ar statusu "Kailcirte" veido cirsmu: piesaistītā nogabala
platība = kartē uzmērīto laukumu summa, nogabals tiek iekļauts cirsmā. Pārējos
nogabalus var izslēgt (režīms "tikai kartē atzīmētie"). Aprēķins izmanto tos
pašus moduļus kā Meža inventarizācijas sadaļa (labojumi -> vērtējums -> finanses).
"""
from __future__ import annotations

import copy
from dataclasses import dataclass

from cirsma.labojumi import Labojums, nogabala_atslega, novertet_ar_labojumiem
from cirsma.parser import Inventarizacija
from cirsma.sortiment import FinansuRezultats, aprekinat, vertejuma_apjoms

from .geometrija import ir_laukums, lks_geometrija, mervienibas

CIRSMAS_STATUSS = "Kailcirte"


def nogabalu_saraksts(inv: Inventarizacija) -> dict[str, str]:
    """Nogabala apzīmējums -> izvēlnes teksts."""
    rez = {}
    for n in inv.nogabali:
        dalas = [f"{n.platiba_ha:.2f} ha"]
        if n.formula:
            dalas.append(n.formula)
        if n.vecums:
            dalas.append(f"{n.vecums} g.")
        if not n.ir_mezaudze:
            dalas.append(n.zemes_veids)
        rez[n.apzimejums] = f"{n.apzimejums} · " + " · ".join(dalas)
    return rez


MIN_DALA_HA = 0.01        # mazākas pārklāšanās ar nogabalu ir zīmēšanas neprecizitāte
MIN_DALA_PROC = 0.02      # ... vai < 2 % no nogabala platības


def uzmeritas_platibas(objekti: list[dict], nogabalu_robezas: dict[str, dict] | None = None,
                       ) -> dict[str, float]:
    """Nogabala apzīmējums -> kartē uzmērītā cirsmas platība (ha).

    Kailcirtes laukums ar manuāli piesaistītu nogabalu -> visa laukuma platība tam nogabalam.
    Bez piesaistes, ja zināmas nogabalu robežas (MVR), laukumu automātiski sadala pa
    nogabaliem pēc pārklāšanās (LKS-92), atmetot sīkas malu pārklāšanās.
    """
    rez: dict[str, float] = {}
    robezas_lks = {k: lks_geometrija(g) for k, g in (nogabalu_robezas or {}).items()}
    for o in objekti:
        if o.get("statuss") != CIRSMAS_STATUSS or not ir_laukums(o):
            continue
        if o.get("nogabals"):
            rez[o["nogabals"]] = rez.get(o["nogabals"], 0.0) + mervienibas(o["geometry"])["platiba_ha"]
            continue
        if not robezas_lks:
            continue
        g = lks_geometrija(o["geometry"])
        for apz, ng in robezas_lks.items():
            if not g.intersects(ng):
                continue
            ha = g.intersection(ng).area / 10_000
            if ha >= MIN_DALA_HA and ha >= MIN_DALA_PROC * ng.area / 10_000:
                rez[apz] = rez.get(apz, 0.0) + ha
    return {k: round(v, 2) for k, v in rez.items()}


def objekta_sadalijums(obj: dict, nogabalu_robezas: dict[str, dict]) -> dict[str, float]:
    """Viena laukuma platība pa nogabaliem (tabulai)."""
    o = dict(obj, statuss=CIRSMAS_STATUSS)
    return uzmeritas_platibas([o], nogabalu_robezas)


def labojumi_no_kartes(
    inv: Inventarizacija,
    objekti: list[dict],
    esosie: dict[str, Labojums] | None = None,
    tikai_atzimetie: bool = True,
    nogabalu_robezas: dict[str, dict] | None = None,
) -> dict[str, Labojums]:
    """Esošie labojumi + kartes uzmērījumi (platība, iekļaušana cirsmā)."""
    labojumi = copy.deepcopy(esosie or {})
    platibas = uzmeritas_platibas(objekti, nogabalu_robezas)
    for i, n in enumerate(inv.nogabali):
        atsl = nogabala_atslega(i)
        if n.apzimejums in platibas:
            lab = labojumi.setdefault(atsl, Labojums())
            lab.platiba_ha = platibas[n.apzimejums]
            lab.kailcirte = True
            lab.apjoms_m3 = None          # apjoms jāpārrēķina no jaunās platības
        elif tikai_atzimetie:
            lab = labojumi.setdefault(atsl, Labojums())
            lab.kailcirte = False
    return {k: v for k, v in labojumi.items() if not v.tukss()}


def _piezime(v, atzimets: bool) -> str:
    if not atzimets and not v.atlauta_kailcirte:
        return "Nav atzīmēts kartē — izslēgts no cirsmas"
    if atzimets and "pēc kritērijiem neatbilst" in v.pamatojums:
        return "⚠ Atzīmēts kartē, bet pēc kailcirtes kritērijiem neatbilst: " + \
            v.pamatojums.split("neatbilst:", 1)[-1].rstrip(")").strip()
    return ""


@dataclass
class Salidzinajums:
    pirms: FinansuRezultats
    pec: FinansuRezultats
    rindas: list[dict]


def salidzinat(
    inv: Inventarizacija,
    objekti: list[dict],
    esosie: dict[str, Labojums] | None = None,
    tikai_atzimetie: bool = True,
    nogabalu_robezas: dict[str, dict] | None = None,
    **aprekina_parametri,
) -> Salidzinajums:
    """Aprēķins pirms (PDF + esošie labojumi) un pēc kartes uzmērījumiem."""
    v_pirms = novertet_ar_labojumiem(inv.nogabali, esosie or {})
    jaunie = labojumi_no_kartes(inv, objekti, esosie, tikai_atzimetie, nogabalu_robezas)
    v_pec = novertet_ar_labojumiem(inv.nogabali, jaunie)
    fin_pirms = aprekinat(v_pirms, **aprekina_parametri)
    fin_pec = aprekinat(v_pec, **aprekina_parametri)
    platibas = uzmeritas_platibas(objekti, nogabalu_robezas)

    pirms_pec_idx = {v.indekss: v for v in v_pirms}
    rindas = []
    for v in v_pec:
        a = pirms_pec_idx.get(v.indekss)
        n, n0 = v.nogabals, (a.nogabals if a else None)
        if not (v.atlauta_kailcirte or (a and a.atlauta_kailcirte) or n.apzimejums in platibas):
            continue
        apj_pirms = vertejuma_apjoms(a)[0] if a and a.atlauta_kailcirte else 0.0
        apj_pec = vertejuma_apjoms(v)[0] if v.atlauta_kailcirte else 0.0
        rindas.append({
            "Nogabals": n.apzimejums,
            "Platība inventarizācijā ha": n0.platiba_ha if n0 else None,
            "Uzmērīts kartē ha": platibas.get(n.apzimejums),
            "Cirsmā pirms": bool(a and a.atlauta_kailcirte),
            "Cirsmā pēc": v.atlauta_kailcirte,
            "Apjoms pirms m³": round(apj_pirms, 1),
            "Apjoms pēc m³": round(apj_pec, 1),
            "Starpība m³": round(apj_pec - apj_pirms, 1),
            "Piezīme": (_piezime(v, n.apzimejums in platibas)),
        })
    return Salidzinajums(fin_pirms, fin_pec, rindas)
