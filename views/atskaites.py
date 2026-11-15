"""Modulis: leadu atskaites no monday.com iepirkumu agentu boardiem."""
from __future__ import annotations

import os
import tempfile
from datetime import date, timedelta

import pandas as pd
import streamlit as st

from atskaites.demo import demo_boardi
from atskaites.eksports import excel_atskaite
from atskaites.metrikas import (
    Periods, aprekinat, iepriekseja_menesa_periods, nedelu_tendence, salidzinajuma_periods, tekosais_menesis,
    teksta_kopsavilkums,
)
from atskaites.panelis import (
    Kartite, cipi_html, josla_html, iemeslu_grafiks, kartites_html, laiku_df, laiku_grafiks, piltuves_df,
    piltuves_grafiks, tendences_grafiks,
)
from atskaites.modelis import LAUKI, LAUKI_PEC_KEY, POSMI, POSMU_NOSAUKUMI, Konfiguracija, sagatavot, sodiena
from atskaites.monday import MondayKlients, MondayKluda
from views.kopigi import glabatuve, lietotajs

KONF_CELS = os.path.join(os.path.dirname(__file__), "..", "dati", "monday_konfiguracija.json")
KONF_ATSLEGA = "monday_konfiguracija"
ss = st.session_state


def _ielasit_konf() -> Konfiguracija:
    """Datubāze (izdzīvo Streamlit Cloud restartu); rezerve — lokālais JSON fails."""
    g = glabatuve()
    ier = g.iestatijums(KONF_ATSLEGA) if g else None
    if ier:
        return Konfiguracija.no_dict(ier["vertiba"])
    return Konfiguracija.ielasit(KONF_CELS)


def _saglabat_konf() -> None:
    g = glabatuve()
    if g:
        try:
            g.saglabat_iestatijumu(KONF_ATSLEGA, ss.konf.uz_dict(), lietotajs())
            return
        except Exception as e:  # noqa: BLE001
            st.warning(f"Neizdevās saglabāt datubāzē ({e}) — saglabāts lokāli.")
    ss.konf.saglabat(KONF_CELS)


DATU_VERSIJA = 3  # palielini, ja mainās Boards/Rinda struktūra — citādi kešā paliek vecie objekti


@st.cache_data(ttl=900, show_spinner="Ielādē boardus un grupu vēsturi no monday.com…")
def _ieladet(token: str, ids: tuple[str, ...], versija: int = DATU_VERSIJA):
    k = MondayKlients(token)
    return [k.ieladet_boardu(i) for i in ids]


def _token_no_vides() -> str:
    try:
        t = st.secrets.get("MONDAY_API_TOKEN", "")
    except Exception:  # noqa: BLE001 — nav secrets.toml
        t = ""
    return t or os.environ.get("MONDAY_API_TOKEN", "")


def _formatet(v, vien: str) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        s = f"{v:,.2f}".rstrip("0").rstrip(".")
    else:
        s = f"{v:,}"
    return f"{s.replace(',', ' ')} {vien}".strip()


if "konf" not in ss:
    ss.konf = _ielasit_konf()

st.title(":material/bar_chart: Leadu atskaites no monday.com")
st.caption(
    "Savāc datus no iepirkumu agentu boardiem, apvieno rindas leados (1 īpašuma kadastra Nr. = 1 lead) "
    "un aprēķina CEO metrikus: leadi, kvalifikācija, priekšvērtējums, apsekošana, pirkumi, atteikumi."
)

# --- Sānjosla: datu avots un periods ---------------------------------------
st.sidebar.header("Datu avots")
avots = st.sidebar.radio("Avots", ["monday.com API", "Demo dati"], label_visibility="collapsed")
token = ""
if avots == "monday.com API":
    token = _token_no_vides()
    if token:
        st.sidebar.success("API tokens nolasīts no iestatījumiem", icon=":material/key:")
    else:
        token = st.sidebar.text_input(
            "monday API tokens", type="password",
            help="monday: profila bilde → Developers → My access tokens. Pastāvīgai lietošanai "
                 "ieliec to .streamlit/secrets.toml kā MONDAY_API_TOKEN.",
        )

st.sidebar.header("Periods")
sod = sodiena()
perioda_izvele = st.sidebar.selectbox(
    "Periods", ["Tekošais mēnesis", "Iepriekšējais mēnesis", "Pēdējās 30 dienas", "Šis gads", "Cits periods"],
    label_visibility="collapsed",
)
if perioda_izvele == "Tekošais mēnesis":
    periods = tekosais_menesis(sod)
elif perioda_izvele == "Iepriekšējais mēnesis":
    periods = iepriekseja_menesa_periods(sod)
