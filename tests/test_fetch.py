"""Resolving which ONSPD release to download.

The download itself is a thin wrapper around urllib and is not tested here; the
part worth testing is the choice, which is where a wrong answer would be silent.
"""

import pytest

from postcode_privacy.fetch import NoReleaseFoundError, choose_latest

GUIDE = {
    "id": "guide1",
    "properties": {"title": "ONS Postcode Directory (August 2026) User Guide",
                   "created": 9_999_999_999_999},
}  # fmt: skip
MAY = {
    "id": "may2026",
    "properties": {"title": "ONS Postcode Directory (May 2026)",
                   "created": 1_780_047_907_000},
}  # fmt: skip
AUGUST = {
    "id": "aug2026",
    "properties": {"title": "ONS Postcode Directory (August 2026)",
                   "created": 1_788_260_239_000},
}  # fmt: skip


def test_it_picks_the_most_recent_release() -> None:
    release = choose_latest([MAY, AUGUST])

    assert release.item_id == "aug2026"
    assert release.title == "ONS Postcode Directory (August 2026)"


def test_user_guides_are_not_mistaken_for_the_data() -> None:
    # The guide is a separate item with the newest timestamp of all, so sorting
    # without filtering would download a PDF and call it a postcode directory.
    release = choose_latest([GUIDE, MAY, AUGUST])

    assert release.item_id == "aug2026"


def test_the_download_url_is_derived_from_the_item_id() -> None:
    assert choose_latest([AUGUST]).download_url.endswith("/aug2026/data")


def test_nothing_matching_says_how_to_do_it_by_hand() -> None:
    # The portal's search is outside our control, so the failure has to leave
    # the user able to continue rather than stuck.
    with pytest.raises(NoReleaseFoundError) as caught:
        choose_latest([GUIDE])

    assert "geoportal.statistics.gov.uk" in str(caught.value)
    assert "--onspd" in str(caught.value)


def test_a_download_url_that_is_not_https_to_the_portal_is_refused() -> None:
    # The identifier comes from an external search API. It is interpolated into
    # a fixed template so this should never fire, but a downloader that would
    # follow file: or an unexpected host is not left to argument alone.
    from postcode_privacy.fetch import _checked_url

    with pytest.raises(NoReleaseFoundError):
        _checked_url("file:///etc/passwd")
    with pytest.raises(NoReleaseFoundError):
        _checked_url("https://evil.example.com/data")

    assert _checked_url(choose_latest([AUGUST]).download_url)
