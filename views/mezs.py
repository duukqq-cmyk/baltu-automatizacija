"""Modulis: meža inventarizācijas analīze (cirsmas vērtības aprēķins)."""
from __future__ import annotations

import copy
import hashlib
import os
import tempfile

import pandas as pd
import streamlit as st

from cirsma.parser import parse_inventory_pdf
from cirsma.labojumi import (
    BONITATES, Labojums, labojumu_izmainas, nogabala_atslega, novertet_ar_labojumiem,
)
from cirsma.cirtes import CIRTES_NOSAUKUMI, NOSAUKUMS_UZ_VEIDU
from cirsma.sortiment import aprekinat, vertejuma_apjoms
from cirsma.report import (
    cirsmas_rindas, teksta_atskaite, excel_atskaite, nog_nosaukums, atrast_apjomu,
)
from cirsma.formula import SUGU_NOSAUKUMI
from cirsma import priekvertejums as pv
from cirsma.pdf_atskaite import priekvertejuma_pdf
from views.kopigi import aktivais_cenradis, cenradis_statuss_sanjosla, glabatuve, lietotajs

@st.cache_data(show_spinner="Nolasa PDF…")
def _nolasit(pdf_baiti: bytes):
    """PDF nolasīšana (kešota pēc faila satura — labojumi PDF nenolasa no jauna)."""
    return parse_inventory_pdf(_saglabat_pdf(pdf_baiti))


def _saglabat_pdf(pdf_baiti: bytes) -> str:
    cels = os.path.join(tempfile.gettempdir(), f"inv_{hashlib.sha1(pdf_baiti).hexdigest()}.pdf")
    if not os.path.exists(cels):
        with open(cels, "wb") as f:
            f.write(pdf_baiti)
    return cels


_KOLONNA_LAUKS = {
    "Platība ha": "platiba_ha", "Krāja m³/ha": "kraja_m3_ha", "Bonitāte": "bonitate",
    "Vecums": "vecums", "Cirtes veids": "cirtes_veids", "Apjoms m³": "apjoms_m3",
}


def _saglabat_labojumus(redaktora_atslega: str, atslegas: list[str]) -> None:
    """data_editor izmaiņas -> Labojums sesijā; pēc tam tabula tiek uzzīmēta no jauna."""
    izmainas = st.session_state[redaktora_atslega].get("edited_rows", {})
    labojumi = st.session_state.labojumi
    for rinda, kolonnas in izmainas.items():
        atsl = atslegas[int(rinda)]
        lab = labojumi.setdefault(atsl, Labojums())
        for kolonna, vertiba in kolonnas.items():
            lauks = _KOLONNA_LAUKS.get(kolonna)
            if lauks is None:
                continue
            if isinstance(vertiba, float) and vertiba != vertiba:  # NaN = dzēsta šūna
                vertiba = None
            if lauks == "cirtes_veids":
                vertiba = NOSAUKUMS_UZ_VEIDU.get(vertiba) if vertiba else None  # None -> automātiski
                lab.kailcirte = None
            setattr(lab, lauks, vertiba)  # None -> atpakaļ uz PDF vērtību
            if lauks in ("platiba_ha", "kraja_m3_ha"):
                lab.apjoms_m3 = None  # apjoms jāpārrēķina no jaunās platības/krājas
        if lab.tukss():
            labojumi.pop(atsl, None)
    st.session_state.tabulas_versija += 1


st.title(":material/forest: Cirsmas vērtības aprēķins")
from views.ikonas import AVOTS_KARTE, AVOTS_NOVERTEJUMS, AVOTS_PDF  # noqa: E402
if st.session_state.pop("mezs_uz_karti", False):
    st.session_state.mezs_avots = AVOTS_KARTE
st.session_state.setdefault("mezs_avots", AVOTS_PDF)
avots = st.segmented_control("Datu avots", [AVOTS_PDF, AVOTS_KARTE, AVOTS_NOVERTEJUMS],
                             key="mezs_avots", label_visibility="collapsed") or AVOTS_PDF
