"""UI: 🧮 Cirsmas novērtējums — summu kalkulators cirsmas novērtējuma PDF.

Nav atsevišķa lapa — to izsauc views/mezs.py kā trešo datu avota režīmu.
"""
from __future__ import annotations

import hashlib

import pandas as pd
import streamlit as st

from cirsma.novertejums import (
    FORMATS_PARDODAMA,
    RADITAJI,
    SUGU_SUMMEJAMAS,
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
def _nolasit(dati: bytes, fails: str, _hash: str) -> list[Novertejums]:
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
            "Ievelc vienu vai vairākus **cirsmas novērtējuma** PDF — Mežvērtes (viens nogabals) vai "
            "pārdodamo cirsmu (daudz cirsmu vienā PDF). Sistēma saskaita nogabalus un platības; "
            "ar ⚙️ vari ieslēgt arī vērtības, krājas, sortimentus u.c."
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
            novertejumi.extend(_nolasit(dati, f.name, hashlib.md5(dati).hexdigest()))
        except Exception as e:  # noqa: BLE001 — rādām lietotājam, turpinām ar pārējiem
            st.error(f"**{f.name}**: neizdevās nolasīt — {e}")
    if not novertejumi:
        return

    dup = dublikati(novertejumi)
    if dup:
        st.warning("Tas pats nogabals ir vairākās cirsmās (summās ieskaitīts katru reizi): "
                   + "; ".join(dup))
    for n in novertejumi:
        for b in n.bridinajumi:
            st.warning(f"**{n.avots}**: {b}")

    novertejumi = kartot(novertejumi)
    rindas = [rindas_vertibas(n) for n in novertejumi]
    kop = kopsummas(rindas)

    bez_eur = sum(1 for r in rindas if r["vertiba_kopa"] is None)
    if bez_eur and any(RADITAJI[k].get("eur") for k in raditaji):
        if bez_eur == len(rindas):
            st.info("Šajos PDF nav € vērtību (pārdodamo cirsmu formātā ir tikai apjomi m³).")
        else:
            st.info(f"{bez_eur} no {len(rindas)} cirsmām nav € vērtību — € summās tās nav iekļautas.")

    # --- Kopsummas ---
    st.subheader("Kopā")
    pa_rindai = 5
    for i in range(0, len(raditaji), pa_rindai):
        kolonnas = st.columns(pa_rindai)
        for kol, k in zip(kolonnas, raditaji[i:i + pa_rindai]):
            kol.metric(_kol(k), fmt(kop.get(k), RADITAJI[k]["dec"]))

    pa_ipasumiem: dict[str, int] = {}
    for n, r in zip(novertejumi, rindas):
        pa_ipasumiem[n.ipasuma_nosaukums] = pa_ipasumiem.get(n.ipasuma_nosaukums, 0) + r["nogabali"]
    st.caption(" · ".join(f"**{k}**: {v} nog." for k, v in pa_ipasumiem.items()))

    # --- Pa cirsmām / nogabaliem ---
    st.subheader("Pa nogabaliem")
    ir_cirsmu_nr = any(n.formats == FORMATS_PARDODAMA for n in novertejumi)
    tabulas = [k for k in raditaji if k not in ("nogabali", "cirsmas")]
    ieraksti = []
    for n, r in zip(novertejumi, rindas):
        ier = {"Īpašums": n.ipasuma_nosaukums}
        if ir_cirsmu_nr:
            ier["Cirsma"] = f"nr. {n.cirsmas_nr}" if n.cirsmas_nr else ""
        ier["Nogabals"] = n.nosaukums
        ier["Nog. sk."] = r["nogabali"]
        ier.update({_kol(k): r.get(k) for k in tabulas})
        ieraksti.append(ier)
    kop_ier = {"Īpašums": "KOPĀ"}
    if ir_cirsmu_nr:
        kop_ier["Cirsma"] = f"{len(novertejumi)} cirsm."
    kop_ier["Nogabals"] = ""
    kop_ier["Nog. sk."] = kop["nogabali"]
    kop_ier.update({_kol(k): kop.get(k) for k in tabulas})
    df = pd.DataFrame(ieraksti + [kop_ier])

    formati = {_kol(k): (lambda v, d=RADITAJI[k]["dec"]: fmt(v, d)) for k in tabulas}
    formati["Nog. sk."] = lambda v: fmt(v, 0)
    stils = df.style.format(formati, na_rep="—").apply(
        lambda r: ["font-weight: 700"] * len(r) if r["Īpašums"] == "KOPĀ" else [""] * len(r),
        axis=1)
    st.dataframe(stils, hide_index=True, use_container_width=True)

    # --- Pa sugām ---
    if st.session_state.get("nov_radit_sugas"):
        st.subheader("Pa sugām (visas cirsmas kopā)")
        sugas = [s for n in novertejumi for s in n.sugas]
        if sugas:
            sdf = (pd.DataFrame(sugas).reindex(columns=["suga", *SUGU_SUMMEJAMAS])
                   .groupby("suga", sort=False)[SUGU_SUMMEJAMAS].sum(min_count=1)
                   .sort_values("kraja", ascending=False).reset_index())
            sdf["dala"] = sdf["kraja"] / sdf["kraja"].sum() * 100
            if sdf["p_malka"].isna().all():
                sdf = sdf.drop(columns="p_malka")
            nosaukumi = {"suga": "Suga", "skaits": "Koku skaits", "kraja": "Krāja, m³",
                         "lietkoksne": "Lietkoksne, m³", "resna": "Resnā", "videja": "Vidējā",
                         "tieva": "Tievā", "p_malka": "P.malka", "malka": "Malka",
                         "atlikumi": "Atlikumi", "pardosanai": "Pārdošanai, m³", "dala": "Daļa, %"}
            sdf = sdf.rename(columns=nosaukumi)
            sf = {c: (lambda v: fmt(v, 2)) for c in sdf.columns[1:]}
            sf["Koku skaits"] = lambda v: fmt(v, 0)
            sf["Daļa, %"] = lambda v: fmt(v, 1)
            st.dataframe(sdf.style.format(sf, na_rep="—"), hide_index=True, use_container_width=True)
        else:
            st.caption("Sugu dati netika nolasīti.")

    csv = df.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig")
    st.download_button("⬇️ Lejupielādēt CSV", csv,
                       file_name="cirsmas_novertejums_kopsavilkums.csv", mime="text/csv")
