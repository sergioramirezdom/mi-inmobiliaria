"""Bounded in-process log capture for operator-triggered manual runs (slice S6).

Design: sdd/scraper-admin-console/design decision D1 option (b). A manual scrape
or sold-check launched from ``app/pages/1_fuentes.py`` wraps its body in
``capture_logs(...)`` so the log output of that single run can be shown back to
the operator. Scheduled (CI) runs have no in-app logs — the Ejecuciones page
links out to GitHub Actions for those.

This module is deliberately Streamlit-free and DB-free: it is a thin wrapper
around :mod:`logging` and :mod:`collections.deque`, fully unit-testable by
emitting records inside the context manager and asserting the captured lines.
"""
from __future__ import annotations

import logging
from collections import deque
from contextlib import contextmanager
from typing import Iterator, Optional, Sequence

# Hard cap on retained formatted log lines. Past this, only the most recent
# ``MAX_LINES`` lines are kept and a marker line is prepended by ``lines()``.
MAX_LINES = 500

# When the caller passes no explicit names, attach to the root logger ("") so
# every record at ``level`` and above is captured regardless of which module
# logger emitted it (the scrapers use ``logging.getLogger(__name__)`` and one
# base class logs under its own class name, so a single root attach is the
# simplest complete choice).
DEFAULT_LOGGER_NAMES: tuple[str, ...] = ("",)

_LINE_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class BoundedLogCapture(logging.Handler):
    """A ``logging.Handler`` that retains at most ``max_lines`` formatted records.

    Once the cap is reached each further record evicts the oldest retained line;
    :meth:`lines` then returns the retained tail with a single leading
    ``"… (truncated, N earlier lines dropped)"`` marker.
    """

    def __init__(self, max_lines: int = MAX_LINES, level: int = logging.INFO) -> None:
        super().__init__(level=level)
        self.max_lines = max(1, int(max_lines))
        self._buffer: "deque[str]" = deque(maxlen=self.max_lines)
        self._dropped = 0
        self.setFormatter(logging.Formatter(_LINE_FORMAT, datefmt=_DATE_FORMAT))

    def emit(self, record: logging.LogRecord) -> None:  # noqa: D102 - Handler API
        try:
            message = self.format(record)
        except Exception:  # pragma: no cover - logging must never raise upward
            self.handleError(record)
            return
        if len(self._buffer) == self._buffer.maxlen:
            self._dropped += 1
        self._buffer.append(message)

    def lines(self) -> list[str]:
        """Return the captured formatted lines as a plain ``list[str]``."""
        out = list(self._buffer)
        if self._dropped:
            out.insert(
                0, f"… (truncated, {self._dropped} earlier lines dropped)"
            )
        return out


@contextmanager
def capture_logs(
    logger_names: Optional[Sequence[str]] = None,
    level: int = logging.INFO,
) -> Iterator[BoundedLogCapture]:
    """Attach a :class:`BoundedLogCapture` to the given loggers for the block.

    ``logger_names=None`` attaches to the root logger, capturing every record at
    ``level`` and above. The handler is ALWAYS detached again on exit, including
    when the ``with`` body raises. Any logger whose effective threshold would
    suppress ``level`` is temporarily lowered and restored on exit.

    Yields the handler; call ``.lines()`` for the captured ``list[str]``.
    """
    names = (
        list(logger_names)
        if logger_names is not None
        else list(DEFAULT_LOGGER_NAMES)
    )
    handler = BoundedLogCapture(level=level)
    loggers = [logging.getLogger(name) for name in names]
    restore: list[tuple[logging.Logger, int]] = []

    for lg in loggers:
        lg.addHandler(handler)
        if lg.level == logging.NOTSET or lg.level > level:
            restore.append((lg, lg.level))
            lg.setLevel(level)

    try:
        yield handler
    finally:
        for lg in loggers:
            lg.removeHandler(handler)
        for lg, previous_level in restore:
            lg.setLevel(previous_level)
        handler.close()


def captured_lines(handler: BoundedLogCapture) -> list[str]:
    """Return the captured formatted lines for ``handler`` as a ``list[str]``."""
    return handler.lines()
