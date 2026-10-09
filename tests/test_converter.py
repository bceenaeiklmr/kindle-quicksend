"""Tests for converter module."""

from pathlib import Path
import zipfile
import pytest

from kindle_quicksend.converter import ascii_stem, extract_title, to_epub
from kindle_quicksend.errors import KqsError
from kindle_quicksend.inputs import detect


def test_ascii_stem():
    assert ascii_stem("Jegyzetek – angol.md") == "Jegyzetek_angol"
    assert ascii_stem("Árvíztűrő tükörfúrógép.markdown") == "Arvizturo_tukorfurogep"
    assert ascii_stem("My Notes (2026)!?.txt") == "My_Notes_2026"
    assert ascii_stem("???") == "document"
    assert ascii_stem("simple_name") == "simple_name"


def test_extract_title_from_frontmatter():
    text = "---\ntitle: 'Egyéni Cím'\nauthor: Teszt\n---\n# Második cím\nTartalom"
    title, is_h1 = extract_title(text, "fallback")
    assert title == "Egyéni Cím"
    assert is_h1 is False


def test_extract_title_from_h1():
    text = "Bevezető szöveg\n\n# Első Címsor\n\n## Második szint"
    title, is_h1 = extract_title(text, "fallback")
    assert title == "Első Címsor"
    assert is_h1 is True


def test_extract_title_fallback():
    text = "Csak sima szöveg, címsor nélkül."
    title, is_h1 = extract_title(text, "eredeti_fajlnev")
    assert title == "eredeti_fajlnev"
    assert is_h1 is False


def test_to_epub_markdown(tmp_path: Path):
    fixture_md = Path("tests/fixtures/sample.md").resolve()
    orig_bytes = fixture_md.read_bytes()
    orig_mtime = fixture_md.stat().st_mtime_ns

    src = detect(fixture_md)
    book = to_epub(src, tmp_path)

    # 1. Source file untouched
    assert fixture_md.read_bytes() == orig_bytes
    assert fixture_md.stat().st_mtime_ns == orig_mtime

    # 2. Book metadata
    assert book.title == "Árvíztűrő tükörfúrógép"
    assert book.path.exists()
    assert book.path.name == "sample.epub"

    # 3. Valid EPUB zip structure
    with zipfile.ZipFile(book.path, "r") as zf:
        namelist = zf.namelist()
        assert "mimetype" in namelist
        assert zf.read("mimetype").decode("utf-8").strip() == "application/epub+zip"

        # Check content files
        all_content = ""
        for name in namelist:
            if name.endswith((".xhtml", ".html", ".ncx", ".opf")):
                all_content += zf.read(name).decode("utf-8", errors="ignore")

        assert "Árvíztűrő tükörfúrógép" in all_content
        assert "Formázási elemek" in all_content
        assert "https://amazon.com" in all_content
        assert "koszones" in all_content
        assert "Leonardo da Vinci" in all_content
        # Check image was included in the zip (Pandoc stores media under EPUB/media/)
        image_entries = [n for n in namelist if n.endswith(".png")]
        assert len(image_entries) > 0


def test_to_epub_text_preserves_literals(tmp_path: Path):
    fixture_txt = Path("tests/fixtures/sample.txt").resolve()
    src = detect(fixture_txt)
    book = to_epub(src, tmp_path)

    assert book.path.exists()
    assert book.path.name == "sample.epub"

    with zipfile.ZipFile(book.path, "r") as zf:
        all_content = ""
        for name in zf.namelist():
            if name.endswith((".xhtml", ".html")):
                all_content += zf.read(name).decode("utf-8", errors="ignore")

        # Must preserve literals, not convert to Markdown markdown tags
        assert "# Ez nem c" in all_content and "msor!" in all_content
        assert "*Ez nem d" in all_content and "lt bet" in all_content
        assert "[Ez nem link](https://example.com)" in all_content
        assert "<em" not in all_content
        assert 'href="https://example.com"' not in all_content


def test_to_epub_pandoc_not_found(tmp_path: Path):
    fixture_md = Path("tests/fixtures/sample.md").resolve()
    src = detect(fixture_md)
    with pytest.raises(KqsError) as exc_info:
        to_epub(src, tmp_path, pandoc_path="nonexistent_pandoc_binary_xyz")
    assert "Pandoc" in str(exc_info.value)
