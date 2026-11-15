"""Modulis: ĢIS karte — cirsmu atzīmēšana, mērījumi un pārrēķins (beta)."""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import tempfile

import folium
import shapely
from shapely.geometry import mapping
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
    CIRSMAS_STATUSS, automatiskas_cirsmas, blakus_kailcirsu_bridinajumi, labojumi_no_kartes,
    nogabalu_saraksts, objekta_sadalijums, sadalit_objektu, salidzinat, uzmeritas_visas,
)
from views.kopigi import aktivais_cenradis, cenradis_statuss_sanjosla
from karte.slani import ATRIBUCIJA, NOKLUSETIE_PARKLAJUMI, PAMATKARTES, PARKLAJUMI

# VZD proxy no Streamlit Secrets (drošībai arī tad, ja Secrets netiek padoti kā vides mainīgie)
try:
    for _atsl in ("VZD_PROXY", "MVR_GITHUB_TOKEN"):
        if st.secrets.get(_atsl) and not os.environ.get(_atsl):
            os.environ[_atsl] = str(st.secrets[_atsl])
except Exception:  # noqa: BLE001 — lokāli Secrets var nebūt
    pass

LATVIJA = {"center": [56.95, 24.6], "zoom": 8}
AKCENTS = "#ff4b4b"      # aplikācijas pogu krāsa — līnijām un virsotnēm kartē

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
ss.setdefault("karte_auto_zv", [])        # zemes vienības, kurām jāiezīmē cērtamie nogabali
ss.setdefault("karte_auto", True)
cenradis = aktivais_cenradis()
nt = cenradis.noteikumi
aprekina_param = dict(matricas=cenradis.matricas, izdevumi_pa_veidiem=cenradis.izdevumi,
                      pelnas_rezerve=cenradis.pelnas_rezerve)
if ss.pop("karte_ieslegt_nogabalus", False):
    ss.karte_parklajumi = list(dict.fromkeys(list(ss.karte_parklajumi) + ["Mežaudžu plāns (VMD nogabali)"]))


# Karte tiek pārzīmēta (HTML mainās) tikai pilnā lapas pārlādē. Pārvietojot karti, fragments
# saglabā skatu `karte_skats`, bet HTML izmanto `karte_skats_html`, lai karte nepārlādētos.
ss.karte_skats_html = ss.karte_skats
ss.karte_pietuvinat_html = ss.karte_pietuvinat
ss.karte_fokuss_html = ss.karte_fokuss


def _mainits(pietuvinat: bool = False) -> None:
    ss.karte_versija += 1
    if pietuvinat:
        ss.karte_pietuvinat = ss.karte_pietuvinat_html = True


@st.cache_data(ttl=12 * 3600, show_spinner="Ielādē nogabalu datus (Meža valsts reģistrs)…")
def _mvr_teritorija(prefikss: str) -> bytes | None:
    return lejupieladet_teritoriju(prefikss)


def _mvr_nogabali(kadastrs: str):
    try:
        return nogabali_no_faila(_mvr_teritorija(kadastrs[:4]), kadastrs), None
    except MvrKluda as e:
        return None, str(e)


def _zv_no_mvr(kadastrs: str) -> dict | None:
    """Rezerves variants, ja VZD serviss nav sasniedzams: zemes vienības meža daļa no MVR."""
    df, _ = _mvr_nogabali(kadastrs)
    if df is None or df.empty:
        return None
    g = shapely.union_all([shapely.from_wkb(b) for b in df["geom"]])
    geom = mapping(g)
    return {"kadastrs": kadastrs, "platiba_ha": None, "platiba_graf_ha": mervienibas(geom)["platiba_ha"],
            "geometry": geom, "saite": f"https://www.kadastrs.lv/parcels/search?cad_num={kadastrs}",
            "tikai_mezs": True}


def _meklet_kadastru(kodi: list[str] | None = None, auto: bool = True) -> None:
    """Atrod zemes vienības VZD servisā, parāda kartē un ieslēdz nogabalu slāni."""
    kodi = kodi if kodi is not None else apzimejumi(ss.get("karte_kad_ievade", ""))
    if not kodi:
        ss.karte_zv_zina = ("error", "Ievadi 11 ciparu kadastra apzīmējumu, piem., 80640010066.")
        return
    vzd_kluda = None
    try:
        atrasti = atrast(kodi, timeout=8)
    except KadastrsKluda as e:
        atrasti, vzd_kluda = [], e
    # Ko VZD neatrada (vai serviss nav pieejams) — meklē Meža valsts reģistrā
    for k in [k for k in kodi if k not in {z["kadastrs"] for z in atrasti}]:
        z = _zv_no_mvr(k)
        if z:
            atrasti.append(z)
    if vzd_kluda and not atrasti:
        ss.karte_zv_zina = ("error", f"Zemes vienība nav atrasta: VZD kadastra serviss nav pieejams, "
                                     f"un Meža valsts reģistrā šim apzīmējumam nav nogabalu.")
        return
    esosie = {z["kadastrs"] for z in ss.karte_zv}
    ss.karte_zv = ss.karte_zv + [z for z in atrasti if z["kadastrs"] not in esosie]
    neatrasti = [k for k in kodi if k not in {z["kadastrs"] for z in atrasti}]
    ss.karte_zv_zina = (("warning", "Nav atrasta zemes vienība: " + ", ".join(neatrasti)
                         + ". Ja tas ir īpašuma numurs, kadastrs.lv apskaties tā zemes vienību apzīmējumus.")
                        if neatrasti else
                        ("info", "VZD kadastra serviss šobrīd nav sasniedzams — rādīta zemes vienības meža "
                                 "daļa pēc Meža valsts reģistra nogabaliem (bez precīzas kadastra robežas).")
                        if any(z.get("tikai_mezs") for z in atrasti) else None)
    if atrasti and auto and ss.get("karte_auto", True):
        ss.karte_auto_zv = ss.karte_auto_zv + [z["kadastrs"] for z in atrasti]
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
        ss.karte_objekti = ss.karte_objekti + [jauns_objekts(geom, nos, statuss=CIRSMAS_STATUSS)]
    ss.karte_fokuss = [kadastrs]
    _mainits(pietuvinat=True)


# Atvērts no "Saglabātie" — atrod zemes vienību (poligoni jau ielādēti, auto iezīmēšana nav vajadzīga)
if ss.get("karte_atvert_kadastru"):
    _meklet_kadastru([ss.pop("karte_atvert_kadastru")], auto=False)

