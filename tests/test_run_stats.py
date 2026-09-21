"""Tests for the shared whole-run failure normalisation (issue #50).

`run_paginated_scraper` reports a whole-run failure as ``errores=0`` plus an
``error`` string; both the scheduler and the manual-run path must turn that
into a failing run-log row through the same helper.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from scraper.run_stats import MAX_ERROR_CHARS, RunSummary, normalize_run_stats


def test_error_forces_at_least_one_errores_and_clears_encontradas():
    stats = normalize_run_stats(
        {"errores": 0, "urls_encontradas": 0, "error": "network down"}
    )

    assert stats["errores"] == 1
    assert stats["urls_encontradas"] is None
    assert stats["error_mensaje"] == "network down"


def test_error_keeps_a_higher_errores_count():
    stats = normalize_run_stats({"errores": 4, "error": "boom"})

    assert stats["errores"] == 4


def test_clean_stats_are_left_untouched():
    original = {"nuevas": 2, "errores": 0, "urls_encontradas": 9}

    stats = normalize_run_stats(original)

    assert stats["errores"] == 0
    assert stats["urls_encontradas"] == 9
    assert stats.get("error_mensaje") is None


def test_error_text_is_truncated():
    stats = normalize_run_stats({"error": "x" * (MAX_ERROR_CHARS + 200)})

    assert len(stats["error_mensaje"]) == MAX_ERROR_CHARS


def test_input_dict_is_not_mutated():
    original = {"errores": 0, "error": "boom"}

    normalize_run_stats(original)

    assert original == {"errores": 0, "error": "boom"}


def test_run_summary_ok_only_without_failures_or_fatal_error():
    assert RunSummary().ok is True
    assert RunSummary(failed=["A: boom"]).ok is False
    assert RunSummary(fatal_error="db down").ok is False
