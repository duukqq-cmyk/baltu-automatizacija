"""Cirsmas novērtējuma PDF nolasīšana un summēšana.

Atbalstītie formāti (atpazīst automātiski):

* **Mežvērte** — "CIRSMAS NOVĒRTĒJUMS" ar galveni "Saimniecība: … Kadastrs: …",
  viens nogabals, ir € vērtības (cirsmas, biomasas, kopā).
* **Pārdodamās cirsmas** — "CIRSMAS NOVĒRTĒJUMS / Pārdod. cirsmas nr. …",
  viena cirsma lapā (PDF var saturēt daudzas), cirsmā var būt vairāki nogabali,
  tikai apjomi (m³) — € vērtību nav.

Viens PDF var saturēt vairākas cirsmas: teksts tiek dalīts pa lapām, un lapa
bez virsraksta tiek pievienota iepriekšējai cirsmai (turpinājums).

Tīra loģika bez Streamlit — UI ir views/novertejums.py.
"""
from __future__ import annotations

import io
import os
import re
from dataclasses import dataclass, field

import pdfplumber

FORMATS_MEZVERTE = "Mežvērte"
FORMATS_PARDODAMA = "Pārdodamā cirsma"

# ---------------------------------------------------------------------------
# Skaitļi
# ---------------------------------------------------------------------------

_DEC_RE = re.compile(r"^-?\d+[.,]\d+$")
_INT_RE = re.compile(r"^-?\d+$")


def skaitlis(s: str | None) -> float | None:
    """'35 038,99' -> 35038.99 ; '0.52' -> 0.52 ; '1' -> 1.0 ; '' -> None"""
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
    dalas: list[str] = []
    i = 0
    while i < len(tokeni) and _INT_RE.match(tokeni[i]):
        dalas.append(tokeni[i])
        i += 1
    skaits = int("".join(dalas)) if dalas else None
    decimali = [v for v in (skaitlis(t) for t in tokeni[i:]) if v is not None]
    return skaits, decimali


def _veselie_beigas(tokeni: list[str]) -> list[int]:
    """Veselie skaitļi aiz pēdējā decimālskaitļa — saglabājamo koku skaits."""
    pedejais = max((i for i, t in enumerate(tokeni) if _DEC_RE.match(t)), default=-1)
    return [int(t) for t in tokeni[pedejais + 1:] if _INT_RE.match(t)]


# Sugu nosaukumi dažādos formātos → vienots nosaukums
_SUGU_SINONIMI = {
    "BAlksnis": "Baltalksnis",
    "MAlksnis": "Melnalksnis",
    "Ozols/Os": "Ozols/Osis",
}


def _suga(nosaukums: str) -> str:
    return _SUGU_SINONIMI.get(nosaukums, nosaukums)


# ---------------------------------------------------------------------------
# Datu modelis
# ---------------------------------------------------------------------------

# Mežvērtes sugu tabulas kolonnas aiz koku skaita (secība kā PDF)
_KOL_MEZVERTE = ["kraja", "lietkoksne", "ip_kval", "resna", "videja", "tieva",
                 "p_malka", "malka", "atlikumi", "pardosanai", "vid_koks"]
# Pārdodamās cirsmas tabula (nav īp. kvalitātes un P.malkas)
_KOL_PARDODAMA = ["kraja", "lietkoksne", "resna", "videja", "tieva",
                  "malka", "atlikumi", "pardosanai", "vid_koks"]
SUGU_SUMMEJAMAS = ["skaits", "kraja", "lietkoksne", "resna", "videja", "tieva",
                   "p_malka", "malka", "atlikumi", "pardosanai"]


