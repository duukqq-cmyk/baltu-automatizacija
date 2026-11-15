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

from cirsma.cirtes import (
    IZLASES, KAILCIRTE, KOPSANA, NOKLUSEJUMA_NOTEIKUMI, Noteikumi, blakus_grupas,
    max_kailcirtes_platiba, sadalit_kailcirtes,
)
from cirsma.labojumi import Labojums, nogabala_atslega, novertet_ar_labojumiem
from cirsma.parser import Inventarizacija
from cirsma.rules import novertet_nogabalu
from cirsma.sortiment import FinansuRezultats, aprekinat, vertejuma_apjoms

from .geometrija import (
    ir_laukums, jauns_objekts, lks_geometrija, mervienibas, sadalit_poligonu, wgs_geometrija,
)

CIRSMAS_STATUSS = "Kailcirte"
JOSLAS_STATUSS = "Atdalošā josla"
# Kartes objekta statuss -> cirtes veids aprēķinā
STATUSS_VEIDS = {"Kailcirte": KAILCIRTE, "Kopšanas cirte": KOPSANA, "Izlases cirte": IZLASES}
VEIDS_STATUSS = {v: k for k, v in STATUSS_VEIDS.items()}


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


def uzmeritas_dalas(objekti: list[dict], nogabalu_robezas: dict[str, dict] | None = None,
                    statuss: str = CIRSMAS_STATUSS) -> dict[str, list[float]]:
    """Nogabala apzīmējums -> katra laukuma (ar šo statusu) daļa nogabalā, ha.

    Laukums ar manuāli piesaistītu nogabalu -> visa laukuma platība tam nogabalam.
    Bez piesaistes, ja zināmas nogabalu robežas (MVR), laukumu automātiski sadala pa
    nogabaliem pēc pārklāšanās (LKS-92), atmetot sīkas malu pārklāšanās.
    """
    rez: dict[str, list[float]] = {}
    robezas_lks = {k: lks_geometrija(g) for k, g in (nogabalu_robezas or {}).items()}
    for o in objekti:
        if o.get("statuss") != statuss or not ir_laukums(o):
            continue
        if o.get("nogabals"):
            rez.setdefault(o["nogabals"], []).append(mervienibas(o["geometry"])["platiba_ha"])
            continue
        if not robezas_lks:
            continue
        g = lks_geometrija(o["geometry"])
        for apz, ng in robezas_lks.items():
            if not g.intersects(ng):
                continue
            ha = g.intersection(ng).area / 10_000
            if ha >= MIN_DALA_HA and ha >= MIN_DALA_PROC * ng.area / 10_000:
                rez.setdefault(apz, []).append(ha)
    return {k: [round(x, 2) for x in v] for k, v in rez.items()}


def uzmeritas_platibas(objekti: list[dict], nogabalu_robezas: dict[str, dict] | None = None,
                       statuss: str = CIRSMAS_STATUSS) -> dict[str, float]:
    """Nogabala apzīmējums -> kartē uzmērītā platība (ha) ar šo statusu."""
    return {k: round(sum(v), 2) for k, v in uzmeritas_dalas(objekti, nogabalu_robezas, statuss).items()}


