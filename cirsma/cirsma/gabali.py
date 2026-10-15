"""gabali.lv "Nogabalu raksturojošie rādītāji" PDF parsēšana.

Atšķirībā no VMD izdrukas šis PDF ir ģenerēts ar LaTeX:
  * garumzīmes un mīkstinājuma zīmes ir atsevišķas rakstzīmes (¯ ˇ ,), kas
    novietotas virs/zem burta — tās apvienojam pēc koordinātām;
  * tabulai ir skaidras līnijas, tāpēc to nolasām pa šūnām (extract_tables),
    nevis ar regex pa teksta rindām;
  * katram nogabalam ir faktiskā krāja pa sugām, kopējā krāja, aizsargjoslas,
    VMD plānotā darbība, bojājumi u.c. atribūti.
"""
from __future__ import annotations

import re

import pdfplumber

from .parser import Inventarizacija, Nogabals, SugasKraja

# --- Garumzīmju apvienošana ------------------------------------------------

_MAKRONS = {"a": "ā", "e": "ē", "i": "ī", "ı": "ī", "u": "ū", "o": "ō",
            "A": "Ā", "E": "Ē", "I": "Ī", "U": "Ū", "O": "Ō"}
_HACEKS = {"c": "č", "s": "š", "z": "ž", "C": "Č", "S": "Š", "Z": "Ž"}
_CEDILLA = {"n": "ņ", "l": "ļ", "k": "ķ", "g": "ģ", "r": "ŗ",
            "N": "Ņ", "L": "Ļ", "K": "Ķ", "G": "Ģ"}
_AKCENTI = {"¯": _MAKRONS, "ˇ": _HACEKS}


def _atrast_bazi(chars: list[dict], i: int, karte: dict, zem: bool) -> dict | None:
    """Atrod burtu, kuram pieder akcents chars[i] (pēc horizontālās pārklāšanās)."""
    a = chars[i]
    centrs = (a["x0"] + a["x1"]) / 2
    labakais, labaka_att = None, None
    for j in range(max(0, i - 8), min(len(chars), i + 9)):
        if j == i:
            continue
        b = chars[j]
        if b["text"] not in karte:
            continue
        if not (b["x0"] - 0.6 <= centrs <= b["x1"] + 0.6):
            continue
        dy = a["top"] - b["top"]
        if zem:   # mīkstinājuma zīme ir zem burta (lielāks "top")
            if not (1.0 < dy < b["size"] * 0.9):
                continue
        elif abs(dy) > b["size"] * 0.6:  # garumzīme/haceks virs burta
            continue
        att = abs((b["x0"] + b["x1"]) / 2 - centrs)
        if labaka_att is None or att < labaka_att:
            labakais, labaka_att = b, att
    return labakais


def normalizet_lapu(page):
    """Apvieno LaTeX akcentus ar burtiem un atgriež lapu bez atsevišķajiem akcentiem."""
    chars = page.chars
    izmest: set[int] = set()
    for i, c in enumerate(chars):
        t = c["text"]
        if t in _AKCENTI:
            b = _atrast_bazi(chars, i, _AKCENTI[t], zem=False)
            if b is not None:
                b["text"] = _AKCENTI[t][b["text"]]
                izmest.add(id(c))
        elif t == ",":
            # Mīkstinājuma zīme: neliels komats tieši zem burta
            b = _atrast_bazi(chars, i, _CEDILLA, zem=True)
            if b is not None and c["size"] < b["size"] * 0.8:
                b["text"] = _CEDILLA[b["text"]]
                izmest.add(id(c))
    # Atlikušie bezpunkta "ı" (ja garumzīme netika atrasta) -> "i"
    for c in chars:
        if c["text"] == "ı":
            c["text"] = "i"
    return page.filter(lambda o: o.get("object_type") != "char" or id(o) not in izmest)


# --- Formāta atpazīšana ----------------------------------------------------

def ir_gabali_formats(pdf) -> bool:
    """gabali.lv izdruka: LaTeX ģenerēta, galvenē kolonnas "Zemes kategorija" un "Kopējā krāja"."""
    producents = (pdf.metadata or {}).get("Producer", "") or ""
    teksts = normalizet_lapu(pdf.pages[0]).extract_text() or ""
    vienots = re.sub(r"\s+", "", teksts)
    return "Kopējā" in vienots and "kategorija" in vienots and (
        "pdfTeX" in producents or "RAKSTUROJOŠIE" in vienots
    )


# --- Šūnu parsēšana --------------------------------------------------------