@dataclass
class Novertejums:
    """Viena cirsma (Mežvērtē — viens nogabals; pārdodamām cirsmām — var būt vairāki)."""
    fails: str
    formats: str = ""
    lapa: int | None = None          # PDF lapa, kur sākas šī cirsma (1-bāzēta)
    saimnieciba: str = ""
    ipasnieks: str = ""
    novads: str = ""
    pagasts: str = ""
    kadastrs: str = ""
    mezsaimnieciba: str = ""
    iecirknis: str = ""
    cirsmas_nr: str = ""
    kvartals: str = ""
    nogabali: list = field(default_factory=list)   # ["5"] vai ["01", "03", ...]
    platiba: float | None = None
    uzmerija: str = ""
    datums: str = ""
    cirtes_veids: str = ""
    koku_skaits: int | None = None
    kopa: dict = field(default_factory=dict)       # "Kopā" rinda
    sugas: list = field(default_factory=list)      # [{suga, skaits, kraja, ...}]
    saglabajamie: int | None = None
    saglabajamie_kraja: float | None = None
    cirsmas_kraja: float | None = None
    cirsmas_vertiba: float | None = None
    biomasas_apjoms: float | None = None
    biomasas_vertiba: float | None = None
    vertiba_kopa: float | None = None
    bridinajumi: list = field(default_factory=list)

    @property
    def nogabali_teksts(self) -> str:
        return ", ".join(self.nogabali) if self.nogabali else "?"

    @property
    def nosaukums(self) -> str:
        return f"{self.kvartals or '?'}. kv. {self.nogabali_teksts}. nog."

    @property
    def ipasums(self) -> str:
        """Kas identificē īpašumu dublikātu pārbaudei un grupēšanai."""
        if self.kadastrs:
            return self.kadastrs
        if self.mezsaimnieciba:
            return f"{self.fails_bez_pap} / {self.mezsaimnieciba}-{self.iecirknis}"
        return self.fails_bez_pap

    @property
    def ipasuma_nosaukums(self) -> str:
        if self.saimnieciba:
            return f"{self.saimnieciba} ({self.kadastrs})" if self.kadastrs else self.saimnieciba
        return self.fails_bez_pap

    @property
    def fails_bez_pap(self) -> str:
        return os.path.splitext(os.path.basename(self.fails))[0] if self.fails else "—"

    @property
    def avots(self) -> str:
        return f"{self.fails}, {self.lapa}. lpp." if self.lapa else self.fails


# ---------------------------------------------------------------------------
# Parsētāji
# ---------------------------------------------------------------------------

def _nem(pattern: str, teksts: str, flags=0) -> str:
    m = re.search(pattern, teksts, flags)
    return m.group(1).strip() if m else ""


_MEZVERTE_SUGA_RE = re.compile(
    r"^([A-ZĀČĒĢĪĶĻŅŠŪŽ][a-zāčēģīķļņšūž]+(?:\s[a-zāčēģīķļņšūž]+)?)\s+(\d[\d\s,.]*)$"
)


def _parse_mezverte(teksts: str, n: Novertejums) -> None:
    n.formats = FORMATS_MEZVERTE
    n.saimnieciba = _nem(r"Saimniecība:\s*(.*?)\s*Īpašnieks:", teksts)
    n.ipasnieks = _nem(r"Īpašnieks:\s*(.*?)\s*Uzmērīja:", teksts)
    n.uzmerija = _nem(r"Īpašnieks:.*?Uzmērīja:\s*([^\n]+?)\s*$", teksts, re.M)
    n.novads = _nem(r"Novads:\s*(.*?)\s*Kadastrs:", teksts)
    n.pagasts = _nem(r"Pagasts:\s*(.*?)\s*Kvartāls:", teksts)
    n.kadastrs = _nem(r"Kadastrs:\s*(\d+)", teksts)
    n.kvartals = _nem(r"Kvartāls:\s*(\S+)", teksts)
    nog = _nem(r"(?<!A\.)Nogabals:\s*(\S+)", teksts)
    a_nog = _nem(r"A\.Nogabals:\s*(\S+)", teksts)
    if nog:
        n.nogabali = [f"{nog}/{a_nog}" if a_nog and a_nog != "0" else nog]
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
            if len(dec) >= len(_KOL_MEZVERTE):
                n.kopa = {"skaits": skaits, **dict(zip(_KOL_MEZVERTE, dec))}
                beigas = _veselie_beigas(tok)
                n.saglabajamie = beigas[0] if beigas else 0
            continue
        m = _MEZVERTE_SUGA_RE.match(rinda)
        if not m or m.group(1) in ("Kopā", "Sugas", "Mežvērte"):
            continue
        tok = m.group(2).split()
        skaits, dec = _skaits_un_decimali(tok)
        if skaits is None or len(dec) < len(_KOL_MEZVERTE):
            continue
        beigas = _veselie_beigas(tok)
        n.sugas.append({"suga": _suga(m.group(1)), "skaits": skaits,
                        **dict(zip(_KOL_MEZVERTE, dec)),
                        "saglabajamie": beigas[0] if beigas else 0})

    if n.vertiba_kopa is None:
        n.bridinajumi.append("Nav nolasīta 'Vērtība kopā'.")
    if None not in (n.cirsmas_vertiba, n.biomasas_vertiba, n.vertiba_kopa):
        if abs(n.cirsmas_vertiba + n.biomasas_vertiba - n.vertiba_kopa) > 0.05:
            n.bridinajumi.append("Cirsmas + biomasas vērtība nesakrīt ar 'Vērtība kopā'.")


