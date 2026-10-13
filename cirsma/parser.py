"""Meža inventarizācijas PDF (VMD "Nogabalu raksturojošie rādītāji") parsēšana.

Pieeja: pdfplumber izvelk tekstu ar saglabātu izkārtojumu; nogabalu rindas
atpazīst pēc struktūras (nogabala nr., platība, "Mežaudze", meža tips, formula,
izcelšanās, bonitāte, skaitliskās kolonnas). Formulas turpinājums nākamajā
rindā (piem., "1A47") tiek pievienots pie iepriekšējā nogabala formulas.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import pdfplumber

from .formula import _parse_bloks

_BONITATES = ("Ia", "Ib", "IV", "III", "II", "I", "Va", "V")  # garākās vispirms

# Galvenā nogabala rinda:
#  nr  platība  Mežaudze  tips  <formula>  izcelšanās  bonitāte  augst  caurm  vecums  <pārējais>
_ROW_RE = re.compile(
    r"^\s*(?P<nog>\d{1,3})\s+"
    r"(?P<platiba>\d+(?:[.,]\d+)?)\s+"
    r"(?P<veids>Mežaudze)\s+"
    r"(?P<tips>\S+)\s+"
    r"(?P<formula>.+?)\s+"
    r"(?P<izcelsanas>[A-Z])\s+"
    r"(?P<bonitate>" + "|".join(_BONITATES) + r")\s+"
    r"(?P<augstums>\d+)\s+"
    r"(?P<caurmers>\d+)\s+"
    r"(?P<vecums>\d+)\s+"
    r"(?P<aste>.*)$"
)

# Rindas, kas nav taksācijas dati (metadati zem nogabala)
_SKIP_PREFIXES = (
    "Pēdējais", "Platību", "Aizs.", "Atjaunots", "Kopā", "Pavisam",
    "Zemes vienība", "Kvartāls", "Nogabalu", "Meža zemes",
)

# Formulas turpinājuma rinda — tikai formulas fragmenti, nekas cits.
# Fragmentā var būt vairākas salipušas grupas (piem., "1E911E131" = "1E91 1E131"),
# tāpēc katru vārdu pārbauda ar formulas parsētāju, nevis ar vienu regex.
_CONT_TOKEN_RE = re.compile(r"^\d{1,2}[A-ZĀČĒĢĪĶĻŅŠŪŽ][0-9A-Za-zĀČĒĢĪĶĻŅŠŪŽāčēģīķļņšūž]*$")


def _formulas_turpinajums(stripped: str) -> str | None:
    """Atgriež rindu kā formulas turpinājumu, ja tā sastāv tikai no formulas blokiem."""
    tokeni = stripped.split()
    if not tokeni:
        return None
    for t in tokeni:
        if not _CONT_TOKEN_RE.match(t) or not _parse_bloks(t):
            return None
    return " ".join(tokeni)

# Nogabals bez mežaudzes (lauce, purvs u.tml.) — nr + platība + apraksts bez skaitļiem
_NONFOREST_RE = re.compile(r"^\s*(?P<nog>\d{1,3})\s+(?P<platiba>\d+(?:[.,]\d+)?)\s+(?P<veids>[A-ZĀ][^\d]+?)\s*$")


@dataclass
class Nogabals:
    nr: int
    platiba_ha: float
    zemes_veids: str
    meza_tips: str | None = None
    formula: str | None = None
    izcelsanas: str | None = None
    bonitate: str | None = None
    vid_augstums: int | None = None
    vid_caurmers: int | None = None
    vecums: int | None = None
    kraja_m3_ha: float | None = None
    piezimes: list[str] = field(default_factory=list)

    @property
    def ir_mezaudze(self) -> bool:
        return self.zemes_veids == "Mežaudze"


@dataclass
class Inventarizacija:
    zemes_vieniba: str | None
    ipasums: str | None
    nogabali: list[Nogabals]


def _norm_num(s: str) -> float:
    return float(s.replace(",", "."))


def parse_inventory_pdf(pdf_path: str) -> Inventarizacija:
    """Nolasa inventarizācijas PDF un atgriež strukturētus nogabalu datus."""
    lines: list[str] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text(layout=True) or ""
            lines.extend(text.splitlines())

    zemes_vieniba = None
    ipasums = None
    nogabali: list[Nogabals] = []
    pedejais: Nogabals | None = None

    for raw in lines:
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped:
            continue

        if zemes_vieniba is None:
            m = re.search(r"Zemes vienības apzīmējums\s*[-–]?\s*(\d+)", stripped)
            if m:
                zemes_vieniba = m.group(1)
        if ipasums is None:
            m = re.search(r"Īpašums\s*[-–]\s*\d+\s*[-–]\s*(\S+)", stripped)
            if m:
                ipasums = m.group(1)

        # Galvenā nogabala rinda ar mežaudzi
        m = _ROW_RE.match(line)
        if m:
            aste_skaitli = re.findall(r"\d+(?:[.,]\d+)?", m.group("aste"))
            kraja = _norm_num(aste_skaitli[-1]) if aste_skaitli else None
            pedejais = Nogabals(
                nr=int(m.group("nog")),
                platiba_ha=_norm_num(m.group("platiba")),
                zemes_veids="Mežaudze",
                meza_tips=m.group("tips"),
                formula=m.group("formula").strip(),
                izcelsanas=m.group("izcelsanas"),
                bonitate=m.group("bonitate"),
                vid_augstums=int(m.group("augstums")),
                vid_caurmers=int(m.group("caurmers")),
                vecums=int(m.group("vecums")),
                kraja_m3_ha=kraja,
            )
            nogabali.append(pedejais)
            continue

        # Metadatu rindas — pievieno kā piezīmes pēdējam nogabalam
        if any(stripped.startswith(p) for p in _SKIP_PREFIXES):
            if pedejais is not None and not stripped.startswith(("Kopā", "Pavisam")):
                pedejais.piezimes.append(stripped)
            continue

        # Formulas turpinājums (piem., "1A47" nākamajā rindā zem formulas)
        turp = _formulas_turpinajums(stripped)
        if turp and pedejais is not None and pedejais.formula is not None:
            pedejais.formula += " " + turp
            continue

        # Ne-meža nogabals (lauce u.tml.) — var būt sadalīts vairākās rindās,
        # pietiek ar pirmo rindu, kur ir nr + platība
        mn = _NONFOREST_RE.match(line)
        if mn and not any(k in stripped for k in ("kvartāls", "pagasts", "Saimniecība")):
            pedejais = Nogabals(
                nr=int(mn.group("nog")),
                platiba_ha=_norm_num(mn.group("platiba")),
                zemes_veids=mn.group("veids").strip(),
            )
            nogabali.append(pedejais)
            continue

    if not nogabali:
        raise ValueError(
            f"No {pdf_path} neizdevās nolasīt nevienu nogabalu — "
            "iespējams, cits PDF formāts vai skenēts dokuments (nepieciešams OCR)."
        )
    return Inventarizacija(zemes_vieniba=zemes_vieniba, ipasums=ipasums, nogabali=nogabali)
