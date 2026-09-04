"""Streamlit-free per-scraper fixture test runner (slice S7).

The admin UI lets an operator run ``tests/test_<name>_scraper.py`` for a chosen
scraper by shelling out to ``pytest`` via ``subprocess`` (never in-process
``pytest.main()`` — Streamlit's ScriptRunner thread has a live asyncio loop and
a mutated ``sys.path``, and repeated in-process collection pollutes import
state). The result is surfaced to the operator: pass shows the pytest summary,
failure shows the captured stdout/stderr.

If ``pytest`` or the ``tests/`` tree is absent in the deployment (Streamlit
Cloud ships neither unless ``requirements.txt`` names them), the control must
degrade to a clear message and spawn nothing.

Design D4 pins the exact invocation::

    subprocess.run(
        [sys.executable, "-m", "pytest", *files, "-q", "--no-header",
         "-p", "no:cacheprovider"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=180,
    )

with ``shell=False`` (default) and ``sys.executable`` — never ``"pytest"`` from
``PATH``. Every element of ``files`` is a repo-relative path produced by our own
glob under ``tests/`` — never operator text.

This module has no UI-framework dependency and no database import.
"""

from __future__ import annotations

import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional

# app/admin/test_runner.py -> parents[0]=admin, [1]=app, [2]=repo root
# (repo root is where pytest.ini lives; the test files do their own
# sys.path.insert, so the subprocess cwd must be the repo root).
REPO_ROOT = Path(__file__).resolve().parents[2]


def _tests_dir() -> Path:
    """Repo ``tests/`` directory, resolved against the current ``REPO_ROOT``
    (indirection keeps it monkeypatchable in unit tests)."""
    return REPO_ROOT / "tests"

# The one scraper whose fixture file name does not match its detail_scraper_type
# key: a fuente configured with detail_scraper_type "puerto" is tested by
# tests/test_puerto_inmobiliaria_scraper.py.
TEST_FILE_ALIASES: Dict[str, str] = {"puerto": "puerto_inmobiliaria"}

# Probe / run timeouts (seconds).
PROBE_TIMEOUT = 15
RUN_TIMEOUT = 180

_SAFE_KEY = re.compile(r"^[a-z0-9_]+$")
_SUMMARY = re.compile(r"\d+\s+(passed|failed|error|errors|skipped|deselected|xfailed)")

_UNAVAILABLE_MSG = "pytest/tests no disponibles en este despliegue"

Runner = Callable[..., "subprocess.CompletedProcess"]


@dataclass(frozen=True)
class TestRunResult:
    """Outcome of one per-scraper fixture test run.

    ``ran`` is ``False`` when nothing was executed (pytest unavailable, no
    fixture file for the scraper, or an unsafe key). ``passed`` is ``rc == 0``.
    """

    __test__ = False  # keep pytest from collecting this as a test class

    ran: bool
    passed: bool
    message: str
    returncode: Optional[int] = None
    stdout: str = ""
    stderr: str = ""
    duration_s: float = 0.0
    files: List[str] = field(default_factory=list)


def _relative_tests_glob(name: str) -> List[str]:
    """Repo-relative ``tests/`` paths for a scraper name, existing only.

    The project convention is ``tests/test_<name>_scraper.py``; when that exact
    file exists it is the sole result. Only when it does not exist do we fall
    back to the broader ``tests/test_<name>_*.py`` glob.
    """
    tests_dir = _tests_dir()
    scraper_file = tests_dir / f"test_{name}_scraper.py"
    if scraper_file.is_file():
        return [f"tests/test_{name}_scraper.py"]
    return [
        f"tests/{path.name}"
        for path in sorted(tests_dir.glob(f"test_{name}_*.py"))
        if path.is_file()
    ]


