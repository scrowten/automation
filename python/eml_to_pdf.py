#!/usr/bin/env python3
"""
EML to PDF Converter — converts email (.eml) files to PDF documents locally.

All conversion happens entirely on your machine. No data is sent to any
external server or cloud service. Your emails stay private.

Requirements:
    pip install weasyprint Jinja2

    # System libraries required by weasyprint:
    # Ubuntu/Debian:
    #   sudo apt install libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf-2.0-0
    # macOS:
    #   brew install pango
    # Fedora/RHEL:
    #   sudo dnf install pango gdk-pixbuf2

Usage examples:
    # Convert a single EML file (output: message.pdf)
    python eml_to_pdf.py message.eml

    # Convert with explicit output path
    python eml_to_pdf.py message.eml output.pdf

    # Batch convert a directory of EML files
    python eml_to_pdf.py ./emails/ ./pdfs/

    # Convert and also extract attachments to disk
    python eml_to_pdf.py message.eml output.pdf --extract-attachments

    # Verbose output
    python eml_to_pdf.py ./emails/ ./pdfs/ --verbose
"""

import argparse
import base64
import email
import email.header
import email.policy
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path


# ─────────────────────────────────────────────
# Data structures
# ─────────────────────────────────────────────

@dataclass(frozen=True)
class EmailAttachment:
    filename: str
    content_type: str
    size_bytes: int
    content_id: str | None        # set for inline images (cid:xxx)
    payload_bytes: bytes


@dataclass(frozen=True)
class ParsedEmail:
    subject: str
    from_addr: str
    to_addr: str
    cc_addr: str
    date: str
    html_body: str | None
    text_body: str | None
    inline_images: dict[str, EmailAttachment]   # keyed by Content-ID (stripped of <>)
    attachments: list[EmailAttachment]


# ─────────────────────────────────────────────
# EML parsing
# ─────────────────────────────────────────────

def _decode_header_value(raw: str | None) -> str:
    """Decode an RFC 2047 encoded header value (e.g. =?UTF-8?B?...?=) to str."""
    if not raw:
        return ""
    parts = email.header.decode_header(raw)
    decoded_parts = []
    for part, charset in parts:
        if isinstance(part, bytes):
            decoded_parts.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            decoded_parts.append(part)
    return "".join(decoded_parts)


def _decode_payload(part: email.message.Message) -> bytes:
    """Return decoded payload bytes for a MIME part."""
    payload = part.get_payload(decode=True)
    return payload if isinstance(payload, bytes) else b""


def _decode_text_payload(part: email.message.Message) -> str:
    """Decode a text MIME part to str using its declared charset."""
    raw = _decode_payload(part)
    charset = part.get_param("charset") or "utf-8"
    return raw.decode(charset, errors="replace")


def _strip_cid(content_id: str) -> str:
    """Remove angle brackets from a Content-ID value: <foo@bar> → foo@bar."""
    return content_id.strip().lstrip("<").rstrip(">")


