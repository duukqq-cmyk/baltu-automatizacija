"""monday.com GraphQL API klients (tikai standarta bibliotēka, bez papildu atkarībām).

Lieto:
    k = MondayKlients(token)
    k.boardu_saraksts()             -> [{"id", "nosaukums", "workspace", "rindas"}]
    k.ieladet_boardu(board_id)      -> Boards (kolonnas + visas rindas ar lapošanu)
    k.izveidot_kolonnu(id, nosaukums, tips)

Tokenu iegūst monday: profila bilde → Developers → My access tokens.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Callable

API_URL = "https://api.monday.com/v2"
API_VERSION = "2025-04"
LAPAS_IZMERS = 200


class MondayKluda(RuntimeError):
    """Saprotama kļūda lietotājam (tokens, tīkls, API limiti)."""


@dataclass
class Kolonna:
    id: str
    title: str
    type: str


@dataclass
class Rinda:
    """Viena monday rinda (item). Vērtības pēc kolonnas nosaukuma (title)."""
    board_id: str
    board_nosaukums: str
    item_id: str
    nosaukums: str
    grupa: str
    izveidots: str | None
    vertibas: dict[str, str] = field(default_factory=dict)


@dataclass
class Boards:
    id: str
    nosaukums: str
    kolonnas: list[Kolonna]
    rindas: list[Rinda]
    workspace: str = ""
    grupas: list[str] = field(default_factory=list)


_ITEM_LAUKI = """
    id
    name
    created_at
    group { title }
    column_values {
      id
      text
      type
      value
      ... on FormulaValue { display_value }
      ... on MirrorValue { display_value }
      ... on BoardRelationValue { display_value }
    }
