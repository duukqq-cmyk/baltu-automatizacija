"""Saglabātie darbi visām sadaļām: meklēšana pēc kadastra / nosaukuma, atvēršana, faili, dzēšana."""
from __future__ import annotations

import copy
import hashlib
import io
import zipfile

import pandas as pd
import streamlit as st

from cirsma import priekvertejums as pv
from cirsma.cenradis import Cenradis
from views.ikonas import AVOTS_NOVERTEJUMS, AVOTS_PDF
from views.kopigi import SADALU_NOSAUKUMI, aktivais_cenradis, faili_no_json, glabatuve

st.title(":material/folder_open: Saglabātie darbi")
g = glabatuve()
if g is None:
    st.stop()
st.caption(f"Meža inventarizācija, karte, cirsmas novērtējumi un līgumi. Meklē pēc kadastra numura vai "
           f"nosaukuma; atverot darbs atjaunojas tieši tāds, kāds saglabāts. Glabātuve: {g.apraksts}.")

FILTRI = {"Visi": None, ":material/forest: Meža inventarizācija": "pdf", ":material/map: Karte": "karte",
          ":material/calculate: Novērtējumi": "novertejums", ":material/description: Līgumi": "ligumi"}
meklet = st.text_input("Meklēt", placeholder="kadastra nr. vai nosaukuma daļa", label_visibility="collapsed")
filtrs = st.segmented_control("Sadaļa", list(FILTRI), default="Visi", label_visibility="collapsed") or "Visi"

saraksts = [x for x in g.meklet_priekvertejumus(meklet)
            if FILTRI[filtrs] is None or x["avots"] == FILTRI[filtrs]]
if not saraksts:
    st.info("Nekas nav atrasts." if (meklet or FILTRI[filtrs]) else
            "Vēl nav saglabātu darbu. Saglabāt var katrā sadaļā ar pogu :material/save: Saglabāt.")
    st.stop()


def _sk(v, d=0):
    return None if v is None else round(v, d)


df = pd.DataFrame([{
    "Nosaukums": x["nosaukums"], "Sadaļa": SADALU_NOSAUKUMI.get(x["avots"], x["avots"]),
    "Kadastrs": x["kadastrs"],
    "m³": _sk(x["kopsavilkums"].get("m3")), "ha": _sk(x["kopsavilkums"].get("platiba_ha"), 2),
    "Summa €": _sk(x["kopsavilkums"].get("max_summa") or x["kopsavilkums"].get("summa_eur")),
    "€/m³": _sk(x["kopsavilkums"].get("cena_eur_m3"), 2),
    "Mainīts": x["mainits"].replace("T", " ")[:16], "Autors": x["autors"] or "",
} for x in saraksts])
izv = st.dataframe(df, hide_index=True, use_container_width=True, on_select="rerun",
                   selection_mode="single-row", key="pv_saraksts",
                   column_config={"Summa €": st.column_config.NumberColumn(
                       help="Meža inventarizācijai, kartei un novērtējumam — max iegādes summa; "
                            "līgumiem — līgumu summa")})
rindas = izv.selection.rows if izv else []
if not rindas:
    st.caption("Atzīmē rindu, lai atvērtu, lejupielādētu vai dzēstu.")
    st.stop()

ier = g.ielasit_priekvertejumu(saraksts[rindas[0]]["id"])
d = ier["dati"]
veids = ier["avots"]
faili = faili_no_json(d.get("faili"))
if ier["pdf"] and not faili:
    faili = [(ier["pdf_nosaukums"] or "avots.pdf", ier["pdf"])]

st.subheader(ier["nosaukums"])
st.caption(f"{SADALU_NOSAUKUMI.get(veids, veids)} · saglabāts {ier['mainits'].replace('T', ' ')[:16]}"
           + (f" · {ier['autors']}" if ier["autors"] else "")
           + (f" · faili: {', '.join(n for n, _ in faili)}" if faili else ""))