def parse_eml(file_path: Path) -> ParsedEmail:
    """Parse an .eml file into a ParsedEmail dataclass.

    Handles: multipart/mixed, multipart/alternative, multipart/related,
    nested multipart, inline images (CID), RFC 2047 encoded headers,
    non-UTF-8 charsets, and malformed MIME structures.
    """
    try:
        with open(file_path, "rb") as fh:
            msg = email.message_from_binary_file(fh, policy=email.policy.compat32)
    except OSError as exc:
        raise FileNotFoundError(f"Cannot open '{file_path}': {exc}") from exc
    except Exception as exc:
        raise ValueError(f"Failed to parse '{file_path}' as EML: {exc}") from exc

    subject = _decode_header_value(msg.get("Subject"))
    from_addr = _decode_header_value(msg.get("From"))
    to_addr = _decode_header_value(msg.get("To"))
    cc_addr = _decode_header_value(msg.get("Cc"))
    date = _decode_header_value(msg.get("Date"))

    html_body: str | None = None
    text_body: str | None = None
    inline_images: dict[str, EmailAttachment] = {}
    attachments: list[EmailAttachment] = []

    # Track whether we have found the preferred body in a multipart/alternative
    # context. Once an HTML body is found, we stop accepting plain-text bodies.
    _html_found = False

    for part in msg.walk():
        content_type = part.get_content_type()
        disposition = part.get("Content-Disposition", "")
        content_id_raw = part.get("Content-ID")

        # Skip multipart containers — we process their leaves
        if part.get_content_maintype() == "multipart":
            continue

        # Inline images are identified by Content-ID header
        if content_id_raw:
            cid = _strip_cid(content_id_raw)
            payload = _decode_payload(part)
            if payload:
                filename = part.get_filename() or cid
                inline_images[cid] = EmailAttachment(
                    filename=filename,
                    content_type=content_type,
                    size_bytes=len(payload),
                    content_id=cid,
                    payload_bytes=payload,
                )
            continue

        # Attachments
        if "attachment" in disposition:
            payload = _decode_payload(part)
            raw_filename = part.get_filename() or "attachment"
            filename = _sanitize_filename(
                _decode_header_value(raw_filename) if not isinstance(raw_filename, str)
                else raw_filename
            )
            attachments.append(EmailAttachment(
                filename=filename,
                content_type=content_type,
                size_bytes=len(payload),
                content_id=None,
                payload_bytes=payload,
            ))
            continue

        # Body parts
        if content_type == "text/html" and not _html_found:
            html_body = _decode_text_payload(part)
            _html_found = True

        elif content_type == "text/plain" and text_body is None:
            text_body = _decode_text_payload(part)

    return ParsedEmail(
        subject=subject,
        from_addr=from_addr,
        to_addr=to_addr,
        cc_addr=cc_addr,
        date=date,
        html_body=html_body,
        text_body=text_body,
        inline_images=inline_images,
        attachments=attachments,
    )


# ─────────────────────────────────────────────
# CID resolution
# ─────────────────────────────────────────────

def resolve_cid_references(
    html: str,
    inline_images: dict[str, EmailAttachment],
    max_image_bytes: int = 5 * 1024 * 1024,
) -> str:
    """Replace cid:xxx references in HTML with base64 data URIs.

    Images larger than max_image_bytes are replaced with a placeholder.
    """
    def _replace(match: re.Match) -> str:
        quote = match.group(1)
        cid = match.group(2)
        normalized = _strip_cid(cid)

        img = inline_images.get(normalized) or inline_images.get(cid)
        if not img:
            return match.group(0)  # leave unchanged if not found

        if img.size_bytes > max_image_bytes:
            size_mb = img.size_bytes / (1024 * 1024)
            placeholder = (
                f"data:image/svg+xml;base64,"
                + base64.b64encode(
                    f'<svg xmlns="http://www.w3.org/2000/svg" width="200" height="60">'
                    f'<rect width="200" height="60" fill="#f0f0f0"/>'
                    f'<text x="10" y="35" font-size="12" fill="#888">'
                    f'[Image skipped: {size_mb:.1f} MB]</text></svg>'.encode()
                ).decode()
            )
            return f"src={quote}{placeholder}{quote}"

        encoded = base64.b64encode(img.payload_bytes).decode()
        data_uri = f"data:{img.content_type};base64,{encoded}"
        return f"src={quote}{data_uri}{quote}"

    # Match src="cid:..." or src='cid:...' with any CID format
    pattern = re.compile(r'src=(["\'])cid:([^"\'>\s]+)\1', re.IGNORECASE)
    return pattern.sub(_replace, html)


# ─────────────────────────────────────────────
# HTML assembly
# ─────────────────────────────────────────────

