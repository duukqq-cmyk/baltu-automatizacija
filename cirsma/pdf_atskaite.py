"""Priekšvērtējuma PDF atskaite (viena faila kopsavilkums monday / e-pastam / arhīvam).

Saturs: objekts, galvenie skaitļi, cirsmas (katra kailcirtes daļa atsevišķi),
apjoms pa sugām, finanses, riska karogi un — ja ir kartes dati — cirsmu skice
(nogabalu robežas + iezīmētie laukumi, LKS-92 mērogā).
"""
from __future__ import annotations

import os
from datetime import date

from fpdf import FPDF

from .cirtes import CIRTES_NOSAUKUMI
from .formula import SUGU_NOSAUKUMI
from .report import cirsmas_rindas, nog_nosaukums

_FONTI = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dati", "fonti")
_KRASAS = {"Kailcirte": (255, 75, 75), "Kopšanas cirte": (245, 158, 11), "Izlases cirte": (168, 85, 247),
           "Atdalošā josla": (120, 113, 108)}


def _sk(v, dec=2) -> str:
    if v is None:
        return "—"
    return f"{v:,.{dec}f}".replace(",", " ").replace(".", ",")


class _Pdf(FPDF):
    def footer(self):
        self.set_y(-12)
        self.set_font("DejaVu", "", 7)
        self.set_text_color(120)
        self.cell(0, 6, f"Baltu Koks · cirsmas priekšvērtējums · {date.today():%d.%m.%Y} · {self.page_no()}. lpp.",
                  align="C")


def _tabula(pdf: FPDF, galvas: list[str], rindas: list[list], platumi: list[float], izl: list[str]) -> None:
    pdf.set_font("DejaVu", "B", 7.5)
    pdf.set_fill_color(230, 236, 245)
    for g, w, a in zip(galvas, platumi, izl):
        pdf.cell(w, 6, g, border=1, fill=True, align=a)
    pdf.ln()
    pdf.set_font("DejaVu", "", 7.5)
    for r in rindas:
        if pdf.get_y() > 275:
            pdf.add_page()
        bold = str(r[0]).startswith("KOPĀ")
        pdf.set_font("DejaVu", "B" if bold else "", 7.5)
        for v, w, a in zip(r, platumi, izl):
            t = str(v)
            while pdf.get_string_width(t) > w - 1.5 and len(t) > 3:
                t = t[:-2] + "…" if not t.endswith("…") else t[:-2] + "…"
            pdf.cell(w, 5.5, t, border=1, align=a)
        pdf.ln()


def _skice(pdf: FPDF, objekti: list[dict], robezas: dict[str, dict] | None, augstums: float = 85) -> None:
    """Vienkāršota cirsmu skice LKS-92 mērogā."""
    from karte.geometrija import lks_geometrija  # noqa: PLC0415
    import shapely  # noqa: PLC0415

    nog = {k: lks_geometrija(g) for k, g in (robezas or {}).items()}
    obj = [(o, lks_geometrija(o["geometry"])) for o in objekti
           if o["geometry"]["type"] in ("Polygon", "MultiPolygon")]
    visi = list(nog.values()) + [g for _, g in obj]
    if not visi:
        return
    minx, miny, maxx, maxy = shapely.union_all(visi).bounds
    platums = 180
    merogs = min(platums / max(maxx - minx, 1), augstums / max(maxy - miny, 1))
    x0 = 15 + (platums - (maxx - minx) * merogs) / 2
    y0 = pdf.get_y()

    def punkti(gred):
        return [(x0 + (x - minx) * merogs, y0 + (maxy - y) * merogs) for x, y, *_ in gred.coords]

    def zimet(g, krasa, fill, biezums):
        for p in getattr(g, "geoms", [g]):
            if p.geom_type != "Polygon":
                continue
            pdf.set_draw_color(*krasa)
            pdf.set_line_width(biezums)
            if fill:
                pdf.set_fill_color(*fill)
            pdf.polygon(punkti(p.exterior), style="DF" if fill else "D")

    for g in nog.values():
        zimet(g, (150, 150, 150), None, 0.2)
    for o, g in obj:
        k = _KRASAS.get(o.get("statuss"))
        if k:
            zimet(g, k, tuple(int(255 - (255 - x) * 0.35) for x in k), 0.5)
    pdf.set_font("DejaVu", "B", 6.5)
    pdf.set_text_color(40)
    for apz, g in nog.items():
        c = g.representative_point()
        pdf.text(x0 + (c.x - minx) * merogs - 1.5, y0 + (maxy - c.y) * merogs + 1, apz.split(" ")[-1])
    pdf.set_text_color(0)
    pdf.set_y(y0 + (maxy - miny) * merogs + 3)
    # mērogjosla
    garums_m = 10 ** int(len(str(int(max(maxx - minx, 1) / 4))) - 1) * 1
    while garums_m * merogs < 15:
        garums_m *= 2
    y = pdf.get_y()
    pdf.set_draw_color(0)
    pdf.set_line_width(0.4)
    pdf.line(15, y, 15 + garums_m * merogs, y)
    pdf.set_font("DejaVu", "", 6.5)
    pdf.text(17 + garums_m * merogs, y + 1, f"{garums_m} m")
    x = 60
    for nos, k in _KRASAS.items():
        pdf.set_fill_color(*k)
        pdf.rect(x, y - 1.5, 3, 3, style="F")
        pdf.text(x + 4, y + 1, nos)
        x += 32
    pdf.ln(5)


