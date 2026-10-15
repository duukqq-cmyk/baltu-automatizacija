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
from cirsma.sortiment import (
    aprekinat, vertejuma_apjoms, NOKLUSEJUMA_MATRICA, NOKLUSEJUMA_IZDEVUMI, NOKLUSEJUMA_PELNAS_REZERVE,
)
from cirsma.report import teksta_atskaite, excel_atskaite, nog_nosaukums, atrast_apjomu
from cirsma.formula import SUGU_NOSAUKUMI

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
    "Vecums": "vecums", "Kailcirte": "kailcirte", "Apjoms m³": "apjoms_m3",
}
# Kailcirte kā izvēle (nevis ķeksis), lai "Jā" būtu redzams ar zaļo ✅
KAILCIRTE_JA, KAILCIRTE_NE = "✅ Jā", "— Nē"


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
            if lauks == "kailcirte" and vertiba is not None:
                vertiba = vertiba == KAILCIRTE_JA
            setattr(lab, lauks, vertiba)  # None -> atpakaļ uz PDF vērtību
            if lauks in ("platiba_ha", "kraja_m3_ha"):
                lab.apjoms_m3 = None  # apjoms jāpārrēķina no jaunās platības/krājas
        if lab.tukss():
            labojumi.pop(atsl, None)
    st.session_state.tabulas_versija += 1


st.title("🌲 Cirsmas vērtības aprēķins no meža inventarizācijas PDF")
st.caption(
    "Augšupielādē nogabalu raksturojošo rādītāju PDF (VMD vai gabali.lv — formātu atpazīst "
    "automātiski). Sistēma atlasa kailcirtei atbilstošos nogabalus, aprēķina apjomu pa sugām "
    "un maksimālo iegādes summu, kā arī atzīmē riskus (aizsargjoslas, VMD plānotā darbība u.c.)."
)

# --- Sānjosla: rediģējamas cenas un izdevumi -------------------------------
st.sidebar.header("Sortimentu cenas un izdevumi")
matrica = copy.deepcopy(NOKLUSEJUMA_MATRICA)
with st.sidebar.expander("Sortimentu cenas (EUR/m3)", expanded=False):
    for kolonna, sortimenti in matrica.items():
        st.markdown(f"**{kolonna}**")
        for sortiments, (cena, ipatsvars) in sortimenti.items():
            jauna = st.number_input(
                f"{kolonna} · {sortiments} ({ipatsvars:.0%})",
                min_value=0.0, value=float(cena), step=1.0,
                key=f"cena_{kolonna}_{sortiments}",
            )
            matrica[kolonna][sortiments] = (jauna, ipatsvars)

izdevumi = {}
with st.sidebar.expander("Izdevumi (EUR/m3)", expanded=True):
    for poz, likme in NOKLUSEJUMA_IZDEVUMI.items():
        izdevumi[poz] = st.number_input(poz, min_value=0.0, value=float(likme), step=0.5)
pelna = st.sidebar.slider("Peļņas rezerve, %", 0, 50, int(NOKLUSEJUMA_PELNAS_REZERVE * 100)) / 100

# --- PDF augšupielāde ------------------------------------------------------
fails = st.file_uploader("Meža inventarizācijas PDF", type="pdf")
if not fails:
    st.info("⬆️ Augšupielādē PDF failu, lai sāktu (paraugs: `dati/Nogabalu_raksturojosie_raditaji_64560020029.pdf`).")
    st.stop()

pdf_baiti = fails.getvalue()
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
labojumi: dict[str, Labojums] = st.session_state.labojumi

try:
    vertejumi = novertet_ar_labojumiem(inv.nogabali, labojumi)
    fin = aprekinat(vertejumi, matrica=matrica, izdevumi_eur_m3=izdevumi, pelnas_rezerve=pelna)
except Exception as e:  # noqa: BLE001
    st.error(f"Neizdevās aprēķināt: {e}")
    st.stop()

# --- Rezultāti -------------------------------------------------------------
cirt = [v for v in vertejumi if v.atlauta_kailcirte]
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
        "Valdošā suga": SUGU_NOSAUKUMI.get(v.valdosa_suga, v.valdosa_suga),
        "Kailcirte": KAILCIRTE_JA if v.atlauta_kailcirte else KAILCIRTE_NE,
        "Apjoms m³": apjoms,
        "Karogi": karogi,
    }
    if gabali:
        rinda["Info no PDF"] = " · ".join(n.pdf_apraksts)
    rinda["Pamatojums"] = v.pamatojums
    rindas.append(rinda)
    atslegas.append(nogabala_atslega(v.indekss))

redaktora_atslega = f"nogabali_{faila_id[:8]}_{st.session_state.tabulas_versija}"
st.data_editor(
    pd.DataFrame(rindas),
    key=redaktora_atslega,
    on_change=_saglabat_labojumus,
    args=(redaktora_atslega, atslegas),
    hide_index=True,
    use_container_width=True,
    disabled=["Nog.", "Formula", "Valdošā suga", "Karogi", "Info no PDF", "Pamatojums"],
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
        "Kailcirte": st.column_config.SelectboxColumn(
            options=[KAILCIRTE_JA, KAILCIRTE_NE], width="small",
            help="Manuāli iekļauj vai izslēdz nogabalu no cirsmas. Notīri šūnu, lai atjaunotu sistēmas lēmumu."),
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
    izmainas = labojumu_izmainas(inv.nogabali, labojumi)
    atsifrejums = "\n".join(
        f"- **{nog_nosaukums(inv, inv.nogabali[i])}** — " + "; ".join(r)
        for i, r in sorted(izmainas.items())
    )
    l1.info(f"✎ Manuāli laboti {len(izmainas)} nogabali — aprēķins un atskaites ņem vērā labojumus."
            + (f"\n\n{atsifrejums}" if atsifrejums else ""))
    if l2.button("↺ Atiestatīt visus labojumus", use_container_width=True):
        st.session_state.labojumi = {}
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
                        f"({'cērtams' if v.atlauta_kailcirte else 'necērtams'}, {n.formula})")
            punkti = list(n.pdf_apraksts if gabali else []) + v.bridinajumi
            st.markdown("\n".join(f"- {p}" for p in punkti))

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
st.subheader("Gala atskaite")
atskaite = teksta_atskaite(inv, vertejumi, fin)
st.code(atskaite, language=None)

xlsx_cels = cels.replace(".pdf", "_atskaite.xlsx")
excel_atskaite(xlsx_cels, inv, vertejumi, fin)
with open(xlsx_cels, "rb") as f:
    st.download_button("⬇️ Lejupielādēt Excel atskaiti", f,
                       file_name="cirsmas_atskaite.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
st.download_button("⬇️ Lejupielādēt teksta atskaiti", atskaite, file_name="cirsmas_atskaite.txt")
