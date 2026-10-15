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
class SugasKraja:
    """Faktiskā krāja vienai sugai (ja avots to sniedz, piem., gabali.lv)."""
    suga: str
    kraja_m3_ha: float
    kraja_m3: float | None = None      # kopējā krāja nogabalā
    skerslaukums: float | None = None  # m²/ha


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
    # --- Papildu atribūti (aizpildīti, ja avotā tādi ir) ---
    kvartals: str | None = None
    avots: str = "VMD"
    kopeja_kraja_m3: float | None = None
    bieziba: float | None = None
    skerslaukums: float | None = None
    koku_skaits: int | None = None
    sugu_kraja: list[SugasKraja] = field(default_factory=list)
    planots: str | None = None              # VMD plānotā darbība
    aizsargjoslas: list[str] = field(default_factory=list)
    plantacija: bool = False
    otrais_stavs: str | None = None
    pedeja_cirte: str | None = None
    pedeja_darbiba: str | None = None
    bojajumi: list[str] = field(default_factory=list)
    komentari: str | None = None
    inventarizacija: str | None = None      # "Nogabala meža inventarizācija veikta 2026. gadā."
    labots: set[str] = field(default_factory=set)  # lietotāja manuāli labotie lauki

    @property
    def pdf_apraksts(self) -> list[str]:
        """Papildu informācija zem nogabala rindas PDF (gabali.lv), tādā pašā secībā."""
        rindas = [self.inventarizacija] if self.inventarizacija else []
        return rindas + list(self.piezimes) if self.avots == "gabali.lv" else rindas

    @property
    def ir_mezaudze(self) -> bool:
        return self.zemes_veids == "Mežaudze"

    @property
    def apzimejums(self) -> str:
        """Nogabala apzīmējums atskaitē: "3.kv. 12" vai vienkārši "12"."""
        return f"{self.kvartals}.kv. {self.nr}" if self.kvartals else str(self.nr)


@dataclass
class Inventarizacija:
    zemes_vieniba: str | None
    ipasums: str | None
    nogabali: list[Nogabals]
    avots: str = "VMD"

    @property
    def vairaki_kvartali(self) -> bool:
        return len({n.kvartals for n in self.nogabali}) > 1


def _norm_num(s: str) -> float:
    return float(s.replace(",", "."))


def parse_inventory_pdf(pdf_path: str) -> Inventarizacija:
    """Nolasa inventarizācijas PDF (formātu atpazīst automātiski: VMD vai gabali.lv)."""
    from .gabali import ir_gabali_formats, parse_gabali_pdf

    with pdfplumber.open(pdf_path) as pdf:
        gabali = bool(pdf.pages) and ir_gabali_formats(pdf)
    if gabali:
        return parse_gabali_pdf(pdf_path)
    return parse_vmd_pdf(pdf_path)


def parse_vmd_pdf(pdf_path: str) -> Inventarizacija:
    """Nolasa VMD "Nogabalu raksturojošie rādītāji" PDF."""
    lines: list[str] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text(layout=True) or ""
            lines.extend(text.splitlines())

    zemes_vieniba = None
    ipasums = None
    nogabali: list[Nogabals] = []
    pedejais: Nogabals | None = None
    kvartals: str | None = None

    for raw in lines:
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped:
            continue

        mkv = re.fullmatch(r"(\d+)\.\s*kvartāls", stripped)
        if mkv:
            kvartals = mkv.group(1)
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
                kvartals=kvartals,
            )
            nogabali.append(pedejais)
            continue

        # Metadatu rindas — pievieno kā piezīmes pēdējam nogabalam
        if any(stripped.startswith(p) for p in _SKIP_PREFIXES):
            if pedejais is not None and not stripped.startswith(("Kopā", "Pavisam")):
                pedejais.piezimes.append(stripped)
                if stripped.startswith("Aizs."):
                    pedejais.aizsargjoslas.append(re.sub(r"^Aizs\.\s*paz\.\s*[-:]?\s*", "", stripped))
                elif stripped.startswith("Pēdējais cirtes") or stripped.startswith("Pēdējaiscirtes"):
                    pedejais.pedeja_cirte = stripped.split(":", 1)[-1].strip()
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
                kvartals=kvartals,
            )
            nogabali.append(pedejais)
            continue

    if not nogabali:
        raise ValueError(
            f"No {pdf_path} neizdevās nolasīt nevienu nogabalu — "
            "iespējams, cits PDF formāts vai skenēts dokuments (nepieciešams OCR)."
        )
    return Inventarizacija(zemes_vieniba=zemes_vieniba, ipasums=ipasums, nogabali=nogabali)
