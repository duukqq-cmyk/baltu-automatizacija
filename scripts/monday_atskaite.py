"""Leadu atskaite no monday.com komandrindā (piem., ikrīta cron / Windows Task Scheduler).

Piemēri:
    export MONDAY_API_TOKEN=...            # monday: Developers → My access tokens
    python scripts/monday_atskaite.py                         # tekošais mēnesis, boardi no konfigurācijas
    python scripts/monday_atskaite.py --menesis 2026-09 --excel sept.xlsx
    python scripts/monday_atskaite.py --boardi 123 456 --no 2026-10-01 --lidz 2026-10-15
    python scripts/monday_atskaite.py --demo --excel demo.xlsx

Boardu ID un kolonnu sasaisti ņem no dati/monday_konfiguracija.json (to saglabā web saskarne).
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from atskaites.demo import demo_boardi  # noqa: E402
from atskaites.eksports import excel_atskaite  # noqa: E402
from atskaites.metrikas import Periods, aprekinat, menesis, tekosais_menesis, teksta_kopsavilkums  # noqa: E402
from atskaites.modelis import Konfiguracija, sagatavot  # noqa: E402
from atskaites.monday import MondayKlients, MondayKluda  # noqa: E402

KONF = os.path.join(os.path.dirname(__file__), "..", "dati", "monday_konfiguracija.json")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Leadu atskaite no monday.com boardiem")
    p.add_argument("--menesis", help="YYYY-MM (noklusējums: tekošais mēnesis)")
    p.add_argument("--no", type=date.fromisoformat, help="perioda sākums YYYY-MM-DD")
    p.add_argument("--lidz", type=date.fromisoformat, help="perioda beigas YYYY-MM-DD")
    p.add_argument("--boardi", nargs="*", help="monday boardu ID (noklusējums: no konfigurācijas)")
    p.add_argument("--konfiguracija", default=KONF)
    p.add_argument("--demo", action="store_true", help="izmantot demo datus (bez API)")
    p.add_argument("--excel", help="saglabāt Excel atskaiti")
    p.add_argument("--txt", help="saglabāt teksta kopsavilkumu")
    a = p.parse_args(argv)

    if a.no and a.lidz:
        periods = Periods(a.no, a.lidz, f"{a.no:%d.%m.%Y}–{a.lidz:%d.%m.%Y}")
    elif a.menesis:
        g, m = map(int, a.menesis.split("-"))
        periods = menesis(g, m)
    else:
        periods = tekosais_menesis()

    konf = Konfiguracija.ielasit(a.konfiguracija)
    if a.demo:
        boardi = demo_boardi()
    else:
        token = os.environ.get("MONDAY_API_TOKEN")
        ids = a.boardi or konf.boardi
        if not token:
            print("Nav MONDAY_API_TOKEN vides mainīgā.", file=sys.stderr)
            return 2
        if not ids:
            print("Nav norādīti boardi (--boardi vai konfigurācijā).", file=sys.stderr)
            return 2
        try:
            k = MondayKlients(token)
            boardi = [k.ieladet_boardu(i) for i in ids]
        except MondayKluda as e:
            print(f"Kļūda: {e}", file=sys.stderr)
            return 1

    dati = sagatavot(boardi, konf)
    atsk = aprekinat(dati, periods)
    teksts = teksta_kopsavilkums(atsk)
    print(teksts)
    if a.excel:
        excel_atskaite(a.excel, atsk, dati)
        print(f"\nExcel: {a.excel}")
    if a.txt:
        with open(a.txt, "w", encoding="utf-8") as f:
            f.write(teksts)
    return 0


if __name__ == "__main__":
    sys.exit(main())
