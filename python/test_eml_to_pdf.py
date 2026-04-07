"""Tests for eml_to_pdf.py — unit and integration."""

import base64
import email.mime.image
import email.mime.multipart
import email.mime.text
import io
import textwrap
from pathlib import Path

import pytest

from eml_to_pdf import (
    EmailAttachment,
    ParsedEmail,
    _sanitize_filename,
    _strip_cid,
    build_html,
    convert_batch,
    extract_attachments_to_dir,
    main,
    parse_eml,
    resolve_cid_references,
)


# ─────────────────────────────────────────────
# Helpers — build .eml bytes programmatically
# ─────────────────────────────────────────────

def _make_plain_eml(
    subject: str = "Hello",
    from_addr: str = "alice@example.com",
    to_addr: str = "bob@example.com",
    body: str = "Plain text body.",
) -> bytes:
    msg = email.mime.text.MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg["Date"] = "Mon, 07 Apr 2025 10:00:00 +0000"
    return msg.as_bytes()


def _make_html_eml(
    subject: str = "HTML Email",
    body: str = "<p>Hello <b>World</b></p>",
) -> bytes:
    msg = email.mime.text.MIMEText(body, "html", "utf-8")
    msg["Subject"] = subject
    msg["From"] = "alice@example.com"
    msg["To"] = "bob@example.com"
    msg["Date"] = "Mon, 07 Apr 2025 10:00:00 +0000"
    return msg.as_bytes()


def _make_multipart_alternative_eml(
    plain: str = "Plain text",
    html: str = "<p>HTML text</p>",
) -> bytes:
    msg = email.mime.multipart.MIMEMultipart("alternative")
    msg["Subject"] = "Alternative"
    msg["From"] = "alice@example.com"
    msg["To"] = "bob@example.com"
    msg["Date"] = "Mon, 07 Apr 2025 10:00:00 +0000"
    msg.attach(email.mime.text.MIMEText(plain, "plain", "utf-8"))
    msg.attach(email.mime.text.MIMEText(html, "html", "utf-8"))
    return msg.as_bytes()


def _make_eml_with_inline_image(html_with_cid: str, img_bytes: bytes, cid: str) -> bytes:
    related = email.mime.multipart.MIMEMultipart("related")
    related["Subject"] = "Inline image"
    related["From"] = "alice@example.com"
    related["To"] = "bob@example.com"
    related["Date"] = "Mon, 07 Apr 2025 10:00:00 +0000"

    related.attach(email.mime.text.MIMEText(html_with_cid, "html", "utf-8"))

    img_part = email.mime.image.MIMEImage(img_bytes, "png")
    img_part["Content-ID"] = f"<{cid}>"
    related.attach(img_part)

    return related.as_bytes()


def _make_eml_with_attachment(attachment_data: bytes, filename: str = "report.pdf") -> bytes:
    msg = email.mime.multipart.MIMEMultipart("mixed")
    msg["Subject"] = "With attachment"
    msg["From"] = "alice@example.com"
    msg["To"] = "bob@example.com"
    msg["Date"] = "Mon, 07 Apr 2025 10:00:00 +0000"
    msg.attach(email.mime.text.MIMEText("See attached.", "plain", "utf-8"))

    from email.mime.base import MIMEBase
    from email import encoders
    att = MIMEBase("application", "octet-stream")
    att.set_payload(attachment_data)
    encoders.encode_base64(att)
    att.add_header("Content-Disposition", "attachment", filename=filename)
    msg.attach(att)

    return msg.as_bytes()


def _write_eml(tmp_path: Path, name: str, content: bytes) -> Path:
    p = tmp_path / name
    p.write_bytes(content)
    return p


# ─────────────────────────────────────────────
# Unit tests — parse_eml
# ─────────────────────────────────────────────

