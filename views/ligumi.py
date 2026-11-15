"""Modulis: līgumu / dokumentu strukturētu datu izvilkšana."""
from __future__ import annotations

import dataclasses
import tempfile

import pandas as pd
import streamlit as st

from cirsma.ligumi import (
    ekstrakcija_regex, ekstrakcija_ai, epasta_kopsavilkums, excel_ligumi,
)
from views.kopigi import faili_uz_json, saglabasanas_bloks

st.title(":material/description: Līgumu datu izvilkšana no PDF")
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

ss = st.session_state
augsupladeti = st.file_uploader(
    "Līgumu PDF faili", type="pdf", accept_multiple_files=True,
    help="Paraugi: dati/ligumi/paraugs_pirkuma_ligums.pdf un paraugs_nomas_ligums.pdf",
)
if augsupladeti:
    faili = [(f.name, f.getvalue()) for f in augsupladeti]
    ss.ligumi_faili_sesija = faili               # lai paliek, pārslēdzot lapas
elif ss.get("ligumi_faili_sesija"):
    faili = ss.ligumi_faili_sesija
    k1, k2 = st.columns([4, 1])
    k1.caption(":material/folder_open: Izmanto iepriekš atvērtos failus: " + ", ".join(n for n, _ in faili))
    if k2.button(":material/close: Notīrīt", use_container_width=True):
        ss.pop("ligumi_faili_sesija", None)
        ss.pop("pv_ielad_ligumi", None)
        st.rerun()
else:
    st.info(":material/upload: Augšupielādē vienu vai vairākus PDF līgumus (paraugi mapē `dati/ligumi/`).")
    st.stop()

rezultati = []
for nosaukums, baiti in faili:
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(baiti)
        cels = tmp.name
    try:
        if ai_atslega:
            d = ekstrakcija_ai(cels, ai_atslega, nosaukums)
        else:
            d = ekstrakcija_regex(cels, nosaukums)
    except Exception as e:  # noqa: BLE001
        st.error(f"{nosaukums}: neizdevās apstrādāt — {e}")
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
    st.download_button(":material/download: Lejupielādēt Excel tabulu", f,
                       file_name="ligumu_dati.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
st.download_button(":material/download: Lejupielādēt kopsavilkumu (teksts)", kopsavilkums,
                   file_name="ligumu_kopsavilkums.txt")

st.divider()
summas = [d.summa_eur for d in rezultati if d.summa_eur is not None]
with st.container(border=True):
    saglabasanas_bloks(
        "ligumi", noklusetais=", ".join(dict.fromkeys(
            p["nosaukums"] for d in rezultati for p in d.puses[:1] if p.get("nosaukums"))) or "Līgumi",
        kadastrs=None,
        dati_fn=lambda: {"faili": faili_uz_json(faili),
                         "rezultati": [dataclasses.asdict(d) for d in rezultati]},
        kopsavilkums={"ligumi": len(rezultati), "summa_eur": sum(summas) if summas else None,
                      "datu_avots": "līgumi"},
        virsraksts="Saglabāt līgumus")
