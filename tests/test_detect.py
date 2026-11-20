"""Tests for bump.detect: finding and rewriting versions in files."""

from pathlib import Path

import pytest

from bump.detect import detect, read_version, write_version
from bump.semver import SemVer, SemVerError


def test_pyproject_project_section(tmp_path):
    p = tmp_path / "pyproject.toml"
    p.write_text('[build-system]\nrequires = ["setuptools"]\n\n[project]\nname = "demo"\nversion = "1.2.3"\n')
    vf = read_version(p)
    assert str(vf.version) == "1.2.3"
    assert vf.kind == "pyproject"
    assert write_version(p, vf.version, SemVer.parse("1.2.4"))
    assert 'version = "1.2.4"' in p.read_text()
    assert 'name = "demo"' in p.read_text()  # untouched


def test_pyproject_poetry_section(tmp_path):
    p = tmp_path / "pyproject.toml"
    p.write_text('[tool.poetry]\nname = "demo"\nversion = "0.1.0"\n')
    assert str(read_version(p).version) == "0.1.0"
    assert write_version(p, SemVer.parse("0.1.0"), SemVer.parse("0.2.0"))
    assert 'version = "0.2.0"' in p.read_text()


def test_pyproject_single_quotes_preserved(tmp_path):
    p = tmp_path / "pyproject.toml"
    p.write_text("[project]\nversion = '1.0.0'\n")
    assert write_version(p, SemVer.parse("1.0.0"), SemVer.parse("2.0.0"))
    assert "version = '2.0.0'" in p.read_text()


def test_package_json(tmp_path):
    p = tmp_path / "package.json"
    p.write_text('{\n  "name": "demo",\n  "version": "3.4.5",\n  "private": true\n}\n')
    vf = read_version(p)
    assert vf.kind == "package.json" and str(vf.version) == "3.4.5"
    assert write_version(p, vf.version, SemVer.parse("3.4.6"))
    assert '"version": "3.4.6"' in p.read_text()
    assert '"private": true' in p.read_text()


def test_package_json_minified_single_line(tmp_path):
    p = tmp_path / "package.json"
    p.write_text('{"name":"demo","private":true,"version":"3.4.5"}')
    assert str(read_version(p).version) == "3.4.5"
    assert write_version(p, SemVer.parse("3.4.5"), SemVer.parse("3.4.6"))
    assert p.read_text() == '{"name":"demo","private":true,"version":"3.4.6"}'


def test_cargo_toml(tmp_path):
    p = tmp_path / "Cargo.toml"
    p.write_text('[package]\nname = "demo"\nversion = "0.3.0"\nedition = "2021"\n\n[dependencies]\nfoo = "1.0"\n')
    assert str(read_version(p).version) == "0.3.0"
    assert write_version(p, SemVer.parse("0.3.0"), SemVer.parse("0.4.0"))
    text = p.read_text()
    assert 'version = "0.4.0"' in text
    assert 'foo = "1.0"' in text


def test_version_file(tmp_path):
    p = tmp_path / "VERSION"
    p.write_text("1.0.0\n")
    assert str(read_version(p).version) == "1.0.0"
    assert write_version(p, SemVer.parse("1.0.0"), SemVer.parse("1.0.1"))
    assert p.read_text() == "1.0.1\n"


def test_setup_cfg(tmp_path):
    p = tmp_path / "setup.cfg"
    p.write_text("[metadata]\nname = demo\nversion = 2.1.0\n")
    assert str(read_version(p).version) == "2.1.0"
    assert write_version(p, SemVer.parse("2.1.0"), SemVer.parse("2.1.1"))
    assert "version = 2.1.1" in p.read_text()


def test_init_py(tmp_path):
    p = tmp_path / "__init__.py"
    p.write_text('"""Demo."""\n\n__version__ = "0.0.9"\n')
    assert str(read_version(p).version) == "0.0.9"
    assert write_version(p, SemVer.parse("0.0.9"), SemVer.parse("0.1.0"))
    assert '__version__ = "0.1.0"' in p.read_text()


def test_no_version_raises(tmp_path):
    p = tmp_path / "pyproject.toml"
    p.write_text('[project]\nname = "demo"\n')
    with pytest.raises(SemVerError):
        read_version(p)


def test_invalid_version_ignored(tmp_path):
    p = tmp_path / "VERSION"
    p.write_text("not-a-version\n")
    with pytest.raises(SemVerError):
        read_version(p)


def test_detect_prefers_standard_files(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "1.0.0"\n')
    (tmp_path / "package.json").write_text('{"version": "1.0.0"}')
    found = detect(tmp_path)
    kinds = [f.kind for f in found]
    assert kinds == ["pyproject", "package.json"]


def test_detect_finds_src_layout_init(tmp_path):
    pkg = tmp_path / "src" / "mypkg"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text('__version__ = "4.5.6"\n')
    found = detect(tmp_path)
    assert len(found) == 1
    assert found[0].kind == "__init__"
    assert str(found[0].version) == "4.5.6"


def test_write_version_wrong_old_returns_false(tmp_path):
    p = tmp_path / "VERSION"
    p.write_text("1.0.0\n")
    assert not write_version(p, SemVer.parse("9.9.9"), SemVer.parse("1.0.1"))
    assert p.read_text() == "1.0.0\n"
