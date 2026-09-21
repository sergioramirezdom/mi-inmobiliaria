"""Exit-code contract of scripts/scheduler.py (issue #50).

GitHub Actions only goes red when the process exits non-zero, so a failed
fuente or an unreachable database must not end in exit code 0. The script is
run in a subprocess (it configures logging and a log file at import time).
DATABASE_URL always points at a closed local port: nothing real is contacted.
"""
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
SCRIPT = ROOT / "scripts" / "scheduler.py"
UNREACHABLE_DB = "postgresql://nobody:nothing@127.0.0.1:1/none"


def _run(tmp_path, argv, prelude=""):
    (tmp_path / "logs").mkdir(exist_ok=True)
    wrapper = textwrap.dedent(
        f"""
        import runpy, sys
        sys.path.insert(0, {str(ROOT)!r})
        sys.path.insert(0, {str(ROOT / "app")!r})
        {textwrap.indent(textwrap.dedent(prelude), "        ").strip()}
        sys.argv = [{str(SCRIPT)!r}] + {argv!r}
        runpy.run_path({str(SCRIPT)!r}, run_name="__main__")
        """
    )
    env = {**os.environ, "DATABASE_URL": UNREACHABLE_DB}
    env.pop("TELEGRAM_TOKEN", None)
    return subprocess.run(
        [sys.executable, "-c", wrapper],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=120,
    )


def _stub(method, *, failed=(), fatal=None):
    return f"""
        from app.scraper.run_stats import RunSummary
        from app.scraper.scheduler import ScraperScheduler

        async def _stub(self, *a, **k):
            return RunSummary(failed=list({list(failed)!r}), fatal_error={fatal!r})

        ScraperScheduler.{method} = _stub
    """


@pytest.mark.parametrize("argv", [["--once", "--force"], ["--once"], ["--check-sold"]])
def test_unreachable_database_exits_non_zero(tmp_path, argv):
    result = _run(tmp_path, argv)

    assert result.returncode == 1, result.stderr[-2000:]


@pytest.mark.parametrize(
    "argv,method",
    [
        (["--once", "--force"], "force_scrape_all"),
        (["--once"], "check_and_scrape"),
        (["--check-sold"], "run_sold_check"),
    ],
)
def test_failed_fuente_exits_non_zero(tmp_path, argv, method):
    result = _run(tmp_path, argv, _stub(method, failed=["A: boom"]))

    assert result.returncode == 1, result.stderr[-2000:]


@pytest.mark.parametrize(
    "argv,method",
    [
        (["--once", "--force"], "force_scrape_all"),
        (["--once"], "check_and_scrape"),
        (["--check-sold"], "run_sold_check"),
    ],
)
def test_clean_run_exits_zero(tmp_path, argv, method):
    result = _run(tmp_path, argv, _stub(method))

    assert result.returncode == 0, result.stderr[-2000:]
