"""Coordinate fresh discovery, offline reads, and checkpointed bulk PDF downloads."""

import json
import logging
import re
from contextlib import contextmanager

import click

from . import auth, inventory
from .cache import Catalog, atomic_write, cached_accounts
from .client import Client

log = logging.getLogger(__name__)


@contextmanager
def catalog(account=None, offline=False, refresh=False):
    identity = auth.load_session()["identity"]
    choices = cached_accounts(identity)
    if not offline and (refresh or not choices or (account and account not in choices)):
        with Client() as client:
            choices = [row["id"] for row in client.accounts()]
    matches = [choice for choice in choices if choice == account] if account else choices
    if len(matches) != 1:
        raise click.ClickException(
            "No unambiguous cached account. Select --account or run documents sync online."
        )
    with Catalog(identity, matches[0]) as cache:
        yield cache


def discover(cache, client):
    rows, coverage = inventory.scan(client, cache.state("account"))
    cache.save_inventory(rows, coverage)
    return rows


def listing(cache, offline=False, refresh=False, max_age=3600):
    if offline:
        if not cache.state("coverage", {}).get("complete"):
            raise click.ClickException("No complete cached inventory. Run: myoralia documents sync")
        log.info("Using offline document index (fetched at %s).", cache.state("fetched_at"))
    elif refresh or not cache.fresh(max_age):
        with Client() as client:
            discover(cache, client)
        if not cache.state("coverage")["complete"]:
            raise click.ClickException(
                "Document scan incomplete. See: myoralia documents status --json"
            )
    else:
        log.info("Using cached document index (fetched at %s).", cache.state("fetched_at"))
    return cache.documents()


def fetch(cache, doc_id, offline=False):
    cached = cache.blob(doc_id)
    if cached:
        return cached
    if offline:
        raise click.ClickException("PDF is not cached or failed integrity verification. Run sync.")
    with Client() as client:
        rows = discover(cache, client)
        matches = [row for row in rows if row["id"] == doc_id]
        if len(matches) != 1:
            raise click.ClickException("Document ID not found. Run documents list --refresh.")
        return cache.store(doc_id, client.pdf(matches[0]["_url"]))


def sync(cache, refresh_files=False):
    downloaded, reused, failed = 0, 0, []
    session_expired = False
    with Client() as client:
        rows = discover(cache, client)
        for index, row in enumerate(rows, 1):
            if not refresh_files and not cache.error(row["id"]) and cache.blob(row["id"]):
                reused += 1
                continue
            log.info("Downloading %s/%s: %s", index, len(rows), row["name"])
            try:
                cache.store(row["id"], client.pdf(row["_url"]))
                downloaded += 1
            except auth.SessionExpired as exc:
                cache.failure(row["id"], exc.format_message())
                failed.append({"id": row["id"], "error": exc.format_message()})
                session_expired = True
                log.warning("Session expired; stopping with downloaded PDFs checkpointed.")
                break
            except click.ClickException as exc:
                cache.failure(row["id"], exc.format_message())
                failed.append({"id": row["id"], "error": exc.format_message()})
                log.warning("Download failed: %s (%s)", row["name"], exc.format_message())
    result = cache.status()
    result.update(
        {
            "new_downloads": downloaded,
            "reused": reused,
            "errors": failed,
            "session_expired": session_expired,
        }
    )
    result["complete"] = (
        result["coverage"].get("complete", False)
        and not failed
        and not result["failures"]
        and result["downloaded"] == result["documents"]
    )
    write_manifest(cache)
    return result


def write_manifest(cache):
    rows = []
    for row in cache.documents():
        path = cache.blob(row["id"])
        rows.append({**row, "file": str(path.relative_to(cache.path)) if path else None})
    atomic_write(
        cache.path / "manifest.json",
        json.dumps(
            {"status": cache.status(), "documents": rows}, ensure_ascii=False, indent=2
        ).encode(),
    )


def filename(row):
    """Keep exported names readable, bounded, and distinct across document IDs."""
    name = re.sub(r"[^\w .()-]", "_", row["name"]).strip(" .")[:140] or "document"
    if not name.lower().endswith(".pdf"):
        name += ".pdf"
    return f"{row['id']}-{name}"


def export(cache, destination):
    """Export readable filenames without overwriting unrelated local files."""
    count = 0
    for row in cache.documents():
        source = cache.blob(row["id"])
        if source is None:
            continue
        section = re.sub(r"[^\w-]", "_", row["source"])
        target = destination / section / filename(row)
        body = source.read_bytes()
        if target.exists():
            if target.read_bytes() != body:
                raise click.ClickException(f"Export destination differs: {target}")
        else:
            atomic_write(target, body, overwrite=False)
        count += 1
    return count
