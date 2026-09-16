"""Shared Click options and predictable stdout rendering keep commands composable."""

import json

import click

from .client import public


def emit(value, as_json):
    value = public(value)
    if as_json:
        click.echo(json.dumps(value, ensure_ascii=False, indent=2))
    elif isinstance(value, dict) and "text" in value:
        click.echo(value["text"])
    elif isinstance(value, list):
        for row in value:
            if "category" in row and "name" in row:
                click.echo(
                    f"{row['id']}  {row.get('created') or '-'}  {row['category']}  {row['name']}"
                )
            else:
                click.echo("  ".join(str(v) for v in row.values() if v is not None))
    else:
        click.echo(json.dumps(value, ensure_ascii=False, indent=2))


def json_option(fn):
    return click.option("--json", "as_json", is_flag=True, help="Emit JSON only on stdout.")(fn)


def account_option(fn):
    return click.option(
        "--account", help="Exact ID from accounts list; required if multiple accounts."
    )(fn)
