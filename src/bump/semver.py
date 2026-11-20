"""Strict Semantic Versioning 2.0.0 parsing, comparison and bumping.

Pure stdlib, no dependencies. Implements the grammar from semver.org:

    MAJOR.MINOR.PATCH[-PRERELEASE][+BUILD]

with the exact comparison precedence (prerelease < release, numeric
identifiers compare numerically, build metadata ignored).
"""

from __future__ import annotations

import re

__all__ = ["SemVer", "SemVerError", "parse", "bump"]

_SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)"
    r"(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?"
    r"(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$"
)

_IDENT_RE = re.compile(r"^(0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)$")


class SemVerError(ValueError):
    """Raised when a string is not a valid SemVer 2.0.0 version."""


class SemVer:
    """An immutable Semantic Version."""

    __slots__ = ("major", "minor", "patch", "prerelease", "build")

    def __init__(
        self,
        major: int,
        minor: int,
        patch: int,
        prerelease: tuple[str, ...] = (),
        build: tuple[str, ...] = (),
    ) -> None:
        if any(n < 0 for n in (major, minor, patch)):
            raise SemVerError("version numbers must be non-negative")
        for ident in prerelease:
            if not _IDENT_RE.match(ident):
                raise SemVerError(f"invalid prerelease identifier: {ident!r}")
        for ident in build:
            if not ident or not re.fullmatch(r"[0-9a-zA-Z-]+", ident):
                raise SemVerError(f"invalid build identifier: {ident!r}")
        self.major = major
        self.minor = minor
        self.patch = patch
        self.prerelease = tuple(prerelease)
        self.build = tuple(build)

    # -- parsing ---------------------------------------------------------
    @classmethod
    def parse(cls, text: str) -> "SemVer":
        """Parse a version string, raising SemVerError on invalid input."""
        m = _SEMVER_RE.match(text.strip())
        if not m:
            raise SemVerError(
                f"{text!r} is not a valid Semantic Version "
                "(expected MAJOR.MINOR.PATCH[-prerelease][+build])"
            )
        major, minor, patch = (int(m.group(i)) for i in (1, 2, 3))
        pre = tuple(m.group(4).split(".")) if m.group(4) else ()
        build = tuple(m.group(5).split(".")) if m.group(5) else ()
        return cls(major, minor, patch, pre, build)

    # -- rendering -------------------------------------------------------
    def __str__(self) -> str:
        s = f"{self.major}.{self.minor}.{self.patch}"
        if self.prerelease:
            s += "-" + ".".join(self.prerelease)
        if self.build:
            s += "+" + ".".join(self.build)
        return s

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return f"SemVer({str(self)!r})"

    @property
    def core(self) -> str:
        """The MAJOR.MINOR.PATCH part, without prerelease or build."""
        return f"{self.major}.{self.minor}.{self.patch}"

    @property
    def is_prerelease(self) -> bool:
        return bool(self.prerelease)

    # -- comparison ------------------------------------------------------
    def _cmp_key(self):
        # A version without a prerelease sorts HIGHER than the same
        # version with one (1.0.0 > 1.0.0-rc.1). Numeric identifiers
        # compare numerically and sort before alphanumeric ones.
        if self.prerelease:
            pre_key = tuple(
                (0, int(p), "") if p.isdigit() else (1, 0, p)
                for p in self.prerelease
            )
            pre = (0, pre_key)
        else:
            pre = (1, ())
        return (self.major, self.minor, self.patch, pre)

    def __eq__(self, other):
        if isinstance(other, str):
            try:
                other = SemVer.parse(other)
            except SemVerError:
                return NotImplemented
        if not isinstance(other, SemVer):
            return NotImplemented
        return self._cmp_key() == other._cmp_key()

    def __lt__(self, other):
        if isinstance(other, str):
            other = SemVer.parse(other)
        if not isinstance(other, SemVer):
            return NotImplemented
        return self._cmp_key() < other._cmp_key()

    def __le__(self, other):
        return self == other or self < other

    def __gt__(self, other):
        return not self <= other

    def __ge__(self, other):
        return not self < other

    def __hash__(self):
        return hash(self._cmp_key())

    # -- bumping ---------------------------------------------------------
    def bump_major(self) -> "SemVer":
        """1.2.3 -> 2.0.0 (drops prerelease and build metadata)."""
        return SemVer(self.major + 1, 0, 0)

    def bump_minor(self) -> "SemVer":
        """1.2.3 -> 1.3.0 (drops prerelease and build metadata)."""
        return SemVer(self.major, self.minor + 1, 0)

    def bump_patch(self) -> "SemVer":
        """1.2.3 -> 1.2.4; 1.2.3-rc.1 -> 1.2.3 (release the candidate)."""
        if self.prerelease:
            return SemVer(self.major, self.minor, self.patch)
        return SemVer(self.major, self.minor, self.patch + 1)

    def bump_prerelease(self, tag: str = "rc") -> "SemVer":
        """1.2.3 -> 1.2.4-rc.1; 1.2.4-rc.1 -> 1.2.4-rc.2.

        If the version already has a prerelease with the same tag, the
        trailing number is incremented (``alpha`` -> ``alpha.1`` ->
        ``alpha.2``). A different tag restarts at ``.1`` on the same
        core version.
        """
        if not tag or not re.fullmatch(r"[0-9a-zA-Z-]+", tag):
            raise SemVerError(f"invalid prerelease tag: {tag!r}")
        if self.prerelease:
            pre = list(self.prerelease)
            if pre[0] == tag and len(pre) > 1 and pre[-1].isdigit():
                pre[-1] = str(int(pre[-1]) + 1)
                return SemVer(self.major, self.minor, self.patch, tuple(pre))
            if pre[0] == tag and len(pre) == 1:
                return SemVer(
                    self.major, self.minor, self.patch, (tag, "1")
                )
            return SemVer(
                self.major, self.minor, self.patch, (tag, "1")
            )
        return SemVer(self.major, self.minor, self.patch + 1, (tag, "1"))

    def bump_release(self) -> "SemVer":
        """1.2.3-rc.1 -> 1.2.3 (strip prerelease, keep the core)."""
        return SemVer(self.major, self.minor, self.patch)


def parse(text: str) -> SemVer:
    """Parse a version string (alias for ``SemVer.parse``)."""
    return SemVer.parse(text)


def bump(version: str, kind: str, tag: str = "rc") -> SemVer:
    """Bump ``version`` by ``kind``: major, minor, patch, prerelease, release."""
    v = SemVer.parse(version)
    kinds = {
        "major": v.bump_major,
        "minor": v.bump_minor,
        "patch": v.bump_patch,
        "release": v.bump_release,
    }
    if kind == "prerelease":
        return v.bump_prerelease(tag)
    try:
        return kinds[kind]()
    except KeyError:
        raise SemVerError(
            f"unknown bump kind: {kind!r} "
            "(expected major, minor, patch, prerelease, release)"
        ) from None
