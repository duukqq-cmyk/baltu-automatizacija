"""Modulis: ĢIS karte — cirsmu atzīmēšana, mērījumi un pārrēķins (beta)."""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import tempfile

import folium
import pandas as pd
import streamlit as st
from branca.element import MacroElement, Template
from folium import plugins
from streamlit_folium import st_folium

from cirsma.formula import SUGU_NOSAUKUMI, valdosa_suga
from cirsma.labojumi import novertet_ar_labojumiem
from cirsma.parser import parse_inventory_pdf
from cirsma.report import excel_atskaite
from cirsma.rules import novertet_nogabalu
from karte.geometrija import (
    STATUSI, apvienot_ar_zimejumiem, ir_laukums, jauns_objekts, kopplatiba_ha, lks_uz_wgs, mervienibas,
    nolasit_failu, objekta_krasa, parklasanas, robezas, uz_geojson, uz_kml,
)
from karte.kadastrs import ATRIBUCIJA as VZD_ATRIBUCIJA, KadastrsKluda, apzimejumi, atrast
from karte.mvr import MvrKluda, lejupieladet_teritoriju, nogabali_no_faila
from karte.mvr import robezas as mvr_robezas, uz_inventarizaciju
from karte.parrekins import (
    CIRSMAS_STATUSS, labojumi_no_kartes, nogabalu_saraksts, objekta_sadalijums, salidzinat,
    uzmeritas_platibas,
)
from karte.slani import ATRIBUCIJA, NOKLUSETIE_PARKLAJUMI, PAMATKARTES, PARKLAJUMI

LATVIJA = {"center": [56.95, 24.6], "zoom": 8}

ss = st.session_state
ss.setdefault("karte_objekti", [])
ss.setdefault("karte_skats", None)
ss.setdefault("karte_pietuvinat", False)
ss.setdefault("karte_versija", 0)
ss.setdefault("karte_pedejie_zim", None)
ss.setdefault("karte_importeti", set())
ss.setdefault("karte_zv", [])            # atrastās zemes vienības (VZD)
ss.setdefault("karte_zv_zina", None)
ss.setdefault("karte_fokuss", None)
ss.setdefault("karte_parklajumi", list(NOKLUSETIE_PARKLAJUMI))
if ss.pop("karte_ieslegt_nogabalus", False):
    ss.karte_parklajumi = list(dict.fromkeys(list(ss.karte_parklajumi) + ["Mežaudžu plāns (VMD nogabali)"]))


# Karte tiek pārzīmēta (HTML mainās) tikai pilnā lapas pārlādē. Pārvietojot karti, fragments
# saglabā skatu `karte_skats`, bet HTML izmanto `karte_skats_html`, lai karte nepārlādētos.
ss.karte_skats_html = ss.karte_skats
ss.karte_pietuvinat_html = ss.karte_pietuvinat


def _mainits(pietuvinat: bool = False) -> None:
    ss.karte_versija += 1
    if pietuvinat:
        ss.karte_pietuvinat = ss.karte_pietuvinat_html = True


def _meklet_kadastru(kodi: list[str] | None = None) -> None:
    """Atrod zemes vienības VZD servisā, parāda kartē un ieslēdz nogabalu slāni."""
    kodi = kodi if kodi is not None else apzimejumi(ss.get("karte_kad_ievade", ""))
    if not kodi:
        ss.karte_zv_zina = ("error", "Ievadi 11 ciparu kadastra apzīmējumu, piem., 80640010066.")
        return
    try:
        atrasti = atrast(kodi)
    except KadastrsKluda as e:
        ss.karte_zv_zina = ("error", str(e))
        return
    esosie = {z["kadastrs"] for z in ss.karte_zv}
    ss.karte_zv = ss.karte_zv + [z for z in atrasti if z["kadastrs"] not in esosie]
    neatrasti = [k for k in kodi if k not in {z["kadastrs"] for z in atrasti}]
    ss.karte_zv_zina = (("warning", "Nav atrasta zemes vienība: " + ", ".join(neatrasti)
                         + ". Ja tas ir īpašuma numurs, kadastrs.lv apskaties tā zemes vienību apzīmējumus.")
                        if neatrasti else None)
    if atrasti:
        ss.karte_ieslegt_nogabalus = True      # slāni ieslēdz nākamajā pārlādē (pirms logrīka)
        ss.karte_fokuss = [z["kadastrs"] for z in atrasti]
        _mainits(pietuvinat=True)


def _nonemt_zv(kadastrs: str) -> None:
    ss.karte_zv = [z for z in ss.karte_zv if z["kadastrs"] != kadastrs]
    _mainits()


def _zv_ka_objekts(kadastrs: str) -> None:
    z = next(z for z in ss.karte_zv if z["kadastrs"] == kadastrs)
    g = z["geometry"]
    poligoni = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
    for i, c in enumerate(poligoni):
        nos = f"ZV {kadastrs}" + (f" ({i + 1})" if len(poligoni) > 1 else "")
        geom = {"type": "Polygon", "coordinates": [[[round(x, 6), round(y, 6)] for x, y, *_ in r] for r in c]}
        ss.karte_objekti = ss.karte_objekti + [jauns_objekts(geom, nos, statuss="Cits")]
    _mainits()


# --- Sānjosla: kadastrs -----------------------------------------------------
st.sidebar.header("Meklēt pēc kadastra")
st.sidebar.text_input("Zemes vienības kadastra apzīmējums", key="karte_kad_ievade",
                      placeholder="piem., 80640010066",
                      help="11 cipari (atstarpes nav svarīgas). Vairākus atdali ar komatu. "
                           "Dati: VZD Kadastrālie zemes gabali (INSPIRE), atjauno reizi nedēļā.")
st.sidebar.button("🔎 Atrast kartē", on_click=_meklet_kadastru, use_container_width=True, type="primary")
if ss.karte_zv_zina:
    getattr(st.sidebar, ss.karte_zv_zina[0])(ss.karte_zv_zina[1])