elif perioda_izvele == "Pēdējās 30 dienas":
    periods = Periods(sod - timedelta(days=29), sod, "pēdējās 30 dienas")
elif perioda_izvele == "Šis gads":
    periods = Periods(date(sod.year, 1, 1), sod, f"{sod.year}. gads")
else:
    no_lidz = st.sidebar.date_input("No – līdz", (sod.replace(day=1), sod), format="DD.MM.YYYY")
    if len(no_lidz) != 2:
        st.stop()
    periods = Periods(no_lidz[0], no_lidz[1], f"{no_lidz[0]:%d.%m.%Y}–{no_lidz[1]:%d.%m.%Y}")

# --- Datu ielāde -----------------------------------------------------------
klients = None
if avots == "Demo dati":
    st.info("Rāda **izdomātus demo datus** (3 agentu boardi). Reāliem datiem sānjoslā izvēlies monday.com API.",
            icon=":material/science:")
    boardi = demo_boardi(sod)
else:
    if not token:
        st.info("Ievadi monday API tokenu sānjoslā (monday: profila bilde → Developers → My access tokens).")
        st.stop()
    klients = MondayKlients(token)
    c1, c2 = st.columns([4, 1])
    if c2.button(":material/refresh: Boardu saraksts", use_container_width=True) or "boardu_saraksts" not in ss:
        try:
            ss.boardu_saraksts = klients.boardu_saraksts()
        except MondayKluda as e:
            st.error(str(e))
            st.stop()
    opcijas = {f"{b['workspace']} › {b['nosaukums']}": b["id"] for b in ss.boardu_saraksts}
    noklusetie = [nos for nos, i in opcijas.items() if i in ss.konf.boardi]
    izveletie = c1.multiselect("Iepirkumu agentu boardi", list(opcijas), default=noklusetie,
                               placeholder="Izvēlies agentu boardus…")
    ids = tuple(opcijas[n] for n in izveletie)
    if not ids:
        st.info("Izvēlies vienu vai vairākus iepirkumu agentu boardus.")
        st.stop()
    if list(ids) != ss.konf.boardi:
        ss.konf.boardi = list(ids)
        _saglabat_konf()
    try:
        boardi = _ieladet(token, ids)
    except MondayKluda as e:
        st.error(str(e))
        st.stop()
    if st.button(":material/refresh: Ielādēt datus no jauna"):
        _ieladet.clear()
        st.rerun()

dati = sagatavot(boardi, ss.konf)
atsk = aprekinat(dati, periods, sod)

