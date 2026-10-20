"""Leadu metriki pēc CEO definīcijām (Monday_metrics.docx).

Katrs notikums tiek skaitīts periodā pēc SAVA datuma: lead pēc 'Lead Datums',
kvalifikācija pēc izpētes zvana datuma, priekšvērtējums pēc tā datuma utt.
Ja boardā nav vajadzīgās kolonnas, metriks netiek izdomāts — tas paliek tukšs
ar piezīmi, kuras kolonnas trūkst.
"""
from __future__ import annotations

import calendar
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta

from atskaites.modelis import (
    LAUKI_PEC_KEY, POSMI, POSMU_NOSAUKUMI, Dati, Lead, darba_dienas, norm_teksts, sodiena,
)

# Mērķa lead kritēriji
KAILC_MAX_SAUSIE_HA = 5.0
KAILC_MAX_SLAPJIE_HA = 2.0
KAILC_REIZINATAJS = 1.5
MIN_M3_1_PIEGAJIENS = 700.0
MIN_MEZA_HA = 5.0
MAX_LAUKS_PROC = 20.0

PROAKTIVI_AVOTI = ("aukst", "personig", "kaimin", "ieteik", "rekomend", "proaktiv", "tiklosan",
                   "pazist", "atkartot", "klatien")
PUBLISKI_AVOTI = ("ss com", "ss lv", "facebook", "fb", "izsol", "portal", "majaslap", "google",
                  "reklam", "inbound", "ienakos", "mezabirza", "latio", "city24")


@dataclass
class Periods:
    no: date
    lidz: date
    nosaukums: str

    def satur(self, d: date | None) -> bool:
        return d is not None and self.no <= d <= self.lidz

    @property
    def dienas(self) -> int:
        return (self.lidz - self.no).days + 1


def menesis(gads: int, men: int) -> Periods:
    pedeja = calendar.monthrange(gads, men)[1]
    nos = ["janvāris", "februāris", "marts", "aprīlis", "maijs", "jūnijs", "jūlijs", "augusts",
           "septembris", "oktobris", "novembris", "decembris"][men - 1]
    return Periods(date(gads, men, 1), date(gads, men, pedeja), f"{gads}. g. {nos}")


def tekosais_menesis(sod: date | None = None) -> Periods:
    sod = sod or sodiena()
    return menesis(sod.year, sod.month)


# --------------------------------------------------------------------------
# Leadu klasifikācija
# --------------------------------------------------------------------------
def ir_sazvanams(lead: Lead) -> bool | None:
    if lead.get("sazvanams") is True:
        return True
    if lead.get("kvalif_datums") or lead.posms not in ("jauns", "nesazvanams", "atteikts"):
        return True
    if lead.get("sazvanams") is False or lead.posms == "nesazvanams":
        return False
    return None


def kvalitativs(lead: Lead) -> tuple[bool, list[str]]:
    """Reāli sazvanāms + identificējams īpašums + izrādīta interese."""
    trukst = []
    if not ir_sazvanams(lead):
        trukst.append("nav apstiprināts, ka sazvanāms")
    if not (lead.get("ipasuma_kad") or lead.get("zv_kad")):
        trukst.append("nav kadastra Nr.")
    if not lead.get("pied_veids"):
        trukst.append("nav norādīta interese (Pied. veids)")
    return (not trukst), trukst


