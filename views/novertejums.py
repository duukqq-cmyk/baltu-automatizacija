"""UI: 🌲 Cirsmas novērtējums — summu kalkulators Mežvērtes cirsmas novērtējuma PDF.

Nav atsevišķa lapa — to izsauc views/mezs.py kā trešo datu avota režīmu.
"""
from __future__ import annotations

import hashlib

import pandas as pd
import streamlit as st

from cirsma.novertejums import (
    RADITAJI,
    Novertejums,
    dublikati,
    fmt,
    kartot,
    kopsummas,
    parse_novertejums_pdf,
    rindas_vertibas,
)

_SEC = list(RADITAJI)


@st.cache_data(show_spinner=False)
def _nolasit(dati: bytes, fails: str, _hash: str) -> Novertejums:
    return parse_novertejums_pdf(dati, fails)


def _iestatijumi() -> list[str]:
    ss = st.session_state
    for k in _SEC:
        ss.setdefault(f"nov_radit_{k}", RADITAJI[k]["default"])
    ss.setdefault("nov_radit_sugas", False)

    with st.popover("⚙️", help="Kuras summas rādīt"):
        st.markdown("**Rādāmās summas**")
        for k in _SEC:
            r = RADITAJI[k]
            st.toggle(f"{r['label']} ({r['unit']})", key=f"nov_radit_{k}",
                      disabled=r.get("locked", False))
        st.divider()
        st.toggle("Sadalījums pa sugām", key="nov_radit_sugas")
        if st.button("Atjaunot noklusējumu", use_container_width=True):
            for k in _SEC:
                ss[f"nov_radit_{k}"] = RADITAJI[k]["default"]
            ss["nov_radit_sugas"] = False
            st.rerun()
    return [k for k in _SEC if ss[f"nov_radit_{k}"]]


def _kol(k: str) -> str:
    return f"{RADITAJI[k]['label']}, {RADITAJI[k]['unit']}"


def render() -> None:
    teksts, zobrats = st.columns([20, 1])
    with teksts:
        st.caption(
            "Ievelc vienu vai vairākus Mežvērtes **cirsmas novērtējuma** PDF (viens fails = viens "
            "nogabals). Sistēma saskaita nogabalus un platības; ar ⚙️ vari ieslēgt arī vērtības, "
            "krājas, sortimentus u.c."
        )
    with zobrats:
        raditaji = _iestatijumi()

    faili = st.file_uploader("Cirsmas novērtējuma PDF", type=["pdf"],
                             accept_multiple_files=True, key="nov_faili")
    if not faili:
        st.info("⬆️ Ievelc šeit cirsmas novērtējuma PDF failus (var vairākus uzreiz).")
        return

    novertejumi: list[Novertejums] = []
    for f in faili:
        dati = f.getvalue()
        try:
            novertejumi.append(_nolasit(dati, f.name, hashlib.md5(dati).hexdigest()))
        except Exception as e:  # noqa: BLE001 — rādām lietotājam, turpinām ar pārējiem
            st.error(f"**{f.name}**: neizdevās nolasīt — {e}")
    if not novertejumi:
        return

    dup = dublikati(novertejumi)
    if dup:
        st.warning("Tas pats nogabals ielādēts vairākkārt (summās ieskaitīts katru reizi): "
                   + "; ".join(dup))
    for n in novertejumi:
        for b in n.bridinajumi:
            st.warning(f"**{n.fails}**: {b}")

    novertejumi = kartot(novertejumi)
    rindas = [rindas_vertibas(n) for n in novertejumi]
    kop = kopsummas(rindas)

    # --- Kopsummas ---
    st.subheader("Kopā")
    pa_rindai = 5
    for i in range(0, len(raditaji), pa_rindai):
        kolonnas = st.columns(pa_rindai)
        for kol, k in zip(kolonnas, raditaji[i:i + pa_rindai]):
            kol.metric(_kol(k), fmt(kop.get(k), RADITAJI[k]["dec"]))

    pa_ipasumiem: dict[str, list[str]] = {}
    for n in novertejumi:
        pa_ipasumiem.setdefault(f"{n.saimnieciba or '—'} ({n.kadastrs})", []).append(n.nosaukums)
    st.caption(" · ".join(f"**{k}**: {', '.join(v)}" for k, v in pa_ipasumiem.items()))

    # --- Pa nogabaliem ---
    st.subheader("Pa nogabaliem")
    tabulas = [k for k in raditaji if k != "nogabali"]
    ieraksti = []
    for n, r in zip(novertejumi, rindas):
        ier = {"Saimniecība": n.saimnieciba, "Kadastrs": n.kadastrs, "Nogabals": n.nosaukums}
        ier.update({_kol(k): r.get(k) for k in tabulas})
        ieraksti.append(ier)
    kop_ier = {"Saimniecība": "KOPĀ", "Kadastrs": "", "Nogabals": f"{len(novertejumi)} nog."}
    kop_ier.update({_kol(k): kop.get(k) for k in tabulas})
    df = pd.DataFrame(ieraksti + [kop_ier])

    stils = df.style.format(
        {_kol(k): (lambda v, d=RADITAJI[k]["dec"]: fmt(v, d)) for k in tabulas}
    ).apply(lambda r: ["font-weight: 700"] * len(r) if r["Saimniecība"] == "KOPĀ"
            else [""] * len(r), axis=1)
    st.dataframe(stils, hide_index=True, use_container_width=True)

    # --- Pa sugām ---
    if st.session_state.get("nov_radit_sugas"):
        st.subheader("Pa sugām (visi nogabali kopā)")
        sugas = [s for n in novertejumi for s in n.sugas]
        if sugas:
            sdf = (pd.DataFrame(sugas)
                   .groupby("suga", sort=False)[["skaits", "kraja", "lietkoksne", "resna", "videja",
                                                 "tieva", "p_malka", "malka", "atlikumi", "pardosanai"]]
                   .sum().sort_values("kraja", ascending=False).reset_index())
            sdf["dala"] = sdf["kraja"] / sdf["kraja"].sum() * 100
            sdf.columns = ["Suga", "Koku skaits", "Krāja, m³", "Lietkoksne, m³", "Resnā", "Vidējā",
                           "Tievā", "P.malka", "Malka", "Atlikumi", "Pārdošanai, m³", "Daļa, %"]
            formati = {c: (lambda v: fmt(v, 2)) for c in sdf.columns[1:]}
            formati["Koku skaits"] = lambda v: fmt(v, 0)
            formati["Daļa, %"] = lambda v: fmt(v, 1)
            st.dataframe(sdf.style.format(formati), hide_index=True, use_container_width=True)
        else:
            st.caption("Sugu dati netika nolasīti.")

    csv = df.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig")
    st.download_button("⬇️ Lejupielādēt CSV", csv,
                       file_name="cirsmas_novertejums_kopsavilkums.csv", mime="text/csv")
