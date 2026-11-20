"""End-to-end CLI tests for bump (run in isolated temp dirs)."""

import json
import os
import subprocess
from pathlib import Path

import pytest

from bump.cli import main


@pytest.fixture
def project(tmp_path, monkeypatch):
    """A minimal project dir; tests run with cwd pointed at it."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "1.2.3"\n'
    )
    monkeypatch.chdir(tmp_path)
    return tmp_path


def run_cli(*args, cwd):
    """Run main() with a faked argv; returns (exit_code, stdout, stderr)."""
    import io
    import sys
    from contextlib import redirect_stdout, redirect_stderr

    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main(list(args))
    return code, out.getvalue(), err.getvalue()


def test_show(project):
    code, out, _ = run_cli("show", cwd=project)
    assert code == 0
    assert "1.2.3" in out


def test_show_json(project):
    code, out, _ = run_cli("show", "--json", cwd=project)
    assert code == 0
    data = json.loads(out)
    assert data["version"] == "1.2.3"
    assert data["files"][0]["kind"] == "pyproject"


def test_check_agrees(project):
    code, out, _ = run_cli("check", cwd=project)
    assert code == 0 and "OK" in out


def test_check_mismatch(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "1.0.0"\n')
    (tmp_path / "package.json").write_text('{"version": "2.0.0"}')
    monkeypatch.chdir(tmp_path)
    code, out, _ = run_cli("check", cwd=tmp_path)
    assert code == 1 and "MISMATCH" in out


def test_bump_patch_updates_file(project):
    code, out, _ = run_cli("patch", cwd=project)
    assert code == 0
    assert "1.2.3 -> 1.2.4" in out
    assert 'version = "1.2.4"' in (project / "pyproject.toml").read_text()


def test_bump_minor_and_major(project):
    assert run_cli("minor", cwd=project)[0] == 0
    assert 'version = "1.3.0"' in (project / "pyproject.toml").read_text()
    assert run_cli("major", cwd=project)[0] == 0
    assert 'version = "2.0.0"' in (project / "pyproject.toml").read_text()


def test_bump_prerelease_flow(project):
    assert run_cli("prerelease", cwd=project)[0] == 0
    assert 'version = "1.2.4-rc.1"' in (project / "pyproject.toml").read_text()
    assert run_cli("prerelease", cwd=project)[0] == 0
    assert 'version = "1.2.4-rc.2"' in (project / "pyproject.toml").read_text()
    assert run_cli("release", cwd=project)[0] == 0
    assert 'version = "1.2.4"' in (project / "pyproject.toml").read_text()


def test_bump_dry_run_changes_nothing(project):
    code, out, _ = run_cli("patch", "--dry-run", cwd=project)
    assert code == 0 and "would bump 1.2.3 -> 1.2.4" in out
    assert 'version = "1.2.3"' in (project / "pyproject.toml").read_text()


def test_set_explicit_version(project):
    code, out, _ = run_cli("set", "2.0.0-rc.1", cwd=project)
    assert code == 0
    assert 'version = "2.0.0-rc.1"' in (project / "pyproject.toml").read_text()


def test_set_invalid_version(project):
    code, _, err = run_cli("set", "banana", cwd=project)
    assert code == 1
    assert "not a valid Semantic Version" in err


def test_set_same_version_is_noop_error(project):
    code, _, err = run_cli("set", "1.2.3", cwd=project)
    assert code == 1 and "already at" in err


def test_bump_mismatch_refuses_without_force(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "1.0.0"\n')
    (tmp_path / "package.json").write_text('{"version": "2.0.0"}')
    monkeypatch.chdir(tmp_path)
    code, _, err = run_cli("patch", cwd=tmp_path)
    assert code == 1 and "mismatch" in err
    # --force proceeds, using the first file's version
    code, out, _ = run_cli("patch", "--force", cwd=tmp_path)
    assert code == 0 and "1.0.0 -> 1.0.1" in out


def test_no_version_found(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    code, _, err = run_cli("show", cwd=tmp_path)
    assert code == 1 and "no version found" in err


def test_no_subcommand_is_usage_error(project):
    code, _, _ = run_cli(cwd=project)
    assert code == 2


def test_bump_multiple_files_stay_in_sync(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "1.0.0"\n')
    (tmp_path / "VERSION").write_text("1.0.0\n")
    monkeypatch.chdir(tmp_path)
    assert run_cli("minor", cwd=tmp_path)[0] == 0
    assert 'version = "1.1.0"' in (tmp_path / "pyproject.toml").read_text()
    assert (tmp_path / "VERSION").read_text() == "1.1.0\n"


def test_commit_and_tag(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "1.0.0"\n')
    monkeypatch.chdir(tmp_path)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=tmp_path, check=True)
    code, out, _ = run_cli("patch", "--commit", "--tag", cwd=tmp_path)
    assert code == 0
    assert "committed" in out and "tagged: v1.0.1" in out
    log = subprocess.run(
        ["git", "log", "--oneline", "-1"], cwd=tmp_path,
        capture_output=True, text=True, check=True,
    ).stdout
    assert "1.0.1" in log
    tags = subprocess.run(
        ["git", "tag"], cwd=tmp_path, capture_output=True, text=True, check=True,
    ).stdout
    assert "v1.0.1" in tags


def test_commit_refuses_dirty_tree(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "1.0.0"\n')
    (tmp_path / "unrelated.txt").write_text("dirty\n")
    monkeypatch.chdir(tmp_path)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=tmp_path, check=True)
    (tmp_path / "unrelated.txt").write_text("changed\n")
    code, _, err = run_cli("patch", "--commit", cwd=tmp_path)
    assert code == 1 and "dirty" in err
    # --allow-dirty proceeds
    code, _, _ = run_cli("patch", "--commit", "--allow-dirty", cwd=tmp_path)
    assert code == 0


def test_explicit_files_flag(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "1.0.0"\n')
    (tmp_path / "VERSION").write_text("9.9.9\n")
    monkeypatch.chdir(tmp_path)
    code, out, _ = run_cli("patch", "--files", "pyproject.toml", cwd=tmp_path)
    assert code == 0 and "1.0.0 -> 1.0.1" in out
    assert (tmp_path / "VERSION").read_text() == "9.9.9\n"  # untouched


def test_bump_binary_entry_point(tmp_path, monkeypatch):
    """The installed `bump` console script works end to end."""
    import shutil
    import sysconfig

    venv_bin = Path(sysconfig.get_path("scripts"))
    bump_bin = shutil.which("bump") or str(venv_bin / "bump")
    if not Path(bump_bin).exists():
        pytest.skip("bump console script not installed in this env")
    (tmp_path / "VERSION").write_text("0.1.0\n")
    r = subprocess.run(
        [bump_bin, "minor"], cwd=tmp_path, capture_output=True, text=True,
    )
    assert r.returncode == 0
    assert "0.1.0 -> 0.2.0" in r.stdout
    assert (tmp_path / "VERSION").read_text() == "0.2.0\n"
