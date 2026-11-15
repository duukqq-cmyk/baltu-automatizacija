"""Cenrādis ar variantiem: katrai cilnei (sadaļai) vairāki nosaukti varianti, viens — noklusējums.

* Izvēlētais variants strādā uzreiz šajā sesijā (visās sadaļās; ātri maināms arī sānjoslā).
* ★ Noklusējums — variants, ko pēc noklusējuma lieto visi.
* "Saglabāt" ieraksta visus variantus datubāzē (ar vēsturi).
"""
from __future__ import annotations

import copy
from dataclasses import asdict

import pandas as pd
import streamlit as st

from cirsma.cenradis import (
    ATSLEGA_VARIANTI, NOV_KOLONNAS, SADALAS, SADALU_NOSAUKUMI, VEIDI, Cenradis, CenrazaVarianti,
    sadalas_dati,
)
from cirsma.cirtes import CIRTES_NOSAUKUMI, KAILCIRTE, Noteikumi
from cirsma.sortiment import CITI, MATRICAS_KOLONNA
from views.kopigi import aktivais_cenradis, cenradis_mainits, glabatuve, izvele, lietotajs, varianti

ss = st.session_state
v: CenrazaVarianti = varianti()
izv = izvele()
versija = ss.cenradis_versija
ss.setdefault("cen_bazes", {})

st.title(":material/euro: Cenrādis un noteikumi")
st.caption("Katrā cilnē var būt vairāki varianti (piem., “Pamata”, “Ziema”, “Pircējs X”). Izvēlētais "
           "variants strādā uzreiz šajā sesijā; ★ noklusējumu pēc noklusējuma lieto visi. Lai izmaiņas "
           "paliktu, spied **Saglabāt**.")
if ss.get("cenradis_ieladets") is not None:
    k1, k2 = st.columns([4, 1])
    k1.info("Šajā sesijā aprēķinos tiek lietotas atvērtā saglabātā darba cenas, nevis šie varianti.")
    if k2.button("Atgriezties pie variantiem", use_container_width=True):
        ss.cenradis_ieladets = None
        st.rerun()

KOLONNU_NOS = {"P": "Priede", "E": "Egle", "B": "Bērzs", "Ma": "Melnalksnis", "A": "Apse",
               "Ba": "Baltalksnis", "Oz/Os": "Ozols/osis", CITI: "Citas sugas"}


def _parzimet() -> None:
    ss.cenradis_versija += 1
    ss.cen_bazes = {}


def _bazes(sadala: str) -> dict:
    """Redaktora sākuma dati — nemainīgi līdz nākamajai versijai (citādi pievienotās rindas dublētos)."""
    atsl = f"{sadala}|{izv[sadala]}|{versija}"
    if atsl not in ss.cen_bazes:
        ss.cen_bazes[atsl] = copy.deepcopy(v.sadalas[sadala]["varianti"][izv[sadala]])
    return ss.cen_bazes[atsl]


def _saglabat_datus(sadala: str, dati: dict) -> None:
    v.atjaunot_dati(sadala, izv[sadala], dati)


# --- Varianta josla katrā cilnē ------------------------------------------------