for z in ss.karte_zv:
    with st.sidebar.container(border=True):
        st.markdown(f"📍 **[{z['kadastrs']}]({z['saite']})** · {z['platiba_ha'] or 0:.2f} ha",
                    help=f"Kadastrā reģistrētā platība {z['platiba_ha'] or 0:.2f} ha; pēc robežām "
                         f"(LKS-92) {z['platiba_graf_ha']:.2f} ha. Saite atver kadastrs.lv.")
        b, c = st.columns(2)
        b.button("Kā objekts", key=f"zv_obj_{z['kadastrs']}", on_click=_zv_ka_objekts,
                 args=(z["kadastrs"],), use_container_width=True,
                 help="Pievienot zemes vienības robežu kā objektu (mērījumiem, eksportam)")
        c.button("Noņemt", key=f"zv_del_{z['kadastrs']}", on_click=_nonemt_zv, args=(z["kadastrs"],),
                 use_container_width=True)

# --- Sānjosla: slāņi --------------------------------------------------------
st.sidebar.divider()
st.sidebar.header("Kartes slāņi")
pamatkarte = st.sidebar.radio("Pamatkarte", list(PAMATKARTES), key="karte_pamats",
                              help="\n\n".join(f"**{k}** — {s.apraksts}" for k, s in PAMATKARTES.items()))
parklajumi = st.sidebar.multiselect(
    "Pārklājumi", list(PARKLAJUMI), key="karte_parklajumi",
    help="\n\n".join(f"**{k}** — {s.apraksts}" for k, s in PARKLAJUMI.items()))
caurspidigums = st.sidebar.slider("Pārklājumu necaurspīdīgums", 0.1, 1.0, 0.6, 0.05,
                                  key="karte_opacity")
uzraksti = st.sidebar.toggle("Objektu nosaukumi un platības kartē", value=True, key="karte_uzraksti")
if any(s.startswith("Veģetācijas") for s in parklajumi):
    st.sidebar.caption("🌲 " + PARKLAJUMI["Veģetācijas augstums"].apraksts)

st.sidebar.divider()
st.sidebar.subheader("Iet uz vietu")
vieta = st.sidebar.text_input(
    "Koordinātas", placeholder="57.1022, 24.5017  vai  LKS-92: 512345 312345",
    help="WGS84 platums, garums (kā Google Maps) vai LKS-92 koordinātas metros.")
if st.sidebar.button("Rādīt kartē", use_container_width=True, disabled=not vieta):
    skaitli = [float(x.replace(",", ".")) for x in re.findall(r"-?\d+(?:[.,]\d+)?", vieta)]
    if len(skaitli) >= 2:
        a, b = skaitli[:2]
        if abs(a) <= 90 and abs(b) <= 180:
            lat, lon = (a, b) if a > b else (b, a)
        else:
            e, n = (a, b) if (a > 440_000 or b < 300_000) else (b, a)
            lat, lon = lks_uz_wgs(e, n)
        ss.karte_skats = ss.karte_skats_html = {"center": [lat, lon], "zoom": 16}
        ss.karte_markieris = [lat, lon]
        ss.karte_pietuvinat = ss.karte_pietuvinat_html = False
        _mainits()
    else:
        st.sidebar.error("Ievadi divas koordinātas.")

# --- Virsraksts ---------------------------------------------------------------
st.title("🗺️ Karte · cirsmu atzīmēšana un mērījumi")
st.caption(
    "Zīmē cirsmas uz ortofoto, mēri platības un attālumus, importē KML/GeoJSON un piesaisti "
    "laukumus nogabaliem — cirsmas apjoms un vērtība pārrēķinās pēc uzmērītajām platībām. "
    "**Beta versija:** objekti glabājas tikai šajā pārlūka sesijā — saglabā tos ar KML eksportu."
)

# --- Imports ------------------------------------------------------------------
with st.expander("📥 Importēt KML / GeoJSON", expanded=not ss.karte_objekti):
    faili = st.file_uploader("KML vai GeoJSON faili (piem., no Google Earth, LVM GEO vai cita kartes rīka)",
                             type=["kml", "geojson", "json"], accept_multiple_files=True,
                             key=f"karte_imports_{ss.karte_versija}")
    for f in faili or []:
        h = hashlib.sha1(f.getvalue()).hexdigest()
        if h in ss.karte_importeti:
            continue
        try:
            jauni = nolasit_failu(f.getvalue(), f.name)
        except Exception as e:  # noqa: BLE001
            st.error(f"{f.name}: neizdevās nolasīt ({e})")
            continue
        ss.karte_importeti.add(h)
        ss.karte_objekti = ss.karte_objekti + jauni
        st.toast(f"{f.name}: importēti {len(jauni)} objekti")
        _mainits(pietuvinat=True)
        st.rerun()

objekti: list[dict] = ss.karte_objekti

# --- Nogabalu dati: MVR (pēc kadastra) un/vai inventarizācijas PDF ---------------


@st.cache_data(show_spinner="Nolasa PDF…")
def _nolasit_pdf(pdf_baiti: bytes):
    cels = os.path.join(tempfile.gettempdir(), f"inv_{hashlib.sha1(pdf_baiti).hexdigest()}.pdf")
    if not os.path.exists(cels):
        with open(cels, "wb") as f:
            f.write(pdf_baiti)
    return parse_inventory_pdf(cels)


@st.cache_data(ttl=12 * 3600, show_spinner="Ielādē nogabalu datus (Meža valsts reģistrs)…")
def _mvr_teritorija(prefikss: str) -> bytes | None:
    return lejupieladet_teritoriju(prefikss)


def _mvr_nogabali(kadastrs: str):
    try:
        return nogabali_no_faila(_mvr_teritorija(kadastrs[:4]), kadastrs), None
    except MvrKluda as e:
        return None, str(e)