def _tabulas_rinda(rinda: str, kolonnas: list[str]) -> tuple[str, dict] | None:
    """'Egle 659 165,78 137,17 ...' -> ('Egle', {...}); 'Kopā 2407 ...' -> ('Kopā', {...})."""
    tok = rinda.split()
    if len(tok) < 2 + len(kolonnas) or not re.match(r"^[A-Za-zĀ-ž]", tok[0]):
        return None
    vards = tok[0]
    skaits, dec = _skaits_un_decimali(tok[1:])
    if skaits is None or len(dec) != len(kolonnas):
        return None
    return vards, {"skaits": skaits, **dict(zip(kolonnas, dec))}


def _parse_pardodama(teksts: str, n: Novertejums) -> None:
    n.formats = FORMATS_PARDODAMA
    n.cirsmas_nr = _nem(r"Pārdod\.\s*cirsmas nr\.\s*(\S+)", teksts)
    n.mezsaimnieciba = _nem(r"Mežsaimniecība\s+(\S+)", teksts)
    n.iecirknis = _nem(r"Iecirknis\s+(\S+)", teksts)
    n.kvartals = _nem(r"Kvartāls\s+(\S+)", teksts)
    nog = _nem(r"^Nogabali\s+(.+?)\s*$", teksts, re.M)
    n.nogabali = [x.strip() for x in re.split(r"[,;]", nog) if x.strip()]
    n.platiba = skaitlis(_nem(r"Platība,\s*ha\s+(\d+(?:[.,]\d+)?)", teksts))
    n.cirtes_veids = _nem(r"Cirtes veids\s+(\S+)", teksts)
    n.datums = _nem(r"Dastoja\s+(\d{1,2}\.\d{1,2}\.\d{4})", teksts)

    sadala = "apjomi"
    for rinda in teksts.splitlines():
        rinda = rinda.strip()
        if rinda.startswith("Saglabājamie koki"):
            sadala = "saglabajamie"
            continue
        if sadala == "apjomi":
            r = _tabulas_rinda(rinda, _KOL_PARDODAMA)
            if not r:
                continue
            vards, vert = r
            if vards == "Kopā":
                n.kopa = vert
            else:
                n.sugas.append({"suga": _suga(vards), **vert})
        elif rinda.startswith("Kopā") and "/" in rinda:
            # "Kopā 8 / 4 8 / 4 0 / 0 0 / 0 11,24 11,24 0,00 0,00"
            m = re.match(r"Kopā\s+(\d+)\s*/", rinda)
            dec = [skaitlis(t) for t in rinda.split() if _DEC_RE.match(t)]
            if m:
                n.saglabajamie = int(m.group(1))
            if dec:
                n.saglabajamie_kraja = dec[0]

    if n.kopa:
        n.koku_skaits = n.kopa.get("skaits")
        n.cirsmas_kraja = n.kopa.get("kraja")
    if n.saglabajamie is None:
        n.saglabajamie = 0


