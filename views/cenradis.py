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

def _matricas_redaktors(sadala: str) -> None:
    """Kartītes pa sugām: katram sortimentam cena un īpatsvars ar +/− pogām."""
    nos = izv[sadala]
    matrica = copy.deepcopy(v.sadalas[sadala]["varianti"][nos]["matrica"])
    pref = f"cm_{sadala}_{nos}_{versija}"
    sugas = list(matrica)
    jauna: dict = {}
    for rinda in range(0, len(sugas), 2):
        kolonnas_ui = st.columns(2, gap="medium")
        for kol_ui, suga in zip(kolonnas_ui, sugas[rinda:rinda + 2]):
            with kol_ui.container(border=True):
                jauna[suga] = _sugas_kartite(sadala, pref, suga, matrica[suga])
    _saglabat_datus(sadala, {"matrica": jauna})

    brivas = [k_ for k_ in dict.fromkeys([*MATRICAS_KOLONNA.values(), CITI]) if k_ not in matrica]
    if brivas:
        with st.popover(":material/add: Pievienot sugu"):
            suga = st.selectbox("Suga", brivas, format_func=lambda k_: f"{KOLONNU_NOS.get(k_, k_)} ({k_})",
                                key=f"{pref}_jsuga")
            if st.button("Pievienot", key=f"{pref}_jsuga_b", type="primary"):
                jauna[suga] = {"Malka": [38.0, 1.0]}
                _saglabat_datus(sadala, {"matrica": jauna})
                _parzimet()
                st.rerun()


def _sugas_kartite(sadala: str, pref: str, suga: str, sortimenti: dict) -> dict:
    galva, summa_vieta = st.columns([3, 2], vertical_alignment="center")
    galva.markdown(f"**{KOLONNU_NOS.get(suga, suga)}** <span style='color:#6b7280'>({suga})</span>",
                   unsafe_allow_html=True)
    h = st.columns([2.2, 2.2, 2.2, 0.6])
    h[0].caption("Sortiments")
    h[1].caption("Cena €/m³")
    h[2].caption("Īpatsvars %")
    rez: dict = {}
    for sort, x in sortimenti.items():
        c = st.columns([2.2, 2.2, 2.2, 0.6], vertical_alignment="center")
        c[0].markdown(sort)
        cena = c[1].number_input(f"{suga} {sort} cena", min_value=0.0, value=float(x[0]), step=1.0,
                                 format="%.2f", key=f"{pref}_{suga}_{sort}_c", label_visibility="collapsed")
        proc = c[2].number_input(f"{suga} {sort} %", min_value=0.0, max_value=100.0,
                                 value=round(float(x[1]) * 100, 2), step=1.0, format="%.1f",
                                 key=f"{pref}_{suga}_{sort}_p", label_visibility="collapsed")
        if c[3].button("✕", key=f"{pref}_{suga}_{sort}_x", help=f"Noņemt {sort}", type="tertiary"):
            sortimenti_bez = {k_: x_ for k_, x_ in sortimenti.items() if k_ != sort}
            _saglabat_datus(sadala, {"matrica": {**v.sadalas[sadala]["varianti"][izv[sadala]]["matrica"],
                                                 suga: sortimenti_bez}})
            _parzimet()
            st.rerun()
        rez[sort] = [cena, proc / 100]
    summa = sum(p for _, p in rez.values()) * 100
    if abs(summa - 100) <= 0.05:
        summa_vieta.markdown(f"<div style='text-align:right;color:#16A34A;font-size:14px'>"
                             f"✓ {summa:.0f} %</div>", unsafe_allow_html=True)
    else:
        summa_vieta.markdown(f"<div style='text-align:right;color:#DC2626;font-size:14px'>"
                             f"⚠ {summa:.1f} % (jābūt 100 %)</div>", unsafe_allow_html=True)
    with st.popover(":material/add: Sortiments", use_container_width=False):
        jauns = st.text_input("Nosaukums", key=f"{pref}_{suga}_jn", placeholder="piem., Finieris")
        jc = st.number_input("Cena €/m³", min_value=0.0, value=50.0, step=1.0, key=f"{pref}_{suga}_jc")
        jp = st.number_input("Īpatsvars %", min_value=0.0, max_value=100.0, value=0.0, step=1.0,
                             key=f"{pref}_{suga}_jp")
        if st.button("Pievienot", key=f"{pref}_{suga}_jb", type="primary"):
            if not jauns.strip():
                st.error("Ievadi sortimenta nosaukumu")
            elif jauns.strip() in rez:
                st.error("Tāds sortiments jau ir")
            else:
                rez[jauns.strip()] = [jc, jp / 100]
                _saglabat_datus(sadala, {"matrica": {**v.sadalas[sadala]["varianti"][izv[sadala]]["matrica"],
                                                     suga: rez}})
                _parzimet()
                st.rerun()
    return rez


def _izdevumu_redaktors() -> None:
    """Izdevumi €/m³ katram cirtes veidam (+/− pogas) un peļņas rezerve."""
    nos = izv["izdevumi"]
    dati = v.sadalas["izdevumi"]["varianti"][nos]
    izd = dati["izdevumi"]
    pref = f"ci_{nos}_{versija}"
    pozicijas = list(dict.fromkeys(p for vd in VEIDI for p in izd.get(vd, {})))
    jauni: dict = {vd: {} for vd in VEIDI}
    kol = st.columns(len(VEIDI), gap="medium")
    for kol_ui, vd in zip(kol, VEIDI):
        with kol_ui.container(border=True):
            st.markdown(f"**{CIRTES_NOSAUKUMI[vd]}**")
            for p in pozicijas:
                jauni[vd][p] = st.number_input(f"{p}, €/m³", min_value=0.0,
                                               value=float(izd.get(vd, {}).get(p, 0.0)), step=0.5,
                                               format="%.2f", key=f"{pref}_{vd}_{p}")
            st.caption(f"Kopā: **{sum(jauni[vd].values()):.2f} €/m³**")
    k1, k2 = st.columns([2, 3], vertical_alignment="bottom")
    pelna = k1.number_input("Peļņas rezerve, %", min_value=0.0, max_value=80.0,
                            value=round(float(dati["pelnas_rezerve"]) * 100, 1), step=1.0, format="%.1f",
                            key=f"{pref}_pelna") / 100
    with k2.popover(":material/add: Izdevumu pozīcija"):
        jp = st.text_input("Nosaukums", key=f"{pref}_jp", placeholder="piem., Meža ceļa remonts")
        if st.button("Pievienot", key=f"{pref}_jpb", type="primary") and jp.strip():
            for vd in VEIDI:
                jauni[vd][jp.strip()] = 0.0
            _saglabat_datus("izdevumi", {"izdevumi": jauni, "pelnas_rezerve": pelna})
            _parzimet()
            st.rerun()
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
