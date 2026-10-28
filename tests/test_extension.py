"""Terminal-free use from Claude Desktop: `connect`, its errors, and the export folder."""

import json
from contextlib import contextmanager
from pathlib import Path

import click
import pytest
from click.testing import CliRunner

from myoralia import auth, documents
from myoralia import cli as cli_module
from myoralia.cache import Catalog
from myoralia.cli import cli
from myoralia.documents_cli import export_dir


@pytest.fixture
def cookie():
    return {"name": "PHPSESSID", "value": "synthetic", "domain": "myoralia.fr", "path": "/"}


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("MYORALIA_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.delenv("MYORALIA_DOWNLOAD_DIR", raising=False)


class StubClient:
    """Accepts any cookies and reports one fixed account holder."""

    def __init__(self, cookies=None):
        self.cookies = cookies

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def whoami(self):
        return {"name": "Example User", "accounts": []}


@pytest.fixture
def chrome_session(monkeypatch, cookie):
    monkeypatch.setattr(auth, "chrome_cookies", lambda cookie_file=None: [cookie])
    monkeypatch.setattr(cli_module, "Client", StubClient)


def test_connect_saves_the_chrome_session(chrome_session):
    CliRunner().invoke(cli, ["connect", "--json"])
    assert auth.load_session()["identity"] == "Example User"


def test_connect_reports_the_account(chrome_session):
    result = CliRunner().invoke(cli, ["connect", "--json"])
    assert json.loads(result.stdout)["authenticated"] is True


def test_failed_connect_keeps_the_saved_session(monkeypatch, cookie):
    auth.save_session([cookie], "Example User")
    before = auth.config_path().read_bytes()

    def signed_out(cookie_file=None):
        raise click.ClickException("No live MyOralia session cookie in Chrome. " + auth.RECONNECT)

    monkeypatch.setattr(auth, "chrome_cookies", signed_out)
    CliRunner().invoke(cli, ["connect"])
    assert auth.config_path().read_bytes() == before


def test_connect_is_not_hidden_from_tools():
    assert "connect" in CliRunner().invoke(cli, ["--help"]).output


def test_not_connected_names_the_connect_tool():
    assert "`connect` tool" in CliRunner().invoke(cli, ["whoami"]).output


def test_not_connected_names_the_keychain_prompt():
    assert "Always Allow" in CliRunner().invoke(cli, ["whoami"]).output


def test_export_dir_unset_keeps_the_cache():
    assert export_dir() is None


def test_export_dir_blank_keeps_the_cache(monkeypatch):
    monkeypatch.setenv("MYORALIA_DOWNLOAD_DIR", "  ")
    assert export_dir() is None


def test_export_dir_expands_home(monkeypatch):
    monkeypatch.setenv("MYORALIA_DOWNLOAD_DIR", "~/Downloads/MyOralia")
    assert export_dir() == Path.home() / "Downloads" / "MyOralia"


@pytest.fixture
def cached_pdf(cookie):
    auth.save_session([cookie], "Example User")
    with Catalog("Example User", "1/1") as cache:
        cache.save_inventory(
            [
                {
                    "id": "abc",
                    "name": "example.pdf",
                    "category": "AG",
                    "source": "meetings",
                    "created": None,
                }
            ],
            {"complete": True},
        )
        cache.store("abc", b"%PDF-1.7\nexample")
        yield cache


def test_download_lands_in_the_export_dir(cached_pdf, monkeypatch, tmp_path):
    monkeypatch.setenv("MYORALIA_DOWNLOAD_DIR", str(tmp_path / "Downloads"))
    result = CliRunner().invoke(cli, ["documents", "download", "abc", "--offline", "--json"])
    assert json.loads(result.stdout)["path"] == str(tmp_path / "Downloads" / "abc-example.pdf")


def test_sync_exports_to_the_export_dir(cached_pdf, monkeypatch, tmp_path):
    monkeypatch.setenv("MYORALIA_DOWNLOAD_DIR", str(tmp_path / "Downloads"))

    @contextmanager
    def catalog(*args, **kwargs):
        yield cached_pdf

    monkeypatch.setattr(documents, "catalog", catalog)
    monkeypatch.setattr(documents, "sync", lambda *args: {"complete": True})
    monkeypatch.setattr(documents, "export", lambda cache, output: [])
    result = CliRunner().invoke(cli, ["documents", "sync", "--json"])
    assert json.loads(result.stdout)["output"] == str(tmp_path / "Downloads")