if avots == AVOTS_NOVERTEJUMS:
    # Atsevišķs summu kalkulators — sānjoslas cenas un inventarizācijas aprēķins te nav vajadzīgi
    from views.novertejums import render as _novertejums_render
    _novertejums_render()
    st.stop()
if avots == AVOTS_PDF:
    st.caption(
        "Augšupielādē nogabalu raksturojošo rādītāju PDF (VMD vai gabali.lv — formātu atpazīst "
        "automātiski). Sistēma katram nogabalam nosaka cirtes veidu — kailcirte (platība pēc meža tipa: "
        "sausieņos ≤ 5 ha, citur ≤ 2 ha), kopšanas cirte (pēc šķērslaukuma) vai necirst; izlases cirti "
        "izvēlies kolonnā **Cirtes veids**. Aprēķina apjomu, sortimentus, iegādes summu un atzīmē riskus."
    )
else:
    st.caption(
        "Aprēķins pēc kartē uzmērītās cirsmas: nogabalu dati no Meža valsts reģistra (vai PDF), "
        "platības — no kartes. Cenas un izdevumus maini sānjoslā; nogabalu tabulā vari vēl labot vērtības."
    )

# --- Cenrādis (kopīgs visām sadaļām; maina lapā "Cenrādis") -------------------
cenradis = aktivais_cenradis()
cenradis_statuss_sanjosla()

# --- Dati: no kartes ----------------------------------------------------------
if avots == AVOTS_KARTE:
    ka = st.session_state.get("karte_aprekins")
    if not ka or not ka.get("uzmerits"):
        st.info("Kartē vēl nav uzmērītas cirsmas. Atrodi zemes vienību pēc kadastra, uzzīmē vai "
                "pārzīmē cirsmu — tad aprēķins parādīsies šeit.")
        if st.button(":material/map: Atvērt karti", type="primary"):
            st.switch_page("views/karte.py")
        st.stop()
    inv = ka["inv"]
    cels = os.path.join(tempfile.gettempdir(), f"karte_{ka['id']}.pdf")
    st.caption(f":material/map: {ka['apraksts']} · uzmērīts kartē: " + ", ".join(
        f"{k} — {v:.2f} ha" for k, v in ka["uzmerits"].items()))
    faila_id = ka["id"]
    if st.session_state.get("faila_id") != faila_id:
        # Jauni kartes mērījumi -> labojumi no kartes (tabulā tos var labot tālāk)
        st.session_state.faila_id = faila_id
        st.session_state.pop("priekvertejums", None)
        if st.session_state.get("priekvertejums_gaida"):   # atvērts no Saglabātie caur karti
            st.session_state.priekvertejums = st.session_state.pop("priekvertejums_gaida")
        st.session_state.labojumi = copy.deepcopy(ka["labojumi"])
        st.session_state.tabulas_versija = st.session_state.get("tabulas_versija", 0) + 1

# --- PDF augšupielāde ------------------------------------------------------
fails = st.file_uploader("Meža inventarizācijas PDF", type="pdf") if avots == AVOTS_PDF else None
if avots == AVOTS_KARTE:
    pass
elif fails:
    # Kopīgs ar Kartes sadaļu — tur var piesaistīt kartes laukumus šī PDF nogabaliem
    st.session_state.inv_pdf = {"baiti": fails.getvalue(), "nosaukums": fails.name}
elif st.session_state.get("inv_pdf"):
    st.caption(f"Izmanto iepriekš ielādēto failu: **{st.session_state.inv_pdf['nosaukums']}**")
else:
    st.info(":material/upload: Augšupielādē PDF failu, lai sāktu (paraugs: `dati/Nogabalu_raksturojosie_raditaji_64560020029.pdf`).")
    st.stop()

