"""Secret redaction for logs (issue #55).

The Telegram Bot API puts the bot token in the URL path and httpx logs every
request URL at INFO, so the token ended up in ``logs/scheduler.log`` (uploaded
as a CI artifact) and in the in-app log viewer. Every token below is fake.
"""
import logging
import os
import subprocess
import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

import httpx
import pytest
import respx

import logging_setup
import notifications.telegram as telegram_mod
from notifications.telegram import TelegramNotifier

ROOT = Path(__file__).parent.parent
SCRIPT = ROOT / "scripts" / "scheduler.py"

TOKEN = "123456789:AAFakeTokenForTestsOnly_0123456789abcd"
SEND_URL = f"https://api.telegram.org/bot{TOKEN}/sendMessage"


@pytest.fixture(autouse=True)
def isolated_logging_state():
    """Undo what install_log_redaction changes process-wide."""
    factory = logging.getLogRecordFactory()
    levels = {n: logging.getLogger(n).level for n in ("httpx", "httpcore")}
    yield
    logging.setLogRecordFactory(factory)
    for name, level in levels.items():
        logging.getLogger(name).setLevel(level)


# ── redact(): pure text masking ──────────────────────────────────────────────


def test_redact_masks_bot_token_in_url():
    out = logging_setup.redact(f"POST {SEND_URL} 200")

    assert TOKEN not in out
    assert "AAFakeTokenForTestsOnly" not in out
    assert "https://api.telegram.org/bot<redacted>/sendMessage" in out


def test_redact_masks_percent_encoded_and_bare_tokens():
    encoded = "https://x/bot123456789%3AAAFakeTokenForTestsOnly_0123456789abcd/y"

    assert "AAFakeToken" not in logging_setup.redact(encoded)
    assert "AAFakeToken" not in logging_setup.redact(f"token={TOKEN}")


def test_redact_masks_the_configured_token_even_in_an_unusual_shape(monkeypatch):
    monkeypatch.setenv("TELEGRAM_TOKEN", "opaque-secret-value-42")

    assert "opaque-secret" not in logging_setup.redact("using opaque-secret-value-42 now")


def test_redact_masks_database_password_but_keeps_the_rest():
    out = logging_setup.redact("postgresql://user:hunter2pw@db.example.com:5432/app")

    assert "hunter2pw" not in out
    assert out == "postgresql://user:***@db.example.com:5432/app"


@pytest.mark.parametrize(
    "text",
    ["", "plain message", "12:30:45 scraped 3:1 ratio", "https://api.telegram.org/getMe"],
)
def test_redact_leaves_ordinary_text_alone(text):
    assert logging_setup.redact(text) == text


def test_redact_is_idempotent():
    once = logging_setup.redact(SEND_URL)

    assert logging_setup.redact(once) == once


# ── install_log_redaction(): every record, every sink ────────────────────────


def _messages(caplog):
    return [r.getMessage() for r in caplog.records]


def test_logged_url_is_redacted_for_lazy_args_and_fstrings(caplog):
    logging_setup.install_log_redaction()
    logger = logging.getLogger("t.redaction")

    with caplog.at_level(logging.INFO):
        logger.info("lazy %s", SEND_URL)
        logger.info(f"eager {SEND_URL}")

    assert len(caplog.records) == 2
    assert all(TOKEN not in m and "AAFakeToken" not in m for m in _messages(caplog))
    assert all("bot<redacted>" in m for m in _messages(caplog))


def test_traceback_that_embeds_the_url_is_redacted(caplog):
    logging_setup.install_log_redaction()

    with caplog.at_level(logging.ERROR):
        try:
            raise httpx.ConnectError(f"cannot reach {SEND_URL}")
        except httpx.ConnectError:
            logging.getLogger("t.redaction").exception("send failed")

    text = caplog.text  # formatted, includes the traceback
    assert "send failed" in text
    assert "ConnectError" in text
    assert "AAFakeToken" not in text
    assert TOKEN not in text


def test_httpx_request_line_is_kept_but_masked(caplog):
    """Masking is the guarantee: it holds even if httpx is turned back to INFO."""
    logging_setup.install_log_redaction()
    logging.getLogger("httpx").setLevel(logging.INFO)

    with respx.mock:
        respx.post(SEND_URL).mock(return_value=httpx.Response(200))
        with caplog.at_level(logging.INFO):
            httpx.post(SEND_URL, json={})

    request_lines = [m for m in _messages(caplog) if "HTTP Request" in m]
    assert request_lines, "httpx request line should still be logged"
    assert all("AAFakeToken" not in m for m in request_lines)
    assert "bot<redacted>" in request_lines[0]


def test_httpx_and_httpcore_are_not_chatty_at_info():
    logging.getLogger("httpx").setLevel(logging.NOTSET)
    logging.getLogger("httpcore").setLevel(logging.NOTSET)

    logging_setup.install_log_redaction()

    assert logging.getLogger("httpx").level == logging.WARNING
    assert logging.getLogger("httpcore").level == logging.WARNING


