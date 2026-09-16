# myoralia-cli

Read your [MyOralia](https://myoralia.fr/) copropriétaire account from the terminal,
using your signed-in Chrome session. Supports account discovery, building and
agency information, tantièmes, agenda, general meetings, news, statements,
recursive document listing, and PDF downloads.

## Install

Requires Python 3.11+, `uv`, and Chrome for the initial login.

```console
uv tool install --editable .
myoralia --help
```

The editable installation runs the current checkout. Dependencies are pinned in
`uv.lock`; contributors can use `uv sync` and `uv run myoralia`.

## Authentication

Sign in at `https://myoralia.fr/` in Chrome, then:

```console
myoralia login --browser chrome --json
myoralia whoami --json
myoralia doctor --json
```

`login` imports only MyOralia cookies, validates them against the live account,
then atomically saves them with mode `0600` beneath
`$XDG_CONFIG_HOME/myoralia-cli` (default `~/.config/myoralia-cli`). A failed login
preserves the previous session. Browser cookie decryption may require access to
the operating system credential store. Passwords are entered only on the website.

For another Chrome profile, `login --cookie-file` accepts its Cookies database.
For an existing local Chrome DevTools connection, use `login --cdp-url`.
For a Chrome cookie JSON export, use `login --cookie-stdin`; it accepts a cookie
array or an object with a `cookies` array. See `myoralia login --help`.

The CLI uses the validated snapshot until it expires. Repeat `login` to import
the current Chrome session. Every read checks authenticated page content and
the account identity; HTTP 200 alone is not treated as authentication.
`logout` deletes the local CLI session, is safe to repeat, and leaves Chrome
signed in. Read commands never silently log the CLI back in.

## Read your account

```console
myoralia accounts list --json
myoralia building --json
myoralia agency --json
myoralia shares --json
myoralia agenda --json
myoralia meetings --json
myoralia news --json
myoralia statement --from 2026-01-01 --json
myoralia documents list --json
myoralia documents list --search "Appel" --json
myoralia documents list --useful --json
```

When several accounts exist, select the exact ID returned by `accounts list`
with `--account`. The CLI refuses to select an ambiguous account.

Read commands support `--json` with data exclusively on stdout; progress and
errors go to stderr. IDs and private signed URLs are distinct: account references
and stable document IDs are emitted, while rotating `Urlhash` links are resolved
fresh and kept out of output. Every command provides focused help and examples.

Statements return EUR amounts as decimal strings, ISO dates, and separate
undated balance rows. The website can include future-dated charges. Date filters
restrict transaction rows only; `balance_label` always remains the website's
unfiltered balance. Building and informational sections return a title and text;
account lists, documents, and statements have structured fields.

Documents include personal files and recursively loaded building folders. Copy
an ID from `documents list` into `documents download`, with an explicit `-o`
destination. Add `--useful` for an ID from the useful-documents list.
Downloads must have a PDF signature, use owner-only permissions, and never
overwrite an existing file. Failure to resolve a document writes nothing.

The current commands are read-only. Account selection uses the site's context
selection POST. The CLI does not send questions, report problems, vote, pay,
upload documents, or change account settings. Other account types are not yet
implemented.

## Development and verification

The project is pure Python, using the release CPython distribution; optimized
Python execution is used for checks. Ruff's distributed binaries are release
builds. Tests use synthetic fixtures, one assertion per test, and opt-in live
subprocess checks. Live tests read the account and download a PDF to a temporary
directory; they do not change business data.

```console
uv sync
uv run python -O -m pytest tests/test_parsing.py -q
uv run python -O -m pytest --lf --lfnf=none -q
uv run python -O -m pytest -q
PYTHONOPTIMIZE=1 MYORALIA_LIVE_TESTS=1 uv run python -O -m pytest tests/test_live.py -q
uv run ruff check .
uv run ruff format --check .
prek run --all-files
uv build
```

Pytest rewrites test assertions under `-O`; its warning concerns assertions
outside rewritten test modules. Production code does not use assertions for
validation. Credentials, PDFs, and private HTML are excluded from the repository.

Live validation on 2026-09-16 covered Chrome import, identity, account selection,
all informational commands, the statement, recursive documents, and a real PDF
download. Counts are account state, not parser assumptions.
