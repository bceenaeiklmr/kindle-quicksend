"""Tests for CLI module."""

from pathlib import Path
import pytest

from kindle_quicksend.cli import main
from kindle_quicksend.config import Config


def test_cli_version(capsys):
    with pytest.raises(SystemExit) as exc_info:
        main(["--version"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "Kindle QuickSend" in captured.out


def test_cli_convert_success(tmp_path: Path, capsys):
    out_file = tmp_path / "result.epub"
    code = main(["convert", "tests/fixtures/sample.md", "-o", str(out_file)])
    assert code == 0
    assert out_file.exists()
    assert out_file.stat().st_size > 0

    captured = capsys.readouterr()
    assert "[OK] Converted" in captured.out
    assert "Árvíztűrő tükörfúrógép" in captured.out


def test_cli_convert_refuses_overwrite_source(tmp_path: Path, capsys):
    source_md = tmp_path / "note.md"
    source_md.write_text("# Test\nContent", encoding="utf-8")
    code = main(["convert", str(source_md), "-o", str(source_md)])
    assert code == 1

    captured = capsys.readouterr()
    assert "cannot overwrite the source file" in captured.err


def test_cli_send_not_configured(monkeypatch, tmp_path: Path, capsys):
    # Point config to a nonexistent file in tmp_path
    monkeypatch.setattr(
        "kindle_quicksend.config.get_config_path",
        lambda: tmp_path / "missing_config.toml",
    )

    code = main(["send", "tests/fixtures/sample.md"])
    assert code == 1

    captured = capsys.readouterr()
    assert "not configured yet" in captured.err
    assert "kqs setup" in captured.err


def test_cli_send_success_mocked(monkeypatch, tmp_path: Path, capsys):
    cfg_file = tmp_path / "config.toml"
    cfg = Config(
        kindle_email="myreader@kindle.com",
        sender_email="myself@gmail.com",
        smtp_host="smtp.gmail.com",
        smtp_port=465,
    )
    monkeypatch.setattr("kindle_quicksend.config.get_config_path", lambda: cfg_file)
    monkeypatch.setattr("kindle_quicksend.cli.load_config", lambda: cfg)
    monkeypatch.setattr("kindle_quicksend.cli.get_password", lambda email: "dummy_pass")

    sent_records = []

    def mock_send(msg, cfg, password):
        sent_records.append((msg["To"], msg["Subject"], password))

    monkeypatch.setattr("kindle_quicksend.cli.send", mock_send)

    code = main(["send", "tests/fixtures/sample.md"])
    assert code == 0
    assert len(sent_records) == 1
    assert sent_records[0][0] == "myreader@kindle.com"
    assert sent_records[0][1] == "Árvíztűrő tükörfúrógép"

    captured = capsys.readouterr()
    assert "[OK] Submitted" in captured.out
    assert "Gmail accepted the email" in captured.out