inv_pdf, pdf_kluda = None, None
if ss.get("inv_pdf"):
    try:
        inv_pdf = _nolasit_pdf(ss.inv_pdf["baiti"])
    except Exception as e:  # noqa: BLE001
        pdf_kluda = str(e)

zv_kodi = [z["kadastrs"] for z in ss.karte_zv]
if inv_pdf and inv_pdf.zemes_vieniba in zv_kodi:
    ss.karte_aktiva_zv = inv_pdf.zemes_vieniba
if ss.get("karte_aktiva_zv") not in zv_kodi:
    ss.karte_aktiva_zv = zv_kodi[0] if zv_kodi else None
aktiva_zv = ss.karte_aktiva_zv

mvr_df, mvr_kluda = (_mvr_nogabali(aktiva_zv) if aktiva_zv else (None, None))
nog_robezas: dict[str, dict] = {}
inv = None
if inv_pdf is not None and (not aktiva_zv or inv_pdf.zemes_vieniba in (None, aktiva_zv)):
    inv = inv_pdf
elif mvr_df is not None and len(mvr_df):
    inv = uz_inventarizaciju(aktiva_zv, mvr_df)
if mvr_df is not None and len(mvr_df):
    nog_robezas = mvr_robezas(mvr_df)
    if inv is inv_pdf and inv is not None and all(n.kvartals is None for n in inv.nogabali):
        # PDF bez kvartāliem -> MVR apzīmējumus "1.kv. 12" pārveido uz "12"
        nog_robezas = {k.split(" ", 1)[-1]: g for k, g in nog_robezas.items()}
    if inv is not None:
        nog_robezas = {k: g for k, g in nog_robezas.items() if k in {n.apzimejums for n in inv.nogabali}}

uzmerits = uzmeritas_platibas(objekti, nog_robezas) if inv else {}
cirsmas_vertejumi = {}
if inv:
    _lab = labojumi_no_kartes(inv, objekti, None, tikai_atzimetie=bool(uzmerits), nogabalu_robezas=nog_robezas)
    cirsmas_vertejumi = {v.nogabals.apzimejums: v for v in novertet_ar_labojumiem(inv.nogabali, _lab)}
sakotnejie = {n.apzimejums: novertet_nogabalu(n) for n in inv.nogabali} if inv else {}

# --- Karte --------------------------------------------------------------------
_OBJEKTI_JS = Template("""
{% macro script(this, kwargs) %}
(function() {
    var fc = {{ this.dati }};
    var fg = {{ this.fg }};
    L.geoJSON(fc, {
        style: function(f) { return {color: f.properties.krasa, weight: 2.5,
                                     fillColor: f.properties.krasa, fillOpacity: 0.25}; },
        pointToLayer: function(f, latlng) { return L.marker(latlng); },
        onEachFeature: function(f, layer) {
            layer.bindTooltip(f.properties.etikete,
                {permanent: {{ this.pastavigi }}, direction: "center", className: "karte-etikete"});
            fg.addLayer(layer);
        }
    });
    // Pastāvīgie uzraksti jāpārvieto, kad kartes izmērs mainās (iframe ielāde)
    var karte = {{ this.karte }};
    function atjaunot() { fg.eachLayer(function(l) {
        if (l.getTooltip && l.getTooltip() && {{ this.pastavigi }}) { l.closeTooltip(); l.openTooltip(); } }); }
    karte.on("resize zoomend", atjaunot);
    setTimeout(atjaunot, 400);
})();
{% endmacro %}
""")

_NOGABALI_JS = Template("""
{% macro script(this, kwargs) %}
(function() {
    var karte = {{ this.karte }};
    var slanis = L.geoJSON({{ this.dati }}, {
        style: function(f) { return f.properties.stils; },
        onEachFeature: function(f, layer) {
            layer.bindTooltip(f.properties.uzraksts, {permanent: true, direction: "center",
                                                     className: "nog-etikete"});
            layer.bindPopup(f.properties.popup, {maxWidth: 360});
        }
    }).addTo(karte);
    slanis.bringToBack();
    function redzamiba() {
        var z = karte.getZoom();
        slanis.eachLayer(function(l) { var t = l.getTooltip(); if (!t) return;
            if (z >= 15) { l.openTooltip(); } else { l.closeTooltip(); } });
    }
    karte.on("zoomend resize", redzamiba);
    setTimeout(redzamiba, 400);
})();
{% endmacro %}
""")

_LATVISKI_JS = Template("""
{% macro script(this, kwargs) %}
if (window.L && L.drawLocal) {
  var d = L.drawLocal.draw, e = L.drawLocal.edit;
  d.toolbar.buttons.polygon = "Zīmēt laukumu (cirsmu)";
  d.toolbar.buttons.polyline = "Zīmēt līniju (mērīt garumu)";
  d.toolbar.buttons.rectangle = "Zīmēt taisnstūri";
  d.toolbar.buttons.marker = "Atzīmēt punktu";
  d.toolbar.actions.text = "Atcelt"; d.toolbar.finish.text = "Pabeigt";
  d.toolbar.undo.text = "Dzēst pēdējo punktu";
  d.handlers.polygon.tooltip.start = "Klikšķini, lai sāktu zīmēt laukumu";
  d.handlers.polygon.tooltip.cont = "Klikšķini, lai turpinātu";
  d.handlers.polygon.tooltip.end = "Klikšķini uz pirmā punkta, lai noslēgtu";
  d.handlers.polyline.tooltip.start = "Klikšķini, lai sāktu līniju";
  d.handlers.polyline.tooltip.cont = "Klikšķini, lai turpinātu";
  d.handlers.polyline.tooltip.end = "Klikšķini uz pēdējā punkta, lai pabeigtu";
  d.handlers.polyline.error = "<strong>Kļūda:</strong> malas nedrīkst krustoties!";
  d.handlers.rectangle.tooltip.start = "Klikšķini un velc taisnstūri";
  d.handlers.marker.tooltip.start = "Klikšķini kartē, lai atzīmētu punktu";
  d.handlers.simpleshape.tooltip.end = "Atlaid peli, lai pabeigtu";
  e.toolbar.buttons.edit = "Labot objektu robežas";
  e.toolbar.buttons.editDisabled = "Nav ko labot";
  e.toolbar.buttons.remove = "Dzēst objektus";
  e.toolbar.buttons.removeDisabled = "Nav ko dzēst";
  e.toolbar.actions.save.text = "Saglabāt"; e.toolbar.actions.cancel.text = "Atcelt";
  e.toolbar.actions.clearAll.text = "Dzēst visus";
  e.handlers.edit.tooltip.text = "Velc virsotnes, lai labotu robežu";
  e.handlers.edit.tooltip.subtext = "Spied Atcelt, lai atsauktu izmaiņas";
  e.handlers.remove.tooltip.text = "Klikšķini uz objekta, lai to dzēstu";
}
{% endmacro %}
""")

