"""Configuration and credential management for Kindle QuickSend."""

from dataclasses import dataclass
import os
from pathlib import Path
import re
import tomllib
from typing import Optional, Tuple

import keyring

from kindle_quicksend.errors import KqsError

KEYRING_SERVICE = "kindle-quicksend"
DEFAULT_SMTP_HOST = "smtp.gmail.com"
DEFAULT_SMTP_PORT = 465


@dataclass(frozen=True)
class Config:
    kindle_email: str
    sender_email: str
    smtp_host: str = DEFAULT_SMTP_HOST
    smtp_port: int = DEFAULT_SMTP_PORT


def get_config_dir() -> Path:
    """Return the configuration directory for the current user."""
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "kindle-quicksend"
    return Path.home() / ".config" / "kindle-quicksend"


def get_config_path() -> Path:
    """Return the config.toml file path."""
    return get_config_dir() / "config.toml"


def is_valid_email(email: str) -> bool:
    """Basic validation for email format."""
    pattern = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
    return bool(re.match(pattern, email.strip()))


def check_kindle_email(email: str) -> Tuple[bool, Optional[str]]:
    """Validate Kindle email and return (is_valid, warning_message)."""
    clean = email.strip()
    if not is_valid_email(clean):
        return False, "Invalid email address format."
    if not (clean.lower().endswith("@kindle.com") or clean.lower().endswith("@free.kindle.com")):
        return True, "Warning: Kindle addresses usually end with @kindle.com."
    return True, None


def load_config(config_path: Optional[Path] = None) -> Config:
    """Load configuration from config.toml.

    Raises KqsError if not found or incomplete.
    """
    path = config_path or get_config_path()
    if not path.exists():
        raise KqsError(
            "Kindle QuickSend is not configured yet.",
            hint="Please run `kqs setup` first to configure your Kindle and sender addresses.",
        )

    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception as err:
        raise KqsError(
            f"Failed to read configuration file '{path}': {err}",
            hint="Run `kqs setup` to recreate your configuration.",
        ) from err

    kindle_email = data.get("kindle_email")
    sender_email = data.get("sender_email")
    smtp_host = data.get("smtp_host", DEFAULT_SMTP_HOST)
    smtp_port = data.get("smtp_port", DEFAULT_SMTP_PORT)

    if not kindle_email or not sender_email:
        raise KqsError(
            "Incomplete configuration in config.toml.",
            hint="Run `kqs setup` to configure your email settings.",
        )

    return Config(
        kindle_email=str(kindle_email).strip(),
        sender_email=str(sender_email).strip(),
        smtp_host=str(smtp_host).strip(),
        smtp_port=int(smtp_port),
    )


def save_config(cfg: Config, config_path: Optional[Path] = None) -> None:
    """Save non-secret configuration to config.toml."""
    path = config_path or get_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    toml_content = (
        f'kindle_email = "{cfg.kindle_email}"\n'
        f'sender_email = "{cfg.sender_email}"\n'
        f'smtp_host = "{cfg.smtp_host}"\n'
        f'smtp_port = {cfg.smtp_port}\n'
    )
    path.write_text(toml_content, encoding="utf-8")


def get_password(sender_email: str) -> str:
    """Retrieve the email app password from the OS credential store."""
    try:
        pw = keyring.get_password(KEYRING_SERVICE, sender_email)
    except Exception as err:
        raise KqsError(
            f"Failed to access Windows Credential Manager: {err}",
            hint="Please run `kqs setup` to re-enter your credentials.",
        ) from err

    if not pw:
        raise KqsError(
            f"No password found for sender '{sender_email}' in Windows Credential Manager.",
            hint="Please run `kqs setup` to save your app password.",
        )
    return pw


def set_password(sender_email: str, password: str) -> None:
    """Store the email app password securely in the OS credential store."""
    try:
        keyring.set_password(KEYRING_SERVICE, sender_email, password)
    except Exception as err:
        raise KqsError(
            f"Failed to store password in Windows Credential Manager: {err}",
            hint="Check that Windows Credential Manager service is running.",
        ) from err