class TestParseEml:
    def test_plain_text_only(self, tmp_path: Path) -> None:
        eml = _write_eml(tmp_path, "msg.eml", _make_plain_eml(body="Hello world"))
        parsed = parse_eml(eml)
        assert parsed.text_body is not None
        assert "Hello world" in parsed.text_body
        assert parsed.html_body is None

    def test_html_only(self, tmp_path: Path) -> None:
        eml = _write_eml(tmp_path, "msg.eml", _make_html_eml(body="<p>Hi</p>"))
        parsed = parse_eml(eml)
        assert parsed.html_body is not None
        assert "<p>Hi</p>" in parsed.html_body
        assert parsed.text_body is None

    def test_multipart_alternative_prefers_html(self, tmp_path: Path) -> None:
        eml = _write_eml(
            tmp_path, "msg.eml",
            _make_multipart_alternative_eml(plain="plain", html="<b>html</b>"),
        )
        parsed = parse_eml(eml)
        assert parsed.html_body is not None
        assert "<b>html</b>" in parsed.html_body
        assert parsed.text_body is not None  # plain text also captured
        assert "plain" in parsed.text_body

    def test_headers_decoded(self, tmp_path: Path) -> None:
        eml = _write_eml(
            tmp_path, "msg.eml",
            _make_plain_eml(
                subject="Test subject",
                from_addr="Alice <alice@example.com>",
                to_addr="Bob <bob@example.com>",
            ),
        )
        parsed = parse_eml(eml)
        assert parsed.subject == "Test subject"
        assert "alice@example.com" in parsed.from_addr
        assert "bob@example.com" in parsed.to_addr

    def test_rfc2047_encoded_subject(self, tmp_path: Path) -> None:
        # =?UTF-8?B? is base64-encoded "Héllo"
        encoded_subject = "=?UTF-8?B?SGVsbG8gV29ybGQ=?="  # "Hello World"
        raw = _make_plain_eml(subject=encoded_subject)
        eml = _write_eml(tmp_path, "msg.eml", raw)
        parsed = parse_eml(eml)
        assert "Hello World" in parsed.subject

    def test_inline_image_collected(self, tmp_path: Path) -> None:
        fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50
        eml = _write_eml(
            tmp_path, "msg.eml",
            _make_eml_with_inline_image(
                html_with_cid='<img src="cid:img001@test">',
                img_bytes=fake_png,
                cid="img001@test",
            ),
        )
        parsed = parse_eml(eml)
        assert "img001@test" in parsed.inline_images
        assert parsed.inline_images["img001@test"].size_bytes == len(fake_png)

    def test_attachment_collected(self, tmp_path: Path) -> None:
        eml = _write_eml(
            tmp_path, "msg.eml",
            _make_eml_with_attachment(b"PDF content here", "report.pdf"),
        )
        parsed = parse_eml(eml)
        assert len(parsed.attachments) == 1
        assert parsed.attachments[0].filename == "report.pdf"

    def test_file_not_found_raises(self) -> None:
        with pytest.raises(FileNotFoundError):
            parse_eml(Path("/nonexistent/path/msg.eml"))


# ─────────────────────────────────────────────
# Unit tests — CID resolution
# ─────────────────────────────────────────────

class TestResolveCidReferences:
    def _make_attachment(self, data: bytes, cid: str, ct: str = "image/png") -> EmailAttachment:
        return EmailAttachment(
            filename="img.png",
            content_type=ct,
            size_bytes=len(data),
            content_id=cid,
            payload_bytes=data,
        )

    def test_replaces_cid_with_data_uri(self) -> None:
        img_bytes = b"PNGDATA"
        att = self._make_attachment(img_bytes, "img001@test")
        html = '<img src="cid:img001@test">'
        result = resolve_cid_references(html, {"img001@test": att})
        assert "data:image/png;base64," in result
        assert "cid:" not in result
        encoded = base64.b64encode(img_bytes).decode()
        assert encoded in result

    def test_large_image_replaced_with_placeholder(self) -> None:
        big_data = b"X" * (6 * 1024 * 1024)  # 6 MB
        att = self._make_attachment(big_data, "big@test")
        html = '<img src="cid:big@test">'
        result = resolve_cid_references(html, {"big@test": att}, max_image_bytes=5 * 1024 * 1024)
        assert "cid:" not in result
        assert "svg" in result  # placeholder SVG

    def test_unknown_cid_left_unchanged(self) -> None:
        html = '<img src="cid:unknown@cid">'
        result = resolve_cid_references(html, {})
        assert 'src="cid:unknown@cid"' in result

    def test_single_quote_src(self) -> None:
        img_bytes = b"DATA"
        att = self._make_attachment(img_bytes, "img@test")
        html = "<img src='cid:img@test'>"
        result = resolve_cid_references(html, {"img@test": att})
        assert "cid:" not in result


