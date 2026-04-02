#!/usr/bin/env python3
"""
HTML to Image Converter — renders an HTML file or URL to an image.

Requirements:
    pip install playwright Pillow
    playwright install chromium

Usage examples:
    # Basic: HTML file → PNG
    python html2img.py page.html output.png

    # Transparent background (PNG or WEBP only)
    python html2img.py page.html output.png --no-background

    # Specific format
    python html2img.py page.html output.jpg --format jpg

    # Screenshot a URL
    python html2img.py https://example.com screenshot.png

    # Full page capture at 2x resolution
    python html2img.py page.html output.png --full-page --scale 2.0

    # WEBP with quality control
    python html2img.py page.html output.webp --format webp --quality 85

    # Custom viewport size
    python html2img.py page.html output.png --width 1920 --height 1080
"""

import argparse
import re
import sys
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright, Error as PlaywrightError

    _PLAYWRIGHT_AVAILABLE = True
except ImportError:
    _PLAYWRIGHT_AVAILABLE = False
    PlaywrightError = Exception  # type: ignore[assignment,misc]


# ─────────────────────────────────────────────
# 1. Format constants
# ─────────────────────────────────────────────

# Maps canonical format name → (file extension, supports_transparency, playwright_native)
SUPPORTED_FORMATS: dict[str, tuple[str, bool, bool]] = {
    "png": (".png", True, True),
    "jpg": (".jpg", False, True),
    "jpeg": (".jpg", False, True),
    "webp": (".webp", True, False),
    "bmp": (".bmp", False, False),
    "tiff": (".tiff", True, False),
    "tif": (".tiff", True, False),
}

_EXT_TO_FORMAT: dict[str, str] = {
    ".png": "png",
    ".jpg": "jpg",
    ".jpeg": "jpeg",
    ".webp": "webp",
    ".bmp": "bmp",
    ".tiff": "tiff",
    ".tif": "tiff",
}


def infer_format_from_path(output_path: str) -> str:
    """Return the canonical format name inferred from the output file extension.

    Falls back to 'png' for unrecognized extensions.
    """
    ext = Path(output_path).suffix.lower()
    return _EXT_TO_FORMAT.get(ext, "png")


def _is_url(path: str) -> bool:
    return bool(re.match(r"^https?://", path, re.IGNORECASE))


# ─────────────────────────────────────────────
# 2. Validation
# ─────────────────────────────────────────────

def validate_args(
    input_path: str,
    output_path: str,
    fmt: str,
    no_background: bool,
    quality: int,
) -> list[str]:
    """Return a list of validation error messages (empty if all valid)."""
    errors: list[str] = []

    if fmt not in SUPPORTED_FORMATS:
        errors.append(
            f"Unsupported format '{fmt}'. Supported: {', '.join(SUPPORTED_FORMATS)}."
        )
        return errors  # further checks depend on a valid fmt

    _ext, supports_transparency, _native = SUPPORTED_FORMATS[fmt]

    if no_background and not supports_transparency:
        errors.append(
            f"--no-background is not supported for '{fmt}' (no alpha channel). "
            "Use png, webp, or tiff instead."
        )

    if not 1 <= quality <= 100:
        errors.append(f"--quality must be between 1 and 100, got {quality}.")

    if not _is_url(input_path):
        if not Path(input_path).is_file():
            errors.append(f"Input file not found: '{input_path}'.")

    return errors


# ─────────────────────────────────────────────
# 3. Core conversion
# ─────────────────────────────────────────────

def html_to_image(
    input_path: str,
    output_path: str,
    fmt: str,
    no_background: bool,
    width: int,
    height: int,
    full_page: bool,
    wait_ms: int,
    quality: int,
    scale: float,
    verbose: bool,
) -> None:
    """Render HTML (file or URL) to an image file.

    Args:
        input_path: Path to a local HTML file or an http(s) URL.
        output_path: Destination image file path.
        fmt: Canonical format name (png, jpg, webp, bmp, tiff).
        no_background: Omit the background, producing a transparent image.
        width: Viewport width in pixels.
        height: Viewport height in pixels.
        full_page: Capture the full scrollable page, not just the viewport.
        wait_ms: Additional milliseconds to wait after page load.
        quality: JPEG/WEBP quality (1-100); ignored for PNG.
        scale: Device scale factor (1.0 = normal, 2.0 = retina).
        verbose: Print progress messages.
    """
    if not _PLAYWRIGHT_AVAILABLE:
        raise RuntimeError(
            "playwright is not installed.\n"
            "Run:  pip install playwright && playwright install chromium"
        )

    _ext, supports_transparency, playwright_native = SUPPORTED_FORMATS[fmt]

    # Resolve the URL to navigate to
    if _is_url(input_path):
        url = input_path
    else:
        url = Path(input_path).resolve().as_uri()

    # Ensure output directory exists
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    if verbose:
        print(f"  Launching Chromium...")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": width, "height": height},
            device_scale_factor=scale,
        )
        page = context.new_page()

        if verbose:
            print(f"  Loading: {url}")

        try:
            page.goto(url, wait_until="networkidle", timeout=30_000)
        except PlaywrightError as e:
            raise RuntimeError(f"Failed to load '{input_path}': {e}") from e

        if wait_ms > 0:
            page.wait_for_timeout(wait_ms)

        if playwright_native:
            # PNG and JPEG are handled directly by Playwright
            screenshot_kwargs: dict = {
                "full_page": full_page,
                "type": "jpeg" if fmt in ("jpg", "jpeg") else "png",
                "omit_background": no_background and supports_transparency,
            }
            if fmt in ("jpg", "jpeg"):
                screenshot_kwargs["quality"] = quality

            if verbose:
                print(f"  Taking screenshot ({fmt.upper()})...")

            page.screenshot(path=output_path, **screenshot_kwargs)
        else:
            # Non-native formats: take PNG first, then convert with Pillow
            if verbose:
                print(f"  Taking screenshot (PNG intermediate)...")

            png_bytes = page.screenshot(
                full_page=full_page,
                type="png",
                omit_background=no_background and supports_transparency,
            )

            if verbose:
                print(f"  Converting to {fmt.upper()} via Pillow...")

            try:
                from PIL import Image
                import io
            except ImportError:
                raise RuntimeError(
                    "Pillow is not installed.\n"
                    "Run:  pip install Pillow"
                )

            img = Image.open(io.BytesIO(png_bytes))

            # Preserve or drop alpha depending on target format
            if supports_transparency:
                # WEBP, TIFF — keep RGBA
                if img.mode not in ("RGBA", "RGB"):
                    img = img.convert("RGBA")
            else:
                # BMP — flatten alpha onto white background
                if img.mode == "RGBA":
                    background = Image.new("RGB", img.size, (255, 255, 255))
                    background.paste(img, mask=img.split()[3])
                    img = background
                else:
                    img = img.convert("RGB")

            save_kwargs: dict = {}
            if fmt == "webp":
                save_kwargs["quality"] = quality
            elif fmt in ("tiff", "tif"):
                save_kwargs["compression"] = "tiff_lzw"

            img.save(output_path, **save_kwargs)

        browser.close()

    if verbose:
        print(f"  Saved → {output_path}")