def uzmeritas_visas(objekti: list[dict], nogabalu_robezas: dict[str, dict] | None = None
                    ) -> dict[str, float]:
    """Visu cirtes statusu (kailcirte, kopšana, izlases) uzmērītās platības pa nogabaliem."""
    rez: dict[str, float] = {}
    for statuss in STATUSS_VEIDS:
        for k, ha in uzmeritas_platibas(objekti, nogabalu_robezas, statuss).items():
            rez[k] = round(rez.get(k, 0.0) + ha, 2)
    return rez


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
    ieklaut_neatbilstosos: bool = False,
) -> dict[str, Labojums]:
    """Esošie labojumi + kartes uzmērījumi (platība, iekļaušana cirsmā).

    Kartē atzīmēts nogabals cirsmā tiek iekļauts tikai tad, ja tas atbilst kailcirtes
    kritērijiem (vai `ieklaut_neatbilstosos`) — citādi, piem., zīmējot visu zemes
    vienību, cirsmā nonāktu arī jaunaudzes.
    """
    labojumi = copy.deepcopy(esosie or {})
    pa_veidiem = {veids: uzmeritas_dalas(objekti, nogabalu_robezas, statuss)
                  for statuss, veids in STATUSS_VEIDS.items()}
    for i, n in enumerate(inv.nogabali):
        atsl = nogabala_atslega(i)
        # nogabalam — tas cirtes veids, kura laukums tajā ir lielākais
        kandidati = {veids: d[n.apzimejums] for veids, d in pa_veidiem.items() if n.apzimejums in d}
        if kandidati:
            veids = max(kandidati, key=lambda k: sum(kandidati[k]))
            dalas = kandidati[veids]
            lab = labojumi.setdefault(atsl, Labojums())
            lab.platiba_ha = round(sum(dalas), 2)
            lab.apjoms_m3 = None          # apjoms jāpārrēķina no jaunās platības
            lab.kailcirte = None
            if veids == KAILCIRTE:
                v = novertet_nogabalu(n)
                atbilst = bool(v and v.atlauta_kailcirte)
                lab.cirtes_veids = KAILCIRTE if (atbilst or ieklaut_neatbilstosos) else "nav"
                lab.kailcirtes_dalas = list(dalas)
            else:
                lab.cirtes_veids = veids
                lab.kailcirtes_dalas = None
        elif tikai_atzimetie:
            lab = labojumi.setdefault(atsl, Labojums())
            lab.kailcirte = None
            lab.cirtes_veids = "nav"
    return {k: v for k, v in labojumi.items() if not v.tukss()}


def automatiskas_cirsmas(inv: Inventarizacija, nogabalu_robezas: dict[str, dict],
                         nt: Noteikumi = NOKLUSEJUMA_NOTEIKUMI,
                         izlaist: set[str] | None = None) -> list[dict]:
    """Kartes objekti cērtamajiem nogabaliem pēc to robežām.

    Kailcirte, kas pārsniedz max platību pēc meža tipa, tiek sadalīta pa garāko asi:
    kailcirte + atdalošā josla + nākamā kailcirte (+ neizcērtamais atlikums). Kopšanas
    cirtes — viss nogabals. Izlases cirti sistēma pati neiezīmē.
    """
    objekti: list[dict] = []
    for n in inv.nogabali:
        apz = n.apzimejums
        if apz in (izlaist or set()) or apz not in nogabalu_robezas:
            continue
        v = novertet_nogabalu(n, nt=nt)
        if v is None or v.cirtes_veids not in (KAILCIRTE, KOPSANA):
            continue
        g = lks_geometrija(nogabalu_robezas[apz])
        if v.cirtes_veids == KOPSANA:
            objekti.append(jauns_objekts(wgs_geometrija(g), f"Kopšana {apz}", statuss="Kopšanas cirte"))
            continue
        max_ha, _ = max_kailcirtes_platiba(n.meza_tips, nt)
        objekti += sagriezt_kailcirti(g, max_ha, nt, apz)
    return objekti