# --- Lejupielādes ------------------------------------------------------------
xlsx = os.path.join(tempfile.gettempdir(), "leadu_atskaite.xlsx")
excel_atskaite(xlsx, atsk, dati)
teksts = teksta_kopsavilkums(atsk)
st.sidebar.header("Lejupielāde")
with open(xlsx, "rb") as f:
    st.sidebar.download_button(":material/download: Excel atskaite", f, file_name=f"leadu_atskaite_{periods.no:%Y-%m}.xlsx",
                               use_container_width=True,
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
st.sidebar.download_button(":material/download: Teksta kopsavilkums", teksts, file_name="leadu_atskaite.txt",
                           use_container_width=True)

vestures_no = [getattr(b, "vesture_no", None)[:10] for b in dati.boardi if getattr(b, "vesture_no", None)]
vestures_kludas = [f"{b.nosaukums}: {b.vestures_kluda}" for b in dati.boardi if getattr(b, "vestures_kluda", None)]
st.subheader(f"{periods.nosaukums[:1].upper()}{periods.nosaukums[1:]}")
josla = [("Periods", f"{periods.no:%d.%m.%Y} – {periods.lidz:%d.%m.%Y}"),
         ("Boardi", ", ".join(b.nosaukums for b in dati.boardi)),
         ("Leadi datubāzē", f"{len(dati.leadi)} (no {len(dati.rindas)} rindām)")]
if dati.no_vestures and vestures_no:
    v = min(vestures_no)
    josla.append(("Posmu vēsture no", f"{v[8:10]}.{v[5:7]}.{v[:4]}"))
st.html(josla_html(josla))
if vestures_kludas:
    st.warning("Grupu vēsturi neizdevās nolasīt — " + "; ".join(vestures_kludas), icon=":material/history:")

tab_k, tab_a, tab_p, tab_l, tab_dk, tab_i = st.tabs(
    ["Kopsavilkums", "Pa agentiem", "Piltuve tagad", "Leadi", f"Datu kvalitāte ({len(atsk.datu_kvalitate)})",
     "Iestatījumi"])

with tab_k:
    iepr_p = salidzinajuma_periods(periods, sod)
    atsk_iepr = aprekinat(dati, iepr_p, sod)
    tend = nedelu_tendence(dati, min(periods.lidz, sod), 12)

    def _t(nos):  # nedēļu sērija sparklainam
        return [r[nos] for r in tend]

    # Salīdzinājums nav godīgs, ja iepriekšējam periodam posmu vēstures vēl nebija (monday to neglabā)
    vest_no = min(vestures_no) if vestures_no else None
    iepr_bez_vestures = bool(dati.no_vestures and vest_no and iepr_p.no.isoformat() < vest_no)
    NO_VESTURES = {"Kvalificēti objekti", "Priekšvērtējumi", "Apsekoti dabā", "Nopirkti objekti",
                   "Atteikti objekti", "Sarunātas klātienes tikšanās", "Priekšvērtējumi vidēji darba dienā",
                   "Kvalitatīvi", "Mērķa"}

    def K(nos, isais, tend_nos=None, **kw):
        m = next(m for m in atsk.metriki if m.nosaukums == nos)
        vien = {"gab.": "", "EUR": "€"}.get(m.vieniba, m.vieniba)
        kw.setdefault("vieniba", vien)
        iepr = None if (iepr_bez_vestures and nos in NO_VESTURES) else atsk_iepr.metriks(nos)
        return Kartite(isais, m.vertiba, iepr=iepr,
                       tendence=_t(tend_nos) if tend_nos else None, paskaidrojums=m.piezime, **kw)

    if iepr_bez_vestures:
        st.caption(f"Posmu rādītājiem salīdzinājums ar {iepr_p.nosaukums} nav rādīts — monday posmu vēsture "
                   f"pieejama tikai no {vest_no[8:10]}.{vest_no[5:7]}.{vest_no[:4]}.")

    st.html(kartites_html([
        K("Leadi kopā", "Jauni leadi", "Leadi", galvenais=True),
        K("Kvalificēti objekti", "Kvalificēti", "Kvalificēti", galvenais=True),
        K("Priekšvērtējumi", "Priekšvērtējumi", "Priekšvērtējumi", galvenais=True),
        K("Apsekoti dabā", "Apsekoti dabā", "Apsekoti", galvenais=True),
        K("Nopirkti objekti", "Nopirkti", "Nopirkti", galvenais=True),
        K("Atteikti objekti", "Atteikti", "Atteikti", augsana_laba=False, galvenais=True),
    ], iepr_p.nosaukums, "Galvenie rādītāji"))

    st.html(kartites_html([
        K("Kvalitatīvi", "Kvalitatīvi leadi"),
        K("Mērķa", "Mērķa leadi"),
        K("Proaktīvi", "Proaktīvi leadi"),
        K("Sarunātas klātienes tikšanās", "Klātienes tikšanās"),
        K("Priekšvērtējumi vidēji darba dienā", "Priekšvērtējumi dienā", vieniba="vid."),
        K("t.sk. atjaunoti", "Atjaunoti leadi", augsana_laba=None),
    ], iepr_p.nosaukums, "Leadu kvalitāte un aktivitāte"))

    k1, k2 = st.columns([3, 2], gap="large")
    with k1:
        st.html(cipi_html("Piltuve periodā", []))
        pdf = piltuves_df(atsk)
        if len(pdf):
            st.altair_chart(piltuves_grafiks(pdf), use_container_width=True)
            st.caption("Cik objektu periodā sasniedza katru posmu, un cik % tas ir no periodā saņemtajiem leadiem.")
    with k2:
        st.html(cipi_html("Posmu ilgums (vidēji)", []))
        ldf = laiku_df(atsk)
        if len(ldf):
            st.altair_chart(laiku_grafiks(ldf), use_container_width=True)
        else:
            st.caption("Periodā nav pāreju starp posmiem.")

    k1, k2 = st.columns([3, 2], gap="large")
    with k1:
        st.html(cipi_html("Nedēļu dinamika (12 ned.)", []))
        st.altair_chart(tendences_grafiks(tend), use_container_width=True)
    with k2:
        st.html(cipi_html("Atteikuma iemesli", []))
        if atsk.atteikuma_iemesli and not (len(atsk.atteikuma_iemesli) == 1
                                           and atsk.atteikuma_iemesli[0][0] == "Nav norādīts"):
            st.altair_chart(iemeslu_grafiks(atsk.atteikuma_iemesli), use_container_width=True)
        else:
            n = sum(c for _, c in atsk.atteikuma_iemesli)
            st.caption(f"{n} atteikumiem iemesls nav norādīts — boardā nav kolonnas 'Atteikuma iemesls'."
                       if n else "Periodā atteikumu nav.")

    st.html(kartites_html([
        K("Apjoms", "Nopirktais apjoms"), K("Platība", "Nopirktā platība"),
        K("Iegādes summa", "Iegādes summa"),
        K("Cenas samazinājums pret maks. gala piedāvājumu", "Cenas samazinājums", augsana_laba=None),
    ], iepr_p.nosaukums, "Pirkumi"))

    trukst = sorted({k for kk in atsk.trukstosas_kolonnas.values() for k in kk})
    if trukst:
        st.html(cipi_html("Trūkst boardā — šie rādītāji nav aprēķināmi",
                          [(k, "Pievieno kolonnu: Iestatījumi → Board standarts") for k in trukst]))

with tab_a:
    if atsk.pa_agentiem:
        adf = pd.DataFrame(atsk.pa_agentiem)
        mx = max(int(adf["Leadi"].max()), 1)
        st.dataframe(
            adf, hide_index=True, use_container_width=True,
            column_config={
                "Agents": st.column_config.TextColumn("Agents (boards)", width="medium"),
                "Leadi": st.column_config.ProgressColumn("Leadi", format="%d", min_value=0, max_value=mx),
                "Kvalificēti": st.column_config.ProgressColumn("Kvalificēti", format="%d", min_value=0, max_value=mx),
                "Priekšvērtējumi": st.column_config.ProgressColumn("Priekšvērt.", format="%d", min_value=0,
                                                                   max_value=mx),
                "Nopirkts m³": st.column_config.NumberColumn("Nopirkts m³", format="%d"),
                "Iegādes summa EUR": st.column_config.NumberColumn("Iegādes summa", format="€ %d"),
            })
    else:
        st.info("Periodā nav datu.")
    st.caption("Lead pieder boardam (agentam), kurā tas parādījās pirmais.")

with tab_p:
    st.caption("Pašreizējais stāvoklis neatkarīgi no perioda — katrs lead savā tālākajā posmā.")
    if atsk.piltuve_tagad:
        st.bar_chart(pd.DataFrame(atsk.piltuve_tagad).set_index("Posms"), horizontal=True)
        st.dataframe(pd.DataFrame(atsk.piltuve_tagad), hide_index=True)

with tab_l:
    df = pd.DataFrame(atsk.leadu_tabula)
    f1, f2 = st.columns(2)
    tikai_perioda = f1.toggle("Tikai periodā saņemtie leadi", value=True)
    meklet = f2.text_input("Meklēt", placeholder="nosaukums, kadastra Nr., agents…")
    if tikai_perioda and not df.empty:
        df = df[df["Lead datums"].apply(periods.satur)]
    if meklet and not df.empty:
        df = df[df.astype(str).apply(lambda r: r.str.contains(meklet, case=False)).any(axis=1)]
    st.dataframe(df, hide_index=True, use_container_width=True)

with tab_dk:
    st.caption("Lietas, kas jāsakārto boardos, lai metriki būtu precīzi.")
    if atsk.datu_kvalitate:
        dk = pd.DataFrame(atsk.datu_kvalitate)
        st.dataframe(dk.groupby("Problēma").size().rename("Skaits").sort_values(ascending=False))
        st.dataframe(dk, hide_index=True, use_container_width=True)
    else:
        st.success("Datu kvalitātes problēmas nav atrastas.")

with tab_i:
    st.markdown("#### Kolonnu karte")
    st.caption("Kura monday kolonna atbilst kuram standarta laukam (atpazīts automātiski pēc nosaukuma).")
    karte_df = pd.DataFrame([
        {"Lauks": l.nosaukums, **{b.nosaukums: dati.kartes.get(b.id, {}).get(l.key, "—") for b in dati.boardi}}
        for l in LAUKI])
    st.dataframe(karte_df, hide_index=True, use_container_width=True)

    with st.expander("Mainīt kolonnu sasaisti"):
        st.caption("Ja kolonna boardā saucas citādi, ieraksti tās precīzu nosaukumu. Tukšs = automātiski.")
        red = st.data_editor(
            pd.DataFrame([{"Lauks": l.nosaukums, "Kolonna monday": ss.konf.kolonnas.get(l.key, "")} for l in LAUKI]),
            hide_index=True, use_container_width=True, disabled=["Lauks"], key="kolonnu_red")
        if st.button("Saglabāt kolonnu sasaisti"):
            pec_nos = {l.nosaukums: l.key for l in LAUKI}
            ss.konf.kolonnas = {pec_nos[r["Lauks"]]: r["Kolonna monday"].strip()
                                for _, r in red.iterrows() if str(r["Kolonna monday"] or "").strip()}
            _saglabat_konf()
            st.rerun()

    st.markdown("#### Grupu nozīme")
    st.caption("Kuram posmam atbilst katra boarda grupa (izmanto 'Piltuvei tagad' un sazvanāmības noteikšanai).")
    nos_uz_posmu = {v: k for k, v in POSMU_NOSAUKUMI.items()}
    gr = st.data_editor(
        pd.DataFrame([{"Grupa": g, "Posms": POSMU_NOSAUKUMI[p]} for g, p in dati.grupu_karte.items()]),
        hide_index=True, use_container_width=True, disabled=["Grupa"], key="grupu_red",
        column_config={"Posms": st.column_config.SelectboxColumn(options=[POSMU_NOSAUKUMI[p] for p in POSMI])})
    if st.button("Saglabāt grupu nozīmi"):
        ss.konf.grupas = {r["Grupa"]: nos_uz_posmu[r["Posms"]] for _, r in gr.iterrows()}
        _saglabat_konf()
        st.rerun()

    st.markdown("#### Board standarts")
    st.caption("Kolonnas, kas vajadzīgas visiem metrikiem. Trūkstošās var izveidot boardā no šejienes.")
    for b in dati.boardi:
        karte = dati.kartes.get(b.id, {})
        trukst = [l for l in LAUKI if l.key not in karte and l.key not in ("posms", "kontaktpersona")]
        with st.expander(f"{b.nosaukums} — trūkst {len(trukst)} kolonnas" if trukst else f"{b.nosaukums} — :green[:material/check_circle:] viss ir"):
            if not trukst:
                continue
            st.dataframe(pd.DataFrame([{"Kolonna": l.nosaukums, "Tips": l.monday_tips, "Kam vajag": l.apraksts}
                                       for l in trukst]), hide_index=True, use_container_width=True)
            if klients is None:
                st.caption("Kolonnu izveide pieejama tikai ar monday.com API (ne demo režīmā).")
                continue
            izv = st.multiselect("Izveidot kolonnas", [l.nosaukums for l in trukst], key=f"izv_{b.id}")
            apst = st.checkbox(f"Apstiprinu, ka šīs kolonnas tiks pievienotas boardam '{b.nosaukums}'",
                               key=f"apst_{b.id}")
            if st.button("Izveidot", key=f"btn_{b.id}", disabled=not (izv and apst)):
                pec_nos = {l.nosaukums: l for l in LAUKI}
                try:
                    for n in izv:
                        klients.izveidot_kolonnu(b.id, n, pec_nos[n].monday_tips)
                except MondayKluda as e:
                    st.error(str(e))
                else:
                    st.success(f"Izveidotas {len(izv)} kolonnas.")
                    _ieladet.clear()
                    st.rerun()

    st.markdown("#### Definīcijas")
    st.markdown(
        "- **Lead** = 1 īpašuma kadastra Nr. (visas zemes vienības = 1 lead; platība un m³ summējas). "
        "Ja kadastra Nr. vēl nav — rinda tiek piesaistīta pēc zemes vienības vai tālruņa.\n"
        "- **Atjaunots** = tas pats īpašums pieteicies atkārtoti vairāk nekā 365 dienas pēc iepriekšējā.\n"
        "- **Kvalitatīvs** = sazvanāms + kadastra Nr. + norādīta interese (Pied. veids).\n"
        "- **Mērķa** = visi 3: kailcirte ≥1,5× atļautās (5 ha sausie / 2 ha slapjie) vai citu ciršu "
        "potenciāls; 1. piegājiens ≥700 m³; mežs ≥5 ha un lauks ≤20%. Ķeksis 'Mērķa lead' pārraksta.\n"
        "- **Proaktīvs** = avots: aukstais zvans, kaimiņi, personīgais mārketings, ieteikums "
        "(ne ss.com, Facebook, izsoles, portāli).\n"
        "- Katrs notikums periodā tiek skaitīts pēc sava datuma kolonnas."
    )

    st.markdown("#### monday vēstures diagnostika")
    for b in dati.boardi:
        st.write(f"**{b.nosaukums}** — vēsture no {getattr(b, 'vesture_no', None) or '—'}; ierakstu veidi:",
                 getattr(b, "zurnala_notikumi", {}) or "nav")
        ar = sum(1 for r in b.rindas if getattr(r, "grupu_vesture", None))
        st.caption(f"{ar} no {len(b.rindas)} rindām ir zināma ienākšana kādā grupā")