def priekvertejuma_pdf(inv, vertejumi, fin, *, nosaukums: str = "", autors: str | None = None,
                       objekti: list[dict] | None = None, robezas: dict[str, dict] | None = None,
                       piezimes: str = "") -> bytes:
    pdf = _Pdf(format="A4")
    pdf.add_font("DejaVu", "", os.path.join(_FONTI, "DejaVuSans.ttf"))
    pdf.add_font("DejaVu", "B", os.path.join(_FONTI, "DejaVuSans-Bold.ttf"))
    pdf.set_auto_page_break(True, 15)
    pdf.set_margins(15, 14, 15)
    pdf.add_page()

    pdf.set_font("DejaVu", "B", 15)
    pdf.cell(0, 9, "Cirsmas priekšvērtējums", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("DejaVu", "", 9)
    rindas = [
        ("Objekts", nosaukums or f"NĪ {inv.ipasums or '—'}"),
        ("Zemes vienība", inv.zemes_vieniba or "—"),
        ("Datu avots", inv.avots),
        ("Datums", f"{date.today():%d.%m.%Y}" + (f" · {autors}" if autors else "")),
    ]
    for k, v in rindas:
        pdf.set_font("DejaVu", "B", 9)
        pdf.cell(35, 5.5, k)
        pdf.set_font("DejaVu", "", 9)
        pdf.cell(0, 5.5, str(v), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    # Galvenie skaitļi
    plat = sum(v.cirsmas_platiba for v in vertejumi if v.cirtams)
    kartites = [("Cērtamais apjoms", f"{_sk(fin.kopejais_m3, 0)} m³"),
                ("Cērtamā platība", f"{_sk(plat)} ha"),
                ("Max iegādes summa", f"{_sk(fin.max_iegades_summa, 0)} €"),
                ("Cena", f"{_sk(fin.cena_eur_m3)} €/m³")]
    w = 180 / len(kartites)
    y = pdf.get_y()
    for i, (k, v) in enumerate(kartites):
        pdf.set_fill_color(245, 247, 250)
        pdf.rect(15 + i * w, y, w - 2, 15, style="F")
        pdf.set_xy(17 + i * w, y + 1.5)
        pdf.set_font("DejaVu", "", 7.5)
        pdf.cell(w - 4, 4, k)
        pdf.set_xy(17 + i * w, y + 6.5)
        pdf.set_font("DejaVu", "B", 12)
        pdf.cell(w - 4, 7, v)
    pdf.set_y(y + 18)

    if objekti:
        pdf.set_font("DejaVu", "B", 10)
        pdf.cell(0, 7, "Cirsmu skice", new_x="LMARGIN", new_y="NEXT")
        _skice(pdf, objekti, robezas)

    # Cirsmas
    c_rindas = cirsmas_rindas(inv, vertejumi, fin)
    pdf.set_font("DejaVu", "B", 10)
    pdf.cell(0, 7, "Cirsmas", new_x="LMARGIN", new_y="NEXT")
    if c_rindas:
        _tabula(pdf, ["Nog.", "Cirte", "ha", "m³/ha", "Tips", "Formula", "Bon.", "Vec.", "m³"],
                [[r["Nog."], r["Cirte"], _sk(r["Platība ha"]), _sk(r["Krāja m³/ha"], 0),
                  r["Meža tips"] or "", r["Formula"] or "", r["Bonitāte"] or "", r["Vecums"] or "",
                  _sk(r["Apjoms m³"])] for r in c_rindas]
                + [["KOPĀ", "", _sk(sum(r["Platība ha"] for r in c_rindas)), "", "", "", "", "",
                    _sk(sum(r["Apjoms m³"] for r in c_rindas))]],
                [22, 26, 14, 14, 22, 42, 12, 12, 16], ["L", "L", "R", "R", "L", "L", "C", "R", "R"])
    else:
        pdf.set_font("DejaVu", "", 9)
        pdf.cell(0, 6, "Nav cērtamo nogabalu.", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    # Apjoms pa sugām + finanses blakus
    if pdf.get_y() > 220:
        pdf.add_page()
    y = pdf.get_y()
    pdf.set_font("DejaVu", "B", 10)
    pdf.cell(85, 7, "Apjoms pa sugām")
    pdf.set_x(110)
    pdf.cell(0, 7, "Finanses", new_x="LMARGIN", new_y="NEXT")
    y0 = pdf.get_y()
    pdf.set_font("DejaVu", "", 8.5)
    for s, m3 in fin.pa_sugam_m3.items():
        pdf.cell(55, 5, SUGU_NOSAUKUMI.get(s, s))
        pdf.cell(30, 5, f"{_sk(m3)} m³", align="R", new_x="LMARGIN", new_y="NEXT")
    y_sugas = pdf.get_y()
    pdf.set_y(y0)
    fin_r = [("Ieņēmumi no sortimentiem", fin.ienemumi_kopa)] + \
        [(p, -e) for p, e in fin.izdevumi.items()] + \
        [("Peļņas rezerve", -fin.pelna), ("MAX IEGĀDES SUMMA", fin.max_iegades_summa)]
    for k, v in fin_r:
        pdf.set_x(110)
        pdf.set_font("DejaVu", "B" if k.startswith("MAX") else "", 8.5)
        pdf.cell(55, 5, k)
        pdf.cell(30, 5, f"{_sk(v)} €", align="R", new_x="LMARGIN", new_y="NEXT")
    if len(fin.pa_veidiem) > 1:
        for veids, d in fin.pa_veidiem.items():
            pdf.set_x(110)
            pdf.set_font("DejaVu", "", 7.5)
            pdf.cell(85, 4.5, f"{CIRTES_NOSAUKUMI[veids]}: {_sk(d['m3'], 0)} m³, segums {_sk(d['segums'], 0)} €",
                      new_x="LMARGIN", new_y="NEXT")
    pdf.set_y(max(pdf.get_y(), y_sugas) + 3)

    # Riski
    riski = [(v, b) for v in vertejumi if v.cirtams for b in v.bridinajumi if b.startswith(("⚠", "✎"))]
    if riski:
        pdf.set_font("DejaVu", "B", 10)
        pdf.cell(0, 7, "Pārbaudāmais (riski un labojumi)", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("DejaVu", "", 8)
        for v, b in riski:
            pdf.multi_cell(0, 4.5, f"{nog_nosaukums(inv, v.nogabals)}: {b}", new_x="LMARGIN", new_y="NEXT")
    if piezimes:
        pdf.ln(2)
        pdf.set_font("DejaVu", "B", 10)
        pdf.cell(0, 7, "Piezīmes", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("DejaVu", "", 8.5)
        pdf.multi_cell(0, 4.5, piezimes)
    return bytes(pdf.output())