def sagriezt_kailcirti(g, max_ha: float, nt: Noteikumi = NOKLUSEJUMA_NOTEIKUMI,
                       apz: str = "") -> list[dict]:
    """LKS-92 laukums -> kailcirte(s) ≤ max_ha + atdalošās joslas (+ neizcērtams atlikums)."""
    nos = f" {apz}" if apz else ""
    platiba = g.area / 10_000
    cirtes, _ = sadalit_kailcirtes(platiba, max_ha, nt)
    if len(cirtes) == 1:
        if platiba <= max_ha + 0.005:
            return [jauns_objekts(wgs_geometrija(g), f"Cirsma{nos}", statuss=CIRSMAS_STATUSS)]
        platibas = [cirtes[0]]
    else:
        platibas = []
        for i, c in enumerate(cirtes):
            platibas.append(c)
            if i < len(cirtes) - 1:
                platibas.append(nt.atdalosa_josla_ha)
    rez, nr = [], 0
    for i, gab in enumerate(sadalit_poligonu(g, platibas)):
        if gab.area < (100 if i >= len(platibas) else 1):   # < 0,01 ha atlikums — griešanas paliekas
            continue
        if i < len(platibas) and i % 2 == 0:
            nr += 1
            suff = f" ({nr})" if len(cirtes) > 1 else ""
            rez.append(jauns_objekts(wgs_geometrija(gab), f"Cirsma{nos}{suff}", statuss=CIRSMAS_STATUSS))
        elif i < len(platibas):
            rez.append(jauns_objekts(wgs_geometrija(gab), f"Josla{nos}", statuss=JOSLAS_STATUSS,
                                     piezimes="Atdalošā josla starp kailcirtēm (netiek cirsta)"))
        else:
            rez.append(jauns_objekts(wgs_geometrija(gab), f"Atlikums{nos}", statuss="Neiekļaut",
                                     piezimes="Pārāk mazs nākamajai kailcirtei"))
    return rez


def sadalit_objektu(o: dict, inv: Inventarizacija | None, nogabalu_robezas: dict[str, dict] | None,
                    nt: Noteikumi = NOKLUSEJUMA_NOTEIKUMI) -> list[dict]:
    """Kartes laukumu sadala kailcirtēs ar atdalošo joslu (izvēlne "Sadalīt ar joslu").

    Limits — pēc nogabala, kurā ir lielākā laukuma daļa (meža tips); nezināms -> stingrākais.
    """
    if not ir_laukums(o):
        return [o]
    g = lks_geometrija(o["geometry"])
    apz = o.get("nogabals")
    if not apz and nogabalu_robezas:
        dalas = uzmeritas_dalas([dict(o, statuss=CIRSMAS_STATUSS)], nogabalu_robezas)
        apz = max(dalas, key=lambda k: sum(dalas[k])) if dalas else None
    tips = next((n.meza_tips for n in inv.nogabali if n.apzimejums == apz), None) if (inv and apz) else None
    max_ha, _ = max_kailcirtes_platiba(tips, nt)
    if g.area / 10_000 <= max_ha + 0.005:
        return [o]
    nos = o["nosaukums"].removeprefix("Cirsma").strip() or (apz or "")
    return sagriezt_kailcirti(g, max_ha, nt, nos)


def blakus_kailcirsu_bridinajumi(objekti: list[dict], inv: Inventarizacija | None,
                                 nogabalu_robezas: dict[str, dict] | None,
                                 nt: Noteikumi = NOKLUSEJUMA_NOTEIKUMI) -> list[str]:
    """Kailcirtes laukumi, kas saskaras, skaitās kopā — brīdina, ja kopplatība > limits.

    Limits — stingrākais no meža tipiem, kuros atrodas laukumi.
    """
    laukumi = {o["id"]: o for o in objekti if o.get("statuss") == CIRSMAS_STATUSS and ir_laukums(o)}
    if not laukumi:
        return []
    geom = {k: lks_geometrija(o["geometry"]) for k, o in laukumi.items()}
    tipi = {n.apzimejums: n.meza_tips for n in inv.nogabali} if inv else {}
    robezas_lks = {k: lks_geometrija(g) for k, g in (nogabalu_robezas or {}).items()}
    rez = []
    grupas = blakus_grupas(geom)
    grupetie = {k for g in grupas for k in g}
    for grupa in grupas + [[k] for k in geom if k not in grupetie]:
        kopa = shapely_union_ha([geom[k] for k in grupa])
        limiti = []
        for k in grupa:
            o = laukumi[k]
            noga = [o["nogabals"]] if o.get("nogabals") else [
                a for a, ng in robezas_lks.items() if geom[k].intersection(ng).area > 100]
            limiti += [max_kailcirtes_platiba(tipi.get(a), nt)[0] for a in noga] or [nt.max_citi_ha]
        limits = min(limiti) if limiti else nt.max_citi_ha
        if kopa > limits + 0.005 and len(grupa) == 1:
            rez.append(f"⚠ Kailcirte {laukumi[grupa[0]]['nosaukums']} ir {kopa:.2f} ha > {limits:g} ha "
                       "(max pēc meža tipa) — sadali ar atdalošo joslu vai samazini.")
        elif kopa > limits + 0.005:
            rez.append(f"⚠ Kailcirtes saskaras: {', '.join(laukumi[k]['nosaukums'] for k in grupa)} — "
                       f"kopā {kopa:.2f} ha > {limits:g} ha. Atdali ar joslu (~{nt.atdalosa_josla_ha:g} ha) "
                       "vai samazini.")
    return rez


