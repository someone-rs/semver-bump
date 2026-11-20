"""Find and rewrite version strings in project files.

Supported sources (checked in this order when auto-detecting):

- ``pyproject.toml``   — ``version = "x.y.z"`` under [project] or
  [tool.poetry] (regex-based, so it works on Python 3.9+)
- ``package.json``     — the ``"version"`` field
- ``Cargo.toml``       — ``version = "x.y.z"`` under [package]
- ``VERSION``          — the whole file is the version
- ``setup.cfg``        — ``version = x.y.z`` under [metadata]
- ``__init__.py``      — ``__version__ = "x.y.z"`` (any package __init__)

Replacement preserves the original quoting and surrounding text, so
diffs stay minimal and formatting untouched.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from .semver import SemVer, SemVerError

__all__ = ["VersionFile", "detect", "read_version", "write_version"]

# File names (or suffixes) auto-detected in a project directory.
_CANDIDATES = (
    "pyproject.toml",
    "package.json",
    "Cargo.toml",
    "VERSION",
    "setup.cfg",
)

_VERSION_LINE = re.compile(
    r"""(?m)^(?P<prefix>[ \t]*version[ \t]*=[ \t]*["'])(?P<ver>[^"']+)(?P<suffix>["'])"""
)
_INIT_VERSION = re.compile(
    r"""(?m)^(?P<prefix>[ \t]*__version__[ \t]*=[ \t]*["'])(?P<ver>[^"']+)(?P<suffix>["'])"""
)
_SETUP_CFG_VERSION = re.compile(
    r"""(?m)^(?P<prefix>[ \t]*version[ \t]*=[ \t]*)(?P<ver>[^\s#]+)(?P<suffix>[ \t]*(?:[#].*)?)$"""
)


@dataclass
class VersionFile:
    """One file that holds the project's version."""

    path: Path
    kind: str  # pyproject | package.json | cargo | version-file | setup.cfg | __init__
    version: SemVer

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.path} ({self.kind}): {self.version}"


def _section_text(text: str, header: str) -> str | None:
    """Return the text of a TOML ``[header]`` section, or None."""
    m = re.search(rf"(?m)^\[{re.escape(header)}\]\s*$", text)
    if not m:
        return None
    start = m.end()
    nxt = re.search(r"(?m)^\[", text[start:])
    end = start + nxt.start() if nxt else len(text)
    return text[start:end]


def _toml_version(text: str, sections: tuple[str, ...]) -> str | None:
    """Find ``version = "..."`` inside one of the given TOML sections."""
    for section in sections:
        body = _section_text(text, section)
        if body is None:
            continue
        m = _VERSION_LINE.search(body)
        if m:
            return m.group("ver")
    # Fallback: first version line anywhere (covers unusual layouts).
    m = _VERSION_LINE.search(text)
    return m.group("ver") if m else None


def _replace_toml_version(text: str, old: str, new: str, sections) -> str:
    """Replace the version inside one of the given TOML sections."""
    for section in sections:
        body = _section_text(text, section)
        if body is None:
            continue
        m = _VERSION_LINE.search(body)
        if m and m.group("ver") == old:
            start = text.find(body)
            replaced = _VERSION_LINE.sub(
                lambda mm: mm.group("prefix") + new + mm.group("suffix"),
                body,
                count=1,
            )
            return text[:start] + replaced + text[start + len(body):]
    # Fallback: replace the first matching version line anywhere.
    return _VERSION_LINE.sub(
        lambda mm: mm.group("prefix") + new + mm.group("suffix")
        if mm.group("ver") == old
        else mm.group(0),
        text,
        count=1,
    )


