"""Līgumu / dokumentu strukturētu datu izvilkšana no PDF (2. uzdevums).

Divi ekstrakcijas režīmi:
1. Deterministiskais (regex heiristikas) — strādā bez ārējiem servisiem,
   labi tipveida latviešu līgumiem; katram laukam validācijas piezīmes.
2. MI režīms (Claude API, ja lietotājs ievada API atslēgu) — noturīgs pret
   brīvu formātu; atbilde tiek validēta pret JSON struktūru.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

import pdfplumber

_MENESI = {
    "janvār": 1, "februār": 2, "mart": 3, "aprīl": 4, "maij": 5, "jūnij": 6,
    "jūlij": 7, "august": 8, "septembr": 9, "oktobr": 10, "novembr": 11, "decembr": 12,
}
_LOMAS = [
    "Pārdevējs", "Pircējs", "Iznomātājs", "Nomnieks", "Pasūtītājs",
    "Izpildītājs", "Aizdevējs", "Aizņēmējs", "Piegādātājs",
]


@dataclass
class LigumaDati:
    fails: str
    liguma_veids: str | None = None
    datums: str | None = None
    puses: list[dict] = field(default_factory=list)
    summa_eur: float | None = None
    summas_konteksts: str | None = None
    termins: str | None = None
    ipasie_nosacijumi: list[str] = field(default_factory=list)
    piezimes: list[str] = field(default_factory=list)  # validācijas brīdinājumi


def _teksts_no_pdf(pdf_cels: str) -> str:
    with pdfplumber.open(pdf_cels) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)


def _atrast_datumu(teksts: str) -> str | None:
    # "2026. gada 15. maijā" / "15.05.2026"
    m = re.search(r"(\d{4})\.\s*gada\s+(\d{1,2})\.\s*([a-zāēīūč]+)", teksts, re.I)
    if m:
        for saknes, nr in _MENESI.items():
            if m.group(3).lower().startswith(saknes):
                return f"{int(m.group(2)):02d}.{nr:02d}.{m.group(1)}"
    m = re.search(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b", teksts)
    if m:
        return f"{int(m.group(1)):02d}.{int(m.group(2)):02d}.{m.group(3)}"
    return None


def _atrast_puses(teksts: str) -> list[dict]:
    puses = []
    # Katram uzņēmumam (forma + nosaukums + reģ. nr.) meklē lomu tuvākajā
    # apkārtnē: "turpmāk — <Loma>" aiz nosaukuma vai "<Loma>" pirms tā.
    for m in re.finditer(
        r"\b(SIA|AS|IK|ZS)\s+[\"“„]([^\"”]+)[\"”“][^\n]{0,120}?"
        r"[Rr]e[ģg]\w*\.?\s*[Nn]r\.?\s*([\d\s]{8,14})", teksts, re.S,
    ):
        aiz = teksts[m.end():m.end() + 250]
        pirms = teksts[max(0, m.start() - 120):m.start()]
        loma = "?"
        ml = re.search(r"turpmāk\s*[—–-]?\s*(?:tekstā\s*)?[\"“]?(" + "|".join(_LOMAS) + r")", aiz)
        if ml:
            loma = ml.group(1)
        else:
            for kandidats in _LOMAS:
                if kandidats in pirms:
                    loma = kandidats
                    break
        puses.append({
            "loma": loma,
            "nosaukums": f"{m.group(1)} \"{m.group(2).strip()}\"",
            "reg_nr": re.sub(r"\s", "", m.group(3)),
        })
    return puses


def _naudas_summa(s: str) -> float:
    s = s.replace(" ", "").replace(" ", "")
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    return float(s)


def _atrast_summu(teksts: str) -> tuple[float | None, str | None]:
    """Meklē līguma summu; priekšroka summām ar skaidru kontekstu."""
    kandidati: list[tuple[float, str]] = []
    for m in re.finditer(r"([\d\s.,]{2,15})\s*(?:EUR|eiro|euro|€)", teksts, re.I):
        try:
            summa = _naudas_summa(m.group(1).strip(" ."))
        except ValueError:
            continue
        konteksts = teksts[max(0, m.start() - 90):m.start()].replace("\n", " ").lower()
        kandidati.append((summa, konteksts))
    if not kandidati:
        return None, None
    ATSLEGVARDI = ("līguma summa", "pirkuma maksa", "kopējā summa", "nomas maksa", "cena")
    for summa, konteksts in kandidati:
        for v in ATSLEGVARDI:
            if v in konteksts:
                return summa, v
    lielaka = max(kandidati, key=lambda k: k[0])
    return lielaka[0], "lielākā atrastā summa (pārbaudīt!)"


def _atrast_terminu(teksts: str) -> str | None:
    m = re.search(
        r"(?:termiņ\w*|spēkā)\s*[^\n.]{0,80}?līdz\s+"
        r"((?:\d{4}\.\s*gada\s+\d{1,2}\.\s*[a-zāēīūčžš]+)|[^\n.;]{4,60})",
        teksts, re.I)
    if m:
        return m.group(1).strip()
    m = re.search(r"(\d+)\s*(darba\s+)?dien\w+\s+laikā", teksts, re.I)
    if m:
        return m.group(0)
    return None


def _ipasie_nosacijumi(teksts: str) -> list[str]:
    ATSLEGVARDI = ("līgumsod", "soda naud", "avans", "drošības naud",
                   "konfidencialitāt", "priekšapmaks", "garantij", "ķīl")
    rezultats = []
    for rinda in teksts.splitlines():
        if any(v in rinda.lower() for v in ATSLEGVARDI):
            rinda = rinda.strip()
            if rinda and rinda not in rezultats:
                rezultats.append(rinda)
    return rezultats[:8]


def _liguma_veids(teksts: str) -> str | None:
    m = re.search(r"^[^\n]{0,60}?([A-ZĀČĒĢĪĶĻŅŠŪŽ][^\n]*L[ĪI]GUMS)", teksts, re.M | re.I)
    return m.group(1).strip().title() if m else None


def ekstrakcija_regex(pdf_cels: str, fails: str | None = None) -> LigumaDati:
    """Deterministiskā ekstrakcija ar regex heiristikām + validācijas piezīmes."""
    teksts = _teksts_no_pdf(pdf_cels)
    d = LigumaDati(fails=fails or pdf_cels)
    if len(teksts.strip()) < 100:
        d.piezimes.append("PDF satur maz teksta — iespējams, skenēts dokuments (vajag OCR)")
        return d

    d.liguma_veids = _liguma_veids(teksts)
    d.datums = _atrast_datumu(teksts)
    d.puses = _atrast_puses(teksts)
    d.summa_eur, d.summas_konteksts = _atrast_summu(teksts)
    d.termins = _atrast_terminu(teksts)
    d.ipasie_nosacijumi = _ipasie_nosacijumi(teksts)

    # Validācija — katrs tukšais vai apšaubāmais lauks tiek marķēts
    if not d.puses:
        d.piezimes.append("Nav atrastas līguma puses — manuāla pārbaude")
    elif any(p["loma"] == "?" for p in d.puses):
        d.piezimes.append("Pušu lomas nav droši noteiktas")
    for p in d.puses:
        if len(p["reg_nr"]) != 11:
            d.piezimes.append(f"Reģ. nr. {p['reg_nr']} nav 11 ciparu — pārbaudīt")
    if d.summa_eur is None:
        d.piezimes.append("Nav atrasta līguma summa — manuāla pārbaude")
    elif d.summas_konteksts and "pārbaudīt" in d.summas_konteksts:
        d.piezimes.append("Summa noteikta bez skaidra konteksta — pārbaudīt")
    if d.datums is None:
        d.piezimes.append("Nav atrasts līguma datums")
    if d.termins is None:
        d.piezimes.append("Nav atrasts termiņš")
    return d


def ekstrakcija_ai(pdf_cels: str, api_key: str, fails: str | None = None) -> LigumaDati:
    """Ekstrakcija ar Claude API (nepieciešama `anthropic` pakotne un API atslēga)."""
    import anthropic  # noqa: PLC0415 — lai pakotne būtu vajadzīga tikai MI režīmam

    teksts = _teksts_no_pdf(pdf_cels)[:30000]
    klients = anthropic.Anthropic(api_key=api_key)
    atbilde = klients.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=1500,
        messages=[{"role": "user", "content": (
            "Izvelc no šī līguma teksta datus un atbildi TIKAI ar JSON objektu ar "
            "laukiem: liguma_veids (str), datums (DD.MM.GGGG), puses (saraksts ar "
            "{loma, nosaukums, reg_nr}), summa_eur (skaitlis), termins (str), "
            "ipasie_nosacijumi (saraksts ar str). Ja lauks nav atrodams — null.\n\n"
            f"LĪGUMA TEKSTS:\n{teksts}"
        )}],
    )
    dati = json.loads(re.search(r"\{.*\}", atbilde.content[0].text, re.S).group(0))
    d = LigumaDati(
        fails=fails or pdf_cels,
        liguma_veids=dati.get("liguma_veids"),
        datums=dati.get("datums"),
        puses=dati.get("puses") or [],
        summa_eur=dati.get("summa_eur"),
        termins=dati.get("termins"),
        ipasie_nosacijumi=dati.get("ipasie_nosacijumi") or [],
    )
    # Krusteniskā validācija pret deterministisko ekstrakciju
    regex_d = ekstrakcija_regex(pdf_cels, fails)
    if (d.summa_eur and regex_d.summa_eur
            and abs(d.summa_eur - regex_d.summa_eur) > 0.01
            and regex_d.summas_konteksts
            and "pārbaudīt" not in (regex_d.summas_konteksts or "")):
        d.piezimes.append(
            f"MI summa {d.summa_eur} nesakrīt ar regex summu {regex_d.summa_eur} — pārbaudīt")
    return d


def epasta_kopsavilkums(rezultati: list[LigumaDati]) -> str:
    """Sagatavo e-pasta kopsavilkuma tekstu par apstrādātajiem līgumiem."""
    rindas = ["Labdien!", "", "Automātiskais kopsavilkums par apstrādātajiem līgumiem:", ""]
    for d in rezultati:
        rindas.append(f"• {d.fails}")
        if d.liguma_veids:
            rindas.append(f"    Veids: {d.liguma_veids}")
        if d.datums:
            rindas.append(f"    Datums: {d.datums}")
        for p in d.puses:
            rindas.append(f"    {p['loma']}: {p['nosaukums']} (reģ. nr. {p['reg_nr']})")
        if d.summa_eur is not None:
            rindas.append(f"    Summa: {d.summa_eur:,.2f} EUR".replace(",", " "))
        if d.termins:
            rindas.append(f"    Termiņš: {d.termins}")
        for n in d.ipasie_nosacijumi:
            rindas.append(f"    Īpašais nosacījums: {n}")
        for pz in d.piezimes:
            rindas.append(f"    ⚠ {pz}")
        rindas.append("")
    rindas.append("Šis kopsavilkums ģenerēts automātiski — laukus ar ⚠ lūdzu pārbaudīt manuāli.")
    return "\n".join(rindas)


def excel_ligumi(cels: str, rezultati: list[LigumaDati]) -> None:
    """Saglabā izvilktos datus Excel tabulā (viena rinda = viens līgums)."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    wb = Workbook()
    ws = wb.active
    ws.title = "Līgumu dati"
    galvas = ["Fails", "Līguma veids", "Datums", "Puses", "Summa EUR",
              "Termiņš", "Īpašie nosacījumi", "Piezīmes (validācija)"]
    for c, g in enumerate(galvas, start=1):
        cell = ws.cell(1, c, g)
        cell.font = Font(bold=True)
        cell.fill = PatternFill("solid", fgColor="D9E1F2")
    for r, d in enumerate(rezultati, start=2):
        puses = "; ".join(f"{p['loma']}: {p['nosaukums']} ({p['reg_nr']})" for p in d.puses)
        ws.cell(r, 1, d.fails)
        ws.cell(r, 2, d.liguma_veids)
        ws.cell(r, 3, d.datums)
        ws.cell(r, 4, puses)
        ws.cell(r, 5, d.summa_eur)
        ws.cell(r, 6, d.termins)
        ws.cell(r, 7, " | ".join(d.ipasie_nosacijumi))
        ws.cell(r, 8, " | ".join(d.piezimes))
    for kol, w in zip("ABCDEFGH", [24, 26, 12, 55, 12, 30, 50, 45]):
        ws.column_dimensions[kol].width = w
    wb.save(cels)
