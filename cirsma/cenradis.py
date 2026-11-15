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


# ---------------------------------------------------------------------------
# Varianti: katrai cenrāža sadaļai (cilnei) vairāki nosaukti varianti, viens — noklusējums
# ---------------------------------------------------------------------------

ATSLEGA_VARIANTI = "cenradis_varianti"
SADALAS = ["kailcirte", "kopsana", "izlases", "izdevumi", "kartejums", "noteikumi"]
SADALU_NOSAUKUMI = {
    "kailcirte": "Kailcirte", "kopsana": "Kopšanas cirte", "izlases": "Izlases cirte",
    "izdevumi": "Izdevumi un peļņa", "kartejums": "Novērtējuma kartējums", "noteikumi": "Noteikumi",
}
PAMATA = "Pamata"


def sadalas_dati(c: Cenradis, sadala: str) -> dict:
    """Vienas sadaļas dati JSON formā."""
    j = c.uz_json()
    if sadala in (KAILCIRTE, KOPSANA, IZLASES):
        return {"matrica": j["matricas"][sadala]}
    if sadala == "izdevumi":
        return {"izdevumi": j["izdevumi"], "pelnas_rezerve": j["pelnas_rezerve"]}
    if sadala == "kartejums":
        return {"kartejums": j["kartejums"]}
    return {"noteikumi": j["noteikumi"]}


def ar_sadalu(c: Cenradis, sadala: str, dati: dict) -> Cenradis:
    """Atgriež cenrāža kopiju, kurā vienas sadaļas dati aizstāti."""
    j = copy.deepcopy(c.uz_json())
    if sadala in (KAILCIRTE, KOPSANA, IZLASES):
        j["matricas"][sadala] = dati["matrica"]
    elif sadala == "izdevumi":
        j["izdevumi"] = dati["izdevumi"]
        j["pelnas_rezerve"] = dati["pelnas_rezerve"]
    elif sadala == "kartejums":
        j["kartejums"] = dati["kartejums"]
    else:
        j["noteikumi"] = dati["noteikumi"]
    return Cenradis.no_json(j)


@dataclass
class CenrazaVarianti:
    """{sadaļa: {"noklusejums": nosaukums, "varianti": {nosaukums: sadaļas dati}}}"""
    sadalas: dict[str, dict] = field(default_factory=dict)

    @classmethod
    def no_cenradis(cls, c: Cenradis, nosaukums: str = PAMATA) -> "CenrazaVarianti":
        return cls({s: {"noklusejums": nosaukums, "varianti": {nosaukums: sadalas_dati(c, s)}}
                    for s in SADALAS})

    @classmethod
    def no_json(cls, d: dict | None) -> "CenrazaVarianti":
        v = cls.no_cenradis(Cenradis())
        for s, x in ((d or {}).get("sadalas") or {}).items():
            if s in SADALAS and x.get("varianti"):
                nokl = x.get("noklusejums") if x.get("noklusejums") in x["varianti"] else next(iter(x["varianti"]))
                v.sadalas[s] = {"noklusejums": nokl, "varianti": dict(x["varianti"])}
        return v

    def uz_json(self) -> dict:
        return {"sadalas": copy.deepcopy(self.sadalas)}

    def nosaukumi(self, sadala: str) -> list[str]:
        return list(self.sadalas[sadala]["varianti"])

    def noklusejums(self, sadala: str) -> str:
        return self.sadalas[sadala]["noklusejums"]

    def noklusejuma_izvele(self) -> dict[str, str]:
        return {s: self.noklusejums(s) for s in SADALAS}

    def kompozicija(self, izvele: dict[str, str] | None = None) -> Cenradis:
        """Cenrādis no katras sadaļas izvēlētā (vai noklusējuma) varianta."""
        c = Cenradis()
        for s in SADALAS:
            nos = (izvele or {}).get(s)
            if nos not in self.sadalas[s]["varianti"]:
                nos = self.noklusejums(s)
            c = ar_sadalu(c, s, self.sadalas[s]["varianti"][nos])
        return c

    # --- darbības ar variantiem ------------------------------------------------
    def izveidot(self, sadala: str, nosaukums: str, no: str | None = None) -> None:
        nosaukums = nosaukums.strip()
        if not nosaukums:
            raise ValueError("Ievadi varianta nosaukumu")
        if nosaukums in self.sadalas[sadala]["varianti"]:
            raise ValueError(f"Variants '{nosaukums}' jau ir")
        avots = no if no in self.sadalas[sadala]["varianti"] else self.noklusejums(sadala)
        self.sadalas[sadala]["varianti"][nosaukums] = copy.deepcopy(self.sadalas[sadala]["varianti"][avots])

    def parsaukt(self, sadala: str, vecais: str, jaunais: str) -> None:
        jaunais = jaunais.strip()
        v = self.sadalas[sadala]["varianti"]
        if not jaunais or jaunais == vecais:
            return
        if jaunais in v:
            raise ValueError(f"Variants '{jaunais}' jau ir")
        self.sadalas[sadala]["varianti"] = {(jaunais if k == vecais else k): x for k, x in v.items()}
        if self.sadalas[sadala]["noklusejums"] == vecais:
            self.sadalas[sadala]["noklusejums"] = jaunais

    def dzest(self, sadala: str, nosaukums: str) -> None:
        if nosaukums == self.noklusejums(sadala):
            raise ValueError("Noklusējuma variantu nevar dzēst — vispirms iestati citu par noklusējumu")
        self.sadalas[sadala]["varianti"].pop(nosaukums, None)

    def iestatit_noklusejumu(self, sadala: str, nosaukums: str) -> None:
        if nosaukums in self.sadalas[sadala]["varianti"]:
            self.sadalas[sadala]["noklusejums"] = nosaukums

    def atjaunot_dati(self, sadala: str, nosaukums: str, dati: dict) -> None:
        self.sadalas[sadala]["varianti"][nosaukums] = copy.deepcopy(dati)
