#!/usr/bin/env python3
"""
HTML to PDF Converter — converts a folder of numbered HTML slides into one merged PDF.

Requirements:
    pip install pypdf

Browser (one of the following must be installed):
    - Google Chrome / Chromium
    - Microsoft Edge

Usage examples:
    # Defaults: current folder → ../sharing_session_final.pdf, slide size, landscape
    python convert_to_pdf.py

    # Custom input/output
    python convert_to_pdf.py --input ./slides --output ./out/deck.pdf

    # A4 portrait
    python convert_to_pdf.py --size a4 --orientation portrait

    # Custom size (width x height in inches)
    python convert_to_pdf.py --size 11x8.5

    # Specific browser binary
    python convert_to_pdf.py --browser "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

    # Extra CDN wait time (ms) for slow connections
    python convert_to_pdf.py --wait 8000
"""

import argparse
import os
import re
import glob
import shutil
import subprocess
import sys
import tempfile
import platform
from pathlib import Path


# ─────────────────────────────────────────────
# 1. Known paper sizes  (width_in, height_in)  — always in portrait order
# ─────────────────────────────────────────────

PAPER_SIZES = {
    "slide":  (13.3333, 7.5),   # 1280×720 px @ 96 dpi  (16:9 presentation)
    "a4":     (8.2677, 11.6929),
    "letter": (8.5,    11.0),
    "legal":  (8.5,    14.0),
    "a3":     (11.6929, 16.5354),
    "a5":     (5.8268,  8.2677),
}


def resolve_size(size_arg: str, orientation: str):
    """
    Return (width_in, height_in) already adjusted for orientation.
    size_arg can be a named preset (e.g. 'a4') or 'WxH' in inches (e.g. '11x8.5').
    """
    key = size_arg.lower().strip()

    if key in PAPER_SIZES:
        w, h = PAPER_SIZES[key]
    else:
        # Try parsing WxH
        m = re.match(r"^([\d.]+)[x×]([\d.]+)$", key, re.IGNORECASE)
        if not m:
            raise ValueError(
                f"Unknown size '{size_arg}'. Use a preset ({', '.join(PAPER_SIZES)}) "
                "or WxH in inches, e.g. '13.33x7.5'."
            )
        w, h = float(m.group(1)), float(m.group(2))

    # For named presets, portrait order is (narrow, tall); swap for landscape.
    # For custom WxH, trust the user's order but still honour --orientation.
    if orientation == "landscape" and w < h:
        w, h = h, w
    elif orientation == "portrait" and w > h:
        w, h = h, w

    return w, h


# ─────────────────────────────────────────────
# 2. Find the browser
# ─────────────────────────────────────────────

def find_chrome():
    """Return the path to a Chrome/Chromium/Edge executable, or None."""
    system = platform.system()

    if system == "Windows":
        candidates = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Chromium\Application\chrome.exe",
        ]
    elif system == "Darwin":
        candidates = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        ]
    else:  # Linux
        candidates = [
            "google-chrome", "google-chrome-stable",
            "chromium-browser", "chromium", "microsoft-edge",
        ]

    for c in candidates:
        if os.path.isabs(c):
            if os.path.isfile(c):
                return c
        else:
            found = shutil.which(c)
            if found:
                return found

    return None


# ─────────────────────────────────────────────
# 3. Sort HTML files numerically by leading digit
# ─────────────────────────────────────────────

def numeric_key(path):
    name = Path(path).stem
    m = re.match(r"^(\d+)", name)
    return int(m.group(1)) if m else float("inf")


def get_sorted_html_files(directory):
    html_files = glob.glob(os.path.join(directory, "*.html"))
    slide_files = [f for f in html_files if re.match(r"^\d+", Path(f).stem)]
    return sorted(slide_files, key=numeric_key)


# ─────────────────────────────────────────────
# 4. Convert a single HTML → PDF via Chrome
# ─────────────────────────────────────────────

def html_to_pdf(chrome_path, html_path, pdf_path, width_in, height_in, wait_ms):
    """
    Render one HTML file to PDF using Chrome headless.
    Injects @page CSS to enforce exact page dimensions and orientation.
    """
    page_css = (
        "<style>"
        "@page {"
        f"  size: {width_in:.4f}in {height_in:.4f}in;"
        "  margin: 0;"
        "}"
        "html, body {"
        "  margin: 0 !important;"
        "  padding: 0 !important;"
        "}"
        "</style>"
    )

    with open(html_path, "r", encoding="utf-8", errors="replace") as f:
        html_content = f.read()

    if "</head>" in html_content:
        html_content = html_content.replace("</head>", f"{page_css}\n</head>", 1)
    else:
        html_content = page_css + html_content

    tmp_html = pdf_path.replace(".pdf", "_tmp.html")
    with open(tmp_html, "w", encoding="utf-8") as f:
        f.write(html_content)

    html_uri = Path(tmp_html).resolve().as_uri()

    cmd = [
        chrome_path,
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--run-all-compositor-stages-before-draw",
        f"--virtual-time-budget={wait_ms}",
        "--no-margins",
        "--print-to-pdf-no-header",
        f"--paper-width={width_in:.4f}",
        f"--paper-height={height_in:.4f}",
        f"--print-to-pdf={pdf_path}",
        html_uri,
    ]

    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
    finally:
        if os.path.isfile(tmp_html):
            os.remove(tmp_html)

    if result.returncode != 0 or not os.path.isfile(pdf_path):
        err = result.stderr.decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Chrome failed for {html_path}.\n"
            f"Return code: {result.returncode}\n"
            f"stderr: {err[:500]}"
        )