_STILS = """
<style>
.karte-etikete {background: rgba(255,255,255,.85); border: 0; box-shadow: none;
  font: 600 11px/1.2 system-ui, sans-serif; padding: 1px 4px; color: #111;}
.karte-etikete:before {display: none;}
.leaflet-draw-tooltip {font-size: 12px;}
.nog-etikete {background: transparent; border: 0; box-shadow: none; color: #fff;
  font: 700 11px/1 system-ui, sans-serif; text-shadow: 0 0 3px #000, 0 0 2px #000; padding: 0;}
.nog-etikete:before {display: none;}
.nog-popup td {padding: 1px 6px 1px 0; vertical-align: top; font-size: 12px;}
.nog-popup td:first-child {color: #666; white-space: nowrap;}
</style>
"""


def _elements(template: Template, **kw) -> MacroElement:
    el = MacroElement()
    el._template = template
    for k, v in kw.items():
        setattr(el, k, v)
    return el


def _etikete(o: dict) -> str:
    m = mervienibas(o["geometry"])
    if ir_laukums(o):
        mers = f"{m['platiba_ha']:.2f} ha"
    elif o["geometry"]["type"] == "LineString":
        mers = f"{m['garums_m']:.0f} m"
    else:
        mers = ""
    teksts = o["nosaukums"] + (f" · {mers}" if mers else "")
    if o.get("nogabals"):
        teksts += f"<br>nog. {o['nogabals']}"
    return teksts


def _wms(s, opacity: float, overlay: bool) -> folium.WmsTileLayer:
    return folium.WmsTileLayer(
        url=s.url, layers=s.wms_slanis, fmt=s.formats, transparent=s.caurspidigs,
        attr=ATRIBUCIJA, name=s.nosaukums, overlay=overlay, control=False,
        opacity=opacity, max_zoom=21, version="1.1.1",
    )


def _nog_popup(n, apz: str) -> str:
    v0 = sakotnejie.get(apz)
    v = cirsmas_vertejumi.get(apz)
    rindas = [("Nogabals", f"<b>{apz}</b>"), ("Platība", f"{n.platiba_ha:.2f} ha"),
              ("Kategorija", n.zemes_veids)]
    if n.ir_mezaudze:
        rindas += [("Formula", n.formula or "—"), ("Vecums", f"{n.vecums or '—'} g."),
                   ("Bonitāte", n.bonitate or "—"),
                   ("H / D", f"{n.vid_augstums or '—'} m / {n.vid_caurmers or '—'} cm"),
                   ("Krāja", f"{n.kraja_m3_ha:.0f} m³/ha" if n.kraja_m3_ha else "—")]
    if apz in uzmerits:
        rindas.append(("Uzmērīts kartē", f"<b>{uzmerits[apz]:.2f} ha</b>"))
    if v0 is not None:
        rindas.append(("Kailcirtei", ("✅ atbilst" if v0.atlauta_kailcirte else "✗ neatbilst")
                       + f"<br><small>{v0.pamatojums}</small>"))
    if v is not None and v.atlauta_kailcirte and apz in uzmerits:
        from cirsma.sortiment import vertejuma_apjoms
        rindas.append(("Cērtamais apjoms", f"<b>{vertejuma_apjoms(v)[0]:.0f} m³</b>"))
    for p in n.piezimes[:4]:
        rindas.append(("Piezīme", p))
    return "<table class='nog-popup'>" + "".join(f"<tr><td>{a}</td><td>{b}</td></tr>" for a, b in rindas) \
        + "</table>"


def _nogabalu_slanis() -> dict:
    pec_apz = {n.apzimejums: n for n in inv.nogabali}
    features = []
    for apz, g in nog_robezas.items():
        n = pec_apz.get(apz)
        if n is None:
            continue
        v0 = sakotnejie.get(apz)
        if apz in uzmerits:
            stils = {"color": "#ffffff", "weight": 2.5, "fillColor": "#e5484d", "fillOpacity": 0.12}
        elif v0 is not None and v0.atlauta_kailcirte:
            stils = {"color": "#4ade80", "weight": 2.5, "dashArray": "6 4", "fillOpacity": 0.05,
                     "fillColor": "#4ade80"}
        else:
            stils = {"color": "#ffffff", "weight": 1.2, "opacity": 0.9, "fillOpacity": 0.02}
        features.append({"type": "Feature", "geometry": g, "properties": {
            "stils": stils, "uzraksts": str(n.nr), "popup": _nog_popup(n, apz)}})
    return {"type": "FeatureCollection", "features": features}


