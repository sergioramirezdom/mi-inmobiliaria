"""Keep secrets out of every log sink (issue #55).

The Telegram Bot API carries the bot token in the URL path
(``https://api.telegram.org/bot<TOKEN>/sendMessage``), so anything that logs a
URL or an exception message carrying it (httpx logs each request at INFO)
leaks it into ``logs/scheduler.log``, the CI log artifacts and the in-app log
viewer. :func:`install_log_redaction` masks secrets in every record at
creation time, so no handler (console, file, ``capture_logs``, test capture)
ever sees them, and quiets httpx/httpcore as a second layer.
"""
from __future__ import annotations

import logging
import os
import re
import traceback

REDACTED = "<redacted>"

# ``bot<digits>:<token>`` as embedded in Bot API URLs (":" may be %3A-encoded).
_BOT_URL_TOKEN = re.compile(r"(bot)\d+(?::|%3A)[A-Za-z0-9_-]+", re.IGNORECASE)
# A bare token outside a URL: "<bot id>:<35-char secret>". Deliberately narrow
# (long secret part) so timestamps and ratios are never touched.
_BARE_TOKEN = re.compile(r"\b\d{6,}(?::|%3A)[A-Za-z0-9_-]{20,}")
# Password of a ``scheme://user:password@host`` URL (e.g. DATABASE_URL).
_URL_PASSWORD = re.compile(r"(://[^/\s:@]+:)[^@/\s]+(?=@)")

# Environment variables whose exact value is masked wherever it appears.
_SECRET_ENV_VARS = ("TELEGRAM_TOKEN",)
_MIN_SECRET_LENGTH = 8  # never mask trivially short values like "1" or "test"

# Marker on the installed factory, so repeated (or duplicated-module) installs
# never stack.
_MARK = "_redacts_secrets"


def redact(text: str) -> str:
    """Return ``text`` with tokens and URL passwords masked."""
    text = _BOT_URL_TOKEN.sub(rf"\1{REDACTED}", text)
    text = _BARE_TOKEN.sub(REDACTED, text)
    text = _URL_PASSWORD.sub(r"\1***", text)
    for name in _SECRET_ENV_VARS:
        secret = os.environ.get(name, "")
        if len(secret) >= _MIN_SECRET_LENGTH:
            text = text.replace(secret, REDACTED)
    return text


def _redact_record(record: logging.LogRecord) -> None:
    try:
        message = record.getMessage()
    except Exception:
        # Malformed format/args: mask each part, so even the fallback error
        # output of the logging module cannot leak.
        record.msg = redact(str(record.msg))
        if isinstance(record.args, tuple):
            record.args = tuple(redact(str(a)) for a in record.args)
        elif record.args:
            record.args = redact(str(record.args))
    else:
        masked = redact(message)
        if masked != message:
            record.msg, record.args = masked, None

    if record.exc_info and record.exc_info[0] is not None and not record.exc_text:
        rendered = "".join(traceback.format_exception(*record.exc_info)).rstrip("\n")
        masked = redact(rendered)
        if masked != rendered:
            record.exc_text = masked  # formatters prefer this over exc_info
    if isinstance(record.stack_info, str):
        record.stack_info = redact(record.stack_info)


def install_log_redaction() -> None:
    """Mask secrets in all log records of this process (idempotent).

    Call it once, before configuring handlers. It also raises ``httpx`` and
    ``httpcore`` to WARNING: their INFO request lines carry the full URL and
    add nothing the scrapers do not already log.
    """
    for name in ("httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)

    previous = logging.getLogRecordFactory()
    if getattr(previous, _MARK, False):
        return

    def factory(*args, **kwargs) -> logging.LogRecord:
        record = previous(*args, **kwargs)
        _redact_record(record)
        return record

    setattr(factory, _MARK, True)
    logging.setLogRecordFactory(factory)
