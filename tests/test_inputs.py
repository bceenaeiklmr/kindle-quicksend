"""Tests for inputs module."""

from pathlib import Path
import pytest

from kindle_quicksend.errors import KqsError
from kindle_quicksend.inputs import detect


def test_detect_markdown(tmp_path: Path):
    md_file = tmp_path / "test.md"
    md_file.write_text("# Hello World\nSome text", encoding="utf-8")
    src = detect(md_file)
    assert src.kind == "markdown"
    assert src.path == md_file.resolve()
    assert "Hello World" in src.text


def test_detect_case_insensitive_extension(tmp_path: Path):
    md_file = tmp_path / "test.MARKDOWN"
    md_file.write_text("# Title\nContent", encoding="utf-8")
    src = detect(md_file)
    assert src.kind == "markdown"


def test_detect_txt(tmp_path: Path):
    txt_file = tmp_path / "notes.txt"
    txt_file.write_text("Line 1\nLine 2", encoding="utf-8")
    src = detect(txt_file)
    assert src.kind == "text"
    assert "Line 1" in src.text


def test_detect_utf8_with_bom(tmp_path: Path):
    bom_file = tmp_path / "bom.md"
    bom_file.write_bytes(b"\xef\xbb\xbf# Title\nContent with BOM")
    src = detect(bom_file)
    assert src.kind == "markdown"
    assert not src.text.startswith("\ufeff")
    assert src.text.startswith("# Title")


def test_detect_nonexistent_file(tmp_path: Path):
    missing = tmp_path / "does_not_exist.md"
    with pytest.raises(KqsError) as exc_info:
        detect(missing)
    assert "File not found" in str(exc_info.value)


def test_detect_directory(tmp_path: Path):
    with pytest.raises(KqsError) as exc_info:
        detect(tmp_path)
    assert "not a regular file" in str(exc_info.value)


def test_detect_unsupported_extension(tmp_path: Path):
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4 dummy")
    with pytest.raises(KqsError) as exc_info:
        detect(pdf)
    assert "Unsupported file format" in str(exc_info.value)
    assert ".md" in exc_info.value.hint


def test_detect_empty_file(tmp_path: Path):
    empty = tmp_path / "empty.md"
    empty.write_text("   \n\t  ", encoding="utf-8")
    with pytest.raises(KqsError) as exc_info:
        detect(empty)
    assert "is empty" in str(exc_info.value)


def test_detect_invalid_utf8(tmp_path: Path):
    bad = tmp_path / "bad_encoding.txt"
    # Invalid UTF-8 sequence
    bad.write_bytes(b"Valami \xe9kezet: \xff\xfehibas")
    with pytest.raises(KqsError) as exc_info:
        detect(bad)
    assert "not valid UTF-8" in str(exc_info.value)
