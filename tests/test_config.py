"""Tests for config module."""

from pathlib import Path
import pytest

from kindle_quicksend.config import (
    Config,
    check_kindle_email,
    get_password,
    is_valid_email,
    load_config,
    save_config,
    set_password,
)
from kindle_quicksend.errors import KqsError


class InMemoryKeyring:
    def __init__(self):
        self._store = {}

    def get_password(self, service, username):
        return self._store.get((service, username))

    def set_password(self, service, username, password):
        self._store[(service, username)] = password


def test_email_validation():
    assert is_valid_email("user@gmail.com") is True
    assert is_valid_email("name.last@example.co.uk") is True
    assert is_valid_email("invalid-email") is False
    assert is_valid_email("@nodomain.com") is False
    assert is_valid_email("user@") is False


def test_kindle_email_check():
    valid, warn = check_kindle_email("mydevice_12@kindle.com")
    assert valid is True
    assert warn is None

    valid, warn = check_kindle_email("device@free.kindle.com")
    assert valid is True
    assert warn is None

    valid, warn = check_kindle_email("device@gmail.com")
    assert valid is True
    assert warn is not None
    assert "usually end with @kindle.com" in warn

    valid, warn = check_kindle_email("bad-email")
    assert valid is False


def test_save_and_load_config_roundtrip(tmp_path: Path):
    cfg_file = tmp_path / "config.toml"
    cfg = Config(
        kindle_email="myreader@kindle.com",
        sender_email="myself@gmail.com",
        smtp_host="smtp.gmail.com",
        smtp_port=465,
    )
    save_config(cfg, cfg_file)

    # Verify config file exists and contains no passwords
    content = cfg_file.read_text(encoding="utf-8")
    assert "myreader@kindle.com" in content
    assert "myself@gmail.com" in content
    assert "password" not in content.lower()

    # Load back
    loaded = load_config(cfg_file)
    assert loaded == cfg


def test_load_config_not_found(tmp_path: Path):
    missing_file = tmp_path / "nonexistent.toml"
    with pytest.raises(KqsError) as exc_info:
        load_config(missing_file)
    assert "not configured yet" in str(exc_info.value)
    assert "kqs setup" in exc_info.value.hint


def test_load_config_incomplete(tmp_path: Path):
    bad_file = tmp_path / "bad.toml"
    bad_file.write_text('smtp_host = "smtp.gmail.com"\n', encoding="utf-8")
    with pytest.raises(KqsError) as exc_info:
        load_config(bad_file)
    assert "Incomplete configuration" in str(exc_info.value)


def test_keyring_password(monkeypatch):
    fake_keyring = InMemoryKeyring()
    monkeypatch.setattr("kindle_quicksend.config.keyring", fake_keyring)

    set_password("user@gmail.com", "secret_app_pw_1234")
    pw = get_password("user@gmail.com")
    assert pw == "secret_app_pw_1234"


def test_keyring_missing_password(monkeypatch):
    fake_keyring = InMemoryKeyring()
    monkeypatch.setattr("kindle_quicksend.config.keyring", fake_keyring)

    with pytest.raises(KqsError) as exc_info:
        get_password("unknown@gmail.com")
    assert "No password found" in str(exc_info.value)
    assert "kqs setup" in exc_info.value.hint
