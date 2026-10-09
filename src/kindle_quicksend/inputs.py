"""Input file detection, validation, and file picking."""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from kindle_quicksend.errors import KqsError

SUPPORTED_EXTENSIONS = {
    ".md": "markdown",
    ".markdown": "markdown",
    ".txt": "text",
}


@dataclass(frozen=True)
class SourceFile:
    path: Path
    kind: str
    text: str


def detect(file_path: Path | str) -> SourceFile:
    """Validate and read a source file.

    Raises KqsError if the file does not exist, is not supported, is empty,
    or cannot be decoded as UTF-8.
    """
    path = Path(file_path).resolve()

    if not path.exists():
        raise KqsError(f"File not found: '{path}'", hint="Please check that the file path is correct.")

    if not path.is_file():
        raise KqsError(f"'{path}' is not a regular file.", hint="Please select a single file to send.")

    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        supported_list = ", ".join(SUPPORTED_EXTENSIONS.keys())
        raise KqsError(
            f"Unsupported file format: '{suffix}'",
            hint=f"Supported file extensions for MVP are: {supported_list}.",
        )

    try:
        raw_bytes = path.read_bytes()
    except OSError as err:
        raise KqsError(f"Cannot read file '{path.name}': {err}") from err

    if not raw_bytes.strip():
        raise KqsError(f"File '{path.name}' is empty.", hint="Please choose a document with content.")

    try:
        # Use utf-8-sig to automatically strip UTF-8 BOM if present
        text = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as err:
        raise KqsError(
            f"File '{path.name}' is not valid UTF-8.",
            hint="Please re-save the file with UTF-8 encoding.",
        ) from err

    return SourceFile(path=path, kind=SUPPORTED_EXTENSIONS[suffix], text=text)


def pick_file() -> Optional[Path]:
    """Open a native Windows file dialog to select a document.

    Tkinter is imported lazily.
    """
    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError as err:
        raise KqsError(
            "Tkinter is not available in your Python installation.",
            hint="Please provide the file path as an argument: kqs send <file>.",
        ) from err

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)

    try:
        filetypes = [
            ("Supported Documents (*.md, *.markdown, *.txt)", "*.md *.markdown *.txt"),
            ("Markdown (*.md, *.markdown)", "*.md *.markdown"),
            ("Text files (*.txt)", "*.txt"),
            ("All files (*.*)", "*.*"),
        ]
        chosen = filedialog.askopenfilename(
            title="Kindle QuickSend - Select Document",
            filetypes=filetypes,
        )
    finally:
        root.destroy()

    if not chosen:
        return None
    return Path(chosen)
