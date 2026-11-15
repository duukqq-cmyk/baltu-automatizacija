"""Kopīgi Streamlit palīgi: aktīvais cenrādis sesijā, glabātuve, lietotāja vārds."""
from __future__ import annotations

import copy

import streamlit as st

from cirsma.cenradis import (
    ATSLEGA, ATSLEGA_VARIANTI, SADALAS, Cenradis, CenrazaVarianti,
)
from cirsma.cenradis import (
    SADALU_NOSAUKUMI as CENRAZA_SADALAS,
)


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


def ielade_saglabatos_variantus() -> tuple[CenrazaVarianti, dict | None]:
    """(varianti no datubāzes vai noklusējums, metadati {mainits, autors}).

    Ja ir tikai vecais vienotais cenrādis (ATSLEGA), tas kļūst par variantu "Pamata" visās sadaļās.
    """
    g = glabatuve()
    ier = g.iestatijums(ATSLEGA_VARIANTI) if g else None
    if ier:
        return CenrazaVarianti.no_json(ier["vertiba"]), {"mainits": ier["mainits"], "autors": ier["autors"]}
    vecais = g.iestatijums(ATSLEGA) if g else None
    if vecais:
        return (CenrazaVarianti.no_cenradis(Cenradis.no_json(vecais["vertiba"])),
                {"mainits": vecais["mainits"], "autors": vecais["autors"]})
    return CenrazaVarianti.no_cenradis(Cenradis()), None


def _sakt_sesiju() -> None:
    ss = st.session_state
    if "cenradis_varianti_saglabatie" not in ss:
        v, meta = ielade_saglabatos_variantus()
        ss.cenradis_varianti = copy.deepcopy(v)
        ss.cenradis_varianti_saglabatie = copy.deepcopy(v)
        ss.cenradis_meta = meta
        ss.cenradis_izvele = v.noklusejuma_izvele()
        ss.setdefault("cenradis_versija", 0)


def varianti() -> CenrazaVarianti:
    """Sesijas (rediģējamie) cenrāža varianti."""
    _sakt_sesiju()
    return st.session_state.cenradis_varianti


def izvele() -> dict[str, str]:
    """Kurš variants katrai sadaļai izvēlēts šajā sesijā (pēc noklusējuma — noklusējuma varianti)."""
    _sakt_sesiju()
    ss = st.session_state
    v = ss.cenradis_varianti
    for s in SADALAS:
        if ss.cenradis_izvele.get(s) not in v.sadalas[s]["varianti"]:
            ss.cenradis_izvele[s] = v.noklusejums(s)
    return ss.cenradis_izvele


def aktivais_cenradis() -> Cenradis:
    """Cenrādis aprēķiniem: katrai sadaļai — šajā sesijā izvēlētais variants.

    Ja atvērts saglabāts darbs ar savām cenām, tiek lietotas tās (līdz lietotājs atgriežas pie variantiem).
    """
    _sakt_sesiju()
    ss = st.session_state
    if ss.get("cenradis_ieladets") is not None:
        return ss.cenradis_ieladets
    return ss.cenradis_varianti.kompozicija(izvele())


def cenradis_mainits() -> bool:
    """Vai sesijas varianti atšķiras no saglabātajiem."""
    _sakt_sesiju()
    ss = st.session_state
    return ss.cenradis_varianti.uz_json() != ss.cenradis_varianti_saglabatie.uz_json()


def _mainit_izveli(sadala: str, atsl: str) -> None:
    st.session_state.cenradis_izvele[sadala] = st.session_state[atsl]


def cenradis_statuss_sanjosla() -> None:
    """Cenrāža statuss sānjoslā + ātra varianta izvēle sadaļām, kurām ir vairāki varianti."""
    _sakt_sesiju()
    ss = st.session_state
    v, izv = varianti(), izvele()
    meta = ss.get("cenradis_meta")
    with st.sidebar:
        st.markdown(":material/euro: **Cenrādis**")
        if ss.get("cenradis_ieladets") is not None:
            st.caption(":material/history: Lietotas saglabātā darba cenas")
            if st.button("Atgriezties pie variantiem", key="sb_cen_atgriezties", use_container_width=True):
                ss.cenradis_ieladets = None
                st.rerun()
        else:
            for s in SADALAS:
                if len(v.nosaukumi(s)) < 2:
                    continue
                atsl = f"sb_izv_{s}"
                ss[atsl] = izv[s]
                st.selectbox(CENRAZA_SADALAS[s], v.nosaukumi(s), key=atsl,
                             format_func=lambda n, s=s: n + (" ★" if n == v.noklusejums(s) else ""),
                             on_change=_mainit_izveli, args=(s, atsl))
            atskiras = [CENRAZA_SADALAS[s] for s in SADALAS if izv[s] != v.noklusejums(s)]
            if cenradis_mainits():
                st.caption("✎ Ir nesaglabātas izmaiņas lapā Cenrādis")
            elif atskiras:
                st.caption("Šajā sesijā ne-noklusējuma varianti: " + ", ".join(atskiras))
            elif meta:
                st.caption(f"Noklusējuma varianti · saglabāts {meta['mainits'][:10]}"
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
