"""Email delivery via SMTP for Send to Kindle."""

from email.message import EmailMessage
import logging
from pathlib import Path
import smtplib
import socket
from typing import Callable, Optional

from kindle_quicksend.config import Config
from kindle_quicksend.converter import Book
from kindle_quicksend.errors import KqsError

logger = logging.getLogger("kindle_quicksend")

# Gmail total message limit is 25 MB
MAX_MESSAGE_BYTES = 25 * 1024 * 1024
DEFAULT_TIMEOUT_SECONDS = 30


def build_message(book: Book, cfg: Config) -> EmailMessage:
    """Build a MIME email message with the EPUB attachment."""
    msg = EmailMessage()
    msg["From"] = cfg.sender_email
    msg["To"] = cfg.kindle_email
    msg["Subject"] = book.title

    # Simple plain text body
    msg.set_content(f"Sent via Kindle QuickSend: {book.title}\n")

    file_bytes = book.path.read_bytes()
    # Amazon expects EPUB as application/epub+zip with clean filename
    msg.add_attachment(
        file_bytes,
        maintype="application",
        subtype="epub+zip",
        filename=book.path.name,
    )
    return msg


def _create_smtp_session(
    cfg: Config,
    smtp_factory: Optional[Callable] = None,
) -> smtplib.SMTP:
    """Create an authenticated or secure SMTP connection."""
    timeout = DEFAULT_TIMEOUT_SECONDS
    if smtp_factory is not None:
        return smtp_factory(cfg.smtp_host, cfg.smtp_port, timeout=timeout)

    if cfg.smtp_port == 465:
        return smtplib.SMTP_SSL(cfg.smtp_host, cfg.smtp_port, timeout=timeout)
    else:
        server = smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=timeout)
        server.starttls()
        return server


def verify_login(
    cfg: Config,
    password: str,
    smtp_factory: Optional[Callable] = None,
) -> None:
    """Test SMTP connection and credentials without sending a message."""
    logger.info("Verifying SMTP connection to %s:%d as %s", cfg.smtp_host, cfg.smtp_port, cfg.sender_email)
    try:
        with _create_smtp_session(cfg, smtp_factory) as server:
            server.login(cfg.sender_email, password)
    except smtplib.SMTPAuthenticationError as err:
        raise KqsError(
            "Gmail rejected your login credentials.",
            hint=(
                "Ensure you are using a 16-character Google App Password (not your regular account password) "
                "generated at https://myaccount.google.com/apppasswords with 2-Step Verification enabled."
            ),
        ) from err
    except (socket.gaierror, TimeoutError, ConnectionError, OSError) as err:
        raise KqsError(
            f"Could not connect to SMTP server '{cfg.smtp_host}': {err}",
            hint="Please check your internet connection and firewall settings.",
        ) from err
    except smtplib.SMTPException as err:
        raise KqsError(
            f"SMTP verification failed: {err}",
            hint="Please verify your SMTP settings in config.toml.",
        ) from err


def send(
    msg: EmailMessage,
    cfg: Config,
    password: str,
    smtp_factory: Optional[Callable] = None,
) -> None:
    """Send an email message via SMTP.

    Never logs credentials or enables smtplib debug tracing.
    """
    msg_bytes = msg.as_bytes()
    if len(msg_bytes) > MAX_MESSAGE_BYTES:
        size_mb = len(msg_bytes) / (1024 * 1024)
        raise KqsError(
            f"Message size ({size_mb:.1f} MB) exceeds Gmail's 25 MB limit.",
            hint="Try reducing image sizes or splitting the document.",
        )

    logger.info(
        "Connecting to %s:%d to send to %s (message size: %.1f KB)",
        cfg.smtp_host,
        cfg.smtp_port,
        cfg.kindle_email,
        len(msg_bytes) / 1024,
    )

    try:
        with _create_smtp_session(cfg, smtp_factory) as server:
            server.login(cfg.sender_email, password)
            server.send_message(msg)
    except smtplib.SMTPAuthenticationError as err:
        raise KqsError(
            "Gmail rejected the email login credentials.",
            hint="Ensure your Google App Password is valid. Run `kqs setup` to re-enter it.",
        ) from err
    except smtplib.SMTPRecipientsRefused as err:
        raise KqsError(
            f"The destination Kindle email was refused: {cfg.kindle_email}",
            hint="Check that your Kindle email address is typed correctly.",
        ) from err
    except smtplib.SMTPDataError as err:
        code = getattr(err, "smtp_code", None)
        if code == 552:
            raise KqsError(
                "Message was rejected because it exceeds size limits.",
                hint="Reduce file attachments or images in the document.",
            ) from err
        raise KqsError(
            f"SMTP data transmission failed: {err}",
            hint="Check with your email provider or retry shortly.",
        ) from err
    except (socket.gaierror, TimeoutError, ConnectionError, OSError) as err:
        raise KqsError(
            f"Network connection failed while sending email: {err}",
            hint="Please verify your internet connection and retry.",
        ) from err
    except smtplib.SMTPException as err:
        raise KqsError(
            f"Failed to send email: {err}",
            hint="Check your SMTP configuration in config.toml.",
        ) from err
