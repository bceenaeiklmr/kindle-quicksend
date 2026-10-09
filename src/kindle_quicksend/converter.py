"""Document conversion to Kindle-friendly EPUB via Pandoc."""

from dataclasses import dataclass
import html
from importlib import resources
import logging
from pathlib import Path
import re
import subprocess
from typing import Optional, Tuple
import unicodedata

import pypandoc

from kindle_quicksend.errors import KqsError
from kindle_quicksend.inputs import SourceFile

logger = logging.getLogger("kindle_quicksend")


@dataclass(frozen=True)
class Book:
    path: Path
    title: str


def ascii_stem(name: str) -> str:
    """Normalize a name to a safe ASCII filename stem.

    Transliterates accented characters (e.g. Hungarian é -> e) and replaces
    spaces/punctuation with underscores.
    """
    stem = Path(name).stem if "." in name else name
    normalized = unicodedata.normalize("NFKD", stem)
    ascii_chars = [c for c in normalized if not unicodedata.combining(c)]
    ascii_str = "".join(ascii_chars)
    cleaned = re.sub(r"[^A-Za-z0-9_\-]+", "_", ascii_str).strip("_")
    return cleaned if cleaned else "document"


def extract_title(text: str, fallback: str, kind: str = "markdown") -> Tuple[str, bool]:
    """Extract document title.

    Returns:
        (title, is_from_h1)
        where is_from_h1 indicates whether the title came from an H1 header.
    """
    if kind != "markdown":
        return fallback, False

    # 1. Check YAML front-matter: starts with --- and ends with ---
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            fm = parts[1]
            match = re.search(r"^title:\s*[\"']?(.*?)[\"']?\s*$", fm, re.MULTILINE)
            if match and match.group(1).strip():
                return match.group(1).strip(), False

    # 2. Check for first Markdown H1: line starting with '# '
    for line in text.splitlines():
        line_stripped = line.strip()
        if line_stripped.startswith("# "):
            title = line_stripped[2:].strip()
            if title:
                return title, True

    # 3. Fallback to file stem
    return fallback, False


def text_to_html(text: str) -> str:
    """Convert plain text to clean HTML preserving paragraphs and line breaks."""
    paragraphs = re.split(r"(?:\r?\n\s*){2,}", text.strip())
    html_paragraphs = []
    for p in paragraphs:
        escaped = html.escape(p)
        br_separated = escaped.replace("\r\n", "\n").replace("\n", "<br/>\n")
        html_paragraphs.append(f"<p>{br_separated}</p>")
    return "\n".join(html_paragraphs)


def get_css_path() -> Path:
    """Return path to packaged epub.css."""
    # Try package directory first
    css_file = Path(__file__).parent / "epub.css"
    if css_file.exists():
        return css_file
    raise KqsError("Internal error: epub.css template not found.")


def to_epub(
    src: SourceFile,
    out_dir: Path,
    pandoc_path: Optional[str] = None,
) -> Book:
    """Convert a SourceFile to an EPUB file in out_dir.

    Preserves source file untouched and creates an EPUB in out_dir.
    """
    if pandoc_path is None:
        try:
            pandoc_path = pypandoc.get_pandoc_path()
        except OSError as err:
            raise KqsError(
                "Pandoc executable not found.",
                hint="Please reinstall kindle-quicksend (e.g. `pipx install kindle-quicksend`).",
            ) from err

    title, is_from_h1 = extract_title(src.text, src.path.stem, kind=src.kind)
    safe_name = ascii_stem(src.path.name)
    out_epub = out_dir / f"{safe_name}.epub"

    css_path = get_css_path()

    cmd = [
        pandoc_path,
        "-t", "epub3",
        "--toc",
        "--toc-depth=2",
        "--split-level=1",
        f"--css={css_path}",
        f"--resource-path={src.path.parent}",
        f"-M", f"title={title}",
        "--highlight-style=monochrome",
        "-o", str(out_epub),
    ]

    # If the title came from the first H1 in the content, disable duplicate title page
    if is_from_h1:
        cmd.append("--epub-title-page=false")

    stdin_input = None

    if src.kind == "markdown":
        cmd.extend(["-f", "markdown", str(src.path)])
    elif src.kind == "text":
        cmd.extend(["-f", "html"])
        stdin_input = text_to_html(src.text).encode("utf-8")
    else:
        raise KqsError(f"Unsupported kind for conversion: '{src.kind}'")

    logger.debug("Running pandoc: %s", " ".join(cmd))

    try:
        proc = subprocess.run(
            cmd,
            input=stdin_input,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except FileNotFoundError as err:
        raise KqsError(
            f"Failed to execute Pandoc at '{pandoc_path}'.",
            hint="Please verify your Pandoc installation.",
        ) from err

    if proc.returncode != 0:
        err_msg = proc.stderr.decode("utf-8", errors="replace").strip()
        logger.error("Pandoc conversion failed: %s", err_msg)
        raise KqsError(
            f"Document conversion failed for '{src.path.name}'.",
            hint=f"Pandoc error: {err_msg}" if err_msg else None,
        )

    if not out_epub.exists() or out_epub.stat().st_size == 0:
        raise KqsError(
            f"Conversion produced an empty or missing file for '{src.path.name}'.",
            hint="Please check if the document contains valid content.",
        )

    return Book(path=out_epub, title=title)
