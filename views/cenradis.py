"""Cenrādis: sortimentu cenas un īpatsvari, izdevumi, noteikumi, novērtējuma kartējums.

Izmaiņas strādā uzreiz šajā sesijā (visās sadaļās). "Saglabāt kā noklusējumu"
ieraksta tās datubāzē — tad tās redz visi lietotāji, un tiek saglabāta vēsture.
"""
from __future__ import annotations

import copy
from dataclasses import fields

import pandas as pd
import streamlit as st

from cirsma.cenradis import ATSLEGA, NOV_KOLONNAS, VEIDI, Cenradis
from cirsma.cirtes import CIRTES_NOSAUKUMI, IZLASES, KAILCIRTE, Noteikumi
from cirsma.sortiment import MATRICAS_KOLONNA, CITI
from views.kopigi import aktivais_cenradis, cenradis_mainits, glabatuve, lietotajs

c = aktivais_cenradis()
versija = st.session_state.cenradis_versija
bazes: Cenradis = st.session_state.setdefault("cenradis_bazes", copy.deepcopy(c))

st.title("💶 Cenrādis un noteikumi")
st.caption("Cenas, sortimentu īpatsvari un izdevumi visām sadaļām: Meža inventarizācija, Karte un "
           "Cirsmas novērtējums. Izmaiņas strādā uzreiz šajā sesijā; lai tās kļūtu par noklusējumu "
           "visiem, spied **Saglabāt kā noklusējumu**.")

KOLONNU_NOS = {"P": "Priede", "E": "Egle", "B": "Bērzs", "Ma": "Melnalksnis", "A": "Apse",
               "Ba": "Baltalksnis", "Oz/Os": "Ozols/osis", CITI: "Citas sugas"}


def _matrica_df(m: dict) -> pd.DataFrame:
    return pd.DataFrame([{"Suga": k, "Sortiments": s, "Cena EUR/m³": float(cena),
                          "Īpatsvars %": round(ip * 100, 2)}
                         for k, sort in m.items() for s, (cena, ip) in sort.items()])


def _df_matrica(df: pd.DataFrame) -> dict:
    m: dict = {}
    for r in df.dropna(subset=["Suga", "Sortiments"]).to_dict("records"):
        suga, sort = str(r["Suga"]).strip(), str(r["Sortiments"]).strip()
        if not suga or not sort:
            continue
        cena = float(r["Cena EUR/m³"] or 0)
        ip = float(r["Īpatsvars %"] or 0) / 100
        m.setdefault(suga, {})[sort] = (cena, ip)
    return m


def _matricas_redaktors(veids: str) -> None:
    kolonnas = list(dict.fromkeys([*MATRICAS_KOLONNA.values(), CITI]))
    sakuma_df = _matrica_df(bazes.matricas[veids])
    df = st.data_editor(
        sakuma_df, key=f"cen_m_{veids}_{versija}", height=min(36 * len(sakuma_df) + 80, 1200),
        num_rows="dynamic", hide_index=True, use_container_width=True,
        column_config={
            "Suga": st.column_config.SelectboxColumn(
                options=kolonnas, required=True,
                help="Matricas kolonna: " + ", ".join(f"{k} = {v}" for k, v in KOLONNU_NOS.items())),
            "Sortiments": st.column_config.TextColumn(required=True),
            "Cena EUR/m³": st.column_config.NumberColumn(min_value=0.0, step=1.0, format="%.2f"),
            "Īpatsvars %": st.column_config.NumberColumn(min_value=0.0, max_value=100.0, step=1.0,
                                                         format="%.1f"),
        },
    )
    c.matricas[veids] = _df_matrica(df)
    summas = df.groupby("Suga")["Īpatsvars %"].sum()
    slikti = {k: v for k, v in summas.items() if abs(v - 100) > 0.05}
    if slikti:
        st.warning("Īpatsvaru summa nav 100 %: " + ", ".join(f"{k} {v:.1f} %" for k, v in slikti.items()))
    else:
        st.caption("✓ Visām sugām īpatsvaru summa ir 100 %.")


cilnes = st.tabs(["🪓 Kailcirte", "🌿 Kopšanas cirte", "🌳 Izlases cirte", "💸 Izdevumi un peļņa",
                  "🧮 Novērtējuma kartējums", "📏 Noteikumi", "🕓 Vēsture"])

