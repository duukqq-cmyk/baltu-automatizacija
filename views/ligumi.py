"""Modulis: līgumu / dokumentu strukturētu datu izvilkšana."""
from __future__ import annotations

import dataclasses
import tempfile

import pandas as pd
import streamlit as st

from cirsma.ligumi import (
    ekstrakcija_regex, ekstrakcija_ai, epasta_kopsavilkums, excel_ligumi,
)

st.title("📄 Līgumu datu izvilkšana no PDF")
st.caption(
    "Augšupielādē vienu vai vairākus PDF līgumus — sistēma izvelk puses, summas, "
    "datumus, termiņus un īpašos nosacījumus. Lauki, par kuriem sistēma nav droša, "
    "tiek marķēti ar ⚠ manuālai pārbaudei."
)

st.sidebar.header("Ekstrakcijas režīms")
ai_atslega = st.sidebar.text_input(
    "Claude API atslēga (neobligāti)", type="password",
    help="Ja norādīta, ekstrakciju veic MI modelis ar krustenisko validāciju pret "
         "deterministisko ekstrakciju. Bez atslēgas strādā noteikumu ekstrakcija.",
)

faili = st.file_uploader(
    "Līgumu PDF faili", type="pdf", accept_multiple_files=True,
    help="Paraugi: dati/ligumi/paraugs_pirkuma_ligums.pdf un paraugs_nomas_ligums.pdf",
)
if not faili:
    st.info("⬆️ Augšupielādē vienu vai vairākus PDF līgumus (paraugi mapē `dati/ligumi/`).")
    st.stop()

rezultati = []
for fails in faili:
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(fails.read())
        cels = tmp.name
    try:
        if ai_atslega:
            d = ekstrakcija_ai(cels, ai_atslega, fails.name)
        else:
            d = ekstrakcija_regex(cels, fails.name)
    except Exception as e:  # noqa: BLE001
        st.error(f"{fails.name}: neizdevās apstrādāt — {e}")
        continue
    rezultati.append(d)

if not rezultati:
    st.stop()

# --- Tabula ----------------------------------------------------------------
st.subheader("Izvilktie dati")
rindas = []
for d in rezultati:
    rindas.append({
        "Fails": d.fails,
        "Veids": d.liguma_veids,
        "Datums": d.datums,
        "Puses": "; ".join(f"{p['loma']}: {p['nosaukums']}" for p in d.puses),
        "Summa EUR": d.summa_eur,
        "Termiņš": d.termins,
        "Īpašie nosacījumi": " | ".join(d.ipasie_nosacijumi),
        "⚠ Piezīmes": " | ".join(d.piezimes),
    })
st.dataframe(pd.DataFrame(rindas), use_container_width=True, hide_index=True)

for d in rezultati:
    if d.piezimes:
        st.warning(f"**{d.fails}** — jāpārbauda manuāli: " + "; ".join(d.piezimes))

with st.expander("Pilnie dati (JSON)"):
    st.json([dataclasses.asdict(d) for d in rezultati])

# --- E-pasta kopsavilkums un lejupielādes ----------------------------------
st.subheader("E-pasta kopsavilkums")
kopsavilkums = epasta_kopsavilkums(rezultati)
st.code(kopsavilkums, language=None)

xlsx_cels = tempfile.mktemp(suffix=".xlsx")
excel_ligumi(xlsx_cels, rezultati)
with open(xlsx_cels, "rb") as f:
    st.download_button("⬇️ Lejupielādēt Excel tabulu", f,
                       file_name="ligumu_dati.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
st.download_button("⬇️ Lejupielādēt kopsavilkumu (teksts)", kopsavilkums,
                   file_name="ligumu_kopsavilkums.txt")