def merka(lead: Lead) -> tuple[bool | None, str]:
    """True/False, vai None, ja trūkst datu. Otrā vērtība — pamatojums."""
    if lead.get("merka_lead") is True:
        return True, "atzīmēts manuāli"
    sausie, slapjie = lead.get("kailc_sausie_ha"), lead.get("kailc_slapjie_ha")
    m3, ha, lauks = lead.get("m3_1_piegajiens"), lead.get("meza_ha"), lead.get("lauks_proc")

    if lead.get("citu_cirsu_pot") is True:
        k1 = True
    elif sausie is None and slapjie is None:
        k1 = None
    else:
        # jauktiem tipiem: katra tipa platība pret tā limitu
        k1 = ((sausie or 0) / KAILC_MAX_SAUSIE_HA + (slapjie or 0) / KAILC_MAX_SLAPJIE_HA) >= KAILC_REIZINATAJS
    k2 = None if m3 is None else m3 >= MIN_M3_1_PIEGAJIENS
    k3 = None if ha is None else (ha >= MIN_MEZA_HA and (lauks is None or lauks <= MAX_LAUKS_PROC))

    neizpild = [n for n, k in (("cirtes apjoms/potenciāls", k1), ("≥700 m³", k2), ("≥5 ha, lauks ≤20%", k3))
                if k is False]
    if neizpild:
        return False, "neatbilst: " + ", ".join(neizpild)
    trukst = [n for n, k in (("kailcirtes platības", k1), ("1. piegājiena m³", k2), ("meža platība", k3))
              if k is None]
    if trukst:
        return None, "trūkst: " + ", ".join(trukst)
    return True, "atbilst visiem 3 kritērijiem"


def proaktivs(lead: Lead) -> bool | None:
    avots = norm_teksts(lead.get("avots") or "")
    if not avots:
        return None
    if any(norm_teksts(a) in avots for a in PUBLISKI_AVOTI):
        return False
    if any(norm_teksts(a) in avots for a in PROAKTIVI_AVOTI):
        return True
    return None


# --------------------------------------------------------------------------
# Atskaite
# --------------------------------------------------------------------------
@dataclass
class Metriks:
    sadala: str
    nosaukums: str
    vertiba: float | int | None
    vieniba: str = ""
    piezime: str = ""


@dataclass
class Atskaite:
    periods: Periods
    metriki: list[Metriks]
    pa_agentiem: list[dict]
    atteikuma_iemesli: list[tuple[str, int]]
    piltuve_tagad: list[dict]
    leadu_tabula: list[dict]
    datu_kvalitate: list[dict]
    trukstosas_kolonnas: dict[str, list[str]] = field(default_factory=dict)

    def metriks(self, nosaukums: str):
        for m in self.metriki:
            if m.nosaukums == nosaukums:
                return m.vertiba
        raise KeyError(nosaukums)


def _dienas_starp(leadi: list[Lead], no_key: str, lidz_key: str) -> list[int]:
    rez = []
    for l in leadi:
        a, b = l.get(no_key), l.get(lidz_key)
        if a and b and b >= a:
            rez.append((b - a).days)
    return rez


def _vid(v: list[int]) -> float | None:
    return round(statistics.mean(v), 1) if v else None


def _med(v: list[int]) -> float | None:
    return round(statistics.median(v), 1) if v else None


