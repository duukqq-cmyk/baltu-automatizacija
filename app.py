"""Baltu Investments procesu automatizācijas platforma.

Palaišana:  streamlit run app.py
Sākuma logā izvēlies moduli:
  1) Meža inventarizācijas analīze (cirsmas vērtības aprēķins)
  2) Līgumu datu izvilkšana
  3) Leadu atskaites no monday.com
  4) ĢIS karte — cirsmu atzīmēšana, mērījumi un pārrēķins (beta)
  + Cenrādis (kopīgas cenas, sortimenti, izdevumi, noteikumi) un Saglabātie priekšvērtējumi
"""
import streamlit as st

st.set_page_config(
    page_title="Automatizācijas platforma",
    page_icon="⚙️",
    layout="wide",
)

# Pārzīmējot lapu (pēc katras darbības), Streamlit uz mirkli padara elementus blāvus — tas izskatās
# kā raustīšanās. Rezultāti atjaunojas sekundes daļā, tāpēc blāvošanu izslēdzam visai lietotnei.
st.sidebar.markdown("""<style>
[data-stale="true"], .stale-element {opacity: 1 !important; transition: none !important; filter: none !important;}
</style>""", unsafe_allow_html=True)

pg = st.navigation([
    st.Page("views/sakums.py", title="Sākums", icon="🏠", default=True),
    st.Page("views/mezs.py", title="Meža inventarizācija", icon="🌲"),
    st.Page("views/saglabatie.py", title="Saglabātie", icon="📁"),
    st.Page("views/cenradis.py", title="Cenrādis", icon="💶"),
    st.Page("views/ligumi.py", title="Līgumu datu izvilkšana", icon="📄"),
    st.Page("views/atskaites.py", title="Atskaites", icon="📊"),
    st.Page("views/karte.py", title="Karte (beta)", icon="🗺️"),
])
# Lietotāja vārds izmaiņu vēsturei un saglabātajiem priekšvērtējumiem (līdz būs pieteikšanās)
st.sidebar.text_input("👤 Tavs vārds", key="lietotaja_vards",
                      help="Tiek ierakstīts cenrāža izmaiņu vēsturē un saglabātajos priekšvērtējumos.")
pg.run()
