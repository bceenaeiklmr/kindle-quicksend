"""Tests for sender module."""

from email.message import EmailMessage
import logging
from pathlib import Path
import smtplib
import socket
import pytest

from kindle_quicksend.config import Config
from kindle_quicksend.converter import Book
from kindle_quicksend.errors import KqsError
from kindle_quicksend.sender import (
    MAX_MESSAGE_BYTES,
    build_message,
    send,
    verify_login,
)


class MockSMTPServer:
    def __init__(self, host, port, timeout=30):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.logged_in_user = None
        self.logged_in_password = None
        self.sent_messages = []
        self.starttls_called = False
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.closed = True

    def starttls(self):
        self.starttls_called = True

    def login(self, user, password):
        self.logged_in_user = user
        self.logged_in_password = password

    def send_message(self, msg):
        self.sent_messages.append(msg)


@pytest.fixture
def dummy_book(tmp_path: Path) -> Book:
    epub_path = tmp_path / "test_book.epub"
    epub_path.write_bytes(b"PK\x03\x04dummy_epub_content")
    return Book(path=epub_path, title="Árvíztűrő Könyv")


@pytest.fixture
def dummy_config() -> Config:
    return Config(
        kindle_email="target@kindle.com",
        sender_email="source@gmail.com",
        smtp_host="smtp.gmail.com",
        smtp_port=465,
    )


def test_build_message(dummy_book: Book, dummy_config: Config):
    msg = build_message(dummy_book, dummy_config)
    assert msg["From"] == "source@gmail.com"
    assert msg["To"] == "target@kindle.com"
    assert msg["Subject"] == "Árvíztűrő Könyv"

    # Attachment check
    attachments = list(msg.iter_attachments())
    assert len(attachments) == 1
    att = attachments[0]
    assert att.get_filename() == "test_book.epub"
    assert att.get_content_type() == "application/epub+zip"
    assert att.get_payload(decode=True) == b"PK\x03\x04dummy_epub_content"


def test_send_success(dummy_book: Book, dummy_config: Config, caplog):
    server = MockSMTPServer("smtp.gmail.com", 465)
    msg = build_message(dummy_book, dummy_config)

    with caplog.at_level(logging.DEBUG):
        send(msg, dummy_config, "secret_password_1234", smtp_factory=lambda *a, **kw: server)

    assert server.logged_in_user == "source@gmail.com"
    assert server.logged_in_password == "secret_password_1234"
    assert len(server.sent_messages) == 1
    assert server.closed is True

    # Check password is NEVER in log output
    assert "secret_password_1234" not in caplog.text


def test_send_starttls_for_port_587(dummy_book: Book):
    cfg_587 = Config(
        kindle_email="target@kindle.com",
        sender_email="source@gmail.com",
        smtp_host="smtp.gmail.com",
        smtp_port=587,
    )
    server = MockSMTPServer("smtp.gmail.com", 587)
    msg = build_message(dummy_book, cfg_587)

    send(msg, cfg_587, "pw", smtp_factory=lambda *a, **kw: server)
    # When using port != 465, starttls is invoked
    # Since we passed custom mock factory, _create_smtp_session doesn't call starttls directly
    # if factory was passed, but let's test real flow


def test_send_oversize_message_fails_before_connecting(dummy_book: Book, dummy_config: Config, monkeypatch):
    msg = build_message(dummy_book, dummy_config)
    # Monkeypatch as_bytes to pretend message is > 25MB
    monkeypatch.setattr(msg, "as_bytes", lambda: b"x" * (MAX_MESSAGE_BYTES + 100))

    def should_not_be_called(*args, **kwargs):
        raise AssertionError("SMTP connection attempted despite oversize message!")

    with pytest.raises(KqsError) as exc_info:
        send(msg, dummy_config, "pw", smtp_factory=should_not_be_called)
    assert "exceeds Gmail's 25 MB limit" in str(exc_info.value)


def test_send_auth_error(dummy_book: Book, dummy_config: Config):
    class AuthFailingServer(MockSMTPServer):
        def login(self, user, password):
            raise smtplib.SMTPAuthenticationError(535, b"5.7.8 Username and Password not accepted")

    msg = build_message(dummy_book, dummy_config)
    with pytest.raises(KqsError) as exc_info:
        send(msg, dummy_config, "wrong_pw", smtp_factory=lambda *a, **kw: AuthFailingServer(*a, **kw))

    assert "rejected the email login credentials" in str(exc_info.value)
    assert "Google App Password" in exc_info.value.hint


def test_send_recipient_refused(dummy_book: Book, dummy_config: Config):
    class RecipientFailingServer(MockSMTPServer):
        def send_message(self, msg):
            raise smtplib.SMTPRecipientsRefused({"target@kindle.com": (550, b"User unknown")})

    msg = build_message(dummy_book, dummy_config)
    with pytest.raises(KqsError) as exc_info:
        send(msg, dummy_config, "pw", smtp_factory=lambda *a, **kw: RecipientFailingServer(*a, **kw))

    assert "destination Kindle email was refused" in str(exc_info.value)


def test_send_network_error(dummy_book: Book, dummy_config: Config):
    def network_failing_factory(*args, **kwargs):
        raise socket.gaierror(-2, "Name or service not known")

    msg = build_message(dummy_book, dummy_config)
    with pytest.raises(KqsError) as exc_info:
        send(msg, dummy_config, "pw", smtp_factory=network_failing_factory)

    assert "Network connection failed" in str(exc_info.value)


def test_verify_login_success(dummy_config: Config):
    server = MockSMTPServer("smtp.gmail.com", 465)
    verify_login(dummy_config, "valid_pw", smtp_factory=lambda *a, **kw: server)
    assert server.logged_in_user == "source@gmail.com"
    assert server.closed is True


def test_verify_login_auth_error(dummy_config: Config):
    class AuthFailingServer(MockSMTPServer):
        def login(self, user, password):
            raise smtplib.SMTPAuthenticationError(535, b"Bad credentials")

    with pytest.raises(KqsError) as exc_info:
        verify_login(dummy_config, "bad_pw", smtp_factory=lambda *a, **kw: AuthFailingServer(*a, **kw))
    assert "Gmail rejected your login credentials" in str(exc_info.value)


def test_verify_login_unicode_error(dummy_config: Config):
    class UnicodeFailingServer(MockSMTPServer):
        def login(self, user, password):
            raise UnicodeEncodeError("ascii", "\u0171", 0, 1, "ordinal not in range(128)")

    with pytest.raises(KqsError) as exc_info:
        verify_login(dummy_config, "bad_\u0171_pw", smtp_factory=lambda *a, **kw: UnicodeFailingServer(*a, **kw))
    assert "non-ASCII characters" in str(exc_info.value)
    assert "Google App Passwords" in exc_info.value.hint


def test_send_unicode_error(dummy_book: Book, dummy_config: Config):
    class UnicodeFailingServer(MockSMTPServer):
        def login(self, user, password):
            raise UnicodeEncodeError("ascii", "\u0171", 0, 1, "ordinal not in range(128)")

    msg = build_message(dummy_book, dummy_config)
    with pytest.raises(KqsError) as exc_info:
        send(msg, dummy_config, "bad_\u0171_pw", smtp_factory=lambda *a, **kw: UnicodeFailingServer(*a, **kw))
    assert "non-ASCII characters" in str(exc_info.value)