def uzbuvet_karti() -> folium.Map:
    skats = ss.karte_skats_html or LATVIJA
    m = folium.Map(location=skats["center"], zoom_start=skats["zoom"], tiles=None,
                   control_scale=True, max_zoom=21, prefer_canvas=False)
    _wms(PAMATKARTES[pamatkarte], 1.0, overlay=False).add_to(m)
    for nos in parklajumi:
        _wms(PARKLAJUMI[nos], caurspidigums, overlay=True).add_to(m)

    m.get_root().header.add_child(folium.Element(_STILS))
    for z in ss.karte_zv:
        folium.GeoJson(
            {"type": "Feature", "geometry": z["geometry"], "properties": {}},
            style_function=lambda _f: {"color": "#facc15", "weight": 3.5, "dashArray": "8 5",
                                       "fill": False, "opacity": 1},
            tooltip=f"Zemes vienība {z['kadastrs']}" + (f" · {z['platiba_ha']:.2f} ha" if z["platiba_ha"] else ""),
            attr=VZD_ATRIBUCIJA,
        ).add_to(m)
    if inv and nog_robezas:
        m.add_child(_elements(_NOGABALI_JS, karte=m.get_name(),
                              dati=json.dumps(_nogabalu_slanis(), ensure_ascii=False)))
    fg = folium.FeatureGroup(name="Objekti", control=False).add_to(m)
    dati = uz_geojson(objekti, ar_merijumiem=False)
    for f, o in zip(dati["features"], objekti):
        f["properties"]["etikete"] = _etikete(o)
    m.add_child(_elements(_OBJEKTI_JS, dati=json.dumps(dati, ensure_ascii=False),
                          fg=fg.get_name(), karte=m.get_name(),
                          pastavigi="true" if uzraksti else "false"))
    m.add_child(_elements(_LATVISKI_JS))
    plugins.Draw(
        feature_group=fg, position="topleft", show_geometry_on_click=False,
        draw_options={
            "polygon": {"allowIntersection": False, "showArea": True, "metric": ["ha", "m"],
                        "precision": {"ha": 2, "m": 0},
                        "shapeOptions": {"color": STATUSI["Kailcirte"], "weight": 2.5}},
            "polyline": {"metric": True, "shapeOptions": {"color": STATUSI["Krautuve / ceļš"]}},
            "rectangle": {"showArea": True, "metric": ["ha", "m"],
                          "shapeOptions": {"color": STATUSI["Kailcirte"], "weight": 2.5}},
            "circle": False, "circlemarker": False, "marker": True,
        },
        edit_options={"edit": True, "remove": True},
    ).add_to(m)
    plugins.MeasureControl(position="topleft", primary_length_unit="meters",
                           secondary_length_unit="kilometers", primary_area_unit="hectares",
                           secondary_area_unit="sqmeters", localization="en",
                           active_color="#e5484d", completed_color="#e5484d").add_to(m)
    plugins.Fullscreen(position="topright", title="Pilnekrāns", title_cancel="Iziet").add_to(m)
    plugins.LocateControl(position="topright", strings={"title": "Mana atrašanās vieta"},
                          flyTo=True, keepCurrentZoomLevel=False).add_to(m)
    plugins.MousePosition(position="bottomleft", separator=" , ", prefix="WGS84:",
                          num_digits=6).add_to(m)
    if ss.get("karte_markieris"):
        folium.Marker(ss.karte_markieris, tooltip="Meklētā vieta",
                      icon=folium.Icon(color="red", icon="crosshairs", prefix="fa")).add_to(m)
    if ss.karte_pietuvinat_html and (objekti or ss.karte_zv):
        fokuss = ss.get("karte_fokuss")
        merkis = ([z for z in ss.karte_zv if z["kadastrs"] in fokuss] if fokuss else []) \
            or objekti + ss.karte_zv
        m.fit_bounds(robezas(merkis), padding=(30, 30), max_zoom=17)
    return m


@st.fragment
def kartes_fragments() -> None:
    karte = uzbuvet_karti()
    rez = st_folium(karte, key="karte", height=640, use_container_width=True,
                    returned_objects=["all_drawings", "center", "zoom"])
    if not rez:
        return
    if rez.get("center") and rez.get("zoom"):
        c = rez["center"]
        ss.karte_skats = {"center": [c["lat"], c["lng"]], "zoom": rez["zoom"]}
        ss.karte_pietuvinat = False
        ss.karte_fokuss = None
    zim = rez.get("all_drawings")
    if zim is None or zim == ss.karte_pedejie_zim:
        return
    ss.karte_pedejie_zim = zim
    jauni, mainits = apvienot_ar_zimejumiem(ss.karte_objekti, zim)
    if mainits:
        ss.karte_objekti = jauni
        _mainits()
        st.rerun(scope="app")


k1, k2, k3 = st.columns([1, 1, 4])
if k1.button("🔍 Pietuvināt objektiem", disabled=not (objekti or ss.karte_zv), use_container_width=True):
    ss.karte_fokuss = None
    _mainits(pietuvinat=True)
if k2.button("🗑 Notīrīt visu", disabled=not objekti, use_container_width=True):
    ss.karte_objekti, ss.karte_importeti = [], set()
    _mainits()
    st.rerun()
k3.caption("Rīki kartes kreisajā pusē: ⬠ laukums · ╱ līnija · ▭ taisnstūris · 📍 punkts · "
           "✎ labot · 🗑 dzēst · 📏 ātrais mērījums (netiek saglabāts).")

kartes_fragments()
objekti = ss.karte_objekti

# --- Nogabali ------------------------------------------------------------------


def _iezimet_cirsmu(apzimejumi_: list[str]) -> None:
    """Kopē nogabalu robežas kā rediģējamus kailcirtes laukumus."""
    for apz in apzimejumi_:
        g = nog_robezas.get(apz)
        if not g:
            continue
        poligoni = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        for i, c in enumerate(poligoni):
            geom = {"type": "Polygon",
                    "coordinates": [[[round(x, 6), round(y, 6)] for x, y, *_ in r] for r in c]}
            nos = f"Cirsma {apz}" + (f" ({i + 1})" if len(poligoni) > 1 else "")
            ss.karte_objekti = ss.karte_objekti + [jauns_objekts(geom, nos, statuss=CIRSMAS_STATUSS)]
    _mainits()


