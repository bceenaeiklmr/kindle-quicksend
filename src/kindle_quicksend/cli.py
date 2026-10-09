"""Command-line interface for Kindle QuickSend."""

import argparse
import getpass
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import sys
import tempfile
from typing import Optional

from kindle_quicksend import __version__
from kindle_quicksend.config import (
    Config,
    check_kindle_email,
    get_config_dir,
    get_password,
    is_valid_email,
    load_config,
    save_config,
    set_password,
)
from kindle_quicksend.converter import to_epub
from kindle_quicksend.errors import KqsError
from kindle_quicksend.inputs import detect, pick_file
from kindle_quicksend.sender import build_message, send, verify_login

logger = logging.getLogger("kindle_quicksend")


def setup_logging(verbose: bool = False) -> Path:
    """Configure rotating file logger and optional console logging."""
    log_dir = get_config_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "kqs.log"

    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    # File handler (rotates at 1 MB, keeps 2 backups)
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=1024 * 1024,
        backupCount=2,
        encoding="utf-8",
    )
    file_formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
    file_handler.setFormatter(file_formatter)
    file_handler.setLevel(logging.DEBUG)
    logger.addHandler(file_handler)

    # Console handler if verbose
    if verbose:
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
        console_handler.setLevel(logging.DEBUG)
        logger.addHandler(console_handler)

    return log_file


def run_setup() -> None:
    """Interactively configure Kindle QuickSend."""
    print("=== Kindle QuickSend Setup ===")
    print("This will configure your Send to Kindle destination and approved Gmail sender.\n")

    current_cfg: Optional[Config] = None
    has_stored_pw = False
    try:
        current_cfg = load_config()
        try:
            get_password(current_cfg.sender_email)
            has_stored_pw = True
        except Exception:
            has_stored_pw = False
    except Exception:
        pass

    # 1. Kindle email
    kindle_default = current_cfg.kindle_email if current_cfg else ""
    prompt_kindle = f"Kindle email address [{kindle_default}]: " if kindle_default else "Kindle email address (e.g. yourname@kindle.com): "
    kindle_input = input(prompt_kindle).strip()
    kindle_email = kindle_input or kindle_default

    valid, warning = check_kindle_email(kindle_email)
    if not valid:
        raise KqsError(f"Invalid email: '{kindle_email}'", hint="Please enter a valid email address.")
    if warning:
        print(f"  {warning}")

    # 2. Sender Gmail address
    sender_default = current_cfg.sender_email if current_cfg else ""
    prompt_sender = f"Sender Gmail address [{sender_default}]: " if sender_default else "Sender Gmail address (e.g. you@gmail.com): "
    sender_input = input(prompt_sender).strip()
    sender_email = sender_input or sender_default

    if not is_valid_email(sender_email):
        raise KqsError(f"Invalid sender email: '{sender_email}'", hint="Please enter a valid Gmail address.")

    # 3. Gmail App Password
    print("\nGmail App Password:")
    print("  * You need a 16-character App Password from Google Accounts.")
    print("  * Generate one at: https://myaccount.google.com/apppasswords")
    if has_stored_pw and sender_email == (current_cfg.sender_email if current_cfg else ""):
        prompt_pw = "Google App Password [leave blank to keep existing password]: "
    else:
        prompt_pw = "Google App Password: "

    pw_input = getpass.getpass(prompt_pw).strip()

    if not pw_input:
        if has_stored_pw and current_cfg and sender_email == current_cfg.sender_email:
            password = get_password(sender_email)
        else:
            raise KqsError("App password cannot be empty.", hint="Please enter a Google App Password.")
    else:
        # Strip spaces from app password if copied with spaces
        password = pw_input.replace(" ", "")

    cfg = Config(
        kindle_email=kindle_email,
        sender_email=sender_email,
        smtp_host="smtp.gmail.com",
        smtp_port=465,
    )

    print("\nVerifying connection and login to smtp.gmail.com:465 ... ", end="", flush=True)
    verify_login(cfg, password)
    print("OK!")

    save_config(cfg)
    set_password(sender_email, password)

    print("\n[SUCCESS] Kindle QuickSend configured successfully!")
    print(f"  Destination : {cfg.kindle_email}")
    print(f"  Sender      : {cfg.sender_email}")
    print("  Password    : Stored securely in Windows Credential Manager")
    print(f"  Config file : {get_config_dir() / 'config.toml'}\n")
    print("Make sure your sender address is added to your Amazon Approved Personal Document E-mail List:")
    print("  https://www.amazon.com/myk (Preferences -> Personal Document Settings)\n")


