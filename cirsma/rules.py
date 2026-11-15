"""Nogabala cirtes veida noteikšana.

Secība (katram nogabalam viens lēmums):
  1. Kailcirte — valdošā suga sasniegusi galvenās cirtes vecumu VAI valdaudzes
     vidējo caurmēru (P/E/B); baltalksnis — ≥ 25 g. VAI ≥ 16 cm. Platību ierobežo
     pēc meža tipa (sausieņi 5 ha, citi 2 ha), lielāku nogabalu sadala (cirtes.py).
  2. Izlases cirte — tikai manuāli izvēlēta (Gkrit + 1).
  3. Kopšanas cirte — ja kailcirte nav atļauta un izcērtamais G ≥ 4 m²/ha (Gmin + 1).
  4. Citādi — necirst.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .cirtes import (
    CIRTES_NOSAUKUMI, IZLASES, KAILCIRTE, KOPSANA, NECIRST, NOKLUSEJUMA_NOTEIKUMI, Noteikumi,
    SkerslaukumaCirte, max_kailcirtes_platiba, sadalit_kailcirtes, skerslaukuma_cirte,
)
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

# Baltalksnim nav noteikta ciršanas vecuma — cērt, kad sasniegts vismaz viens no:
BALTALKSNIS_VECUMS = 25   # gadi
BALTALKSNIS_CAURMERS = 16  # cm


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
    cirtes_veids: str = NECIRST               # kailcirte / kopsana / izlases / nav
    kailcirtes_ha: list[float] = field(default_factory=list)  # kailciršu daļas (ha)
    atdalosa_ha: float = 0.0                  # atdalošās joslas (netiek cirstas)
    max_kailcirte_ha: float | None = None
    sk_cirte: SkerslaukumaCirte | None = None # kopšanas/izlases aprēķins
    kailcirte_pec_kriterijiem: bool = False   # vai kailcirte atļauta pēc vecuma/caurmēra
    manuals_veids: bool = False
    cirtes_apraksts: str = ""                 # platību sadalījums / kopšanas aprēķins

    @property
    def cirtams(self) -> bool:
        return self.cirtes_veids != NECIRST

    @property
    def cirtes_nosaukums(self) -> str:
        return CIRTES_NOSAUKUMI[self.cirtes_veids]

    @property
    def cirsmas_platiba(self) -> float:
        """Faktiski cērtamā platība (kailcirtēm — bez atdalošajām joslām)."""
        if self.cirtes_veids == KAILCIRTE:
            return round(sum(self.kailcirtes_ha), 2)
        if self.cirtes_veids in (KOPSANA, IZLASES):
            return self.nogabals.platiba_ha
        return 0.0


# Kontrolsummu sliekšņi: sugu krājas ir noapaļotas līdz veseliem m³, tāpēc
# mazos nogabalos relatīvā atšķirība var būt liela — prasām abus nosacījumus.
KONTROLE_REL = 0.10
KONTROLE_ABS_M3 = 3.0
JAUNAUDZES_VECUMS = 20


def riska_karogi(n: Nogabals, atlauta: bool, veids: str | None = None) -> list[str]:
    """Papildu pārbaudes, kas lēmumu nemaina, bet jāredz speciālistam."""
    k: list[str] = []
    planots = (n.planots or "").lower()
    if veids is None:
        veids = KAILCIRTE if atlauta else NECIRST

    for josla in n.aizsargjoslas:
        m = re.search(r"\d{8}", josla)
        kods = m.group(0) if m else ""
        nosaukums = josla.rsplit("/", 1)[-1].strip() or josla
        if kods.startswith("4002"):
            k.append(f"⚠ Ūdens objektu aizsargjosla {kods} ({nosaukums}) — kailcirte var būt ierobežota"
                     + ("; apsver izlases cirti" if veids == KAILCIRTE else ""))
        else:
            k.append(f"⚠ Apgrūtinājums {kods} ({nosaukums}) — jāpārbauda ierobežojumi")

    if n.planots:
        if "izlases" in planots and veids != IZLASES:
            k.append(f"ℹ VMD plānotā darbība: {n.planots} — apsver izlases cirti (Cirtes veids)")
        elif veids == KAILCIRTE and "kailcirte" not in planots:
            k.append(f"⚠ VMD plānotā darbība: {n.planots} (nevis kailcirte)")
        elif veids != KAILCIRTE and "kailcirte" in planots:
            k.append("ℹ VMD plāno kailcirti, bet pēc mūsu kritērijiem tā vēl nav atļauta — pārbaudīt")

    if n.plantacija:
        k.append("ℹ Plantācijas audze")
    if veids == KAILCIRTE and n.vecums is not None and n.vecums < JAUNAUDZES_VECUMS:
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


def novertet_nogabalu(n: Nogabals, veids: str | None = None,
                      nt: Noteikumi = NOKLUSEJUMA_NOTEIKUMI) -> Vertejums | None:
    """Novērtē nogabalu un nosaka cirtes veidu. None — nav mežaudze.

    veids — lietotāja izvēlētais cirtes veids (None = automātiski).
    """
    v = _novertet_kriterijus(n)
    if v is None:
        return None
    v.kailcirte_pec_kriterijiem = v.atlauta_kailcirte
    pamats = v.pamatojums
    piezimes: list[str] = []

    if veids is None:
        if v.atlauta_kailcirte:
            veids = KAILCIRTE
        else:
            kops = _sk_cirte(v, n, KOPSANA, nt)
            if isinstance(kops, SkerslaukumaCirte) and kops.atbilst:
                veids = KOPSANA
            else:
                veids = NECIRST
                iemesls = kops if isinstance(kops, str) else (
                    f"izcērtamais G {kops.izcertamais_g:g} < {nt.min_izcertamais_g:g} m²/ha "
                    f"(G {kops.g:g}, Gmin {kops.g_norma}+1)")
                pamats += f". Kopšana: {iemesls}"
    else:
        v.manuals_veids = True

    v.cirtes_veids = veids
    v.atlauta_kailcirte = veids == KAILCIRTE
    if veids == KAILCIRTE:
        max_ha, tips = max_kailcirtes_platiba(n.meza_tips, nt)
        v.max_kailcirte_ha = max_ha
        if n.kartes_dalas:
            # kartē uzzīmētās kailcirtes — katru vērtē atsevišķi (lielāku par max sadala)
            v.kailcirtes_ha, v.atdalosa_ha = [], 0.0
            for d in n.kartes_dalas:
                c, j = sadalit_kailcirtes(d, max_ha, nt)
                v.kailcirtes_ha += c
                v.atdalosa_ha += j
                if d > max_ha + 0.005:
                    piezimes.append(f"⚠ Kartē uzzīmētā kailcirte {d:.2f} ha > {max_ha:g} ha ({tips}) — "
                                    "aprēķinā sadalīta; pārzīmē kartē")
            if len(n.kartes_dalas) > 1:
                pamats += ". Kailcirtes pēc kartes: " + " + ".join(f"{d:.2f}" for d in n.kartes_dalas) + " ha"
        else:
            v.kailcirtes_ha, v.atdalosa_ha = sadalit_kailcirtes(n.platiba_ha, max_ha, nt)
        if not n.kartes_dalas and (len(v.kailcirtes_ha) > 1 or sum(v.kailcirtes_ha) < n.platiba_ha - 0.005):
            dalas = " + ".join(f"{d:.2f}" for d in v.kailcirtes_ha)
            neizm = round(n.platiba_ha - sum(v.kailcirtes_ha) - v.atdalosa_ha, 2)
            pamats += (f". Max kailcirte {max_ha:g} ha ({tips}): cērt {dalas} ha"
                       + (f", atdalošā josla {v.atdalosa_ha:g} ha" if v.atdalosa_ha else "")
                       + (f", neizcērtams atlikums {neizm:g} ha" if neizm > 0.004 else ""))
        if "nav atpazīts" in tips:
            piezimes.append(f"⚠ Max kailcirtes platība: {tips}")
    elif veids in (KOPSANA, IZLASES):
        sk = _sk_cirte(v, n, veids, nt)
        nos = CIRTES_NOSAUKUMI[veids]
        if isinstance(sk, str):
            piezimes.append(f"⚠ {nos}: apjomu nevar aprēķināt — {sk}; ievadi apjomu manuāli")
            pamats += f". {nos}: {sk}"
        else:
            v.sk_cirte = sk
            pamats += f". {nos}: {sk.formula_teksts}"
            if not sk.atbilst:
                piezimes.append(f"⚠ {nos}: izcērtamais G {sk.izcertamais_g:g} m²/ha < "
                                f"{nt.min_izcertamais_g:g} — var neatmaksāties")
            piezimes += [f"ℹ {p}" for p in sk.piezimes]
    v.cirtes_apraksts = pamats[len(v.pamatojums):].removeprefix(". ")
    v.pamatojums = pamats
    v.bridinajumi = piezimes + riska_karogi(n, v.atlauta_kailcirte, veids)
    return v


def _sk_cirte(v: Vertejums, n: Nogabals, veids: str, nt: Noteikumi):
    return skerslaukuma_cirte(veids, v.valdosa_suga, n.vid_augstums, n.skerslaukums,
                              n.platiba_ha, nt)


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

    if suga == "Ba":
        if vecums is not None and vecums >= BALTALKSNIS_VECUMS:
            return Vertejums(n, suga, True, f"{nosaukums}: {vecums} g. ≥ {BALTALKSNIS_VECUMS} g.")
        if n.vid_caurmers is not None and n.vid_caurmers >= BALTALKSNIS_CAURMERS:
            return Vertejums(n, suga, True,
                             f"{nosaukums}: vid. caurmērs {n.vid_caurmers} cm ≥ {BALTALKSNIS_CAURMERS} cm")
        return Vertejums(n, suga, False,
                         f"{nosaukums} nav sasniedzis ne {BALTALKSNIS_VECUMS} g. ({vecums if vecums is not None else '—'} g.), "
                         f"ne {BALTALKSNIS_CAURMERS} cm caurmēru ({n.vid_caurmers if n.vid_caurmers is not None else '—'} cm)")

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