if avots == AVOTS_PDF:
    pdf_baiti = st.session_state.inv_pdf["baiti"]
    cels = _saglabat_pdf(pdf_baiti)

    try:
        inv = _nolasit(pdf_baiti)
    except Exception as e:  # noqa: BLE001
        st.error(f"Neizdevās apstrādāt failu: {e}")
        st.stop()

    # Labojumi dzīvo sesijā; jauns fails -> labojumi no jauna
    faila_id = hashlib.sha1(pdf_baiti).hexdigest()
    if st.session_state.get("faila_id") != faila_id:
        st.session_state.faila_id = faila_id
        st.session_state.labojumi = {}
        st.session_state.tabulas_versija = 0
        st.session_state.pop("priekvertejums", None)
labojumi: dict[str, Labojums] = st.session_state.labojumi

try:
    vertejumi = novertet_ar_labojumiem(inv.nogabali, labojumi, cenradis.noteikumi)
    fin = aprekinat(vertejumi, matricas=cenradis.matricas, izdevumi_pa_veidiem=cenradis.izdevumi,
                    pelnas_rezerve=cenradis.pelnas_rezerve)
    pelna = cenradis.pelnas_rezerve
except Exception as e:  # noqa: BLE001
    st.error(f"Neizdevās aprēķināt: {e}")
    st.stop()

# --- Rezultāti -------------------------------------------------------------
cirt = [v for v in vertejumi if v.cirtams]
riski = [v for v in cirt if any(b.startswith("⚠") for b in v.bridinajumi)]
laboti = [v for v in vertejumi if any(b.startswith("✎") for b in v.bridinajumi)]
gabali = inv.avots == "gabali.lv"
st.caption(
    f"Datu avots: **{inv.avots}** · NĪ {inv.ipasums or '—'} · {len(inv.nogabali)} nogabali"
    + (" · apjomi pēc faktiskās sugu krājas" if any(a.metode == "sugu tabula" for a in fin.apjomi) else "")
)
c1, c2, c3, c4 = st.columns(4)
c1.metric("Cērtamais apjoms", f"{fin.kopejais_m3:,.0f} m³")
c2.metric("Ieņēmumi", f"{fin.ienemumi_kopa:,.0f} EUR")
c3.metric("Max iegādes summa", f"{fin.max_iegades_summa:,.0f} EUR")
c4.metric("Cena", f"{fin.cena_eur_m3:.2f} EUR/m³")
if fin.pa_veidiem:
    st.caption(" · ".join(
        f"**{CIRTES_NOSAUKUMI[k]}**: {sum(1 for v in cirt if v.cirtes_veids == k)} nog., "
        f"{d['m3']:,.0f} m³, segums {d['segums']:,.0f} EUR".replace(",", " ")
        for k, d in fin.pa_veidiem.items()))

if riski:
    st.warning(
        f"⚠ {len(riski)} no {len(cirt)} cērtamajiem nogabaliem ir riska karogi — "
        "pirms piedāvājuma pārbaudi tos (skat. sadaļu zemāk)."
    )

st.subheader("Nogabalu vērtējums")

rindas, atslegas = [], []
for v in vertejumi:
    n = v.nogabals
    apjoms, _, _ = vertejuma_apjoms(v)
    karogi = "".join(z for z in ("✎", "⚠", "ℹ") if any(b.startswith(z) for b in v.bridinajumi))
    rinda = {
        "Nog.": nog_nosaukums(inv, n).removesuffix(".nog"),
        "Platība ha": n.platiba_ha,
        "Krāja m³/ha": n.kraja_m3_ha,
        "Formula": n.formula,
        "Bonitāte": n.bonitate,
        "Vecums": n.vecums,
        "Meža tips": n.meza_tips,
        "Augst. m": n.vid_augstums,
        "G m²/ha": n.skerslaukums,
        "Valdošā suga": SUGU_NOSAUKUMI.get(v.valdosa_suga, v.valdosa_suga),
        "Cirtes veids": v.cirtes_nosaukums,
        "Cērt. ha": v.cirsmas_platiba or None,
        "Apjoms m³": apjoms,
        "Karogi": karogi,
    }
    if gabali:
        rinda["Info no PDF"] = " · ".join(n.pdf_apraksts)
    rinda["Pamatojums"] = v.pamatojums
    rindas.append(rinda)
    atslegas.append(nogabala_atslega(v.indekss))