def discover_test_files(scraper_key: Optional[str]) -> List[str]:
    """Resolve a scraper key to its existing fixture test file(s).

    Applies :data:`TEST_FILE_ALIASES`, then globs ``tests/test_<key>_*.py`` and
    ``tests/test_<key>_scraper.py``. An empty / unknown / unsafe key (anything
    outside ``[a-z0-9_]``, e.g. a ``../scripts`` path-traversal attempt) yields
    ``[]`` so no subprocess is ever spawned for it.
    """
    if not scraper_key:
        return []
    key = TEST_FILE_ALIASES.get(scraper_key, scraper_key)
    if not _SAFE_KEY.match(key):
        return []
    return _relative_tests_glob(key)


def available_scraper_tests() -> Dict[str, List[str]]:
    """Map every scraper key that has fixture tests to its test file(s).

    Built by globbing ``tests/test_*_scraper.py`` on disk, so only real files
    appear. Each :data:`TEST_FILE_ALIASES` entry is added as an extra key
    pointing at the aliased scraper's files.
    """
    mapping: Dict[str, List[str]] = {}
    tests_dir = _tests_dir()
    if not tests_dir.is_dir():
        return mapping
    for path in sorted(tests_dir.glob("test_*_scraper.py")):
        if not path.is_file():
            continue
        name = path.name[len("test_") : -len("_scraper.py")]
        mapping[name] = [f"tests/{path.name}"]
    for alias, target in TEST_FILE_ALIASES.items():
        if target in mapping:
            mapping[alias] = list(mapping[target])
    return mapping


def pytest_available(runner: Runner = subprocess.run) -> bool:
    """True when ``python -m pytest --version`` exits 0 and ``tests/`` exists."""
    if not _tests_dir().is_dir():
        return False
    try:
        proc = runner(
            [sys.executable, "-m", "pytest", "--version"],
            capture_output=True,
            text=True,
            timeout=PROBE_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError, ValueError):
        return False
    return getattr(proc, "returncode", 1) == 0


def _summary_line(stdout: str) -> Optional[str]:
    """Last pytest summary-ish line from stdout (e.g. ``8 passed in 2.1s``)."""
    for line in reversed(stdout.splitlines()):
        cleaned = line.strip().strip("=").strip()
        if cleaned and _SUMMARY.search(cleaned):
            return cleaned
    return None


def run_scraper_tests(
    scraper_key: str,
    *,
    runner: Runner = subprocess.run,
) -> TestRunResult:
    """Run the fixture test file(s) for ``scraper_key`` in a subprocess.

    Returns a :class:`TestRunResult`. Never raises for a test failure or a
    timeout — both are reported in the result. When ``pytest`` / ``tests/`` are
    absent, or the scraper has no fixture file, nothing is spawned and
    ``ran=False``.
    """
    files = discover_test_files(scraper_key)
    if not files:
        return TestRunResult(
            ran=False,
            passed=False,
            message="sin tests de fixtures para este scraper",
            files=[],
        )

    if not pytest_available(runner=runner):
        return TestRunResult(
            ran=False, passed=False, message=_UNAVAILABLE_MSG, files=files
        )

    cmd = [
        sys.executable,
        "-m",
        "pytest",
        *files,
        "-q",
        "--no-header",
        "-p",
        "no:cacheprovider",
    ]
    started = time.monotonic()
    try:
        proc = runner(
            cmd,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=RUN_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return TestRunResult(
            ran=True,
            passed=False,
            message=f"timeout tras {RUN_TIMEOUT}s",
            returncode=None,
            duration_s=round(time.monotonic() - started, 3),
            files=files,
        )

    duration = round(time.monotonic() - started, 3)
    stdout = getattr(proc, "stdout", "") or ""
    stderr = getattr(proc, "stderr", "") or ""
    rc = getattr(proc, "returncode", 1)
    summary = _summary_line(stdout)
    message = summary or (
        "tests OK" if rc == 0 else f"pytest terminó con código {rc}"
    )
    return TestRunResult(
        ran=True,
        passed=rc == 0,
        message=message,
        returncode=rc,
        stdout=stdout,
        stderr=stderr,
        duration_s=duration,
        files=files,
    )