def _read_one(path: Path) -> VersionFile | None:
    """Detect the version in a single file, or None if it has none."""
    name = path.name
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None

    if name == "pyproject.toml":
        raw = _toml_version(text, ("project", "tool.poetry"))
        kind = "pyproject"
    elif name == "package.json":
        try:
            raw = json.loads(text).get("version")
        except (json.JSONDecodeError, AttributeError):
            raw = None
        kind = "package.json"
    elif name == "Cargo.toml":
        raw = _toml_version(text, ("package",))
        kind = "cargo"
    elif name == "VERSION":
        raw = text.strip()
        kind = "version-file"
    elif name == "setup.cfg":
        body = _section_text(text, "metadata")
        raw = None
        if body is not None:
            m = _SETUP_CFG_VERSION.search(body)
            raw = m.group("ver") if m else None
        kind = "setup.cfg"
    elif name == "__init__.py":
        m = _INIT_VERSION.search(text)
        raw = m.group("ver") if m else None
        kind = "__init__"
    else:
        return None

    if not raw:
        return None
    try:
        return VersionFile(path=path, kind=kind, version=SemVer.parse(raw))
    except SemVerError:
        return None


def _replace_one(path: Path, old: SemVer, new: SemVer) -> bool:
    """Rewrite the version in ``path``. Returns True if changed."""
    text = path.read_text(encoding="utf-8")
    old_s, new_s = str(old), str(new)
    name = path.name

    if name in ("pyproject.toml", "Cargo.toml"):
        sections = ("project", "tool.poetry") if name == "pyproject.toml" else ("package",)
        updated = _replace_toml_version(text, old_s, new_s, sections)
    elif name == "package.json":
        data = json.loads(text)
        if str(data.get("version")) != old_s:
            return False
        data["version"] = new_s
        # Preserve formatting: rewrite only the version value, wherever
        # it sits on the line (pretty-printed or minified single-line).
        updated = re.sub(
            r"""(?P<prefix>"version"[ \t]*:[ \t]*")(?P<ver>[^"]+)(?P<suffix>")""",
            lambda mm: (
                mm.group("prefix") + new_s + mm.group("suffix")
                if mm.group("ver") == old_s
                else mm.group(0)
            ),
            text,
            count=1,
        )
    elif name == "VERSION":
        if text.strip() != old_s:
            return False
        updated = new_s + ("\n" if text.endswith("\n") else "")
    elif name == "setup.cfg":
        body = _section_text(text, "metadata")
        if body is None:
            return False
        m = _SETUP_CFG_VERSION.search(body)
        if not m or m.group("ver") != old_s:
            return False
        start = text.find(body)
        replaced = _SETUP_CFG_VERSION.sub(
            lambda mm: mm.group("prefix") + new_s + mm.group("suffix"),
            body,
            count=1,
        )
        updated = text[:start] + replaced + text[start + len(body):]
    elif name == "__init__.py":
        m = _INIT_VERSION.search(text)
        if not m or m.group("ver") != old_s:
            return False
        updated = _INIT_VERSION.sub(
            lambda mm: mm.group("prefix") + new_s + mm.group("suffix"),
            text,
            count=1,
        )
    else:
        return False

    if updated == text:
        return False
    path.write_text(updated, encoding="utf-8")
    return True


def detect(directory: Path | str = ".") -> list[VersionFile]:
    """Auto-detect every version file in ``directory`` (non-recursive).

    Also scans one level of ``src/*/`` and ``*/`` package directories
    for ``__init__.py`` files carrying ``__version__``.
    """
    directory = Path(directory)
    found: list[VersionFile] = []
    for name in _CANDIDATES:
        vf = _read_one(directory / name)
        if vf is not None:
            found.append(vf)
    # __init__.py: project root, src layout, and single-package layout.
    init_candidates = [directory / "__init__.py"]
    for base in (directory, directory / "src"):
        if base.is_dir():
            init_candidates += sorted(p for p in base.glob("*/__init__.py"))
    for path in init_candidates:
        vf = _read_one(path)
        if vf is not None:
            found.append(vf)
    return found


def read_version(path: Path | str) -> VersionFile:
    """Read the version from one explicit file (raises on failure)."""
    p = Path(path)
    vf = _read_one(p)
    if vf is None:
        raise SemVerError(f"no valid SemVer version found in {p}")
    return vf


def write_version(path: Path | str, old: SemVer, new: SemVer) -> bool:
    """Rewrite the version in one explicit file."""
    return _replace_one(Path(path), old, new)
