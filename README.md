# myoralia-cli

**Visibility: public.**

Read your [MyOralia](https://myoralia.fr/) copropriétaire account from the terminal,
using your signed-in Chrome session. Supports account discovery, building and
agency information, tantièmes, agenda, general meetings, news, statements,
recursive document listing, and PDF downloads.

## Install

Requires Python 3.11+, `uv`, and Chrome for the initial login.

```console
uv run claudine/scripts/link_clis.py   # links bin/myoralia into ~/.local/bin
myoralia --help
```

`bin/myoralia` is a PEP 723 shim that runs the current checkout's `src/` with the
dependencies pinned exactly as in `pyproject.toml`. Contributors can use
`uv sync` and `uv run myoralia`.

## Authentication

Sign in at `https://myoralia.fr/` in Chrome, then:

```console
myoralia connect --json
myoralia whoami --json
myoralia doctor --json
```

`connect` (or `login --browser chrome`) imports only MyOralia cookies, validates them against the live account,
then atomically saves them with mode `0600` beneath
`$XDG_CONFIG_HOME/myoralia-cli` (default `~/.config/myoralia-cli`). A failed login
preserves the previous session. Browser cookie decryption may require access to
the operating system credential store. Passwords are entered only on the website.

For another Chrome profile, `login --cookie-file` accepts its Cookies database.
For an existing local Chrome DevTools connection, use `login --cdp-url`.
For a Chrome cookie JSON export, use `login --cookie-stdin`; it accepts a cookie
array or an object with a `cookies` array. See `myoralia login --help`.

The CLI uses the validated snapshot until it expires. Repeat `connect` to import
the current Chrome session. Online page reads check authenticated content and
the account identity; HTTP 200 alone is not treated as authentication.
Cached document reads use the local session identity without contacting the site.
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
myoralia documents sync --json
myoralia documents list --offline --json
myoralia documents status --json
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

Documents include personal files, recursively loaded building folders, AG viewer
attachments, agenda attachments, useful guides, and the maintenance PDF. The
scanner also checks the other read-only navigation sections and follows activity
archives and intervention details. It reports failed or unknown sections instead
of calling an incomplete scan complete. Account-action pages are explicitly
excluded in the coverage report.

Copy an ID from `documents list` into `documents download`. The command returns
an absolute local `path` that agents can open directly. It verifies and reuses
the persistent cached PDF, fetching and caching it on a miss. No separate sync
or destination is required. Optionally pass `--target-dir DIRECTORY` for a copy
with a readable filename, or `-o FILE` for an exact filename. IDs from every
indexed section work without additional flags;
`--useful` remains accepted for compatibility.
Downloads must have a PDF signature, use owner-only permissions, and never
overwrite a different existing file. Identical copies are safe to retry.

```console
myoralia documents download DOCUMENT_ID --json
myoralia documents download DOCUMENT_ID --target-dir ./documents --json
myoralia documents download DOCUMENT_ID -o ./document.pdf --offline --json
```

## Document cache and bulk download

`documents list` reuses its complete inventory for one hour. `--refresh` forces
a new scan, `--max-age SECONDS` controls freshness, and `--offline` makes no
network requests. A partial scan is recorded but is never treated as a complete
cached list. These cache options apply to documents; other read commands remain
live reads.

`documents sync` always refreshes the inventory, then downloads missing or corrupt
PDFs. Successful downloads are checkpointed individually; rerunning after an
interruption resumes them. Identical PDF contents share one SHA-256-addressed
file, while every website reference and source section remains in the catalog.
Sync returns a nonzero exit code if any section or download fails. If a download
response indicates session expiry, it validates authentication and stops with
completed PDFs checkpointed. Sign in again, run `connect`, and rerun `sync`.

With `$MYORALIA_DOWNLOAD_DIR` set (`~` and `$VARS` expand), `documents download`
without a destination copies the PDF there instead of returning the cache path,
and `documents sync` exports there as if given `--output`.

## Claude Desktop extension

`mcpb.json` customizes the extension `mcp-bridge pack myoralia-cli` builds, so
someone without a terminal can install it by double-click. The user signs in at
myoralia.fr in Chrome and asks Claude to connect, which calls `connect`; macOS
asks once for the "Chrome Safe Storage" keychain item. The extension sets
`MYORALIA_DOWNLOAD_DIR` to its Download folder setting (default
`~/Downloads/MyOralia`).

```console
myoralia documents sync --output ./oralia-documents --json
myoralia documents status --json
myoralia documents list --offline --json
```

`--output` additionally exports readable filenames grouped by website section.
Repeated exports accept identical files and refuse to overwrite different files.
Without `--output`, downloaded PDFs remain available in the cache. Single-file
`documents download` reuses an integrity-checked cached PDF; add `--offline` to
require a local copy.

The cache lives under `$XDG_CACHE_HOME/myoralia-cli` (default
`~/.cache/myoralia-cli`), isolated by login identity and account. Override its root
with `MYORALIA_CACHE_DIR`. `documents status` reports the exact location,
scan coverage, document/download counts, unique PDFs, and failures.
Each account has an SQLite index, a `pdfs` directory, and a `manifest.json` written
after sync that maps document names to cached files. Credentials and signed links
are not stored in the index or manifest. Cache files use owner-only permissions.

Existing PDFs are retained when their references disappear from the site.
Unchanged document IDs are reused on subsequent syncs; use `--refresh-files` to
detect replacements whose filenames and metadata did not change, including
updated generated reports. Logout removes credentials but retains the downloaded
archive. Offline CLI access requires a local login identity.

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
