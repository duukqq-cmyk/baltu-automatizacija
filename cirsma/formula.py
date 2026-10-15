"""Mežaudzes formulas parsēšana.

Formula, piem., "4Ba3B37 2Ba26 1A47" nozīmē:
  40% Baltalksnis (37 g.), 30% Bērzs (37 g.), 20% Baltalksnis (26 g.), 10% Apse (47 g.)

Katrs ar atstarpi atdalītais bloks satur vienu vai vairākus (koeficients, suga)
pārus un beidzas ar vecumu gados. Koeficients ir daļa desmitdaļās (1 = 10%).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Sugu kodi — garākie vispirms, lai "Ba" nenolasītos kā "B" + "a"
SUGU_KODI = [
    "Ba", "Bl", "Ma", "Oz", "Os", "Vī", "Vi", "Go", "Kļ", "Sa", "Ie", "Pī",
    "P", "E", "B", "A", "L", "K", "V", "M",
]
SUGU_NOSAUKUMI = {
    "P": "Priede", "E": "Egle", "B": "Bērzs", "A": "Apse", "Ba": "Baltalksnis",
    "Ma": "Melnalksnis", "M": "Melnalksnis", "Oz": "Ozols", "Os": "Osis", "L": "Liepa", "K": "Kļava",
    "Go": "Goba", "V": "Vīksna", "Vī": "Vīksna", "Bl": "Blīgzna", "Sa": "Baltais vītols",
    "Ie": "Ieva", "Pī": "Pīlādzis",
}

_PAIR_RE = re.compile(r"(\d{1,2})(" + "|".join(SUGU_KODI) + r")")


@dataclass(frozen=True)
class FormulasDala:
    """Viena formulas komponente: suga ar īpatsvaru un vecumu."""
    suga: str        # sugas kods, piem., "Ba"
    ipatsvars: float # daļa no 0 līdz 1 (koeficients / 10)
    vecums: int | None


def _parse_bloks(bloks: str) -> list[list[tuple[list[tuple[int, str]], int | None]]]:
    """Atrod visus derīgos bloka parsējumus.

    Gramatika: bloks = viena vai vairākas grupas; grupa = (koef, suga)+ vecums.
    PDF ekstrakcijā atstarpe starp grupām var pazust ("4Ba3B372Ba26"),
    tāpēc izmantojam atkāpšanās (backtracking) parsētāju.
    Atgriež parsējumu sarakstu; katrs parsējums = [(pāri, vecums), ...].
    """
    rezultati: list = []

    def rec(i: int, grupas: list, pari: list) -> None:
        if i == len(bloks):
            if pari:  # pēdējai grupai vecums var nebūt norādīts
                rezultati.append(grupas + [(pari, None)])
            elif grupas:
                rezultati.append(grupas)
            return
        m = _PAIR_RE.match(bloks, i)
        if m:  # nākamais (koeficients, suga) pāris
            rec(m.end(), grupas, pari + [(int(m.group(1)), m.group(2))])
        if pari:  # vecums (1–3 cipari); biežākais ir 2 cipari, tāpēc to mēģina pirmo
            for garums in (2, 3, 1):
                cipari = bloks[i:i + garums]
                if len(cipari) == garums and cipari.isdigit():
                    rec(i + garums, grupas + [(pari, int(cipari))], [])

    rec(0, [], [])
    return rezultati


def parse_formula(formula: str) -> list[FormulasDala]:
    """Parsē mežaudzes formulu par komponentu sarakstu.

    >>> parse_formula("4Ba3B37 2Ba26 1A47")  # doctest: +SKIP
    [FormulasDala('Ba', 0.4, 37), FormulasDala('B', 0.3, 37),
     FormulasDala('Ba', 0.2, 26), FormulasDala('A', 0.1, 47)]
    """
    import itertools

    # Daļa pēc "+" (piem., "7B2E1P75+M75") = sugas zem 5% no krājas — koeficienta
    # nav, kopsummā 10 neietilpst. Apjoma sadalījumā tās netiek ņemtas vērā.
    formula = formula.split("+", 1)[0]

    bloku_varianti = []
    for bloks in formula.split():
        varianti = _parse_bloks(bloks)
        if not varianti:
            raise ValueError(f"Nevar parsēt formulas bloku: {bloks!r} (formulā {formula!r})")
        bloku_varianti.append(varianti)

    # Izvēlas bloku parsējumu kombināciju, kur koeficientu summa ir tieši 10
    izvele = None
    for kombinacija in itertools.product(*bloku_varianti):
        summa = sum(koef for parsejums in kombinacija for pari, _ in parsejums for koef, _ in pari)
        if summa == 10:
            izvele = kombinacija
            break
    if izvele is None:
        raise ValueError(
            f"Formulai {formula!r} nav parsējuma ar koeficientu summu 10 — "
            "nepieciešama manuāla pārbaude"
        )

    dalas: list[FormulasDala] = []
    for parsejums in izvele:
        for pari, vecums in parsejums:
            for koef, suga in pari:
                dalas.append(FormulasDala(suga=suga, ipatsvars=koef / 10, vecums=vecums))
    return dalas


def piejaukums(formula: str) -> list[tuple[str, int | None]]:
    """Sugas zem 5% (formulas daļa pēc "+"), piem., "+Ba54M54" -> [("Ba", 54), ("M", 54)]."""
    if "+" not in formula:
        return []
    aste = re.sub(r"\s+", "", formula.split("+", 1)[1])
    kodi = "|".join(SUGU_KODI)
    return [(m.group(1), int(m.group(2)) if m.group(2) else None)
            for m in re.finditer(r"(" + kodi + r")(\d{0,3})", aste)]


def valdosa_suga(formula: str) -> str:
    """Valdošā suga = pirmā (lielākā) komponente formulā."""
    return parse_formula(formula)[0].suga
