"""Modulis: meža inventarizācijas analīze (cirsmas vērtības aprēķins)."""
from __future__ import annotations

import copy
import tempfile

import pandas as pd
import streamlit as st

from cirsma.parser import parse_inventory_pdf
from cirsma.rules import atlasit_kailcirtes
from cirsma.sortiment import (
    aprekinat, NOKLUSEJUMA_MATRICA, NOKLUSEJUMA_IZDEVUMI, NOKLUSEJUMA_PELNAS_REZERVE,
)
from cirsma.report import teksta_atskaite, excel_atskaite
from cirsma.formula import SUGU_NOSAUKUMI

st.title("🌲 Cirsmas vērtības aprēķins no meža inventarizācijas PDF")
st.caption(
    "Augšupielādē VMD nogabalu raksturojošo rādītāju PDF — sistēma atlasa kailcirtei "
    "atbilstošos nogabalus, aprēķina apjomu pa sugām un maksimālo iegādes summu."
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

with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
    tmp.write(fails.read())
    cels = tmp.name

try:
    inv = parse_inventory_pdf(cels)
    vertejumi = atlasit_kailcirtes(inv.nogabali)
    fin = aprekinat(vertejumi, matrica=matrica, izdevumi_eur_m3=izdevumi, pelnas_rezerve=pelna)
except Exception as e:  # noqa: BLE001
    st.error(f"Neizdevās apstrādāt failu: {e}")
    st.stop()

# --- Rezultāti -------------------------------------------------------------
c1, c2, c3, c4 = st.columns(4)
c1.metric("Cērtamais apjoms", f"{fin.kopejais_m3:,.0f} m³")
c2.metric("Ieņēmumi", f"{fin.ienemumi_kopa:,.0f} EUR")
c3.metric("Max iegādes summa", f"{fin.max_iegades_summa:,.0f} EUR")
c4.metric("Cena", f"{fin.cena_eur_m3:.2f} EUR/m³")

st.subheader("Nogabalu vērtējums")
rindas = []
for v in vertejumi:
    n = v.nogabals
    apjoms = next((a.kopejais_m3 for a in fin.apjomi if a.nog_nr == n.nr), None)
    rindas.append({
        "Nog.": n.nr, "Platība ha": n.platiba_ha, "Krāja m³/ha": n.kraja_m3_ha,
        "Formula": n.formula, "Bonitāte": n.bonitate, "Vecums": n.vecums,
        "Valdošā suga": SUGU_NOSAUKUMI.get(v.valdosa_suga, v.valdosa_suga),
        "Kailcirte": "✅" if v.atlauta_kailcirte else "—",
        "Apjoms m³": apjoms, "Pamatojums": v.pamatojums,
    })
st.dataframe(pd.DataFrame(rindas), use_container_width=True, hide_index=True)

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