redaktora_atslega = f"nogabali_{faila_id[:8]}_{st.session_state.tabulas_versija}"
tabula = pd.DataFrame(rindas)
for kol in ("Augst. m", "G m²/ha", "Cērt. ha", "Krāja m³/ha", "Vecums"):
    tabula[kol] = pd.to_numeric(tabula[kol], errors="coerce")
st.data_editor(
    tabula,
    key=redaktora_atslega,
    on_change=_saglabat_labojumus,
    args=(redaktora_atslega, atslegas),
    hide_index=True,
    use_container_width=True,
    disabled=["Nog.", "Formula", "Meža tips", "Augst. m", "G m²/ha", "Valdošā suga", "Cērt. ha",
              "Karogi", "Info no PDF", "Pamatojums"],
    column_config={
        "Platība ha": st.column_config.NumberColumn(
            min_value=0.0, step=0.01, format="%.2f",
            help="Mainot pārrēķinās apjoms. Notīri šūnu, lai atjaunotu PDF vērtību."),
        "Krāja m³/ha": st.column_config.NumberColumn(
            min_value=0.0, step=1.0, format="%.0f",
            help="Mainot pārrēķinās apjoms. Notīri šūnu, lai atjaunotu PDF vērtību."),
        "Bonitāte": st.column_config.SelectboxColumn(
            options=BONITATES,
            help="Mainot pārvērtē kailcirtes atbilstību. Notīri šūnu, lai atjaunotu PDF vērtību."),
        "Vecums": st.column_config.NumberColumn(
            min_value=0, max_value=300, step=1, format="%d",
            help="Mainot pārvērtē kailcirtes atbilstību. Notīri šūnu, lai atjaunotu PDF vērtību."),
        "Cirtes veids": st.column_config.SelectboxColumn(
            options=list(CIRTES_NOSAUKUMI.values()),
            help="Sistēma izvēlas automātiski (kailcirte → kopšana → necirst). Izlases cirti izvēlies "
                 "manuāli. Notīri šūnu, lai atgrieztos pie automātiskā lēmuma."),
        "Cērt. ha": st.column_config.NumberColumn(
            format="%.2f", help="Faktiski cērtamā platība — kailcirtei bez atdalošajām joslām"),
        "G m²/ha": st.column_config.NumberColumn(format="%.0f", help="Šķērslaukums"),
        "Apjoms m³": st.column_config.NumberColumn(
            min_value=0.0, step=0.01, format="%.2f",
            help="Manuāli ievadīts apjoms aizstāj aprēķināto. Notīri šūnu, lai atjaunotu aprēķināto."),
        "Karogi": st.column_config.TextColumn(help="✎ manuāli labots · ⚠ risks · ℹ informācija",
                                              width="small"),
        "Info no PDF": st.column_config.TextColumn(width="large"),
        "Pamatojums": st.column_config.TextColumn(width="large"),
    },
)

if labojumi:
    l1, l2 = st.columns([3, 1])
    izmainas = labojumu_izmainas(inv.nogabali, labojumi, cenradis.noteikumi)
    atsifrejums = "\n".join(
        f"- **{nog_nosaukums(inv, inv.nogabali[i])}** — " + "; ".join(r)
        for i, r in sorted(izmainas.items())
    )
    l1.info(f"✎ Manuāli laboti {len(izmainas)} nogabali — aprēķins un atskaites ņem vērā labojumus."
            + (f"\n\n{atsifrejums}" if atsifrejums else ""))
    if l2.button(":material/undo: Atiestatīt visus labojumus" if avots == AVOTS_PDF else ":material/undo: Atjaunot kartes mērījumus",
                 use_container_width=True):
        st.session_state.labojumi = (copy.deepcopy(st.session_state.karte_aprekins["labojumi"])
                                     if avots == AVOTS_KARTE else {})
        st.session_state.tabulas_versija += 1
        st.rerun()

