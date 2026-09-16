"""Parse observed MyOralia HTML without exposing signed links as resource identities."""

import hashlib
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import urljoin, urlparse

import click
from bs4 import BeautifulSoup

from .auth import ORIGIN, SessionExpired

BASE = ORIGIN + "/extranet/"


def soup(html):
    return BeautifulSoup(html, "html.parser")


def text(element):
    return " ".join(element.get_text(" ", strip=True).split()) if element else ""


def safe_url(url, base=BASE):
    resolved = urljoin(base, url)
    parsed = urlparse(resolved)
    if (parsed.scheme, parsed.hostname, parsed.port) != ("https", "myoralia.fr", None):
        raise click.ClickException("Rejected a link outside https://myoralia.fr.")
    if parsed.username or parsed.password:
        raise click.ClickException("Rejected a credential-bearing link.")
    return resolved


def identity(page):
    if page.select_one('input[type="password"]'):
        raise SessionExpired("MyOralia session expired. Sign in to Chrome, then myoralia login.")
    # Help modals reuse the header ID, so welcome text identifies the account header.
    headers = " ".join(text(header) for header in page.select("#page-header"))
    match = re.search(r"Bienvenue\s+(.+?)(?=\s+Compte|\s+Mon profil|$)", headers)
    if not match or not page.select_one('a[href*="logout=1"]'):
        raise click.ClickException("MyOralia did not return a recognized authenticated page.")
    return match[1].strip()


def accounts(page):
    result = []
    for link in page.select("a.account-item[onclick]"):
        query = re.fullmatch(
            r"ajaxload\('(?P<query>Urlhash=[a-zA-Z0-9]+)'\);?", link.get("onclick", "")
        )
        match = re.search(r"Réf\s*n°\s*:\s*(\d+)\s*/\s*(\d+)", text(link))
        if not query or not match:
            raise click.ClickException("Unrecognized account selector; the website layout changed.")
        result.append(
            {
                "id": f"{match[1]}/{match[2]}",
                "name": text(link.select_one("h3")),
                "type": text(link.select_one(".sr-only")),
                "agency": text(link.select_one("small i")),
                "_query": query["query"],
            }
        )
    return result


def content(page):
    element = page.select_one(".content-inner")
    if element is None:
        raise click.ClickException("Expected account content is missing; website layout changed.")
    # Scripts and hidden forms are not user-facing account information.
    element = soup(str(element))
    for node in element.select("script, style, form, .modal, input, button"):
        node.decompose()
    return {"title": text(element.select_one("h1")), "text": element.get_text("\n", strip=True)}


def amount(value):
    normalized = re.sub(r"[\s€\x80]", "", value).replace(",", ".")
    try:
        return format(Decimal(normalized), ".2f") if normalized else None
    except InvalidOperation as exc:
        raise click.ClickException("Unrecognized amount in account statement.") from exc


def statement(page):
    table = page.select_one(".content-inner table")
    if table is None:
        raise click.ClickException("Account statement table is missing.")
    rows = []
    balance_rows = []
    for tr in table.select("tbody tr"):
        cells = [td for td in tr.select("td") if "hidden-md-up" not in td.get("class", [])]
        if not cells:
            continue
        if len(cells) != 5:
            raise click.ClickException("Unrecognized account statement row.")
        if not text(cells[0]) and text(cells[1]).startswith("Solde"):
            balance_rows.append({"label": text(cells[1]), "balance": amount(text(cells[4]))})
            continue
        try:
            date = datetime.strptime(text(cells[0]), "%d/%m/%Y").date().isoformat()
        except ValueError as exc:
            raise click.ClickException("Unrecognized statement date.") from exc
        rows.append(
            {
                "date": date,
                "label": text(cells[1]),
                "debit": amount(text(cells[2])),
                "credit": amount(text(cells[3])),
                "balance": amount(text(cells[4])),
            }
        )
    balance = table.select_one("th[colspan]")
    return {
        "currency": "EUR",
        "balance_label": text(balance),
        "balance_rows": balance_rows,
        "transactions": rows,
    }


def folders(page):
    result = []
    for link in page.select('[onclick*="MAJDOSSIER"]'):
        match = re.fullmatch(
            r"MAJDOSSIER\('(Urlhash=[a-zA-Z0-9]+)','([\w-]+)'\);?", link["onclick"].strip()
        )
        if not match:
            raise click.ClickException("Unrecognized document folder selector.")
        result.append({"id": match[2], "name": text(link), "_query": match[1]})
    return result


def documents(page, parent=""):
    result = []
    for link in page.select(
        'a[href*="downdocged.php"], a[href*="docpdf.php"], a[href*="lettre.php"]'
    ):
        item = link.find_parent("li")
        if item is None:
            raise click.ClickException("Unrecognized document row.")
        filename = text(
            item.select_one("b") if "downdocged.php" in link["href"] else item.select_one(".col")
        )
        if not filename:
            raise click.ClickException("Document title is missing.")
        metadata = [text(node) for node in item.select("small") if text(node)]
        categories = []
        for box in item.find_parents(class_="collapse-box"):
            heading = box.select_one(":scope > a.collapse-box-header")
            if heading:
                categories.append(text(heading))
        category = " / ".join(filter(None, [parent, *reversed(categories)]))
        date = re.search(r"créé le (\d{4}-\d{2}-\d{2})", " ".join(metadata))
        stable = "\n".join([category, filename, *metadata])
        doc_id = hashlib.sha256(stable.encode()).hexdigest()[:16]
        result.append(
            {
                "id": doc_id,
                "name": filename,
                "category": category,
                "created": date[1] if date else None,
                "metadata": metadata,
                "_url": safe_url(link["href"]),
            }
        )
    return result
