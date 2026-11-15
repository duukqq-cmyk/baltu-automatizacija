"""Pastāvīgā glabātuve: cenrādis/iestatījumi un saglabātie priekšvērtējumi.

Datubāze:
  * DATABASE_URL (env vai Streamlit Secrets), piem. ``postgresql://lietotajs:parole@host/db``
    — ieteicams serverī/Streamlit Cloud, jo tur lokālie faili pēc restarta pazūd;
  * citādi SQLite fails ``dati/baltu.db`` (vai ``BALTU_DB`` ceļš) — derīgs lokāli un VPS.

Tīra loģika (bez Streamlit atkarības, izņemot Secrets nolasīšanu, ja pieejami).
"""
from __future__ import annotations

import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone

_NOKL_SQLITE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dati", "baltu.db")


def _secret(nosaukums: str) -> str | None:
    v = os.environ.get(nosaukums)
    if v:
        return v
    try:
        import streamlit as st
        return st.secrets.get(nosaukums)  # type: ignore[no-any-return]
    except Exception:  # noqa: BLE001 — nav Streamlit vai secrets.toml
        return None


def _tagad() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Glabatuve:
    url: str | None = None          # postgres URL; None -> SQLite
    sqlite_cels: str | None = None

    @classmethod
    def no_konfiguracijas(cls) -> "Glabatuve":
        url = _secret("DATABASE_URL")
        if url and url.startswith(("postgres://", "postgresql://")):
            return cls(url=url)
        return cls(sqlite_cels=os.environ.get("BALTU_DB", _NOKL_SQLITE))

    # --- savienojums -------------------------------------------------------
    @property
    def ir_postgres(self) -> bool:
        return self.url is not None

    @property
    def apraksts(self) -> str:
        if self.ir_postgres:
            return "Postgres (DATABASE_URL)"
        return f"SQLite ({self.sqlite_cels})"

    @contextmanager
    def _savienojums(self):
        if self.ir_postgres:
            import psycopg  # noqa: PLC0415 — vajadzīgs tikai ar Postgres
            con = psycopg.connect(self.url)
        else:
            os.makedirs(os.path.dirname(self.sqlite_cels) or ".", exist_ok=True)
            con = sqlite3.connect(self.sqlite_cels)
        try:
            yield con
            con.commit()
        finally:
            con.close()

    def _sql(self, sql: str) -> str:
        return sql.replace("?", "%s") if self.ir_postgres else sql

    def _izpildit(self, sql: str, params: tuple = (), viens=False, visi=False):
        with self._savienojums() as con:
            cur = con.cursor()
            cur.execute(self._sql(sql), params)
            if viens:
                return cur.fetchone()
            if visi:
                return cur.fetchall()
            return None

    def izveidot(self) -> None:
        blob = "BYTEA" if self.ir_postgres else "BLOB"
        id_auto = "SERIAL PRIMARY KEY" if self.ir_postgres else "INTEGER PRIMARY KEY AUTOINCREMENT"
        with self._savienojums() as con:
            cur = con.cursor()
            for ddl in (
                "CREATE TABLE IF NOT EXISTS iestatijumi (atslega TEXT PRIMARY KEY, vertiba TEXT NOT NULL, "
                "mainits TEXT NOT NULL, autors TEXT)",
                f"CREATE TABLE IF NOT EXISTS iestatijumu_vesture (id {id_auto}, atslega TEXT NOT NULL, "
                "vertiba TEXT NOT NULL, mainits TEXT NOT NULL, autors TEXT)",
                f"CREATE TABLE IF NOT EXISTS priekvertejumi (id TEXT PRIMARY KEY, kadastrs TEXT, "
                "nosaukums TEXT, avots TEXT, izveidots TEXT NOT NULL, mainits TEXT NOT NULL, autors TEXT, "
                f"kopsavilkums TEXT, dati TEXT NOT NULL, pdf_nosaukums TEXT, pdf {blob})",
                "CREATE INDEX IF NOT EXISTS priekvertejumi_kadastrs ON priekvertejumi (kadastrs)",
            ):
                cur.execute(ddl)

    # --- iestatījumi (cenrādis) --------------------------------------------
    def iestatijums(self, atslega: str) -> dict | None:
        r = self._izpildit("SELECT vertiba, mainits, autors FROM iestatijumi WHERE atslega = ?",
                           (atslega,), viens=True)
        if not r:
            return None
        return {"vertiba": json.loads(r[0]), "mainits": r[1], "autors": r[2]}

    def saglabat_iestatijumu(self, atslega: str, vertiba, autors: str | None = None) -> None:
        teksts = json.dumps(vertiba, ensure_ascii=False)
        laiks = _tagad()
        if self.ir_postgres:
            sql = ("INSERT INTO iestatijumi (atslega, vertiba, mainits, autors) VALUES (?, ?, ?, ?) "
                   "ON CONFLICT (atslega) DO UPDATE SET vertiba = EXCLUDED.vertiba, "
                   "mainits = EXCLUDED.mainits, autors = EXCLUDED.autors")
        else:
            sql = "INSERT OR REPLACE INTO iestatijumi (atslega, vertiba, mainits, autors) VALUES (?, ?, ?, ?)"
        self._izpildit(sql, (atslega, teksts, laiks, autors))
        self._izpildit("INSERT INTO iestatijumu_vesture (atslega, vertiba, mainits, autors) VALUES (?, ?, ?, ?)",
                       (atslega, teksts, laiks, autors))

    def iestatijuma_vesture(self, atslega: str, limits: int = 30) -> list[dict]:
        r = self._izpildit("SELECT id, mainits, autors, vertiba FROM iestatijumu_vesture WHERE atslega = ? "
                           "ORDER BY id DESC LIMIT ?", (atslega, limits), visi=True)
        return [{"id": x[0], "mainits": x[1], "autors": x[2], "vertiba": json.loads(x[3])} for x in r]

    # --- priekšvērtējumi ---------------------------------------------------
    def saglabat_priekvertejumu(self, *, kadastrs: str | None, nosaukums: str, avots: str,
                                dati: dict, kopsavilkums: dict, autors: str | None = None,
                                pdf: bytes | None = None, pdf_nosaukums: str | None = None,
                                id_: str | None = None) -> str:
        """Saglabā jaunu vai pārraksta esošu (id_) priekšvērtējumu; atgriež id."""
        laiks = _tagad()
        dati_t = json.dumps(dati, ensure_ascii=False)
        kops_t = json.dumps(kopsavilkums, ensure_ascii=False)
        if id_ and self._izpildit("SELECT 1 FROM priekvertejumi WHERE id = ?", (id_,), viens=True):
            self._izpildit(
                "UPDATE priekvertejumi SET kadastrs = ?, nosaukums = ?, avots = ?, mainits = ?, autors = ?, "
                "kopsavilkums = ?, dati = ?, pdf_nosaukums = ?, pdf = ? WHERE id = ?",
                (kadastrs, nosaukums, avots, laiks, autors, kops_t, dati_t, pdf_nosaukums, pdf, id_))
            return id_
        id_ = id_ or uuid.uuid4().hex[:12]
        self._izpildit(
            "INSERT INTO priekvertejumi (id, kadastrs, nosaukums, avots, izveidots, mainits, autors, "
            "kopsavilkums, dati, pdf_nosaukums, pdf) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (id_, kadastrs, nosaukums, avots, laiks, laiks, autors, kops_t, dati_t, pdf_nosaukums, pdf))
        return id_

    def meklet_priekvertejumus(self, teksts: str = "", limits: int = 200) -> list[dict]:
        """Saraksts (bez datiem un PDF). Meklē pēc kadastra nr. vai nosaukuma daļas."""
        maska = f"%{teksts.strip()}%"
        r = self._izpildit(
            "SELECT id, kadastrs, nosaukums, avots, izveidots, mainits, autors, kopsavilkums "
            "FROM priekvertejumi WHERE COALESCE(kadastrs, '') LIKE ? OR COALESCE(nosaukums, '') LIKE ? "
            "ORDER BY mainits DESC LIMIT ?", (maska, maska, limits), visi=True)
        return [{"id": x[0], "kadastrs": x[1], "nosaukums": x[2], "avots": x[3], "izveidots": x[4],
                 "mainits": x[5], "autors": x[6], "kopsavilkums": json.loads(x[7] or "{}")} for x in r]

    def ielasit_priekvertejumu(self, id_: str) -> dict | None:
        x = self._izpildit("SELECT id, kadastrs, nosaukums, avots, izveidots, mainits, autors, kopsavilkums, "
                           "dati, pdf_nosaukums, pdf FROM priekvertejumi WHERE id = ?", (id_,), viens=True)
        if not x:
            return None
        return {"id": x[0], "kadastrs": x[1], "nosaukums": x[2], "avots": x[3], "izveidots": x[4],
                "mainits": x[5], "autors": x[6], "kopsavilkums": json.loads(x[7] or "{}"),
                "dati": json.loads(x[8]), "pdf_nosaukums": x[9], "pdf": bytes(x[10]) if x[10] else None}

    def dzest_priekvertejumu(self, id_: str) -> None:
        self._izpildit("DELETE FROM priekvertejumi WHERE id = ?", (id_,))


_GLABATUVE: Glabatuve | None = None


def glabatuve() -> Glabatuve:
    """Kopīgā glabātuve (tabulas izveido pirmajā izsaukumā)."""
    global _GLABATUVE
    if _GLABATUVE is None:
        g = Glabatuve.no_konfiguracijas()
        g.izveidot()
        _GLABATUVE = g
    return _GLABATUVE
