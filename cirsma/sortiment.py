"""Apjoma aprēķins, sadalījums pa sugām, sortimentu matrica un finanšu aprēķins.

Noklusējuma matricas īpatsvari un cenas atbilst darba devēja pamācības piemēram;
tos var mainīt konfigurācijā (Streamlit saskarnē vai JSON failā).
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from .formula import parse_formula
from .rules import Vertejums

# Sugas kods -> matricas kolonna
MATRICAS_KOLONNA = {
    "P": "P", "E": "E", "B": "B", "Ma": "Ma", "A": "A", "Ba": "Ba",
    "Oz": "Oz/Os", "Os": "Oz/Os",
}
CITI = "Citi"

# Sortimentu iznākuma matrica: kolonna -> {sortiments: (cena EUR/m3, īpatsvars)}
NOKLUSEJUMA_MATRICA: dict[str, dict[str, tuple[float, float]]] = {
    "P": {
        "A klase": (120, 0.03), "Zāģbaļķi": (100, 0.70), "Sīkbaļķi": (80, 0.07),
        "Tara": (60, 0.10), "Papīrmalka": (50, 0.07), "Malka": (38, 0.03),
    },
    "E": {
        "Zāģbaļķi": (100, 0.50), "Sīkbaļķi": (80, 0.15), "Tara": (60, 0.10),
        "Papīrmalka": (50, 0.20), "Malka": (38, 0.05),
    },
    "B": {
        "Finieris A": (150, 0.05), "Finieris B": (110, 0.15), "Finieris C": (90, 0.10),
        "Tara": (50, 0.30), "Papīrmalka": (40, 0.30), "Malka": (38, 0.10),
    },
    "Ma": {
        "Zāģbaļķi": (80, 0.30), "Tara": (50, 0.40), "Malka": (38, 0.30),
    },
    "A": {
        "Zāģbaļķi": (80, 0.20), "Tara": (50, 0.50), "Papīrmalka": (45, 0.20),
        "Malka": (38, 0.10),
    },
    "Ba": {
        "Tara": (50, 0.20), "Malka": (38, 0.80),
    },
    "Oz/Os": {
        "Zāģbaļķi": (200, 0.10), "Tara": (60, 0.60), "Kamīnmalka": (50, 0.30),
    },
    CITI: {
        "Malka": (38, 1.00),
    },
}

NOKLUSEJUMA_IZDEVUMI = {  # EUR/m3
    "Koku ciršana": 11.0,
    "Kokmateriālu pievešana": 7.0,
    "Transports": 6.0,
}
NOKLUSEJUMA_PELNAS_REZERVE = 0.10  # 10% no seguma


@dataclass
class NogabalaApjoms:
    nog_nr: int
    kopejais_m3: float
    pa_sugam: dict[str, float]


@dataclass
class FinansuRezultats:
    apjomi: list[NogabalaApjoms]
    kopejais_m3: float
    pa_sugam_m3: dict[str, float]          # pēc sugu kodiem
    pa_kolonnam_m3: dict[str, float]       # pēc matricas kolonnām
    sortimentu_ienemumi: dict[str, float]  # sortiments -> EUR
    ienemumi_kopa: float
    izdevumi: dict[str, float]             # pozīcija -> EUR
    izdevumi_kopa: float
    pelna: float
    max_iegades_summa: float
    cena_eur_m3: float
    detalas: list[dict] = field(default_factory=list)  # sortimentu rindas tabulai


def aprekinat(
    kailcirtes: list[Vertejums],
    matrica: dict | None = None,
    izdevumi_eur_m3: dict | None = None,
    pelnas_rezerve: float = NOKLUSEJUMA_PELNAS_REZERVE,
) -> FinansuRezultats:
    """Pilns aprēķins: apjomi -> sadalījums pa sugām -> sortimenti -> finanses."""
    matrica = matrica or NOKLUSEJUMA_MATRICA
    izdevumi_eur_m3 = izdevumi_eur_m3 or NOKLUSEJUMA_IZDEVUMI

    apjomi: list[NogabalaApjoms] = []
    pa_sugam: dict[str, float] = defaultdict(float)

    for v in kailcirtes:
        if not v.atlauta_kailcirte:
            continue
        n = v.nogabals
        kopejais = round((n.kraja_m3_ha or 0) * n.platiba_ha, 2)
        sadalijums: dict[str, float] = defaultdict(float)
        for dala in parse_formula(n.formula):
            sadalijums[dala.suga] += kopejais * dala.ipatsvars
        sadalijums = {s: round(m3, 2) for s, m3 in sadalijums.items()}
        apjomi.append(NogabalaApjoms(n.nr, kopejais, dict(sadalijums)))
        for suga, m3 in sadalijums.items():
            pa_sugam[suga] += m3

    pa_kolonnam: dict[str, float] = defaultdict(float)
    for suga, m3 in pa_sugam.items():
        pa_kolonnam[MATRICAS_KOLONNA.get(suga, CITI)] += m3

    sortimentu_ienemumi: dict[str, float] = defaultdict(float)
    detalas: list[dict] = []
    for kolonna, m3 in pa_kolonnam.items():
        for sortiments, (cena, ipatsvars) in matrica.get(kolonna, {}).items():
            s_m3 = m3 * ipatsvars
            eur = s_m3 * cena
            sortimentu_ienemumi[sortiments] += eur
            detalas.append({
                "Suga": kolonna, "Sortiments": sortiments, "Īpatsvars": ipatsvars,
                "Apjoms m3": round(s_m3, 2), "Cena EUR/m3": cena, "Summa EUR": round(eur, 2),
            })

    kopejais_m3 = sum(pa_kolonnam.values())
    ienemumi = sum(sortimentu_ienemumi.values())
    izdevumi = {poz: likme * kopejais_m3 for poz, likme in izdevumi_eur_m3.items()}
    izdevumi_kopa = sum(izdevumi.values())
    segums = ienemumi - izdevumi_kopa
    pelna = segums * pelnas_rezerve
    max_summa = segums - pelna

    return FinansuRezultats(
        apjomi=apjomi,
        kopejais_m3=round(kopejais_m3, 2),
        pa_sugam_m3={
            s: round(pa_sugam[s], 2)
            for s in sorted(pa_sugam, key=lambda x: -pa_sugam[x])
        },
        pa_kolonnam_m3={k: round(m3, 2) for k, m3 in sorted(pa_kolonnam.items())},
        sortimentu_ienemumi={s: round(e, 2) for s, e in sortimentu_ienemumi.items()},
        ienemumi_kopa=round(ienemumi, 2),
        izdevumi={p: round(e, 2) for p, e in izdevumi.items()},
        izdevumi_kopa=round(izdevumi_kopa, 2),
        pelna=round(pelna, 2),
        max_iegades_summa=round(max_summa, 2),
        cena_eur_m3=round(max_summa / kopejais_m3, 2) if kopejais_m3 else 0.0,
        detalas=detalas,
    )
