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

from views.autentifikacija import lietotaja_josla, pieteiksanas_ieslegta, prasit_pieteiksanos
from views.ikonas import SADALAS, css, nav

st.set_page_config(
    page_title="Automatizācijas platforma",
    page_icon=":material/forest:",
    layout="wide",
)

# Pieteikšanās (ieslēdzas, kad secrets ir [auth] — sk. views/autentifikacija.py)
AUTH = pieteiksanas_ieslegta()
if AUTH:
    prasit_pieteiksanos()

NOSAUKUMI = {"sakums": "Sākums", "mezs": "Meža inventarizācija", "saglabatie": "Saglabātie",
             "cenradis": "Cenrādis", "ligumi": "Līgumu datu izvilkšana", "atskaites": "Atskaites",
             "karte": "Karte (beta)"}
lapas = {atsl: st.Page(SADALAS[atsl][2], title=NOSAUKUMI[atsl], icon=nav(atsl), default=atsl == "sakums")
         for atsl in NOSAUKUMI}
pg = st.navigation(list(lapas.values()))
aktiva = next((a for a, l in lapas.items() if l.url_path == pg.url_path), None)

# Stils visai lietotnei:
#  * ikonu krāsas (navigācija, aktīvās lapas virsraksts) — views/ikonas.py;
#  * pārzīmējot lapu (pēc katras darbības), Streamlit uz mirkli padara elementus blāvus — tas
#    izskatās kā raustīšanās; rezultāti atjaunojas sekundes daļā, tāpēc blāvošanu izslēdzam.
st.sidebar.markdown("<style>\n" + css(aktiva) + """
[data-stale="true"], .stale-element {opacity: 1 !important; transition: none !important; filter: none !important;}
</style>""", unsafe_allow_html=True)

if AUTH:
    lietotaja_josla()
else:
    # Bez pieteikšanās — vārdu ieraksta pats (izmaiņu vēsturei un saglabātajiem priekšvērtējumiem)
    st.sidebar.text_input(":material/person: Tavs vārds", key="lietotaja_vards",
                          help="Tiek ierakstīts cenrāža izmaiņu vēsturē un saglabātajos priekšvērtējumos.")
pg.run()