# --- Sānjosla: kadastrs -----------------------------------------------------
st.sidebar.header("Meklēt pēc kadastra")
st.sidebar.text_input("Zemes vienības kadastra apzīmējums", key="karte_kad_ievade",
                      placeholder="piem., 80640010066",
                      help="11 cipari (atstarpes nav svarīgas). Vairākus atdali ar komatu. "
                           "Dati: VZD Kadastrālie zemes gabali (INSPIRE), atjauno reizi nedēļā.")
st.sidebar.toggle("Uzreiz iezīmēt cērtamos nogabalus", key="karte_auto",
                  help="Atrodot zemes vienību, kailcirtei un kopšanai atbilstošajiem nogabaliem automātiski "
                       "tiek uzzīmēti poligoni. Kailcirti, kas pārsniedz max platību pēc meža tipa, sadala "
                       "ar atdalošo joslu. Poligonus var labot (✎) vai dzēst.")
st.sidebar.button("🔎 Atrast kartē", on_click=_meklet_kadastru, use_container_width=True, type="primary")
if ss.karte_zv_zina:
    getattr(st.sidebar, ss.karte_zv_zina[0])(ss.karte_zv_zina[1])
for z in ss.karte_zv:
    with st.sidebar.container(border=True):
        if z.get("tikai_mezs"):
            st.markdown(f"📍 **[{z['kadastrs']}]({z['saite']})** · mežs {z['platiba_graf_ha']:.2f} ha",
                        help="Robeža = Meža valsts reģistra nogabalu apvienojums (VZD serviss nebija "
                             "pieejams). Saite atver kadastrs.lv.")
        else:
            st.markdown(f"📍 **[{z['kadastrs']}]({z['saite']})** · {z['platiba_ha'] or 0:.2f} ha",
                        help=f"Kadastrā reģistrētā platība {z['platiba_ha'] or 0:.2f} ha; pēc robežām "
                             f"(LKS-92) {z['platiba_graf_ha']:.2f} ha. Saite atver kadastrs.lv.")
        b, c = st.columns(2)
        b.button("🧮 Aprēķins", key=f"zv_obj_{z['kadastrs']}", on_click=_zv_ka_objekts,
                 args=(z["kadastrs"],), use_container_width=True,
                 help="Pārņem zemes vienības robežu kā cirsmu un aprēķina tās vērtību. Robežu var "
                      "labot: kartē spied ✎, velc virsotnes — platība, malu garumi un aprēķins atjaunojas.")
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
    "Lai saglabātu darbu, atver aprēķinu kalkulatorā un spied **Saglabāt priekšvērtējumu** "
    "(vai eksportē KML)."
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

# Automātiski iezīmē cērtamos nogabalus tikko atrastajai zemes vienībai
if aktiva_zv in ss.karte_auto_zv and inv is not None and nog_robezas:
    ss.karte_auto_zv = [k for k in ss.karte_auto_zv if k != aktiva_zv]
    jau = set(uzmeritas_visas(objekti, nog_robezas))
    jauni = automatiskas_cirsmas(inv, nog_robezas, nt, izlaist=jau)
    if jauni:
        ss.karte_objekti = objekti = objekti + jauni
        ss.karte_zv_zina = ("success", f"Iezīmēti {len(jauni)} poligoni cērtamajiem nogabaliem "
                                       f"({aktiva_zv}). Labo tos kartē ar ✎ vai dzēs tabulā Objekti.")
        st.toast(ss.karte_zv_zina[1], icon="🌲")
        _mainits()

ss.setdefault("karte_tikai", True)
ss.setdefault("karte_visi", True)     # iezīmētais laukums vienmēr nonāk aprēķinā (ar ⚠, ja neatbilst)
uzmerits = uzmeritas_visas(objekti, nog_robezas) if inv else {}
cirsmas_vertejumi = {}
kartes_fin = None
if inv:
    _lab = labojumi_no_kartes(inv, objekti, None, tikai_atzimetie=ss.karte_tikai and bool(uzmerits),
                              nogabalu_robezas=nog_robezas, ieklaut_neatbilstosos=ss.karte_visi)
    cirsmas_vertejumi = {v.nogabals.apzimejums: v for v in novertet_ar_labojumiem(inv.nogabali, _lab, nt)}
    if uzmerits:
        from cirsma.sortiment import aprekinat as _aprekinat
        kartes_fin = _aprekinat(list(cirsmas_vertejumi.values()), **aprekina_param)
sakotnejie = {n.apzimejums: novertet_nogabalu(n, nt=nt) for n in inv.nogabali} if inv else {}
blakus_bridinajumi = blakus_kailcirsu_bridinajumi(objekti, inv, nog_robezas, nt)

