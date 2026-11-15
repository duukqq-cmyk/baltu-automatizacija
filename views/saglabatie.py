"""Saglabātie priekšvērtējumi: meklēšana pēc kadastra numura, atvēršana, PDF, dzēšana."""
from __future__ import annotations

import copy
import hashlib

import pandas as pd
import streamlit as st

from cirsma import priekvertejums as pv
from cirsma.cenradis import Cenradis
from views.ikonas import AVOTS_PDF
from views.kopigi import aktivais_cenradis, glabatuve

st.title(":material/folder_open: Saglabātie priekšvērtējumi")
g = glabatuve()
if g is None:
    st.stop()
st.caption(f"Meklē pēc kadastra numura vai nosaukuma. Atverot tiek atjaunots avota PDF, labojumi, "
           f"kartes poligoni un tobrīd lietotās cenas. Glabātuve: {g.apraksts}.")

meklet = st.text_input("Meklēt", placeholder="kadastra nr. vai nosaukuma daļa", label_visibility="collapsed")
saraksts = g.meklet_priekvertejumus(meklet)
if not saraksts:
    st.info("Nekas nav atrasts." if meklet else
            "Vēl nav saglabātu priekšvērtējumu. Tos saglabā lapā Meža inventarizācija → :material/save: Saglabāt.")
    st.stop()


def _sk(v, d=0):
    return None if v is None else round(v, d)


df = pd.DataFrame([{
    "Nosaukums": x["nosaukums"], "Kadastrs": x["kadastrs"],
    "Avots": "Karte" if x["avots"] == "karte" else "PDF",
    "m³": _sk(x["kopsavilkums"].get("m3")), "ha": _sk(x["kopsavilkums"].get("platiba_ha"), 2),
    "Max summa €": _sk(x["kopsavilkums"].get("max_summa")),
    "€/m³": _sk(x["kopsavilkums"].get("cena_eur_m3"), 2),
    "Mainīts": x["mainits"].replace("T", " ")[:16], "Autors": x["autors"] or "",
} for x in saraksts])
izv = st.dataframe(df, hide_index=True, use_container_width=True, on_select="rerun",
                   selection_mode="single-row", key="pv_saraksts")
rindas = izv.selection.rows if izv else []
if not rindas:
    st.caption("Atzīmē rindu, lai atvērtu, lejupielādētu vai dzēstu.")
    st.stop()

ier = g.ielasit_priekvertejumu(saraksts[rindas[0]]["id"])
d = ier["dati"]
st.subheader(ier["nosaukums"])
if d.get("piezimes"):
    st.caption(d["piezimes"])
st.code(pv.monday_teksts(ier["nosaukums"], ier["kopsavilkums"]), language=None)


def _atvert() -> None:
    ss = st.session_state
    # cenas — kā saglabāšanas brīdī (sesijā; noklusējums nemainās)
    aktivais_cenradis()
    ss.cenradis = Cenradis.no_json(d.get("cenradis"))
    ss.cenradis_bazes = copy.deepcopy(ss.cenradis)
    ss.cenradis_versija = ss.get("cenradis_versija", 0) + 1
    labojumi = pv.labojumi_no_json(d.get("labojumi"))
    if ier["pdf"]:
        ss.inv_pdf = {"baiti": ier["pdf"], "nosaukums": ier["pdf_nosaukums"] or "saglabātais.pdf"}
    if d["avots"] == "karte":
        ss.karte_objekti = copy.deepcopy(d.get("objekti") or [])
        ss.karte_versija = ss.get("karte_versija", 0) + 1
        ss.karte_pietuvinat = True
        if d.get("kadastrs"):
            ss.karte_atvert_kadastru = d["kadastrs"]
        ss.priekvertejums_gaida = {"id": ier["id"], "nosaukums": ier["nosaukums"],
                                   "piezimes": d.get("piezimes", "")}
        ss.atvert_lapu = "views/karte.py"
    else:
        ss.faila_id = hashlib.sha1(ier["pdf"]).hexdigest()
        ss.labojumi = labojumi
        ss.tabulas_versija = ss.get("tabulas_versija", 0) + 1
        ss.mezs_avots = AVOTS_PDF
        ss.priekvertejums = {"id": ier["id"], "nosaukums": ier["nosaukums"], "piezimes": d.get("piezimes", "")}
        ss.atvert_lapu = "views/mezs.py"


b1, b2, b3, b4 = st.columns(4)
if b1.button(":material/folder_open: Atvērt", type="primary", use_container_width=True,
             disabled=d["avots"] == "pdf" and not ier["pdf"]):
    _atvert()
    st.switch_page(st.session_state.pop("atvert_lapu"))
atsk = pv.atskaites_pdf(d)
if atsk:
    b2.download_button(":material/download: PDF atskaite", atsk, file_name=f"priekvertejums_{ier['kadastrs'] or ier['id']}.pdf",
                       mime="application/pdf", use_container_width=True)
if ier["pdf"]:
    b3.download_button(":material/download: Avota PDF", ier["pdf"], file_name=ier["pdf_nosaukums"] or "avots.pdf",
                       mime="application/pdf", use_container_width=True)
with b4.popover(":material/delete: Dzēst", use_container_width=True):
    st.write(f"Dzēst **{ier['nosaukums']}**? To nevar atsaukt.")
    if st.button("Jā, dzēst", type="primary"):
        g.dzest_priekvertejumu(ier["id"])
        st.rerun()