"""

_Q_BOARDS = """
query ($page: Int!) {
  boards(limit: 100, page: $page, state: active) {
    id name type items_count
    workspace { id name }
  }
}
"""

_Q_BOARD = """
query ($ids: [ID!], $limit: Int!) {
  boards(ids: $ids) {
    id name
    workspace { name }
    groups { title }
    columns { id title type }
    items_page(limit: $limit) { cursor items { %s } }
  }
}
""" % _ITEM_LAUKI

_Q_NAKAMA_LAPA = """
query ($cursor: String!, $limit: Int!) {
  next_items_page(cursor: $cursor, limit: $limit) { cursor items { %s } }
}
""" % _ITEM_LAUKI

_M_KOLONNA = """
mutation ($board: ID!, $title: String!, $tips: ColumnType!) {
  create_column(board_id: $board, title: $title, column_type: $tips) { id title type }
}
"""


class MondayKlients:
    def __init__(self, token: str, url: str = API_URL, timeout: int = 60,
                 transport: Callable[[dict], dict] | None = None):
        if not token and transport is None:
            raise MondayKluda("Nav norādīts monday API tokens.")
        self.token = token
        self.url = url
        self.timeout = timeout
        self._transport = transport or self._http

    # --- zemā līmeņa izsaukums -------------------------------------------------
    def _http(self, payload: dict) -> dict:
        req = urllib.request.Request(
            self.url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": self.token,
                "Content-Type": "application/json",
                "API-Version": API_VERSION,
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as atb:
            return json.loads(atb.read().decode("utf-8"))

    def vaicajums(self, query: str, variables: dict | None = None, meginajumi: int = 5) -> dict:
        pauze = 5.0
        for _ in range(meginajumi):
            try:
                atb = self._transport({"query": query, "variables": variables or {}})
            except urllib.error.HTTPError as e:
                if e.code == 401:
                    raise MondayKluda("monday noraidīja tokenu (401) — pārbaudi API tokenu.") from e
                if e.code == 429 or e.code >= 500:
                    time.sleep(pauze)
                    pauze *= 2
                    continue
                raise MondayKluda(f"monday API kļūda HTTP {e.code}") from e
            except urllib.error.URLError as e:
                raise MondayKluda(f"Nevar sasniegt monday API: {e.reason}") from e

            kludas = atb.get("errors") or []
            if atb.get("error_message"):
                kludas.append({"message": atb["error_message"], "extensions": {"code": atb.get("error_code", "")}})
            if kludas:
                ext = kludas[0].get("extensions") or {}
                kods = str(ext.get("code", ""))
                if any(x in kods.upper() for x in ("COMPLEXITY", "RATE_LIMIT", "MAX_CONCURRENCY")):
                    time.sleep(float(ext.get("retry_in_seconds") or pauze))
                    pauze *= 2
                    continue
                raise MondayKluda("monday API: " + "; ".join(k.get("message", "?") for k in kludas))
            return atb.get("data") or {}
        raise MondayKluda("monday API limits pārsniegts — mēģini pēc brīža vēlreiz.")

    # --- augsta līmeņa funkcijas ----------------------------------------------
    def boardu_saraksts(self) -> list[dict]:
        rezultats, lapa = [], 1
        while True:
            dati = self.vaicajums(_Q_BOARDS, {"page": lapa})
            boardi = dati.get("boards") or []
            for b in boardi:
                if b.get("type") not in (None, "board"):
                    continue  # subitemu un dokumentu boardi
                rezultats.append({
                    "id": str(b["id"]),
                    "nosaukums": b["name"],
                    "workspace": (b.get("workspace") or {}).get("name") or "Main workspace",
                    "rindas": b.get("items_count"),
                })
            if len(boardi) < 100:
                return rezultats
            lapa += 1

    def ieladet_boardu(self, board_id: str) -> Boards:
        dati = self.vaicajums(_Q_BOARD, {"ids": [str(board_id)], "limit": LAPAS_IZMERS})
        boardi = dati.get("boards") or []
        if not boardi:
            raise MondayKluda(f"Board {board_id} nav atrasts vai tam nav piekļuves.")
        b = boardi[0]
        kolonnas = [Kolonna(str(c["id"]), c["title"].strip(), c["type"]) for c in b["columns"]]
        nosaukumi = {c.id: c.title for c in kolonnas}
        boards = Boards(
            id=str(b["id"]), nosaukums=b["name"], kolonnas=kolonnas, rindas=[],
            workspace=(b.get("workspace") or {}).get("name") or "",
            grupas=[g["title"] for g in b.get("groups") or []],
        )
        lapa = b["items_page"]
        while True:
            for it in lapa["items"]:
                boards.rindas.append(_rinda(boards, it, nosaukumi))
            kursors = lapa.get("cursor")
            if not kursors:
                return boards
            lapa = self.vaicajums(_Q_NAKAMA_LAPA, {"cursor": kursors, "limit": LAPAS_IZMERS})["next_items_page"]

    def izveidot_kolonnu(self, board_id: str, nosaukums: str, tips: str) -> dict:
        return self.vaicajums(_M_KOLONNA, {"board": str(board_id), "title": nosaukums, "tips": tips})["create_column"]


def _rinda(boards: Boards, it: dict, nosaukumi: dict[str, str]) -> Rinda:
    vert = {}
    for cv in it.get("column_values") or []:
        title = nosaukumi.get(str(cv["id"]))
        if not title:
            continue
        teksts = cv.get("text") or cv.get("display_value") or ""
        if cv.get("type") == "checkbox":
            # checkbox teksts ir "v"/""; drošāk skatīt value
            try:
                teksts = "v" if (json.loads(cv.get("value") or "null") or {}).get("checked") in (True, "true") else ""
            except (ValueError, AttributeError):
                pass
        vert[title] = str(teksts).strip()
    return Rinda(
        board_id=boards.id,
        board_nosaukums=boards.nosaukums,
        item_id=str(it["id"]),
        nosaukums=it.get("name") or "",
        grupa=((it.get("group") or {}).get("title") or "").strip(),
        izveidots=it.get("created_at"),
        vertibas=vert,
    )