with cilnes[0]:
    st.caption("Sortimentu iznākums kailcirtē. Šīs cenas izmanto arī cirsmas novērtējuma kalkulators.")
    _matricas_redaktors(KAILCIRTE)
with cilnes[1]:
    st.caption("Kopšanas cirtē iznāk galvenokārt tara, papīrmalka un malka.")
    _matricas_redaktors("kopsana")
with cilnes[2]:
    st.caption("Izlases cirtē cērt arī resnos kokus — iekļauj zāģbaļķus, finieri u.c.")
    if st.button("Kopēt no kailcirtes", key="kop_izl"):
        c.matricas[IZLASES] = copy.deepcopy(c.matricas[KAILCIRTE])
        st.session_state.cenradis_bazes = copy.deepcopy(c)
        st.session_state.cenradis_versija += 1
        st.rerun()
    _matricas_redaktors(IZLASES)

with cilnes[3]:
    st.caption("Izdevumi EUR uz izcirsto m³ katram cirtes veidam. Kopšanā ciršana un pievešana "
               "parasti ir dārgāka par m³ nekā kailcirtē.")
    pozicijas = list(dict.fromkeys(p for v in VEIDI for p in bazes.izdevumi.get(v, {})))
    df = pd.DataFrame([{"Pozīcija": p, **{CIRTES_NOSAUKUMI[v]: bazes.izdevumi.get(v, {}).get(p, 0.0)
                                         for v in VEIDI}} for p in pozicijas])
    df = st.data_editor(df, key=f"cen_izd_{versija}", num_rows="dynamic", hide_index=True,
                        use_container_width=True,
                        column_config={CIRTES_NOSAUKUMI[v]: st.column_config.NumberColumn(
                            min_value=0.0, step=0.5, format="%.2f") for v in VEIDI})
    for v in VEIDI:
        c.izdevumi[v] = {str(r["Pozīcija"]): float(r[CIRTES_NOSAUKUMI[v]] or 0)
                         for r in df.dropna(subset=["Pozīcija"]).to_dict("records")}
    c.pelnas_rezerve = st.slider("Peļņas rezerve, %", 0, 50, int(round(bazes.pelnas_rezerve * 100)),
                                 key=f"cen_pelna_{versija}") / 100

with cilnes[4]:
    st.caption("Kā cirsmas novērtējuma kolonnas (Resnā, Vidējā, Tievā …) pārvēršas sortimentos. "
               "Cenas ņem no kailcirtes cenrāža. Pārdodamo cirsmu PDF nav atsevišķas P. malkas — "
               "tur Tievā tiek sadalīta starp Tievās un P. malkas sortimentiem pēc kailcirtes īpatsvariem.")
    visi_sort = sorted({s for sort in c.matricas[KAILCIRTE].values() for s in sort})
    df = pd.DataFrame([{"Suga": k, **{NOV_KOLONNAS[l]: kart.get(l, "") for l in NOV_KOLONNAS}}
                       for k, kart in bazes.kartejums.items()])
    df = st.data_editor(df, key=f"cen_kart_{versija}", hide_index=True, use_container_width=True,
                        disabled=["Suga"],
                        column_config={NOV_KOLONNAS[l]: st.column_config.SelectboxColumn(options=visi_sort)
                                       for l in NOV_KOLONNAS})
    c.kartejums = {r["Suga"]: {l: r[NOV_KOLONNAS[l]] for l in NOV_KOLONNAS if r[NOV_KOLONNAS[l]]}
                   for r in df.to_dict("records")}

