from views.autentifikacija import atlauts


def test_domens_un_epasts():
    assert atlauts("Janis@Uznemums.lv", domeni=["uznemums.lv"])
    assert atlauts("a@b.lv", domeni=["@b.lv"])
    assert atlauts("kads@gmail.com", epasti=["Kads@gmail.com"])
    assert not atlauts("kads@gmail.com", domeni=["uznemums.lv"])
    assert not atlauts("x@uznemums.lv.evil.com", domeni=["uznemums.lv"])
    assert not atlauts(None, domeni=["uznemums.lv"])
    assert not atlauts("bez-pasta", domeni=["uznemums.lv"])