# --- Karte --------------------------------------------------------------------
_OBJEKTI_JS = Template("""
{% macro script(this, kwargs) %}
(function() {
    var fc = {{ this.dati }};
    var fg = {{ this.fg_el.get_name() }};
    var karte = {{ this._parent.get_name() }};
    var STATUSI = {{ this.statusi }};
    var LAUKUMA_STATUSI = ["Kailcirte", "Kopšanas cirte", "Izlases cirte"];
    var BK = window.BK = {karte: karte, fg: fg, izvelets: null, aiznemts: false};

    // ---- Paziņošana Python pusei (streamlit-folium nolasa visus fg objektus) ----------
    var taimeris = null;
    BK.pazinot = function(uzreiz) {
        clearTimeout(taimeris);
        taimeris = setTimeout(function() {
            karte.fire("draw:edited", {layers: L.layerGroup()});
        }, uzreiz ? 0 : 700);
    };

    // ---- Stils un izvēle -----------------------------------------------------------
    function krasa(l) { return (l.feature && l.feature.properties.krasa) || "#ff4b4b"; }
    function bazesStils(l) { return {color: krasa(l), weight: 3.5, fillColor: krasa(l),
                                    fillOpacity: 0.25, dashArray: null}; }
    function izvelesStils(l) { return {color: "#ffffff", weight: 5, fillColor: krasa(l),
                                       fillOpacity: 0.4, dashArray: "8 6"}; }
    BK.izveleties = function(l) {
        if (BK.izvelets && BK.izvelets !== l && BK.izvelets.setStyle) BK.izvelets.setStyle(bazesStils(BK.izvelets));
        BK.izvelets = l;
        if (l && l.setStyle) l.setStyle(izvelesStils(l));
        fg.eachLayer(function(x) { if (x.setStyle) {
            x.options.editing = L.extend({}, BK.izvelets === x ? izvelesStils(x) : bazesStils(x));
            x.options.original = L.extend({}, x.options.editing); } });
        if (BK.atjaunotRikus) BK.atjaunotRikus();
    };

    // ---- Uzraksts (atjaunojas uzreiz pēc virsotnes pārvilkšanas) ---------------------
    function gredzeni(ll) {
        if (!ll.length) return [];
        if (ll[0] instanceof L.LatLng) return [ll];
        return ll.reduce(function(a, x) { return a.concat(gredzeni(x)); }, []);
    }
    function garumsTeksts(d) { return d < 1000 ? d.toFixed(d < 100 ? 1 : 0) + " m" : (d / 1000).toFixed(2) + " km"; }
    function atjaunotUzrakstu(l) {
        if (!(l instanceof L.Polygon) || !L.GeometryUtil || !l.getTooltip()) return;
        var r = gredzeni(l.getLatLngs()), ha = 0, p = 0;
        r.forEach(function(g, i) {
            var a = L.GeometryUtil.geodesicArea(g) / 10000;
            ha += i === 0 ? a : 0;
            for (var j = 0; j < g.length; j++) p += karte.distance(g[j], g[(j + 1) % g.length]);
        });
        var nos = (l.feature && l.feature.properties.nosaukums) || "Laukums";
        l.setTooltipContent(nos + " · " + ha.toFixed(2) + " ha · " + garumsTeksts(p));
    }

    // ---- Objekti ---------------------------------------------------------------------
    function piesaistit(layer) {
        layer.on("click", function(e) {
            if (BK.aiznemts) return;
            L.DomEvent.stopPropagation(e);
            BK.izveleties(layer);
        });
        layer.on("contextmenu", function(e) {
            L.DomEvent.stopPropagation(e);
            if (e.originalEvent) e.originalEvent.preventDefault();
            if (BK.aiznemts) return;
            BK.izveleties(layer);
            BK.izvelne(e.containerPoint, layer);
        });
        layer.on("edit", function() { atjaunotUzrakstu(layer); BK.pazinot(); });
    }
    L.geoJSON(fc, {
        style: function(f) { return {color: f.properties.krasa, weight: 3.5,
                                     fillColor: f.properties.krasa, fillOpacity: 0.25}; },
        pointToLayer: function(f, latlng) { return L.marker(latlng); },
        onEachFeature: function(f, layer) {
            layer.bindTooltip(f.properties.etikete,
                {permanent: {{ this.pastavigi }}, direction: "center", className: "karte-etikete"});
            fg.addLayer(layer);
            piesaistit(layer);
        }
    });
    // Jauna figūra (klikšķis uz nogabala / ZV vai zīmēšanas rīks) — ar savu id, stilu un uzrakstu,
    // lai Python pusei karte nebūtu jāpārzīmē (tad tā nemirgo)
    function jaunsId() { return "j" + Math.random().toString(36).slice(2, 12); }
    BK.pievienot = function(l, props) {
        l.feature = l.feature || {type: "Feature", properties: {}};
        var p = L.extend(l.feature.properties, props || {});
        if (!p.id) p.id = jaunsId();
        if (!p.statuss && l instanceof L.Polygon) p.statuss = "Kailcirte";
        p.krasa = STATUSI[p.statuss] || "#14b8a6";
        if (l.setStyle) l.setStyle(bazesStils(l));
        if (!fg.hasLayer(l)) fg.addLayer(l);
        if (!l.getTooltip()) {
            l.bindTooltip(p.nosaukums || (l instanceof L.Polygon ? "Laukums" : l instanceof L.Polyline ? "Līnija" : "Punkts"),
                          {permanent: {{ this.pastavigi }}, direction: "center", className: "karte-etikete"});
        }
        piesaistit(l);
        atjaunotUzrakstu(l);
        redigesana();
        BK.pazinot(true);
    };
    karte.on("draw:created", function(e) { setTimeout(function() { BK.pievienot(e.layer); }, 0); });

    // ---- Virsotņu vilkšana bez rīka (no 15. tuvinājuma) -------------------------------
    var REDIGET_NO = 16;
    function redigesana() {
        var var_ = karte.getZoom() >= REDIGET_NO && !BK.aiznemts;
        fg.eachLayer(function(l) {
            if (!l.editing) return;
            if (l.setStyle) {   // Leaflet.draw sagaida stilus, ko parasti iestata tā rīkjosla
                var st = BK.izvelets === l ? izvelesStils(l) : bazesStils(l);
                l.options.editing = L.extend({}, st);
                l.options.original = L.extend({}, st);
            }
            try { if (var_) { l.editing.enable(); } else { l.editing.disable(); } }
            catch (err) { if (window.console) console.warn("rediģēšana", err); }
        });
        zimetGarumus();
    }
    karte.on("zoomend", redigesana);
    karte.on("draw:drawstart draw:deletestart measurestart", function() { BK.aiznemts = true; redigesana(); });
    karte.on("draw:drawstop draw:deletestop measurefinish", function() {
        setTimeout(function() { BK.aiznemts = false; redigesana(); }, 50); });
    karte.on("draw:deleted", function() { BK.pazinot(true); });
    karte.on("click", function() { if (!BK.aiznemts) BK.izveleties(null); BK.aizvertIzvelni(); });
    setTimeout(redigesana, 300);

    // Pastāvīgie uzraksti jāpārvieto, kad kartes izmērs mainās (iframe ielāde)
    function atjaunot() { fg.eachLayer(function(l) {
        if (l.getTooltip && l.getTooltip() && {{ this.pastavigi }}) { l.closeTooltip(); l.openTooltip(); } }); }
    karte.on("resize zoomend", atjaunot);
    setTimeout(atjaunot, 400);

    // ---- Malu garumi (kā LVM GEO) ----------------------------------------------------
    var garumi = L.layerGroup().addTo(karte);
    function zimetGarumus() {
        garumi.clearLayers();
        if (karte.getZoom() < 14) return;
        var rediget = karte.getZoom() >= REDIGET_NO && !BK.aiznemts;
        fg.eachLayer(function(l) {
            if (!(l instanceof L.Polyline)) return;
            var slegts = l instanceof L.Polygon;
            gredzeni(l.getLatLngs()).forEach(function(r) {
                var n = r.length;
                for (var i = 0; i < n; i++) {
                    if (!rediget) {   // rediģējot virsotnes zīmē pats rīks
                        L.circleMarker(r[i], {radius: 5, color: "#fff", weight: 2, fillColor: "#ff4b4b",
                                              fillOpacity: 1, interactive: false}).addTo(garumi);
                    }
                    if (!slegts && i === n - 1) break;
                    var a = r[i], b = r[(i + 1) % n], d = karte.distance(a, b);
                    if (d < 3) continue;
                    var px = karte.latLngToLayerPoint(a).distanceTo(karte.latLngToLayerPoint(b));
                    if (px < 45) continue;   // pārāk īsa mala šajā mērogā
                    L.marker(L.latLng((a.lat + b.lat) / 2, (a.lng + b.lng) / 2), {interactive: false,
                        icon: L.divIcon({className: "seg-garums", html: "<span>" + garumsTeksts(d) + "</span>",
                                         iconSize: null})}).addTo(garumi);
                }
            });
        });
    }
    karte.on("draw:created draw:edited draw:deleted draw:editvertex draw:editmove " +
             "draw:editresize draw:editstop draw:deletestop", function() { setTimeout(zimetGarumus, 0); });
    fg.on("edit", function() { setTimeout(zimetGarumus, 0); });
    setTimeout(zimetGarumus, 450);

    // ---- Darbības ar figūru (kopīgas labā taustiņa izvēlnei un rīkjoslai) ------------
    BK.dzest = function(l) {
        if (!l) return;
        if (l.editing) { try { l.editing.disable(); } catch (err) {} }
        fg.removeLayer(l);
        BK.izvelets = null; BK.aizvertIzvelni(); BK.atjaunotRikus(); zimetGarumus();
        BK.pazinot(true);
    };
    BK.statuss = function(l, s) {
        if (!l || !l.feature) return;
        l.feature.properties.statuss = s;
        l.feature.properties.krasa = STATUSI[s] || "#14b8a6";
        if (l.setStyle) l.setStyle(BK.izvelets === l ? izvelesStils(l) : bazesStils(l));
        BK.aizvertIzvelni();
        BK.pazinot(true);
    };
    BK.sadalit = function(l) {
        if (!l || !l.feature || !(l instanceof L.Polygon)) return;
        l.feature.properties.darbiba = "sadalit";
        BK.aizvertIzvelni();
        BK.pazinot(true);
    };
    BK.pietuvinat = function(l) {
        if (!l) return;
        if (l.getBounds) { karte.fitBounds(l.getBounds(), {padding: [40, 40], maxZoom: 18}); }
        else if (l.getLatLng) { karte.setView(l.getLatLng(), 18); }
        BK.aizvertIzvelni();
    };

    // ---- Labā taustiņa izvēlne -------------------------------------------------------
    var izv = L.DomUtil.create("div", "bk-izvelne", karte.getContainer());
    izv.style.display = "none";
    L.DomEvent.disableClickPropagation(izv);
    L.DomEvent.disableScrollPropagation(izv);
    L.DomEvent.on(izv, "contextmenu", L.DomEvent.preventDefault);
    BK.aizvertIzvelni = function() { izv.style.display = "none"; };
    function punkts(teksts, fn, papild) {
        var a = L.DomUtil.create("div", "bk-punkts" + (papild ? " " + papild : ""), izv);
        a.innerHTML = teksts;
        L.DomEvent.on(a, "click", function(ev) { L.DomEvent.stop(ev); fn(); });
        return a;
    }
    BK.izvelne = function(pt, l, papildPunkti) {
        izv.innerHTML = "";
        if (l) {
            var p = l.feature ? l.feature.properties : {};
            L.DomUtil.create("div", "bk-virsraksts", izv).innerHTML = p.nosaukums || "Objekts";
            if (l instanceof L.Polygon) {
                L.DomUtil.create("div", "bk-grupa", izv).innerHTML = "Statuss";
                Object.keys(STATUSI).forEach(function(s) {
                    punkts("<i style='background:" + STATUSI[s] + "'></i>" + s + (p.statuss === s ? " ✓" : ""),
                           function() { BK.statuss(l, s); }, p.statuss === s ? "bk-aktivs" : "");
                });
                L.DomUtil.create("div", "bk-atdalitajs", izv);
                punkts("✂️ Sadalīt ar atdalošo joslu", function() { BK.sadalit(l); });
            }
            punkts("🔍 Pietuvināt", function() { BK.pietuvinat(l); });
            L.DomUtil.create("div", "bk-atdalitajs", izv);
            punkts("🗑 Dzēst figūru", function() { BK.dzest(l); }, "bk-bistams");
        }
        (papildPunkti || []).forEach(function(x) { punkts(x[0], x[1]); });
        izv.style.display = "block";
        var c = karte.getSize();
        izv.style.left = Math.min(pt.x, c.x - izv.offsetWidth - 6) + "px";
        izv.style.top = Math.min(pt.y, c.y - izv.offsetHeight - 6) + "px";
    };
    document.addEventListener("keydown", function(ev) {
        if (ev.key === "Escape") { BK.aizvertIzvelni(); BK.izveleties(null); }
        if ((ev.key === "Delete" || ev.key === "Backspace") && BK.izvelets && !BK.aiznemts
            && !/input|textarea/i.test((ev.target || {}).tagName || "")) { BK.dzest(BK.izvelets); }
    });

    // ---- Rīkjosla kreisajā pusē: tās pašas darbības izvēlētajai figūrai ---------------
    var Riki = L.Control.extend({
        options: {position: "topleft"},
        onAdd: function() {
            var c = L.DomUtil.create("div", "leaflet-bar bk-riki");
            L.DomEvent.disableClickPropagation(c);
            function poga(ikona, nos, fn) {
                var a = L.DomUtil.create("a", "", c);
                a.href = "#"; a.innerHTML = ikona; a.title = nos;
                L.DomEvent.on(a, "click", function(ev) {
                    L.DomEvent.stop(ev);
                    if (!BK.izvelets) { BK.padoms(a); return; }
                    fn(BK.izvelets, a);
                });
                return a;
            }
            this.pogas = [
                poga("🏷", "Mainīt statusu (cirtes veidu)", function(l, a) {
                    var r = a.getBoundingClientRect(), k = karte.getContainer().getBoundingClientRect();
                    BK.izvelne(L.point(r.right - k.left + 6, r.top - k.top), l);
                }),
                poga("✂️", "Sadalīt kailcirti ar atdalošo joslu", function(l) { BK.sadalit(l); }),
                poga("🔍", "Pietuvināt izvēlētajai figūrai", function(l) { BK.pietuvinat(l); }),
                poga("🗑", "Dzēst izvēlēto figūru (arī Delete taustiņš)", function(l) { BK.dzest(l); }),
            ];
            BK.atjaunotRikus = function() {
                this.pogas.forEach(function(a) { a.classList.toggle("bk-izslegts", !BK.izvelets); });
            }.bind(this);
            BK.atjaunotRikus();
            return c;
        }
    });
    new Riki().addTo(karte);
    var padomsEl = L.DomUtil.create("div", "bk-padoms", karte.getContainer());
    padomsEl.style.display = "none";
    BK.padoms = function(a) {
        var r = a.getBoundingClientRect(), k = karte.getContainer().getBoundingClientRect();
        padomsEl.innerHTML = "Vispirms izvēlies figūru: klikšķini uz tās (vai labais taustiņš)";
        padomsEl.style.left = (r.right - k.left + 8) + "px";
        padomsEl.style.top = (r.top - k.top + 4) + "px";
        padomsEl.style.display = "block";
        setTimeout(function() { padomsEl.style.display = "none"; }, 2200);
    };
})();
{% endmacro %}
""")