def parse_novertejums_teksts(teksts: str, fails: str = "", lapa: int | None = None) -> Novertejums:
    """Nolasa vienu cirsmu no teksta. Formātu atpazīst automātiski."""
    if "CIRSMAS NOVĒRTĒJUMS" not in teksts.upper():
        raise ValueError("Neizskatās pēc cirsmas novērtējuma PDF.")

    n = Novertejums(fails=fails, lapa=lapa)
    if re.search(r"Pārdod\.\s*cirsmas nr\.|Lielumu tabula", teksts):
        _parse_pardodama(teksts, n)
    elif "Saimniecība:" in teksts or "Mežvērte" in teksts:
        _parse_mezverte(teksts, n)
    else:
        raise ValueError("Nezināms cirsmas novērtējuma formāts (nav ne Mežvērtes, "
                         "ne pārdodamās cirsmas galvenes).")

    if not n.nogabali and n.platiba is None and not n.kopa:
        raise ValueError(f"Formāts '{n.formats}' atpazīts, bet neizdevās nolasīt ne nogabalus, "
                         "ne platību, ne apjomus.")

    # Kontrolsummas
    if not n.nogabali:
        n.bridinajumi.append("Nav nolasīts nogabala numurs.")
    if n.platiba is None:
        n.bridinajumi.append("Nav nolasīta platība.")
    if not n.kopa:
        n.bridinajumi.append("Nav nolasīta apjomu 'Kopā' rinda.")
    if n.sugas and n.kopa:
        if abs(sum(s["kraja"] for s in n.sugas) - n.kopa["kraja"]) > 0.05 * max(1, len(n.sugas)):
            n.bridinajumi.append("Sugu krāju summa nesakrīt ar 'Kopā' rindu.")
    return n


def _sadalit_cirsmas(lapas: list[str]) -> list[tuple[int, str]]:
    """Lapas → cirsmas. Lapa ar virsrakstu sāk jaunu cirsmu; lapa bez tā ir turpinājums."""
    cirsmas: list[tuple[int, str]] = []
    for i, t in enumerate(lapas, start=1):
        if not t.strip():
            continue
        if "CIRSMAS NOVĒRTĒJUMS" in t.upper() or not cirsmas:
            cirsmas.append((i, t))
        else:
            sak, iepr = cirsmas[-1]
            cirsmas[-1] = (sak, iepr + "\n" + t)
    return cirsmas


def parse_novertejums_pdf(dati: bytes | str, fails: str = "") -> list[Novertejums]:
    """Nolasa PDF (baiti vai ceļš) → visas tajā esošās cirsmas.

    Ja kāda cirsma nav nolasāma, tā tiek atgriezta ar brīdinājumu tikai tad, ja
    vismaz kaut kas ir nolasīts; ja PDF vispār nesatur atpazīstamu cirsmu — ValueError.
    """
    fails = fails or (os.path.basename(dati) if isinstance(dati, str) else "")
    avots = io.BytesIO(dati) if isinstance(dati, (bytes, bytearray)) else dati
    with pdfplumber.open(avots) as pdf:
        lapas = [(p.extract_text() or "") for p in pdf.pages]

    if not any(t.strip() for t in lapas):
        raise ValueError("PDF nesatur tekstu (iespējams, skenēts attēls) — nav ko nolasīt.")

    dalas = _sadalit_cirsmas(lapas)
    vairakas = len(dalas) > 1
    rezultats, kludas = [], []
    for lapa, teksts in dalas:
        try:
            rezultats.append(parse_novertejums_teksts(teksts, fails, lapa if vairakas else None))
        except ValueError as e:
            kludas.append(f"{lapa}. lpp.: {e}" if vairakas else str(e))
    if not rezultats:
        raise ValueError("; ".join(kludas) or "Nav atrasta neviena cirsma.")
    if kludas:
        rezultats[0].bridinajumi.append("Dažas lapas netika nolasītas — " + "; ".join(kludas))
    return rezultats


# ---------------------------------------------------------------------------
# Rādītāji un summēšana
# ---------------------------------------------------------------------------