ar_info = [v for v in vertejumi if v.bridinajumi or (gabali and v.nogabals.pdf_apraksts)]
if ar_info:
    virsraksts = ("Nogabalu papildu informācija no PDF un karogi" if gabali
                  else "Riska karogi un papildu informācija")
    with st.expander(f"{virsraksts} ({len(ar_info)} nogabali)", expanded=bool(riski or laboti)):
        for v in ar_info:
            n = v.nogabals
            st.markdown(f"**{nog_nosaukums(inv, n)}** "
                        f"({v.cirtes_nosaukums.lower()}, {n.formula})")
            punkti = list(n.pdf_apraksts if gabali else []) + v.bridinajumi
            st.markdown("\n".join(f"- {p}" for p in punkti))

c_rindas = cirsmas_rindas(inv, vertejumi, fin)
if c_rindas:
    st.subheader("Cirsmas")
    st.caption("Katra cirsma atsevišķā rindā. Ja kailcirte pārsniedz max platību pēc meža tipa, "
               "nogabals sadalīts vairākās kailcirtēs ar atdalošo joslu starp tām.")
    st.dataframe(pd.DataFrame(c_rindas), use_container_width=True, hide_index=True,
                 column_config={"Platība ha": st.column_config.NumberColumn(format="%.2f"),
                                "Apjoms m³": st.column_config.NumberColumn(format="%.2f")})

kol1, kol2 = st.columns(2)
with kol1:
    st.subheader("Apjoms pa sugām")
    st.dataframe(pd.DataFrame(
        [{"Suga": f"{SUGU_NOSAUKUMI.get(s, s)} ({s})", "m³": m3} for s, m3 in fin.pa_sugam_m3.items()]
    ), use_container_width=True, hide_index=True)
with kol2:
    st.subheader("Finanses")
    fin_rindas = [{"Pozīcija": "Ieņēmumi no sortimentiem", "EUR": fin.ienemumi_kopa}]
    fin_rindas += [{"Pozīcija": p, "EUR": -e} for p, e in fin.izdevumi.items()]
    fin_rindas += [
        {"Pozīcija": f"Peļņas rezerve ({pelna:.0%})", "EUR": -fin.pelna},
        {"Pozīcija": "MAX IEGĀDES SUMMA", "EUR": fin.max_iegades_summa},
    ]
    st.dataframe(pd.DataFrame(fin_rindas), use_container_width=True, hide_index=True)

with st.expander("Sortimentu aprēķina detaļas"):
    st.dataframe(pd.DataFrame(fin.detalas), use_container_width=True, hide_index=True)