def aprekinat(dati: Dati, periods: Periods, sod: date | None = None) -> Atskaite:
    sod = sod or sodiena()
    leadi = dati.leadi
    kartetie = {k for karte in dati.kartes.values() for k in karte}

    def nav(*keys) -> str:
        tr = [LAUKI_PEC_KEY[k].nosaukums for k in keys if k not in kartetie]
        return ("Boardos nav kolonnas: " + ", ".join(f"'{t}'" for t in tr)) if tr else ""

    def notikumi(key: str) -> list[Lead]:
        return [l for l in leadi if periods.satur(l.get(key))]

    M: list[Metriks] = []

    def pievienot(sadala, nos, vert, vien="", piez="", kolonnas=()):
        trukst = nav(*kolonnas)
        if trukst and not vert:
            vert = None
        M.append(Metriks(sadala, nos, vert, vien, "; ".join(x for x in (piez, trukst) if x)))

    # --- 1. Leadi -------------------------------------------------------------
    jauni = notikumi("lead_datums")
    rindas_perioda = [r for r in dati.rindas if periods.satur(r.lauki.get("lead_datums"))]
    S = "1. Saņemtie leadi"
    pievienot(S, "Leadi kopā", len(jauni), "gab.",
              f"{len(rindas_perioda)} monday rindas apvienotas {len(jauni)} leados (1 īpašums = 1 lead)")
    pievienot(S, "t.sk. unikāli", sum(1 for l in jauni if not l.atjaunots), "gab.",
              "Nav bijis datubāzē (pēc ielādētajiem boardiem)")
    pievienot(S, "t.sk. atjaunoti", sum(1 for l in jauni if l.atjaunots), "gab.",
              "Tas pats īpašums >365 dienas iepriekš")

    kval = [l for l in jauni if kvalitativs(l)[0]]
    pievienot(S, "Kvalitatīvi", len(kval), "gab.", _proc(len(kval), len(jauni)),
              ("ipasuma_kad", "pied_veids"))
    mk = [merka(l)[0] for l in jauni]
    pievienot(S, "Mērķa", mk.count(True), "gab.",
              f"{mk.count(None)} leadiem nepietiek datu vērtējumam" if mk.count(None) else "",
              ("m3_1_piegajiens", "meza_ha"))
    pr = [proaktivs(l) for l in jauni]
    pievienot(S, "Proaktīvi", pr.count(True), "gab.",
              f"{pr.count(None)} leadiem avots nav norādīts/atpazīts" if pr.count(None) else "",
              ("avots",))

    # --- 2. Kvalifikācija -------------------------------------------------------
    S = "2. Kvalifikācija (izpētes zvans)"
    kvalif = notikumi("kvalif_datums")
    pievienot(S, "Kvalificēti objekti", len(kvalif), "gab.", kolonnas=("kvalif_datums",))
    d = _dienas_starp(kvalif, "lead_datums", "kvalif_datums")
    pievienot(S, "Vid. laiks lead → kvalifikācija", _vid(d), "dienas",
              f"mediāna {_med(d):g} d." if d else "", ("kvalif_datums",))

    # --- 3. Priekšvērtējums -----------------------------------------------------
    S = "3. Priekšvērtējums"
    pv = notikumi("priekszv_datums")
    pievienot(S, "Priekšvērtējumi", len(pv), "gab.", kolonnas=("priekszv_datums",))
    d = _dienas_starp(pv, "kvalif_datums", "priekszv_datums")
    pievienot(S, "Vid. laiks kvalifikācija → priekšvērtējums", _vid(d), "dienas",
              f"mediāna {_med(d):g} d." if d else "", ("priekszv_datums", "kvalif_datums"))
    lidz = min(periods.lidz, sod) if periods.no <= sod else periods.lidz
    dd = max(darba_dienas(periods.no, lidz), 1)
    kal_dienas = max((lidz - periods.no).days + 1, 1)
    pievienot(S, "Priekšvērtējumi vidēji darba dienā", round(len(pv) / dd, 2), "gab./d.",
              f"{dd} darba dienas periodā", ("priekszv_datums",))
    pievienot(S, "Priekšvērtējumi vidēji nedēļā", round(len(pv) / kal_dienas * 7, 1), "gab./ned.",
              kolonnas=("priekszv_datums",))
    pievienot(S, "Priekšvērtējumi vidēji mēnesī", round(len(pv) / kal_dienas * 30.44, 1), "gab./mēn.",
              kolonnas=("priekszv_datums",))

    # --- 4. Tikšanās un apsekošana ---------------------------------------------
    S = "4. Tikšanās un apsekošana"
    pievienot(S, "Sarunātas klātienes tikšanās", len(notikumi("tiksanas_datums")), "gab.",
              kolonnas=("tiksanas_datums",))
    aps = notikumi("apsekots_datums")
    pievienot(S, "Apsekoti dabā", len(aps), "gab.", kolonnas=("apsekots_datums",))
    gp = notikumi("gala_pied_datums")
    d = _dienas_starp(gp, "apsek_nosut_datums", "gala_pied_datums")
    pievienot(S, "Vid. laiks nosūtīts apsekot → gala piedāvājums", _vid(d), "dienas",
              f"mediāna {_med(d):g} d." if d else "", ("apsek_nosut_datums", "gala_pied_datums"))

    # --- 5. Nopirkts -----------------------------------------------------------
    S = "5. Nopirktie objekti"
    nop = notikumi("nopirkts_datums")
    pievienot(S, "Nopirkti objekti", len(nop), "gab.", kolonnas=("nopirkts_datums",))
    pievienot(S, "Apjoms", round(sum(l.get("nopirkts_m3") or 0 for l in nop), 1), "m³",
              kolonnas=("nopirkts_m3",))
    pievienot(S, "Platība", round(sum(l.get("nopirkts_ha") or 0 for l in nop), 2), "ha",
              kolonnas=("nopirkts_ha",))
    summa = sum(l.get("iegades_summa") or 0 for l in nop)
    pievienot(S, "Iegādes summa", round(summa, 2), "EUR", kolonnas=("iegades_summa",))
    abi = [l for l in nop if l.get("iegades_summa") and l.get("max_piedavajums")]
    if abi:
        s_max = sum(l.get("max_piedavajums") for l in abi)
        s_iz = sum(l.get("iegades_summa") for l in abi)
        pievienot(S, "Cenas samazinājums pret maks. gala piedāvājumu", round((s_max - s_iz) / s_max * 100, 1),
                  "%", f"{s_max - s_iz:,.0f} EUR no {s_max:,.0f} EUR ({len(abi)} objekti)".replace(",", " "))
    else:
        pievienot(S, "Cenas samazinājums pret maks. gala piedāvājumu", None, "%",
                  "Nav objektu ar abām summām" if nop else "", ("max_piedavajums", "iegades_summa"))

    # --- 6. Atteikti -----------------------------------------------------------
    S = "6. Atteiktie objekti"
    att = notikumi("atteikts_datums")
    pievienot(S, "Atteikti objekti", len(att), "gab.", kolonnas=("atteikts_datums",))
    iemesli = Counter((l.get("atteikuma_iemesls") or "Nav norādīts") for l in att)

    # --- Pa agentiem -------------------------------------------------------------
    agenti = defaultdict(lambda: defaultdict(int))
    for l in jauni:
        a = agenti[l.agents]
        a["Leadi"] += 1
        a["Kvalitatīvi"] += kvalitativs(l)[0]
        a["Mērķa"] += merka(l)[0] is True
        a["Proaktīvi"] += proaktivs(l) is True
    for key, nos in (("kvalif_datums", "Kvalificēti"), ("priekszv_datums", "Priekšvērtējumi"),
                     ("tiksanas_datums", "Tikšanās"), ("apsekots_datums", "Apsekoti"),
                     ("nopirkts_datums", "Nopirkti"), ("atteikts_datums", "Atteikti")):
        for l in notikumi(key):
            agenti[l.agents][nos] += 1
    for l in nop:
        agenti[l.agents]["Nopirkts m³"] += round(l.get("nopirkts_m3") or 0)
        agenti[l.agents]["Iegādes summa EUR"] += round(l.get("iegades_summa") or 0)
    kolonnas = ["Leadi", "Kvalitatīvi", "Mērķa", "Proaktīvi", "Kvalificēti", "Priekšvērtējumi",
                "Tikšanās", "Apsekoti", "Nopirkti", "Atteikti", "Nopirkts m³", "Iegādes summa EUR"]
    pa_agentiem = [{"Agents": a, **{k: v.get(k, 0) for k in kolonnas}} for a, v in sorted(agenti.items())]

    # --- Piltuve tagad (pašreizējais stāvoklis, neatkarīgi no perioda) --------
    pedeja_ep = defaultdict(int)
    for l in leadi:
        pedeja_ep[l.atslega] = max(pedeja_ep[l.atslega], l.epizode)
    pc = Counter(l.posms for l in leadi if l.epizode == pedeja_ep[l.atslega])
    piltuve = [{"Posms": POSMU_NOSAUKUMI[p], "Leadi": pc.get(p, 0)} for p in POSMI if pc.get(p)]

    # --- Leadu tabula un datu kvalitāte ----------------------------------------
    tabula, kvalitate = [], []
    for l in sorted(leadi, key=lambda x: (x.get("lead_datums") or date.min), reverse=True):
        kv, kv_trukst = kvalitativs(l)
        mv, m_pamat = merka(l)
        tabula.append({
            "Lead": l.nosaukums,
            "Atslēga": l.atslega.split(":", 1)[-1] if not l.atslega.startswith("I:") else "",
            "Atslēgas veids": l.atslegas_veids,
            "Agents": l.agents,
            "Rindas": len(l.rindas),
            "Lead datums": l.get("lead_datums"),
            "Unikāls/atjaunots": "atjaunots" if l.atjaunots else "unikāls",
            "Posms tagad": POSMU_NOSAUKUMI[l.posms],
            "Kvalitatīvs": "jā" if kv else "nē",
            "Mērķa": {True: "jā", False: "nē", None: "?"}[mv],
            "Mērķa pamatojums": m_pamat,
            "Proaktīvs": {True: "jā", False: "nē", None: "?"}[proaktivs(l)],
            "Meža ha": l.get("meza_ha"),
            "1. piegāj. m³": l.get("m3_1_piegajiens"),
            "Kvalificēts": l.get("kvalif_datums"),
            "Priekšvērtējums": l.get("priekszv_datums"),
            "Tikšanās": l.get("tiksanas_datums"),
            "Apsekots": l.get("apsekots_datums"),
            "Nopirkts": l.get("nopirkts_datums"),
            "Iegādes summa EUR": l.get("iegades_summa"),
            "Atteikts": l.get("atteikts_datums"),
            "Atteikuma iemesls": l.get("atteikuma_iemesls"),
            "Piezīmes": "; ".join(l.piezimes),
        })
        for p in l.piezimes:
            kvalitate.append({"Agents": l.agents, "Lead": l.nosaukums, "Problēma": p})
        for a_key, b_key in (("lead_datums", "kvalif_datums"), ("kvalif_datums", "priekszv_datums"),
                             ("apsek_nosut_datums", "gala_pied_datums")):
            a, b = l.get(a_key), l.get(b_key)
            if a and b and b < a:
                kvalitate.append({"Agents": l.agents, "Lead": l.nosaukums,
                                  "Problēma": f"'{LAUKI_PEC_KEY[b_key].nosaukums}' ir pirms "
                                              f"'{LAUKI_PEC_KEY[a_key].nosaukums}'"})

    trukstosas = {}
    for b in dati.boardi:
        karte = dati.kartes.get(b.id, {})
        trukstosas[b.nosaukums] = [l.nosaukums for k, l in LAUKI_PEC_KEY.items()
                                   if k not in karte and k not in ("posms", "merka_lead", "kontaktpersona")]

    return Atskaite(periods, M, pa_agentiem, iemesli.most_common(), piltuve, tabula, kvalitate, trukstosas)


