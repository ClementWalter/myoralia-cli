"""Website-shaped fixtures cover attachments outside the main document library."""

import click
import pytest

from myoralia import inventory, parsing


@pytest.fixture
def meeting():
    return """<div class="content-inner"><div class="collapse-box">
      <a class="collapse-box-header">AG 25/06/2026</a><div class="collapse-box-content">
      <a onclick="load('Urlhash=TOKEN')">Quote.pdf</a></div></div></div>"""


def test_viewer_resolves_download_route(meeting):
    assert inventory.attachments(parsing.soup(meeting), "meetings")[0]["_url"] == (
        "https://myoralia.fr/extranet/downdoc.php?Urlhash=TOKEN"
    )


def test_activity_archives_are_followed():
    page = parsing.soup(
        '<div class="content-inner">'
        '<a href="viearchives_coproprietaire.php?Urlhash=abc">Archives</a></div>'
    )
    assert inventory.child_pages(page, "activity")[0][0] == "activity-archives"


def test_activity_details_do_not_follow_return_links():
    page = parsing.soup(
        '<div class="content-inner">'
        '<a href="viearchives_coproprietaire.php?Urlhash=abc">Return</a></div>'
    )
    assert inventory.child_pages(page, "activity-details") == []


def test_viewer_id_survives_url_rotation(meeting):
    assert (
        inventory.attachments(parsing.soup(meeting), "meetings")[0]["id"]
        == (
            inventory.attachments(parsing.soup(meeting.replace("TOKEN", "OTHER")), "meetings")[0][
                "id"
            ]
        )
    )


def test_meeting_date_distinguishes_same_filename(meeting):
    assert (
        inventory.attachments(parsing.soup(meeting), "meetings")[0]["id"]
        != (
            inventory.attachments(parsing.soup(meeting.replace("2026", "2025")), "meetings")[0][
                "id"
            ]
        )
    )


def test_malformed_viewer_fails_instead_of_omitting():
    with pytest.raises(click.ClickException):
        inventory.attachments(parsing.soup('<a onclick="load(unknown)">PDF</a>'), "meetings")


def test_agenda_attachment_without_list_item():
    page = parsing.soup(
        '<div class="content-inner"><div>Event 2026-09-01'
        '<a href="downdocged.php?Urlhash=abc">Compte-rendu</a></div></div>'
    )
    assert inventory.attachments(page, "agenda")[0]["name"] == "Compte-rendu"


def test_unrelated_action_not_followed():
    assert (
        inventory.attachments(
            parsing.soup('<a href="paiement.php">Pay</a><button onclick="submit()">Send</button>'),
            "meetings",
        )
        == []
    )
