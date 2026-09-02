"""Gala atskaites ģenerēšana (teksts + Excel)."""
from __future__ import annotations

from .formula import SUGU_NOSAUKUMI
from .parser import Inventarizacija
from .rules import Vertejums
from .sortiment import FinansuRezultats


def teksta_atskaite(inv: Inventarizacija, vertejumi: list[Vertejums], fin: FinansuRezultats) -> str:
    """Gala atskaite pamācībā prasītajā formātā + izvērsts pamatojums."""
    cirt = [v for v in vertejumi if v.atlauta_kailcirte]
    necirt = [v for v in vertejumi if not v.atlauta_kailcirte]

    nog_saraksts = ";".join(f"{v.nogabals.nr}.nog" for v in cirt)
    sugas = "; ".join(f"{s}={round(m3)}m3" for s, m3 in fin.pa_sugam_m3.items())
    summa_txt = f"{fin.max_iegades_summa:,.0f}".replace(",", " ")

    rindas = [
        "CIRSMAS VĒRTĪBAS APRĒĶINS",
        "=" * 60,
        "",
        f"NĪ {inv.ipasums or '—'} , zemes vienība {inv.zemes_vieniba or '—'}",
        "",
        f"Kailcirtes: {nog_saraksts}",
        "",
        f"Cērtamais apjoms: {round(fin.kopejais_m3)}m3 ( {sugas} )",
        "",
        f"Maksimālā iegādes summa = {summa_txt} EUR, jeb {fin.cena_eur_m3:.2f} EUR/m3.",
        "",
        "-" * 60,
        "DETALIZĒTS APRĒĶINS",
        "-" * 60,
        "",
        "Kailcirtei atbilstošie nogabali:",
    ]
    for v in cirt:
        n = v.nogabals
        apjoms = next((a for a in fin.apjomi if a.nog_nr == n.nr), None)
        rindas.append(
            f"  {n.nr}.nog | {n.platiba_ha} ha x {n.kraja_m3_ha:.0f} m3/ha = "
            f"{apjoms.kopejais_m3 if apjoms else 0:.2f} m3 | {n.formula} | {v.pamatojums}"
        )
    rindas += ["", "Kailcirtei NEatbilstošie nogabali:"]
    for v in necirt:
        rindas.append(f"  {v.nogabals.nr}.nog | {v.pamatojums}")

    rindas += ["", "Apjoms pa sugām:"]
    for s, m3 in fin.pa_sugam_m3.items():
        rindas.append(f"  {SUGU_NOSAUKUMI.get(s, s):14s} {m3:10.2f} m3")

    rindas += [
        "",
        "Finanses:",
        f"  Ieņēmumi no sortimentiem:  {fin.ienemumi_kopa:12,.2f} EUR".replace(",", " "),
    ]
    for poz, eur in fin.izdevumi.items():
        rindas.append(f"  {poz + ':':27s}{-eur:12,.2f} EUR".replace(",", " "))
    rindas += [
        f"  Peļņas rezerve (10%):      {-fin.pelna:12,.2f} EUR".replace(",", " "),
        f"  MAX IEGĀDES SUMMA:         {fin.max_iegades_summa:12,.2f} EUR".replace(",", " "),
        f"  Cena:                      {fin.cena_eur_m3:12.2f} EUR/m3",
    ]
    return "\n".join(rindas)


def excel_atskaite(cels: str, inv: Inventarizacija, vertejumi: list[Vertejums], fin: FinansuRezultats) -> None:
    """Izveido Excel atskaiti ar 3 lapām: kopsavilkums, nogabali, sortimenti."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    wb = Workbook()
    bold = Font(bold=True)
    header_fill = PatternFill("solid", fgColor="D9E1F2")

    # 1. lapa — kopsavilkums
    ws = wb.active
    ws.title = "Kopsavilkums"
    cirt = [v for v in vertejumi if v.atlauta_kailcirte]
    dati = [
        ("Objekts", f"NĪ {inv.ipasums or '—'}, zemes vienība {inv.zemes_vieniba or '—'}"),
        ("Kailcirtes", ";".join(f"{v.nogabals.nr}.nog" for v in cirt)),
        ("Cērtamais apjoms, m3", fin.kopejais_m3),
        *[(f"  t.sk. {SUGU_NOSAUKUMI.get(s, s)} ({s}), m3", m3) for s, m3 in fin.pa_sugam_m3.items()],
        ("Ieņēmumi kopā, EUR", fin.ienemumi_kopa),
        *[(f"Izdevumi: {p}, EUR", -e) for p, e in fin.izdevumi.items()],
        ("Peļņas rezerve, EUR", -fin.pelna),
        ("MAKSIMĀLĀ IEGĀDES SUMMA, EUR", fin.max_iegades_summa),
        ("Cena, EUR/m3", fin.cena_eur_m3),
    ]
    for r, (k, val) in enumerate(dati, start=1):
        ws.cell(r, 1, k).font = bold
        ws.cell(r, 2, val)
    ws.column_dimensions["A"].width = 38
    ws.column_dimensions["B"].width = 46

    # 2. lapa — nogabalu vērtējums
    ws2 = wb.create_sheet("Nogabali")
    galvas = ["Nog.", "Platība ha", "Krāja m3/ha", "Formula", "Bonitāte", "Caurmērs cm",
              "Vecums", "Valdošā suga", "Kailcirte?", "Pamatojums", "Apjoms m3"]
    for c, g in enumerate(galvas, start=1):
        cell = ws2.cell(1, c, g)
        cell.font = bold
        cell.fill = header_fill
    for r, v in enumerate(vertejumi, start=2):
        n = v.nogabals
        apjoms = next((a.kopejais_m3 for a in fin.apjomi if a.nog_nr == n.nr), "")
        for c, val in enumerate([n.nr, n.platiba_ha, n.kraja_m3_ha, n.formula, n.bonitate,
                                 n.vid_caurmers, n.vecums, v.valdosa_suga,
                                 "JĀ" if v.atlauta_kailcirte else "NĒ", v.pamatojums, apjoms],
                                start=1):
            ws2.cell(r, c, val)
    for kol, w in zip("ABCDEFGHIJK", [6, 10, 11, 22, 9, 12, 8, 12, 10, 60, 11]):
        ws2.column_dimensions[kol].width = w

    # 3. lapa — sortimentu aprēķins
    ws3 = wb.create_sheet("Sortimenti")
    galvas3 = ["Suga", "Sortiments", "Īpatsvars", "Apjoms m3", "Cena EUR/m3", "Summa EUR"]
    for c, g in enumerate(galvas3, start=1):
        cell = ws3.cell(1, c, g)
        cell.font = bold
        cell.fill = header_fill
    r = 2
    for rinda in fin.detalas:
        for c, k in enumerate(galvas3, start=1):
            ws3.cell(r, c, rinda[k])
        r += 1
    ws3.cell(r, 5, "KOPĀ:").font = bold
    ws3.cell(r, 6, fin.ienemumi_kopa).font = bold
    for kol, w in zip("ABCDEF", [10, 14, 10, 11, 12, 12]):
        ws3.column_dimensions[kol].width = w

    wb.save(cels)
