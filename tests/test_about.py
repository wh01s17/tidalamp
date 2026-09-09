"""Credits, licence, release notes, and turning key names into keys."""

from __future__ import annotations

from pathlib import Path

import pytest

from tidalamp import __version__, about


def test_the_credits_point_at_the_authors_repository():
    assert about.REPO_URL == "https://github.com/wh01s17/tidalamp"
    assert about.AUTHOR == "wh01s17"
    assert about.LICENSE == "GPL-3.0-or-later"
    assert about.LICENSE_URL.startswith("https://")


def test_the_version_is_the_one_the_package_declares():
    # Installed metadata wins, but in a checkout both are the same string.
    assert about.version() == __version__


def pyproject_version() -> str | None:
    """The version in pyproject.toml, or None when it is not next to us.

    It ships in the sdist, so this runs in the AUR's `check()` too; from an
    installed wheel there is nothing to compare against and the test skips.
    """
    import tomllib

    path = Path(__file__).resolve().parent.parent / "pyproject.toml"
    if not path.is_file():
        return None
    with path.open("rb") as handle:
        return str(tomllib.load(handle)["project"]["version"])


def test_every_copy_of_the_version_agrees():
    """A release edits pyproject.toml and the PKGBUILD; two more copies live
    here, and nothing but this test would notice them drifting.

    `release.yml` already refuses a tag that disagrees with pyproject.toml, so
    tying the rest to it is what keeps the About screen from announcing a
    version the package is not."""
    declared = pyproject_version()
    if declared is None:
        pytest.skip("pyproject.toml no está junto al paquete instalado")

    assert __version__ == declared, "tidalamp/__init__.py"
    assert about.releases()[0].version == declared, "about.releases()"


@pytest.mark.parametrize(
    "binding, shown",
    [
        ("slash", "/"),
        ("question_mark,h", "? / h"),
        ("d,delete", "d / del"),
        ("plus,equals_sign", "+ / ="),
        ("alt+up", "alt+↑"),
        ("q,ctrl+c", "q / ctrl+c"),
        # Anything unmapped is shown as it is rather than dropped.
        ("p", "p"),
        ("ctrl+shift+z", "ctrl+shift+z"),
        ("", ""),
    ],
)
def test_key_names_are_shown_as_the_key_you_press(binding, shown):
    assert about.pretty_keys(binding) == shown


def test_every_release_has_notes():
    releases = about.releases()
    assert releases
    for release in releases:
        assert release.version and release.date
        assert release.changes


def test_the_shortcuts_come_from_the_resolver_not_from_the_defaults():
    """A rebound key has to reach the screen, or the help lies about the app."""
    asked: list[str] = []

    def keys(action: str) -> str:
        asked.append(action)
        return "ctrl+j" if action == "play" else "p"

    sections = about.shortcuts(keys)
    assert "play" in asked
    rows = [row for section in sections for row in section.rows]
    assert ("ctrl+j", "reproducir o pausar (▶ / ‖)") in rows


def test_every_section_has_a_title_and_rows():
    for section in about.shortcuts(lambda action: "k"):
        assert section.title
        assert section.rows
        for key, description in section.rows:
            assert key and description
