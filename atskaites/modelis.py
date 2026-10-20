"""Datu modelis: monday kolonnas → standarta lauki → leadi.

Lead definīcija (CEO, 2026-10-15):
    1 lead = viens īpašnieka tālrunis + viens īpašuma kadastra numurs.
    Visas zemes vienības vienā īpašumā = 1 lead (platība/m³ summējas).
    Viens īpašnieks, divi īpašumi = 2 leadi.  Viens īpašums, divi īpašnieki = 1 lead.

Tātad praktiskā atslēga ir ĪPAŠUMA kadastra numurs. Tālrunis ir rezerves atslēga,
kamēr kadastra numurs vēl nav zināms (rinda pievienojas īpašumam, ja tālrunis
viennozīmīgi norāda uz vienu īpašumu).

Atjaunots lead: tas pats īpašums atkal pieteicies vairāk nekā 365 dienas pēc
iepriekšējā pieteikuma → jauna "epizode".
"""
from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from atskaites.monday import Boards, Kolonna, Rinda

ATJAUNOSANAS_DIENAS = 365


# --------------------------------------------------------------------------
# Standarta lauki un to atpazīšana monday kolonnās
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Lauks:
    key: str
    nosaukums: str          # ieteicamais kolonnas nosaukums monday
    tips: str               # date | num | text | phone | bool | label
    sinonimi: tuple[str, ...] = ()
    agregacija: str = "first"   # sum | mean | min | any | first
    monday_tips: str = "text"   # kolonnas tips, ja to izveido no platformas
    apraksts: str = ""


