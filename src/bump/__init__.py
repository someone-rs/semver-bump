"""semver-bump: bump Semantic Versions across your project files.

A small, stdlib-only library + CLI that finds the version in your
project (pyproject.toml, package.json, Cargo.toml, VERSION, setup.cfg,
__init__.py), bumps it according to SemVer 2.0.0, and — if you ask —
commits and tags the release in git.
"""

__version__ = "1.0.0"
__all__ = ["__version__"]
