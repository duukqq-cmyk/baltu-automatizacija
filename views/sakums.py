"""Sākuma lapa — moduļa izvēle."""
import streamlit as st

st.title("⚙️ Procesu automatizācijas platforma")
st.caption("Izvēlies, kuru funkciju vēlies izmantot.")

c1, c2 = st.columns(2, gap="large")

with c1:
    with st.container(border=True):
        st.subheader("🌲 Meža inventarizācijas analīze")
        st.write(
            "Augšupielādē meža inventarizācijas PDF — sistēma atlasa kailcirtei "
            "atbilstošos nogabalus, aprēķina cērtamo apjomu pa sugām, piemēro "
            "sortimentu matricu un izrēķina maksimālo cirsmas iegādes summu."
        )
        st.write("**Rezultāts:** gala atskaite (ekrānā, Excel un teksta failā).")
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

st.divider()
st.caption(
    "Prototips izstrādāts SIA Baltu Investments atlases uzdevumam · "
    "aprēķini ir deterministiski un auditējami · paraugu dati mapē `dati/`"
)
