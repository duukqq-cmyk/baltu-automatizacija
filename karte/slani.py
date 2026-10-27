"""Kartes slāņi no LVM GEO brīvpieejas WMS servisiem.

Avots: https://www.lvmgeo.lv/dati/tabmenu-two/brivpieejas-wms-wfs-servisi
(GetCapabilities: Fees = NONE, AccessConstraints = NONE). Slāņi pieejami
EPSG:3857, tāpēc tos var rādīt tieši Leaflet kartē kā WMS flīzes.
Ortofoto un reljefa pamatdati — LĢIA; LiDAR modeļi — LĢIA/LVM GEO apstrāde.
"""
from __future__ import annotations

from dataclasses import dataclass

RASTRS = "https://geoserver.lvmgeo.lv/wms62531a9bfcfa4015856924e94076a178"
VEKTORS = "https://geoserver.lvmgeo.lv/wmsvector62531a9bfcfa4015856924e94076a179"
ATRIBUCIJA = "© LVM GEO, LĢIA, VMD, VZD"


@dataclass(frozen=True)
class Slanis:
    nosaukums: str
    url: str
    wms_slanis: str
    apraksts: str = ""
    formats: str = "image/png"
    caurspidigs: bool = True
    max_zoom: int = 21


# Pamatkartes — vienlaikus redzama viena
PAMATKARTES: dict[str, Slanis] = {s.nosaukums: s for s in [
    Slanis("Ortofoto (jaunākais)", RASTRS, "Orto_LKS",
           "LĢIA ortofoto, katrā vietā jaunākais pieejamais (7./8. cikls)",
           formats="image/jpeg", caurspidigs=False),
    Slanis("Ortofoto infrasarkanais", RASTRS, "OrtoIR_LKS",
           "Krāsu infrasarkanais ortofoto (7./8. cikls) — veģetācija sarkanos toņos, "
           "labi izšķir lapu un skuju kokus", formats="image/jpeg", caurspidigs=False),
    Slanis("Sentinel-2 (pēdējais bezmākoņu)", RASTRS, "S2_RGB_last_cloudless",
           "Satelītattēlu mozaīka — svaigākais skats (piem., nesenas cirtes), 10 m pikselis",
           formats="image/jpeg", caurspidigs=False),
    Slanis("Topogrāfiskā karte 1:10 000", RASTRS, "Topo10DTM",
           "LĢIA topokarte ar reljefa ēnojumu", formats="image/jpeg", caurspidigs=False),
    Slanis("OpenStreetMap", RASTRS, "OSM", "Ceļi, apdzīvotas vietas",
           formats="image/jpeg", caurspidigs=False),
]}

# Pārklājuma slāņi — var ieslēgt vairākus
PARKLAJUMI: dict[str, Slanis] = {s.nosaukums: s for s in [
    Slanis("Veģetācijas augstums", RASTRS, "CanopyHeightLKS",
           "LiDAR veģetācijas augstuma modelis (1./2. cikls): zaļš — zemāka veģetācija, "
           "dzeltens → oranžs → sarkans — augstākas audzes; balts — nav veģetācijas"),
    Slanis("Veģetācijas augstums (izlīdzināts)", RASTRS, "SmoothCanopyHeightLKS",
           "Tas pats modelis, izlīdzināts — labāk redzamas audžu robežas"),
    Slanis("Mežaudžu plāns (VMD nogabali)", VEKTORS, "vmdpubliccompartments",
           "VMD publiskotie nogabali, krāsoti pēc valdošās sugas un vecuma grupas"),
    Slanis("Kadastra karte", VEKTORS, "Kadastra_karte",
           "Zemes vienību robežas un kadastra apzīmējumi"),
    Slanis("Vējgāzes (2026.08.22. vētra)", RASTRS, "Windfalls",
           "LVM GEO aprēķinātās vējgāzu teritorijas pēc 2026. gada 22. augusta vētras"),
    Slanis("Meža ceļi un grāvji (LVM)", VEKTORS, "LVM_Meza_infrastruktura",
           "LVM meža ceļi, grāvji, caurtekas, tilti, apgriešanās laukumi"),
    Slanis("Augsnes", VEKTORS, "soils", "Augsnes laukumi"),
    Slanis("Reljefa horizontāles", RASTRS, "Contours_color_labels",
           "Horizontāles ar augstuma vērtībām"),
]}

NOKLUSETIE_PARKLAJUMI = ["Mežaudžu plāns (VMD nogabali)"]
