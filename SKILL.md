---
name: myoralia-cli
description: Read the user's MyOralia coproprietaire account with the myoralia CLI, including building information, agency contacts, tantiemes, agenda, general meetings, statements, and PDF documents. Reuses a signed-in Chrome session.
---

# MyOralia CLI

Use `myoralia` on PATH. If unavailable, run `uv run myoralia` in this checkout or
install with `uv tool install --editable .`.

Start with `myoralia whoami --json`. If the session is missing or expired, sign
in on `https://myoralia.fr/` in Chrome and run `myoralia login --browser chrome`.
The CLI also accepts a Chrome cookie export through `login --cookie-stdin` and
an existing local DevTools connection through `login --cdp-url`.
Never put cookie values in command arguments, documentation, or responses.

Use `accounts list --json` to discover exact account IDs. Supply `--account`
when more than one account is present. Read commands:

- `building`, `agency`, `shares`, `agenda`, `meetings`, `news`: title and text.
- `statement --from YYYY-MM-DD --to YYYY-MM-DD`: structured transactions.
- `documents list --search TEXT`: cached inventory across read-only website sections.
- `documents list --useful`: guides and Oralia publications.
- `documents download DOCUMENT_ID --json`: returns an absolute cached PDF `path`
  to open directly; automatically fetches and caches missing files.
- `documents download DOCUMENT_ID --target-dir DIRECTORY`: optional readable copy;
  `-o OUTPUT.pdf` selects an exact filename. Identical copies are safe to retry;
  different existing files are never overwritten.
- `documents sync --output DIRECTORY --json`: refresh inventory, resume missing downloads,
  and export readable filenames grouped by section.
- `documents status --json`: cache location, coverage, integrity counts, and failures.

Use `--json` for parsing. Progress is on stderr. Resolve document IDs from a
list; do not invent or reuse signed `Urlhash` URLs. Listings cache for one hour;
use `--refresh` to rescan or `--offline` to forbid network access. A cached PDF can
also be downloaded with `--offline`. Download IDs resolve across all sections.

Sync covers recursive library folders, AG PDF viewers, agenda, useful documents,
the maintenance PDF, and read-only activity archive/detail pages. Read the coverage
and failures in the result before reporting completeness. Sync resumes verified
PDFs and deduplicates identical bytes; it exits nonzero for partial results.
Use `--refresh-files` to check for replacements with unchanged names/metadata.
The local cache is account-isolated under `~/.cache/myoralia-cli` by default;
`documents status` gives the exact path and the manifest maps IDs to local PDFs.

Statement amounts are decimal strings in EUR. Future-dated charges can appear.
`balance_label` is the website's total even when transaction date filters are
used. Undated year-end balance rows are separate from transactions.

The CLI supports coproprietaire accounts and read operations only. It does not
send messages, submit payments, upload documents, or vote. `logout` removes only
the local CLI session and does not log Chrome out. See [README.md](README.md) for
installation, session storage, and development checks.