def run_send(file_arg: Optional[str], pause: bool = False) -> None:
    """Send a document to Kindle."""
    cfg = load_config()
    password = get_password(cfg.sender_email)

    target_path: Optional[Path] = None
    if file_arg:
        target_path = Path(file_arg)
    else:
        print("Opening file picker...")
        target_path = pick_file()
        if not target_path:
            print("No file selected. Operation cancelled.")
            return

    src = detect(target_path)
    print(f"Converting '{src.path.name}' to EPUB ... ", end="", flush=True)

    with tempfile.TemporaryDirectory(prefix="kqs_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        book = to_epub(src, tmp_path)
        print("OK")
        print(f"  Title: \"{book.title}\"")

        print(f"Sending to {cfg.kindle_email} ... ", end="", flush=True)
        msg = build_message(book, cfg)
        send(msg, cfg, password)
        print("OK\n")

    print(f"[OK] Submitted \"{book.title}\" to {cfg.kindle_email}.")
    print("Note: Gmail accepted the email. Delivery to your Kindle usually takes 1-5 minutes over Wi-Fi.")
    print(f"If Amazon encounters an issue, a notification will be sent to {cfg.sender_email}.")


def run_convert(file_arg: str, out_arg: str) -> None:
    """Convert a document locally without sending."""
    target_path = Path(file_arg)
    src = detect(target_path)

    out_path = Path(out_arg).resolve()
    if out_path.resolve() == src.path.resolve():
        raise KqsError(
            "Output file cannot overwrite the source file.",
            hint="Please specify a different output path.",
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="kqs_convert_") as tmp_dir:
        book = to_epub(src, Path(tmp_dir))
        # Copy or move generated epub to desired output location
        out_path.write_bytes(book.path.read_bytes())

    print(f"[OK] Converted '{src.path.name}' -> '{out_path}'")
    print(f"  Title: \"{book.title}\"")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="kqs",
        description="Kindle QuickSend: Effortlessly send documents to your Kindle.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"Kindle QuickSend {__version__}",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose diagnostic output.",
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # setup
    subparsers.add_parser("setup", help="Configure Kindle destination and Gmail sender.")

    # send
    send_parser = subparsers.add_parser("send", help="Convert and send a document to Kindle.")
    send_parser.add_argument(
        "file",
        nargs="?",
        default=None,
        help="Document to send (.md, .txt). If omitted, opens file picker.",
    )
    send_parser.add_argument(
        "--pause",
        action="store_true",
        help="Wait for Enter key before exiting (useful for Windows shortcuts).",
    )

    # convert
    convert_parser = subparsers.add_parser("convert", help="Convert document to EPUB locally.")
    convert_parser.add_argument("file", help="Input document (.md, .txt).")
    convert_parser.add_argument(
        "-o", "--out",
        required=True,
        help="Destination .epub file path.",
    )

    args = parser.parse_args(argv)
    log_file = setup_logging(verbose=args.verbose)

    pause = getattr(args, "pause", False)

    try:
        if args.command == "setup":
            run_setup()
        elif args.command == "send":
            run_send(args.file, pause=args.pause)
        elif args.command == "convert":
            run_convert(args.file, args.out)
        else:
            parser.print_help()
            return 0
        return 0

    except KqsError as err:
        logger.error("KqsError: %s", err)
        print(f"\nError: {err.message}", file=sys.stderr)
        if err.hint:
            print(f"Hint: {err.hint}", file=sys.stderr)
        return 1

    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
        return 130

    except Exception as err:
        logger.exception("Unexpected exception occurred")
        print(f"\nError: An unexpected error occurred: {err}", file=sys.stderr)
        print(f"Diagnostics logged to: {log_file}", file=sys.stderr)
        return 1

    finally:
        if pause:
            try:
                input("\nPress Enter to exit...")
            except (KeyboardInterrupt, EOFError):
                pass


if __name__ == "__main__":
    sys.exit(main())
