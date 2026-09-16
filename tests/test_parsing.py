"""Synthetic website fixtures verify parsing without retaining account data."""

import click
import pytest

from myoralia import parsing


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1\u00a0876,54 €", "1876.54"),
        ("-111,11 €", "-111.11"),
        ("0,00 €", "0.00"),
        ("", None),
        ("1 234,56\x80", "1234.56"),
    ],
)
def test_decimal_amount(value, expected):
    assert parsing.amount(value) == expected


@pytest.mark.parametrize("value", ["unknown", "1,2,3"])
def test_bad_amount_fails(value):
    with pytest.raises(click.ClickException):
        parsing.amount(value)


@pytest.mark.parametrize(
    "url",
    [
        "https://evil.test/file",
        "//evil.test/file",
        "https://myoralia.fr.evil.test/",
        "http://myoralia.fr/",
        "https://user@myoralia.fr/",
        "https://myoralia.fr:444/",
    ],
)
def test_foreign_links_rejected(url):
    with pytest.raises(click.ClickException):
        parsing.safe_url(url)


def test_relative_link_is_site_scoped():
    assert parsing.safe_url("downdocged.php?Urlhash=abc") == (
        "https://myoralia.fr/extranet/downdocged.php?Urlhash=abc"
    )


def test_identity_requires_authenticated_layout():
    with pytest.raises(click.ClickException):
        parsing.identity(parsing.soup("<h1>Service unavailable</h1>"))


def test_expired_session_rejected():
    with pytest.raises(click.ClickException, match="expired"):
        parsing.identity(parsing.soup('<input type="password">'))


def test_identity_extracts_name():
    assert (
        parsing.identity(
            parsing.soup(
                '<header id="page-header">Bienvenue Example User <button>Compte</button>'
                '<a href="../index.php?logout=1">Déconnexion</a></header>'
            )
        )
        == "Example User"
    )


def test_identity_ignores_help_modal_header():
    assert (
        parsing.identity(
            parsing.soup(
                '<header id="page-header">Retour à la liste</header>'
                '<header id="page-header">Bienvenue Example User <button>Compte</button>'
                '<a href="../index.php?logout=1">Déconnexion</a></header>'
            )
        )
        == "Example User"
    )


def test_accounts_use_stable_reference():
    page = parsing.soup("""<a class="account-item" onclick="ajaxload('Urlhash=abc123')">
      <p class="sr-only">Copropriété syndic</p><h3>Example property</h3>
      <p>Réf n° : 1234 / 0001</p><small><i>Example agency</i></small></a>""")
    assert parsing.accounts(page)[0]["id"] == "1234/0001"


@pytest.fixture
def statement_page():
    return parsing.soup("""<div class="content-inner"><table>
    <thead><tr><th colspan="5">Solde débiteur : 12,34 €</th></tr></thead>
    <tbody><tr><td>01/10/2026</td><td>Charge</td>
    <td class="hidden-sm-down">12,34 €</td><td class="hidden-md-up">12,34 €</td>
    <td class="hidden-sm-down"></td><td>12,34 €</td></tr></tbody></table></div>""")


def test_mobile_statement_amount_is_not_duplicated(statement_page):
    assert parsing.statement(statement_page)["transactions"] == [
        {
            "date": "2026-10-01",
            "label": "Charge",
            "debit": "12.34",
            "credit": None,
            "balance": "12.34",
        }
    ]


def test_statement_retains_website_balance_label(statement_page):
    assert parsing.statement(statement_page)["balance_label"] == "Solde débiteur : 12,34 €"


def test_statement_preserves_undated_year_end_balance():
    page = parsing.soup(
        '<div class="content-inner"><table><tbody><tr><td></td>'
        "<td>Solde à jour au 31/12/2025</td><td></td><td></td><td>0,00 €</td>"
        "</tr></tbody></table></div>"
    )
    assert parsing.statement(page)["balance_rows"] == [
        {"label": "Solde à jour au 31/12/2025", "balance": "0.00"}
    ]


@pytest.fixture
def document_html():
    return """<div class="collapse-box"><a class="collapse-box-header">Charges</a>
      <ul><li><b>example.pdf</b><small>créé le 2026-09-01</small>
      <a href="downdocged.php?Urlhash=TOKEN">PDF</a></li></ul></div>"""


def test_document_id_survives_rotating_urlhash(document_html):
    assert (
        parsing.documents(parsing.soup(document_html.replace("TOKEN", "aaa")))[0]["id"]
        == (parsing.documents(parsing.soup(document_html.replace("TOKEN", "bbb")))[0]["id"])
    )


def test_document_category(document_html):
    assert parsing.documents(parsing.soup(document_html))[0]["category"] == "Charges"


def test_document_date(document_html):
    assert parsing.documents(parsing.soup(document_html))[0]["created"] == "2026-09-01"


@pytest.mark.parametrize("route", ["docpdf.php", "lettre.php"])
def test_useful_document_titles(route):
    page = parsing.soup(
        f'<li><div class="col">Example guide</div><a href="{route}?Urlhash=example">PDF</a></li>'
    )
    assert parsing.documents(page)[0]["name"] == "Example guide"


def test_content_excludes_scripts():
    assert (
        parsing.content(
            parsing.soup(
                '<div class="content-inner"><h1>Agenda</h1>'
                "<script>secret()</script><p>Event</p></div>"
            )
        )["text"]
        == "Agenda\nEvent"
    )