def _proc(a: int, b: int) -> str:
    return f"{a / b * 100:.0f}% no visiem" if b else ""


def teksta_kopsavilkums(a: Atskaite) -> str:
    rindas = [f"LEADU ATSKAITE — {a.periods.nosaukums} ({a.periods.no:%d.%m.%Y}–{a.periods.lidz:%d.%m.%Y})", ""]
    sadala = None
    for m in a.metriki:
        if m.sadala != sadala:
            sadala = m.sadala
            rindas += ["", sadala.upper()]
        v = "—" if m.vertiba is None else (f"{m.vertiba:,.2f}".rstrip("0").rstrip(".").replace(",", " ")
                                            if isinstance(m.vertiba, float) else f"{m.vertiba:,}".replace(",", " "))
        rindas.append(f"  • {m.nosaukums}: {v} {m.vieniba}".rstrip() + (f"  ({m.piezime})" if m.piezime else ""))
    if a.atteikuma_iemesli:
        rindas += ["", "ATTEIKUMA IEMESLI"] + [f"  • {i}: {n}" for i, n in a.atteikuma_iemesli]
    if a.pa_agentiem:
        rindas += ["", "PA AGENTIEM (leadi / kvalificēti / priekšvērt. / nopirkti)"]
        rindas += [f"  • {r['Agents']}: {r['Leadi']} / {r['Kvalificēti']} / {r['Priekšvērtējumi']} / {r['Nopirkti']}"
                   for r in a.pa_agentiem]
    if a.datu_kvalitate:
        rindas += ["", f"Datu kvalitāte: {len(a.datu_kvalitate)} piezīmes (sk. Excel lapu 'Datu kvalitāte')"]
    return "\n".join(rindas)


def iepriekseja_menesa_periods(sod: date | None = None) -> Periods:
    sod = sod or sodiena()
    pirm = sod.replace(day=1) - timedelta(days=1)
    return menesis(pirm.year, pirm.month)