LAUKI: list[Lauks] = [
    Lauks("lead_datums", "Lead Datums", "date", ("lead datums", "ienaksanas datums", "lead sanemts"),
          "min", "date", "Kad lead ienāca"),
    Lauks("telefons", "Tel.Nr", "phone", ("tel nr", "talrunis", "telefons", "tel", "telefona nr"),
          "first", "phone", "Īpašnieka tālrunis"),
    Lauks("kontaktpersona", "Kontaktpersona", "text", ("kontaktpersona", "ipasnieks", "klients"),
          "first", "text"),
    Lauks("ipasuma_kad", "Īpašuma kad. Nr.", "text",
          ("ipasuma kad nr", "ipasuma kadastra nr", "ipasuma kadastra numurs", "kadastra nr", "kad nr"),
          "first", "text", "Lead atslēga — viens īpašums"),
    Lauks("zv_kad", "Zemes vienības kad. apz.", "text",
          ("zemes vienibas kad apz", "zemes vienibas kad", "zv kad apz", "zv kad", "kadastra apzimejums"),
          "first", "text", "Zemes vienība (vienam īpašumam var būt vairākas)"),
    Lauks("pied_veids", "Pied. veids", "label", ("pied veids", "piedavajuma veids", "interese"),
          "first", "status", "Par kuru pakalpojumu interese"),
    Lauks("avots", "Lead avots", "label", ("lead avots", "avots", "kanals", "lead kanals"),
          "first", "dropdown", "Aukstais zvans, kaimiņš, ss.com, Facebook, izsole…"),
    Lauks("sazvanams", "Sazvanāms", "bool", ("sazvanams",), "any", "checkbox"),
    Lauks("meza_ha", "Meža platība, ha", "num", ("meza platiba ha", "meza platiba", "meza ha"),
          "sum", "numbers"),
    Lauks("lauks_proc", "Lauks. zeme, %", "num",
          ("lauks zeme", "lauksaimniecibas zeme", "lauksaimn zeme", "lauks"), "mean", "numbers"),
    Lauks("kailc_sausie_ha", "Kailcirte sausie, ha", "num", ("kailcirte sausie", "kailc sausie"),
          "sum", "numbers", "Plānojamā kailcirtes platība sausajos tipos"),
    Lauks("kailc_slapjie_ha", "Kailcirte slapjie, ha", "num", ("kailcirte slapjie", "kailc slapjie"),
          "sum", "numbers", "Plānojamā kailcirtes platība slapjajos tipos"),
    Lauks("citu_cirsu_pot", "Citu ciršu potenciāls", "bool",
          ("citu cirsu potencials", "caurmera cirtes potencials"), "any", "checkbox",
          "Caurmēra/neproduktīvās/kopšanas/izlases cirtes, ko citi neredz"),
    Lauks("m3_1_piegajiens", "1. piegājiena apjoms, m³", "num",
          ("1 piegajiena apjoms", "pirma piegajiena apjoms", "izcertamais apjoms", "1 piegajiens"),
          "sum", "numbers"),
    Lauks("merka_lead", "Mērķa lead", "bool", ("merka lead",), "any", "checkbox",
          "Manuāla atzīme (pārraksta automātisko vērtējumu)"),
    Lauks("kvalif_datums", "Izpētes zvans (datums)", "date",
          ("izpetes zvans datums", "izpetes zvans", "kvalificets", "kvalifikacijas datums"), "min", "date"),
    Lauks("priekszv_datums", "Priekšvērtējums (datums)", "date",
          ("priekšvertejums datums", "priekšvertejums", "prieksvertejums datums", "prieksvertejums"),
          "min", "date"),
    Lauks("tiksanas_datums", "Tikšanās sarunāta (datums)", "date",
          ("tiksanas sarunata datums", "tiksanas sarunata", "tiksanas datums", "tiksanas"), "min", "date"),
    Lauks("apsek_nosut_datums", "Nosūtīts apsekot (datums)", "date",
          ("nosutits apsekot datums", "nosutits apsekot", "nosutits apsekosanai"), "min", "date"),
    Lauks("apsekots_datums", "Apsekots dabā (datums)", "date",
          ("apsekots daba datums", "apsekots daba", "apsekots", "apsekosanas datums"), "min", "date"),
    Lauks("gala_pied_datums", "Gala piedāvājums (datums)", "date",
          ("gala piedavajums datums", "gala piedavajuma datums"), "min", "date"),
    Lauks("max_piedavajums", "Maks. gala piedāvājums, EUR", "num",
          ("maks gala piedavajums eur", "maks gala piedavajums", "maksimalais piedavajums",
           "maksimala iegades summa", "max piedavajums", "gala piedavajums eur"), "sum", "numbers",
          "Maksimāli aprēķinātais gala piedāvājums"),
    Lauks("nopirkts_datums", "Nopirkts (datums)", "date",
          ("nopirkts datums", "nopirkts", "darijuma datums", "liguma datums"), "min", "date"),
    Lauks("iegades_summa", "Iegādes summa, EUR", "num",
          ("iegades summa eur", "iegades summa", "pirkuma summa", "darijuma summa"), "sum", "numbers"),
    Lauks("nopirkts_m3", "Iegādātais apjoms, m³", "num",
          ("iegadatais apjoms m3", "iegadatais apjoms", "nopirktais apjoms"), "sum", "numbers"),
    Lauks("nopirkts_ha", "Iegādātā platība, ha", "num",
          ("iegadata platiba ha", "iegadata platiba", "nopirkta platiba"), "sum", "numbers"),
    Lauks("atteikts_datums", "Atteikts (datums)", "date",
          ("atteikts datums", "atteikuma datums", "atteikts"), "min", "date"),
    Lauks("posms", "Posms", "label", ("posms", "statuss", "status", "stadija"), "first", "status",
          "Neobligāti — ja posmu glabā statusa kolonnā, nevis grupās"),
    Lauks("atteikuma_iemesls", "Atteikuma iemesls", "label",
          ("atteikuma iemesls", "atteikuma iemesli", "iemesls"), "first", "dropdown"),
]
LAUKI_PEC_KEY = {l.key: l for l in LAUKI}

