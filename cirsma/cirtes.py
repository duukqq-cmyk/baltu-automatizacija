"""Ciršu veidi un to normatīvi: kailcirtes platības pēc meža tipa, kopšanas un
izlases cirtes apjoms pēc šķērslaukuma.

Tīra loģika (bez Streamlit), visas konstantes vienuviet — tās var mainīt
iestatījumos (`Noteikumi`).

Kailcirte
    Sausieņos max 5 ha, pārējos meža tipos (slapjaiņi, purvaiņi, āreņi, kūdreņi)
    max 2 ha. Lielāku nogabalu sadala: kailcirte (max) + atdalošā josla (0,5 ha)
    + nākamā kailcirte, ja tai paliek vismaz 0,5 ha. Atdalošā josla netiek cirsta.

Kopšanas cirte  (automātiski, ja kailcirte nav atļauta)
    izcērtamais G = G − (Gmin + 1); jābūt ≥ 4 m²/ha (citādi neatmaksājas).
    apjoms = izcērtamais G × veidaugstums × platība.

Izlases cirte  (tikai manuāli izvēlēta)
    tāpat, bet ar kritisko šķērslaukumu: G − (Gkrit + 1).
"""
from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Cirtes veidi
# ---------------------------------------------------------------------------

KAILCIRTE = "kailcirte"
KOPSANA = "kopsana"
IZLASES = "izlases"
NECIRST = "nav"

CIRTES_NOSAUKUMI = {
    KAILCIRTE: "Kailcirte",
    KOPSANA: "Kopšanas cirte",
    IZLASES: "Izlases cirte",
    NECIRST: "Necirst",
}
NOSAUKUMS_UZ_VEIDU = {v: k for k, v in CIRTES_NOSAUKUMI.items()}


@dataclass
class Noteikumi:
    """Konfigurējamie sliekšņi (noklusējumi atbilst darba uzdevumam)."""
    max_sausieni_ha: float = 5.0
    max_citi_ha: float = 2.0
    atdalosa_josla_ha: float = 0.5
    min_kailcirte_ha: float = 0.5     # nākamā kailcirte tikai, ja tai paliek vismaz tik
    g_rezerve: float = 1.0            # plāno ar Gmin + 1 / Gkrit + 1
    min_izcertamais_g: float = 4.0    # m²/ha — mazāk neatmaksājas
    min_g_izlases: bool = True        # vai 4 m²/ha slieksnis attiecas arī uz izlases cirti


NOKLUSEJUMA_NOTEIKUMI = Noteikumi()

# ---------------------------------------------------------------------------
# Meža tipi
# ---------------------------------------------------------------------------

SAUSIENI, SLAPJAINI, PURVAINI, ARENI, KUDRENI = "sausieņi", "slapjaiņi", "purvaiņi", "āreņi", "kūdreņi"

MEZA_TIPU_GRUPAS: dict[str, tuple[str, str]] = {
    # saīsinājums: (nosaukums, grupa)
    "Sl": ("Sils", SAUSIENI), "Mr": ("Mētrājs", SAUSIENI), "Ln": ("Lāns", SAUSIENI),
    "Dm": ("Damaksnis", SAUSIENI), "Vr": ("Vēris", SAUSIENI), "Gr": ("Gārša", SAUSIENI),
    "Gs": ("Grīnis", SLAPJAINI), "Mrs": ("Slapjais mētrājs", SLAPJAINI),
    "Dms": ("Slapjais damaksnis", SLAPJAINI), "Vrs": ("Slapjais vēris", SLAPJAINI),
    "Grs": ("Slapjā gārša", SLAPJAINI),
    "Pv": ("Purvājs", PURVAINI), "Nd": ("Niedrājs", PURVAINI), "Db": ("Dumbrājs", PURVAINI),
    "Lk": ("Liekņa", PURVAINI),
    "Av": ("Viršu ārenis", ARENI), "Am": ("Mētru ārenis", ARENI), "As": ("Šaurlapju ārenis", ARENI),
    "Ap": ("Platlapju ārenis", ARENI),
    "Kv": ("Viršu kūdrenis", KUDRENI), "Km": ("Mētru kūdrenis", KUDRENI),
    "Ks": ("Šaurlapju kūdrenis", KUDRENI), "Kp": ("Platlapju kūdrenis", KUDRENI),
}
_NOSAUKUMS_UZ_GRUPU = {nos.lower(): gr for nos, gr in MEZA_TIPU_GRUPAS.values()}
_KODS_UZ_GRUPU = {k.lower(): gr for k, (_, gr) in MEZA_TIPU_GRUPAS.items()}


