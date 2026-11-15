"""Atskaišu panelis BI stilā: KPI kartītes (HTML), piltuve, posmu laiki, tendence (Altair).

Tīras funkcijas bez Streamlit — view tikai izsauc un parāda rezultātu.
Krāsas — tikai aplikācijas paletes (views/ikonas.py, cenradis.py): Atskaišu sadaļas rozā datiem,
zaļš/sarkans tikai izmaiņu bultām (ar ▲▼), pelēkais palīgtekstam un otrai sērijai.
"""
from __future__ import annotations

import base64
import html
from dataclasses import dataclass

import altair as alt
import pandas as pd

from atskaites.metrikas import Atskaite

# Aplikācijas paletes krāsas (sk. views/ikonas.py SADALAS["atskaites"] un views/cenradis.py)
AKCENTS = "#DB2777"   # Atskaišu sadaļas krāsa — visi datu stabiņi, līnijas, akcenti
LABS = "#16A34A"      # pozitīva izmaiņa (kā Cenrādī)
SLIKTS = "#DC2626"    # negatīva izmaiņa (kā Cenrādī)
PELEKS = "#6b7280"    # palīgteksts, etiķetes, otrā sērija

CSS = """
<style>
.bk-sec{font-size:.78rem;font-weight:600;letter-spacing:.04em;text-transform:uppercase;color:#6b7280;margin:.2rem 0 .5rem}
.bk-grid{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:12px;margin-bottom:10px}
.bk-grid.g4{grid-template-columns:repeat(4,minmax(0,1fr))}
@media (max-width:1100px){.bk-grid,.bk-grid.g4{grid-template-columns:repeat(3,minmax(0,1fr))}}
@media (max-width:640px){.bk-grid,.bk-grid.g4{grid-template-columns:repeat(2,minmax(0,1fr))}}
.bk-kpi{border:1px solid rgba(128,128,128,.3);border-radius:.5rem;padding:12px 14px 10px;
        display:flex;flex-direction:column;gap:2px;min-height:118px;position:relative}
.bk-l{font-size:.8rem;color:#6b7280;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.bk-v{font-size:1.85rem;font-weight:600;line-height:1.15}
.bk-v small{font-size:.85rem;font-weight:500;opacity:.65;margin-left:3px}
.bk-v.nav{font-size:1.05rem;font-weight:500;opacity:.45;padding:.45rem 0 .3rem}
.bk-d{font-size:.78rem;opacity:.9;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.bk-d .s{opacity:.6}
.bk-d.labs b{color:#16A34A}.bk-d.slikts b{color:#DC2626}.bk-d.neitr b{opacity:.75}
.bk-spark{margin-top:auto;padding-top:6px}
.bk-chip{display:inline-block;border:1px solid rgba(128,128,128,.3);border-radius:999px;padding:2px 10px;
         font-size:.75rem;margin:0 6px 6px 0;opacity:.8}
.bk-josla{display:flex;flex-wrap:wrap;gap:6px 18px;font-size:.8rem;opacity:.75;margin:-4px 0 14px}
.bk-josla b{font-weight:600}
</style>
"""


def _skaitlis(v, vieniba: str = "") -> str:
    if v is None:
        return "—"
    if isinstance(v, float) and not v.is_integer():
        s = f"{v:,.1f}"
    else:
        v = int(round(v))
        if abs(v) >= 100_000:
            return f"{v / 1000:,.0f}K".replace(",", " ")
        s = f"{v:,}"
    return s.replace(",", " ").replace(".", ",")


def _sparkline(vertibas: list[float], plat: int = 140, augst: int = 28) -> str:
    if not vertibas or max(vertibas) == 0:
        return ""
    mx = max(vertibas)
    n = len(vertibas)
    pts = [(round(i * (plat - 6) / max(n - 1, 1) + 3, 1), round(augst - 3 - v / mx * (augst - 8), 1))
           for i, v in enumerate(vertibas)]
    linija = " ".join(f"{x},{y}" for x, y in pts)
    x, y = pts[-1]
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{plat}" height="{augst}" '
           f'viewBox="0 0 {plat} {augst}">'
           f'<polyline points="{linija}" fill="none" stroke="#6b7280" stroke-width="1.5" '
           f'stroke-linejoin="round" stroke-linecap="round"/>'
           f'<circle cx="{x}" cy="{y}" r="3" fill="{AKCENTS}"/></svg>')
    b64 = base64.b64encode(svg.encode()).decode()
    return f'<img alt="12 nedēļu tendence" src="data:image/svg+xml;base64,{b64}" style="width:100%;height:{augst}px">'


