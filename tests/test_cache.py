"""Synthetic PDF bytes exercise persistence, isolation, integrity, and deduplication."""

import json

import click
import pytest

from myoralia.cache import Catalog, atomic_write, cached_accounts


@pytest.fixture
def row():
    return {
        "id": "abc",
        "name": "example.pdf",
        "category": "AG",
        "source": "meetings",
        "_url": "https://myoralia.fr/extranet/downdoc.php?Urlhash=secret",
    }


@pytest.fixture
def cache(tmp_path, monkeypatch, row):
    monkeypatch.setenv("MYORALIA_CACHE_DIR", str(tmp_path))
    with Catalog("Example User", "1/1") as value:
        value.save_inventory([row], {"complete": True})
        yield value


def test_inventory_never_persists_signed_urls(cache):
    assert "Urlhash" not in json.dumps(cache.documents())


def test_fresh_inventory(cache):
    assert cache.fresh(3600)


def test_expired_inventory(cache):
    assert not cache.fresh(0)


def test_incomplete_inventory_never_fresh(cache, row):
    cache.save_inventory([row], {"complete": False})
    assert not cache.fresh(3600)


def test_account_discovery_is_offline(cache):
    assert cached_accounts("Example User") == ["1/1"]


def test_identity_isolation(cache):
    assert cached_accounts("Another User") == []


def test_pdf_deduplication(cache, row):
    cache.save_inventory([row, {**row, "id": "def"}], {"complete": True})
    first = cache.store("abc", b"%PDF-1.7\nexample")
    second = cache.store("def", b"%PDF-1.7\nexample")
    assert first == second


def test_pdf_permissions(cache):
    path = cache.store("abc", b"%PDF-1.7\nexample")
    assert path.stat().st_mode & 0o777 == 0o600


def test_database_permissions(cache):
    assert (cache.path / "index.sqlite3").stat().st_mode & 0o777 == 0o600


def test_corrupt_blob_requires_redownload(cache):
    path = cache.store("abc", b"%PDF-1.7\nexample")
    path.write_bytes(b"%PDF-corrupt")
    assert cache.blob("abc") is None


def test_missing_blob_requires_redownload(cache):
    path = cache.store("abc", b"%PDF-1.7\nexample")
    path.unlink()
    assert cache.blob("abc") is None


def test_non_pdf_rejected(cache):
    with pytest.raises(click.ClickException, match="PDF"):
        cache.store("abc", b"<html>Login</html>")


def test_empty_provider_document_is_explicit(cache):
    with pytest.raises(click.ClickException, match="zero bytes"):
        cache.store("abc", b"")


def test_inventory_refresh_retains_download(cache, row):
    path = cache.store("abc", b"%PDF-1.7\nexample")
    cache.save_inventory([row], {"complete": True})
    assert cache.blob("abc") == path


def test_removed_document_blob_is_retained(cache):
    path = cache.store("abc", b"%PDF-1.7\nexample")
    cache.save_inventory([], {"complete": True})
    assert path.exists()


def test_checkpoint_survives_reopening(cache):
    cache.store("abc", b"%PDF-1.7\nexample")
    with Catalog("Example User", "1/1") as reopened:
        assert reopened.blob("abc") is not None


def test_duplicate_inventory_preserves_existing(cache, row):
    try:
        cache.save_inventory([row, row], {"complete": True})
    except click.ClickException:
        pass
    assert len(cache.documents()) == 1


def test_atomic_export_cannot_overwrite(tmp_path):
    target = tmp_path / "original.pdf"
    target.write_bytes(b"original")
    with pytest.raises(FileExistsError):
        atomic_write(target, b"replacement", overwrite=False)
