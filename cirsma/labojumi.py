"""Lietotāja manuālie labojumi nogabalu tabulā.

Rediģējami lauki: platība, krāja m³/ha, bonitāte, vecums, kailcirte (ieķeksēt /
izķeksēt) un apjoms m³. Pēc labojuma nogabals tiek novērtēts no jauna, un visi
aprēķini (apjomi, sortimenti, iegādes summa) pārrēķinās.

Prioritātes:
  * bonitāte / vecums  -> kailcirtes kritēriji tiek pārvērtēti no jauna;
  * platība / krāja    -> apjoms = krāja × platība (sugu proporcijas saglabājas);
  * apjoms m³          -> manuāli ievadīts apjoms aizstāj aprēķināto;
  * kailcirte          -> manuāls lēmums aizstāj sistēmas lēmumu.
Oriģinālie PDF dati netiek mainīti — labojumi tiek piemēroti nogabalu kopijām.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, fields

from .cirtes import CIRTES_NOSAUKUMI, KAILCIRTE, NECIRST, NOKLUSEJUMA_NOTEIKUMI, Noteikumi
from .parser import Nogabals
from .rules import Vertejums, novertet_nogabalu

BONITATES = ["Ia", "Ib", "I", "II", "III", "IV", "V", "Va"]

LAUKU_NOSAUKUMI = {
    "platiba_ha": "platība", "kraja_m3_ha": "krāja", "bonitate": "bonitāte",
    "vecums": "vecums", "kailcirte": "kailcirte", "apjoms_m3": "apjoms",
    "cirtes_veids": "cirtes veids", "kailcirtes_dalas": "kailcirtes kartē",
}


@dataclass
class Labojums:
    """Viena nogabala labojumi; None = nav labots."""
    platiba_ha: float | None = None
    kraja_m3_ha: float | None = None
    bonitate: str | None = None
    vecums: int | None = None
    kailcirte: bool | None = None       # vecais ķeksis (True = kailcirte, False = necirst)
    apjoms_m3: float | None = None
    cirtes_veids: str | None = None     # kailcirte / kopsana / izlases / nav (None = automātiski)
    kailcirtes_dalas: list[float] | None = None  # no kartes: katra uzzīmētā kailcirte atsevišķi

    def izveletais_veids(self) -> str | None:
        if self.cirtes_veids is not None:
            return self.cirtes_veids
        if self.kailcirte is not None:
            return KAILCIRTE if self.kailcirte else NECIRST
        return None

    def tukss(self) -> bool:
        return all(getattr(self, f.name) is None for f in fields(self))

    def laboti_lauki(self) -> list[str]:
        return [LAUKU_NOSAUKUMI[f.name] for f in fields(self) if getattr(self, f.name) is not None]


def nogabala_atslega(indekss: int) -> str:
    """Stabila nogabala atslēga labojumiem (secība PDF nemainās)."""
    return str(indekss)


def piemerot_labojumu(n: Nogabals, lab: Labojums | None) -> Nogabals:
    """Atgriež nogabala kopiju ar piemērotiem lauku labojumiem."""
    k = copy.deepcopy(n)
    if lab is None:
        return k
    if lab.platiba_ha is not None:
        k.platiba_ha = float(lab.platiba_ha)
        k.labots.add("platiba_ha")
    if lab.kraja_m3_ha is not None:
        k.kraja_m3_ha = float(lab.kraja_m3_ha)
        k.labots.add("kraja_m3_ha")
    if lab.platiba_ha is not None or lab.kraja_m3_ha is not None:
        # PDF kopējā krāja vairs neatbilst — apjomu rēķina no krājas × platības.
        # Sugu krājas saglabājas tikai kā proporcijas.
        k.kopeja_kraja_m3 = None
        if k.kraja_m3_ha is None:
            k.kraja_m3_ha = sum(s.kraja_m3_ha for s in k.sugu_kraja) or None
    if lab.bonitate is not None:
        k.bonitate = lab.bonitate
        k.labots.add("bonitate")
    if lab.vecums is not None:
        k.vecums = int(lab.vecums)
        k.labots.add("vecums")
    if lab.kailcirtes_dalas:
        k.kartes_dalas = [float(x) for x in lab.kailcirtes_dalas]
    return k


def novertet_ar_labojumiem(
    nogabali: list[Nogabals], labojumi: dict[str, Labojums] | None = None,
    nt: Noteikumi | None = None,
) -> list[Vertejums]:
    """Novērtē visus nogabalus, ņemot vērā lietotāja labojumus."""
    labojumi = labojumi or {}
    nt = nt or NOKLUSEJUMA_NOTEIKUMI
    rezultati: list[Vertejums] = []
    for i, n in enumerate(nogabali):
        lab = labojumi.get(nogabala_atslega(i))
        k = piemerot_labojumu(n, lab)
        sistemas = novertet_nogabalu(k, nt=nt)
        if sistemas is None:
            continue
        v = sistemas
        if lab is not None and not lab.tukss():
            lauki = lab.laboti_lauki()
            veids = lab.izveletais_veids()
            for lieks in ("kailcirte", "cirtes veids", "kailcirtes kartē"):
                if lieks in lauki:
                    lauki.remove(lieks)
            if veids is not None and veids != sistemas.cirtes_veids:
                v = novertet_nogabalu(k, veids=veids, nt=nt)
                v.pamatojums = (
                    f"✎ Manuāli: {CIRTES_NOSAUKUMI[veids]} "
                    f"(sistēmas lēmums: {sistemas.cirtes_nosaukums} — {sistemas.pamatojums})"
                    + (f". {v.cirtes_apraksts}" if v.cirtes_apraksts and veids != NECIRST else "")
                )
                lauki.append("cirtes veids")
            v.apjoms_m3_manuali = lab.apjoms_m3
            if lauki:
                v.bridinajumi = ["✎ Manuāli labots: " + ", ".join(lauki)] + v.bridinajumi
        v.indekss = i
        rezultati.append(v)
    return rezultati


def _fmt(lauks: str, vertiba) -> str:
    if vertiba is None:
        return "—"
    if lauks == "kailcirte":
        return "jā" if vertiba else "nē"
    if lauks == "cirtes_veids":
        return CIRTES_NOSAUKUMI.get(vertiba, str(vertiba))
    if lauks == "platiba_ha":
        return f"{float(vertiba):.2f} ha"
    if lauks == "kraja_m3_ha":
        return f"{float(vertiba):.0f} m³/ha"
    if lauks == "apjoms_m3":
        return f"{float(vertiba):.2f} m³"
    if lauks == "vecums":
        return str(int(vertiba))
    return str(vertiba)


def labojumu_izmainas(
    nogabali: list[Nogabals], labojumi: dict[str, Labojums] | None,
    nt: Noteikumi | None = None,
) -> dict[int, list[str]]:
    """Katram labotajam nogabalam — saraksts ar lietotāja izmaiņām "Lauks: vecā → jaunā".

    Uzskaita tikai lietotāja ievadītās vērtības (automātiski pārrēķinātais apjoms
    vai kailcirtes lēmums netiek rādīts kā atsevišķs labojums).
    """
    from .sortiment import vertejuma_apjoms  # sortiment neimportē labojumi — cikla nav

    labojumi = labojumi or {}
    bazes = {v.indekss: v for v in novertet_ar_labojumiem(nogabali, {}, nt)}
    galigie = {v.indekss: v for v in novertet_ar_labojumiem(nogabali, labojumi, nt)}
    rezultats: dict[int, list[str]] = {}
    for i, n in enumerate(nogabali):
        lab = labojumi.get(nogabala_atslega(i))
        if lab is None or lab.tukss() or i not in galigie:
            continue
        rindas = []
        for lauks in ("platiba_ha", "kraja_m3_ha", "bonitate", "vecums", "cirtes_veids", "apjoms_m3"):
            jauna = lab.izveletais_veids() if lauks == "cirtes_veids" else getattr(lab, lauks)
            if jauna is None:
                continue
            if lauks == "cirtes_veids":
                if not galigie[i].pamatojums.startswith("✎"):  # sakrīt ar sistēmas lēmumu
                    continue
                veca = bazes[i].cirtes_veids if i in bazes else None
            elif lauks == "apjoms_m3":
                veca = vertejuma_apjoms(bazes[i])[0] if i in bazes else None
            else:
                veca = getattr(n, lauks)
            if _fmt(lauks, veca) == _fmt(lauks, jauna):
                continue
            rindas.append(f"{LAUKU_NOSAUKUMI[lauks].capitalize()}: "
                          f"{_fmt(lauks, veca)} → {_fmt(lauks, jauna)}")
        if rindas:
            rezultats[i] = rindas
    return rezultats
