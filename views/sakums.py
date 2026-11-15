"""Sākuma lapa — moduļa izvēle."""
import streamlit as st

from views.ikonas import sadalas_ik


def _virsraksts(kolonna, atsl: str, teksts: str) -> None:
    """Kartītes virsraksts ar sadaļas krāsaino ikonu (tāda pati kā navigācijā)."""
    kolonna.markdown(f"### {sadalas_ik(atsl)}&nbsp; {teksts}", unsafe_allow_html=True)


st.title(":material/home: Procesu automatizācijas platforma")
st.caption("Izvēlies, kuru funkciju vēlies izmantot.")

c1, c2, c3 = st.columns(3, gap="large")

with c1:
    with st.container(border=True):
        _virsraksts(st, "mezs", "Meža inventarizācijas analīze")
        st.write(
            "Augšupielādē meža inventarizācijas PDF — sistēma katram nogabalam nosaka cirtes veidu "
            "(kailcirte ar platību pēc meža tipa, kopšanas vai izlases cirte pēc šķērslaukuma), "
            "aprēķina apjomu pa sugām un sortimentiem un maksimālo cirsmas iegādes summu."
        )
        st.write("**Rezultāts:** gala atskaite (ekrānā, PDF, Excel), saglabājama pēc kadastra nr.")
        if st.button("Atvērt", icon=":material/arrow_forward:", key="uz_mezu", type="primary", use_container_width=True):
            st.switch_page("views/mezs.py")

with c2:
    with st.container(border=True):
        _virsraksts(st, "ligumi", "Līgumu datu izvilkšana")
        st.write(
            "Augšupielādē vienu vai vairākus PDF līgumus — sistēma izvelk "
            "galvenos parametrus: līguma puses, summas, datumus, termiņus un "
            "īpašos nosacījumus, ar validācijas brīdinājumiem šaubīgiem laukiem."
        )
        st.write("**Rezultāts:** datu tabula, Excel fails un e-pasta kopsavilkums.")
        if st.button("Atvērt", icon=":material/arrow_forward:", key="uz_ligumiem", type="primary", use_container_width=True):
            st.switch_page("views/ligumi.py")

with c3:
    with st.container(border=True):
        _virsraksts(st, "atskaites", "Atskaites")
        st.write(
            "Savāc datus no iepirkumu agentu monday.com boardiem, apvieno rindas leados "
            "(1 īpašuma kadastra Nr. = 1 lead) un aprēķina leadu, kvalifikācijas, "
            "priekšvērtējumu, apsekošanas, pirkumu un atteikumu metrikus."
        )
        st.write("**Rezultāts:** metriki ekrānā, pa agentiem, Excel un teksta atskaite.")
        if st.button("Atvērt", icon=":material/arrow_forward:", key="uz_atskaitem", type="primary", use_container_width=True):
            st.switch_page("views/atskaites.py")

with st.container(border=True):
    k1, k2 = st.columns([4, 1], vertical_alignment="center")
    _virsraksts(k1, "karte", "Karte (beta)")
    k1.write(
        "Ortofoto, LiDAR veģetācijas augstums, VMD mežaudžu plāns un kadastra karte vienā kartē. "
        "Zīmē un mēri cirsmas, importē KML, piesaisti laukumus nogabaliem — apjoms un iegādes "
        "summa pārrēķinās pēc uzmērītajām platībām."
    )
    if k2.button("Atvērt", icon=":material/arrow_forward:", key="uz_karti", type="primary", use_container_width=True):
        st.switch_page("views/karte.py")

k1, k2 = st.columns(2)
with k1.container(border=True):
    st.markdown(f"{sadalas_ik('saglabatie')}&nbsp; **Saglabātie priekšvērtējumi** — meklē pēc kadastra numura, "
                "atver, lejupielādē PDF.", unsafe_allow_html=True)
    if st.button("Atvērt", icon=":material/arrow_forward:", key="uz_saglabatajiem", use_container_width=True):
        st.switch_page("views/saglabatie.py")
with k2.container(border=True):
    st.markdown(f"{sadalas_ik('cenradis')}&nbsp; **Cenrādis** — sortimentu cenas un īpatsvari, izdevumi un "
                "ciršanas noteikumi visām sadaļām.", unsafe_allow_html=True)
    if st.button("Atvērt", icon=":material/arrow_forward:", key="uz_cenradi", use_container_width=True):
        st.switch_page("views/cenradis.py")

st.divider()
st.caption(
    "Prototips izstrādāts SIA Baltu Investments atlases uzdevumam · "
    "aprēķini ir deterministiski un auditējami · paraugu dati mapē `dati/`"
)
