"""Opt-in subprocess checks read the real website without modifying account data."""

import json
import os
import subprocess

import pytest

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        os.environ.get("MYORALIA_LIVE_TESTS") != "1",
        reason="Set MYORALIA_LIVE_TESTS=1 for live reads",
    ),
]


@pytest.mark.parametrize("section", ["building", "shares", "agenda", "meetings", "news", "agency"])
def test_live_section_cli(section):
    result = subprocess.run(
        ["myoralia", section, "--json"], capture_output=True, text=True, check=True, timeout=90
    )
    assert json.loads(result.stdout)["title"]


def test_live_doctor_cli():
    result = subprocess.run(
        ["myoralia", "doctor", "--json"], capture_output=True, text=True, check=True, timeout=60
    )
    assert json.loads(result.stdout)["ok"] is True


def test_live_statement_cli():
    result = subprocess.run(
        ["myoralia", "statement", "--json"], capture_output=True, text=True, check=True, timeout=90
    )
    assert json.loads(result.stdout)["currency"] == "EUR"


@pytest.fixture(scope="module")
def documents():
    result = subprocess.run(
        ["myoralia", "documents", "list", "--json"],
        capture_output=True,
        text=True,
        check=True,
        timeout=180,
    )
    return json.loads(result.stdout)


def test_live_documents_cli(documents):
    assert documents


def test_live_pdf_download_cli(documents, tmp_path):
    output = tmp_path / "document.pdf"
    subprocess.run(
        ["myoralia", "documents", "download", documents[0]["id"], "-o", str(output)],
        capture_output=True,
        text=True,
        check=True,
        timeout=180,
    )
    assert output.read_bytes().startswith(b"%PDF-")


def test_live_useful_documents_cli():
    result = subprocess.run(
        ["myoralia", "documents", "list", "--useful", "--json"],
        capture_output=True,
        text=True,
        check=True,
        timeout=180,
    )
    assert json.loads(result.stdout)


def test_live_useful_pdf_download_cli(tmp_path):
    listing = subprocess.run(
        ["myoralia", "documents", "list", "--useful", "--json"],
        capture_output=True,
        text=True,
        check=True,
        timeout=180,
    )
    output = tmp_path / "guide.pdf"
    subprocess.run(
        [
            "myoralia",
            "documents",
            "download",
            json.loads(listing.stdout)[0]["id"],
            "--useful",
            "-o",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=180,
    )
    assert output.read_bytes().startswith(b"%PDF-")