_NOGABALI_JS = Template("""
{% macro script(this, kwargs) %}
(function() {
    var karte = {{ this._parent.get_name() }};
    function bk() { return window.BK || {}; }
    // Klikšķis uz nogabala -> rediģējama robežfigūra (tāda pati kā "Iezīmēt kā cirsmu")
    function izveidot(f) {
        var B = bk();
        if (!B.fg || B.aiznemts) return;
        var p = f.properties;
        B.pievienot(L.geoJSON(f.geometry).getLayers()[0],
                    {nosaukums: p.nosaukums_kartei, statuss: p.statuss_kartei});
    }
    var slanis = L.geoJSON({{ this.dati }}, {
        style: function(f) { return f.properties.stils; },
        onEachFeature: function(f, layer) {
            layer.bindTooltip(f.properties.uzraksts, {permanent: true, direction: "center",
                                                     className: "nog-etikete"});
            layer.on("mouseover", function() {
                if (bk().aiznemts) return;
                layer.setStyle({weight: 3.5, color: "#ffffff", opacity: 1});
                var el = layer.getElement && layer.getElement();
                if (el) el.classList.add("nog-spid");
            });
            layer.on("mouseout", function() {
                slanis.resetStyle(layer);
                var el = layer.getElement && layer.getElement();
                if (el) el.classList.remove("nog-spid");
            });
            layer.on("click", function(e) {
                if (bk().aiznemts) return;
                L.DomEvent.stopPropagation(e);
                izveidot(f);
            });
            layer.on("contextmenu", function(e) {
                L.DomEvent.stopPropagation(e);
                if (e.originalEvent) e.originalEvent.preventDefault();
                var B = bk();
                if (!B.izvelne || B.aiznemts) return;
                B.izveleties(null);
                B.izvelne(e.containerPoint, null, [
                    ["➕ Iezīmēt nogabalu kā figūru", function() { B.aizvertIzvelni(); izveidot(f); }],
                    ["ℹ️ Nogabala dati", function() {
                        B.aizvertIzvelni();
                        L.popup({maxWidth: 360}).setLatLng(e.latlng).setContent(f.properties.popup).openOn(karte);
                    }],
                ]);
            });
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

_ZV_JS = Template("""
{% macro script(this, kwargs) %}
(function() {
    var karte = {{ this._parent.get_name() }};
    var STILS = {color: "#facc15", weight: 3.5, dashArray: "8 5", fill: false, opacity: 1};
    L.geoJSON({{ this.dati }}, {
        style: function() { return STILS; },
        onEachFeature: function(f, layer) {
            layer.bindTooltip(f.properties.tooltip, {sticky: true});
            layer.on("mouseover", function() {
                if ((window.BK || {}).aiznemts) return;
                layer.setStyle({weight: 6, dashArray: null});
                var el = layer.getElement && layer.getElement(); if (el) el.classList.add("nog-spid");
            });
            layer.on("mouseout", function() {
                layer.setStyle(STILS);
                var el = layer.getElement && layer.getElement(); if (el) el.classList.remove("nog-spid");
            });
            layer.on("click", function(e) {
                var B = window.BK || {};
                if (!B.fg || B.aiznemts) return;
                L.DomEvent.stopPropagation(e);
                B.pievienot(L.geoJSON(f.geometry).getLayers()[0],
                            {nosaukums: "ZV " + f.properties.kadastrs, statuss: "Kailcirte"});
            });
        }
    }).addTo(karte);
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
  d.handlers.polyline.tooltip.end = "Klikšķini uz pēdējā punkta, lai pabeigtu, vai uz pirmā — lai noslēgtu laukumu";
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

  // Līnijas rīks: klikšķis atpakaļ uz pirmā punkta noslēdz figūru -> laukums (kā LVM GEO)
  if (!L.Draw.Polyline.prototype._aizversanaIelikta) {
    L.Draw.Polyline.prototype._aizversanaIelikta = true;
    var pievienot = L.Draw.Polyline.prototype.addVertex;
    L.Draw.Polyline.prototype.addVertex = function(latlng) {
      if (this.type === "polyline" && this._markers && this._markers.length >= 3) {
        var a = this._map.latLngToLayerPoint(this._markers[0].getLatLng());
        var b = this._map.latLngToLayerPoint(latlng);
        if (a.distanceTo(b) < 14) { this._aizvert = true; this.completeShape(); return; }
      }
      return pievienot.call(this, latlng);
    };
    // Klikšķis tieši uz pirmā punkta (marķieris pārtver klikšķi, addVertex netiek izsaukts)
    var finisaApstr = L.Draw.Polyline.prototype._updateFinishHandler;
    L.Draw.Polyline.prototype._updateFinishHandler = function() {
      finisaApstr.call(this);
      if (this.type === "polyline" && this._markers && this._markers.length >= 3) {
        if (!this._aizvertKlik) {
          this._aizvertKlik = function() { this._aizvert = true; this.completeShape(); };
        }
        this._markers[0].off("click", this._aizvertKlik, this).on("click", this._aizvertKlik, this);
      }
    };
    var izveidot = L.Draw.Polyline.prototype._fireCreatedEvent;
    L.Draw.Polyline.prototype._fireCreatedEvent = function() {
      if (this.type === "polyline" && this._aizvert) {
        this._aizvert = false;
        var laukums = new L.Polygon(this._poly.getLatLngs(), L.extend({}, this.options.shapeOptions, {fill: true}));
        L.Draw.Feature.prototype._fireCreatedEvent.call(this, laukums);
        return;
      }
      return izveidot.call(this);
    };
  }
}
{% endmacro %}
""")

_STILS = """
<style>
.karte-etikete {background: rgba(255,255,255,.85); border: 0; box-shadow: none;
  font: 600 11px/1.2 system-ui, sans-serif; padding: 1px 4px; color: #111;}
.karte-etikete:before {display: none;}
.leaflet-draw-tooltip {font-size: 12px;}
.leaflet-editing-icon, .karte-virsotne {border-radius: 50% !important; background: #ff4b4b !important;
  border: 2px solid #fff !important; box-shadow: 0 0 0 1px rgba(0,0,0,.35);
  width: 11px !important; height: 11px !important; margin-left: -5.5px !important; margin-top: -5.5px !important;
  cursor: move;}
.leaflet-editing-icon.leaflet-middle-icon {opacity: .5 !important; width: 8px !important; height: 8px !important;
  margin-left: -4px !important; margin-top: -4px !important; background: #fff !important; cursor: copy;}
.leaflet-draw-guide-dash {background-color: #ff4b4b !important; border-radius: 50%;}
.seg-garums span {background: rgba(17,24,39,.82); color: #fff; font: 600 11px/1 system-ui, sans-serif;
  padding: 2px 4px; border-radius: 3px; white-space: nowrap; transform: translate(-50%, -50%);
  display: inline-block;}
.nog-etikete {background: transparent; border: 0; box-shadow: none; color: #fff;
  font: 700 11px/1 system-ui, sans-serif; text-shadow: 0 0 3px #000, 0 0 2px #000; padding: 0;}
.nog-etikete:before {display: none;}
.nog-popup td {padding: 1px 6px 1px 0; vertical-align: top; font-size: 12px;}
.nog-spid {filter: drop-shadow(0 0 4px rgba(255,255,255,.9)) drop-shadow(0 0 9px rgba(255,255,255,.55));
  cursor: pointer;}
.bk-izvelne {position: absolute; z-index: 1000; min-width: 210px; background: #fff; border-radius: 8px;
  box-shadow: 0 6px 24px rgba(0,0,0,.28); padding: 4px 0; font: 13px/1.3 system-ui, sans-serif; color: #111;}
.bk-virsraksts {font-weight: 700; padding: 6px 12px 4px; border-bottom: 1px solid #eee; margin-bottom: 2px;
  max-width: 260px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;}
.bk-grupa {font-size: 11px; color: #6b7280; padding: 4px 12px 2px; text-transform: uppercase; letter-spacing: .03em;}
.bk-punkts {padding: 5px 12px; cursor: pointer; white-space: nowrap;}
.bk-punkts:hover {background: #f3f4f6;}
.bk-punkts i {display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-right: 8px;
  vertical-align: -1px;}
.bk-aktivs {font-weight: 600;}
.bk-bistams {color: #dc2626;}
.bk-atdalitajs {height: 1px; background: #eee; margin: 3px 0;}
.bk-riki a {font-size: 15px; line-height: 30px !important;}
.bk-riki a.bk-izslegts {opacity: .4;}
.bk-padoms {position: absolute; z-index: 1000; background: rgba(17,24,39,.9); color: #fff;
  font: 12px system-ui, sans-serif; padding: 5px 8px; border-radius: 4px; white-space: nowrap;}
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
        p = m["garums_m"]
        mers = f"{m['platiba_ha']:.2f} ha · " + (f"{p:.0f} m" if p < 1000 else f"{p / 1000:.2f} km")
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
                   ("Meža tips", n.meza_tips or "—"),
                   ("Šķērslaukums", f"{n.skerslaukums:g} m²/ha" if n.skerslaukums else "—"),
                   ("Krāja", f"{n.kraja_m3_ha:.0f} m³/ha" if n.kraja_m3_ha else "—")]
    if apz in uzmerits:
        rindas.append(("Uzmērīts kartē", f"<b>{uzmerits[apz]:.2f} ha</b>"))
    if v0 is not None:
        rindas.append(("Sistēmas lēmums", f"<b>{v0.cirtes_nosaukums}</b>"
                       + f"<br><small>{v0.pamatojums}</small>"))
    if v is not None and v.cirtams and apz in uzmerits:
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
        if apz in uzmerits and v0 is not None and v0.cirtams:
            stils = {"color": "#ffffff", "weight": 2.5, "fillColor": "#e5484d", "fillOpacity": 0.12}
        elif apz in uzmerits:     # atzīmēts, bet neatbilst kailcirtei
            stils = {"color": "#f59e0b", "weight": 2.5, "dashArray": "2 4", "fillOpacity": 0.05,
                     "fillColor": "#f59e0b"}
        elif v0 is not None and v0.cirtes_veids == "kopsana":
            stils = {"color": "#f59e0b", "weight": 2.5, "dashArray": "6 4", "fillOpacity": 0.05,
                     "fillColor": "#f59e0b"}
        elif v0 is not None and v0.atlauta_kailcirte:
            stils = {"color": "#4ade80", "weight": 2.5, "dashArray": "6 4", "fillOpacity": 0.05,
                     "fillColor": "#4ade80"}
        else:
            stils = {"color": "#ffffff", "weight": 1.2, "opacity": 0.9, "fillOpacity": 0.02}
        statuss = "Kopšanas cirte" if (v0 is not None and v0.cirtes_veids == "kopsana") else CIRSMAS_STATUSS
        features.append({"type": "Feature", "geometry": g, "properties": {
            "stils": stils, "uzraksts": str(n.nr), "popup": _nog_popup(n, apz),
            "nosaukums_kartei": ("Kopšana " if statuss != CIRSMAS_STATUSS else "Cirsma ") + apz,
            "statuss_kartei": statuss, "krasa_kartei": STATUSI[statuss]}})
    return {"type": "FeatureCollection", "features": features}


def kartes_ievade() -> dict:
    """Viss, no kā atkarīgs kartes HTML (momentuzņēmums)."""
    return {
        "skats": ss.karte_skats_html, "pietuvinat": ss.karte_pietuvinat_html,
        "fokuss": ss.get("karte_fokuss_html"), "objekti": [dict(o) for o in objekti],
        "nogabali": json.dumps(_nogabalu_slanis(), ensure_ascii=False) if (inv and nog_robezas) else None,
        "zv": [dict(z) for z in ss.karte_zv], "markieris": ss.get("karte_markieris"),
    }


def uzbuvet_karti(iev: dict) -> folium.Map:
    objekti = iev["objekti"]
    skats = iev["skats"] or LATVIJA
    m = folium.Map(location=skats["center"], zoom_start=skats["zoom"], tiles=None,
                   control_scale=True, max_zoom=21, prefer_canvas=False)
    _wms(PAMATKARTES[pamatkarte], 1.0, overlay=False).add_to(m)
    for nos in parklajumi:
        _wms(PARKLAJUMI[nos], caurspidigums, overlay=True).add_to(m)

    m.get_root().header.add_child(folium.Element(_STILS))
    if iev["zv"]:
        zv_fc = {"type": "FeatureCollection", "features": [
            {"type": "Feature", "geometry": z["geometry"], "properties": {
                "kadastrs": z["kadastrs"],
                "tooltip": f"Zemes vienība {z['kadastrs']}"
                           + (f" · {z['platiba_ha']:.2f} ha" if z["platiba_ha"] else "")
                           + " · klikšķis = iezīmēt visu ZV kā figūru"}}
            for z in iev["zv"]]}
        m.add_child(_elements(_ZV_JS, dati=json.dumps(zv_fc, ensure_ascii=False)))
    if iev["nogabali"]:
        m.add_child(_elements(_NOGABALI_JS, dati=iev["nogabali"]))
    fg = folium.FeatureGroup(name="Objekti", control=False).add_to(m)
    dati = uz_geojson(objekti, ar_merijumiem=False)
    for f, o in zip(dati["features"], objekti):
        f["properties"]["etikete"] = _etikete(o)
    m.add_child(_elements(_OBJEKTI_JS, dati=json.dumps(dati, ensure_ascii=False),
                          fg_el=fg, statusi=json.dumps(STATUSI, ensure_ascii=False),
                          pastavigi="true" if uzraksti else "false"))
    m.add_child(_elements(_LATVISKI_JS))
    plugins.Draw(
        feature_group=fg, position="topleft", show_geometry_on_click=False,
        draw_options={
            "polygon": {"allowIntersection": False, "showArea": True, "metric": ["ha", "m"],
                        "precision": {"ha": 2, "m": 0},
                        "shapeOptions": {"color": AKCENTS, "weight": 3.5, "opacity": 1}},
            "polyline": {"metric": True,
                         "shapeOptions": {"color": AKCENTS, "weight": 3.5, "opacity": 1}},
            "rectangle": {"showArea": True, "metric": ["ha", "m"],
                          "shapeOptions": {"color": AKCENTS, "weight": 3.5, "opacity": 1}},
            "circle": False, "circlemarker": False, "marker": True,
        },
        # "edit": True (bool) Leaflet.draw 1.0.x nesaprot -> virsotnes netiek rādītas; jādod objekts
        # Virsotnes velk bez rīka (tuvinot ≥ 15) — labošanas poga nav vajadzīga
        edit_options={"edit": False, "remove": True, "poly": {"allowIntersection": False}},
    ).add_to(m)
    plugins.MeasureControl(position="topleft", primary_length_unit="meters",
                           secondary_length_unit="kilometers", primary_area_unit="hectares",
                           secondary_area_unit="sqmeters", localization="en",
                           active_color=AKCENTS, completed_color=AKCENTS).add_to(m)
    plugins.Fullscreen(position="topright", title="Pilnekrāns", title_cancel="Iziet").add_to(m)
    plugins.LocateControl(position="topright", strings={"title": "Mana atrašanās vieta"},
                          flyTo=True, keepCurrentZoomLevel=False).add_to(m)
    plugins.MousePosition(position="bottomleft", separator=" , ", prefix="WGS84:",
                          num_digits=6).add_to(m)
    if iev["markieris"]:
        folium.Marker(iev["markieris"], tooltip="Meklētā vieta",
                      icon=folium.Icon(color="red", icon="crosshairs", prefix="fa")).add_to(m)
    if iev["pietuvinat"] and (objekti or iev["zv"]):
        fokuss = iev["fokuss"]
        merkis = ([z for z in iev["zv"] if z["kadastrs"] in fokuss] if fokuss else []) \
            or objekti + iev["zv"]
        m.fit_bounds(robezas(merkis), padding=(30, 30), max_zoom=17)
    return m


@st.fragment
def kartes_fragments() -> None:
    # Karti būvē no jauna tikai, ja mainās kas ārpus kartes (imports, tabula, slāņi, zemes vienība…).
    # Izmaiņas, kas veiktas pašā kartē, tajā jau ir — pārzīmējot iframe pārlādētos un lapa "noraustītos".
    atsl = (ss.karte_versija, pamatkarte, tuple(parklajumi), caurspidigums, uzraksti, aktiva_zv,
            inv.zemes_vieniba if inv else None, len(nog_robezas), tuple(z["kadastrs"] for z in ss.karte_zv),
            str(ss.get("karte_markieris")))
    if ss.get("karte_html_atsl") != atsl or ss.get("karte_html_ievade") is None:
        ss.karte_html_ievade = kartes_ievade()
        ss.karte_html_atsl = atsl
    # Tā pati ievade -> identisks HTML -> pārlūks karti nepārlādē
    karte = uzbuvet_karti(ss.karte_html_ievade)
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
        # Kartes izvēlnes darbības: "Sadalīt ar atdalošo joslu"
        izpilditi = []
        for o in jauni:
            if o.pop("darbiba", None) == "sadalit":
                dalas = sadalit_objektu(o, inv, nog_robezas, nt)
                if len(dalas) == 1:
                    st.toast(f"{o['nosaukums']} nepārsniedz max kailcirtes platību — nav ko dalīt", icon="ℹ️")
                izpilditi += dalas
            else:
                izpilditi.append(o)
        ss.karte_objekti = izpilditi
        ss.karte_tabula_v = ss.get("karte_tabula_v", 0) + 1
        if len(izpilditi) != len(jauni):
            _mainits()           # sadale izveido jaunas figūras — tās jāuzzīmē
        st.rerun(scope="app")


k1, k2, k3 = st.columns([1, 1, 4])
if k1.button("🔍 Pietuvināt objektiem", disabled=not (objekti or ss.karte_zv), use_container_width=True):
    ss.karte_fokuss = ss.karte_fokuss_html = None
    _mainits(pietuvinat=True)
if k2.button("🗑 Notīrīt visu", disabled=not objekti, use_container_width=True):
    ss.karte_objekti, ss.karte_importeti = [], set()
    _mainits()
    st.rerun()
k3.caption("**Klikšķis uz nogabala** — iezīmē to kā figūru · **velc virsotnes** (tuvinot līdz 16+) — robeža un "
           "platība mainās · **labais taustiņš** uz figūras — statuss, sadalīt ar joslu, dzēst (tās pašas "
           "darbības ir kreisajā rīkjoslā: 🏷 ✂️ 🔍 🗑; Delete dzēš izvēlēto). Zīmēšana: ⬠ ╱ ▭ 📍, 📏 mērījums.")

kartes_fragments()
objekti = ss.karte_objekti

# --- Tūlītējs rezultāts zem kartes ------------------------------------------------
if objekti:
    kc = [o for o in objekti if o.get("statuss") == CIRSMAS_STATUSS and ir_laukums(o)]
    kc = [o for o in objekti if o.get("statuss") in ("Kailcirte", "Kopšanas cirte", "Izlases cirte")
          and ir_laukums(o)]
    if not kc:
        st.info("Uzzīmētajiem laukumiem nav cirtes statusa (Kailcirte / Kopšanas cirte / Izlases cirte) — "
                "tabulā zemāk nomaini statusu, lai laukums nonāktu aprēķinā.")
    elif inv is None:
        st.warning("Aprēķinam vajag nogabalu datus: sānjoslā atrodi zemes vienību pēc kadastra "
                   "apzīmējuma vai ielādē inventarizācijas PDF.")
    elif not uzmerits:
        st.warning("Iezīmētā cirsma nepārklājas ne ar vienu šīs zemes vienības nogabalu"
                   + ("" if nog_robezas else " (nogabalu robežas nav zināmas — tabulā kolonnā "
                      "**Nogabals** piesaisti laukumu nogabalam)") + ".")
    elif kartes_fin is not None:
        iezimets = kopplatiba_ha(kc)
        uz_nog = sum(uzmerits.values())
        with st.container(border=True):
            r1, r2, r3, r4 = st.columns(4)
            r1.metric("Iezīmētā cirsma", f"{iezimets:.2f} ha",
                      help="Visu kailcirtes laukumu platība (LKS-92), pārklāšanās netiek skaitītas divreiz")
            r2.metric("Cērtamais apjoms", f"{kartes_fin.kopejais_m3:,.0f} m³")
            r3.metric("Max iegādes summa", f"{kartes_fin.max_iegades_summa:,.0f} EUR")
            r4.metric("Cena", f"{kartes_fin.cena_eur_m3:.2f} €/m³")
            st.caption("Pa nogabaliem: " + " · ".join(f"**{k}** {v:.2f} ha" for k, v in uzmerits.items()))
            if iezimets - uz_nog >= 0.01:
                st.caption(f"ℹ️ No iezīmētajiem {iezimets:.2f} ha uz meža nogabaliem ir {uz_nog:.2f} ha; "
                           f"{iezimets - uz_nog:.2f} ha atrodas ārpus nogabaliem (ceļš, lauce, cita zeme vai "
                           "kaimiņu zeme) un netiek vērtēti.")
            for b in blakus_bridinajumi:
                st.warning(b)
            neatb = [k for k in uzmerits if sakotnejie.get(k) is not None and not sakotnejie[k].cirtams]
            if neatb:
                st.caption("⚠ Kailcirtei neatbilst: " + ", ".join(neatb)
                           + (" — iekļauti aprēķinā." if ss.karte_visi else " — aprēķinā nav iekļauti."))

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
            "G m²/ha": n.skerslaukums, "Meža tips": n.meza_tips,
            "Sistēmas lēmums": v0.cirtes_nosaukums if v0 else "",
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
    cirtami = [r["Nogabals"] for r in nog_rindas if r["Sistēmas lēmums"] in ("Kailcirte", "Kopšanas cirte")]

    def _iezimet_cirtamos() -> None:
        jau = set(uzmeritas_visas(ss.karte_objekti, nog_robezas))
        ss.karte_objekti = ss.karte_objekti + automatiskas_cirsmas(inv, nog_robezas, nt, izlaist=jau)
        _mainits()

    b2.button(f"🌲 Iezīmēt visus cērtamos ({len(cirtami)})", disabled=not (cirtami and nog_robezas),
              on_click=_iezimet_cirtamos, use_container_width=True,
              help="Kailcirtes un kopšanas poligoni pēc nogabalu robežām; kailcirti virs max platības "
                   "sadala ar atdalošo joslu. Jau iezīmētos nogabalus izlaiž.")
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
    atsl = f"karte_tabula_{ss.karte_versija}_{ss.get('karte_tabula_v', 0)}"
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
            "Statuss": st.column_config.SelectboxColumn(
                options=list(STATUSI), required=True,
                help="Nosaka krāsu un cirtes veidu: Kailcirte / Kopšanas cirte / Izlases cirte laukumi "
                     "nonāk aprēķinā; Atdalošā josla, Neiekļaut u.c. — ne."),
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
ss.karte_aprekins = None
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
        t1, t2 = st.columns(2)
        tikai = t1.toggle("Cirsmā tikai kartē atzīmētie nogabali", key="karte_tikai",
                          help="Ieslēgts: nogabali bez kailcirtes laukuma kartē netiek cirsti. "
                               "Izslēgts: pārējiem paliek sistēmas lēmums pēc kailcirtes kritērijiem.")
        visi = t2.toggle("Iekļaut arī kailcirtei neatbilstošos", key="karte_visi",
                         help="Ieslēgts: viss, ko iezīmē kartē, nonāk aprēķinā (neatbilstošie atzīmēti ar ⚠). "
                              "Izslēgts: jaunaudzes u.c. kailcirtei neatbilstoši nogabali netiek iekļauti.")
        s = salidzinat(inv, objekti, esosie, tikai_atzimetie=tikai, nogabalu_robezas=nog_robezas,
                       ieklaut_neatbilstosos=visi, nt=nt, **aprekina_param)
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
        st.caption("Cenas un izdevumi — no Cenrāža (kā Meža inventarizācijas sadaļā). Kailcirte: krāja "
                   "m³/ha × uzmērītā platība; kopšana/izlases: izcērtamais šķērslaukums × veidaugstums × "
                   "platība. Laukuma statuss kartē nosaka cirtes veidu.")

        jaunie = labojumi_no_kartes(inv, objekti, esosie, tikai, nog_robezas, visi)
        v_pec = novertet_ar_labojumiem(inv.nogabali, jaunie, nt)
        # Momentuzņēmums kalkulatoram ("Aprēķins no kartes" Meža inventarizācijas sadaļā)
        zimejums = json.dumps([[o["geometry"], o["statuss"], o.get("nogabals")] for o in objekti],
                              sort_keys=True) + str(tikai) + str(visi) + (inv.zemes_vieniba or "") + str(ir_pdf)
        ss.karte_aprekins = {
            "id": "karte_" + hashlib.sha1(zimejums.encode()).hexdigest()[:12],
            "inv": inv, "labojumi": jaunie, "uzmerits": dict(uzmerits),
            "objekti": list(objekti), "kadastrs": inv.zemes_vieniba or aktiva_zv,
            "robezas": nog_robezas,
            "apraksts": f"Zemes vienība {inv.zemes_vieniba or aktiva_zv or '—'} · dati: "
                        + (f"PDF {ss.inv_pdf['nosaukums']}" if ir_pdf else "Meža valsts reģistrs"),
        }

        def _uz_kalkulatoru() -> None:
            ss.mezs_uz_karti = True

        if st.button("🧮 Atvērt kalkulatorā (cenas, sortimenti, atskaites)", type="primary",
                     on_click=_uz_kalkulatoru, use_container_width=True):
            st.switch_page("views/mezs.py")
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