def test_install_is_idempotent():
    logging_setup.install_log_redaction()
    installed = logging.getLogRecordFactory()

    logging_setup.install_log_redaction()

    assert logging.getLogRecordFactory() is installed


def test_file_handler_output_has_no_token(tmp_path):
    logging_setup.install_log_redaction()
    log_file = tmp_path / "scheduler.log"
    handler = logging.FileHandler(log_file)
    handler.setFormatter(logging.Formatter("%(levelname)s | %(name)s | %(message)s"))
    root = logging.getLogger()
    previous_level = root.level
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    try:
        logging.getLogger("t.file").info("calling %s", SEND_URL)
        try:
            raise RuntimeError(SEND_URL)
        except RuntimeError:
            logging.getLogger("t.file").error("boom", exc_info=True)
    finally:
        root.removeHandler(handler)
        root.setLevel(previous_level)
        handler.close()

    content = log_file.read_text()
    assert "calling https://api.telegram.org/bot<redacted>/sendMessage" in content
    assert "boom" in content and "RuntimeError" in content
    assert "AAFakeToken" not in content


def test_in_app_log_capture_shows_no_token():
    from admin.log_capture import capture_logs

    logging_setup.install_log_redaction()
    with capture_logs() as handler:
        logging.getLogger("t.capture").info("calling %s", SEND_URL)

    text = "\n".join(handler.lines())
    assert "calling" in text
    assert "AAFakeToken" not in text


# ── TelegramNotifier end to end (acceptance criterion 1) ─────────────────────


@respx.mock
async def test_send_message_never_logs_the_token(caplog):
    respx.post(SEND_URL).mock(return_value=httpx.Response(200))
    notifier = TelegramNotifier()
    notifier.token, notifier.chat_id = TOKEN, "CHAT"
    notifier.api_url = f"https://api.telegram.org/bot{TOKEN}"
    # Worst case: httpx INFO logging switched back on by someone else.
    logging.getLogger("httpx").setLevel(logging.INFO)

    with caplog.at_level(logging.DEBUG):
        assert await notifier.send_message("hello") is True

    assert "AAFakeToken" not in caplog.text
    assert TOKEN not in caplog.text
    assert not any(TOKEN in r.getMessage() for r in caplog.records)


@respx.mock
async def test_failed_send_never_logs_the_token(caplog, monkeypatch):
    async def no_sleep(_):
        return None

    monkeypatch.setattr(telegram_mod, "_sleep", no_sleep)
    respx.post(SEND_URL).mock(side_effect=httpx.ConnectError(f"boom {SEND_URL}"))
    notifier = TelegramNotifier()
    notifier.token, notifier.chat_id = TOKEN, "CHAT"
    notifier.api_url = f"https://api.telegram.org/bot{TOKEN}"

    with caplog.at_level(logging.DEBUG):
        assert await notifier.send_message("hello") is False

    assert "failed after" in caplog.text
    assert "AAFakeToken" not in caplog.text


# ── scripts/scheduler.py: logs/scheduler.log (acceptance criterion 2) ────────

_STUB = """
    import logging, httpx
    from app.scraper.run_stats import RunSummary
    from app.scraper.scheduler import ScraperScheduler

    URL = "https://api.telegram.org/bot{token}/sendMessage"

    async def _stub(self, *a, **k):
        log = logging.getLogger("stub")
        log.info("sending to " + URL)
        transport = httpx.MockTransport(lambda request: httpx.Response(200))
        async with httpx.AsyncClient(transport=transport) as client:
            await client.post(URL, json={{}})
        try:
            raise RuntimeError("failed calling " + URL)
        except RuntimeError:
            log.error("send failed", exc_info=True)
        return RunSummary()

    ScraperScheduler.run_sold_check = _stub
"""


def test_scheduler_script_log_file_contains_no_token(tmp_path):
    (tmp_path / "logs").mkdir()
    wrapper = textwrap.dedent(
        f"""
        import runpy, sys
        sys.path.insert(0, {str(ROOT)!r})
        sys.path.insert(0, {str(ROOT / "app")!r})
        {textwrap.indent(textwrap.dedent(_STUB.format(token=TOKEN)), "        ").strip()}
        sys.argv = [{str(SCRIPT)!r}, "--check-sold"]
        runpy.run_path({str(SCRIPT)!r}, run_name="__main__")
        """
    )
    env = {**os.environ, "TELEGRAM_TOKEN": TOKEN,
           "DATABASE_URL": "postgresql://nobody:nothing@127.0.0.1:1/none"}
    result = subprocess.run(
        [sys.executable, "-c", wrapper],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=120,
    )

    assert result.returncode == 0, result.stderr[-2000:]
    content = (tmp_path / "logs" / "scheduler.log").read_text()
    assert "sending to https://api.telegram.org/bot<redacted>/sendMessage" in content
    assert "send failed" in content
    for sink in (content, result.stderr, result.stdout):
        assert "AAFakeToken" not in sink
        assert TOKEN not in sink
