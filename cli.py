#!/usr/bin/env python3
"""Komandrindas rīks: inventarizācijas PDF -> cirsmas vērtības atskaite.

Lietošana:
    python cli.py <inventarizacijas.pdf> [--excel atskaite.xlsx] [--txt atskaite.txt]
"""
from __future__ import annotations

import argparse
import sys

from cirsma.parser import parse_inventory_pdf
from cirsma.rules import atlasit_kailcirtes
from cirsma.sortiment import aprekinat
from cirsma.report import teksta_atskaite, excel_atskaite


def main() -> int:
    ap = argparse.ArgumentParser(description="Cirsmas vērtības aprēķins no inventarizācijas PDF")
    ap.add_argument("pdf", help="Meža inventarizācijas PDF fails")
    ap.add_argument("--excel", help="Saglabāt Excel atskaiti šajā failā")
    ap.add_argument("--txt", help="Saglabāt teksta atskaiti šajā failā")
    args = ap.parse_args()

    inv = parse_inventory_pdf(args.pdf)
    vertejumi = atlasit_kailcirtes(inv.nogabali)
    fin = aprekinat(vertejumi)
    atskaite = teksta_atskaite(inv, vertejumi, fin)

    print(atskaite)
    if args.txt:
        with open(args.txt, "w", encoding="utf-8") as f:
            f.write(atskaite + "\n")
        print(f"\nTeksta atskaite: {args.txt}", file=sys.stderr)
    if args.excel:
        excel_atskaite(args.excel, inv, vertejumi, fin)
        print(f"Excel atskaite: {args.excel}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