# ─────────────────────────────────────────────
# 5. Merge PDFs
# ─────────────────────────────────────────────

def merge_pdfs(pdf_files, output_path):
    try:
        from pypdf import PdfWriter
    except ImportError:
        raise ImportError("pypdf is not installed. Run:  pip install pypdf")

    writer = PdfWriter()
    for pdf in pdf_files:
        writer.append(pdf)

    with open(output_path, "wb") as f:
        writer.write(f)

    print(f"\n✅  Saved merged PDF → {output_path}")


# ─────────────────────────────────────────────
# 6. Argument parser
# ─────────────────────────────────────────────

def build_parser():
    script_dir = Path(__file__).parent.resolve()
    default_output = str(script_dir.parent / "sharing_session_final.pdf")

    parser = argparse.ArgumentParser(
        description="Convert numbered HTML slides to a single merged PDF.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Size presets:  slide (16:9 default), a4, letter, legal, a3, a5
               or supply WxH in inches, e.g.  --size 11x8.5

Examples:
  python convert_to_pdf.py
  python convert_to_pdf.py --input ./slides --output ./deck.pdf
  python convert_to_pdf.py --size a4 --orientation portrait
  python convert_to_pdf.py --size 11x8.5 --orientation landscape
  python convert_to_pdf.py --wait 8000
        """,
    )

    parser.add_argument(
        "--input", "-i",
        default=str(script_dir),
        metavar="DIR",
        help="Folder containing the numbered HTML files. (default: script directory)",
    )
    parser.add_argument(
        "--output", "-o",
        default=default_output,
        metavar="FILE",
        help="Output PDF path. (default: <parent folder>/sharing_session_final.pdf)",
    )
    parser.add_argument(
        "--size", "-s",
        default="slide",
        metavar="PRESET|WxH",
        help="Page size preset or custom WxH in inches. (default: slide = 13.33×7.5 in)",
    )
    parser.add_argument(
        "--orientation", "-r",
        choices=["landscape", "portrait"],
        default="landscape",
        help="Page orientation. (default: landscape)",
    )
    parser.add_argument(
        "--browser", "-b",
        default=None,
        metavar="PATH",
        help="Path to Chrome/Chromium/Edge binary. Auto-detected if omitted.",
    )
    parser.add_argument(
        "--wait", "-w",
        type=int,
        default=4000,
        metavar="MS",
        help="Milliseconds to wait for CDN resources per slide. (default: 4000)",
    )

    return parser


# ─────────────────────────────────────────────
# 7. Main
# ─────────────────────────────────────────────

def main():
    parser = build_parser()
    args = parser.parse_args()

    # ── resolve page dimensions ───────────────────────────
    try:
        width_in, height_in = resolve_size(args.size, args.orientation)
    except ValueError as e:
        parser.error(str(e))

    # ── resolve browser ───────────────────────────────────
    chrome = args.browser or os.environ.get("CHROME_PATH") or find_chrome()
    if not chrome:
        print("❌  No Chrome/Chromium/Edge browser found.")
        print("   Install Google Chrome or pass --browser /path/to/chrome")
        sys.exit(1)

    # ── print summary ─────────────────────────────────────
    print("=" * 62)
    print("  HTML → PDF Converter")
    print("=" * 62)
    print(f"  Input folder  : {args.input}")
    print(f"  Output PDF    : {args.output}")
    print(f"  Page size     : {width_in:.4f} × {height_in:.4f} in  ({args.size}, {args.orientation})")
    print(f"  CDN wait      : {args.wait} ms per slide")
    print(f"  Browser       : {chrome}")
    print()

    # ── collect + sort HTML files ─────────────────────────
    html_files = get_sorted_html_files(args.input)
    if not html_files:
        print(f"❌  No numbered HTML files found in: {args.input}")
        sys.exit(1)

    print(f"  Slides found  : {len(html_files)}")
    for f in html_files:
        print(f"    {Path(f).name}")
    print()

    # ── convert each HTML → PDF ───────────────────────────
    with tempfile.TemporaryDirectory() as tmpdir:
        pdf_files = []

        for i, html_file in enumerate(html_files, start=1):
            name = Path(html_file).stem
            pdf_out = os.path.join(tmpdir, f"{i:03d}_{name}.pdf")
            print(f"  [{i:>2}/{len(html_files)}] {Path(html_file).name} ...", end=" ", flush=True)

            try:
                html_to_pdf(chrome, html_file, pdf_out, width_in, height_in, args.wait)
                pdf_files.append(pdf_out)
                print("✓")
            except Exception as e:
                print(f"✗  ({e})")
                print("  Skipping and continuing...")

        if not pdf_files:
            print("\n❌  No slides were converted successfully.")
            sys.exit(1)

        # ── ensure output directory exists ────────────────
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)

        # ── merge ─────────────────────────────────────────
        print(f"\n  Merging {len(pdf_files)} PDFs...")
        merge_pdfs(pdf_files, args.output)

    print(f"\n  Done! {len(pdf_files)} of {len(html_files)} slides → {args.output}\n")


if __name__ == "__main__":
    main()