def _variantu_josla(sadala: str) -> None:
    nosaukumi = v.nosaukumi(sadala)
    nokl = v.noklusejums(sadala)
    aktivs = izv[sadala]
    k = st.columns([2.6, 1.3, 1.1, 1.25, 1.0, 1.5], vertical_alignment="bottom")
    atsl = f"cen_izv_{sadala}_{versija}"

    def _mainit():
        izv[sadala] = ss[atsl]

    k[0].selectbox("Variants", nosaukumi, index=nosaukumi.index(aktivs), key=atsl, on_change=_mainit,
                   format_func=lambda n: n + ("  ★ noklusējums" if n == nokl else ""))
    if k[1].button(":material/star: Noklusējums", key=f"cen_nokl_{sadala}", use_container_width=True,
                   disabled=aktivs == nokl, help="Šo variantu pēc noklusējuma lietos visi (pēc saglabāšanas)"):
        v.iestatit_noklusejumu(sadala, aktivs)
        st.rerun()
    with k[2].popover(":material/add: Jauns", help="Jauns variants (kopija no izvēlētā)", use_container_width=True):
        jauns = st.text_input("Jauna varianta nosaukums", key=f"cen_jauns_{sadala}_{versija}",
                              placeholder="piem., Ziema 2026")
        st.caption(f"Tiks nokopētas varianta “{aktivs}” vērtības.")
        if st.button("Izveidot", key=f"cen_jauns_b_{sadala}", type="primary"):
            try:
                v.izveidot(sadala, jauns, no=aktivs)
                izv[sadala] = jauns.strip()
                _parzimet()
                st.rerun()
            except ValueError as e:
                st.error(str(e))
    with k[3].popover(":material/edit: Pārdēvēt", help="Pārdēvēt variantu", use_container_width=True):
        jaunais = st.text_input("Jaunais nosaukums", value=aktivs, key=f"cen_pard_{sadala}_{versija}")
        if st.button("Pārdēvēt", key=f"cen_pard_b_{sadala}", type="primary"):
            try:
                v.parsaukt(sadala, aktivs, jaunais)
                izv[sadala] = jaunais.strip() or aktivs
                _parzimet()
                st.rerun()
            except ValueError as e:
                st.error(str(e))
    with k[4].popover(":material/delete: Dzēst", help="Dzēst variantu", use_container_width=True):
        if aktivs == nokl:
            st.caption("Noklusējuma variantu nevar dzēst — vispirms iestati citu par noklusējumu.")
        else:
            st.write(f"Dzēst variantu **{aktivs}**?")
            if st.button("Jā, dzēst", key=f"cen_dz_b_{sadala}", type="primary"):
                v.dzest(sadala, aktivs)
                izv[sadala] = v.noklusejums(sadala)
                _parzimet()
                st.rerun()
    if k[5].button(":material/restart_alt: Rūpnīcas vērtības", key=f"cen_rup_{sadala}", use_container_width=True,
                   help="Aizstāj šī varianta vērtības ar sākotnējām (pamācības) vērtībām"):
        v.atjaunot_dati(sadala, aktivs, sadalas_dati(Cenradis(), sadala))
        _parzimet()
        st.rerun()


# --- Redaktori -----------------------------------------------------------------

def _matrica_df(m: dict) -> pd.DataFrame:
    return pd.DataFrame([{"Suga": k_, "Sortiments": s, "Cena EUR/m³": float(x[0]),
                          "Īpatsvars %": round(float(x[1]) * 100, 2)}
                         for k_, sort in m.items() for s, x in sort.items()])


def _df_matrica(df: pd.DataFrame) -> dict:
    m: dict = {}
    for r in df.dropna(subset=["Suga", "Sortiments"]).to_dict("records"):
        suga, sort = str(r["Suga"]).strip(), str(r["Sortiments"]).strip()
        if suga and sort:
            m.setdefault(suga, {})[sort] = [float(r["Cena EUR/m³"] or 0), float(r["Īpatsvars %"] or 0) / 100]
    return m


def _matricas_redaktors(sadala: str) -> None:
    sakuma_df = _matrica_df(_bazes(sadala)["matrica"])
    kolonnas = list(dict.fromkeys([*MATRICAS_KOLONNA.values(), CITI]))
    df = st.data_editor(
        sakuma_df, key=f"cen_m_{sadala}_{izv[sadala]}_{versija}", height=min(36 * len(sakuma_df) + 80, 1200),
        num_rows="dynamic", hide_index=True, use_container_width=True,
        column_config={
            "Suga": st.column_config.SelectboxColumn(
                options=kolonnas, required=True,
                help="Matricas kolonna: " + ", ".join(f"{k_} = {n}" for k_, n in KOLONNU_NOS.items())),
            "Sortiments": st.column_config.TextColumn(required=True),
            "Cena EUR/m³": st.column_config.NumberColumn(min_value=0.0, step=1.0, format="%.2f"),
            "Īpatsvars %": st.column_config.NumberColumn(min_value=0.0, max_value=100.0, step=1.0, format="%.1f"),
        },
    )
    _saglabat_datus(sadala, {"matrica": _df_matrica(df)})
    summas = df.groupby("Suga")["Īpatsvars %"].sum()
    slikti = {k_: x for k_, x in summas.items() if abs(x - 100) > 0.05}
    if slikti:
        st.warning("Īpatsvaru summa nav 100 %: " + ", ".join(f"{k_} {x:.1f} %" for k_, x in slikti.items()))
    else:
        st.caption("✓ Visām sugām īpatsvaru summa ir 100 %.")


