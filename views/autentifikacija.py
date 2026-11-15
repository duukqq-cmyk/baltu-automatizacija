"""Lietotāju pieteikšanās (Streamlit st.login, OpenID Connect — Google vai Microsoft Entra ID).

Ieslēdzas, kad secrets ir sadaļa [auth]. Kas drīkst ienākt — sadaļā [piekluve]:

    [auth]
    redirect_uri = "https://<app>.streamlit.app/oauth2callback"
    cookie_secret = "<gara nejauša virkne>"
    client_id = "..."
    client_secret = "..."
    server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"

    [piekluve]
    domeni = ["uznemums.lv"]             # visi ar e-pastu šajā domēnā
    epasti = ["kads.cits@gmail.com"]     # papildus atsevišķi e-pasti

Pāreja uz Microsoft 365: server_metadata_url =
"https://login.microsoftonline.com/<tenant-id>/v2.0/.well-known/openid-configuration"
un Entra ID app reģistrācijas client_id / client_secret.
"""
from __future__ import annotations

from typing import Iterable

import streamlit as st


def atlauts(epasts: str | None, domeni: Iterable[str] = (), epasti: Iterable[str] = ()) -> bool:
    """Vai e-pasts ir atļauto sarakstā (pēc precīza e-pasta vai domēna)."""
    e = (epasts or "").strip().lower()
    if "@" not in e:
        return False
    if e in {x.strip().lower() for x in epasti}:
        return True
    domens = e.rsplit("@", 1)[1]
    return domens in {d.strip().lower().lstrip("@") for d in domeni}


def _secrets_sadala(nos: str) -> dict:
    try:
        return dict(st.secrets.get(nos, {}) or {})
    except Exception:  # noqa: BLE001 — nav secrets.toml
        return {}


def pieteiksanas_ieslegta() -> bool:
    return bool(_secrets_sadala("auth"))


def prasit_pieteiksanos() -> None:
    """Aptur lapu, ja lietotājs nav pieteicies vai nav atļauto sarakstā."""
    if not st.user.get("is_logged_in", False):
        st.title(":material/forest: Automatizācijas platforma")
        st.write("Lai turpinātu, piesakies ar sava uzņēmuma kontu.")
        if st.button(":material/login: Pieteikties", type="primary"):
            st.login()
        st.stop()

    piekluve = _secrets_sadala("piekluve")
    epasts = st.user.get("email")
    verificets = st.user.get("email_verified", True) not in (False, "false")
    if not (verificets and atlauts(epasts, piekluve.get("domeni", []), piekluve.get("epasti", []))):
        st.error(f"Kontam **{epasts or '?'}** nav piekļuves šai platformai. "
                 "Lūdz administratoru tevi pievienot vai piesakies ar citu kontu.")
        if st.button(":material/logout: Iziet"):
            st.logout()
        st.stop()

    # Vārds izmaiņu vēsturei un saglabātajiem priekšvērtējumiem
    st.session_state["lietotaja_vards"] = st.user.get("name") or epasts


def lietotaja_josla() -> None:
    """Sānjoslā: kas pieteicies + izrakstīšanās."""
    st.sidebar.caption(f":material/person: {st.user.get('name') or ''}  \n{st.user.get('email') or ''}")
    if st.sidebar.button(":material/logout: Iziet", use_container_width=True):
        st.logout()
