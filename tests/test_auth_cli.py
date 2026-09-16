"""Authentication and CLI failures must leave existing sessions and files intact."""

import json
import os
import subprocess

import click
import pytest
from click.testing import CliRunner

from myoralia import auth
from myoralia.cli import cli


@pytest.fixture
def cookie():
    return {"name": "PHPSESSID", "value": "synthetic", "domain": "myoralia.fr", "path": "/"}


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))


def test_cookie_import_preserves_scope(cookie):
    assert auth.normalize_cookies([cookie]) == [cookie]


def test_expired_session_cookie_rejected(cookie):
    with pytest.raises(click.ClickException):
        auth.normalize_cookies([{**cookie, "expires": 1}])


def test_foreign_session_cookie_rejected(cookie):
    with pytest.raises(click.ClickException):
        auth.normalize_cookies([{**cookie, "domain": "evil.test"}])


def test_saved_session_permissions(cookie):
    auth.save_session([cookie], "Example User")
    assert auth.config_path().stat().st_mode & 0o777 == 0o600


def test_failed_login_preserves_saved_session(cookie):
    auth.save_session([cookie], "Example User")
    before = auth.config_path().read_bytes()
    CliRunner().invoke(cli, ["login", "--cookie-stdin"], input="bad-json")
    assert auth.config_path().read_bytes() == before


def test_logout_removes_session(cookie):
    auth.save_session([cookie], "Example User")
    CliRunner().invoke(cli, ["logout"])
    assert not auth.config_path().exists()


def test_logout_is_idempotent():
    CliRunner().invoke(cli, ["logout"])
    assert CliRunner().invoke(cli, ["logout"]).exit_code == 0


def test_logged_out_command_has_actionable_error():
    assert "myoralia login" in CliRunner().invoke(cli, ["whoami"]).output


def test_bare_cli_is_successful_discovery():
    assert CliRunner().invoke(cli, []).exit_code == 0


def test_existing_download_never_overwritten(tmp_path):
    output = tmp_path / "existing.pdf"
    output.write_bytes(b"original")
    CliRunner().invoke(cli, ["documents", "download", "unused", "-o", str(output)])
    assert output.read_bytes() == b"original"


def test_missing_download_id_is_usage_error():
    assert CliRunner().invoke(cli, ["documents", "download"]).exit_code == 2


@pytest.mark.parametrize(
    "arguments",
    [
        [],
        ["login"],
        ["logout"],
        ["whoami"],
        ["doctor"],
        ["accounts"],
        ["accounts", "list"],
        ["documents"],
        ["documents", "list"],
        ["documents", "download"],
        ["building"],
        ["shares"],
        ["agenda"],
        ["agency"],
        ["meetings"],
        ["news"],
        ["statement"],
    ],
)
def test_help_has_examples(arguments):
    assert "Example" in CliRunner().invoke(cli, [*arguments, "--help"]).output


def test_subprocess_json_stdout_is_parseable():
    result = subprocess.run(
        ["myoralia", "logout", "--json"],
        capture_output=True,
        text=True,
        check=True,
        env=os.environ.copy(),
    )
    assert json.loads(result.stdout) == {"authenticated": False, "scope": "local-cli"}


def test_subprocess_error_uses_stderr():
    result = subprocess.run(
        ["myoralia", "whoami", "--json"], capture_output=True, text=True, env=os.environ.copy()
    )
    assert "myoralia login" in result.stderr
