# semver-bump

[![PyPI version](https://img.shields.io/pypi/v/semver-bump.svg)](https://pypi.org/project/semver-bump/)
[![Python](https://img.shields.io/pypi/pyversions/semver-bump.svg)](https://pypi.org/project/semver-bump/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Bump Semantic Versions across your whole project with one command — and optionally commit + tag the release.**

`bump` finds the version wherever it lives — `pyproject.toml`, `package.json`, `Cargo.toml`, `VERSION`, `setup.cfg`, or `__version__` in an `__init__.py` — bumps it according to [SemVer 2.0.0](https://semver.org), and keeps every file in sync. No dependencies, no config file, no surprises.

## Install

```bash
pip install semver-bump
```

Python 3.9+, zero dependencies.

## Quickstart

```console
$ cd my-project
$ bump show
pyproject.toml: 1.2.3
package.json: 1.2.3
current version: 1.2.3

$ bump minor
bumped 1.2.3 -> 1.3.0
  updated pyproject.toml
  updated package.json

$ bump prerelease
bumped 1.3.0 -> 1.3.1-rc.1
  updated pyproject.toml
  updated package.json

$ bump release
bumped 1.3.1-rc.1 -> 1.3.1
  updated pyproject.toml
  updated package.json
```

## Commands

| Command | What it does |
|---|---|
| `bump show` | Print the current version (and every file it was found in) |
| `bump check` | Exit 1 if version files disagree — made for CI |
| `bump major` | `1.2.3` → `2.0.0` |
| `bump minor` | `1.2.3` → `1.3.0` |
| `bump patch` | `1.2.3` → `1.2.4`; on a prerelease it just releases it (`1.2.3-rc.1` → `1.2.3`) |
| `bump prerelease` | `1.2.3` → `1.2.4-rc.1`, then `1.2.4-rc.2`, `1.2.4-rc.3`… (`--pre beta` for `beta.1`) |
| `bump release` | Strip the prerelease tag: `1.2.3-rc.1` → `1.2.3` |
| `bump set 2.0.0-rc.1` | Set an explicit version (validated as strict SemVer) |

## Release workflow in one command

```console
$ bump patch --commit --tag
bumped 1.2.3 -> 1.2.4
  updated pyproject.toml
  updated package.json
  committed: chore(release): 1.2.4
  tagged: v1.2.4
```

`--commit` refuses to run on a dirty tree unless you pass `--allow-dirty`. Customize with `--message "release {version}"` and `--tag-prefix ""` (no `v` prefix).

## Options

- `--files pyproject.toml VERSION` — bump only these files instead of auto-detecting
- `--dry-run` — show what would change, touch nothing
- `--force` — proceed when files disagree (uses the first file's version)
- `--json` — machine-readable output for scripts
- `--pre beta` — prerelease tag (default `rc`)

## Safety first

- **Strict SemVer parsing** — `01.2.3`, `v1.2.3`, `1.2` and `1.2.3-01` are all rejected with a plain-language error, exactly as the spec demands.
- **Files must agree** — if `pyproject.toml` says `1.0.0` and `package.json` says `2.0.0`, `bump` stops and shows you the mismatch instead of guessing.
- **Minimal diffs** — only the version string is rewritten; quoting, comments and formatting in your files are left alone.
- **Exit codes** — `0` success, `1` runtime error, `2` usage error. `bump check` in CI fails the build when versions drift apart.

## As a library

```python
from bump.semver import parse, bump

v = parse("1.2.3-rc.1")
print(v < "1.2.3")          # True — prereleases sort before the release
print(bump("1.2.3", "minor"))       # 1.3.0
print(bump("1.2.4-rc.1", "prerelease"))  # 1.2.4-rc.2
```

## License

MIT — see [LICENSE](LICENSE).