@dataclass
class Kartite:
    nosaukums: str
    vertiba: float | int | None
    vieniba: str = ""
    iepr: float | int | None = None       # iepriekšējā perioda vērtība
    augsana_laba: bool | None = True      # True: ▲ zaļš; False: ▲ sarkans; None: neitrāls
    tendence: list[float] | None = None   # nedēļu vērtības sparklainam
    paskaidrojums: str = ""
    galvenais: bool = False


def kartite_html(k: Kartite, salidz_nos: str) -> str:
    title = html.escape(k.paskaidrojums or k.nosaukums, quote=True)
    if k.vertiba is None:
        v = '<div class="bk-v nav">nav datu</div>'
    else:
        vien = f"<small>{html.escape(k.vieniba)}</small>" if k.vieniba else ""
        v = f'<div class="bk-v">{_skaitlis(k.vertiba)}{vien}</div>'
    d = ""
    if k.vertiba is not None and k.iepr is not None:
        starp = k.vertiba - k.iepr
        if abs(starp) < 1e-9:
            d = f'<div class="bk-d neitr"><b>= 0</b> <span class="s">pret {salidz_nos} ({_skaitlis(k.iepr)})</span></div>'
        else:
            aug = starp > 0
            klase = "neitr" if k.augsana_laba is None else ("labs" if aug == k.augsana_laba else "slikts")
            bulta = "▲" if aug else "▼"
            d = (f'<div class="bk-d {klase}"><b>{bulta} {_skaitlis(abs(starp))}</b> '
                 f'<span class="s">pret {salidz_nos} ({_skaitlis(k.iepr)})</span></div>')
    sp = f'<div class="bk-spark">{_sparkline(k.tendence)}</div>' if k.tendence else ""
    kl = "bk-kpi galvenais" if k.galvenais else "bk-kpi"
    return (f'<div class="{kl}" title="{title}"><div class="bk-l">{html.escape(k.nosaukums)}</div>'
            f'{v}{d}{sp}</div>')


def kartites_html(kartites: list[Kartite], salidz_nos: str, virsraksts: str = "") -> str:
    sec = f'<div class="bk-sec">{html.escape(virsraksts)}</div>' if virsraksts else ""
    kl = "bk-grid g4" if len(kartites) == 4 else "bk-grid"
    return CSS + sec + f'<div class="{kl}">' + "".join(kartite_html(k, salidz_nos) for k in kartites) + "</div>"


def josla_html(elementi: list[tuple[str, str]]) -> str:
    return CSS + '<div class="bk-josla">' + "".join(
        f"<span>{html.escape(a)}: <b>{html.escape(b)}</b></span>" for a, b in elementi) + "</div>"


def cipi_html(virsraksts: str, cipi: list[tuple[str, str]]) -> str:
    return (CSS + f'<div class="bk-sec">{html.escape(virsraksts)}</div>' + "".join(
        f'<span class="bk-chip" title="{html.escape(p, quote=True)}">{html.escape(n)}</span>' for n, p in cipi))


# --------------------------------------------------------------------------
# Datu sagatavošana no Atskaites
# --------------------------------------------------------------------------
def _m(a: Atskaite, nos: str):
    try:
        return a.metriks(nos)
    except KeyError:
        return None


def _piez(a: Atskaite, nos: str) -> str:
    for m in a.metriki:
        if m.nosaukums == nos:
            return m.piezime
    return ""


PILTUVE = [("Leadi kopā", "Leadi"), ("Kvalificēti objekti", "Kvalificēti"), ("Priekšvērtējumi", "Priekšvērtējums"),
           ("Sarunātas klātienes tikšanās", "Tikšanās"), ("Apsekoti dabā", "Apsekoti"), ("Nopirkti objekti", "Nopirkti")]

LAIKI = [("Vid. laiks lead → kvalifikācija", "Lead → izpētes zvans"),
         ("Vid. laiks kvalifikācija → priekšvērtējums", "Izpētes zvans → priekšvērtējums"),
         ("Vid. laiks nosūtīts apsekot → gala piedāvājums", "Apsekot → gala piedāvājums")]


def piltuves_df(a: Atskaite) -> pd.DataFrame:
    rindas, bāze = [], None
    for nos, isais in PILTUVE:
        v = _m(a, nos)
        if v is None:
            continue
        konv = (v / bāze * 100) if bāze else None
        rindas.append({"Posms": isais, "Skaits": int(v), "Konversija": konv,
                       "Etiķete": f"{int(v)}" + (f"  ·  {konv:.0f}% no leadiem" if konv is not None else "")})
        if bāze is None:
            bāze = v or None
    return pd.DataFrame(rindas)


