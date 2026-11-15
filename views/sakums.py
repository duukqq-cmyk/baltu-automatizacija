"""Sākuma lapa — moduļa izvēle.

Visas sadaļas ir vienādās kartītēs vienotā režģī (3 kolonnas): ikona + virsraksts,
apraksts, rezultāts un poga "Atvērt" kartītes apakšā (vienā līmenī visās kartītēs). Kartītes vienā rindā ir vienāda augstuma.
Jaunu sadaļu pievieno, ierakstot to sarakstā KARTITES.
"""
import streamlit as st

from views.ikonas import SADALAS, sadalas_ik

# (sadaļas atslēga, virsraksts, apraksts, rezultāts)
KARTITES: list[tuple[str, str, str, str]] = [
    ("mezs", "Meža inventarizācija",
     "Augšupielādē inventarizācijas PDF — katram nogabalam nosaka cirtes veidu, aprēķina apjomu "
     "pa sugām un sortimentiem un maksimālo cirsmas iegādes summu.",
     "gala atskaite ekrānā, PDF un Excel; saglabājama pēc kadastra nr."),
    ("ligumi", "Līgumu datu izvilkšana",
     "Augšupielādē vienu vai vairākus PDF līgumus — izvelk puses, summas, datumus, termiņus un "
     "īpašos nosacījumus, ar brīdinājumiem šaubīgiem laukiem.",
     "datu tabula, Excel fails un e-pasta kopsavilkums."),
    ("atskaites", "Atskaites",
     "Savāc datus no iepirkumu agentu monday.com boardiem, apvieno tos leados "
     "(1 kadastra nr. = 1 lead) un aprēķina piltuves metrikus.",
     "metriki ekrānā un pa agentiem, Excel un teksta atskaite."),
    ("karte", "Karte (beta)",
     "Ortofoto, LiDAR veģetācijas augstums, VMD mežaudžu plāns un kadastrs vienā kartē. "
     "Zīmē un mēri cirsmas, importē KML, piesaisti laukumus nogabaliem.",
     "apjoms un iegādes summa pēc uzmērītajām platībām."),
    ("saglabatie", "Saglabātie darbi",
     "Visi saglabātie darbi vienuviet — inventarizācijas, kartes aprēķini, novērtējumi un "
     "līgumi. Meklē pēc kadastra nr., atver un turpini darbu.",
     "atvērts darbs vai lejupielādēts PDF."),
    ("cenradis", "Cenrādis",
     "Kopīgie iestatījumi visām sadaļām — sortimentu cenas un īpatsvari pa sugām, "
     "izdevumi un ciršanas noteikumi, ar izmaiņu vēsturi.",
     "vienotas cenas un noteikumi visos aprēķinos."),
]

KOLONNAS = 3

# Vienāda augstuma kartītes: kolonnas izstiepjas līdz rindas augstumam, kartīte aizpilda kolonnu,
# un poga tiek nobīdīta uz kartītes apakšu.
st.markdown("""<style>
[data-testid="stHorizontalBlock"]:has(div[class*="st-key-kartite_"]) {align-items: stretch;}
[data-testid="stColumn"]:has(div[class*="st-key-kartite_"]) > div {height: 100%;}
[data-testid="stLayoutWrapper"]:has(> div[class*="st-key-kartite_"]) {flex: 1 1 auto; display: flex;}
div[class*="st-key-kartite_"] {flex: 1 1 auto; height: 100%; display: flex; flex-direction: column;}
div[class*="st-key-apaksa_"],
div[class*="st-key-kartite_"] > div:has(> div[class*="st-key-apaksa_"]) {margin-top: auto;}
div[class*="st-key-kartite_"] h4 {padding-top: 0;}
div[class*="st-key-kartite_"] p {margin-bottom: 0.25rem;}
</style>""", unsafe_allow_html=True)

st.title(":material/home: Procesu automatizācijas platforma")
st.caption("Izvēlies, kuru funkciju vēlies izmantot.")

for sakums in range(0, len(KARTITES), KOLONNAS):
    kolonnas = st.columns(KOLONNAS, gap="medium")
    for kol, (atsl, virsraksts, apraksts, rezultats) in zip(kolonnas, KARTITES[sakums:sakums + KOLONNAS]):
        with kol:
            with st.container(border=True, key=f"kartite_{atsl}"):
                st.markdown(f"#### {sadalas_ik(atsl)}&nbsp; {virsraksts}", unsafe_allow_html=True)
                st.markdown(apraksts)
                # rezultāts + poga vienmēr kartītes apakšā (vienā līmenī visās kartītēs rindā)
                with st.container(key=f"apaksa_{atsl}"):
                    st.markdown(f"**Rezultāts:** {rezultats}")
                    if st.button("Atvērt", icon=":material/arrow_forward:", key=f"uz_{atsl}",
                                 type="primary", use_container_width=True):
                        st.switch_page(SADALAS[atsl][2])

st.divider()
st.caption(
    "Prototips izstrādāts SIA Baltu Investments atlases uzdevumam · "
    "aprēķini ir deterministiski un auditējami · paraugu dati mapē `dati/`"
)
