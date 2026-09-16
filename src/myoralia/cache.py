"""Account-isolated SQLite catalogs and content-addressed PDFs support resumable sync."""

import hashlib
import json
import os
import sqlite3
import tempfile
import time
from pathlib import Path

import click


def identity_root(identity):
    base = Path(
        os.environ.get(
            "MYORALIA_CACHE_DIR",
            Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "myoralia-cli",
        )
    )
    return base.expanduser().resolve() / hashlib.sha256(identity.encode()).hexdigest()[:24]


def cached_accounts(identity):
    root = identity_root(identity)
    result = []
    for path in root.glob("*/index.sqlite3"):
        with sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True) as db:
            row = db.execute("SELECT value FROM state WHERE key='account'").fetchone()
            if row:
                result.append(json.loads(row[0]))
    return result


def atomic_write(path, data, overwrite=True):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if overwrite:
            os.replace(temporary, path)
        else:
            # Publishing a completed inode prevents partial exports and overwrite races.
            os.link(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


class Catalog:
    def __init__(self, identity, account):
        self.path = identity_root(identity) / hashlib.sha256(account.encode()).hexdigest()[:24]
        self.path.mkdir(mode=0o700, parents=True, exist_ok=True)
        database = self.path / "index.sqlite3"
        database.touch(mode=0o600, exist_ok=True)
        database.chmod(0o600)
        self.db = sqlite3.connect(database, timeout=30)
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY, metadata TEXT NOT NULL, present INTEGER NOT NULL DEFAULT 1,
                sha256 TEXT, error TEXT
            );
        """)
        with self.db:
            self.set_state("account", account)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.db.close()

    def set_state(self, key, value):
        self.db.execute("INSERT OR REPLACE INTO state VALUES (?, ?)", (key, json.dumps(value)))

    def state(self, key, default=None):
        row = self.db.execute("SELECT value FROM state WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def fresh(self, max_age):
        return (
            self.state("coverage", {}).get("complete", False)
            and time.time() - self.state("fetched_at", 0) < max_age
        )

    def save_inventory(self, rows, coverage):
        if len({row["id"] for row in rows}) != len(rows):
            raise click.ClickException("Duplicate document IDs; previous catalog preserved.")
        with self.db:
            self.db.execute("UPDATE documents SET present=0")
            for row in rows:
                # Signed URLs are short-lived credentials and never belong in the catalog.
                metadata = {key: value for key, value in row.items() if not key.startswith("_")}
                self.db.execute(
                    """INSERT INTO documents(id,metadata,present) VALUES (?,?,1)
                    ON CONFLICT(id) DO UPDATE SET metadata=excluded.metadata,present=1""",
                    (row["id"], json.dumps(metadata, ensure_ascii=False)),
                )
            self.set_state("coverage", coverage)
            self.set_state("fetched_at", time.time())

    def documents(self):
        return [
            json.loads(row[0])
            for row in self.db.execute(
                "SELECT metadata FROM documents WHERE present=1 ORDER BY rowid"
            )
        ]

    def blob(self, doc_id):
        row = self.db.execute("SELECT sha256 FROM documents WHERE id=?", (doc_id,)).fetchone()
        if not row or not row[0]:
            return None
        path = self.path / "pdfs" / f"{row[0]}.pdf"
        try:
            body = path.read_bytes()
        except FileNotFoundError:
            return None
        if not body.startswith(b"%PDF-") or hashlib.sha256(body).hexdigest() != row[0]:
            return None
        return path

    def store(self, doc_id, body):
        if not body:
            raise click.ClickException("MyOralia returned an empty document (zero bytes).")
        if not body.startswith(b"%PDF-"):
            raise click.ClickException("MyOralia did not return a PDF; no file was cached.")
        digest = hashlib.sha256(body).hexdigest()
        path = self.path / "pdfs" / f"{digest}.pdf"
        atomic_write(path, body)
        with self.db:
            self.db.execute(
                "UPDATE documents SET sha256=?, error=NULL WHERE id=?", (digest, doc_id)
            )
        return path

    def failure(self, doc_id, error):
        with self.db:
            self.db.execute("UPDATE documents SET error=? WHERE id=?", (error, doc_id))

    def error(self, doc_id):
        row = self.db.execute("SELECT error FROM documents WHERE id=?", (doc_id,)).fetchone()
        return row[0] if row else None

    def status(self):
        documents = self.documents()
        paths = [path for row in documents if (path := self.blob(row["id"]))]
        failures = [
            {"id": row[0], "error": row[1]}
            for row in self.db.execute(
                "SELECT id,error FROM documents WHERE present=1 AND error IS NOT NULL"
            )
        ]
        return {
            "path": str(self.path),
            "account": self.state("account"),
            "fetched_at": self.state("fetched_at"),
            "documents": len(documents),
            "downloaded": len(paths),
            "unique_pdfs": len(set(paths)),
            "bytes": sum(path.stat().st_size for path in set(paths)),
            "coverage": self.state("coverage", {}),
            "failures": failures,
            "complete": (
                self.state("coverage", {}).get("complete", False)
                and not failures
                and len(paths) == len(documents)
            ),
        }