with cilnes[5]:
    st.caption("Ciršanas noteikumi. Sausieņi: sils, mētrājs, lāns, damaksnis, vēris, gārša; pārējie "
               "(slapjaiņi, purvaiņi, āreņi, kūdreņi) — mazākais limits.")
    nt_b = bazes.noteikumi
    k1, k2 = st.columns(2)
    jauni = dict(
        max_sausieni_ha=k1.number_input("Max kailcirte sausieņos, ha", 0.1, 50.0, nt_b.max_sausieni_ha, 0.5,
                                        key=f"nt1_{versija}"),
        max_citi_ha=k1.number_input("Max kailcirte pārējos meža tipos, ha", 0.1, 50.0, nt_b.max_citi_ha, 0.5,
                                    key=f"nt2_{versija}"),
        atdalosa_josla_ha=k1.number_input("Atdalošā josla starp kailcirtēm, ha", 0.0, 5.0,
                                          nt_b.atdalosa_josla_ha, 0.1, key=f"nt3_{versija}"),
        min_kailcirte_ha=k1.number_input("Min nākamās kailcirtes platība, ha", 0.0, 5.0,
                                         nt_b.min_kailcirte_ha, 0.1, key=f"nt4_{versija}"),
        g_rezerve=k2.number_input("Rezerve virs Gmin / Gkrit, m²/ha", 0.0, 5.0, nt_b.g_rezerve, 0.5,
                                  key=f"nt5_{versija}"),
        min_izcertamais_g=k2.number_input("Min izcērtamais šķērslaukums, m²/ha", 0.0, 20.0,
                                          nt_b.min_izcertamais_g, 0.5, key=f"nt6_{versija}",
                                          help="Mazāk neatmaksājas dzīt tehniku mežā"),
        min_g_izlases=k2.checkbox("Min izcērtamais G attiecas arī uz izlases cirti", nt_b.min_g_izlases,
                                  key=f"nt7_{versija}"),
    )
    c.noteikumi = Noteikumi(**jauni)
    st.caption("Baltalksnis: kailcirte, ja ≥ 25 g. vai vid. caurmērs ≥ 16 cm. Kopšanas cirte: "
               "G − (Gmin + rezerve), izlases: G − (Gkrit + rezerve); apjoms = izcērtamais G × "
               "veidaugstums × platība.")

g = glabatuve()
with cilnes[6]:
    if g is None:
        st.info("Datubāze nav pieejama — vēsture netiek glabāta.")
    else:
        vest = g.iestatijuma_vesture(ATSLEGA)
        if not vest:
            st.info("Cenrādis vēl nav saglabāts.")
        for ieraksts in vest:
            k1, k2 = st.columns([4, 1])
            k1.markdown(f"**{ieraksts['mainits'].replace('T', ' ')[:16]}** · {ieraksts['autors'] or 'nav norādīts'}")
            if k2.button("Ielādēt", key=f"vest_{ieraksts['id']}"):
                st.session_state.cenradis = Cenradis.no_json(ieraksts["vertiba"])
                st.session_state.cenradis_bazes = copy.deepcopy(st.session_state.cenradis)
                st.session_state.cenradis_versija += 1
                st.rerun()

# --- Saglabāšana -------------------------------------------------------------
st.divider()
for b in c.bridinajumi():
    st.warning(b)
mainits = cenradis_mainits()
st.caption("✎ Šajā sesijā ir nesaglabātas izmaiņas." if mainits else "Sesijas cenrādis sakrīt ar saglabāto.")
b1, b2, b3 = st.columns(3)
if b1.button("💾 Saglabāt kā noklusējumu visiem", type="primary", disabled=g is None or not mainits,
             use_container_width=True):
    g.saglabat_iestatijumu(ATSLEGA, c.uz_json(), lietotajs())
    st.session_state.cenradis_saglabatais = copy.deepcopy(c)
    st.session_state.cenradis_meta = g.iestatijums(ATSLEGA) and {
        k: v for k, v in g.iestatijums(ATSLEGA).items() if k != "vertiba"}
    st.success("Saglabāts.")
    st.rerun()
if b2.button("↺ Atjaunot saglabāto", disabled=not mainits, use_container_width=True):
    st.session_state.cenradis = copy.deepcopy(st.session_state.cenradis_saglabatais)
    st.session_state.cenradis_bazes = copy.deepcopy(st.session_state.cenradis)
    st.session_state.cenradis_versija += 1
    st.rerun()
if b3.button("↺ Rūpnīcas noklusējums", use_container_width=True,
             help="Sākotnējās cenas (pamācības matrica). Lai tās kļūtu par noklusējumu, pēc tam saglabā."):
    st.session_state.cenradis = Cenradis()
    st.session_state.cenradis_bazes = copy.deepcopy(st.session_state.cenradis)
    st.session_state.cenradis_versija += 1
    st.rerun()
