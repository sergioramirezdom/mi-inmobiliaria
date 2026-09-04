"""Tests for app/admin/test_runner.py — Streamlit-free per-scraper fixture test
runner (slice S7).

Spec: sdd/scraper-admin-console/spec — "Per-Scraper Fixture Test Runner"
(Pass surfaced; Fail surfaced with output; Missing tooling in deployment).

Design D4 pins the exact subprocess invocation:
``[sys.executable, "-m", "pytest", *files, "-q", "--no-header", "-p",
"no:cacheprovider"]`` with ``cwd=REPO_ROOT``, ``timeout=180``, ``shell=False``.

Threat matrix (S7): subprocess invocation + documentation-like paths. Every test
here mocks the ``runner`` callable — a real recursive pytest is never spawned.
"""
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from admin import test_runner as tr  # noqa: E402
from admin.test_runner import (  # noqa: E402
    REPO_ROOT,
    TestRunResult,
    available_scraper_tests,
    pytest_available,
    run_scraper_tests,
)


class FakeCompleted:
    """Stand-in for ``subprocess.CompletedProcess``."""

    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class FakeRunner:
    """Configurable stub for ``subprocess.run``.

    Distinguishes the ``pytest --version`` availability probe from the actual
    test-run call and records every invocation for argv assertions.
    """

    def __init__(self, *, version_rc=0, run_result=None, run_exc=None):
        self.calls = []
        self.version_rc = version_rc
        self.run_result = run_result
        self.run_exc = run_exc

    def __call__(self, cmd, **kwargs):
        self.calls.append({"cmd": list(cmd), "kwargs": kwargs})
        if "--version" in cmd:
            return FakeCompleted(returncode=self.version_rc, stdout="pytest 8.0.0")
        if self.run_exc is not None:
            raise self.run_exc
        return self.run_result or FakeCompleted(returncode=0, stdout="1 passed in 0.1s")

    @property
    def run_calls(self):
        return [c for c in self.calls if "--version" not in c["cmd"]]


# ── Discovery ────────────────────────────────────────────────────────────────


def test_available_scraper_tests_maps_existing_fixture_files():
    mapping = available_scraper_tests()

    assert mapping["tular"] == ["tests/test_tular_scraper.py"]
    assert mapping["samper"] == ["tests/test_samper_scraper.py"]
    # only entries whose files really exist on disk are returned
    for files in mapping.values():
        for rel in files:
            assert (REPO_ROOT / rel).is_file()
    assert "does_not_exist" not in mapping


def test_available_scraper_tests_resolves_puerto_alias():
    mapping = available_scraper_tests()

    # a fuente whose detail_scraper_type is "puerto" must resolve to the
    # puerto_inmobiliaria fixture file via the explicit alias
    assert mapping["puerto"] == ["tests/test_puerto_inmobiliaria_scraper.py"]
    assert mapping["puerto_inmobiliaria"] == [
        "tests/test_puerto_inmobiliaria_scraper.py"
    ]


def test_run_scraper_tests_rejects_path_traversal_scraper_key():
    runner = FakeRunner()

    result = run_scraper_tests("../scripts", runner=runner)

    assert result.ran is False
    assert result.files == []
    assert runner.run_calls == []


# ── Command composition (threat: subprocess argv) ────────────────────────────


def test_run_scraper_tests_composes_exact_pytest_command():
    runner = FakeRunner(run_result=FakeCompleted(returncode=0, stdout="3 passed"))

    run_scraper_tests("tular", runner=runner)

    assert len(runner.run_calls) == 1
    call = runner.run_calls[0]
    assert call["cmd"] == [
        sys.executable,
        "-m",
        "pytest",
        "tests/test_tular_scraper.py",
        "-q",
        "--no-header",
        "-p",
        "no:cacheprovider",
    ]
    assert call["kwargs"]["cwd"] == REPO_ROOT
    assert call["kwargs"]["timeout"] == 180
    assert call["kwargs"]["capture_output"] is True
    assert call["kwargs"]["text"] is True
    assert call["kwargs"].get("shell", False) is False


# ── Pass / fail surfacing ───────────────────────────────────────────────────


def test_run_scraper_tests_pass_result_parses_summary():
    runner = FakeRunner(
        run_result=FakeCompleted(returncode=0, stdout="collected 8 items\n\n8 passed in 2.10s\n")
    )

    result = run_scraper_tests("tular", runner=runner)

    assert isinstance(result, TestRunResult)
    assert result.ran is True
    assert result.passed is True
    assert result.returncode == 0
    assert "8 passed" in result.message
    assert result.files == ["tests/test_tular_scraper.py"]


def test_run_scraper_tests_failure_surfaces_output():
    runner = FakeRunner(
        run_result=FakeCompleted(
            returncode=1,
            stdout="F\n\n1 failed, 2 passed in 1.00s\n",
            stderr="AssertionError: boom",
        )
    )

    result = run_scraper_tests("tular", runner=runner)

    assert result.ran is True
    assert result.passed is False
    assert result.returncode == 1
    assert "1 failed" in result.message
    assert "1 failed, 2 passed in 1.00s" in result.stdout
    assert "AssertionError: boom" in result.stderr


def test_run_scraper_tests_unknown_scraper_has_no_files_and_no_spawn():
    runner = FakeRunner()

    result = run_scraper_tests("totally_unknown_scraper", runner=runner)

    assert result.ran is False
    assert result.files == []
    assert runner.run_calls == []


# ── Missing tooling in deployment (threat: no spawn when unavailable) ────────


def test_run_scraper_tests_returns_unavailable_when_pytest_missing():
    runner = FakeRunner(version_rc=1)  # `pytest --version` fails

    result = run_scraper_tests("tular", runner=runner)

    assert result.ran is False
    assert result.passed is False
    assert "no disponibles" in result.message
    assert runner.run_calls == []  # never spawned the real run


def test_pytest_available_true_when_probe_succeeds():
    runner = FakeRunner(version_rc=0)

    assert pytest_available(runner=runner) is True


def test_pytest_available_false_when_probe_nonzero():
    runner = FakeRunner(version_rc=1)

    assert pytest_available(runner=runner) is False


def test_pytest_available_false_when_tests_dir_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(tr, "REPO_ROOT", tmp_path)  # tmp_path has no tests/ dir
    runner = FakeRunner(version_rc=0)

    assert pytest_available(runner=runner) is False


def test_pytest_available_false_on_probe_exception():
    runner = FakeRunner()
    runner.__call__ = None  # force a TypeError when invoked

    def boom(cmd, **kwargs):
        raise FileNotFoundError("python gone")

    assert pytest_available(runner=boom) is False


# ── Timeout handling (threat: TimeoutExpired) ────────────────────────────────


def test_run_scraper_tests_handles_timeout_without_raising():
    runner = FakeRunner(
        run_exc=subprocess.TimeoutExpired(cmd=["pytest"], timeout=180)
    )

    result = run_scraper_tests("tular", runner=runner)

    assert result.ran is True
    assert result.passed is False
    assert result.returncode is None
    assert "timeout" in result.message.lower()
    assert "180" in result.message


# ── Convention: no Streamlit / DB imports ───────────────────────────────────


def test_test_runner_module_has_no_streamlit_import():
    source = (
        Path(__file__).parent.parent / "app" / "admin" / "test_runner.py"
    ).read_text()
    import_lines = [
        ln.strip()
        for ln in source.splitlines()
        if ln.strip().startswith(("import ", "from "))
    ]
    assert not any("streamlit" in ln for ln in import_lines)
    assert not any(ln.startswith("from db") or ln == "import db" for ln in import_lines)