st.subheader("Nogabali")
if len(zv_kodi) > 1:
    st.selectbox("Zemes vienība", zv_kodi, key="karte_aktiva_zv",
                 help="Kuras zemes vienības nogabalus rādīt un vērtēt")
if mvr_kluda:
    st.warning(f"Meža valsts reģistra dati nav pieejami: {mvr_kluda}")
if pdf_kluda:
    st.error(f"Neizdevās nolasīt PDF: {pdf_kluda}")

if inv is None:
    st.info("Atrodi zemes vienību pēc kadastra apzīmējuma (sānjosla) — nogabali ar robežām un "
            "taksācijas datiem tiks ielādēti no Meža valsts reģistra. Vai ielādē inventarizācijas PDF.")
else:
    avots = (f"inventarizācijas PDF **{ss.inv_pdf['nosaukums']}**" if inv is inv_pdf
             else "Meža valsts reģistra atvērtie dati (VMD, atjauno reizi ceturksnī)")
    st.caption(f"Zemes vienība **{inv.zemes_vieniba or aktiva_zv or '—'}** · {len(inv.nogabali)} nogabali · "
               f"dati: {avots}" + (" · robežas: MVR" if nog_robezas else " · nogabalu robežas nav pieejamas"))
    nog_rindas = []
    for n in inv.nogabali:
        apz = n.apzimejums
        v0 = sakotnejie.get(apz)
        nog_rindas.append({
            "Nogabals": apz, "Platība ha": n.platiba_ha, "Uzmērīts kartē ha": uzmerits.get(apz),
            "Kategorija": n.zemes_veids, "Formula": n.formula,
            "Valdošā suga": SUGU_NOSAUKUMI.get(valdosa_suga(n.formula), "") if n.formula else "",
            "Vecums": n.vecums, "Bonitāte": n.bonitate, "Krāja m³/ha": n.kraja_m3_ha,
            "Kailcirtei": ("✅" if v0.atlauta_kailcirte else "—") if v0 else "",
            "Pamatojums": v0.pamatojums if v0 else "",
        })
    izvele = st.dataframe(
        pd.DataFrame(nog_rindas), hide_index=True, use_container_width=True,
        on_select="rerun", selection_mode="multi-row", key=f"nog_tabula_{aktiva_zv}",
        column_config={
            "Platība ha": st.column_config.NumberColumn(format="%.2f"),
            "Uzmērīts kartē ha": st.column_config.NumberColumn(
                format="%.2f", help="Kailcirtes laukumu daļa šajā nogabalā (automātiski pēc robežām "
                                    "vai pēc manuālas piesaistes)"),
            "Krāja m³/ha": st.column_config.NumberColumn(format="%.0f"),
            "Pamatojums": st.column_config.TextColumn(width="large"),
        },
    )
    atlasiti = [nog_rindas[i]["Nogabals"] for i in (izvele.selection.rows if izvele else [])]
    b1, b2, b3 = st.columns([2, 2, 3])
    b1.button(f"✏️ Iezīmēt kā cirsmu ({len(atlasiti)})", disabled=not (atlasiti and nog_robezas),
              on_click=_iezimet_cirsmu, args=(atlasiti,), use_container_width=True, type="primary",
              help="Nogabala robeža tiek nokopēta kā kailcirtes laukums — kartē to var labot (✎), "
                   "un aprēķins pārrēķinās pēc uzmērītās platības.")
    atbilst = [r["Nogabals"] for r in nog_rindas if r["Kailcirtei"] == "✅"]
    b2.button(f"🌲 Visi kailcirtei atbilstošie ({len(atbilst)})", disabled=not (atbilst and nog_robezas),
              on_click=_iezimet_cirsmu, args=(atbilst,), use_container_width=True)
    b3.caption("Atzīmē rindas tabulā vai uzzīmē cirsmu kartē — laukums automātiski tiek sadalīts pa "
               "nogabaliem. Kartē uzklikšķini uz nogabala, lai redzētu tā datus.")

with st.expander("📄 Inventarizācijas PDF (precīzāki dati nekā reģistrā)", expanded=False):
    jauns_pdf = st.file_uploader("VMD vai gabali.lv nogabalu PDF", type="pdf", key="karte_pdf")
    if jauns_pdf and (not ss.get("inv_pdf") or ss.inv_pdf["baiti"] != jauns_pdf.getvalue()):
        ss.inv_pdf = {"baiti": jauns_pdf.getvalue(), "nosaukums": jauns_pdf.name}
        pdf_inv = _nolasit_pdf(ss.inv_pdf["baiti"])
        if pdf_inv.zemes_vieniba and pdf_inv.zemes_vieniba not in zv_kodi:
            _meklet_kadastru([pdf_inv.zemes_vieniba])
        st.rerun()
    if inv_pdf is not None:
        zv = next((z for z in ss.karte_zv if z["kadastrs"] == inv_pdf.zemes_vieniba), None)
        st.caption(f"Ielādēts: **{ss.inv_pdf['nosaukums']}** · {inv_pdf.avots} · NĪ {inv_pdf.ipasums or '—'} · "
                   f"zemes vienība {inv_pdf.zemes_vieniba or '—'} · {len(inv_pdf.nogabali)} nogabali"
                   + (f" · kadastrā {zv['platiba_ha']:.2f} ha" if zv and zv["platiba_ha"] else ""))
    st.caption("Ja PDF ir ielādēts, aprēķinā izmanto PDF datus, bet nogabalu robežas — no reģistra.")

nogabali = nogabalu_saraksts(inv) if inv else {}

# --- Objektu tabula -------------------------------------------------------------
st.subheader("Objekti")
if not objekti:
    st.info("Uzzīmē laukumu kartē (⬠ rīks kreisajā pusē) vai importē KML failu.")
