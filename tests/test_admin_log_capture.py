"""Tests for app/admin/log_capture.py — bounded in-process log capture (slice S6).

Design: sdd/scraper-admin-console/design decision D1 option (b). Manual runs
launched from the Fuentes page capture their own log output in-process with a
bounded ``logging.Handler``; CI (scheduled) runs have no in-app logs. The
capture logic is pure (no Streamlit, no DB) and fully unit-tested here:

  * records emitted inside the ``with`` block are captured as formatted lines,
    in emission order;
  * the buffer is capped at ``MAX_LINES`` — older lines are dropped and a
    truncation marker is prepended;
  * the handler is always detached from the target loggers on exit, including
    when the block body raises;
  * capturing nothing yields an empty list.
"""
import logging
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from admin.log_capture import MAX_LINES, capture_logs  # noqa: E402


def test_captures_records_emitted_inside_the_block_in_order():
    logger = logging.getLogger("scraper.test_capture_order")

    with capture_logs() as cap:
        logger.info("first line")
        logger.warning("second line")
        logger.error("third line")

    lines = cap.lines()
    assert len(lines) == 3
    assert "first line" in lines[0]
    assert "second line" in lines[1]
    assert "third line" in lines[2]
    # levelname is part of the formatted output
    assert "WARNING" in lines[1]


def test_named_loggers_argument_attaches_only_to_those_loggers():
    captured = logging.getLogger("scraper.runner")
    ignored = logging.getLogger("some.other.tree")

    with capture_logs(logger_names=("scraper", "notifications")) as cap:
        captured.info("inside scraper tree")
        ignored.info("outside the requested trees")

    lines = cap.lines()
    assert any("inside scraper tree" in ln for ln in lines)
    assert not any("outside the requested trees" in ln for ln in lines)


def test_buffer_is_capped_at_max_lines_and_prepends_truncation_marker():
    logger = logging.getLogger("scraper.test_capture_truncation")
    overflow = 25

    with capture_logs() as cap:
        for i in range(MAX_LINES + overflow):
            logger.info("line %d", i)

    lines = cap.lines()
    # MAX_LINES retained records + exactly one truncation marker
    assert len(lines) == MAX_LINES + 1
    assert lines[0].startswith("…") and "truncated" in lines[0]
    assert f"{overflow} earlier lines dropped" in lines[0]
    # the most recent lines are the ones kept
    assert f"line {MAX_LINES + overflow - 1}" in lines[-1]
    assert not any("line 0" == ln for ln in lines)


def test_handler_is_detached_after_the_block_even_when_body_raises():
    root = logging.getLogger()
    before = list(root.handlers)

    with pytest.raises(RuntimeError):
        with capture_logs() as cap:
            logging.getLogger("scraper.boom").info("emitted before the raise")
            raise RuntimeError("boom")

    assert list(root.handlers) == before
    assert not any(h is cap for h in root.handlers)
    # lines emitted before the exception are still available
    assert any("emitted before the raise" in ln for ln in cap.lines())


def test_capturing_nothing_yields_empty_list():
    with capture_logs() as cap:
        pass

    assert cap.lines() == []