if d.get("piezimes"):
    st.markdown(f"> {d['piezimes']}")
if veids in ("pdf", "karte") and ier["kopsavilkums"].get("m3") is not None:
    st.code(pv.monday_teksts(ier["nosaukums"], ier["kopsavilkums"]), language=None)


def _atvert() -> str:
    """Atjauno sesiju un atgriež lapu, kuru atvērt."""
    ss = st.session_state
    ielad = {"id": ier["id"], "nosaukums": ier["nosaukums"], "piezimes": d.get("piezimes", "")}
    if d.get("cenradis"):                       # cenas — kā saglabāšanas brīdī (tikai šajā sesijā)
        aktivais_cenradis()
        ss.cenradis_ieladets = Cenradis.no_json(d["cenradis"])

    if veids == "novertejums":
        ss.nov_faili_sesija = faili
        ss.pv_ielad_novertejums = ielad
        ss.mezs_avots = AVOTS_NOVERTEJUMS
        return "views/mezs.py"
    if veids == "ligumi":
        ss.ligumi_faili_sesija = faili
        ss.pv_ielad_ligumi = ielad
        return "views/ligumi.py"

    if ier["pdf"]:
        ss.inv_pdf = {"baiti": ier["pdf"], "nosaukums": ier["pdf_nosaukums"] or "saglabātais.pdf"}
    if veids == "karte":
        ss.karte_objekti = copy.deepcopy(d.get("objekti") or [])
        ss.karte_versija = ss.get("karte_versija", 0) + 1
        ss.karte_tikai = d.get("karte_tikai", True)
        ss.karte_visi = d.get("karte_visi", True)
        kadastri = d.get("kadastri") or ([d["kadastrs"]] if d.get("kadastrs") else [])
        ss.karte_zv = []
        if kadastri:
            ss.karte_atvert_kadastri = kadastri
        if d.get("skats"):
            ss.karte_atvert_skats = d["skats"]
        ss.karte_pietuvinat = not d.get("skats")
        ss.pv_ielad_karte = ielad
        ss.priekvertejums_gaida = ielad          # ja no kartes atvērs kalkulatorā
        return "views/karte.py"

    labojumi = pv.labojumi_no_json(d.get("labojumi"))
    ss.faila_id = hashlib.sha1(ier["pdf"]).hexdigest()
    ss.labojumi = labojumi
    ss.tabulas_versija = ss.get("tabulas_versija", 0) + 1
    ss.mezs_avots = AVOTS_PDF
    ss.priekvertejums = ielad
    return "views/mezs.py"


b1, b2, b3, b4 = st.columns(4)
if b1.button(":material/open_in_new: Atvērt", type="primary", use_container_width=True,
             disabled=veids == "pdf" and not ier["pdf"]):
    st.switch_page(_atvert())
atsk = pv.atskaites_pdf(d)
if atsk:
    b2.download_button(":material/picture_as_pdf: PDF atskaite", atsk, use_container_width=True,
                       file_name=f"priekvertejums_{ier['kadastrs'] or ier['id']}.pdf", mime="application/pdf")
if len(faili) == 1:
    b3.download_button(":material/download: Avota PDF", faili[0][1], file_name=faili[0][0],
                       mime="application/pdf", use_container_width=True)
elif faili:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for n, b in faili:
            z.writestr(n, b)
    b3.download_button(f":material/folder_zip: Faili ({len(faili)})", buf.getvalue(), use_container_width=True,
                       file_name=f"{ier['nosaukums'][:40]}.zip", mime="application/zip")
with b4.popover(":material/delete: Dzēst", use_container_width=True):
    st.write(f"Dzēst **{ier['nosaukums']}**? To nevar atsaukt.")
    if st.button("Jā, dzēst", type="primary"):
        g.dzest_priekvertejumu(ier["id"])
        st.rerun()
