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
- `documents list --search TEXT`: personal files and recursive building folders.
- `documents list --useful`: guides and Oralia publications.
- `documents download DOCUMENT_ID -o OUTPUT.pdf`: verified PDF, no overwrite.

Use `--json` for parsing. Progress is on stderr. Resolve document IDs from a
fresh list; do not invent or reuse signed `Urlhash` URLs. Use `--useful` on the
download as well when the ID came from that section.

Statement amounts are decimal strings in EUR. Future-dated charges can appear.
`balance_label` is the website's total even when transaction date filters are
used. Undated year-end balance rows are separate from transactions.

The CLI supports coproprietaire accounts and read operations only. It does not
send messages, submit payments, upload documents, or vote. `logout` removes only
the local CLI session and does not log Chrome out. See [README.md](README.md) for
installation, session storage, and development checks.
