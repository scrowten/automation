#!/usr/bin/env python3
"""
Image Compressor — batch compress, resize, and convert images.

Requirements:
    pip install Pillow

Usage examples:
    # Compress a single image (output to ./compressed/)
    python compress_img.py photo.jpg

    # Compress with explicit output path
    python compress_img.py photo.jpg output.jpg

    # Compress all images in a directory
    python compress_img.py ./photos/ ./compressed/

    # Resize to max 1280px wide, 80% quality
    python compress_img.py photo.jpg output.jpg --max-width 1280 --quality 80

    # Convert to WebP
    python compress_img.py photo.jpg output.webp --format webp

    # Strip EXIF metadata (privacy)
    python compress_img.py photo.jpg output.jpg --strip-exif

    # Batch directory, recursive, dry run first
    python compress_img.py ./photos/ ./out/ --recursive --dry-run

    # Full example
    python compress_img.py ./photos/ ./compressed/ --max-width 1920 --quality 75 --strip-exif --recursive
"""

import argparse
import os
import sys
from pathlib import Path

SUPPORTED_INPUT_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".tif", ".gif"}
FORMAT_TO_EXT = {"jpg": ".jpg", "jpeg": ".jpg", "png": ".png", "webp": ".webp"}


def _output_path_for(
    input_file: Path,
    input_root: Path,
    output_root: Path,
    target_format: str | None,
) -> Path:
    """Compute the output file path mirroring the input directory structure."""
    relative = input_file.relative_to(input_root)
    out = output_root / relative

    if target_format:
        out = out.with_suffix(FORMAT_TO_EXT[target_format])

    return out


def compress_image(
    input_path: Path,
    output_path: Path,
    max_width: int | None,
    max_height: int | None,
    quality: int,
    target_format: str | None,
    strip_exif: bool,
    dry_run: bool,
    verbose: bool,
) -> tuple[int, int]:
    """Compress, resize, and/or convert a single image.

    Returns:
        (original_size_bytes, output_size_bytes) — both 0 in dry-run mode.
    """
    from PIL import Image

    original_size = input_path.stat().st_size

    if dry_run:
        label = f"[dry-run] {input_path} → {output_path}"
        if max_width or max_height:
            label += f"  (resize max {max_width}×{max_height})"
        if target_format:
            label += f"  (→{target_format.upper()})"
        if verbose:
            print(f"  {label}")
        return original_size, 0

    img = Image.open(input_path)

    # Determine save format
    fmt = (target_format or input_path.suffix.lstrip(".").lower()).replace("jpg", "jpeg")
    if fmt == "tif":
        fmt = "tiff"

    # Convert mode for format compatibility
    if fmt == "jpeg" and img.mode in ("RGBA", "P", "LA"):
        background = Image.new("RGB", img.size, (255, 255, 255))
        if img.mode in ("RGBA", "LA"):
            background.paste(img, mask=img.split()[-1])
        else:
            background.paste(img)
        img = background
    elif fmt in ("png", "webp") and img.mode not in ("RGB", "RGBA", "L", "LA", "P"):
        img = img.convert("RGBA")

    # Resize maintaining aspect ratio
    if max_width or max_height:
        orig_w, orig_h = img.size
        new_w, new_h = orig_w, orig_h

        if max_width and orig_w > max_width:
            new_w = max_width
            new_h = int(orig_h * max_width / orig_w)

        if max_height and new_h > max_height:
            new_h = max_height
            new_w = int(new_w * max_height / new_h)

        if (new_w, new_h) != (orig_w, orig_h):
            img = img.resize((new_w, new_h), Image.LANCZOS)

    # Strip EXIF by creating a fresh image (no metadata)
    if strip_exif:
        clean = Image.new(img.mode, img.size)
        clean.paste(img)
        img = clean

    output_path.parent.mkdir(parents=True, exist_ok=True)

    save_kwargs: dict = {}
    if fmt == "jpeg":
        save_kwargs["quality"] = quality
        save_kwargs["optimize"] = True
    elif fmt == "webp":
        save_kwargs["quality"] = quality
        save_kwargs["method"] = 6
    elif fmt == "png":
        save_kwargs["optimize"] = True

    img.save(output_path, format=fmt.upper(), **save_kwargs)

    output_size = output_path.stat().st_size

    if verbose:
        ratio = (1 - output_size / original_size) * 100 if original_size else 0
        print(
            f"  {input_path.name} → {output_path.name}  "
            f"({_fmt_bytes(original_size)} → {_fmt_bytes(output_size)}, "
            f"{ratio:.1f}% smaller)"
        )

    return original_size, output_size


