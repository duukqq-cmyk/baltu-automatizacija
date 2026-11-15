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
        st.markdown(":material/euro: **Cenrādis**")
        if cenradis_mainits():
            st.caption("✎ Šajā sesijā mainīts (nav saglabāts kā noklusējums)")
        elif meta:
            st.caption(f"Saglabātais noklusējums · {meta['mainits'][:10]}"
                       + (f" · {meta['autors']}" if meta.get("autors") else ""))
        else:
            st.caption("Rūpnīcas noklusējums (vēl nav saglabāts)")
        st.page_link("views/cenradis.py", label="Mainīt cenas, sortimentus, izdevumus", icon=":material/tune:")


def lietotajs() -> str | None:
    """Lietotāja vārds izmaiņu vēsturei (līdz būs pieteikšanās)."""
    return (st.session_state.get("lietotaja_vards") or "").strip() or None


# ---------------------------------------------------------------------------
# Saglabāšana — kopīgs bloks visām sadaļām (Karte, Cirsmas novērtējums, Līgumi)
# ---------------------------------------------------------------------------

SADALU_NOSAUKUMI = {
    "pdf": "Meža inventarizācija", "karte": "Karte", "novertejums": "Cirsmas novērtējums",
    "ligumi": "Līgumi",
}


def faili_uz_json(faili: list[tuple[str, bytes]]) -> list[dict]:
    import base64
    return [{"nosaukums": n, "b64": base64.b64encode(b).decode()} for n, b in faili]


def faili_no_json(d: list[dict] | None) -> list[tuple[str, bytes]]:
    import base64
    return [(x["nosaukums"], base64.b64decode(x["b64"])) for x in (d or [])]


def saglabasanas_bloks(veids: str, *, noklusetais: str, kadastrs: str | None,
                       dati_fn, kopsavilkums: dict, pdf: tuple[str, bytes] | None = None,
                       virsraksts: str = "Saglabāt") -> None:
    """Nosaukums + piezīmes + Saglabāt / Saglabāt izmaiņas / Saglabāt kā jaunu.

    dati_fn() -> dict ar visu, kas vajadzīgs atvēršanai (izsauc tikai saglabājot).
    Ja darbs atvērts no "Saglabātie", st.session_state[f"pv_ielad_{veids}"] = {id, nosaukums, piezimes}.
    """
    ss = st.session_state
    atsl = f"pv_ielad_{veids}"
    ielad = ss.get(atsl)
    st.subheader(f":material/save: {virsraksts}")
    k1, k2 = st.columns([2, 3])
    nosaukums = k1.text_input("Nosaukums", value=(ielad or {}).get("nosaukums") or noklusetais,
                              key=f"pv_nos_{veids}_{(ielad or {}).get('id', 'jauns')}")
    piezimes = k2.text_area("Piezīmes", value=(ielad or {}).get("piezimes", ""), height=68,
                            key=f"pv_piez_{veids}_{(ielad or {}).get('id', 'jauns')}")
    g = glabatuve()

    def _saglabat(parrakstit: bool) -> None:
        d = dict(dati_fn(), piezimes=piezimes, versija=1)
        id_ = g.saglabat_priekvertejumu(
            kadastrs=kadastrs, nosaukums=nosaukums, avots=veids, dati=d, kopsavilkums=kopsavilkums,
            autors=lietotajs(), pdf=pdf[1] if pdf else None, pdf_nosaukums=pdf[0] if pdf else None,
            id_=ielad["id"] if (parrakstit and ielad) else None)
        ss[atsl] = {"id": id_, "nosaukums": nosaukums, "piezimes": piezimes}
        st.toast(f"Saglabāts: {nosaukums}", icon=":material/save:")

    b1, b2, b3 = st.columns(3)
    if ielad:
        b1.button(":material/save: Saglabāt izmaiņas", type="primary", use_container_width=True,
                  disabled=g is None, on_click=_saglabat, args=(True,), key=f"pv_s1_{veids}",
                  help="Pārraksta atvērto saglabāto darbu")
        b2.button(":material/library_add: Saglabāt kā jaunu", use_container_width=True, disabled=g is None,
                  on_click=_saglabat, args=(False,), key=f"pv_s2_{veids}")
        if b3.button(":material/close: Aizvērt saglabāto", use_container_width=True, key=f"pv_s3_{veids}",
                     help="Turpmāk saglabāt kā jaunu darbu"):
            ss.pop(atsl, None)
            st.rerun()
    else:
        b1.button(":material/save: Saglabāt", type="primary", use_container_width=True, disabled=g is None,
                  on_click=_saglabat, args=(False,), key=f"pv_s1_{veids}",
                  help="Atrodams lapā Saglabātie (meklē pēc kadastra numura vai nosaukuma)")