def meza_tipa_grupa(tips: str | None) -> str | None:
    """'Dms' / 'Slapjais damaksnis' -> 'slapjaiņi'. Nezināms -> None."""
    if not tips:
        return None
    t = " ".join(tips.split()).strip().lower()
    return _KODS_UZ_GRUPU.get(t) or _NOSAUKUMS_UZ_GRUPU.get(t)


def max_kailcirtes_platiba(tips: str | None, nt: Noteikumi = NOKLUSEJUMA_NOTEIKUMI) -> tuple[float, str]:
    """(max ha, paskaidrojums). Nezināms meža tips -> konservatīvi mazākais limits."""
    grupa = meza_tipa_grupa(tips)
    if grupa == SAUSIENI:
        return nt.max_sausieni_ha, f"{tips} ({grupa})"
    if grupa is None:
        return nt.max_citi_ha, f"meža tips '{tips or '—'}' nav atpazīts — pieņemts stingrākais limits"
    return nt.max_citi_ha, f"{tips} ({grupa})"


def sadalit_kailcirtes(platiba: float, max_ha: float,
                       nt: Noteikumi = NOKLUSEJUMA_NOTEIKUMI) -> tuple[list[float], float]:
    """Sadala nogabalu kailcirtēs, kas nesaskaras.

    Atgriež (kailciršu platības, atdalošo joslu kopplatība). Pēdējā pāri palikusī
    daļa, kas mazāka par min_kailcirte_ha, netiek cirsta (pievienojas joslai).
      3,2 ha, max 2 -> [2.0, 0.7], josla 0.5
      2,8 ha, max 2 -> [2.0], neizmantots 0.8
      6,0 ha, max 5 -> [5.0, 0.5], josla 0.5
    """
    platiba = round(max(platiba or 0.0, 0.0), 4)
    if platiba <= max_ha + 1e-9:
        return [round(platiba, 2)], 0.0
    cirtes: list[float] = []
    joslas = 0.0
    atlikums = platiba
    while atlikums > 1e-9:
        if not cirtes:
            dala = min(max_ha, atlikums)
        else:
            # pirms nākamās kailcirtes vajag atdalošo joslu un vismaz min platību
            if atlikums < nt.atdalosa_josla_ha + nt.min_kailcirte_ha - 1e-9:
                break
            joslas += nt.atdalosa_josla_ha
            atlikums -= nt.atdalosa_josla_ha
            dala = min(max_ha, atlikums)
        cirtes.append(round(dala, 2))
        atlikums = round(atlikums - dala, 4)
    return cirtes, round(joslas, 2)


# ---------------------------------------------------------------------------
# Šķērslaukums: Gmin / Gkrit pēc valdošās sugas un vidējā augstuma
# ---------------------------------------------------------------------------

# Sugu grupas tabulā "Mežaudzes pirmajā stāvā augošo koku minimālais un kritiskais
# šķērslaukums"
G_PRIEDE, G_SKUJU, G_BERZS, G_MIKSTIE, G_CIETIE, G_OSIS = (
    "priede", "egle un citi skuju koki", "bērzs, liepa",
    "apse, melnalksnis, baltalksnis, citi lapu koki",
    "ozols, vīksna, goba, kļava, dižskābardis, skābardis", "osis",
)
_G_KOLONNAS = [G_PRIEDE, G_SKUJU, G_BERZS, G_MIKSTIE, G_CIETIE, G_OSIS]

