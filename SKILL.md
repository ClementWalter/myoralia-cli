---
name: myoralia-cli
description: Read the user's MyOralia coproprietaire account with the myoralia CLI, including building information, agency contacts, tantiemes, agenda, general meetings, statements, and PDF documents. Reuses a signed-in Chrome session.
---

# MyOralia CLI

Read-only access to a MyOralia (Oralia syndic) coproprietaire account.

## How to invoke

Invoke it as **`myoralia`**, on `$PATH` via `uv run claudine/scripts/link_clis.py`
(it links this repo's `bin/myoralia` into `~/.local/bin`, so the current checkout
always runs). If `myoralia` is missing from `$PATH`, run `<skill-dir>/bin/myoralia`
directly: a PEP 723 shim that resolves its pinned deps with `uv` and imports the
package from the checkout's `src/`.

## Authentication

Start with `myoralia whoami --json`. If the session is missing or expired, sign
in on `https://myoralia.fr/` in Chrome and run `myoralia login --browser chrome`.
The CLI also accepts a Chrome cookie export through `login --cookie-stdin` and
an existing local DevTools connection through `login --cdp-url`.
Never put cookie values in command arguments, documentation, or responses.
`logout` removes only the local CLI session and does not log Chrome out.

## Output conventions

- `--json` on every command, with data only on stdout; progress and errors go to
  stderr. Use it for parsing.
- Default text: section commands print their title and text; lists print one
  row per record with the id first.
- Statement amounts are decimal strings in EUR; dates are ISO.
- Signed `Urlhash` URLs never appear in output; stable document IDs do.

## Commands

```bash
# Read
myoralia whoami --json                      # identity and accounts of the session
myoralia doctor --json                      # session file permissions + live auth
myoralia accounts list --json               # exact account IDs for --account
myoralia building --json                    # also: agency, shares, agenda, meetings, news
myoralia statement --from 2026-01-01 --to 2026-06-30 --json
myoralia documents list --search TEXT --json   # cached inventory across sections
myoralia documents list --useful            # guides and Oralia publications
myoralia documents download DOCUMENT_ID --json # absolute cached PDF `path`
myoralia documents download DOCUMENT_ID --target-dir DIRECTORY
myoralia documents download DOCUMENT_ID -o OUTPUT.pdf --offline
myoralia documents sync --output DIRECTORY --json
myoralia documents status --json            # cache location, coverage, failures

# Local session only (no website writes exist)
myoralia login --browser chrome
myoralia logout --json
```

Supply `--account` when more than one account is present.

## Recipes

```bash
# Open a document the user asks about: find it, then read the returned path
myoralia documents list --search "assemblée" --json
myoralia documents download DOCUMENT_ID --json     # -> {"path": "/…/x.pdf"}

# What did I pay this year, and what is the balance?
myoralia statement --from 2026-01-01 --json

# Archive every document with readable names
myoralia documents sync --output ./oralia-documents --json
```

## Gotchas

- Resolve document IDs from a list; do not invent or reuse signed `Urlhash`
  URLs. Download IDs resolve across all sections.
- Listings cache for one hour; use `--refresh` to rescan or `--offline` to
  forbid network access. A cached PDF can also be downloaded with `--offline`.
- Sync covers recursive library folders, AG PDF viewers, agenda, useful
  documents, the maintenance PDF, and read-only activity archive/detail pages.
  Read the coverage and failures in the result before reporting completeness.
  Sync resumes verified PDFs, deduplicates identical bytes, and exits nonzero
  for partial results. Use `--refresh-files` to check for replacements with
  unchanged names/metadata.
- The local cache is account-isolated under `~/.cache/myoralia-cli` by default;
  `documents status` gives the exact path and the manifest maps IDs to local PDFs.
- Future-dated charges can appear in a statement. `balance_label` is the
  website's total even when transaction date filters are used. Undated year-end
  balance rows are separate from transactions.
- Coproprietaire accounts and read operations only: the CLI does not send
  messages, submit payments, upload documents, or vote.

See [README.md](README.md) for installation, session storage, and development
checks.