# ─────────────────────────────────────────────
# 4. CLI
# ─────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convert an HTML file or URL to an image.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Supported formats:  png (default), jpg, webp, bmp, tiff

Examples:
  python html2img.py page.html output.png
  python html2img.py page.html output.png --no-background
  python html2img.py page.html output.jpg --format jpg --quality 90
  python html2img.py https://example.com screenshot.png
  python html2img.py page.html output.png --full-page --scale 2.0
  python html2img.py page.html output.png --width 1920 --height 1080
        """,
    )

    parser.add_argument(
        "input_path",
        metavar="INPUT",
        help="Path to an HTML file or an http(s) URL.",
    )
    parser.add_argument(
        "output_path",
        metavar="OUTPUT",
        help="Destination image file path (e.g. output.png).",
    )
    parser.add_argument(
        "--format", "-f",
        dest="fmt",
        default=None,
        metavar="FORMAT",
        help=(
            "Output image format: png, jpg, webp, bmp, tiff. "
            "Inferred from OUTPUT extension when omitted; defaults to png."
        ),
    )
    parser.add_argument(
        "--no-background",
        action="store_true",
        help="Remove the page background (transparent). Supported for png, webp, tiff only.",
    )
    parser.add_argument(
        "--width",
        type=int,
        default=1280,
        metavar="PX",
        help="Viewport width in pixels. (default: 1280)",
    )
    parser.add_argument(
        "--height",
        type=int,
        default=720,
        metavar="PX",
        help="Viewport height in pixels. (default: 720)",
    )
    parser.add_argument(
        "--full-page",
        action="store_true",
        help="Capture the full scrollable page, not just the viewport.",
    )
    parser.add_argument(
        "--wait",
        type=int,
        default=2000,
        metavar="MS",
        help="Extra milliseconds to wait after page load. (default: 2000)",
    )
    parser.add_argument(
        "--quality",
        type=int,
        default=90,
        metavar="1-100",
        help="Output quality for jpg/webp (1-100). Ignored for png. (default: 90)",
    )
    parser.add_argument(
        "--scale",
        type=float,
        default=1.0,
        metavar="FACTOR",
        help="Device scale factor; use 2.0 for high-DPI/retina output. (default: 1.0)",
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

    # Resolve format: explicit flag > inferred from extension > default png
    fmt = (args.fmt or infer_format_from_path(args.output_path)).lower()

    # Validate
    errors = validate_args(
        args.input_path,
        args.output_path,
        fmt,
        args.no_background,
        args.quality,
    )
    if errors:
        for err in errors:
            print(f"Error: {err}", file=sys.stderr)
        return 1

    # Summary banner
    _ext, supports_transparency, _native = SUPPORTED_FORMATS[fmt]
    print("=" * 54)
    print("  HTML → Image Converter")
    print("=" * 54)
    print(f"  Input         : {args.input_path}")
    print(f"  Output        : {args.output_path}")
    print(f"  Format        : {fmt.upper()}")
    print(f"  Viewport      : {args.width} × {args.height} px  (scale {args.scale}x)")
    print(f"  Full page     : {'yes' if args.full_page else 'no'}")
    print(f"  Transparent   : {'yes' if args.no_background else 'no'}")
    if fmt in ("jpg", "jpeg", "webp"):
        print(f"  Quality       : {args.quality}")
    print()

    try:
        html_to_image(
            input_path=args.input_path,
            output_path=args.output_path,
            fmt=fmt,
            no_background=args.no_background,
            width=args.width,
            height=args.height,
            full_page=args.full_page,
            wait_ms=args.wait,
            quality=args.quality,
            scale=args.scale,
            verbose=args.verbose,
        )
    except RuntimeError as e:
        print(f"\nError: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"\nUnexpected error: {e}", file=sys.stderr)
        return 1

    print(f"\n  Done! Image saved to: {args.output_path}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