# ─────────────────────────────────────────────
# Unit tests — HTML building
# ─────────────────────────────────────────────

class TestBuildHtml:
    def _plain_parsed(self, text: str = "Hello") -> ParsedEmail:
        return ParsedEmail(
            subject="Test", from_addr="a@b.com", to_addr="c@d.com",
            cc_addr="", date="Mon, 07 Apr 2025",
            html_body=None, text_body=text,
            inline_images={}, attachments=[],
        )

    def _html_parsed(self, html: str = "<p>Hi</p>") -> ParsedEmail:
        return ParsedEmail(
            subject="Test", from_addr="a@b.com", to_addr="c@d.com",
            cc_addr="", date="Mon, 07 Apr 2025",
            html_body=html, text_body=None,
            inline_images={}, attachments=[],
        )

    def test_includes_subject_in_output(self) -> None:
        result = build_html(self._plain_parsed())
        assert "Test" in result

    def test_plain_text_wrapped_in_pre(self) -> None:
        result = build_html(self._plain_parsed("some plain text"))
        assert "<pre>" in result
        assert "some plain text" in result

    def test_html_body_rendered(self) -> None:
        result = build_html(self._html_parsed("<p>Rich content</p>"))
        assert "<p>Rich content</p>" in result
        assert "<pre>" not in result

    def test_no_body_shows_placeholder(self) -> None:
        parsed = ParsedEmail(
            subject="Empty", from_addr="a@b.com", to_addr="c@d.com",
            cc_addr="", date="", html_body=None, text_body=None,
            inline_images={}, attachments=[],
        )
        result = build_html(parsed)
        assert "No message body" in result

    def test_attachments_list_rendered(self) -> None:
        att = EmailAttachment(
            filename="file.pdf", content_type="application/pdf",
            size_bytes=1024, content_id=None, payload_bytes=b"",
        )
        parsed = ParsedEmail(
            subject="Att", from_addr="a@b.com", to_addr="c@d.com",
            cc_addr="", date="", html_body=None, text_body="body",
            inline_images={}, attachments=[att],
        )
        result = build_html(parsed)
        assert "file.pdf" in result
        assert "Attachments" in result

    def test_cc_only_shown_when_present(self) -> None:
        parsed = ParsedEmail(
            subject="X", from_addr="a@b.com", to_addr="c@d.com",
            cc_addr="cc@d.com", date="",
            html_body=None, text_body="hi",
            inline_images={}, attachments=[],
        )
        result = build_html(parsed)
        assert "cc@d.com" in result


# ─────────────────────────────────────────────
# Unit tests — utilities
# ─────────────────────────────────────────────

class TestUtilities:
    def test_sanitize_filename_strips_path(self) -> None:
        assert _sanitize_filename("../../etc/passwd") == "passwd"
        assert _sanitize_filename("/root/secret.txt") == "secret.txt"

    def test_sanitize_filename_strips_control_chars(self) -> None:
        result = _sanitize_filename("file\x00name.txt")
        assert "\x00" not in result

    def test_sanitize_filename_empty_fallback(self) -> None:
        assert _sanitize_filename("") == "attachment"

    def test_strip_cid_removes_brackets(self) -> None:
        assert _strip_cid("<img001@test>") == "img001@test"
        assert _strip_cid("img001@test") == "img001@test"
        assert _strip_cid("  <foo>  ") == "foo"


# ─────────────────────────────────────────────
# Unit tests — extract_attachments_to_dir
# ─────────────────────────────────────────────