else:
    laukumi = [o for o in objekti if ir_laukums(o)]
    pa_statusiem: dict[str, float] = {}
    for o in laukumi:
        pa_statusiem[o["statuss"]] = pa_statusiem.get(o["statuss"], 0) + mervienibas(o["geometry"])["platiba_ha"]
    c = st.columns(4)
    c[0].metric("Objekti", len(objekti))
    c[1].metric("Laukumu platība (bez pārklāšanās)", f"{kopplatiba_ha(laukumi):.2f} ha")
    c[2].metric("Kailcirte", f"{pa_statusiem.get('Kailcirte', 0):.2f} ha")
    c[3].metric("Citas cirtes", f"{pa_statusiem.get('Kopšanas cirte', 0) + pa_statusiem.get('Izlases cirte', 0):.2f} ha")

    # KML krāsas -> statuss (importētajiem failiem)
    krasas: dict[str, int] = {}
    for o in objekti:
        if o.get("krasa"):
            krasas[o["krasa"]] = krasas.get(o["krasa"], 0) + 1
    if krasas:
        with st.expander(f"🎨 Importēto krāsu nozīme ({len(krasas)} krāsas)", expanded=len(krasas) > 1):
            st.caption("Piešķir statusu visiem importētajiem objektiem ar vienu krāsu.")
            for kr, sk in krasas.items():
                a, b, cc = st.columns([1, 3, 1])
                a.markdown(f"<div style='background:{kr};height:28px;border-radius:4px;margin-top:4px'></div>",
                           unsafe_allow_html=True)
                izv = b.selectbox(f"{kr} · {sk} obj.", list(STATUSI), key=f"krasa_{kr}",
                                  label_visibility="visible")
                if cc.button("Piemērot", key=f"krasa_btn_{kr}", use_container_width=True):
                    for o in objekti:
                        if o.get("krasa") == kr:
                            o["statuss"] = izv
                    _mainits()
                    st.rerun()

    rindas = []
    for o in objekti:
        m = mervienibas(o["geometry"])
        veids = {"Polygon": "Laukums", "LineString": "Līnija", "Point": "Punkts"}.get(o["geometry"]["type"], "?")
        rindas.append({
            "Nosaukums": o["nosaukums"], "Statuss": o["statuss"], "Nogabals": o.get("nogabals"),
            "Veids": veids,
            "Platība ha": m["platiba_ha"] if veids == "Laukums" else None,
            "Perimetrs / garums m": m["garums_m"] if veids != "Punkts" else None,
            "Nogabali (pēc robežām)": ("; ".join(f"{k}: {v:.2f} ha" for k, v in
                                                 objekta_sadalijums(o, nog_robezas).items())
                                       if veids == "Laukums" and nog_robezas and not o.get("nogabals")
                                       else ""),
            "LKS-92 x": m["x"], "LKS-92 y": m["y"],
            "Piezīmes": o.get("piezimes") or "",
        })

    def _saglabat_tabulu(atsl: str, ids: list[str]) -> None:
        st_ed = ss[atsl]
        pec_id = {o["id"]: o for o in ss.karte_objekti}
        lauki = {"Nosaukums": "nosaukums", "Statuss": "statuss", "Nogabals": "nogabals",
                 "Piezīmes": "piezimes"}
        for rinda, izm in st_ed.get("edited_rows", {}).items():
            o = pec_id[ids[int(rinda)]]
            for kol, v in izm.items():
                if kol == "Nogabals":
                    o["nogabals"] = v.split(" · ")[0] if v else None
                elif kol in lauki:
                    o[lauki[kol]] = v or ("" if kol == "Piezīmes" else o[lauki[kol]])
        dzest = {ids[i] for i in st_ed.get("deleted_rows", [])}
        if dzest:
            ss.karte_objekti = [o for o in ss.karte_objekti if o["id"] not in dzest]
        ss.karte_versija += 1

    ids = [o["id"] for o in objekti]
    atsl = f"karte_tabula_{ss.karte_versija}"
    df = pd.DataFrame(rindas)
    nog_opcijas = list(nogabali.values())
    if nogabali:
        df["Nogabals"] = [nogabali.get(o.get("nogabals"), o.get("nogabals")) for o in objekti]
    st.data_editor(
        df, key=atsl, on_change=_saglabat_tabulu, args=(atsl, ids), hide_index=True,
        use_container_width=True, num_rows="delete",
        disabled=["Veids", "Platība ha", "Perimetrs / garums m", "LKS-92 x", "LKS-92 y",
                  "Nogabali (pēc robežām)"]
        + ([] if nogabali else ["Nogabals"]),
        column_config={
            "Statuss": st.column_config.SelectboxColumn(options=list(STATUSI), required=True,
                                                        help="Nosaka krāsu kartē; 'Kailcirte' laukumi veido cirsmu"),
            "Nogabals": (st.column_config.SelectboxColumn(
                options=nog_opcijas, width="large",
                help="Neobligāti: piesaisti visu laukumu vienam nogabalam. Ja tukšs un nogabalu "
                     "robežas zināmas, laukums tiek sadalīts pa nogabaliem automātiski.")
                if nogabali else st.column_config.TextColumn(help="Ielādē nogabalu PDF, lai varētu piesaistīt")),
            "Platība ha": st.column_config.NumberColumn(format="%.2f", help="Aprēķināts LKS-92 (EPSG:3059)"),
            "Perimetrs / garums m": st.column_config.NumberColumn(format="%.0f"),
            "LKS-92 x": st.column_config.NumberColumn(format="%d", help="Centra austrumu koordināta (E)"),
            "LKS-92 y": st.column_config.NumberColumn(format="%d", help="Centra ziemeļu koordināta (N)"),
            "Piezīmes": st.column_config.TextColumn(width="medium"),
            "Nogabali (pēc robežām)": st.column_config.TextColumn(width="medium"),
        },
    )

    parkl = parklasanas(objekti)
    if parkl:
        nos = {o["id"]: o["nosaukums"] for o in objekti}
        st.warning("Laukumi pārklājas: " + "; ".join(
            f"{nos[a]} ↔ {nos[b]} ({m2:.0f} m²)" for a, b, m2 in parkl)
            + ". Kopplatībā pārklāšanās netiek skaitīta divreiz, bet nogabalu pārrēķinā gan — "
              "precizē robežas ar ✎ rīku.")

    # --- Eksports ---------------------------------------------------------------
    e1, e2, e3 = st.columns(3)
    e1.download_button("⬇️ KML (Google Earth, LVM GEO)", uz_kml(objekti), file_name="cirsmas.kml",
                       mime="application/vnd.google-earth.kml+xml", use_container_width=True)
    e2.download_button("⬇️ GeoJSON", json.dumps(uz_geojson(objekti), ensure_ascii=False, indent=1),
                       file_name="cirsmas.geojson", mime="application/geo+json", use_container_width=True)
    buf = io.BytesIO()
    pd.DataFrame(rindas).to_excel(buf, index=False, sheet_name="Objekti")
    e3.download_button("⬇️ Excel tabula", buf.getvalue(), file_name="cirsmas_objekti.xlsx",
                       use_container_width=True)