def _izdevumu_redaktors() -> None:
    bazes = _bazes("izdevumi")
    izd = bazes["izdevumi"]
    pozicijas = list(dict.fromkeys(p for vd in VEIDI for p in izd.get(vd, {})))
    df = pd.DataFrame([{"Pozīcija": p, **{CIRTES_NOSAUKUMI[vd]: float(izd.get(vd, {}).get(p, 0.0)) for vd in VEIDI}}
                       for p in pozicijas])
    df = st.data_editor(df, key=f"cen_izd_{izv['izdevumi']}_{versija}", num_rows="dynamic", hide_index=True,
                        use_container_width=True,
                        column_config={CIRTES_NOSAUKUMI[vd]: st.column_config.NumberColumn(
                            min_value=0.0, step=0.5, format="%.2f") for vd in VEIDI})
    jauni = {vd: {str(r["Pozīcija"]): float(r[CIRTES_NOSAUKUMI[vd]] or 0)
                  for r in df.dropna(subset=["Pozīcija"]).to_dict("records")} for vd in VEIDI}
    pelna = st.slider("Peļņas rezerve, %", 0, 50, int(round(float(bazes["pelnas_rezerve"]) * 100)),
                      key=f"cen_pelna_{izv['izdevumi']}_{versija}") / 100
    _saglabat_datus("izdevumi", {"izdevumi": jauni, "pelnas_rezerve": pelna})


def _kartejuma_redaktors() -> None:
    bazes = _bazes("kartejums")
    visi_sort = sorted({s for sort in aktivais_cenradis().matricas[KAILCIRTE].values() for s in sort}
                       | {s for kart in bazes["kartejums"].values() for s in kart.values()})
    df = pd.DataFrame([{"Suga": k_, **{NOV_KOLONNAS[l]: kart.get(l, "") for l in NOV_KOLONNAS}}
                       for k_, kart in bazes["kartejums"].items()])
    df = st.data_editor(df, key=f"cen_kart_{izv['kartejums']}_{versija}", hide_index=True,
                        use_container_width=True, disabled=["Suga"],
                        column_config={NOV_KOLONNAS[l]: st.column_config.SelectboxColumn(options=visi_sort)
                                       for l in NOV_KOLONNAS})
    _saglabat_datus("kartejums", {"kartejums": {r["Suga"]: {l: r[NOV_KOLONNAS[l]] for l in NOV_KOLONNAS
                                                             if r[NOV_KOLONNAS[l]]}
                                                for r in df.to_dict("records")}})


def _noteikumu_redaktors() -> None:
    nt_b = Noteikumi(**_bazes("noteikumi")["noteikumi"])
    sfx = f"{izv['noteikumi']}_{versija}"
    k1, k2 = st.columns(2)
    jauni = dict(
        max_sausieni_ha=k1.number_input("Max kailcirte sausieņos, ha", 0.1, 50.0, nt_b.max_sausieni_ha, 0.5,
                                        key=f"nt1_{sfx}"),
        max_citi_ha=k1.number_input("Max kailcirte pārējos meža tipos, ha", 0.1, 50.0, nt_b.max_citi_ha, 0.5,
                                    key=f"nt2_{sfx}"),
        atdalosa_josla_ha=k1.number_input("Atdalošā josla starp kailcirtēm, ha", 0.0, 5.0,
                                          nt_b.atdalosa_josla_ha, 0.1, key=f"nt3_{sfx}"),
        min_kailcirte_ha=k1.number_input("Min nākamās kailcirtes platība, ha", 0.0, 5.0,
                                         nt_b.min_kailcirte_ha, 0.1, key=f"nt4_{sfx}"),
        g_rezerve=k2.number_input("Rezerve virs Gmin / Gkrit, m²/ha", 0.0, 5.0, nt_b.g_rezerve, 0.5,
                                  key=f"nt5_{sfx}"),
        min_izcertamais_g=k2.number_input("Min izcērtamais šķērslaukums, m²/ha", 0.0, 20.0,
                                          nt_b.min_izcertamais_g, 0.5, key=f"nt6_{sfx}",
                                          help="Mazāk neatmaksājas dzīt tehniku mežā"),
        min_g_izlases=k2.checkbox("Min izcērtamais G attiecas arī uz izlases cirti", nt_b.min_g_izlases,
                                  key=f"nt7_{sfx}"),
    )
    _saglabat_datus("noteikumi", {"noteikumi": asdict(Noteikumi(**jauni))})
    st.caption("Baltalksnis: kailcirte, ja ≥ 25 g. vai vid. caurmērs ≥ 16 cm. Kopšanas cirte: "
               "G − (Gmin + rezerve), izlases: G − (Gkrit + rezerve); apjoms = izcērtamais G × "
               "veidaugstums × platība.")


