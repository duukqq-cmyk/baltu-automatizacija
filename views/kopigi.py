"""Kopīgi Streamlit palīgi: aktīvais cenrādis sesijā, glabātuve, lietotāja vārds."""
from __future__ import annotations

import copy

import streamlit as st

from cirsma.cenradis import ATSLEGA, Cenradis


@st.cache_resource(show_spinner=False)
def _glabatuve_resurss():
    from glabatuve import glabatuve
    return glabatuve()


def glabatuve():
    """Glabātuve vai None, ja datubāze nav pieejama (kļūda tiek parādīta vienreiz)."""
    try:
        return _glabatuve_resurss()
    except Exception as e:  # noqa: BLE001
        if not st.session_state.get("_db_kluda_paradita"):
            st.session_state._db_kluda_paradita = True
            st.warning(f"Datubāze nav pieejama ({e}) — saglabāšana nedarbosies, tiek lietoti noklusējumi.")
        return None


def ielade_saglabato_cenradi() -> tuple[Cenradis, dict | None]:
    """(cenrādis no datubāzes vai noklusējums, metadati {mainits, autors})."""
    g = glabatuve()
    ier = g.iestatijums(ATSLEGA) if g else None
    if ier:
        return Cenradis.no_json(ier["vertiba"]), {"mainits": ier["mainits"], "autors": ier["autors"]}
    return Cenradis(), None


def aktivais_cenradis() -> Cenradis:
    """Sesijas cenrādis (pirmajā reizē ielādē saglabāto). Izmaiņas lapā Cenrādis
    darbojas uzreiz šajā sesijā; "Saglabāt" padara tās par noklusējumu visiem."""
    if "cenradis_saglabatais" not in st.session_state:
        c, meta = ielade_saglabato_cenradi()
        st.session_state.setdefault("cenradis", c)
        st.session_state.cenradis_saglabatais = copy.deepcopy(c)
        st.session_state.cenradis_meta = meta
        st.session_state.setdefault("cenradis_versija", 0)
    return st.session_state.cenradis


def cenradis_mainits() -> bool:
    """Vai sesijas cenrādis atšķiras no saglabātā noklusējuma."""
    aktivais_cenradis()
    return st.session_state.cenradis.uz_json() != st.session_state.cenradis_saglabatais.uz_json()


def cenradis_statuss_sanjosla() -> None:
    """Īss cenrāža statuss sānjoslā ar saiti uz lapu Cenrādis."""
    aktivais_cenradis()
    meta = st.session_state.get("cenradis_meta")
    with st.sidebar:
        st.markdown("**💶 Cenrādis**")
        if cenradis_mainits():
            st.caption("✎ Šajā sesijā mainīts (nav saglabāts kā noklusējums)")
        elif meta:
            st.caption(f"Saglabātais noklusējums · {meta['mainits'][:10]}"
                       + (f" · {meta['autors']}" if meta.get("autors") else ""))
        else:
            st.caption("Rūpnīcas noklusējums (vēl nav saglabāts)")
        st.page_link("views/cenradis.py", label="Mainīt cenas, sortimentus, izdevumus", icon="⚙️")


def lietotajs() -> str | None:
    """Lietotāja vārds izmaiņu vēsturei (līdz būs pieteikšanās)."""
    return (st.session_state.get("lietotaja_vards") or "").strip() or None