_TABULAS_IESTATIJUMI = {"text_x_tolerance": 1.5, "text_y_tolerance": 2}
_SUGAS_VERTIBA_RE = re.compile(r"^([A-ZĀČĒĢĪĶĻŅŠŪŽ][a-zāčēģīķļņšūž]?)\s*(\d+(?:[.,]\d+)?)$")
_ZV_RE = re.compile(r"Zemes\s*vienība\s*(\d{11})")


def _sk(vertiba: str | None) -> float | None:
    if vertiba is None:
        return None
    v = vertiba.strip().replace(",", ".")
    if not v or v == "-":
        return None
    try:
        return float(v)
    except ValueError:
        return None


def _vesels(vertiba: str | None) -> int | None:
    f = _sk(vertiba)
    return int(f) if f is not None else None


def _vienrinda(s: str | None) -> str:
    return re.sub(r"\s+", " ", (s or "").replace("\n", " ")).strip()


def _sugu_saraksts(teksts: str | None) -> list[tuple[str, float]]:
    rez = []
    for rinda in (teksts or "").splitlines():
        m = _SUGAS_VERTIBA_RE.match(rinda.strip())
        if m:
            rez.append((m.group(1), float(m.group(2).replace(",", "."))))
    return rez


def _pievienot_sugas(n: Nogabals, rinda: list) -> None:
    """Sugu tabula: G (m²/ha) | krāja m³/ha | kopā m³. Jaunaudzēm G nav."""
    g = _sugu_saraksts(rinda[11])
    m3ha = _sugu_saraksts(rinda[13])
    m3 = _sugu_saraksts(rinda[14])
    for k, (suga, kraja_ha) in enumerate(m3ha):
        kopa = m3[k][1] if k < len(m3) and m3[k][0] == suga else None
        g_val = g[k][1] if k < len(g) and g[k][0] == suga else None
        n.sugu_kraja.append(SugasKraja(suga=suga, skerslaukums=g_val,
                                       kraja_m3_ha=kraja_ha, kraja_m3=kopa))


def _apstradat_aprakstu(n: Nogabals, teksts: str | None) -> None:
    """Apraksta šūna: atslēga: vērtība rindas; garās vērtības turpinās nākamajā rindā."""
    ieraksti: list[list[str]] = []
    for rinda in (teksts or "").splitlines():
        r = rinda.strip()
        if not r or r == ",":
            continue
        m = re.match(r"^([A-ZĀČĒĢĪĶĻŅŠŪŽ0-9][^:]{0,60}?):\s*(.*)$", r)
        if m or r.startswith(("Plantācijas", "Sugas <5", "Sugas<5")):
            ieraksti.append([r])
        elif ieraksti:
            ieraksti[-1].append(r)
        else:
            ieraksti.append([r])

    for daļas in ieraksti:
        pilns = re.sub(r"\s+([,.])", r"\1", " ".join(daļas))
        n.piezimes.append(pilns)
        atsl, _, vert = pilns.partition(":")
        atsl_v = re.sub(r"\s+", "", atsl).lower()
        vert = vert.strip()
        if atsl_v.startswith("plantācijas"):
            n.plantacija = True
        elif atsl_v == "plānots":
            n.planots = vert
        elif atsl_v.startswith("aizs.paz"):
            n.aizsargjoslas.append(vert)
        elif atsl_v.startswith("pēdējāscirtes"):
            n.pedeja_cirte = vert
        elif atsl_v.startswith("pēdējaisdarbības"):
            n.pedeja_darbiba = vert
        elif atsl_v.startswith("2.stāvs"):
            n.otrais_stavs = vert
        elif atsl_v.startswith("bojājums"):
            n.bojajumi.extend(x.strip(" '’‘\"") for x in re.split(r"['’‘\"],\s*['’‘\"]", vert.strip("[]")))
        elif atsl_v.startswith("komentāri"):
            n.komentari = vert


def _kolonnu_robezas(tabula) -> list[tuple[float, float]] | None:
    """Kolonnu x robežas no pirmās rindas, kurai ir visas 15 šūnas."""
    for r in tabula.rows:
        if len(r.cells) >= 15 and all(c is not None for c in r.cells):
            return [(c[0], c[2]) for c in r.cells]
    return None


