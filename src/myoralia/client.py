"""Follow fresh account links and perform only observed read operations."""

from urllib.parse import urlencode, urlparse

import click
from curl_cffi import requests

from . import parsing
from .auth import RECONNECT, SessionExpired, load_session

SECTIONS = {
    "building": "bien_coproprietaire.php",
    "shares": "tantieme_coproprietaire.php",
    "agenda": "calendrier_coproprietaire.php",
    "meetings": "ag_coproprietaire.php",
    "news": "actualites_coproprietaire.php",
    "agency": "monagence_coproprietaire.php",
    "statement": "relevedecompte_coproprietaire.php",
    "documents": "mesdocuments_coproprietaire.php",
    "useful-documents": "mesdocuments_oraliacopro.php",
}


class Client:
    def __init__(self, cookies=None):
        saved = load_session() if cookies is None else None
        self.expected_identity = saved.get("identity") if saved else None
        self.session = requests.Session(impersonate="chrome")
        for cookie in cookies if cookies is not None else saved["cookies"]:
            self.session.cookies.set(
                cookie["name"], cookie["value"], domain=cookie["domain"], path=cookie["path"]
            )
        self.account_page = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.session.close()

    def request(self, url, method="GET"):
        url = parsing.safe_url(url)
        try:
            for _ in range(6):
                # AG convocations bundle large PDFs that can take more than thirty seconds.
                timeout = (
                    180
                    if urlparse(url).path.rsplit("/", 1)[-1]
                    in {"downdoc.php", "downdocged.php", "docpdf.php", "lettre.php", "carnet.php"}
                    else 30
                )
                response = self.session.request(method, url, timeout=timeout, allow_redirects=False)
                if response.status_code in {301, 302, 303, 307, 308}:
                    url = parsing.safe_url(response.headers.get("location", ""), url)
                    if response.status_code in {301, 302, 303}:
                        method = "GET"
                    continue
                if response.status_code in {401, 403}:
                    raise SessionExpired("MyOralia rejected this session. " + RECONNECT)
                if response.status_code != 200:
                    raise click.ClickException(f"MyOralia returned HTTP {response.status_code}.")
                return response
            raise click.ClickException("MyOralia returned too many redirects.")
        except requests.RequestsError as exc:
            raise click.ClickException(
                "MyOralia request failed. Check your connection and retry."
            ) from exc

    def page(self, url):
        response = self.request(url)
        # The server labels legacy Windows-1252 pages as ISO-8859-1.
        html = response.content.decode(
            "utf-8" if "utf-8" in response.headers.get("content-type", "").lower() else "cp1252",
            errors="replace",
        )
        page = parsing.soup(html)
        name = parsing.identity(page)
        if self.expected_identity and name != self.expected_identity:
            raise click.ClickException(
                "The session account changed. Run `myoralia connect` explicitly to switch."
            )
        return page

    def pdf(self, url):
        response = self.request(url)
        if not response.content.startswith(b"%PDF-"):
            # Download endpoints can return empty HTTP 200 responses after session expiry.
            self.page(parsing.BASE + "selection_account.php")
            if not response.content:
                raise click.ClickException("MyOralia returned an empty document (zero bytes).")
            raise click.ClickException("MyOralia did not return a PDF; no file was cached.")
        return response.content

    def accounts(self):
        if self.account_page is None:
            self.account_page = self.page(parsing.BASE + "selection_account.php")
        return parsing.accounts(self.account_page)

    def whoami(self):
        accounts = self.accounts()
        return {"name": parsing.identity(self.account_page), "accounts": public(accounts)}

    def dashboard(self, account=None):
        accounts = self.accounts()
        matches = [row for row in accounts if row["id"] == account] if account else accounts
        if len(matches) != 1:
            raise click.ClickException("Choose an exact --account ID from: myoralia accounts list")
        # Account selection is the website's read-context POST, not a business mutation.
        response = self.request(
            parsing.BASE + "include/ajax_load.php?" + matches[0]["_query"], "POST"
        )
        url = parsing.safe_url(response.text.strip())
        if urlparse(url).path != "/extranet/bien_coproprietaire.php":
            raise click.ClickException("This CLI currently supports coproprietaire accounts only.")
        return self.page(url)

    def section(self, name, account=None):
        page = self.dashboard(account)
        if name == "building":
            return page
        for link in page.select("#nav-primary a[href]"):
            if urlparse(link["href"]).path == SECTIONS[name]:
                return self.page(parsing.safe_url(link["href"]))
        raise click.ClickException(f"The account does not expose the {name} section.")

    def documents(self, account=None, useful=False):
        page = self.section("useful-documents" if useful else "documents", account)
        return self.document_tree(page)

    def document_tree(self, page):
        """Expand lazy folders from a document page already selected for this account."""
        result = parsing.documents(page)
        pending = [(folder, "") for folder in parsing.folders(page)]
        visited = set()
        while pending:
            folder, parent = pending.pop(0)
            if folder["id"] in visited:
                continue
            if len(visited) >= 200:
                raise click.ClickException(
                    "Document folder limit reached; refusing a partial list."
                )
            visited.add(folder["id"])
            url = parsing.BASE + "include/ajax_GED.php?" + urlencode({"idrep": folder["id"]})
            response = self.request(url + "&" + folder["_query"])
            fragment = parsing.soup(response.content.decode("cp1252", errors="replace"))
            if fragment.select_one('input[type="password"]'):
                raise click.ClickException("Session expired while loading document folders.")
            category = " / ".join(filter(None, [parent, folder["name"]]))
            result.extend(parsing.documents(fragment, category))
            pending.extend((child, category) for child in parsing.folders(fragment))
        ids = [row["id"] for row in result]
        if len(ids) != len(set(ids)):
            raise click.ClickException(
                "Ambiguous document identities; refusing an incomplete list."
            )
        return result

    def download(self, doc_id, account=None, useful=False):
        rows = [row for row in self.documents(account, useful) if row["id"] == doc_id]
        if len(rows) != 1:
            raise click.ClickException("Document ID not found. Run: myoralia documents list --json")
        response = self.request(rows[0]["_url"])
        if not response.content.startswith(b"%PDF-"):
            raise click.ClickException("MyOralia did not return a PDF; no file was written.")
        return rows[0], response.content


def public(value):
    if isinstance(value, list):
        return [public(item) for item in value]
    if isinstance(value, dict):
        return {key: public(item) for key, item in value.items() if not key.startswith("_")}
    return value
