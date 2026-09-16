"""Discover documents in known read-only sections, including JavaScript PDF viewers."""

import hashlib
import logging
import re
from collections import Counter
from urllib.parse import urlparse

import click

from . import parsing
from .client import SECTIONS

log = logging.getLogger(__name__)
READ_SECTIONS = {
    **SECTIONS,
    "activity": "vie_coproprietaire.php",
    "forum": "forum_coproprietaire.php",
    "directory": "annuairecopro.php",
    "neighbors": "monvoisinage_coproprietaire.php",
    "renovation": "renovation_energ_coproprietaire.php",
}
DOWNLOAD_ROUTES = {"downdoc.php", "downdocged.php", "docpdf.php", "lettre.php"}
ACTIVITY_CHILDREN = {
    "activity": {
        "viearchives_coproprietaire.php": "activity-archives",
        "vieinterventions_coproprietaire.php": "activity-details",
    },
    "activity-archives": {"vieinterventions_coproprietaire.php": "activity-details"},
}
ACTION_ROUTES = {
    "prendreRDV_coproprietaire.php",
    "poserquestion_coproprietaire.php",
    "joindredoc_coproprietaire.php",
    "signaler_coproprietaire.php",
    "paiementenlignecomm_coproprietaire.php",
    "convocelec_coproprietaire.php",
    "vendregerer_coproprietaire.php",
    "idee_coproprietaire.php",
    "soutien1.php",
}


def record(name, category, url, context=""):
    key = "\n".join([category, name, context])
    return {
        "id": hashlib.sha256(key.encode()).hexdigest()[:16],
        "name": name,
        "category": category,
        "created": None,
        "metadata": [],
        "_url": parsing.safe_url(url),
    }


def attachments(page, section):
    """Parse links and the site's load('Urlhash=…') viewer without executing JavaScript."""
    root = page.select_one(".content-inner") or page
    result = []
    occurrences = Counter()
    for link in root.select("a[href], [onclick]"):
        href = link.get("href", "")
        onclick = link.get("onclick", "").strip()
        if onclick.startswith("load("):
            match = re.fullmatch(r"load\('(Urlhash=[a-zA-Z0-9]+)'\);?", onclick)
            if not match:
                raise click.ClickException("Unrecognized PDF viewer; refusing to omit it.")
            href = "downdoc.php?" + match[1]
        elif urlparse(href).path.rsplit("/", 1)[-1] not in DOWNLOAD_ROUTES:
            if not urlparse(href).path.lower().endswith(".pdf"):
                continue
        context = []
        for box in link.find_parents(class_="collapse-box"):
            heading = box.select_one(":scope > .collapse-box-header")
            if heading and heading is not link:
                context.append(parsing.text(heading))
        category = " / ".join([section, *reversed(context)])
        name = parsing.text(link) or "Document.pdf"
        # Agenda buttons share labels; their enclosing event distinguishes documents.
        event = parsing.text(link.parent) if section == "agenda" else ""
        row = record(name, category, href, event)
        occurrences[row["id"]] += 1
        if occurrences[row["id"]] > 1:
            row["id"] += f"-{occurrences[row['id']]}"
        row["source"] = section
        result.append(row)
    return result


def scan(client, account):
    """Return a coverage report even when a section fails, so sync can resume safely."""
    dashboard = client.dashboard(account)
    links = {}
    for link in dashboard.select("a[href]"):
        path = urlparse(link["href"]).path
        if path in {*READ_SECTIONS.values(), "carnet.php"}:
            links[path] = parsing.safe_url(link["href"])
    result, scanned, unavailable, errors = [], [], [], []
    pending = []
    for name, route in READ_SECTIONS.items():
        if route not in links:
            unavailable.append(name)
            continue
        log.info("Scanning %s…", name)
        try:
            page = dashboard if name == "building" else client.page(links[route])
            if name in {"documents", "useful-documents"}:
                rows = client.document_tree(page)
                for row in rows:
                    row["source"] = name
            else:
                rows = attachments(page, name)
            result.extend(rows)
            scanned.append({"section": name, "documents": len(rows)})
            pending.extend(child_pages(page, name))
        except click.ClickException as exc:
            errors.append({"section": name, "error": exc.format_message()})
    visited = set()
    while pending:
        name, url = pending.pop(0)
        if url in visited:
            continue
        if len(visited) >= 200:
            errors.append({"section": name, "error": "Child-page limit reached."})
            break
        visited.add(url)
        log.info("Scanning %s…", name)
        try:
            page = client.page(url)
            rows = attachments(page, name)
            result.extend(rows)
            scanned.append({"section": name, "documents": len(rows)})
            pending.extend(child_pages(page, name))
        except click.ClickException as exc:
            errors.append({"section": name, "error": exc.format_message()})
    if "carnet.php" in links:
        row = record("Carnet d'entretien.pdf", "maintenance", links["carnet.php"])
        result.append({**row, "source": "maintenance"})
        scanned.append({"section": "maintenance", "documents": 1})
    routes = {
        urlparse(link["href"]).path
        for link in dashboard.select("#nav-primary a[href]")
        if urlparse(link["href"]).path.endswith(".php")
    }
    unknown = routes - set(READ_SECTIONS.values()) - ACTION_ROUTES - {"carnet.php"}
    errors.extend(
        {"section": route, "error": "Unrecognized navigation section; not scanned."}
        for route in sorted(unknown)
    )
    return result, {
        "complete": not errors,
        "scanned": scanned,
        "unavailable": unavailable,
        "errors": errors,
        "excluded_actions": sorted(routes & ACTION_ROUTES),
    }


def child_pages(page, section):
    children = ACTIVITY_CHILDREN.get(section, {})
    return [
        (children[urlparse(link["href"]).path], parsing.safe_url(link["href"]))
        for link in page.select(".content-inner a[href]")
        if urlparse(link["href"]).path in children
    ]