# Kuri monday kolonnu tipi der kuram lauka tipam
_SADERIBA = {
    "date": {"date", "formula", "mirror", "lookup", "text"},
    "num": {"numbers", "numeric", "formula", "mirror", "lookup", "text"},
    "phone": {"phone", "text", "numbers", "formula", "mirror", "lookup"},
    "bool": {"checkbox", "boolean", "status", "color", "dropdown", "text", "formula", "mirror", "lookup"},
    "text": {"text", "long_text", "formula", "mirror", "lookup", "numbers", "dropdown", "status", "color"},
    "label": {"status", "color", "dropdown", "tags", "text", "formula", "mirror", "lookup"},
}


def norm_teksts(s: str) -> str:
    """Mazie burti, bez garumzīmēm un pieturzīmēm: 'Tel.Nr' -> 'tel nr'."""
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return s.strip()


def auto_karte(kolonnas: list[Kolonna], parraksti: dict[str, str] | None = None) -> dict[str, str]:
    """Atrod, kura board kolonna atbilst kuram standarta laukam. -> {lauka key: kolonnas title}."""
    parraksti = parraksti or {}
    pec_norm = {norm_teksts(k.title): k for k in kolonnas}
    karte: dict[str, str] = {}
    aiznemtas: set[str] = set()

    # 1) lietotāja norādītie nosaukumi
    for key, title in parraksti.items():
        if not title:
            continue
        k = pec_norm.get(norm_teksts(title))
        if k and key in LAUKI_PEC_KEY:
            karte[key] = k.title
            aiznemtas.add(k.id)

    # 2) automātiski: precīza sakritība > garākā daļēja sakritība
    kandidati = []
    for l in LAUKI:
        if l.key in karte or l.key in parraksti:
            continue
        sinonimi = {norm_teksts(l.nosaukums), *(norm_teksts(s) for s in l.sinonimi)}
        for k in kolonnas:
            if k.type not in _SADERIBA[l.tips]:
                continue
            kn = norm_teksts(k.title)
            for s in sinonimi:
                if not s:
                    continue
                if kn == s:
                    kandidati.append((1000 + len(s), l.key, k))
                elif re.search(rf"(^| ){re.escape(s)}( |$)", kn):
                    kandidati.append((len(s), l.key, k))
    for _, key, k in sorted(kandidati, key=lambda x: -x[0]):
        if key in karte or k.id in aiznemtas:
            continue
        karte[key] = k.title
        aiznemtas.add(k.id)
    return karte


# --------------------------------------------------------------------------
# Posmi (grupas / statusa kolonna)
# --------------------------------------------------------------------------
POSMI = ["jauns", "nesazvanams", "kvalificets", "priekszv", "tiksanas", "apsekosana",
         "gala_pied", "nopirkts", "atteikts"]
POSMU_NOSAUKUMI = {
    "jauns": "Jauns", "nesazvanams": "Nevar sazvanīt", "kvalificets": "Kvalificēts (izpētes zvans)",
    "priekszv": "Priekšvērtējums", "tiksanas": "Tikšanās sarunāta", "apsekosana": "Apsekošana",
    "gala_pied": "Gala piedāvājums", "nopirkts": "Nopirkts", "atteikts": "Atteikts",
}
_POSMU_SECIBA = {"jauns": 1, "kvalificets": 2, "priekszv": 3, "tiksanas": 4, "apsekosana": 5,
                 "gala_pied": 6, "nopirkts": 8}
_POSMU_ATSLEGVARDI = [
    ("nesazvanams", ("nevar sazvan", "nesazvan", "neatbild", "nav sazvan")),
    ("atteikts", ("atteik", "zaudet", "nav aktual", "noraid", "slegts")),
    ("nopirkts", ("nopirkt", "iegadat", "darijums nosle", "noslegts")),
    ("gala_pied", ("gala piedav",)),
    ("apsekosana", ("apsek",)),
    ("tiksanas", ("tiksan",)),
    ("priekszv", ("prieksvert", "priekšvert")),
    ("kvalificets", ("izpetes zvan", "kvalific")),
    ("jauns", ("jauns", "jaunie", "new")),
]


