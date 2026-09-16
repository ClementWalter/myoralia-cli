"""Cached CLI reads and sync resumption operate without unnecessary website requests."""

import json
import os
import subprocess
from contextlib import contextmanager
from types import SimpleNamespace

import click
import pytest
from click.testing import CliRunner

from myoralia import auth, documents
from myoralia.cache import Catalog
from myoralia.cli import cli


@pytest.fixture
def cache(tmp_path, monkeypatch):
    monkeypatch.setenv("MYORALIA_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    auth.save_session(
        [{"name": "PHPSESSID", "value": "synthetic", "domain": "myoralia.fr", "path": "/"}],
        "Example User",
    )
    with Catalog("Example User", "1/1") as value:
        value.save_inventory(
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
        yield value


@pytest.fixture
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("No network request is allowed")

    monkeypatch.setattr(documents, "Client", forbidden)


def test_fresh_list_avoids_network(cache, no_network):
    assert CliRunner().invoke(cli, ["documents", "list", "--json"]).exit_code == 0


def test_offline_list_avoids_network(cache, no_network):
    assert (
        json.loads(CliRunner().invoke(cli, ["documents", "list", "--offline", "--json"]).output)[0][
            "id"
        ]
        == "abc"
    )


def test_offline_download_avoids_network(cache, no_network, tmp_path):
    cache.store("abc", b"%PDF-1.7\nexample")
    target = tmp_path / "export.pdf"
    CliRunner().invoke(cli, ["documents", "download", "abc", "--offline", "-o", str(target)])
    assert target.read_bytes() == b"%PDF-1.7\nexample"


def test_offline_missing_pdf_fails(cache, no_network, tmp_path):
    result = CliRunner().invoke(
        cli, ["documents", "download", "abc", "--offline", "-o", str(tmp_path / "missing.pdf")]
    )
    assert result.exit_code == 1


def test_offline_refresh_is_rejected(cache):
    assert CliRunner().invoke(cli, ["documents", "list", "--offline", "--refresh"]).exit_code == 2


def test_incomplete_cache_refused_offline(cache):
    cache.save_inventory([], {"complete": False})
    with pytest.raises(click.ClickException, match="complete"):
        documents.listing(cache, offline=True)


def test_sync_reuses_valid_pdf(cache, monkeypatch):
    cache.store("abc", b"%PDF-1.7\nexample")

    @contextmanager
    def client():
        yield SimpleNamespace()

    monkeypatch.setattr(documents, "Client", client)
    monkeypatch.setattr(
        documents.inventory, "scan", lambda *a: (cache.documents(), {"complete": True})
    )
    assert documents.sync(cache)["new_downloads"] == 0


def test_sync_checkpoints_failure(cache, monkeypatch):
    @contextmanager
    def client():
        yield SimpleNamespace(pdf=lambda *a: b"<html>Error</html>")

    monkeypatch.setattr(documents, "Client", client)
    monkeypatch.setattr(
        documents.inventory,
        "scan",
        lambda *a: (
            [{**cache.documents()[0], "_url": "https://myoralia.fr/document"}],
            {"complete": True},
        ),
    )
    assert documents.sync(cache)["complete"] is False


def test_export_keeps_existing_different_file(cache, tmp_path):
    cache.store("abc", b"%PDF-1.7\nexample")
    target = tmp_path / "output" / "meetings" / "abc-example.pdf"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"original")
    try:
        documents.export(cache, tmp_path / "output")
    except click.ClickException:
        pass
    assert target.read_bytes() == b"original"


def test_export_is_idempotent(cache, tmp_path):
    cache.store("abc", b"%PDF-1.7\nexample")
    documents.export(cache, tmp_path / "output")
    assert documents.export(cache, tmp_path / "output") == 1


def test_subprocess_offline_json(cache):
    result = subprocess.run(
        ["myoralia", "documents", "list", "--offline", "--json"],
        env=os.environ.copy(),
        check=True,
        text=True,
        capture_output=True,
    )
    assert json.loads(result.stdout)[0]["id"] == "abc"


def test_failed_refresh_retries_despite_existing_blob(cache, monkeypatch):
    cache.store("abc", b"%PDF-1.7\nold")
    cache.failure("abc", "Download failed")

    @contextmanager
    def client():
        yield SimpleNamespace(pdf=lambda *a: b"%PDF-1.7\nnew")

    monkeypatch.setattr(documents, "Client", client)
    monkeypatch.setattr(
        documents.inventory,
        "scan",
        lambda *a: (
            [{**cache.documents()[0], "_url": "https://myoralia.fr/document"}],
            {"complete": True},
        ),
    )
    assert documents.sync(cache)["new_downloads"] == 1


def test_manifest_maps_documents_to_cached_files(cache):
    cache.store("abc", b"%PDF-1.7\nexample")
    documents.write_manifest(cache)
    manifest = json.loads((cache.path / "manifest.json").read_text())
    assert (cache.path / manifest["documents"][0]["file"]).is_file()


@pytest.mark.parametrize("command", ["sync", "status"])
def test_document_command_help_has_example(command):
    assert "Example" in CliRunner().invoke(cli, ["documents", command, "--help"]).output


def test_expired_session_stops_bulk_requests(cache, monkeypatch):
    calls = []

    def expired(url):
        calls.append(url)
        raise auth.SessionExpired("Session expired")

    @contextmanager
    def client():
        yield SimpleNamespace(pdf=expired)

    monkeypatch.setattr(documents, "Client", client)
    row = {**cache.documents()[0], "_url": "https://myoralia.fr/document"}
    monkeypatch.setattr(
        documents.inventory, "scan", lambda *a: ([row, {**row, "id": "def"}], {"complete": True})
    )
    documents.sync(cache)
    assert len(calls) == 1


@pytest.mark.parametrize(
    ("expired", "message"),
    [(True, "myoralia login --browser chrome"), (False, "see errors above")],
)
def test_incomplete_sync_explains_recovery(cache, monkeypatch, expired, message):
    @contextmanager
    def catalog(*args, **kwargs):
        yield cache

    monkeypatch.setattr(documents, "catalog", catalog)
    monkeypatch.setattr(
        documents, "sync", lambda *args: {"complete": False, "session_expired": expired}
    )
    result = CliRunner().invoke(cli, ["documents", "sync", "--json"])
    assert message in result.stderr