# --- Cilnes ----------------------------------------------------------------------
cilnes = st.tabs([":red[:material/forest:] Kailcirte", ":orange[:material/eco:] Kopšanas cirte",
                  ":violet[:material/park:] Izlases cirte", ":green[:material/payments:] Izdevumi un peļņa",
                  ":blue[:material/calculate:] Novērtējuma kartējums", ":gray[:material/rule:] Noteikumi",
                  ":gray[:material/history:] Vēsture"])
APRAKSTI = {
    "kailcirte": "Sortimentu iznākums kailcirtē. Šīs cenas izmanto arī cirsmas novērtējuma kalkulators.",
    "kopsana": "Kopšanas cirtē iznāk galvenokārt tara, papīrmalka un malka.",
    "izlases": "Izlases cirtē cērt arī resnos kokus — iekļauj zāģbaļķus, finieri u.c.",
    "izdevumi": "Izdevumi EUR uz izcirsto m³ katram cirtes veidam. Kopšanā ciršana un pievešana parasti ir "
                "dārgāka par m³ nekā kailcirtē.",
    "kartejums": "Kā cirsmas novērtējuma kolonnas (Resnā, Vidējā, Tievā …) pārvēršas sortimentos. Cenas ņem no "
                 "kailcirtes cenrāža. Pārdodamo cirsmu PDF nav atsevišķas P. malkas — tur Tievā tiek sadalīta "
                 "starp Tievās un P. malkas sortimentiem pēc kailcirtes īpatsvariem.",
    "noteikumi": "Ciršanas noteikumi. Sausieņi: sils, mētrājs, lāns, damaksnis, vēris, gārša; pārējie "
                 "(slapjaiņi, purvaiņi, āreņi, kūdreņi) — mazākais limits.",
}
for cilne, sadala in zip(cilnes, SADALAS):
    with cilne:
        _variantu_josla(sadala)
        st.caption(APRAKSTI[sadala])
        if sadala in ("kailcirte", "kopsana", "izlases"):
            _matricas_redaktors(sadala)
        elif sadala == "izdevumi":
            _izdevumu_redaktors()
        elif sadala == "kartejums":
            _kartejuma_redaktors()
        else:
            _noteikumu_redaktors()

g = glabatuve()
with cilnes[-1]:
    if g is None:
        st.info("Datubāze nav pieejama — vēsture netiek glabāta.")
    else:
        vest = g.iestatijuma_vesture(ATSLEGA_VARIANTI)
        if not vest:
            st.info("Cenrādis ar variantiem vēl nav saglabāts.")
        for ieraksts in vest:
            k1, k2 = st.columns([4, 1])
            vv = CenrazaVarianti.no_json(ieraksts["vertiba"])
            k1.markdown(f"**{ieraksts['mainits'].replace('T', ' ')[:16]}** · {ieraksts['autors'] or 'nav norādīts'}  \n"
                        + " · ".join(f"{SADALU_NOSAUKUMI[s]}: {len(vv.nosaukumi(s))} var. (★ {vv.noklusejums(s)})"
                                     for s in SADALAS))
            if k2.button("Ielādēt", key=f"vest_{ieraksts['id']}"):
                ss.cenradis_varianti = vv
                ss.cenradis_izvele = vv.noklusejuma_izvele()
                _parzimet()
                st.rerun()

# --- Saglabāšana -------------------------------------------------------------
st.divider()
for b in aktivais_cenradis().bridinajumi():
    st.warning(b)
mainits = cenradis_mainits()
st.caption("✎ Ir nesaglabātas izmaiņas (strādā tikai šajā sesijā)." if mainits else "Viss saglabāts.")
b1, b2 = st.columns(2)
if b1.button(":material/save: Saglabāt variantus un noklusējumus", type="primary",
             disabled=g is None or not mainits, use_container_width=True):
    g.saglabat_iestatijumu(ATSLEGA_VARIANTI, v.uz_json(), lietotajs())
    ss.cenradis_varianti_saglabatie = copy.deepcopy(v)
    ier = g.iestatijums(ATSLEGA_VARIANTI)
    ss.cenradis_meta = {"mainits": ier["mainits"], "autors": ier["autors"]}
    st.toast("Cenrādis saglabāts", icon=":material/save:")
    st.rerun()
if b2.button(":material/undo: Atcelt nesaglabātās izmaiņas", disabled=not mainits, use_container_width=True):
    ss.cenradis_varianti = copy.deepcopy(ss.cenradis_varianti_saglabatie)
    ss.cenradis_izvele = ss.cenradis_varianti.noklusejuma_izvele()
    _parzimet()
    st.rerun()