def posms_no_teksta(teksts: str) -> str | None:
    t = norm_teksts(teksts)
    if not t:
        return None
    for posms, vardi in _POSMU_ATSLEGVARDI:
        if any(norm_teksts(v) in t for v in vardi):
            return posms
    return None


def auto_grupu_karte(grupas: list[str]) -> dict[str, str]:
    return {g: (posms_no_teksta(g) or "jauns") for g in grupas}


# --------------------------------------------------------------------------
# Vērtību parsēšana
# --------------------------------------------------------------------------
def parse_datums(s: str | None) -> date | None:
    if not s:
        return None
    s = str(s).strip()
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return date(int(m[1]), int(m[2]), int(m[3]))
    m = re.match(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", s)
    if m:
        return date(int(m[3]), int(m[2]), int(m[1]))
    return None


def parse_skaitlis(s: str | None) -> float | None:
    if s is None:
        return None
    t = re.sub(r"[^\d,.\-]", "", str(s).replace(" ", "").replace(" ", ""))
    if not t or t in "-.,":
        return None
    if "," in t and "." in t:
        t = t.replace(",", "") if t.rfind(".") > t.rfind(",") else t.replace(".", "").replace(",", ".")
    else:
        t = t.replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


def parse_bool(s: str | None) -> bool | None:
    t = norm_teksts(s or "")
    if not t:
        return None
    if t in ("v", "ja", "yes", "true", "1", "x", "done", "ir"):
        return True
    if t in ("ne", "no", "false", "0", "nav"):
        return False
    return None


def norm_telefons(s: str | None) -> str | None:
    cip = re.sub(r"\D", "", s or "")
    if cip.startswith("00371"):
        cip = cip[5:]
    elif cip.startswith("371") and len(cip) == 11:
        cip = cip[3:]
    return cip[-8:] if len(cip) >= 8 else None


def norm_kadastrs(s: str | None) -> str | None:
    cip = re.sub(r"\D", "", s or "")
    return cip if len(cip) >= 10 else None


# --------------------------------------------------------------------------
# Normalizēta rinda un lead
# --------------------------------------------------------------------------
@dataclass
class NRinda:
    rinda: Rinda
    lauki: dict           # key -> parsēta vērtība
    posms: str            # no grupas / statusa
    piezimes: list[str] = field(default_factory=list)

    @property
    def agents(self) -> str:
        return self.rinda.board_nosaukums


def normalizet_rindu(r: Rinda, karte: dict[str, str], grupu_karte: dict[str, str]) -> NRinda:
    lauki, piez = {}, []
    for key, title in karte.items():
        l = LAUKI_PEC_KEY[key]
        teksts = r.vertibas.get(title, "")
        if l.tips == "date":
            v = parse_datums(teksts)
        elif l.tips == "num":
            v = parse_skaitlis(teksts)
        elif l.tips == "bool":
            v = parse_bool(teksts)
        elif l.tips == "phone":
            v = norm_telefons(teksts)
        else:
            v = teksts.strip() or None
        if key in ("ipasuma_kad", "zv_kad"):
            v = norm_kadastrs(teksts)
        lauki[key] = v

    if lauki.get("lead_datums") is None and r.izveidots:
        lauki["lead_datums"] = parse_datums(r.izveidots)
        if lauki["lead_datums"]:
            piez.append("Nav 'Lead Datums' — izmantots rindas izveides datums")

    posms = grupu_karte.get(r.grupa) or posms_no_teksta(r.grupa) or "jauns"
    statuss = r.vertibas.get(karte.get("posms", ""), "") if "posms" in karte else ""
    if statuss and posms_no_teksta(statuss):
        posms = posms_no_teksta(statuss)
    return NRinda(r, lauki, posms, piez)


@dataclass
class Lead:
    atslega: str
    atslegas_veids: str            # kadastrs | zemes_vieniba | telefons | rinda
    epizode: int
    rindas: list[NRinda]
    lauki: dict = field(default_factory=dict)
    piezimes: list[str] = field(default_factory=list)

    @property
    def atjaunots(self) -> bool:
        return self.epizode > 1

    @property
    def agents(self) -> str:
        """Agents = board, kurā lead parādījās pirmais."""
        ar_datumu = [r for r in self.rindas if r.lauki.get("lead_datums")]
        r = min(ar_datumu, key=lambda x: x.lauki["lead_datums"]) if ar_datumu else self.rindas[0]
        return r.agents

    @property
    def nosaukums(self) -> str:
        return " / ".join(dict.fromkeys(r.rinda.nosaukums for r in self.rindas))

    @property
    def grupas(self) -> list[str]:
        return list(dict.fromkeys(r.rinda.grupa for r in self.rindas))

    @property
    def posms(self) -> str:
        posmi = [r.posms for r in self.rindas]
        if "nopirkts" in posmi:
            return "nopirkts"
        aktivi = [p for p in posmi if p not in ("atteikts", "nesazvanams")]
        if not aktivi:
            return "atteikts" if "atteikts" in posmi else "nesazvanams"
        return max(aktivi, key=lambda p: _POSMU_SECIBA.get(p, 0))

    def get(self, key: str):
        return self.lauki.get(key)


def _agregacija(lauks: Lauks, vertibas: list, piez: list[str]):
    v = [x for x in vertibas if x is not None]
    if not v:
        return None
    m = lauks.agregacija
    if m == "min":
        return min(v)
    if m == "any":
        return any(v)
    if m == "mean":
        return sum(v) / len(v)
    if m == "sum":
        if len(v) > 1 and len(set(v)) == 1 and lauks.key in ("iegades_summa", "max_piedavajums"):
            piez.append(f"'{lauks.nosaukums}' vienāda visās {len(v)} rindās — ņemta vienreiz")
            return v[0]
        return sum(v)
    return Counter(v).most_common(1)[0][0]


def _izveidot_lead(atslega, veids, epizode, rindas: list[NRinda]) -> Lead:
    lead = Lead(atslega, veids, epizode, rindas)
    for l in LAUKI:
        lead.lauki[l.key] = _agregacija(l, [r.lauki.get(l.key) for r in rindas], lead.piezimes)
    for r in rindas:
        lead.piezimes.extend(r.piezimes)
    if veids == "zemes_vieniba":
        lead.piezimes.append("Nav īpašuma kad. Nr. — atslēga ir zemes vienība (var dublēties)")
    elif veids == "telefons":
        lead.piezimes.append("Nav kadastra Nr. — lead apvienots pēc tālruņa")
    elif veids == "rinda":
        lead.piezimes.append("Nav ne kadastra Nr., ne tālruņa — lead = viena rinda")
    lead.piezimes = list(dict.fromkeys(lead.piezimes))
    return lead


def apvienot_leados(rindas: list[NRinda]) -> list[Lead]:
    """Rindas → leadi pēc īpašuma kadastra Nr. (rezerve: tālrunis), sadalīti epizodēs."""
    grupas: dict[str, list[NRinda]] = defaultdict(list)
    veidi: dict[str, str] = {}
    tel_uz_kad: dict[str, set[str]] = defaultdict(set)
    zv_uz_kad: dict[str, set[str]] = defaultdict(set)

    # 1) rindas ar īpašuma kadastra Nr.
    bez_kad = []
    for r in rindas:
        kad = r.lauki.get("ipasuma_kad")
        if kad:
            a = f"K:{kad}"
            grupas[a].append(r)
            veidi[a] = "kadastrs"
            if r.lauki.get("telefons"):
                tel_uz_kad[r.lauki["telefons"]].add(a)
            if r.lauki.get("zv_kad"):
                zv_uz_kad[r.lauki["zv_kad"]].add(a)
        else:
            bez_kad.append(r)

    # 2) rindas bez īpašuma Nr.: zināma zemes vienība → tālrunis → zemes vienība kā atslēga → tālrunis → rinda
    for r in bez_kad:
        tel, zv = r.lauki.get("telefons"), r.lauki.get("zv_kad")
        if zv and len(zv_uz_kad.get(zv, ())) == 1:
            a = next(iter(zv_uz_kad[zv]))
            r.piezimes.append("Nav īpašuma kad. Nr. — pievienots īpašumam pēc zemes vienības")
        elif tel and len(tel_uz_kad.get(tel, ())) == 1:
            a = next(iter(tel_uz_kad[tel]))
            r.piezimes.append("Nav kadastra Nr. — pievienots īpašumam pēc tālruņa")
        elif zv:
            a = f"Z:{zv}"
            veidi[a] = "zemes_vieniba"
        elif tel:
            a = f"T:{tel}"
            veidi[a] = "telefons"
        else:
            a = f"I:{r.rinda.board_id}:{r.rinda.item_id}"
            veidi[a] = "rinda"
        grupas[a].append(r)

    leadi: list[Lead] = []
    for a, rr in grupas.items():
        ar_dat = sorted((r for r in rr if r.lauki.get("lead_datums")), key=lambda r: r.lauki["lead_datums"])
        bez_dat = [r for r in rr if not r.lauki.get("lead_datums")]
        epizodes: list[list[NRinda]] = []
        pedejais: date | None = None
        for r in ar_dat:
            d = r.lauki["lead_datums"]
            if not epizodes or (pedejais and (d - pedejais).days > ATJAUNOSANAS_DIENAS):
                epizodes.append([])
            epizodes[-1].append(r)
            pedejais = max(pedejais or d, d)
        if not epizodes:
            epizodes.append([])
        epizodes[-1].extend(bez_dat)
        for i, ep in enumerate(epizodes, start=1):
            leadi.append(_izveidot_lead(a, veidi.get(a, "kadastrs"), i, ep))
    return leadi


# --------------------------------------------------------------------------
# Konfigurācija (kolonnu un grupu karte) — glabājas JSON failā
# --------------------------------------------------------------------------
@dataclass
class Konfiguracija:
    boardi: list[str] = field(default_factory=list)
    kolonnas: dict[str, str] = field(default_factory=dict)   # lauka key -> kolonnas nosaukums
    grupas: dict[str, str] = field(default_factory=dict)     # grupas nosaukums -> posms

    @classmethod
    def ielasit(cls, cels: str) -> "Konfiguracija":
        try:
            with open(cels, encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError):
            return cls()
        return cls(boardi=[str(b) for b in d.get("boardi", [])],
                   kolonnas=dict(d.get("kolonnas", {})), grupas=dict(d.get("grupas", {})))

    def saglabat(self, cels: str) -> None:
        with open(cels, "w", encoding="utf-8") as f:
            json.dump({"boardi": self.boardi, "kolonnas": self.kolonnas, "grupas": self.grupas},
                      f, ensure_ascii=False, indent=2)


@dataclass
class Dati:
    """Viss, kas nepieciešams metrikiem: normalizētas rindas, leadi, kartes."""
    boardi: list[Boards]
    kartes: dict[str, dict[str, str]]       # board id -> {lauks: kolonna}
    grupu_karte: dict[str, str]
    rindas: list[NRinda]
    leadi: list[Lead]


def sagatavot(boardi: list[Boards], konf: Konfiguracija | None = None) -> Dati:
    konf = konf or Konfiguracija()
    visas_grupas = list(dict.fromkeys(g for b in boardi for g in (b.grupas or [r.grupa for r in b.rindas])))
    grupu_karte = {**auto_grupu_karte(visas_grupas), **konf.grupas}
    kartes, rindas = {}, []
    for b in boardi:
        karte = auto_karte(b.kolonnas, konf.kolonnas)
        kartes[b.id] = karte
        rindas.extend(normalizet_rindu(r, karte, grupu_karte) for r in b.rindas)
    return Dati(boardi, kartes, grupu_karte, rindas, apvienot_leados(rindas))


def sodiena() -> date:
    return datetime.now().date()


def darba_dienas(no: date, lidz: date) -> int:
    n, d = 0, no
    while d <= lidz:
        if d.weekday() < 5:
            n += 1
        d += timedelta(days=1)
    return n
