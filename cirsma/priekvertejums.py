"""Priekšvērtējuma saglabāšanas formāts (JSON) — lai to varētu atvērt tieši tādu, kāds bija.

Saglabā: avotu (PDF / karte), lietotāja labojumus, kartes objektus, tobrīd lietoto
cenrādi un kopsavilkumu (meklēšanai un sarakstam). Avota PDF glabājas atsevišķi (baiti).
"""
from __future__ import annotations

import base64
from dataclasses import asdict, fields

from .labojumi import Labojums

VERSIJA = 1


def labojumi_uz_json(labojumi: dict[str, Labojums]) -> dict:
    return {k: {f: v for f, v in asdict(l).items() if v is not None} for k, l in labojumi.items()}


def labojumi_no_json(d: dict | None) -> dict[str, Labojums]:
    zinami = {f.name for f in fields(Labojums)}
    return {k: Labojums(**{f: v for f, v in x.items() if f in zinami}) for k, x in (d or {}).items()}


def kopsavilkums(inv, vertejumi, fin) -> dict:
    return {
        "m3": fin.kopejais_m3,
        "max_summa": fin.max_iegades_summa,
        "cena_eur_m3": fin.cena_eur_m3,
        "ienemumi": fin.ienemumi_kopa,
        "platiba_ha": round(sum(v.cirsmas_platiba for v in vertejumi if v.cirtams), 2),
        "nogabali": len([v for v in vertejumi if v.cirtams]),
        "pa_veidiem": fin.pa_veidiem,
        "ipasums": inv.ipasums,
        "zemes_vieniba": inv.zemes_vieniba,
        "datu_avots": inv.avots,
    }


def dati(*, avots: str, labojumi: dict[str, Labojums], cenradis_json: dict,
         objekti: list[dict] | None = None, kadastrs: str | None = None,
         pdf_nosaukums: str | None = None, piezimes: str = "",
         atskaite_pdf: bytes | None = None) -> dict:
    return {
        "versija": VERSIJA,
        "avots": avots,                       # "pdf" vai "karte"
        "labojumi": labojumi_uz_json(labojumi),
        "cenradis": cenradis_json,
        "objekti": objekti or [],
        "kadastrs": kadastrs,
        "pdf_nosaukums": pdf_nosaukums,
        "piezimes": piezimes,
        "atskaite_pdf_b64": base64.b64encode(atskaite_pdf).decode() if atskaite_pdf else None,
    }


def atskaites_pdf(d: dict) -> bytes | None:
    b = d.get("atskaite_pdf_b64")
    return base64.b64decode(b) if b else None


def monday_teksts(nosaukums: str, kops: dict, saite: str | None = None) -> str:
    """Īss kopsavilkums ielīmēšanai monday update / e-pastā."""
    def sk(v, d=0):
        return "—" if v is None else f"{v:,.{d}f}".replace(",", " ").replace(".", ",")
    rindas = [
        f"Priekšvērtējums: {nosaukums}",
        f"Kadastrs: {kops.get('zemes_vieniba') or '—'}",
        f"Cērtamais apjoms: {sk(kops.get('m3'))} m³ · platība {sk(kops.get('platiba_ha'), 2)} ha "
        f"· {kops.get('nogabali', 0)} nog.",
        f"Max iegādes summa: {sk(kops.get('max_summa'))} € ({sk(kops.get('cena_eur_m3'), 2)} €/m³)",
    ]
    if saite:
        rindas.append(saite)
    return "\n".join(rindas)
