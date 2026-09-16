"""Import Chrome sessions and keep validated credentials in owner-only local files."""

import json
import os
import tempfile
import time
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen

import click
import websocket

ORIGIN = "https://myoralia.fr"


class SessionExpired(click.ClickException):
    """An expired provider session requires login before more downloads are attempted."""


def config_path():
    root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return root / "myoralia-cli" / "session.json"


def normalize_cookies(value):
    """Preserve cookie scope while rejecting unrelated or expired browser credentials."""
    rows = value.get("cookies") if isinstance(value, dict) else value
    if not isinstance(rows, list):
        raise click.ClickException('Expected a Chrome cookie JSON array or {"cookies": [...]}.')
    result = []
    for row in rows:
        if not isinstance(row, dict):
            raise click.ClickException("Invalid cookie record.")
        domain = row.get("domain", "")
        if not isinstance(domain, str):
            raise click.ClickException("Cookie domain must be a string.")
        if domain.lstrip(".") != "myoralia.fr":
            continue
        if not all(isinstance(row.get(key), str) for key in ("name", "value", "path")):
            raise click.ClickException(
                "Cookies require string name, value, domain and path fields."
            )
        expires = row.get("expires", -1)
        if not isinstance(expires, (float, int)):
            raise click.ClickException("Cookie expiry must be a number.")
        if expires > 0 and expires <= time.time():
            continue
        result.append({key: row[key] for key in ("name", "value", "domain", "path")})
    if not any(row["name"] == "PHPSESSID" for row in result):
        raise click.ClickException(
            "No live MyOralia PHPSESSID cookie. Sign in to myoralia.fr in Chrome."
        )
    return result


def chrome_cookies(cookie_file=None):
    import browser_cookie3

    try:
        jar = browser_cookie3.chrome(cookie_file=cookie_file, domain_name="myoralia.fr")
    except Exception as exc:
        # Provider errors can contain local credential details.
        raise click.ClickException(
            "Could not read Chrome cookies. Use login --cdp-url or login --cookie-stdin."
        ) from exc
    return normalize_cookies(
        [
            {
                "name": c.name,
                "value": c.value,
                "domain": c.domain,
                "path": c.path,
                "expires": c.expires or -1,
            }
            for c in jar
        ]
    )


def cdp_cookies(endpoint):
    """Read only this site's cookies from an existing local Chrome DevTools connection."""
    parsed = urlparse(endpoint)
    if parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise click.ClickException("--cdp-url must be a local http Chrome DevTools endpoint.")
    try:
        with urlopen(endpoint.rstrip("/") + "/json/list", timeout=10) as response:
            targets = json.load(response)
        target = next(
            t
            for t in targets
            if t.get("type") == "page" and urlparse(t.get("url", "")).hostname == "myoralia.fr"
        )
        address = target["webSocketDebuggerUrl"]
        if urlparse(address).hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("Non-local debugger")
        connection = websocket.create_connection(address, timeout=10, suppress_origin=True)
        try:
            connection.send(
                json.dumps(
                    {
                        "id": 1,
                        "method": "Network.getCookies",
                        "params": {"urls": [ORIGIN + "/", ORIGIN + "/extranet/"]},
                    }
                )
            )
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                reply = json.loads(connection.recv())
                if reply.get("id") == 1:
                    return normalize_cookies(reply.get("result", {}))
            raise TimeoutError
        finally:
            connection.close()
    except (OSError, ValueError, KeyError, StopIteration, websocket.WebSocketException) as exc:
        raise click.ClickException(
            "Cannot read MyOralia from Chrome DevTools. Open a signed-in MyOralia tab "
            "in the Chrome instance listening at --cdp-url."
        ) from exc


def save_session(cookies, identity):
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump({"cookies": cookies, "identity": identity}, stream, ensure_ascii=False)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def load_session():
    try:
        data = json.loads(config_path().read_text())
        if not isinstance(data, dict):
            raise ValueError("Session must be an object")
        data["cookies"] = normalize_cookies(data)
        return data
    except (OSError, ValueError, KeyError) as exc:
        raise click.ClickException(
            "No valid CLI session. Run: myoralia login --browser chrome"
        ) from exc
