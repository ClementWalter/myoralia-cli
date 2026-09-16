"""Document commands expose cached listings, offline downloads, and resumable sync."""

from pathlib import Path

import click

from . import documents as service
from .cache import atomic_write
from .output import account_option, emit, json_option


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
def documents():
    """Cache and download documents across the account's read-only sections.

    Example: myoralia documents sync --json
    """


@documents.command("list")
@account_option
@click.option("--search", help="Case-insensitive filename/category filter.")
@click.option("--useful", is_flag=True, help="Only Documents utiles.")
@click.option("--refresh", is_flag=True, help="Fetch a fresh inventory across all sections.")
@click.option("--offline", is_flag=True, help="Use the cached inventory without network requests.")
@click.option(
    "--max-age",
    default=3600,
    type=click.IntRange(min=0),
    show_default=True,
    help="Maximum cached inventory age in seconds.",
)
@json_option
def documents_list(account, search, useful, refresh, offline, max_age, as_json):
    """List all discovered attachments; cached for one hour by default.

    Example: myoralia documents list --offline --json
    """
    if offline and refresh:
        raise click.UsageError("--offline and --refresh are mutually exclusive.")
    with service.catalog(account, offline, refresh) as cache:
        rows = service.listing(cache, offline, refresh, max_age)
        if useful:
            rows = [row for row in rows if row["source"] == "useful-documents"]
        if search:
            rows = [
                row
                for row in rows
                if search.casefold() in (row["name"] + " " + row["category"]).casefold()
            ]
        emit(rows, as_json)


@documents.command("download")
@click.argument("document_id")
@click.option(
    "-o",
    "--output",
    type=click.Path(path_type=Path, dir_okay=False),
    help="Optionally copy to an exact filename.",
)
@click.option(
    "--target-dir",
    type=click.Path(path_type=Path, file_okay=False),
    help="Optionally copy into this directory with a readable document filename.",
)
@click.option(
    "--useful", is_flag=True, help="Accepted for compatibility; all sections are indexed."
)
@click.option(
    "--offline", is_flag=True, help="Copy a verified cached PDF without network requests."
)
@account_option
@json_option
def download(document_id, output, target_dir, useful, offline, account, as_json):
    """Return a local PDF path, fetching into the persistent cache only when needed.

    Without a destination, use the cached file directly. Identical copies are safe to retry.

    \b
    Examples:
      myoralia documents download DOCUMENT_ID --json
      myoralia documents download DOCUMENT_ID --target-dir ./documents --json
      myoralia documents download DOCUMENT_ID -o document.pdf --offline
    """
    if output and target_dir:
        raise click.UsageError("Choose either --output or --target-dir.")
    with service.catalog(account, offline) as cache:
        source = service.fetch(cache, document_id, offline)
        if target_dir:
            row = next(row for row in cache.documents() if row["id"] == document_id)
            output = target_dir / service.filename(row)
        body = source.read_bytes()
        if output:
            if output.exists():
                if output.read_bytes() != body:
                    raise click.ClickException(
                        f"Destination differs; choose another path: {output}"
                    )
            else:
                atomic_write(output, body, overwrite=False)
        path = (output or source).resolve()
    emit({"id": document_id, "path": str(path), "bytes": len(body)}, as_json)


@documents.command("sync")
@account_option
@click.option(
    "--refresh-files", is_flag=True, help="Re-download PDFs to detect same-metadata replacements."
)
@click.option(
    "-o",
    "--output",
    type=click.Path(path_type=Path, file_okay=False),
    help="Also export PDFs to this directory, grouped by website section.",
)
@json_option
def sync(account, refresh_files, output, as_json):
    """Refresh the inventory and download missing PDFs; reruns resume verified progress.

    Example: myoralia documents sync --output ./oralia-documents --json
    """
    with service.catalog(account, refresh=True) as cache:
        result = service.sync(cache, refresh_files)
        if output:
            result["exported"] = service.export(cache, output)
            result["output"] = str(output.resolve())
    emit(result, as_json)
    if not result["complete"]:
        if result.get("session_expired"):
            raise click.ClickException(
                "Session expired; downloaded PDFs are saved. Sign in at https://myoralia.fr/ "
                "in Chrome, run `myoralia login --browser chrome`, then rerun this sync to resume."
            )
        raise click.ClickException("Sync incomplete; see errors above. Rerun to resume.")


@documents.command("status")
@account_option
@json_option
def status(account, as_json):
    """Inspect cache location, scan coverage, failures, and PDF integrity without network access.

    Example: myoralia documents status --json
    """
    with service.catalog(account, offline=True) as cache:
        emit(cache.status(), as_json)