# label, mērvienība, decimāles, noklusējums; locked = vienmēr rādīts;
# atvasinats = dalījums; eur = pieejams tikai formātos ar cenām
RADITAJI: dict[str, dict] = {
    "nogabali":         dict(label="Nogabali", unit="gab.", dec=0, default=True, locked=True),
    "platiba":          dict(label="Platība", unit="ha", dec=2, default=True, locked=True),
    "cirsmas":          dict(label="Cirsmas", unit="gab.", dec=0, default=False),
    "vertiba_kopa":     dict(label="Vērtība kopā", unit="€", dec=2, default=False, eur=True),
    "cirsmas_vertiba":  dict(label="Cirsmas vērtība", unit="€", dec=2, default=False, eur=True),
    "biomasas_vertiba": dict(label="Biomasas vērtība", unit="€", dec=2, default=False, eur=True),
    "eur_ha":           dict(label="Vērtība uz ha", unit="€/ha", dec=0, default=False, atvasinats=True, eur=True),
    "eur_m3":           dict(label="Vērtība uz m³", unit="€/m³", dec=2, default=False, atvasinats=True, eur=True),
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


def _dal(a, b):
    return a / b if a is not None and b else None


def rindas_vertibas(n: Novertejums) -> dict:
    k = n.kopa or {}
    v = {
        "nogabali": len(n.nogabali) or 1,
        "cirsmas": 1,
        "platiba": n.platiba,
        "vertiba_kopa": n.vertiba_kopa,
        "cirsmas_vertiba": n.cirsmas_vertiba,
        "biomasas_vertiba": n.biomasas_vertiba,
        "cirsmas_kraja": n.cirsmas_kraja if n.cirsmas_kraja is not None else k.get("kraja"),
        "pardosanai": k.get("pardosanai"),
        "lietkoksne": k.get("lietkoksne"),
        "malka": k.get("malka"),  # P.malka (papīrmalka) ir lietkoksnē, ne malkā
        "atlikumi": k.get("atlikumi"),
        "biomasas_apjoms": n.biomasas_apjoms,
        "koku_skaits": n.koku_skaits if n.koku_skaits is not None else k.get("skaits"),
        "saglabajamie": n.saglabajamie,
    }
    v["eur_ha"] = _dal(v["vertiba_kopa"], v["platiba"])
    v["eur_m3"] = _dal(v["vertiba_kopa"], v["cirsmas_kraja"])
    v["m3_ha"] = _dal(v["cirsmas_kraja"], v["platiba"])
    return v


def kopsummas(rindas: list[dict]) -> dict:
    kop = {}
    for key, r in RADITAJI.items():
        if r.get("atvasinats"):
            continue
        vertibas = [x[key] for x in rindas if x.get(key) is not None]
        kop[key] = sum(vertibas) if vertibas else None
    # €/ha un €/m³ — tikai no cirsmām, kurām € vērtība ir (citādi platība "atšķaidītu" cenu)
    ar_eur = [x for x in rindas if x.get("vertiba_kopa") is not None]
    kop["eur_ha"] = _dal(sum(x["vertiba_kopa"] for x in ar_eur),
                         sum(x["platiba"] or 0 for x in ar_eur)) if ar_eur else None
    kop["eur_m3"] = _dal(sum(x["vertiba_kopa"] for x in ar_eur),
                         sum(x["cirsmas_kraja"] or 0 for x in ar_eur)) if ar_eur else None
    kop["m3_ha"] = _dal(kop.get("cirsmas_kraja"), kop.get("platiba"))
    return kop


def dublikati(novertejumi: list[Novertejums]) -> list[str]:
    """Nogabali, kas parādās vairāk nekā vienā cirsmā (tā paša īpašuma un kvartāla)."""
    redzeti: dict[tuple, str] = {}
    dup = []
    for n in novertejumi:
        for nog in n.nogabali:
            atsl = (n.ipasums, n.kvartals, nog.lstrip("0") or "0")
            if atsl in redzeti:
                dup.append(f"{n.kvartals}. kv. {nog}. nog. ({n.avots} = {redzeti[atsl]})")
            else:
                redzeti[atsl] = n.avots
    return dup


def _nat(s: str):
    s = (s or "").split("/")[0]
    return (int(s), "") if s.isdigit() else (10**9, s)


def kartot(novertejumi: list[Novertejums]) -> list[Novertejums]:
    return sorted(novertejumi, key=lambda n: (n.ipasums, _nat(n.kvartals),
                                              _nat(n.nogabali[0] if n.nogabali else "")))
