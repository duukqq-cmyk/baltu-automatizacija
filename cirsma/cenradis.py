"""Cenrādis — viens cenu un normatīvu avots visām sadaļām.

Satur:
  * sortimentu matricas (cena EUR/m³, īpatsvars) katram cirtes veidam;
  * izdevumus EUR/m³ katram cirtes veidam un peļņas rezervi;
  * ciršanas noteikumus (max kailcirtes platības, šķērslaukuma sliekšņi);
  * cirsmas novērtējuma kolonnu kartējumu uz sortimentiem (resnā -> zāģbaļķi utt.).

Glabājas datubāzē kā JSON (atslēga "cenradis"), ar izmaiņu vēsturi.
"""
from __future__ import annotations

import copy
from dataclasses import asdict, dataclass, field

from .cirtes import IZLASES, KAILCIRTE, KOPSANA, Noteikumi
from .sortiment import (
    CITI, NOKLUSEJUMA_IZDEVUMI, NOKLUSEJUMA_KOPSANAS_MATRICA, NOKLUSEJUMA_MATRICA,
    NOKLUSEJUMA_PELNAS_REZERVE,
)

ATSLEGA = "cenradis"
VEIDI = (KAILCIRTE, KOPSANA, IZLASES)

# Cirsmas novērtējuma kolonnas (lietkoksnes daļas + malka)
NOV_KOLONNAS = {
    "ip_kval": "Īp. kvalitāte", "resna": "Resnā", "videja": "Vidējā", "tieva": "Tievā",
    "p_malka": "P. malka", "malka": "Malka",
}

NOKLUSEJUMA_KARTEJUMS: dict[str, dict[str, str]] = {
    "P": {"ip_kval": "A klase", "resna": "Zāģbaļķi", "videja": "Sīkbaļķi", "tieva": "Tara",
          "p_malka": "Papīrmalka", "malka": "Malka"},
    "E": {"ip_kval": "Zāģbaļķi", "resna": "Zāģbaļķi", "videja": "Sīkbaļķi", "tieva": "Tara",
          "p_malka": "Papīrmalka", "malka": "Malka"},
    "B": {"ip_kval": "Finieris A", "resna": "Finieris B", "videja": "Finieris C", "tieva": "Tara",
          "p_malka": "Papīrmalka", "malka": "Malka"},
    "A": {"ip_kval": "Zāģbaļķi", "resna": "Zāģbaļķi", "videja": "Tara", "tieva": "Tara",
          "p_malka": "Papīrmalka", "malka": "Malka"},
    "Ma": {"ip_kval": "Zāģbaļķi", "resna": "Zāģbaļķi", "videja": "Zāģbaļķi", "tieva": "Tara",
           "p_malka": "Tara", "malka": "Malka"},
    "Ba": {"ip_kval": "Tara", "resna": "Tara", "videja": "Tara", "tieva": "Tara",
           "p_malka": "Tara", "malka": "Malka"},
    "Oz/Os": {"ip_kval": "Zāģbaļķi", "resna": "Zāģbaļķi", "videja": "Tara", "tieva": "Tara",
              "p_malka": "Kamīnmalka", "malka": "Kamīnmalka"},
    CITI: {k: "Malka" for k in NOV_KOLONNAS},
}


@dataclass
class Cenradis:
    matricas: dict[str, dict[str, dict[str, tuple[float, float]]]] = field(default_factory=lambda: {
        KAILCIRTE: copy.deepcopy(NOKLUSEJUMA_MATRICA),
        KOPSANA: copy.deepcopy(NOKLUSEJUMA_KOPSANAS_MATRICA),
        IZLASES: copy.deepcopy(NOKLUSEJUMA_MATRICA),
    })
    izdevumi: dict[str, dict[str, float]] = field(default_factory=lambda: {
        v: dict(NOKLUSEJUMA_IZDEVUMI) for v in VEIDI})
    pelnas_rezerve: float = NOKLUSEJUMA_PELNAS_REZERVE
    noteikumi: Noteikumi = field(default_factory=Noteikumi)
    kartejums: dict[str, dict[str, str]] = field(default_factory=lambda: copy.deepcopy(NOKLUSEJUMA_KARTEJUMS))

    # --- JSON --------------------------------------------------------------
    def uz_json(self) -> dict:
        return {
            "matricas": {v: {k: {s: [c, i] for s, (c, i) in sort.items()} for k, sort in m.items()}
                         for v, m in self.matricas.items()},
            "izdevumi": self.izdevumi,
            "pelnas_rezerve": self.pelnas_rezerve,
            "noteikumi": asdict(self.noteikumi),
            "kartejums": self.kartejums,
        }

    @classmethod
    def no_json(cls, d: dict | None) -> "Cenradis":
        c = cls()
        if not d:
            return c
        for v, m in (d.get("matricas") or {}).items():
            c.matricas[v] = {k: {s: (float(x[0]), float(x[1])) for s, x in sort.items()}
                             for k, sort in m.items()}
        for v, izd in (d.get("izdevumi") or {}).items():
            c.izdevumi[v] = {p: float(x) for p, x in izd.items()}
        if d.get("pelnas_rezerve") is not None:
            c.pelnas_rezerve = float(d["pelnas_rezerve"])
        if d.get("noteikumi"):
            zinami = set(Noteikumi.__dataclass_fields__)
            c.noteikumi = Noteikumi(**{k: v for k, v in d["noteikumi"].items() if k in zinami})
        for k, kart in (d.get("kartejums") or {}).items():
            c.kartejums[k] = dict(kart)
        return c

    # --- palīgi ------------------------------------------------------------
    def cena(self, kolonna: str, sortiments: str, veids: str = KAILCIRTE) -> float | None:
        x = self.matricas.get(veids, {}).get(kolonna, {}).get(sortiments)
        return x[0] if x else None

    def sortimenti(self, veids: str = KAILCIRTE) -> list[str]:
        redzeti: list[str] = []
        for sort in self.matricas.get(veids, {}).values():
            for s in sort:
                if s not in redzeti:
                    redzeti.append(s)
        return redzeti

    def bridinajumi(self) -> list[str]:
        """Īpatsvaru summas ≠ 100 % u.c. konfigurācijas kļūdas."""
        k = []
        for veids, m in self.matricas.items():
            for kol, sort in m.items():
                summa = sum(i for _, i in sort.values())
                if sort and abs(summa - 1) > 0.001:
                    k.append(f"{veids} / {kol}: īpatsvaru summa {summa:.1%} (jābūt 100 %)")
        for kol, kart in self.kartejums.items():
            for lauks, sort in kart.items():
                if self.cena(kol, sort) is None:
                    k.append(f"Novērtējuma kartējums {kol} / {NOV_KOLONNAS.get(lauks, lauks)}: "
                             f"sortimentam '{sort}' nav cenas kailcirtes cenrādī")
        return k