# --- Pārrēķins ------------------------------------------------------------------
if inv and objekti:
    st.subheader("Cirsmas aprēķins pēc kartes")
    if not uzmerits:
        st.info("Uzzīmē kailcirtes laukumu nogabalu robežās (vai atzīmē nogabalus tabulā un spied "
                "**Iezīmēt kā cirsmu**) — šeit uzreiz redzēsi apjomu un iegādes summu."
                + ("" if nog_robezas else " Bez nogabalu robežām laukumu piesaisti nogabalam tabulā "
                   "kolonnā **Nogabals**."))
    else:
        ir_pdf = inv is inv_pdf
        pdf_id = hashlib.sha1(ss.inv_pdf["baiti"]).hexdigest() if ir_pdf else None
        esosie = ss.labojumi if ir_pdf and ss.get("faila_id") == pdf_id else {}
        tikai = st.toggle("Cirsmā tikai kartē atzīmētie nogabali", value=True,
                          help="Ieslēgts: nogabali bez kailcirtes laukuma kartē netiek cirsti. "
                               "Izslēgts: pārējiem paliek sistēmas lēmums pēc kailcirtes kritērijiem.")
        s = salidzinat(inv, objekti, esosie, tikai_atzimetie=tikai, nogabalu_robezas=nog_robezas)
        uz = "inventarizāciju" if ir_pdf else "reģistra platībām"
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Cirsmas platība", f"{sum(uzmerits.values()):.2f} ha")
        m2.metric("Cērtamais apjoms", f"{s.pec.kopejais_m3:,.0f} m³",
                  f"{s.pec.kopejais_m3 - s.pirms.kopejais_m3:+,.0f} m³ pret {uz}")
        m3.metric("Max iegādes summa", f"{s.pec.max_iegades_summa:,.0f} EUR",
                  f"{s.pec.max_iegades_summa - s.pirms.max_iegades_summa:+,.0f} EUR")
        m4.metric("Cena", f"{s.pec.cena_eur_m3:.2f} EUR/m³", f"{s.pec.cena_eur_m3 - s.pirms.cena_eur_m3:+.2f}")
        tab = pd.DataFrame(s.rindas)
        tab["Uzmērīts kartē ha"] = [f"{x:.2f}" if x is not None else "—" for x in tab["Uzmērīts kartē ha"]]
        st.dataframe(tab, hide_index=True, use_container_width=True,
                     column_config={"Platība inventarizācijā ha": st.column_config.NumberColumn(format="%.2f"),
                                    "Piezīme": st.column_config.TextColumn(width="large")})
        if s.pec.pa_sugam_m3:
            st.caption("Apjoms pa sugām: " + " · ".join(
                f"{SUGU_NOSAUKUMI.get(k, k)} {v:,.0f} m³" for k, v in s.pec.pa_sugam_m3.items()))
        st.caption("Aprēķinā noklusējuma sortimentu cenas un izdevumi (kā Meža inventarizācijas sadaļā). "
                   "Apjoms = krāja m³/ha × uzmērītā platība; sugu proporcijas saglabājas.")

        jaunie = labojumi_no_kartes(inv, objekti, esosie, tikai, nog_robezas)
        v_pec = novertet_ar_labojumiem(inv.nogabali, jaunie)
        p1, p2 = st.columns(2)
        xlsx = os.path.join(tempfile.gettempdir(),
                            f"karte_{hashlib.sha1(json.dumps(uz_geojson(objekti, False)).encode()).hexdigest()[:10]}.xlsx")
        excel_atskaite(xlsx, inv, v_pec, s.pec)
        with open(xlsx, "rb") as f:
            p1.download_button("⬇️ Excel atskaite ar kartes platībām", f.read(),
                               file_name=f"cirsma_{inv.zemes_vieniba or 'karte'}.xlsx", use_container_width=True)
        if ir_pdf and p2.button("➡️ Pārnest uz Meža inventarizāciju", use_container_width=True,
                                help="Kartes platības kļūst par labojumiem nogabalu tabulā (var atiestatīt)."):
            ss.faila_id = pdf_id
            ss.labojumi = jaunie
            ss.tabulas_versija = ss.get("tabulas_versija", 0) + 1
            st.switch_page("views/mezs.py")

st.divider()
st.caption("Kartes dati: LVM GEO brīvpieejas WMS (ortofoto, LiDAR veģetācijas augstums — LĢIA; "
           "mežaudžu plāns — VMD; kadastrs — VZD); zemes vienību robežas — VZD INSPIRE WFS (CC BY 4.0); "
           "nogabalu robežas un dati — VMD Meža valsts reģistra atvērtie dati (CC0). Platības rēķinātas LKS-92 / TM (EPSG:3059).")
