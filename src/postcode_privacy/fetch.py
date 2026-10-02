"""Locating and downloading the current ONS Postcode Directory.

This is best-effort by design. The release is published quarterly under a new
item on the ONS Open Geography Portal, so the identifier changes four times a
year and the search that finds it is outside this project's control. Every
failure path therefore ends with instructions for doing it by hand, so a broken
search is an inconvenience rather than a dead end.

The package still ships no data. This downloads to the user's own machine, and
Northern Ireland records in the result remain non-redistributable.
"""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

SEARCH_URL = (
    "https://hub.arcgis.com/api/search/v1/collections/dataset/items"
    "?q=ONS%20Postcode%20Directory&limit=50"
)
ITEM_DATA_URL = "https://www.arcgis.com/sharing/rest/content/items/{item_id}/data"
PORTAL = "https://geoportal.statistics.gov.uk/"

# "ONS Postcode Directory (August 2026)" and nothing more. The portal also
# publishes a User Guide under a near-identical title, often with a newer
# timestamp, so matching loosely would download a PDF and call it the data.
RELEASE_TITLE = re.compile(r"^ONS Postcode Directory \(([A-Za-z]+ \d{4})\)$")

MANUAL_INSTRUCTIONS = (
    f"Download the current ONS Postcode Directory by hand from {PORTAL} and "
    "pass it with --onspd PATH instead."
)


class NoReleaseFoundError(RuntimeError):
    """Raised when the portal search returns nothing usable."""


ALLOWED_HOSTS = frozenset({"www.arcgis.com", "hub.arcgis.com"})


def _checked_url(url: str) -> str:
    """Refuse anything that is not https to a known portal host.

    The identifier is interpolated into a fixed template, so this should never
    fire -- but the value comes from an external search API, and a downloader
    that would follow ``file:`` or an unexpected host is not something to leave
    to argument alone.
    """
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS:
        raise NoReleaseFoundError(
            f"refusing to download from {url!r}: only https to "
            f"{sorted(ALLOWED_HOSTS)} is permitted. {MANUAL_INSTRUCTIONS}"
        )
    return url


@dataclass(frozen=True)
class OnspdRelease:
    """One published ONSPD release."""

    item_id: str
    title: str
    created: int

    @property
    def download_url(self) -> str:
        return ITEM_DATA_URL.format(item_id=self.item_id)


def choose_latest(features: list[dict]) -> OnspdRelease:
    """The newest actual data release among portal search results."""
    releases = [
        OnspdRelease(
            item_id=str(feature.get("id", "")),
            title=str((feature.get("properties") or {}).get("title", "")),
            created=int((feature.get("properties") or {}).get("created", 0)),
        )
        for feature in features
    ]
    matching = [release for release in releases if RELEASE_TITLE.match(release.title)]
    if not matching:
        raise NoReleaseFoundError(
            "no ONS Postcode Directory release found in the portal search "
            f"results. {MANUAL_INSTRUCTIONS}"
        )
    return max(matching, key=lambda release: release.created)


def latest_release() -> OnspdRelease:  # pragma: no cover - network
    with urllib.request.urlopen(SEARCH_URL, timeout=60) as response:
        payload = json.load(response)
    return choose_latest(payload.get("features") or [])


def fetch_onspd(destination: Path) -> Path:  # pragma: no cover - network
    """Download the current release into ``destination`` and return the CSV."""
    destination.mkdir(parents=True, exist_ok=True)
    release = latest_release()

    archive = destination / f"{release.item_id}.zip"
    if not archive.exists():
        urllib.request.urlretrieve(  # noqa: S310 - scheme and host checked
            _checked_url(release.download_url), archive
        )

    with zipfile.ZipFile(archive) as bundle:
        names = [
            name
            for name in bundle.namelist()
            # The combined UK file, not the per-area split in multi_csv/.
            if name.endswith("_UK.csv") and "multi_csv" not in name
        ]
        if not names:
            raise NoReleaseFoundError(
                f"{archive} contains no combined UK CSV. {MANUAL_INSTRUCTIONS}"
            )
        bundle.extract(names[0], destination)

    return destination / names[0]
