"""Tests for bump.semver: parsing, comparison, bumping."""

import pytest

from bump.semver import SemVer, SemVerError, bump, parse


def test_parse_full():
    v = parse("1.2.3-rc.1+build.5")
    assert (v.major, v.minor, v.patch) == (1, 2, 3)
    assert v.prerelease == ("rc", "1")
    assert v.build == ("build", "5")
    assert str(v) == "1.2.3-rc.1+build.5"


def test_parse_plain():
    assert str(parse("0.0.0")) == "0.0.0"
    assert str(parse("10.20.30")) == "10.20.30"
    assert parse("  1.2.3  ") == parse("1.2.3")  # surrounding whitespace ok


@pytest.mark.parametrize(
    "bad",
    [
        "1.2", "1.2.3.4", "v1.2.3", "01.2.3", "1.02.3", "1.2.03",
        "1.2.3-", "1.2.3+", "1.2.3-01", "1.2.3-rc..1", "1.2.3-rc_1",
        "", "1.2.x", "latest",
    ],
)
def test_parse_rejects_invalid(bad):
    with pytest.raises(SemVerError):
        parse(bad)


def test_comparison_semver_org_ordering():
    # The canonical ordering example from semver.org:
    # 1.0.0-alpha < 1.0.0-alpha.1 < 1.0.0-alpha.beta < 1.0.0-beta
    # < 1.0.0-beta.2 < 1.0.0-beta.11 < 1.0.0-rc.1 < 1.0.0
    ordered = [
        "1.0.0-alpha", "1.0.0-alpha.1", "1.0.0-alpha.beta", "1.0.0-beta",
        "1.0.0-beta.2", "1.0.0-beta.11", "1.0.0-rc.1", "1.0.0",
    ]
    parsed = [parse(v) for v in ordered]
    assert parsed == sorted(parsed)
    assert parse("1.0.0") > parse("1.0.0-rc.1")
    assert parse("2.0.0") > parse("1.999.999")


def test_build_metadata_ignored_in_precedence():
    assert parse("1.0.0+build.1") == parse("1.0.0+build.2")
    assert parse("1.0.0+build.1") == parse("1.0.0")


def test_bump_major_minor_patch():
    assert str(bump("1.2.3", "major")) == "2.0.0"
    assert str(bump("1.2.3", "minor")) == "1.3.0"
    assert str(bump("1.2.3", "patch")) == "1.2.4"
    assert str(bump("0.9.9", "major")) == "1.0.0"
    # bumping drops prerelease and build metadata
    assert str(bump("1.2.3-rc.1+build.1", "major")) == "2.0.0"
    assert str(bump("1.2.3-rc.1", "minor")) == "1.3.0"


def test_bump_patch_releases_prerelease():
    # patch on a prerelease just releases it — no version increment.
    assert str(bump("1.2.3-rc.1", "patch")) == "1.2.3"


def test_bump_prerelease():
    assert str(bump("1.2.3", "prerelease")) == "1.2.4-rc.1"
    assert str(bump("1.2.4-rc.1", "prerelease")) == "1.2.4-rc.2"
    assert str(bump("1.2.3-alpha", "prerelease", tag="alpha")) == "1.2.3-alpha.1"
    assert str(bump("1.2.3-alpha.1", "prerelease", tag="alpha")) == "1.2.3-alpha.2"
    assert str(bump("1.2.3", "prerelease", tag="beta")) == "1.2.4-beta.1"
    # switching tag restarts the counter on the same core version
    assert str(bump("1.2.4-rc.2", "prerelease", tag="beta")) == "1.2.4-beta.1"


def test_bump_release():
    assert str(bump("1.2.3-rc.1", "release")) == "1.2.3"
    assert str(bump("1.2.3", "release")) == "1.2.3"


def test_bump_unknown_kind():
    with pytest.raises(SemVerError):
        bump("1.2.3", "nope")


def test_is_prerelease_and_core():
    v = parse("2.0.0-beta.1")
    assert v.is_prerelease
    assert v.core == "2.0.0"
    assert not parse("2.0.0").is_prerelease