def laiku_df(a: Atskaite) -> pd.DataFrame:
    rindas = []
    for nos, isais in LAIKI:
        v = _m(a, nos)
        if v is not None:
            rindas.append({"Posms": isais, "Dienas": v, "Mediāna": _piez(a, nos) or "",
                           "Etiķete": f"{v:.1f}".replace(".", ",") + " d."})
    return pd.DataFrame(rindas)


# --------------------------------------------------------------------------
# Grafiki
# --------------------------------------------------------------------------
ETIKETE = PELEKS


def _hbar(df: pd.DataFrame, y: str, x: str, etikete: str, tooltip: list, augstums_rindai: int = 34,
          krasa: str = AKCENTS) -> alt.Chart:
    secība = list(df[y])
    pamats = alt.Chart(df).encode(
        y=alt.Y(f"{y}:N", sort=secība, title=None, axis=alt.Axis(labelLimit=220, ticks=False, domain=False)),
    )
    stabini = pamats.mark_bar(color=krasa, cornerRadiusEnd=4, size=20).encode(
        x=alt.X(f"{x}:Q", title=None, axis=None, scale=alt.Scale(domainMin=0, nice=False,
                                                                  domainMax=float(df[x].max() or 1) * 1.25)),
        tooltip=tooltip)
    teksts = pamats.mark_text(align="left", dx=6, fontSize=12, color=ETIKETE).encode(x=f"{x}:Q", text=f"{etikete}:N")
    return (stabini + teksts).properties(height=max(len(df) * augstums_rindai, 60))


def piltuves_grafiks(df: pd.DataFrame) -> alt.Chart:
    return _hbar(df, "Posms", "Skaits", "Etiķete",
                 [alt.Tooltip("Posms:N"), alt.Tooltip("Skaits:Q"),
                  alt.Tooltip("Konversija:Q", format=".0f", title="No periodā saņemtajiem leadiem, %")])


def laiku_grafiks(df: pd.DataFrame) -> alt.Chart:
    return _hbar(df, "Posms", "Dienas", "Etiķete",
                 [alt.Tooltip("Posms:N"), alt.Tooltip("Dienas:Q", format=".1f", title="Vidēji, dienas"),
                  alt.Tooltip("Mediāna:N", title="Piezīme")])


def iemeslu_grafiks(iemesli: list[tuple[str, int]]) -> alt.Chart:
    df = pd.DataFrame(iemesli[:10], columns=["Iemesls", "Skaits"])
    df["Etiķete"] = df["Skaits"].astype(str)
    return _hbar(df, "Iemesls", "Skaits", "Etiķete", ["Iemesls:N", "Skaits:Q"], 36)


def tendences_grafiks(tend: list[dict], serijas=("Leadi", "Kvalificēti", "Priekšvērtējumi")) -> alt.Chart:
    """Viena sadaļas krāsa: 1. sērija pilna līnija, 2. raustīta, 3. pelēka — bez svešiem toņiem."""
    df = pd.DataFrame(tend)
    df["Nedēļa no"] = pd.to_datetime(df["Nedēļa"])
    gars = df.melt(id_vars=["Nedēļa no"], value_vars=list(serijas), var_name="Rādītājs", value_name="Skaits")
    dom = list(serijas)
    krasas = alt.Scale(domain=dom, range=[AKCENTS, AKCENTS, PELEKS][:len(dom)])
    svitras = alt.Scale(domain=dom, range=[[1, 0], [5, 4], [1, 0]][:len(dom)])
    pamats = alt.Chart(gars).encode(
        x=alt.X("Nedēļa no:T", title=None, axis=alt.Axis(format="%d.%m", tickCount="week", grid=False)),
        y=alt.Y("Skaits:Q", title=None, axis=alt.Axis(tickMinStep=1, gridOpacity=.35, domain=False)),
        color=alt.Color("Rādītājs:N", scale=krasas, legend=alt.Legend(orient="top", title=None, symbolType="stroke",
                                                                      symbolStrokeWidth=2)),
        strokeDash=alt.StrokeDash("Rādītājs:N", scale=svitras, legend=None),
    )
    linija = pamats.mark_line(strokeWidth=2)
    punkti = pamats.mark_circle(size=36).encode(
        tooltip=[alt.Tooltip("Nedēļa no:T", format="%d.%m.%Y"), "Rādītājs:N", "Skaits:Q"])
    return (linija + punkti).properties(height=230)
