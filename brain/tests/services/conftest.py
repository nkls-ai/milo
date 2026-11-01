"""Controlled desktop facts for services that otherwise query installed applications."""
import pytest


@pytest.fixture
def fake_installed_apps(tmp_path, monkeypatch):
    from milo.services import helpers

    folder = tmp_path / "Applications"
    for name in ("Safari", "Microsoft Excel", "Mail"):
        (folder / (name + ".app")).mkdir(parents=True)
    monkeypatch.setattr(helpers, "APP_FOLDERS", (folder,))
    helpers.is_installed_app.cache_clear()
    yield helpers.is_installed_app
    helpers.is_installed_app.cache_clear()