# --- Lejupielādes ----------------------------------------------------------
atskaite = teksta_atskaite(inv, vertejumi, fin)
with st.expander("Gala atskaite", expanded=False):
    st.code(atskaite, language=None)

    xlsx_cels = cels.replace(".pdf", "_atskaite.xlsx")
    excel_atskaite(xlsx_cels, inv, vertejumi, fin)
    with open(xlsx_cels, "rb") as f:
        st.download_button(":material/download: Lejupielādēt Excel atskaiti", f,
                           file_name="cirsmas_atskaite.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    st.download_button(":material/download: Lejupielādēt teksta atskaiti", atskaite, file_name="cirsmas_atskaite.txt")


# --- Saglabāšana un eksports ---------------------------------------------------
st.subheader(":material/save: Saglabāt priekšvērtējumu")
ss = st.session_state
ielad = ss.get("priekvertejums")          # {"id", "nosaukums", "piezimes"} — ja atvērts no saglabātajiem
kad = (ss.get("karte_aprekins") or {}).get("kadastrs") if avots == AVOTS_KARTE else None
kad = kad or inv.zemes_vieniba
noklusetais = (ielad or {}).get("nosaukums") or " · ".join(
    x for x in (inv.ipasums, kad) if x) or "Priekšvērtējums"
k1, k2 = st.columns([2, 3])
nosaukums = k1.text_input("Nosaukums", value=noklusetais, key=f"pv_nos_{faila_id[:8]}")
piezimes = k2.text_area("Piezīmes (nonāk PDF)", value=(ielad or {}).get("piezimes", ""), height=68,
                        key=f"pv_piez_{faila_id[:8]}")
karte_dati = ss.get("karte_aprekins") if avots == AVOTS_KARTE else None
try:
    pdf_baiti_atsk = priekvertejuma_pdf(
        inv, vertejumi, fin, nosaukums=nosaukums, autors=lietotajs(),
        objekti=(karte_dati or {}).get("objekti"), robezas=(karte_dati or {}).get("robezas"),
        piezimes=piezimes)
except Exception as e:  # noqa: BLE001
    pdf_baiti_atsk = None
    st.warning(f"PDF atskaiti neizdevās izveidot: {e}")

g = glabatuve()
kops = pv.kopsavilkums(inv, vertejumi, fin)


def _saglabat(parrakstit: bool) -> None:
    avota_pdf = ss.inv_pdf if ss.get("inv_pdf") and (avots == AVOTS_PDF or (
        karte_dati and "PDF" in karte_dati.get("apraksts", ""))) else None
    d = pv.dati(avots="karte" if avots == AVOTS_KARTE else "pdf", labojumi=labojumi,
                cenradis_json=cenradis.uz_json(), objekti=(karte_dati or {}).get("objekti"),
                kadastrs=kad, pdf_nosaukums=avota_pdf["nosaukums"] if avota_pdf else None,
                piezimes=piezimes, atskaite_pdf=pdf_baiti_atsk)
    id_ = g.saglabat_priekvertejumu(
        kadastrs=kad, nosaukums=nosaukums, avots=d["avots"], dati=d, kopsavilkums=kops,
        autors=lietotajs(), pdf=avota_pdf["baiti"] if avota_pdf else None,
        pdf_nosaukums=avota_pdf["nosaukums"] if avota_pdf else None,
        id_=ielad["id"] if (parrakstit and ielad) else None)
    ss.priekvertejums = {"id": id_, "nosaukums": nosaukums, "piezimes": piezimes}
    st.toast(f"Saglabāts: {nosaukums}", icon=":material/save:")


b1, b2, b3 = st.columns(3)
if ielad:
    b1.button(f":material/save: Saglabāt izmaiņas", type="primary", use_container_width=True, disabled=g is None,
              on_click=_saglabat, args=(True,), help=f"Pārraksta atvērto priekšvērtējumu ({ielad['id']})")
    b2.button(":material/save: Saglabāt kā jaunu", use_container_width=True, disabled=g is None,
              on_click=_saglabat, args=(False,))
else:
    b1.button(":material/save: Saglabāt", type="primary", use_container_width=True, disabled=g is None,
              on_click=_saglabat, args=(False,),
              help="Saglabā avota PDF, labojumus, kartes poligonus, cenas un rezultātu. Atrodams lapā "
                   "Saglabātie pēc kadastra numura.")
if pdf_baiti_atsk:
    b3.download_button(":material/download: PDF atskaite", pdf_baiti_atsk, use_container_width=True,
                       file_name=f"priekvertejums_{kad or 'cirsma'}.pdf", mime="application/pdf")
with st.expander(":material/content_copy: Teksts monday / e-pastam"):
    st.code(pv.monday_teksts(nosaukums, kops), language=None)
    st.caption("Ielīmē monday ieraksta Updates un pievieno PDF atskaiti. Automātiska augšupielāde "
               "monday būs, kad zināms boards un kolonnas.")
