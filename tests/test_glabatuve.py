"""Glabātuves testi (SQLite vienmēr; Postgres — ja iestatīts TEST_DATABASE_URL)."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from glabatuve import Glabatuve  # noqa: E402


def _glabatuves(tmp_path):
    g = [Glabatuve(sqlite_cels=str(tmp_path / "t.db"))]
    if os.environ.get("TEST_DATABASE_URL"):
        g.append(Glabatuve(url=os.environ["TEST_DATABASE_URL"]))
    return g


def test_iestatijumi_un_priekvertejumi(tmp_path):
    for g in _glabatuves(tmp_path):
        g.izveidot()
        g.izveidot()                                   # atkārtoti — bez kļūdām
        g.saglabat_iestatijumu("tests_cenradis", {"ā": 1}, "A")
        g.saglabat_iestatijumu("tests_cenradis", {"ā": 2}, None)
        assert g.iestatijums("tests_cenradis")["vertiba"] == {"ā": 2}
        assert len(g.iestatijuma_vesture("tests_cenradis")) >= 2
        i = g.saglabat_priekvertejumu(kadastrs="64560020029", nosaukums="Mežpurvi", avots="pdf",
                                      dati={"x": [1]}, kopsavilkums={"m3": 1}, pdf=b"%PDF\x00\xff")
        assert g.meklet_priekvertejumus("6456002")[0]["id"] == i
        assert g.ielasit_priekvertejumu(i)["pdf"] == b"%PDF\x00\xff"
        g.saglabat_priekvertejumu(kadastrs="64560020029", nosaukums="Jauns", avots="pdf", dati={},
                                  kopsavilkums={}, id_=i)
        assert g.ielasit_priekvertejumu(i)["nosaukums"] == "Jauns"
        g.dzest_priekvertejumu(i)
        assert g.ielasit_priekvertejumu(i) is None
