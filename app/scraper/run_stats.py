"""Shared normalisation of scrape-run stats and the scheduler's run summary.

`ScraperRunner.run_paginated_scraper` reports a whole-run failure (network
down, unknown scraper type, layout change...) as ``errores=0`` plus an
``error`` string. Every path that writes a run-log row (the scheduler and the
manual run) goes through `normalize_run_stats`, so a failed run is recorded
as failing with its cause instead of looking clean.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

MAX_ERROR_CHARS = 500


def normalize_run_stats(stats: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy of ``stats`` where a whole-run failure reads as one.

    With an ``error`` key: ``errores`` is at least 1, ``urls_encontradas`` is
    None (a run that crashed parsed nothing; 0 would read as EMPTY, not
    FAILING) and the truncated text is exposed as ``error_mensaje``.
    """
    normalized = dict(stats)
    error = normalized.get("error")
    if error:
        normalized["errores"] = max(int(normalized.get("errores") or 0), 1)
        normalized["urls_encontradas"] = None
        normalized["error_mensaje"] = str(error)[:MAX_ERROR_CHARS]
    return normalized


@dataclass
class RunSummary:
    """Outcome of one scheduler cycle, used to pick the process exit code."""

    failed: List[str] = field(default_factory=list)  # "<fuente>: <error>"
    fatal_error: Optional[str] = None  # top-level exception (e.g. DB unreachable)

    @property
    def ok(self) -> bool:
        return not self.failed and not self.fatal_error