# augstums m: (Gmin, Gkrit) katrai kolonnai; None = nav noteikts
_G_TABULA_RINDAS: dict[int, list[tuple[int, int] | None]] = {
    12: [(10, 7), (11, 6), (8, 4), (10, 5), (9, 5), (7, 4)],
    13: [(11, 8), (12, 6), (9, 5), (10, 6), (10, 5), (8, 4)],
    14: [(12, 8), (12, 7), (10, 5), (11, 6), (10, 6), (8, 5)],
    15: [(12, 8), (14, 7), (10, 5), (11, 6), (11, 6), (9, 5)],
    16: [(13, 8), (15, 7), (11, 6), (12, 6), (12, 6), (10, 5)],
    17: [(14, 8), (16, 8), (11, 6), (12, 7), (12, 6), (10, 6)],
    18: [(14, 8), (17, 8), (12, 6), (13, 7), (14, 7), (11, 6)],
    19: [(15, 8), (18, 8), (12, 6), (13, 7), (15, 7), (13, 6)],
    20: [(16, 9), (18, 8), (13, 6), (14, 8), (16, 7), (13, 6)],
    21: [(17, 9), (19, 8), (14, 7), (15, 8), (17, 7), (14, 6)],
    22: [(18, 9), (20, 9), (14, 7), (16, 8), (17, 8), (14, 6)],
    23: [(19, 9), (20, 9), (16, 7), (16, 8), (18, 8), (14, 6)],
    24: [(21, 9), (21, 9), (16, 7), (18, 9), (18, 8), (14, 7)],
    25: [(22, 9), (22, 10), (17, 8), (19, 9), (19, 8), (15, 7)],
    26: [(22, 9), (22, 10), (17, 8), (19, 9), (20, 8), (15, 7)],
    27: [(22, 9), (23, 10), (17, 8), (20, 10), (20, 9), (15, 7)],
    28: [(22, 9), (23, 10), (18, 8), (21, 10), (21, 9), (16, 7)],
    29: [(22, 9), (24, 10), (18, 8), (22, 10), (21, 9), (16, 7)],
    30: [(22, 9), (25, 10), (19, 8), (22, 10), (22, 9), (16, 7)],
    31: [(23, 9), (25, 11), (19, 8), (23, 10), (22, 9), None],
    32: [(23, 9), (26, 11), (20, 9), (23, 10), (22, 9), None],
    33: [(23, 10), (26, 11), (20, 9), (24, 11), (23, 10), None],
    34: [(23, 10), (26, 11), (21, 9), (24, 11), (23, 10), None],
    35: [(23, 10), (26, 11), (21, 9), (24, 11), (23, 10), None],  # 35 un vairāk
}
G_MIN_AUGSTUMS, G_MAX_AUGSTUMS = 12, 35

_G_SUGU_GRUPA = {
    "P": G_PRIEDE,
    "E": G_SKUJU, "Le": G_SKUJU, "Pc": G_SKUJU, "Ci": G_SKUJU,
    "B": G_BERZS, "L": G_BERZS,
    "A": G_MIKSTIE, "M": G_MIKSTIE, "Ma": G_MIKSTIE, "Ba": G_MIKSTIE,
    "Oz": G_CIETIE, "V": G_CIETIE, "Vī": G_CIETIE, "Vi": G_CIETIE, "Go": G_CIETIE,
    "K": G_CIETIE, "Kļ": G_CIETIE, "Ds": G_CIETIE, "Sk": G_CIETIE,
    "Os": G_OSIS,
}


def g_grupa(suga: str) -> str:
    return _G_SUGU_GRUPA.get(suga, G_MIKSTIE)  # citi lapu koki


def g_normativi(suga: str, augstums: float | None) -> tuple[int, int] | None:
    """(Gmin, Gkrit) valdošajai sugai un vid. augstumam; None — nav noteikts."""
    if augstums is None or augstums < G_MIN_AUGSTUMS:
        return None
    h = min(int(round(augstums)), G_MAX_AUGSTUMS)
    return _G_TABULA_RINDAS[h][_G_KOLONNAS.index(g_grupa(suga))]


# ---------------------------------------------------------------------------
# Veidaugstums (m) pēc sugas un augstuma
# ---------------------------------------------------------------------------

