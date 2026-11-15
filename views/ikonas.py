"""Vienota ikonu valoda: Material Symbols (Rounded, kontūra) ar krāsu katrai sadaļai.

Krāsas nozīme:
  * katrai sadaļai sava krāsa (navigācija, lapas virsraksts, sākuma kartītes);
  * cirtes veidiem — tās pašas krāsas kā kartē (kailcirte sarkana, kopšana oranža, izlase violeta);
  * pogās ikonas ir teksta krāsā (standarta Streamlit izskats).
"""
from __future__ import annotations

# atslēga: (Material ikona, krāsa, lapas fails)
SADALAS: dict[str, tuple[str, str, str]] = {
    "sakums":     ("home",        "#475569", "views/sakums.py"),
    "mezs":       ("forest",      "#16A34A", "views/mezs.py"),
    "saglabatie": ("folder_open", "#D97706", "views/saglabatie.py"),
    "cenradis":   ("euro",        "#0D9488", "views/cenradis.py"),
    "ligumi":     ("description", "#7C3AED", "views/ligumi.py"),
    "atskaites":  ("bar_chart",   "#DB2777", "views/atskaites.py"),
    "karte":      ("map",         "#2563EB", "views/karte.py"),
}

# Cirtes veidu krāsas (sakrīt ar kartes statusiem karte/geometrija.STATUSI)
CIRTES_KRASAS = {"Kailcirte": "#ff4b4b", "Kopšanas cirte": "#f59e0b", "Izlases cirte": "#a855f7"}

# Meža inventarizācijas datu avoti (arī lapā Saglabātie)
AVOTS_PDF = ":material/description: No inventarizācijas PDF"
AVOTS_KARTE = ":material/map: Aprēķins no kartes"
AVOTS_NOVERTEJUMS = ":material/calculate: Cirsmas novērtējums"


def m(nosaukums: str) -> str:
    """Streamlit markdown ikona: m("save") -> ":material/save:"."""
    return f":material/{nosaukums}:"


def nav(atsl: str) -> str:
    return m(SADALAS[atsl][0])


def ik(nosaukums: str, krasa: str | None = None, izmers: str = "1.15em") -> str:
    """HTML ikona krāsā (st.markdown(..., unsafe_allow_html=True))."""
    stils = f"font-size:{izmers};" + (f"color:{krasa};" if krasa else "")
    return f'<span class="ik" style="{stils}">{nosaukums}</span>'


def sadalas_ik(atsl: str, izmers: str = "1.15em") -> str:
    ikona, krasa, _ = SADALAS[atsl]
    return ik(ikona, krasa, izmers)


def css(aktiva_lapa: str | None) -> str:
    """Globālais stils: navigācijas ikonu krāsas, aktīvās lapas virsraksta ikona, .ik klase."""
    rindas = [
        ".ik {font-family: 'Material Symbols Rounded'; font-weight: 400; font-style: normal;"
        " line-height: 1; vertical-align: -0.2em; letter-spacing: normal; text-transform: none;"
        " white-space: nowrap; font-feature-settings: 'liga'; -webkit-font-feature-settings: 'liga';}",
    ]
    for atsl, (_, krasa, fails) in SADALAS.items():
        cels = fails.removeprefix("views/").removesuffix(".py")
        beigas = '"/"' if atsl == "sakums" else f'"/{cels}"'
        rindas.append(f'[data-testid="stSidebarNavLink"][href$={beigas}] [data-testid="stIconMaterial"]'
                      f" {{color: {krasa};}}")
    if aktiva_lapa in SADALAS:
        krasa = SADALAS[aktiva_lapa][1]
        # markdown ikona virsrakstā: <span role="img" translate="no">…</span>
        rindas.append(f'h1 span[role="img"][translate="no"], h3 span[role="img"][translate="no"] {{color: {krasa};}}')
    return "\n".join(rindas)


