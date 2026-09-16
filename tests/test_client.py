"""Transport stubs verify session validation, redirects, and binary download boundaries."""

from types import SimpleNamespace

import click
import pytest

from myoralia import parsing
from myoralia.auth import SessionExpired
from myoralia.client import Client, public


@pytest.fixture
def client():
    with Client([]) as value:
        yield value


def test_public_output_removes_signed_links():
    assert public([{"id": "abc", "_url": "private", "_query": "private"}]) == [{"id": "abc"}]


def test_request_refuses_cross_origin_redirect(client, monkeypatch):
    monkeypatch.setattr(
        client.session,
        "request",
        lambda *a, **k: SimpleNamespace(
            status_code=302, headers={"location": "https://evil.test/"}
        ),
    )
    with pytest.raises(click.ClickException, match="outside"):
        client.request(parsing.BASE + "selection_account.php")


@pytest.mark.parametrize("status", [401, 403, 500])
def test_http_errors_fail(client, monkeypatch, status):
    monkeypatch.setattr(
        client.session, "request", lambda *a, **k: SimpleNamespace(status_code=status, headers={})
    )
    with pytest.raises(click.ClickException):
        client.request(parsing.BASE + "selection_account.php")


def test_multiple_accounts_require_selection(client, monkeypatch):
    monkeypatch.setattr(client, "accounts", lambda: [{"id": "1/1"}, {"id": "2/2"}])
    with pytest.raises(click.ClickException, match="--account"):
        client.dashboard()


def test_unknown_account_refused(client, monkeypatch):
    monkeypatch.setattr(client, "accounts", lambda: [{"id": "1/1"}])
    with pytest.raises(click.ClickException, match="--account"):
        client.dashboard("2/2")


def test_pdf_download_rejects_html(client, monkeypatch):
    monkeypatch.setattr(client, "documents", lambda *a: [{"id": "abc", "_url": "unused"}])
    monkeypatch.setattr(
        client, "request", lambda *a: SimpleNamespace(content=b"<html>Login</html>")
    )
    with pytest.raises(click.ClickException, match="PDF"):
        client.download("abc")


def test_pdf_download_returns_pdf_bytes(client, monkeypatch):
    monkeypatch.setattr(client, "documents", lambda *a: [{"id": "abc", "_url": "unused"}])
    monkeypatch.setattr(client, "request", lambda *a: SimpleNamespace(content=b"%PDF-1.7\nexample"))
    assert client.download("abc")[1] == b"%PDF-1.7\nexample"


def test_changed_account_identity_refused(client, monkeypatch):
    client.expected_identity = "Original User"
    body = (
        b'<header id="page-header">Bienvenue Other User <button>Compte</button>'
        b'<a href="../index.php?logout=1">Logout</a></header>'
    )
    monkeypatch.setattr(client, "request", lambda *a: SimpleNamespace(content=body, headers={}))
    with pytest.raises(click.ClickException, match="account changed"):
        client.page("unused")


def test_recursive_folders_are_loaded(client, monkeypatch):
    root = parsing.soup("""<a onclick="MAJDOSSIER('Urlhash=abc','folder1')">Contracts</a>""")
    child = b'<li><b>contract.pdf</b><a href="downdocged.php?Urlhash=def">PDF</a></li>'
    monkeypatch.setattr(client, "section", lambda *a: root)
    monkeypatch.setattr(client, "request", lambda *a: SimpleNamespace(content=child))
    assert client.documents()[0]["category"] == "Contracts"


def test_empty_download_checks_live_authentication(client, monkeypatch):
    monkeypatch.setattr(client, "request", lambda *a: SimpleNamespace(content=b""))

    def expired(url):
        raise SessionExpired("Session expired")

    monkeypatch.setattr(client, "page", expired)
    with pytest.raises(SessionExpired):
        client.pdf("unused")


def test_empty_document_with_valid_authentication_is_unavailable(client, monkeypatch):
    monkeypatch.setattr(client, "request", lambda *a: SimpleNamespace(content=b""))
    monkeypatch.setattr(client, "page", lambda *a: parsing.soup("<h1>Account</h1>"))
    with pytest.raises(click.ClickException, match="zero bytes"):
        client.pdf("unused")
