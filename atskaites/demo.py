"""Izdomāti demo dati (monday boardu formā), lai sadaļu var izmēģināt bez API tokena.

Satur tipiskās situācijas: īpašums ar vairākām zemes vienībām (vairākas rindas = 1 lead),
viens īpašnieks ar diviem īpašumiem, atjaunots lead (>1 gads), rindas bez kadastra Nr.,
kā arī boardu ar "veco" struktūru (tikai screenshotā redzamās kolonnas).
"""
from __future__ import annotations

import random
from datetime import date, timedelta

from atskaites.modelis import sodiena
from atskaites.monday import Boards, Kolonna, Rinda

GRUPAS = ["Jauns", "Nevar sazvanīt", "Izpētes zvans", "Priekšvērtējums", "Apsekošana",
          "Nopirkts", "Atteikts"]
VARDI = ["Jānis", "Pēteris", "Arturs", "Gatis", "Inese", "Māris", "Ilze", "Andris", "Laura", "Ojārs",
         "Dace", "Valdis", "Rūta", "Edgars", "Zane"]
AVOTI_PRO = ["Aukstais zvans", "Kaimiņu uzrunāšana", "Personīgais mārketings", "Ieteikums"]
AVOTI_PUB = ["ss.com", "Facebook grupa", "Izsoļu portāls", "Mājaslapa"]
PIED = ["Cirsma", "Cirsma/Īpašums", "Īpašums", "Konsultācija"]
IEMESLI = ["Cena par zemu", "Pārdeva konkurentam", "Pārdomāja", "Neatbilst kritērijiem", "Mantojuma strīds"]

PILNAS_KOLONNAS = [
    ("Lead Datums", "date"), ("Aktualiz. dat.", "last_updated"), ("Nākamā darbība", "text"),
    ("Kontaktpersona", "text"), ("Tel.Nr", "phone"), ("Pied. veids", "status"),
    ("Īpašuma kad. Nr.", "text"), ("Zemes vienības kad. apz.", "text"), ("Lead avots", "dropdown"),
    ("Sazvanāms", "checkbox"), ("Meža platība, ha", "numbers"), ("Lauks. zeme, %", "numbers"),
    ("Kailcirte sausie, ha", "numbers"), ("Kailcirte slapjie, ha", "numbers"),
    ("Citu ciršu potenciāls", "checkbox"), ("1. piegājiena apjoms, m³", "numbers"),
    ("Izpētes zvans (datums)", "date"), ("Priekšvērtējums (datums)", "date"),
    ("Tikšanās sarunāta (datums)", "date"), ("Nosūtīts apsekot (datums)", "date"),
    ("Apsekots dabā (datums)", "date"), ("Gala piedāvājums (datums)", "date"),
    ("Maks. gala piedāvājums, EUR", "numbers"), ("Nopirkts (datums)", "date"),
    ("Iegādes summa, EUR", "numbers"), ("Iegādātais apjoms, m³", "numbers"),
    ("Iegādātā platība, ha", "numbers"), ("Atteikts (datums)", "date"), ("Atteikuma iemesls", "dropdown"),
]
VECAS_KOLONNAS = [("Lead Datums", "date"), ("Aktualiz. dat.", "last_updated"), ("Nākamā darbība", "text"),
                  ("Kontaktpersona", "text"), ("Tel.Nr", "phone"), ("Pied. veids", "status")]


def _iso(d: date | None) -> str:
    return d.isoformat() if d else ""


