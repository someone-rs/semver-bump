"""Command-line interface for semver-bump.

Exit codes (CI-friendly, matching the rest of the Muse Lab CLIs):
    0  success
    1  runtime error (no version found, version mismatch, git failure)
    2  usage error (argparse)
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from . import __version__ as _TOOL_VERSION
from .detect import VersionFile, detect, read_version, write_version
from .semver import SemVer, SemVerError, bump

KINDS = ("major", "minor", "patch", "prerelease", "release")


class BumpError(Exception):
    """A user-facing error: print the message, exit 1."""


# ---------------------------------------------------------------- git ----
def _git(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
    )


def _git_available(cwd: Path) -> bool:
    return _git("rev-parse", "--git-dir", cwd=cwd).returncode == 0


def _git_is_dirty(cwd: Path) -> bool:
    return _git("status", "--porcelain", cwd=cwd).stdout.strip() != ""


def _git_commit(cwd: Path, message: str, files: list[Path]) -> None:
    rel = [str(f.relative_to(cwd)) if f.is_absolute() else str(f) for f in files]
    r = _git("add", *rel, cwd=cwd)
    if r.returncode != 0:
        raise BumpError(f"git add failed: {r.stderr.strip()}")
    r = _git("commit", "-m", message, cwd=cwd)
    if r.returncode != 0:
        raise BumpError(f"git commit failed: {r.stderr.strip()}")


def _git_tag(cwd: Path, tag: str) -> None:
    r = _git("tag", tag, cwd=cwd)
    if r.returncode != 0:
        raise BumpError(f"git tag failed: {r.stderr.strip()}")


# ------------------------------------------------------------ helpers ----
def _resolve_files(directory: Path, explicit: list[str] | None) -> list[VersionFile]:
    """Return the version files to operate on."""
    if explicit:
        files = []
        for raw in explicit:
            p = Path(raw)
            if not p.is_absolute():
                p = directory / p
            files.append(read_version(p))
        return files
    files = detect(directory)
    if not files:
        raise BumpError(
            "no version found — expected one of pyproject.toml, "
            "package.json, Cargo.toml, VERSION, setup.cfg or an "
            "__init__.py with __version__ in the current directory"
        )
    return files


def _agree_on_version(files: list[VersionFile], force: bool) -> SemVer:
    """All files must agree on the current version (unless --force)."""
    versions = {str(f.version) for f in files}
    if len(versions) == 1:
        return files[0].version
    detail = ", ".join(f"{f.path.name}: {f.version}" for f in files)
    if not force:
        raise BumpError(
            "version mismatch across files — refusing to bump:\n  " + detail
            + "\nFix the files to agree, or re-run with --force "
            "(uses the first file's version)."
        )
    print(f"warning: versions disagree ({detail}); using {files[0].version}")
    return files[0].version


def _print_json(payload: dict) -> None:
    print(json.dumps(payload, indent=2))


# ------------------------------------------------------------ commands ---
def cmd_show(args, directory: Path) -> int:
    files = _resolve_files(directory, args.files)
    current = _agree_on_version(files, force=True)
    if args.json:
        _print_json(
            {
                "version": str(current),
                "files": [
                    {"path": str(f.path), "kind": f.kind, "version": str(f.version)}
                    for f in files
                ],
            }
        )
    else:
        for f in files:
            print(f"{f.path}: {f.version}")
        if len(files) > 1:
            print(f"current version: {current}")
    return 0


def cmd_check(args, directory: Path) -> int:
    files = _resolve_files(directory, args.files)
    versions = {str(f.version) for f in files}
    if len(versions) == 1:
        print(f"OK: all {len(files)} file(s) agree on {files[0].version}")
        return 0
    print("MISMATCH:")
    for f in files:
        print(f"  {f.path}: {f.version}")
    return 1


def _do_bump(args, directory: Path, new: SemVer) -> int:
    files = _resolve_files(directory, args.files)
    current = _agree_on_version(files, args.force)

    if new == current:
        raise BumpError(f"already at {new} — nothing to do")

    result = {
        "old": str(current),
        "new": str(new),
        "files": [str(f.path) for f in files],
        "dry_run": args.dry_run,
        "committed": False,
        "tagged": None,
    }

    if args.dry_run:
        if args.json:
            _print_json(result)
        else:
            print(f"would bump {current} -> {new}")
            for f in files:
                print(f"  {f.path} ({f.kind})")
            if args.commit:
                print(f"would commit: {args.message.format(version=new)}")
            if args.tag:
                print(f"would tag: {args.tag_prefix}{new}")
        return 0

    if (args.commit or args.tag) and not _git_available(directory):
        raise BumpError(
            "--commit/--tag need a git repository, "
            "but this directory is not one"
        )
    if (args.commit or args.tag) and _git_is_dirty(directory) and not args.allow_dirty:
        raise BumpError(
            "working tree is dirty — commit or stash your changes first, "
            "or re-run with --allow-dirty"
        )

    changed = []
    for f in files:
        if write_version(f.path, current, new):
            changed.append(f.path)
    if not changed:
        raise BumpError("no file was updated (version string not found?)")

    if args.commit:
        message = args.message.format(version=new)
        _git_commit(directory, message, changed)
        result["committed"] = True
    if args.tag:
        tag = f"{args.tag_prefix}{new}"
        _git_tag(directory, tag)
        result["tagged"] = tag

    if args.json:
        _print_json(result)
    else:
        print(f"bumped {current} -> {new}")
        for p in changed:
            print(f"  updated {p}")
        if result["committed"]:
            print(f"  committed: {args.message.format(version=new)}")
        if result["tagged"]:
            print(f"  tagged: {result['tagged']}")
    return 0


def cmd_bump(args, directory: Path) -> int:
    new = bump(str(_agree_on_version(_resolve_files(directory, args.files), args.force)), args.kind, args.pre)
    return _do_bump(args, directory, new)


def cmd_set(args, directory: Path) -> int:
    try:
        new = SemVer.parse(args.version)
    except SemVerError as exc:
        raise BumpError(str(exc)) from None
    return _do_bump(args, directory, new)


# ----------------------------------------------------------------- main --
def build_parser() -> argparse.ArgumentParser:
    # Shared options, accepted both before and after the subcommand
    # (``bump patch --dry-run`` reads as naturally as ``bump --dry-run patch``).
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--files", nargs="+", metavar="FILE",
        help="explicit version file(s) instead of auto-detection",
    )
    common.add_argument(
        "--force", action="store_true",
        help="proceed when files disagree (uses the first file's version)",
    )
    common.add_argument(
        "--dry-run", action="store_true",
        help="show what would change without touching anything",
    )
    common.add_argument(
        "--json", action="store_true",
        help="machine-readable JSON output",
    )
    common.add_argument(
        "--commit", action="store_true",
        help="git commit the version change",
    )
    common.add_argument(
        "--tag", action="store_true",
        help="git tag the new version (implies a clean tree check)",
    )
    common.add_argument(
        "--tag-prefix", default="v", metavar="PREFIX",
        help="prefix for the git tag (default: 'v', use '' for none)",
    )
    common.add_argument(
        "--message", default="chore(release): {version}", metavar="MSG",
        help="commit message template; {version} is replaced "
             "(default: 'chore(release): {version}')",
    )
    common.add_argument(
        "--allow-dirty", action="store_true",
        help="allow --commit/--tag with uncommitted changes",
    )
    common.add_argument(
        "--pre", default="rc", metavar="TAG",
        help="prerelease tag for 'prerelease' bumps (default: rc)",
    )

    p = argparse.ArgumentParser(
        prog="bump",
        description=(
            "Bump Semantic Versions across your project files — "
            "pyproject.toml, package.json, Cargo.toml, VERSION, "
            "setup.cfg, __init__.py — with optional git commit + tag."
        ),
        parents=[common],
    )
    p.add_argument("--version", action="version", version=f"bump {_TOOL_VERSION}")

    sub = p.add_subparsers(dest="command")

    show = sub.add_parser("show", help="print the current version", parents=[common])
    show.set_defaults(func=cmd_show)

    check = sub.add_parser(
        "check",
        help="exit 1 if version files disagree (for CI)",
        parents=[common],
    )
    check.set_defaults(func=cmd_check)

    for kind in KINDS:
        sp = sub.add_parser(kind, help=f"bump the {kind} version", parents=[common])
        sp.set_defaults(func=cmd_bump, kind=kind)

    setp = sub.add_parser("set", help="set an explicit version", parents=[common])
    setp.add_argument("version", help="new version, e.g. 2.0.0-rc.1")
    setp.set_defaults(func=cmd_set)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    directory = Path.cwd()

    if not getattr(args, "func", None):
        parser.print_help()
        return 2

    try:
        return args.func(args, directory)
    except BumpError as exc:
        print(f"bump: error: {exc}", file=sys.stderr)
        return 1
    except SemVerError as exc:
        print(f"bump: error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
