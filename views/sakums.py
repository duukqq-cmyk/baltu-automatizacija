"""Sākuma lapa — moduļa izvēle."""
import streamlit as st

st.title("⚙️ Procesu automatizācijas platforma")
st.caption("Izvēlies, kuru funkciju vēlies izmantot.")

c1, c2, c3 = st.columns(3, gap="large")

with c1:
    with st.container(border=True):
        st.subheader("🌲 Meža inventarizācijas analīze")
        st.write(
            "Augšupielādē meža inventarizācijas PDF — sistēma katram nogabalam nosaka cirtes veidu "
            "(kailcirte ar platību pēc meža tipa, kopšanas vai izlases cirte pēc šķērslaukuma), "
            "aprēķina apjomu pa sugām un sortimentiem un maksimālo cirsmas iegādes summu."
        )
        st.write("**Rezultāts:** gala atskaite (ekrānā, PDF, Excel), saglabājama pēc kadastra nr.")
        if st.button("Atvērt →", key="uz_mezu", type="primary", use_container_width=True):
            st.switch_page("views/mezs.py")

with c2:
    with st.container(border=True):
        st.subheader("📄 Līgumu datu izvilkšana")
        st.write(
            "Augšupielādē vienu vai vairākus PDF līgumus — sistēma izvelk "
            "galvenos parametrus: līguma puses, summas, datumus, termiņus un "
            "īpašos nosacījumus, ar validācijas brīdinājumiem šaubīgiem laukiem."
        )
        st.write("**Rezultāts:** datu tabula, Excel fails un e-pasta kopsavilkums.")
        if st.button("Atvērt →", key="uz_ligumiem", type="primary", use_container_width=True):
            st.switch_page("views/ligumi.py")

with c3:
    with st.container(border=True):
        st.subheader("📊 Atskaites")
        st.write(
            "Savāc datus no iepirkumu agentu monday.com boardiem, apvieno rindas leados "
            "(1 īpašuma kadastra Nr. = 1 lead) un aprēķina leadu, kvalifikācijas, "
            "priekšvērtējumu, apsekošanas, pirkumu un atteikumu metrikus."
        )
        st.write("**Rezultāts:** metriki ekrānā, pa agentiem, Excel un teksta atskaite.")
        if st.button("Atvērt →", key="uz_atskaitem", type="primary", use_container_width=True):
            st.switch_page("views/atskaites.py")

with st.container(border=True):
    k1, k2 = st.columns([4, 1], vertical_alignment="center")
    k1.subheader("🗺️ Karte (beta)")
    k1.write(
        "Ortofoto, LiDAR veģetācijas augstums, VMD mežaudžu plāns un kadastra karte vienā kartē. "
        "Zīmē un mēri cirsmas, importē KML, piesaisti laukumus nogabaliem — apjoms un iegādes "
        "summa pārrēķinās pēc uzmērītajām platībām."
    )
    if k2.button("Atvērt →", key="uz_karti", type="primary", use_container_width=True):
        st.switch_page("views/karte.py")

k1, k2 = st.columns(2)
with k1.container(border=True):
    st.markdown("**📁 Saglabātie priekšvērtējumi** — meklē pēc kadastra numura, atver, lejupielādē PDF.")
    if st.button("Atvērt →", key="uz_saglabatajiem", use_container_width=True):
        st.switch_page("views/saglabatie.py")
with k2.container(border=True):
    st.markdown("**💶 Cenrādis** — sortimentu cenas un īpatsvari, izdevumi un ciršanas noteikumi visām sadaļām.")
    if st.button("Atvērt →", key="uz_cenradi", use_container_width=True):
        st.switch_page("views/cenradis.py")

st.divider()
st.caption(
    "Prototips izstrādāts SIA Baltu Investments atlases uzdevumam · "
    "aprēķini ir deterministiski un auditējami · paraugu dati mapē `dati/`"
)