# Material Symbols (Rounded, 400) SVG ceļi — kartes JS rīkjoslai un izvēlnei (bez ārēja fonta).
# Avots: npm @material-symbols/svg-400 (Apache-2.0).
MATERIAL_SVG: dict[str, str] = {
    "sell": "M863-404 557-97q-9 8.5-20.25 12.75T514.25-80Q503-80 492-84.5T472-97L98-472q-8-8-13-18.96-5-10.95-5-23.04v-306q0-24.75 17.63-42.38Q115.25-880 140-880h307q12.07 0 23.39 4.87Q481.7-870.25 490-862l373 373q9.39 9 13.7 20.25 4.3 11.25 4.3 22.5t-4.5 22.75Q872-412 863-404ZM516-138l306-307-375-375H140v304l376 378ZM245-664q21 0 36.5-15.5T297-716q0-21-15.5-36.5T245-768q-21 0-36.5 15.5T193-716q0 21 15.5 36.5T245-664Zm236 185Z",
    "content_cut": "M481-415 364-298q11 17 13.5 33t2.5 35q0 64-43 107T230-80q-64 0-107-43T80-230q0-64 43-107t107-43q18 0 35.5 5t36.5 15l116-116-118-118q-17 8-34.5 11t-35.5 3q-64 0-107-43T80-730q0-64 43-107t107-43q64 0 107 43t43 107q0 19-2.5 36T367-662l468 468q23 23 10.5 51.5T801-114q-9 0-17.5-3.5T768-128L481-415Zm118-112-66-66 235-235q7-7 15.5-10.5T801-842q32 0 43.5 29T834-762L599-527ZM294-666q26-26 26-64t-26-64q-26-26-64-26t-64 26q-26 26-26 64t26 64q26 26 64 26t64-26Zm202.5 203.5Q502-468 502-476t-5.5-13.5Q491-495 483-495t-13.5 5.5Q464-484 464-476t5.5 13.5Q475-457 483-457t13.5-5.5ZM294-166q26-26 26-64t-26-64q-26-26-64-26t-64 26q-26 26-26 64t26 64q26 26 64 26t64-26Z",
    "zoom_in": "M346-556h-52q-12.75 0-21.37-8.68-8.63-8.67-8.63-21.5 0-12.82 8.63-21.32 8.62-8.5 21.37-8.5h52v-51q0-12.75 8.68-21.38 8.67-8.62 21.5-8.62 12.82 0 21.32 8.62 8.5 8.63 8.5 21.38v51h51q12.75 0 21.38 8.68 8.62 8.67 8.62 21.5 0 12.82-8.62 21.32-8.63 8.5-21.38 8.5h-51v52q0 12.75-8.68 21.37-8.67 8.63-21.5 8.63-12.82 0-21.32-8.63-8.5-8.62-8.5-21.37v-52Zm32 227q-108.16 0-183.08-75Q120-479 120-585t75-181q75-75 181.5-75t181 75Q632-691 632-584.85 632-542 618-502q-14 40-42 75l242 240q9 8.56 9 21.78T818-143q-9 9-22.22 9-13.22 0-21.78-9L533-384q-30 26-69.96 40.5Q423.08-329 378-329Zm-1-60q81.25 0 138.13-57.5Q572-504 572-585t-56.87-138.5Q458.25-781 377-781q-82.08 0-139.54 57.5Q180-666 180-585t57.46 138.5Q294.92-389 377-389Z",
    "delete": "M261-120q-24.75 0-42.37-17.63Q201-155.25 201-180v-570h-11q-12.75 0-21.37-8.68-8.63-8.67-8.63-21.5 0-12.82 8.63-21.32 8.62-8.5 21.37-8.5h158q0-13 8.63-21.5 8.62-8.5 21.37-8.5h204q12.75 0 21.38 8.62Q612-822.75 612-810h158q12.75 0 21.38 8.68 8.62 8.67 8.62 21.5 0 12.82-8.62 21.32-8.63 8.5-21.38 8.5h-11v570q0 24.75-17.62 42.37Q723.75-120 699-120H261Zm438-630H261v570h438v-570ZM418.5-274.63q8.5-8.62 8.5-21.37v-339q0-12.75-8.68-21.38-8.67-8.62-21.5-8.62-12.82 0-21.32 8.62-8.5 8.63-8.5 21.38v339q0 12.75 8.68 21.37 8.67 8.63 21.5 8.63 12.82 0 21.32-8.63Zm166 0q8.5-8.62 8.5-21.37v-339q0-12.75-8.68-21.38-8.67-8.62-21.5-8.62-12.82 0-21.32 8.62-8.5 8.63-8.5 21.38v339q0 12.75 8.68 21.37 8.67 8.63 21.5 8.63 12.82 0 21.32-8.63ZM261-750v570-570Z",
    "add_box": "M450-450v140q0 12.75 8.68 21.37 8.67 8.63 21.5 8.63 12.82 0 21.32-8.63 8.5-8.62 8.5-21.37v-140h140q12.75 0 21.38-8.68 8.62-8.67 8.62-21.5 0-12.82-8.62-21.32-8.63-8.5-21.38-8.5H510v-140q0-12.75-8.68-21.38-8.67-8.62-21.5-8.62-12.82 0-21.32 8.62-8.5 8.63-8.5 21.38v140H310q-12.75 0-21.37 8.68-8.63 8.67-8.63 21.5 0 12.82 8.63 21.32 8.62 8.5 21.37 8.5h140ZM180-120q-24 0-42-18t-18-42v-600q0-24 18-42t42-18h600q24 0 42 18t18 42v600q0 24-18 42t-42 18H180Zm0-60h600v-600H180v600Zm0-600v600-600Z",
    "info": "M504.5-288.63q8.5-8.62 8.5-21.37v-180q0-12.75-8.68-21.38-8.67-8.62-21.5-8.62-12.82 0-21.32 8.62-8.5 8.63-8.5 21.38v180q0 12.75 8.68 21.37 8.67 8.63 21.5 8.63 12.82 0 21.32-8.63Zm-1-314.57q9.5-9.2 9.5-22.8 0-14.45-9.48-24.22-9.48-9.78-23.5-9.78t-23.52 9.78Q447-640.45 447-626q0 13.6 9.48 22.8 9.48 9.2 23.5 9.2t23.52-9.2ZM480.27-80q-82.74 0-155.5-31.5Q252-143 197.5-197.5t-86-127.34Q80-397.68 80-480.5t31.5-155.66Q143-709 197.5-763t127.34-85.5Q397.68-880 480.5-880t155.66 31.5Q709-817 763-763t85.5 127Q880-563 880-480.27q0 82.74-31.5 155.5Q817-252 763-197.68q-54 54.31-127 86Q563-80 480.27-80Zm.23-60Q622-140 721-239.5t99-241Q820-622 721.19-721T480-820q-141 0-240.5 98.81T140-480q0 141 99.5 240.5t241 99.5Zm-.5-340Z",
}


def svg(nosaukums: str, krasa: str, izmers: int = 18) -> str:
    """Iekļaujama SVG ikona (atribūti ar vienpēdiņām — der JS virknēs)."""
    return (f"<svg class='msvg' width='{izmers}' height='{izmers}' viewBox='0 -960 960 960' "
            f"fill='{krasa}' aria-hidden='true'><path d='{MATERIAL_SVG[nosaukums]}'/></svg>")
