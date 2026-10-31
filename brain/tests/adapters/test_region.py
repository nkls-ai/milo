from milo.adapters import region
from milo.services.sheets import currency


def test_off_the_mac_the_region_is_the_money_locale_without_its_encoding(monkeypatch):
    monkeypatch.setattr(region.sys, "platform", "linux")
    for name in ("LC_ALL", "LC_MONETARY", "LANG"):
        monkeypatch.delenv(name, raising=False)
    assert region.region() == ""
    monkeypatch.setenv("LANG", "en_US.UTF-8")
    monkeypatch.setenv("LC_MONETARY", "de_DE.UTF-8")
    assert region.region() == "de_DE" and currency(region.region()) == "EUR"
    monkeypatch.setenv("LC_ALL", "C")
    assert region.region() == "de_DE", "C says nothing about the region"


def test_on_a_mac_it_is_apple_locale(monkeypatch):
    monkeypatch.setattr(region.sys, "platform", "darwin")
    monkeypatch.setattr(region, "_apple_locale", lambda: "en_US@rg=dezzzz")
    assert region.region() == "en_US@rg=dezzzz"
