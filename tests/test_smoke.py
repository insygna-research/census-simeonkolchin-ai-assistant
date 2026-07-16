"""Smoke tests that run without external dependencies, credentials, or network."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_project_layout():
    """Core entry points and packages are present."""
    assert (ROOT / "main.py").is_file()
    assert (ROOT / "src" / "config.py").is_file()
    assert (ROOT / "requirements.txt").is_file()


def test_env_example_has_no_real_secrets():
    """.env.example must ship placeholders only."""
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert "gitlab.uniweb.ru" not in text
    assert "158.160.171.6" not in text


def test_config_declares_supported_providers():
    """Config wires up the three documented LLM providers."""
    config_src = (ROOT / "src" / "config.py").read_text(encoding="utf-8")
    for provider in ("deepseek", "openai", "gigachat"):
        assert provider in config_src.lower()