_VH_KOLONNAS = ["priede", "egle", "ozols", "osis", "bērzs", "melnalksnis", "liepa", "apse", "baltalksnis"]
_VH_TABULA: dict[int, list[float]] = {
    9:  [5.26, 5.62, 4.63, 5.25, 4.75, 4.95, 4.9, 4.9, 5.09],
    10: [5.71, 6.09, 5.04, 5.7, 5.14, 5.36, 5.32, 5.29, 5.41],
    11: [6.14, 6.55, 5.45, 6.13, 5.53, 5.78, 5.74, 5.71, 5.74],
    12: [6.54, 7.05, 5.87, 6.55, 5.92, 6.2, 6.18, 6.15, 6.15],
    13: [6.96, 7.39, 6.28, 6.97, 6.31, 6.62, 6.62, 6.59, 6.52],
    14: [7.34, 7.87, 6.69, 7.39, 6.7, 7.05, 7.06, 7.03, 6.92],
    15: [7.69, 8.27, 7.1, 7.8, 7.1, 7.48, 7.5, 7.48, 7.29],
    16: [8.07, 8.75, 7.52, 8.2, 7.49, 7.9, 7.95, 7.91, 7.61],
    17: [8.44, 9.12, 7.93, 8.6, 7.88, 8.34, 8.39, 8.35, 7.97],
    18: [8.81, 9.49, 8.35, 9.0, 8.28, 8.74, 8.83, 8.8, 8.37],
    19: [9.14, 9.85, 8.78, 9.4, 8.68, 9.15, 9.28, 9.24, 8.73],
    20: [9.5, 10.2, 9.2, 9.79, 9.09, 9.6, 9.72, 9.69, 8.98],
    21: [9.85, 10.54, 9.62, 10.19, 9.49, 10.05, 10.17, 10.14, 9.38],
    22: [10.25, 10.76, 10.06, 10.58, 9.9, 10.51, 10.61, 10.59, 9.74],
    23: [10.61, 10.95, 10.49, 10.96, 10.32, 10.96, 11.06, 11.04, 10.14],
    24: [11.0, 11.39, 10.92, 11.35, 10.73, 11.42, 11.51, 11.5, 10.49],
    25: [11.4, 11.83, 11.37, 11.74, 11.16, 11.9, 11.96, 11.95, 10.89],
    26: [11.8, 12.14, 11.81, 12.12, 11.58, 12.36, 12.36, 12.41, 11.26],
    27: [12.15, 12.57, 12.26, 12.5, 12.01, 12.84, 12.86, 12.86, 11.65],
    28: [12.55, 13.01, 12.72, 12.89, 12.44, 13.32, 13.31, 13.32, 12.0],
    29: [12.9, 13.45, 13.18, 13.27, 12.88, 13.8, 13.77, 13.78, 12.35],
    30: [13.28, 13.8, 13.63, 13.65, 13.3, 14.27, 14.22, 14.24, 12.72],
    31: [13.66, 14.15, 14.07, 14.03, 13.72, 14.74, 14.67, 14.69, 13.1],
    32: [14.04, 14.49, 14.52, 14.41, 14.15, 15.21, 15.12, 15.15, 13.48],
}
VH_MIN, VH_MAX = 9, 32  # TODO: tabulas turpinājums virs 32 m (pagaidām izmanto 32 m vērtību)

_VH_SUGA = {
    "P": "priede",
    "E": "egle", "Le": "egle", "Pc": "egle", "Ci": "egle",
    "Oz": "ozols", "V": "ozols", "Vī": "ozols", "Vi": "ozols", "Go": "ozols",
    "K": "ozols", "Kļ": "ozols", "Ds": "ozols", "Sk": "ozols",
    "Os": "osis", "B": "bērzs", "M": "melnalksnis", "Ma": "melnalksnis",
    "L": "liepa", "A": "apse", "Ba": "baltalksnis",
}