def _fmt_bytes(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def _collect_images(root: Path, recursive: bool) -> list[Path]:
    if recursive:
        return [
            p for p in root.rglob("*")
            if p.is_file() and p.suffix.lower() in SUPPORTED_INPUT_EXTS
        ]
    return [
        p for p in root.iterdir()
        if p.is_file() and p.suffix.lower() in SUPPORTED_INPUT_EXTS
    ]


def compress_batch(
    input_path: str,
    output_path: str | None,
    max_width: int | None,
    max_height: int | None,
    quality: int,
    target_format: str | None,
    strip_exif: bool,
    recursive: bool,
    dry_run: bool,
    verbose: bool,
) -> tuple[int, int, int]:
    """Process one file or an entire directory.

    Returns:
        (files_processed, total_original_bytes, total_output_bytes)
    """
    from PIL import Image  # validate Pillow is available

    inp = Path(input_path)

    if inp.is_file():
        if inp.suffix.lower() not in SUPPORTED_INPUT_EXTS:
            raise ValueError(f"Unsupported image format: '{inp.suffix}'")

        if output_path:
            out = Path(output_path)
        else:
            out = Path("compressed") / inp.name
            if target_format:
                out = out.with_suffix(FORMAT_TO_EXT[target_format])

        orig, compressed = compress_image(
            inp, out, max_width, max_height, quality,
            target_format, strip_exif, dry_run, verbose,
        )
        return 1, orig, compressed

    elif inp.is_dir():
        out_root = Path(output_path) if output_path else Path("compressed")
        images = _collect_images(inp, recursive)

        if not images:
            raise ValueError(f"No supported image files found in '{inp}'.")

        total_orig = total_out = 0
        for img_file in images:
            out_file = _output_path_for(img_file, inp, out_root, target_format)
            orig, compressed = compress_image(
                img_file, out_file, max_width, max_height, quality,
                target_format, strip_exif, dry_run, verbose,
            )
            total_orig += orig
            total_out += compressed

        return len(images), total_orig, total_out

    else:
        raise FileNotFoundError(f"Input not found: '{input_path}'")


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Batch compress, resize, and convert images.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Supported input formats:  jpg, jpeg, png, webp, bmp, tiff, gif

Examples:
  python compress_img.py photo.jpg
  python compress_img.py photo.jpg output.jpg --quality 75
  python compress_img.py photo.jpg output.webp --format webp
  python compress_img.py ./photos/ ./compressed/ --max-width 1920 --strip-exif
  python compress_img.py ./photos/ ./out/ --recursive --dry-run
        """,
    )

    parser.add_argument(
        "input",
        metavar="INPUT",
        help="Path to an image file or a directory of images.",
    )
    parser.add_argument(
        "output",
        metavar="OUTPUT",
        nargs="?",
        default=None,
        help=(
            "Output file or directory. "
            "Defaults to ./compressed/ when INPUT is a directory, "
            "or ./compressed/<filename> when INPUT is a file."
        ),
    )
    parser.add_argument(
        "--format", "-f",
        dest="fmt",
        choices=["jpg", "jpeg", "png", "webp"],
        default=None,
        metavar="FORMAT",
        help="Convert all images to this format: jpg, png, webp.",
    )
    parser.add_argument(
        "--max-width",
        type=int,
        default=None,
        metavar="PX",
        help="Scale down images wider than this (maintains aspect ratio).",
    )
    parser.add_argument(
        "--max-height",
        type=int,
        default=None,
        metavar="PX",
        help="Scale down images taller than this (maintains aspect ratio).",
    )
    parser.add_argument(
        "--quality",
        type=int,
        default=80,
        metavar="1-100",
        help="Output quality for jpg/webp (1-100). Default: 80.",
    )
    parser.add_argument(
        "--strip-exif",
        action="store_true",
        help="Remove EXIF/metadata from output images.",
    )
    parser.add_argument(
        "--recursive", "-r",
        action="store_true",
        help="Process subdirectories recursively (directory input only).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without writing any files.",
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

    if not 1 <= args.quality <= 100:
        parser.error(f"--quality must be between 1 and 100, got {args.quality}.")

    fmt = args.fmt.replace("jpeg", "jpg") if args.fmt else None

    print("=" * 54)
    print("  Image Compressor")
    print("=" * 54)
    print(f"  Input         : {args.input}")
    print(f"  Output        : {args.output or './compressed/'}")
    if fmt:
        print(f"  Format        : {fmt.upper()}")
    if args.max_width or args.max_height:
        print(f"  Max size      : {args.max_width or '—'} × {args.max_height or '—'} px")
    print(f"  Quality       : {args.quality}")
    print(f"  Strip EXIF    : {'yes' if args.strip_exif else 'no'}")
    if args.dry_run:
        print("  Mode          : DRY RUN (no files will be written)")
    print()

    try:
        count, total_orig, total_out = compress_batch(
            input_path=args.input,
            output_path=args.output,
            max_width=args.max_width,
            max_height=args.max_height,
            quality=args.quality,
            target_format=fmt,
            strip_exif=args.strip_exif,
            recursive=args.recursive,
            dry_run=args.dry_run,
            verbose=args.verbose,
        )
    except (FileNotFoundError, ValueError, RuntimeError) as e:
        print(f"\nError: {e}", file=sys.stderr)
        return 1
    except ImportError as e:
        print(f"\nError: {e}", file=sys.stderr)
        return 1

    if args.dry_run:
        print(f"\n  [dry-run] Would process {count} file(s).\n")
    else:
        saved = total_orig - total_out
        ratio = (saved / total_orig * 100) if total_orig else 0
        print(
            f"\n  Done! {count} file(s) compressed. "
            f"Saved {_fmt_bytes(saved)} ({ratio:.1f}%)\n"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