def _lapas_rindas(lapa) -> list[list[list[str | None]]]:
    """Tabulas rindas no lapas + rinda zem tabulas, kurai trūkst vertikālo līniju.

    Lapas beigās nogabala apraksta/sugu rinda reizēm nav noslēgta ar vertikālām
    līnijām, un pdfplumber to neiekļauj tabulā. Šo atlikumu nolasām pēc tās pašas
    tabulas kolonnu robežām, lai sugu dati nepazustu.
    """
    rez = []
    for t in lapa.find_tables(_TABULAS_IESTATIJUMI):
        rindas = t.extract(x_tolerance=1.5, y_tolerance=2)
        robezas = _kolonnu_robezas(t)
        apaksa = t.bbox[3]
        if robezas:
            zona = lapa.crop((t.bbox[0], apaksa + 0.5, t.bbox[2], lapa.height))
            if (zona.extract_text() or "").strip():
                rinda = []
                for x0, x1 in robezas:
                    sunas = zona.crop((max(x0, zona.bbox[0]), zona.bbox[1], min(x1, zona.bbox[2]), zona.bbox[3]))
                    rinda.append(sunas.extract_text(x_tolerance=1.5) or "")
                # Apraksta šūna aizņem kolonnas 4..10 (apvienotas)
                rinda[4] = lapa.crop((robezas[4][0], apaksa + 0.5, robezas[10][1], lapa.height)) \
                    .extract_text(x_tolerance=1.5) or ""
                rinda[0] = lapa.crop((robezas[0][0], apaksa + 0.5, robezas[3][1], lapa.height)) \
                    .extract_text(x_tolerance=1.5) or ""
                rindas.append(rinda)
        rez.append(rindas)
    return rez


def parse_gabali_pdf(pdf_path: str) -> Inventarizacija:
    """Nolasa gabali.lv nogabalu PDF un atgriež strukturētus nogabalu datus."""
    nogabali: list[Nogabals] = []
    pedejais: Nogabals | None = None
    kvartals: str | None = None
    zemes_vieniba: str | None = None
    ipasums: str | None = None

    with pdfplumber.open(pdf_path) as pdf:
        for lpp in pdf.pages:
            lapa = normalizet_lapu(lpp)
            if ipasums is None:
                m = re.search(r"īpašumam\s*(.+?),\s*(\d{11})", lapa.extract_text() or "")
                if m:
                    ipasums = m.group(1).strip()
            for tabula in _lapas_rindas(lapa):
                for rinda in tabula:
                    if len(rinda) < 15:
                        continue
                    sv = [c if c is not None else None for c in rinda]
                    pirma = _vienrinda(sv[0])
                    if pirma.startswith(("Nogabals", "Nr.")):
                        continue  # atkārtota galvene
                    if re.search(r"kopējā\s*platība|^Kopā|^Pavisam", pirma, re.IGNORECASE):
                        continue  # kvartāla / īpašuma kopsavilkuma rinda

                    if "kvartāls" in pirma:
                        mk = re.match(r"(\d+)", pirma)
                        kvartals = mk.group(1) if mk else None
                        mz = _ZV_RE.search(_vienrinda(sv[4]))
                        if mz and zemes_vieniba is None:
                            zemes_vieniba = mz.group(1)
                        continue

                    if re.fullmatch(r"\d{1,3}", pirma):
                        kategorija = _vienrinda(sv[2])
                        pedejais = Nogabals(
                            nr=int(pirma),
                            platiba_ha=_sk(sv[1]) or 0.0,
                            zemes_veids=kategorija,
                            kvartals=kvartals,
                            avots="gabali.lv",
                        )
                        if kategorija == "Mežaudze":
                            pedejais.meza_tips = _vienrinda(sv[3])
                            pedejais.formula = _vienrinda(sv[4]) or None
                            pedejais.izcelsanas = _vienrinda(sv[5])
                            pedejais.bonitate = _vienrinda(sv[6]) or None
                            pedejais.vid_augstums = _vesels(sv[7])
                            pedejais.vid_caurmers = _vesels(sv[8])
                            pedejais.vecums = _vesels(sv[9])
                            pedejais.bieziba = _sk(sv[10])
                            pedejais.skerslaukums = _sk(sv[11])
                            pedejais.koku_skaits = _vesels(sv[12])
                            pedejais.kraja_m3_ha = _sk(sv[13])
                            pedejais.kopeja_kraja_m3 = _sk(sv[14])
                        nogabali.append(pedejais)
                        continue

                    # Apraksta / sugu rinda (var turpināties nākamajā lapā)
                    if pedejais is not None:
                        if pirma.startswith("Nogabala") and not pedejais.inventarizacija:
                            pedejais.inventarizacija = re.sub(r"\s+([,.])", r"\1", pirma)
                        _apstradat_aprakstu(pedejais, sv[4])
                        _pievienot_sugas(pedejais, sv)

    if not nogabali:
        raise ValueError(
            f"No {pdf_path} neizdevās nolasīt nevienu nogabalu (gabali.lv formāts) — "
            "iespējams, mainījies izkārtojums."
        )
    return Inventarizacija(zemes_vieniba=zemes_vieniba, ipasums=ipasums,
                           nogabali=nogabali, avots="gabali.lv")