def shapely_union_ha(geoms) -> float:
    from shapely.ops import unary_union  # noqa: PLC0415
    return unary_union(geoms).area / 10_000


def _piezime(v, atzimets: bool) -> str:
    if not atzimets and not v.cirtams:
        return "Nav atzīmēts kartē — izslēgts no cirsmas"
    if atzimets and not v.cirtams:
        return "⚠ Atzīmēts kartē, bet neatbilst kailcirtes kritērijiem — cirsmā nav iekļauts"
    bridin = [b for b in v.bridinajumi if b.startswith("⚠") and ("Kartē" in b or "nevar" in b)]
    if bridin:
        return "; ".join(bridin)
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
    ieklaut_neatbilstosos: bool = False,
    nt: Noteikumi | None = None,
    **aprekina_parametri,
) -> Salidzinajums:
    """Aprēķins pirms (PDF + esošie labojumi) un pēc kartes uzmērījumiem."""
    v_pirms = novertet_ar_labojumiem(inv.nogabali, esosie or {}, nt)
    jaunie = labojumi_no_kartes(inv, objekti, esosie, tikai_atzimetie, nogabalu_robezas,
                                ieklaut_neatbilstosos)
    v_pec = novertet_ar_labojumiem(inv.nogabali, jaunie, nt)
    fin_pirms = aprekinat(v_pirms, **aprekina_parametri)
    fin_pec = aprekinat(v_pec, **aprekina_parametri)
    platibas = uzmeritas_visas(objekti, nogabalu_robezas)

    pirms_pec_idx = {v.indekss: v for v in v_pirms}
    rindas = []
    for v in v_pec:
        a = pirms_pec_idx.get(v.indekss)
        n, n0 = v.nogabals, (a.nogabals if a else None)
        if not (v.cirtams or (a and a.cirtams) or n.apzimejums in platibas):
            continue
        apj_pirms = vertejuma_apjoms(a)[0] if a and a.cirtams else 0.0
        apj_pec = vertejuma_apjoms(v)[0] if v.cirtams else 0.0
        rindas.append({
            "Nogabals": n.apzimejums,
            "Platība inventarizācijā ha": n0.platiba_ha if n0 else None,
            "Uzmērīts kartē ha": platibas.get(n.apzimejums),
            "Cirte pirms": a.cirtes_nosaukums if a else "—",
            "Cirte pēc": v.cirtes_nosaukums,
            "Apjoms pirms m³": round(apj_pirms, 1),
            "Apjoms pēc m³": round(apj_pec, 1),
            "Starpība m³": round(apj_pec - apj_pirms, 1),
            "Piezīme": (_piezime(v, n.apzimejums in platibas)),
        })
    return Salidzinajums(fin_pirms, fin_pec, rindas)
