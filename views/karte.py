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

from cirsma.labojumi import novertet_ar_labojumiem
from cirsma.parser import parse_inventory_pdf
from cirsma.report import excel_atskaite
from karte.geometrija import (
    STATUSI, apvienot_ar_zimejumiem, ir_laukums, jauns_objekts, kopplatiba_ha, lks_uz_wgs, mervienibas,
    nolasit_failu, objekta_krasa, parklasanas, robezas, uz_geojson, uz_kml,
)
from karte.kadastrs import ATRIBUCIJA as VZD_ATRIBUCIJA, KadastrsKluda, apzimejumi, atrast
from karte.parrekins import labojumi_no_kartes, nogabalu_saraksts, salidzinat
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

# --- Inventarizācijas dati (nogabali) ------------------------------------------


@st.cache_data(show_spinner="Nolasa PDF…")
def _nolasit_pdf(pdf_baiti: bytes):
    cels = os.path.join(tempfile.gettempdir(), f"inv_{hashlib.sha1(pdf_baiti).hexdigest()}.pdf")
    if not os.path.exists(cels):
        with open(cels, "wb") as f:
            f.write(pdf_baiti)
    return parse_inventory_pdf(cels)


inv = None
with st.expander("🌲 Nogabalu dati pārrēķinam (inventarizācijas PDF)",
                 expanded=bool(objekti) and not ss.get("inv_pdf")):
    jauns_pdf = st.file_uploader("VMD vai gabali.lv nogabalu PDF", type="pdf", key="karte_pdf")
    if jauns_pdf:
        ss.inv_pdf = {"baiti": jauns_pdf.getvalue(), "nosaukums": jauns_pdf.name}
    if ss.get("inv_pdf"):
        try:
            inv = _nolasit_pdf(ss.inv_pdf["baiti"])
            st.caption(f"Ielādēts: **{ss.inv_pdf['nosaukums']}** · {inv.avots} · NĪ {inv.ipasums or '—'} · "
                       f"zemes vienība {inv.zemes_vieniba or '—'} · {len(inv.nogabali)} nogabali "
                       "(to pašu failu redz arī Meža inventarizācijas sadaļa).")
            pdf_id = hashlib.sha1(ss.inv_pdf["baiti"]).hexdigest()
            if inv.zemes_vieniba and ss.get("karte_pdf_meklets") != pdf_id:
                # Jauns PDF -> automātiski atrod tā zemes vienību kartē
                ss.karte_pdf_meklets = pdf_id
                if inv.zemes_vieniba not in {z["kadastrs"] for z in ss.karte_zv}:
                    _meklet_kadastru([inv.zemes_vieniba])
                    st.rerun()
            zv = next((z for z in ss.karte_zv if z["kadastrs"] == inv.zemes_vieniba), None)
            if zv and zv["platiba_ha"]:
                kopa = sum(n.platiba_ha for n in inv.nogabali)
                st.caption(f"📍 Zemes vienība {zv['kadastrs']} atzīmēta kartē (dzeltena svītrlīnija): "
                           f"kadastrā {zv['platiba_ha']:.2f} ha, pēc robežām {zv['platiba_graf_ha']:.2f} ha, "
                           f"nogabalu kopplatība PDF {kopa:.2f} ha.")
        except Exception as e:  # noqa: BLE001
            st.error(f"Neizdevās nolasīt PDF: {e}")
    else:
        st.caption("Ielādē PDF, lai kartes laukumus varētu piesaistīt nogabaliem un pārrēķināt cirsmu.")

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
        disabled=["Veids", "Platība ha", "Perimetrs / garums m", "LKS-92 x", "LKS-92 y"]
        + ([] if nogabali else ["Nogabals"]),
        column_config={
            "Statuss": st.column_config.SelectboxColumn(options=list(STATUSI), required=True,
                                                        help="Nosaka krāsu kartē; 'Kailcirte' laukumi veido cirsmu"),
            "Nogabals": (st.column_config.SelectboxColumn(
                options=nog_opcijas, width="large",
                help="Piesaisti laukumu inventarizācijas nogabalam — pārrēķinā nogabala platība = "
                     "piesaistīto kailcirtes laukumu summa")
                if nogabali else st.column_config.TextColumn(help="Ielādē nogabalu PDF, lai varētu piesaistīt")),
            "Platība ha": st.column_config.NumberColumn(format="%.2f", help="Aprēķināts LKS-92 (EPSG:3059)"),
            "Perimetrs / garums m": st.column_config.NumberColumn(format="%.0f"),
            "LKS-92 x": st.column_config.NumberColumn(format="%d", help="Centra austrumu koordināta (E)"),
            "LKS-92 y": st.column_config.NumberColumn(format="%d", help="Centra ziemeļu koordināta (N)"),
            "Piezīmes": st.column_config.TextColumn(width="medium"),
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
    st.subheader("Cirsmas pārrēķins pēc kartes")
    piesaistiti = [o for o in objekti if o.get("nogabals") and o["statuss"] == "Kailcirte" and ir_laukums(o)]
    if not piesaistiti:
        st.info("Tabulā kolonnā **Nogabals** piesaisti kailcirtes laukumus nogabaliem — tad šeit "
                "redzēsi apjoma un vērtības pārrēķinu.")
    else:
        esosie = ss.labojumi if ss.get("faila_id") == hashlib.sha1(ss.inv_pdf["baiti"]).hexdigest() else {}
        tikai = st.toggle("Cirsmā tikai kartē atzīmētie nogabali", value=True,
                          help="Ieslēgts: nogabali bez kailcirtes laukuma kartē netiek cirsti. "
                               "Izslēgts: tiem paliek sistēmas / PDF lēmums.")
        s = salidzinat(inv, objekti, esosie, tikai_atzimetie=tikai)
        m1, m2, m3 = st.columns(3)
        m1.metric("Cērtamais apjoms", f"{s.pec.kopejais_m3:,.0f} m³",
                  f"{s.pec.kopejais_m3 - s.pirms.kopejais_m3:+,.0f} m³ pret PDF")
        m2.metric("Max iegādes summa", f"{s.pec.max_iegades_summa:,.0f} EUR",
                  f"{s.pec.max_iegades_summa - s.pirms.max_iegades_summa:+,.0f} EUR")
        m3.metric("Cena", f"{s.pec.cena_eur_m3:.2f} EUR/m³",
                  f"{s.pec.cena_eur_m3 - s.pirms.cena_eur_m3:+.2f}")
        tab = pd.DataFrame(s.rindas)
        tab["Uzmērīts kartē ha"] = [f"{x:.2f}" if x is not None else "—" for x in tab["Uzmērīts kartē ha"]]
        st.dataframe(tab, hide_index=True, use_container_width=True,
                     column_config={"Platība PDF ha": st.column_config.NumberColumn(format="%.2f"),
                                    "Piezīme": st.column_config.TextColumn(width="large")})
        st.caption("Aprēķinā noklusējuma sortimentu cenas un izdevumi (kā Meža inventarizācijas sadaļā). "
                   "Apjoms = krāja m³/ha × uzmērītā platība; sugu proporcijas saglabājas.")

        jaunie = labojumi_no_kartes(inv, objekti, esosie, tikai)
        v_pec = novertet_ar_labojumiem(inv.nogabali, jaunie)
        p1, p2 = st.columns(2)
        xlsx = os.path.join(tempfile.gettempdir(), f"karte_{hashlib.sha1(json.dumps(uz_geojson(objekti, False)).encode()).hexdigest()[:10]}.xlsx")
        excel_atskaite(xlsx, inv, v_pec, s.pec)
        with open(xlsx, "rb") as f:
            p1.download_button("⬇️ Excel atskaite ar kartes platībām", f.read(),
                               file_name="cirsmas_atskaite_karte.xlsx", use_container_width=True)
        if p2.button("➡️ Pārnest uz Meža inventarizāciju", use_container_width=True,
                     help="Kartes platības kļūst par labojumiem nogabalu tabulā (var atiestatīt)."):
            ss.faila_id = hashlib.sha1(ss.inv_pdf["baiti"]).hexdigest()
            ss.labojumi = jaunie
            ss.tabulas_versija = ss.get("tabulas_versija", 0) + 1
            st.switch_page("views/mezs.py")

st.divider()
st.caption("Kartes dati: LVM GEO brīvpieejas WMS (ortofoto, LiDAR veģetācijas augstums — LĢIA; "
           "mežaudžu plāns — VMD; kadastrs — VZD); zemes vienību robežas — VZD INSPIRE WFS (CC BY 4.0). Platības rēķinātas LKS-92 / TM (EPSG:3059).")