def demo_boardi(sod: date | None = None, seed: int = 42) -> list[Boards]:
    sod = sod or sodiena()
    rnd = random.Random(seed)
    boardi = []
    item_id = 1000
    for b_idx, (nos, kolonnas) in enumerate([("Jaunie_boardi_Arvils", PILNAS_KOLONNAS),
                                             ("Iepirkumi_Janis", PILNAS_KOLONNAS),
                                             ("Iepirkumi_Gatis", VECAS_KOLONNAS)]):
        b = Boards(id=str(9000 + b_idx), nosaukums=nos, workspace="IEPIRKUMS",
                   kolonnas=[Kolonna(f"c{i}", t, tp) for i, (t, tp) in enumerate(kolonnas)],
                   rindas=[], grupas=list(GRUPAS))
        virsraksti = {t for t, _ in kolonnas}
        for n in range(45):
            ipas_kad = f"{rnd.randint(1000, 9999)}{rnd.randint(100, 999)}{rnd.randint(1000, 9999)}"
            tel = f"2{rnd.randint(1000000, 9999999)}"
            lead_d = sod - timedelta(days=rnd.randint(0, 100))
            zv_skaits = rnd.choice([1, 1, 1, 2, 3])
            meza_ha = round(rnd.uniform(2, 40), 1)
            m3 = round(meza_ha * rnd.uniform(40, 120))
            sausie = round(meza_ha * rnd.uniform(0.1, 0.5), 1)
            slapjie = round(meza_ha * rnd.uniform(0, 0.2), 1)

            # posmu progresija
            posms = rnd.choices(range(8), weights=[14, 8, 12, 10, 6, 6, 5, 6])[0]
            d = {}
            dat = lead_d
            sazvanams = posms != 1
            if posms >= 2 and posms != 1:
                dat = dat + timedelta(days=rnd.randint(0, 6)); d["kv"] = dat
            if posms >= 3:
                dat = dat + timedelta(days=rnd.randint(1, 10)); d["pv"] = dat
            if posms >= 4:
                dat = dat + timedelta(days=rnd.randint(1, 7)); d["tk"] = dat
                d["ns"] = dat + timedelta(days=rnd.randint(0, 3))
            if posms >= 5:
                d["ap"] = d["ns"] + timedelta(days=rnd.randint(2, 12))
                d["gp"] = d["ap"] + timedelta(days=rnd.randint(1, 8))
            grupa = {0: "Jauns", 1: "Nevar sazvanīt", 2: "Izpētes zvans", 3: "Priekšvērtējums",
                     4: "Apsekošana", 5: "Apsekošana"}.get(posms)
            if posms == 6:
                grupa = "Nopirkts"
                d["np"] = d["gp"] + timedelta(days=rnd.randint(2, 14))
            if posms == 7:
                grupa = "Atteikts"
                d["at"] = (d.get("gp") or d.get("pv") or lead_d) + timedelta(days=rnd.randint(1, 10))
            max_pied = round(m3 * rnd.uniform(25, 40), -2) if "gp" in d else None
            summa = round(max_pied * rnd.uniform(0.82, 0.98), -2) if "np" in d else None
            proaktivs = rnd.random() < 0.35

            svari = [rnd.uniform(0.5, 1.5) for _ in range(zv_skaits)]
            for zv in range(zv_skaits):
                item_id += 1
                dala = svari[zv] / sum(svari)
                vert = {
                    "Lead Datums": _iso(lead_d),
                    "Kontaktpersona": rnd.choice(VARDI) if zv == 0 else "",
                    "Tel.Nr": tel,
                    "Pied. veids": rnd.choice(PIED) if posms != 1 else "",
                    "Īpašuma kad. Nr.": ipas_kad if (posms >= 2 or rnd.random() < 0.6) else "",
                    "Zemes vienības kad. apz.": f"{ipas_kad[:-3]}{rnd.randint(100, 999)}",
                    "Lead avots": rnd.choice(AVOTI_PRO if proaktivs else AVOTI_PUB),
                    "Sazvanāms": "v" if sazvanams else "",
                    "Meža platība, ha": f"{meza_ha * dala:.1f}",
                    "Lauks. zeme, %": str(rnd.choice([0, 5, 10, 15, 30])),
                    "Kailcirte sausie, ha": f"{sausie * dala:.1f}",
                    "Kailcirte slapjie, ha": f"{slapjie * dala:.1f}",
                    "Citu ciršu potenciāls": "v" if rnd.random() < 0.15 else "",
                    "1. piegājiena apjoms, m³": f"{m3 * dala:.0f}",
                    "Izpētes zvans (datums)": _iso(d.get("kv")),
                    "Priekšvērtējums (datums)": _iso(d.get("pv")),
                    "Tikšanās sarunāta (datums)": _iso(d.get("tk")),
                    "Nosūtīts apsekot (datums)": _iso(d.get("ns")),
                    "Apsekots dabā (datums)": _iso(d.get("ap")),
                    "Gala piedāvājums (datums)": _iso(d.get("gp")),
                    "Maks. gala piedāvājums, EUR": f"{max_pied * dala:.0f}" if max_pied else "",
                    "Nopirkts (datums)": _iso(d.get("np")),
                    "Iegādes summa, EUR": f"{summa * dala:.0f}" if summa else "",
                    "Iegādātais apjoms, m³": f"{m3 * dala:.0f}" if summa else "",
                    "Iegādātā platība, ha": f"{meza_ha * dala:.1f}" if summa else "",
                    "Atteikts (datums)": _iso(d.get("at")),
                    "Atteikuma iemesls": rnd.choice(IEMESLI) if "at" in d else "",
                }
                b.rindas.append(Rinda(b.id, b.nosaukums, str(item_id), f"LEAD - {item_id - 1000}", grupa,
                                      f"{_iso(lead_d)}T09:00:00Z",
                                      {k: v for k, v in vert.items() if k in virsraksti}))
        boardi.append(b)

    # Robežgadījumi Arvila boardā
    b = boardi[0]
    pr = lambda nos, vert, grupa="Jauns": b.rindas.append(  # noqa: E731
        Rinda(b.id, b.nosaukums, str(item_id + len(b.rindas)), nos, grupa, None, vert))
    # viens īpašnieks, divi īpašumi = 2 leadi
    for kad in ("11223344556", "11223344999"):
        pr("Pētera mežs" if kad.endswith("556") else "Pētera otrais īpašums",
           {"Lead Datums": _iso(sod - timedelta(days=3)), "Tel.Nr": "28000000", "Īpašuma kad. Nr.": kad,
            "Pied. veids": "Cirsma", "Lead avots": "Kaimiņu uzrunāšana", "Sazvanāms": "v"})
    # atjaunots lead: tas pats īpašums pirms 2 gadiem un tagad
    for dienas in (730, 2):
        pr("Vecais klients atgriežas", {"Lead Datums": _iso(sod - timedelta(days=dienas)),
                                        "Tel.Nr": "29111111", "Īpašuma kad. Nr.": "66554433221",
                                        "Lead avots": "ss.com"})
    return boardi
