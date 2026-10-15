"""Kailcirtes atbilstības noteikumi.

Nogabalu drīkst cirst kailcirtē, ja valdošā koku suga ir sasniegusi
galvenās cirtes vecumu VAI valdaudzes vidējo caurmēru (P/E/B).
Izņēmums: baltalksnis (Ba) — bez vecuma vai caurmēra ierobežojuma.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .formula import parse_formula, SUGU_NOSAUKUMI
from .parser import Nogabals

# Galvenās cirtes vecums (gados) pēc valdošās sugas un bonitātes grupas.
# Grupas: "I+" (I un augstāka: Ia, Ib, I), "II-III", "IV-" (IV un zemāka)
CIRSANAS_VECUMS: dict[str, dict[str, int]] = {
    "Oz": {"I+": 101, "II-III": 121, "IV-": 121},
    "P":  {"I+": 101, "II-III": 101, "IV-": 121},
    "E":  {"I+": 81,  "II-III": 81,  "IV-": 81},
    "Os": {"I+": 81,  "II-III": 81,  "IV-": 81},
    "L":  {"I+": 81,  "II-III": 81,  "IV-": 81},
    "Go": {"I+": 81,  "II-III": 81,  "IV-": 81},
    "V":  {"I+": 81,  "II-III": 81,  "IV-": 81},
    "Vī": {"I+": 81,  "II-III": 81,  "IV-": 81},
    "K":  {"I+": 81,  "II-III": 81,  "IV-": 81},
    "B":  {"I+": 71,  "II-III": 71,  "IV-": 51},
    "Ma": {"I+": 71,  "II-III": 71,  "IV-": 71},
    "M":  {"I+": 71,  "II-III": 71,  "IV-": 71},  # melnalksnis (VMD kods "M")
    "A":  {"I+": 41,  "II-III": 41,  "IV-": 41},
}

# Valdaudzes vidējais caurmērs (cm) pēc sugas un bonitātes (tikai P, E, B)
CIRSANAS_CAURMERS: dict[str, dict[str, int]] = {
    "P": {"Ia": 39, "I": 35, "II": 31, "III": 27},
    "E": {"Ia": 31, "I": 29, "II": 29, "III": 27},
    "B": {"Ia": 31, "I": 27, "II": 25, "III": 22},
}

BEZ_IEROBEZOJUMA = {"Ba"}  # baltalksnis — cērtams bez vecuma/caurmēra ierobežojuma


def _bonitates_grupa(bonitate: str) -> str:
    if bonitate in ("Ia", "Ib", "I"):
        return "I+"
    if bonitate in ("II", "III"):
        return "II-III"
    return "IV-"


@dataclass
class Vertejums:
    nogabals: Nogabals
    valdosa_suga: str
    atlauta_kailcirte: bool
    pamatojums: str
    bridinajumi: list[str] = field(default_factory=list)  # ⚠ riski / ℹ informācija / ✎ labots
    indekss: int | None = None                # nogabala indekss inventarizācijā
    apjoms_m3_manuali: float | None = None    # lietotāja ievadīts apjoms (aizstāj aprēķināto)


# Kontrolsummu sliekšņi: sugu krājas ir noapaļotas līdz veseliem m³, tāpēc
# mazos nogabalos relatīvā atšķirība var būt liela — prasām abus nosacījumus.
KONTROLE_REL = 0.10
KONTROLE_ABS_M3 = 3.0
JAUNAUDZES_VECUMS = 20


def riska_karogi(n: Nogabals, atlauta: bool) -> list[str]:
    """Papildu pārbaudes, kas kailcirtes lēmumu nemaina, bet jāredz speciālistam."""
    k: list[str] = []
    planots = (n.planots or "").lower()

    for josla in n.aizsargjoslas:
        m = re.search(r"\d{8}", josla)
        kods = m.group(0) if m else ""
        nosaukums = josla.rsplit("/", 1)[-1].strip() or josla
        if kods.startswith("4002"):
            k.append(f"⚠ Ūdens objektu aizsargjosla {kods} ({nosaukums}) — kailcirte var būt ierobežota")
        else:
            k.append(f"⚠ Apgrūtinājums {kods} ({nosaukums}) — jāpārbauda ierobežojumi")

    if n.planots:
        if atlauta and "kailcirte" not in planots:
            k.append(f"⚠ VMD plānotā darbība: {n.planots} (nevis kailcirte)")
        elif not atlauta and "kailcirte" in planots:
            k.append("ℹ VMD plāno kailcirti, bet pēc mūsu kritērijiem tā vēl nav atļauta — pārbaudīt")

    if n.plantacija:
        k.append("ℹ Plantācijas audze")
    if atlauta and n.vecums is not None and n.vecums < JAUNAUDZES_VECUMS:
        k.append(f"ℹ Jaunaudze ({n.vecums} g.) — kailcirte atļauta tikai sugas dēļ, pārbaudīt lietderību")
    if n.otrais_stavs:
        k.append(f"ℹ 2. stāvs: {n.otrais_stavs}")
    for b in n.bojajumi:
        k.append(f"ℹ Bojājums: {b}")
    if n.komentari:
        k.append(f"ℹ Komentārs: {n.komentari}")

    # Kontrolsummas
    if n.kopeja_kraja_m3 and n.kraja_m3_ha is not None:
        aprek = n.kraja_m3_ha * n.platiba_ha
        if abs(aprek - n.kopeja_kraja_m3) > max(KONTROLE_ABS_M3, KONTROLE_REL * n.kopeja_kraja_m3):
            k.append(f"⚠ Krāja × platība ({aprek:.1f} m³) nesakrīt ar kopējo krāju "
                     f"({n.kopeja_kraja_m3:.1f} m³) — manuāla pārbaude")
    if n.sugu_kraja and n.kopeja_kraja_m3:
        sugu_summa = sum(s.kraja_m3 if s.kraja_m3 is not None else s.kraja_m3_ha * n.platiba_ha
                         for s in n.sugu_kraja)
        if abs(sugu_summa - n.kopeja_kraja_m3) > max(KONTROLE_ABS_M3, KONTROLE_REL * n.kopeja_kraja_m3):
            k.append(f"⚠ Sugu krāju summa ({sugu_summa:.0f} m³) atšķiras no kopējās krājas "
                     f"({n.kopeja_kraja_m3:.1f} m³) — manuāla pārbaude")
    return k


def novertet_nogabalu(n: Nogabals) -> Vertejums | None:
    """Novērtē viena nogabala atbilstību kailcirtei. None — nav mežaudze."""
    v = _novertet_kriterijus(n)
    if v is not None:
        v.bridinajumi = riska_karogi(n, v.atlauta_kailcirte)
    return v


def _novertet_kriterijus(n: Nogabals) -> Vertejums | None:
    if not n.ir_mezaudze or not n.formula:
        return None

    dalas = parse_formula(n.formula)
    suga = dalas[0].suga
    nosaukums = SUGU_NOSAUKUMI.get(suga, suga)
    # Valdošās sugas vecums: pirmās komponentes vecums; ja nav — audzes vecums
    vecums = dalas[0].vecums if dalas[0].vecums is not None else n.vecums
    if "vecums" in n.labots:  # lietotāja labotais vecums ir noteicošais
        vecums = n.vecums

    if suga in BEZ_IEROBEZOJUMA:
        return Vertejums(n, suga, True, f"Valdošā suga {nosaukums} — cērtama bez ierobežojuma")

    # 1) vecuma kritērijs
    if suga in CIRSANAS_VECUMS and vecums is not None:
        slieksnis = CIRSANAS_VECUMS[suga][_bonitates_grupa(n.bonitate or "IV")]
        if vecums >= slieksnis:
            return Vertejums(
                n, suga, True,
                f"{nosaukums} sasniedzis ciršanas vecumu: {vecums} g. ≥ {slieksnis} g. "
                f"(bonitāte {n.bonitate})",
            )
    else:
        slieksnis = None

    # 2) caurmēra kritērijs (tikai P, E, B)
    if suga in CIRSANAS_CAURMERS and n.vid_caurmers is not None and n.bonitate:
        c_slieksnis = CIRSANAS_CAURMERS[suga].get(n.bonitate)
        if c_slieksnis is not None and n.vid_caurmers >= c_slieksnis:
            return Vertejums(
                n, suga, True,
                f"{nosaukums} sasniedzis ciršanas caurmēru: {n.vid_caurmers} cm ≥ "
                f"{c_slieksnis} cm (bonitāte {n.bonitate})",
            )

    if suga not in CIRSANAS_VECUMS:
        return Vertejums(
            n, suga, False,
            f"Valdošajai sugai {nosaukums} nav noteikts ciršanas vecums — manuāla pārbaude",
        )
    return Vertejums(
        n, suga, False,
        f"{nosaukums} nav sasniedzis ne ciršanas vecumu ({vecums} g. < {slieksnis} g.), "
        f"ne caurmēru",
    )


def atlasit_kailcirtes(nogabali: list[Nogabals]) -> list[Vertejums]:
    """Novērtē visus nogabalus; atgriež vērtējumus (mežaudzēm)."""
    rezultati = []
    for n in nogabali:
        v = novertet_nogabalu(n)
        if v is not None:
            rezultati.append(v)
    return rezultati