def veidaugstums(suga: str, augstums: float | None) -> tuple[float, str] | None:
    """(veidaugstums m, piezīme). Sugas bez savas kolonnas -> baltalksnis (mīkstie lapu koki)."""
    if augstums is None:
        return None
    kol = _VH_SUGA.get(suga, "baltalksnis")
    h = int(round(augstums))
    piez = ""
    if h > VH_MAX:
        piez = f"augstums {h} m ārpus veidaugstuma tabulas — izmantota {VH_MAX} m vērtība"
        h = VH_MAX
    if h < VH_MIN:
        return None
    if suga not in _VH_SUGA:
        piez = (piez + "; " if piez else "") + f"sugai {suga} izmantots baltalkšņa veidaugstums"
    return _VH_TABULA[h][_VH_KOLONNAS.index(kol)], piez


# ---------------------------------------------------------------------------
# Kopšanas / izlases cirtes apjoms
# ---------------------------------------------------------------------------

@dataclass
class SkerslaukumaCirte:
    veids: str                 # KOPSANA / IZLASES
    g: float                   # nogabala šķērslaukums m²/ha
    g_norma: int               # Gmin (kopšana) vai Gkrit (izlases)
    izcertamais_g: float       # m²/ha
    veidaugstums: float
    platiba: float
    apjoms_m3: float
    atbilst: bool              # vai sasniegts min izcērtamais G
    piezimes: list[str]

    @property
    def formula_teksts(self) -> str:
        return (f"({self.g:g} − ({self.g_norma}+1)) × {self.veidaugstums:g} × {self.platiba:g} ha "
                f"= {self.apjoms_m3:.2f} m³")


def skerslaukuma_cirte(veids: str, suga: str, augstums: float | None, g: float | None,
                       platiba: float, nt: Noteikumi = NOKLUSEJUMA_NOTEIKUMI
                       ) -> SkerslaukumaCirte | str:
    """Aprēķina kopšanas/izlases cirtes apjomu. Ja nevar aprēķināt — atgriež iemeslu (str)."""
    if g is None:
        return "nav šķērslaukuma datu"
    if augstums is None:
        return "nav vidējā augstuma"
    normas = g_normativi(suga, augstums)
    if normas is None:
        if augstums < G_MIN_AUGSTUMS:
            return f"vid. augstums {augstums:g} m < {G_MIN_AUGSTUMS} m (šķērslaukuma normatīvs nav noteikts)"
        return f"sugai {suga} šajā augstumā šķērslaukuma normatīvs nav noteikts"
    vh = veidaugstums(suga, augstums)
    if vh is None:
        return f"nav veidaugstuma sugai {suga} pie {augstums:g} m"
    g_norma = normas[0] if veids == KOPSANA else normas[1]
    izc_g = round(g - (g_norma + nt.g_rezerve), 2)
    piez = [vh[1]] if vh[1] else []
    slieksnis = veids == KOPSANA or nt.min_g_izlases
    atbilst = izc_g >= nt.min_izcertamais_g if slieksnis else izc_g > 0
    apjoms = round(max(izc_g, 0) * vh[0] * platiba, 2)
    return SkerslaukumaCirte(veids, g, g_norma, izc_g, vh[0], platiba, apjoms, atbilst, piez)


# ---------------------------------------------------------------------------
# Blakus esošās kailcirtes (pēc nogabalu robežām)
# ---------------------------------------------------------------------------

def blakus_grupas(geometrijas: dict[str, object], tolerance_m: float = 1.0) -> list[list[str]]:
    """Sagrupē nogabalus, kuru robežas saskaras (shapely ģeometrijas metriskā CRS).

    Atgriež tikai grupas ar ≥ 2 nogabaliem.
    """
    apz = list(geometrijas)
    blakus = {a: set() for a in apz}
    for i, a in enumerate(apz):
        ga = geometrijas[a]
        for b in apz[i + 1:]:
            if ga.distance(geometrijas[b]) <= tolerance_m:
                blakus[a].add(b)
                blakus[b].add(a)
    redzeti, grupas = set(), []
    for a in apz:
        if a in redzeti:
            continue
        steks, grupa = [a], []
        while steks:
            x = steks.pop()
            if x in redzeti:
                continue
            redzeti.add(x)
            grupa.append(x)
            steks.extend(blakus[x] - redzeti)
        if len(grupa) > 1:
            grupas.append(sorted(grupa))
    return grupas