class TestExtractAttachments:
    def test_saves_attachments_to_dir(self, tmp_path: Path) -> None:
        att = EmailAttachment(
            filename="doc.txt", content_type="text/plain",
            size_bytes=5, content_id=None, payload_bytes=b"hello",
        )
        parsed = ParsedEmail(
            subject="X", from_addr="a@b.com", to_addr="c@d.com",
            cc_addr="", date="", html_body=None, text_body=None,
            inline_images={}, attachments=[att],
        )
        out_dir = tmp_path / "atts"
        saved = extract_attachments_to_dir(parsed, out_dir)
        assert len(saved) == 1
        assert saved[0].read_bytes() == b"hello"

    def test_avoids_overwrite_with_counter(self, tmp_path: Path) -> None:
        att = EmailAttachment(
            filename="doc.txt", content_type="text/plain",
            size_bytes=3, content_id=None, payload_bytes=b"abc",
        )
        parsed = ParsedEmail(
            subject="X", from_addr="a@b.com", to_addr="c@d.com",
            cc_addr="", date="", html_body=None, text_body=None,
            inline_images={}, attachments=[att, att],
        )
        out_dir = tmp_path / "atts"
        saved = extract_attachments_to_dir(parsed, out_dir)
        assert len(saved) == 2
        names = {p.name for p in saved}
        assert "doc.txt" in names
        assert "doc_1.txt" in names


# ─────────────────────────────────────────────
# Integration tests — require weasyprint + Jinja2
# ─────────────────────────────────────────────

pytest_plugins: list[str] = []


def _weasyprint_available() -> bool:
    try:
        import weasyprint  # noqa: F401
        import jinja2  # noqa: F401
        return True
    except ImportError:
        return False


integration = pytest.mark.skipif(
    not _weasyprint_available(),
    reason="weasyprint and/or Jinja2 not installed",
)


@integration
class TestIntegration:
    def test_convert_plain_text_eml(self, tmp_path: Path) -> None:
        eml_path = _write_eml(tmp_path, "msg.eml", _make_plain_eml())
        out_pdf = tmp_path / "msg.pdf"
        convert_batch(str(eml_path), str(out_pdf))
        assert out_pdf.exists()
        assert out_pdf.stat().st_size > 100

    def test_convert_html_eml(self, tmp_path: Path) -> None:
        eml_path = _write_eml(tmp_path, "msg.eml", _make_html_eml())
        out_pdf = tmp_path / "msg.pdf"
        convert_batch(str(eml_path), str(out_pdf))
        assert out_pdf.exists()

    def test_batch_directory_conversion(self, tmp_path: Path) -> None:
        emails_dir = tmp_path / "emails"
        emails_dir.mkdir()
        for i in range(3):
            _write_eml(emails_dir, f"msg{i}.eml", _make_plain_eml(subject=f"Email {i}"))
        pdfs_dir = tmp_path / "pdfs"
        total, success = convert_batch(str(emails_dir), str(pdfs_dir))
        assert total == 3
        assert success == 3
        assert len(list(pdfs_dir.glob("*.pdf"))) == 3

    def test_cli_main_single_file(self, tmp_path: Path) -> None:
        eml_path = _write_eml(tmp_path, "msg.eml", _make_plain_eml())
        out_pdf = tmp_path / "out.pdf"
        result = main([str(eml_path), str(out_pdf)])
        assert result == 0
        assert out_pdf.exists()

    def test_cli_main_missing_input_returns_error(self) -> None:
        result = main(["/nonexistent/msg.eml"])
        assert result == 1

    def test_extract_attachments_flag(self, tmp_path: Path) -> None:
        eml_path = _write_eml(
            tmp_path, "msg.eml",
            _make_eml_with_attachment(b"data", "report.pdf"),
        )
        out_pdf = tmp_path / "msg.pdf"
        convert_batch(str(eml_path), str(out_pdf), extract_attachments=True)
        att_dir = tmp_path / "msg_attachments"
        assert att_dir.exists()
        assert (att_dir / "report.pdf").exists()
