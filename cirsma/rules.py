"""Kailcirtes atbilstības noteikumi.

Nogabalu drīkst cirst kailcirtē, ja valdošā koku suga ir sasniegusi
galvenās cirtes vecumu VAI valdaudzes vidējo caurmēru (P/E/B).
Izņēmums: baltalksnis (Ba) — bez vecuma vai caurmēra ierobežojuma.
"""
from __future__ import annotations

from dataclasses import dataclass

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


def novertet_nogabalu(n: Nogabals) -> Vertejums | None:
    """Novērtē viena nogabala atbilstību kailcirtei. None — nav mežaudze."""
    if not n.ir_mezaudze or not n.formula:
        return None

    dalas = parse_formula(n.formula)
    suga = dalas[0].suga
    nosaukums = SUGU_NOSAUKUMI.get(suga, suga)
    # Valdošās sugas vecums: pirmās komponentes vecums; ja nav — audzes vecums
    vecums = dalas[0].vecums if dalas[0].vecums is not None else n.vecums

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
