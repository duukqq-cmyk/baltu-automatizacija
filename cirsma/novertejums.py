"""Cirsmas novērtējuma (Mežvērte "CIRSMAS NOVĒRTĒJUMS") PDF nolasīšana un summēšana.

Viens PDF = viens nogabals. Lietotājs ielādē vairākus, un sistēma saskaita
nogabalus, platības un (pēc izvēles) vērtības, krājas, sortimentus u.c.

Tīra loģika bez Streamlit — UI ir views/novertejums.py.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field

import pdfplumber

# ---------------------------------------------------------------------------
# Skaitļi
# ---------------------------------------------------------------------------

_DEC_RE = re.compile(r"^-?\d+[.,]\d+$")
_INT_RE = re.compile(r"^-?\d+$")


def skaitlis(s: str | None) -> float | None:
    """'35 038,99' -> 35038.99 ; '0.52' -> 0.52 ; '' -> None"""
    if s is None:
        return None
    s = s.replace(" ", " ").replace(" ", "").strip().replace(",", ".")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def fmt(v: float | None, dec: int = 2) -> str:
    """Latviskais formāts: atstarpe tūkstošiem, komats decimāldaļai."""
    if v is None or v != v:  # None vai NaN
        return "—"
    return f"{v:,.{dec}f}".replace(",", " ").replace(".", ",")


def _skaits_un_decimali(tokeni: list[str]) -> tuple[int | None, list[float]]:
    """Koku skaits var būt ar tūkstošu atstarpi ('1 453 751,52 ...'), tāpēc visus
    veselos skaitļus pirms pirmā decimālskaitļa savienojam vienā."""
    daļas: list[str] = []
    i = 0
    while i < len(tokeni) and _INT_RE.match(tokeni[i]):
        daļas.append(tokeni[i])
        i += 1
    skaits = int("".join(daļas)) if daļas else None
    decimali = [v for v in (skaitlis(t) for t in tokeni[i:]) if v is not None]
    return skaits, decimali


def _veselie_beigas(tokeni: list[str]) -> list[int]:
    """Veselie skaitļi aiz pēdējā decimālskaitļa — saglabājamo koku skaits."""
    pedejais = max((i for i, t in enumerate(tokeni) if _DEC_RE.match(t)), default=-1)
    return [int(t) for t in tokeni[pedejais + 1:] if _INT_RE.match(t)]


# ---------------------------------------------------------------------------
# Datu modelis
# ---------------------------------------------------------------------------

# Sugu tabulas kolonnas aiz koku skaita (secība kā PDF)
SUGU_KOLONNAS = [
    "kraja",        # Stumbra krāja, kopā
    "lietkoksne",   # Lietkoksne kopā
    "ip_kval",
    "resna",
    "videja",
    "tieva",
    "p_malka",
    "malka",
    "atlikumi",
    "pardosanai",   # Paredzēts pārdošanai
    "vid_koks",     # Vidējais koks (m3)
]


@dataclass
class Novertejums:
    fails: str
    saimnieciba: str = ""
    ipasnieks: str = ""
    novads: str = ""
    pagasts: str = ""
    kadastrs: str = ""
    kvartals: str = ""
    nogabals: str = ""
    a_nogabals: str = ""
    platiba: float | None = None
    uzmerija: str = ""
    datums: str = ""
    cirtes_veids: str = ""
    koku_skaits: int | None = None
    kopa: dict = field(default_factory=dict)       # "Kopā:" rinda
    sugas: list = field(default_factory=list)      # [{suga, skaits, kraja, ...}]
    saglabajamie: int | None = None
    cirsmas_kraja: float | None = None
    cirsmas_vertiba: float | None = None
    biomasas_apjoms: float | None = None
    biomasas_vertiba: float | None = None
    vertiba_kopa: float | None = None
    bridinajumi: list = field(default_factory=list)

    @property
    def nosaukums(self) -> str:
        nog = self.nogabals or "?"
        if self.a_nogabals and self.a_nogabals != "0":
            nog = f"{nog}/{self.a_nogabals}"
        return f"{self.kvartals or '?'}. kv. {nog}. nog."

    @property
    def atslega(self) -> tuple:
        return (self.kadastrs, self.kvartals, self.nogabals, self.a_nogabals)


# ---------------------------------------------------------------------------
# Parsētājs
# ---------------------------------------------------------------------------

def _nem(pattern: str, teksts: str, flags=0) -> str:
    m = re.search(pattern, teksts, flags)
    return m.group(1).strip() if m else ""


_SUGAS_RE = re.compile(
    r"^([A-ZĀČĒĢĪĶĻŅŠŪŽ][a-zāčēģīķļņšūž]+(?:\s[a-zāčēģīķļņšūž]+)?)\s+(\d[\d\s,.]*)$"
)


def parse_novertejums_teksts(teksts: str, fails: str = "") -> Novertejums:
    if "CIRSMAS NOVĒRTĒJUMS" not in teksts.upper():
        raise ValueError("Neizskatās pēc Mežvērtes 'Cirsmas novērtējums' PDF.")

    n = Novertejums(fails=fails)
    n.saimnieciba = _nem(r"Saimniecība:\s*(.*?)\s*Īpašnieks:", teksts)
    n.ipasnieks = _nem(r"Īpašnieks:\s*(.*?)\s*Uzmērīja:", teksts)
    n.uzmerija = _nem(r"Īpašnieks:.*?Uzmērīja:\s*([^\n]+?)\s*$", teksts, re.M)
    n.novads = _nem(r"Novads:\s*(.*?)\s*Kadastrs:", teksts)
    n.pagasts = _nem(r"Pagasts:\s*(.*?)\s*Kvartāls:", teksts)
    n.kadastrs = _nem(r"Kadastrs:\s*(\d+)", teksts)
    n.kvartals = _nem(r"Kvartāls:\s*(\S+)", teksts)
    n.nogabals = _nem(r"(?<!A\.)Nogabals:\s*(\S+)", teksts)
    n.a_nogabals = _nem(r"A\.Nogabals:\s*(\S+)", teksts)
    n.platiba = skaitlis(_nem(r"Platība:\s*([\d\s]*[.,]?\d+)\s*ha", teksts))
    n.datums = _nem(r"Uzmērīšanas datums:\s*(\d{1,2}\.\d{1,2}\.\d{4})", teksts)
    n.cirtes_veids = _nem(r"Meža izmantošanas veids:\s*(.+)", teksts)
    ks = _nem(r"Koku skaits:\s*([\d\s]+?)\s*gab", teksts)
    n.koku_skaits = int(ks.replace(" ", "")) if ks else None

    summa = r"\s*([\d\s]+,\d+)"
    n.cirsmas_kraja = skaitlis(_nem(r"Cirsmas krāja, m3:" + summa, teksts))
    n.cirsmas_vertiba = skaitlis(_nem(r"Cirsmas vērtība, €:" + summa, teksts))
    n.biomasas_apjoms = skaitlis(_nem(r"Biomasas apjoms, ber\.m3:" + summa, teksts))
    n.biomasas_vertiba = skaitlis(_nem(r"Biomasas vērtība, €:" + summa, teksts))
    n.vertiba_kopa = skaitlis(_nem(r"Vērtība kopā, €:" + summa, teksts))

    for rinda in teksts.splitlines():
        rinda = rinda.strip()
        if rinda.startswith("Kopā:"):
            tok = rinda[len("Kopā:"):].split()
            skaits, dec = _skaits_un_decimali(tok)
            if len(dec) >= len(SUGU_KOLONNAS):
                n.kopa = {"skaits": skaits, **dict(zip(SUGU_KOLONNAS, dec))}
                beigas = _veselie_beigas(tok)
                n.saglabajamie = beigas[0] if beigas else 0
            continue
        m = _SUGAS_RE.match(rinda)
        if not m or m.group(1) in ("Kopā", "Sugas", "Mežvērte"):
            continue
        tok = m.group(2).split()
        skaits, dec = _skaits_un_decimali(tok)
        if skaits is None or len(dec) < len(SUGU_KOLONNAS):
            continue
        beigas = _veselie_beigas(tok)
        n.sugas.append({"suga": m.group(1), "skaits": skaits,
                        **dict(zip(SUGU_KOLONNAS, dec)),
                        "saglabajamie": beigas[0] if beigas else 0})

    # Kontrolsummas
    if n.platiba is None:
        n.bridinajumi.append("Nav nolasīta platība.")
    if n.vertiba_kopa is None:
        n.bridinajumi.append("Nav nolasīta 'Vērtība kopā'.")
    if None not in (n.cirsmas_vertiba, n.biomasas_vertiba, n.vertiba_kopa):
        if abs(n.cirsmas_vertiba + n.biomasas_vertiba - n.vertiba_kopa) > 0.05:
            n.bridinajumi.append("Cirsmas + biomasas vērtība nesakrīt ar 'Vērtība kopā'.")
    if n.sugas and n.kopa:
        if abs(sum(s["kraja"] for s in n.sugas) - n.kopa["kraja"]) > 0.05:
            n.bridinajumi.append("Sugu krāju summa nesakrīt ar 'Kopā' rindu.")
    return n


def parse_novertejums_pdf(dati: bytes | str, fails: str = "") -> Novertejums:
    """Nolasa vienu cirsmas novērtējuma PDF (baiti vai ceļš)."""
    avots = io.BytesIO(dati) if isinstance(dati, (bytes, bytearray)) else dati
    with pdfplumber.open(avots) as pdf:
        teksts = "\n".join((p.extract_text() or "") for p in pdf.pages)
    return parse_novertejums_teksts(teksts, fails or (dati if isinstance(dati, str) else ""))


# ---------------------------------------------------------------------------
# Rādītāji un summēšana
# ---------------------------------------------------------------------------

# label, mērvienība, decimāles, noklusējums; locked = vienmēr rādīts; atvasinats = dalījums
RADITAJI: dict[str, dict] = {
    "nogabali":         dict(label="Nogabali", unit="gab.", dec=0, default=True, locked=True),
    "platiba":          dict(label="Platība", unit="ha", dec=2, default=True, locked=True),
    "vertiba_kopa":     dict(label="Vērtība kopā", unit="€", dec=2, default=False),
    "cirsmas_vertiba":  dict(label="Cirsmas vērtība", unit="€", dec=2, default=False),
    "biomasas_vertiba": dict(label="Biomasas vērtība", unit="€", dec=2, default=False),
    "eur_ha":           dict(label="Vērtība uz ha", unit="€/ha", dec=0, default=False, atvasinats=True),
    "eur_m3":           dict(label="Vērtība uz m³", unit="€/m³", dec=2, default=False, atvasinats=True),
    "cirsmas_kraja":    dict(label="Cirsmas krāja", unit="m³", dec=2, default=False),
    "m3_ha":            dict(label="Krāja uz ha", unit="m³/ha", dec=1, default=False, atvasinats=True),
    "pardosanai":       dict(label="Paredzēts pārdošanai", unit="m³", dec=2, default=False),
    "lietkoksne":       dict(label="Lietkoksne", unit="m³", dec=2, default=False),
    "malka":            dict(label="Malka", unit="m³", dec=2, default=False),
    "atlikumi":         dict(label="Atlikumi", unit="m³", dec=2, default=False),
    "biomasas_apjoms":  dict(label="Biomasas apjoms", unit="ber. m³", dec=2, default=False),
    "koku_skaits":      dict(label="Koku skaits", unit="gab.", dec=0, default=False),
    "saglabajamie":     dict(label="Saglabājamie koki", unit="gab.", dec=0, default=False),
}


def _atvasinat(v: dict) -> dict:
    def dal(a, b):
        return a / b if a is not None and b else None
    v["eur_ha"] = dal(v.get("vertiba_kopa"), v.get("platiba"))
    v["eur_m3"] = dal(v.get("vertiba_kopa"), v.get("cirsmas_kraja"))
    v["m3_ha"] = dal(v.get("cirsmas_kraja"), v.get("platiba"))
    return v


def rindas_vertibas(n: Novertejums) -> dict:
    k = n.kopa or {}
    return _atvasinat({
        "nogabali": 1,
        "platiba": n.platiba,
        "vertiba_kopa": n.vertiba_kopa,
        "cirsmas_vertiba": n.cirsmas_vertiba,
        "biomasas_vertiba": n.biomasas_vertiba,
        "cirsmas_kraja": n.cirsmas_kraja if n.cirsmas_kraja is not None else k.get("kraja"),
        "pardosanai": k.get("pardosanai"),
        "lietkoksne": k.get("lietkoksne"),
        "malka": k.get("malka"),
        "atlikumi": k.get("atlikumi"),
        "biomasas_apjoms": n.biomasas_apjoms,
        "koku_skaits": n.koku_skaits if n.koku_skaits is not None else k.get("skaits"),
        "saglabajamie": n.saglabajamie,
    })


def kopsummas(rindas: list[dict]) -> dict:
    kop = {}
    for key, r in RADITAJI.items():
        if r.get("atvasinats"):
            continue
        vertibas = [x[key] for x in rindas if x.get(key) is not None]
        kop[key] = sum(vertibas) if vertibas else None
    return _atvasinat(kop)


def dublikati(novertejumi: list[Novertejums]) -> list[str]:
    redzeti, dup = {}, []
    for n in novertejumi:
        if n.atslega in redzeti:
            dup.append(f"{n.nosaukums} ({n.fails} = {redzeti[n.atslega]})")
        else:
            redzeti[n.atslega] = n.fails
    return dup


def _nat(s: str):
    return (int(s), "") if s and s.isdigit() else (10**9, s or "")


def kartot(novertejumi: list[Novertejums]) -> list[Novertejums]:
    return sorted(novertejumi, key=lambda n: (n.kadastrs, _nat(n.kvartals),
                                              _nat(n.nogabals), _nat(n.a_nogabals)))
