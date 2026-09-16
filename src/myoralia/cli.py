"""Noninteractive commands with JSON stdout and actionable stderr failures."""

import json
import logging
import sys

import click

from . import auth, parsing
from .client import SECTIONS, Client
from .documents_cli import documents
from .output import account_option, emit, json_option

log = logging.getLogger("myoralia")
CONTEXT = {"help_option_names": ["-h", "--help"]}


@click.group(context_settings=CONTEXT, invoke_without_command=True)
@click.version_option(package_name="myoralia-cli")
@click.pass_context
def cli(ctx):
    """Read your MyOralia account using a Chrome session.

    \b
    Examples:
      myoralia login --browser chrome
      myoralia accounts list --json
      myoralia documents list --json
    """
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@cli.command()
@click.option("--browser", type=click.Choice(["chrome"]), default="chrome", show_default=True)
@click.option(
    "--cookie-file",
    type=click.Path(exists=True, dir_okay=False),
    help="Chrome Cookies database for another profile.",
)
@click.option("--cookie-stdin", is_flag=True, help="Read a Chrome cookie JSON export from stdin.")
@click.option(
    "--cdp-url", envvar="MYORALIA_CDP_URL", help="Existing local Chrome DevTools endpoint."
)
@json_option
def login(browser, cookie_file, cookie_stdin, cdp_url, as_json):
    """Validate Chrome authentication before saving it locally.

    \b
    Examples:
      myoralia login --browser chrome
      myoralia login --cookie-stdin < cookies.json
      myoralia login --cdp-url http://localhost:9222 --json
    """
    if sum(bool(value) for value in (cookie_file, cookie_stdin, cdp_url)) > 1:
        raise click.UsageError("Choose only one of --cookie-file, --cookie-stdin, --cdp-url.")
    if cookie_stdin:
        if sys.stdin.isatty():
            raise click.UsageError("Pipe cookie JSON: myoralia login --cookie-stdin < cookies.json")
        try:
            cookies = auth.normalize_cookies(json.load(sys.stdin))
        except ValueError as exc:
            raise click.ClickException("Invalid cookie JSON on stdin.") from exc
    elif cdp_url:
        cookies = auth.cdp_cookies(cdp_url)
    else:
        log.info("Reading MyOralia cookies from Chrome…")
        cookies = auth.chrome_cookies(cookie_file)
    with Client(cookies) as client:
        identity = client.whoami()
    auth.save_session(cookies, identity["name"])
    emit({"authenticated": True, **identity}, as_json)


@cli.command()
@json_option
def logout(as_json):
    """Remove local CLI credentials; the Chrome website stays signed in.

    Example: myoralia logout --json
    """
    auth.config_path().unlink(missing_ok=True)
    emit({"authenticated": False, "scope": "local-cli"}, as_json)


@cli.command()
@json_option
def whoami(as_json):
    """Verify the current session against MyOralia.

    Example: myoralia whoami --json
    """
    with Client() as client:
        emit(client.whoami(), as_json)


@cli.command()
@json_option
def doctor(as_json):
    """Check local credential permissions and live authentication.

    Example: myoralia doctor --json
    """
    with Client() as client:
        data = client.whoami()
    mode = auth.config_path().stat().st_mode & 0o777
    if mode & 0o077:
        raise click.ClickException("Session file is readable by other users; rerun myoralia login.")
    emit(
        {"ok": True, "session_permissions": oct(mode), "account_count": len(data["accounts"])},
        as_json,
    )


@cli.group()
def accounts():
    """Discover stable account IDs.

    Example: myoralia accounts list --json
    """


@accounts.command("list")
@json_option
def accounts_list(as_json):
    """List properties available to the signed-in user.

    Example: myoralia accounts list --json
    """
    with Client() as client:
        emit(client.accounts(), as_json)


@cli.command("statement")
@account_option
@click.option("--from", "date_from", type=click.DateTime(formats=["%Y-%m-%d"]))
@click.option("--to", "date_to", type=click.DateTime(formats=["%Y-%m-%d"]))
@json_option
def statement(account, date_from, date_to, as_json):
    """Read transactions and the website's balance, including future-dated entries.

    Date filters restrict transactions only; balance_label remains the website total.

    Example: myoralia statement --from 2026-01-01 --json
    """
    if date_from and date_to and date_from > date_to:
        raise click.UsageError("--from must be on or before --to.")
    with Client() as client:
        data = parsing.statement(client.section("statement", account))
    data["transactions"] = [
        row
        for row in data["transactions"]
        if (not date_from or row["date"] >= date_from.date().isoformat())
        and (not date_to or row["date"] <= date_to.date().isoformat())
    ]
    emit(data, as_json)


cli.add_command(documents)


def section_command(name):
    @cli.command(name)
    @account_option
    @json_option
    def read_section(account, as_json):
        with Client() as client:
            emit(parsing.content(client.section(name, account)), as_json)

    read_section.help = f"Read the {name} section.\n\nExample: myoralia {name} --json"


for section in SECTIONS.keys() - {"documents", "useful-documents", "statement"}:
    section_command(section)


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr)
    try:
        cli()
    except OSError as exc:
        log.error("Local file operation failed: %s", exc.strerror)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