_EMAIL_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif;
    font-size: 13px;
    line-height: 1.6;
    color: #1a1a1a;
    background: #fff;
    padding: 24px;
    max-width: 860px;
    margin: 0 auto;
  }

  /* ── Header block ── */
  .email-header {
    background: #f6f8fa;
    border: 1px solid #d0d7de;
    border-radius: 6px;
    padding: 16px 20px;
    margin-bottom: 24px;
  }
  .email-header table { width: 100%; border-collapse: collapse; }
  .email-header td { padding: 3px 0; vertical-align: top; }
  .email-header .label {
    color: #57606a;
    font-weight: 600;
    white-space: nowrap;
    width: 70px;
    padding-right: 12px;
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }
  .email-header .value { color: #1a1a1a; word-break: break-word; }
  .subject-row .value {
    font-size: 16px;
    font-weight: 700;
    color: #0d1117;
  }

  /* ── Body ── */
  .email-body {
    padding-top: 8px;
  }
  .email-body img { max-width: 100%; height: auto; }
  .email-body a { color: #0969da; }

  /* Plain-text body */
  .email-body pre {
    font-family: "Courier New", Courier, monospace;
    font-size: 12.5px;
    white-space: pre-wrap;
    word-break: break-word;
    background: #f6f8fa;
    border: 1px solid #d0d7de;
    border-radius: 4px;
    padding: 16px;
  }

  /* ── Attachments list ── */
  .attachments-section {
    margin-top: 32px;
    border-top: 1px solid #d0d7de;
    padding-top: 16px;
  }
  .attachments-section h3 {
    font-size: 13px;
    font-weight: 600;
    color: #57606a;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    margin-bottom: 10px;
  }
  .attachments-section table {
    width: 100%;
    border-collapse: collapse;
    font-size: 12px;
  }
  .attachments-section th {
    text-align: left;
    padding: 6px 10px;
    background: #f6f8fa;
    border: 1px solid #d0d7de;
    color: #57606a;
    font-weight: 600;
  }
  .attachments-section td {
    padding: 6px 10px;
    border: 1px solid #d0d7de;
    color: #1a1a1a;
    word-break: break-all;
  }
  .attachments-section tr:nth-child(even) td { background: #f6f8fa; }
</style>
</head>
<body>

<div class="email-header">
  <table>
    {% if subject %}
    <tr class="subject-row">
      <td class="label">Subject</td>
      <td class="value">{{ subject }}</td>
    </tr>
    {% endif %}
    {% if from_addr %}
    <tr>
      <td class="label">From</td>
      <td class="value">{{ from_addr }}</td>
    </tr>
    {% endif %}
    {% if to_addr %}
    <tr>
      <td class="label">To</td>
      <td class="value">{{ to_addr }}</td>
    </tr>
    {% endif %}
    {% if cc_addr %}
    <tr>
      <td class="label">CC</td>
      <td class="value">{{ cc_addr }}</td>
    </tr>
    {% endif %}
    {% if date %}
    <tr>
      <td class="label">Date</td>
      <td class="value">{{ date }}</td>
    </tr>
    {% endif %}
  </table>
</div>

<div class="email-body">
  {% if html_body %}
    {{ html_body | safe }}
  {% elif text_body %}
    <pre>{{ text_body }}</pre>
  {% else %}
    <p style="color:#888;">(No message body)</p>
  {% endif %}
</div>

{% if attachments %}
<div class="attachments-section">
  <h3>Attachments ({{ attachments | length }})</h3>
  <table>
    <thead>
      <tr>
        <th>Filename</th>
        <th>Type</th>
        <th>Size</th>
      </tr>
    </thead>
    <tbody>
      {% for att in attachments %}
      <tr>
        <td>{{ att.filename }}</td>
        <td>{{ att.content_type }}</td>
        <td>{{ att.size_bytes | filesizeformat }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
</div>
{% endif %}

</body>
</html>
"""


def _filesizeformat(size: int) -> str:
    """Format byte count as human-readable size."""
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def build_html(
    parsed: ParsedEmail,
    max_image_bytes: int = 5 * 1024 * 1024,
) -> str:
    """Assemble a self-contained HTML document from a ParsedEmail."""
    try:
        from jinja2 import Environment
    except ImportError:
        raise RuntimeError("Jinja2 is not installed. Run:  pip install Jinja2")

    env = Environment(autoescape=False)
    env.filters["filesizeformat"] = _filesizeformat
    template = env.from_string(_EMAIL_TEMPLATE)

    html_body = parsed.html_body
    if html_body and parsed.inline_images:
        html_body = resolve_cid_references(html_body, parsed.inline_images, max_image_bytes)

    return template.render(
        subject=parsed.subject,
        from_addr=parsed.from_addr,
        to_addr=parsed.to_addr,
        cc_addr=parsed.cc_addr,
        date=parsed.date,
        html_body=html_body,
        text_body=parsed.text_body,
        attachments=parsed.attachments,
    )


# ─────────────────────────────────────────────
# PDF rendering
# ─────────────────────────────────────────────

def render_pdf(html: str, output_path: Path) -> None:
    """Render an HTML string to a PDF file using weasyprint."""
    try:
        import weasyprint
    except ImportError:
        raise RuntimeError(
            "weasyprint is not installed. Run:  pip install weasyprint\n"
            "  System deps (Ubuntu): sudo apt install libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf-2.0-0\n"
            "  System deps (macOS):  brew install pango"
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        weasyprint.HTML(string=html).write_pdf(str(output_path))
    except Exception as exc:
        raise RuntimeError(f"PDF rendering failed for '{output_path}': {exc}") from exc


# ─────────────────────────────────────────────
# Attachment extraction
# ─────────────────────────────────────────────

def _sanitize_filename(name: str) -> str:
    """Strip directory components and dangerous characters from a filename."""
    # Take only the final path component to prevent path traversal
    name = Path(name).name
    # Remove null bytes and other control characters
    name = re.sub(r"[\x00-\x1f\x7f]", "_", name)
    return name or "attachment"


def extract_attachments_to_dir(parsed: ParsedEmail, output_dir: Path) -> list[Path]:
    """Save all non-inline attachments to output_dir. Returns saved file paths."""
    saved: list[Path] = []
    output_dir.mkdir(parents=True, exist_ok=True)

    for att in parsed.attachments:
        dest = output_dir / att.filename
        # Avoid silently overwriting: append counter if needed
        counter = 1
        while dest.exists():
            stem = Path(att.filename).stem
            suffix = Path(att.filename).suffix
            dest = output_dir / f"{stem}_{counter}{suffix}"
            counter += 1

        dest.write_bytes(att.payload_bytes)
        saved.append(dest)

    return saved


# ─────────────────────────────────────────────
# Single-file orchestrator
# ─────────────────────────────────────────────

def convert_eml_to_pdf(
    input_path: Path,
    output_path: Path,
    extract_attachments: bool = False,
    max_image_mb: float = 5.0,
    verbose: bool = False,
) -> None:
    """Parse an EML file and write a PDF to output_path."""
    max_image_bytes = int(max_image_mb * 1024 * 1024)

    if verbose:
        print(f"  Parsing  : {input_path}")

    parsed = parse_eml(input_path)
    html = build_html(parsed, max_image_bytes=max_image_bytes)
    render_pdf(html, output_path)

    if verbose:
        inline_count = len(parsed.inline_images)
        att_count = len(parsed.attachments)
        print(
            f"  Saved    : {output_path}  "
            f"(inline images: {inline_count}, attachments: {att_count})"
        )

    if extract_attachments and parsed.attachments:
        att_dir = output_path.parent / (output_path.stem + "_attachments")
        saved = extract_attachments_to_dir(parsed, att_dir)
        if verbose:
            for p in saved:
                print(f"  Extracted: {p}")


# ─────────────────────────────────────────────
# Batch processing
# ─────────────────────────────────────────────

def convert_batch(
    input_path: str,
    output_path: str | None,
    extract_attachments: bool = False,
    max_image_mb: float = 5.0,
    verbose: bool = False,
) -> tuple[int, int]:
    """Convert one EML file or a directory of EML files.

    Returns:
        (total_files, successful_conversions)
    """
    inp = Path(input_path)

    if inp.is_file():
        if inp.suffix.lower() != ".eml":
            raise ValueError(f"Input file is not an .eml file: '{inp}'")

        out = Path(output_path) if output_path else inp.with_suffix(".pdf")

        try:
            convert_eml_to_pdf(inp, out, extract_attachments, max_image_mb, verbose)
        except Exception as exc:
            raise RuntimeError(f"Failed to convert '{inp}': {exc}") from exc

        return 1, 1

    elif inp.is_dir():
        eml_files = sorted(inp.glob("*.eml"))
        if not eml_files:
            eml_files = sorted(inp.glob("**/*.eml"))
        if not eml_files:
            raise ValueError(f"No .eml files found in '{inp}'.")

        out_root = Path(output_path) if output_path else inp / "converted"

        total = len(eml_files)
        success = 0

        for eml_file in eml_files:
            relative = eml_file.relative_to(inp)
            out_file = out_root / relative.with_suffix(".pdf")

            try:
                convert_eml_to_pdf(eml_file, out_file, extract_attachments, max_image_mb, verbose)
                success += 1
            except Exception as exc:
                print(f"\n  Warning: skipped '{eml_file.name}': {exc}", file=sys.stderr)

        return total, success

    else:
        raise FileNotFoundError(f"Input not found: '{input_path}'")


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convert EML email files to PDF — runs fully locally, no data leaves your machine.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python eml_to_pdf.py message.eml
  python eml_to_pdf.py message.eml output.pdf
  python eml_to_pdf.py ./emails/ ./pdfs/
  python eml_to_pdf.py message.eml output.pdf --extract-attachments
  python eml_to_pdf.py ./emails/ ./pdfs/ --verbose
        """,
    )

    parser.add_argument(
        "input",
        metavar="INPUT",
        help="Path to an .eml file or a directory containing .eml files.",
    )
    parser.add_argument(
        "output",
        metavar="OUTPUT",
        nargs="?",
        default=None,
        help=(
            "Output PDF file or directory. "
            "Defaults to <input>.pdf for single files, "
            "or <input>/converted/ for directories."
        ),
    )
    parser.add_argument(
        "--extract-attachments",
        action="store_true",
        help=(
            "Save email attachments to a <output_stem>_attachments/ "
            "directory alongside the PDF."
        ),
    )
    parser.add_argument(
        "--max-image-size",
        type=float,
        default=5.0,
        metavar="MB",
        help=(
            "Skip inline images larger than this size in MB to avoid memory issues "
            "(default: 5). Skipped images are replaced with a placeholder."
        ),
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print progress messages.",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.max_image_size <= 0:
        parser.error("--max-image-size must be a positive number.")

    print("=" * 54)
    print("  EML to PDF Converter")
    print("  Runs 100% locally — your emails stay private.")
    print("=" * 54)
    print(f"  Input         : {args.input}")
    print(f"  Output        : {args.output or '(auto)'}")
    print(f"  Extract att.  : {'yes' if args.extract_attachments else 'no'}")
    print(f"  Max image     : {args.max_image_size} MB")
    print()

    try:
        total, success = convert_batch(
            input_path=args.input,
            output_path=args.output,
            extract_attachments=args.extract_attachments,
            max_image_mb=args.max_image_size,
            verbose=args.verbose,
        )
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        print(f"\nError: {exc}", file=sys.stderr)
        return 1

    if total == 1:
        print(f"\n  Done! Converted {success}/{total} file.\n")
    else:
        print(f"\n  Done! Converted {success}/{total} files.\n")

    return 0 if success > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
