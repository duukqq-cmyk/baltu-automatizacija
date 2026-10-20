"""Baltu Investments procesu automatizācijas platforma.

Palaišana:  streamlit run app.py
Sākuma logā izvēlies moduli:
  1) Meža inventarizācijas analīze (cirsmas vērtības aprēķins)
  2) Līgumu datu izvilkšana
  3) Leadu atskaites no monday.com
"""
import streamlit as st

st.set_page_config(
    page_title="Automatizācijas platforma",
    page_icon="⚙️",
    layout="wide",
)

pg = st.navigation([
    st.Page("views/sakums.py", title="Sākums", icon="🏠", default=True),
    st.Page("views/mezs.py", title="Meža inventarizācija", icon="🌲"),
    st.Page("views/ligumi.py", title="Līgumu datu izvilkšana", icon="📄"),
    st.Page("views/atskaites.py", title="Atskaites", icon="📊"),
])
pg.run()
