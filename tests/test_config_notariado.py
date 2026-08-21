"""Tests for the NOTARIADO_EMAIL / NOTARIADO_PASSWORD config properties."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from config import Settings


def test_notariado_email_reads_from_env(monkeypatch):
    monkeypatch.setenv("NOTARIADO_EMAIL", "user@example.com")
    settings = Settings()
    assert settings.NOTARIADO_EMAIL == "user@example.com"


def test_notariado_password_reads_from_env(monkeypatch):
    monkeypatch.setenv("NOTARIADO_PASSWORD", "s3cr3t")
    settings = Settings()
    assert settings.NOTARIADO_PASSWORD == "s3cr3t"


def test_notariado_credentials_default_to_empty_string(monkeypatch):
    monkeypatch.delenv("NOTARIADO_EMAIL", raising=False)
    monkeypatch.delenv("NOTARIADO_PASSWORD", raising=False)
    settings = Settings()
    assert settings.NOTARIADO_EMAIL == ""
    assert settings.NOTARIADO_PASSWORD == ""
