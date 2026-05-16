#!/usr/bin/env python3
"""
swap_bg.py — Swap background colour for Indonesian formal/ID photos.

Removes the existing background with AI (rembg) and replaces it with one of
the three standard Indonesian formal-photo colours:
  • merah  — red   (#CC0000)   → most common for government docs
  • biru   — blue  (#003399)   → KTP, SIM, passport photos
  • abu    — gray  (#808080)   → CV / job application photos

Standard Indonesian photo sizes (at 300 DPI) are also supported:
  • 2x3 cm  →  236 × 354 px
  • 3x4 cm  →  354 × 472 px   (default — most versatile)
  • 4x6 cm  →  472 × 709 px

Requirements:
    pip install rembg[cpu] Pillow onnxruntime

    # GPU (NVIDIA) — faster, needs CUDA + cuDNN:
    pip install rembg[gpu] Pillow onnxruntime-gpu

Usage examples:
    # Single photo → red background (default), saved to ./output/
    python swap_bg.py foto.jpg

    # Explicit colour + output path
    python swap_bg.py foto.jpg hasil.jpg --color biru

    # All three colours at once
    python swap_bg.py foto.jpg --all-colors

    # Batch directory — swap all photos to gray
    python swap_bg.py ./fotos/ ./hasil/ --color abu

    # Resize to 3×4 cm @ 300 DPI + strip EXIF
    python swap_bg.py foto.jpg --size 3x4 --strip-exif

    # Improve hair/edge quality (slower, uses alpha matting)
    python swap_bg.py foto.jpg --refine-edges

    # Full production run: batch, all colours, 3×4, strip EXIF, verbose
    python swap_bg.py ./fotos/ ./hasil/ --all-colors --size 3x4 --strip-exif --refine-edges -v

    # Dry run first to see what would happen
    python swap_bg.py ./fotos/ ./hasil/ --all-colors --dry-run -v
"""

import argparse
import io
import os
import sys
from pathlib import Path

# ─── Constants ────────────────────────────────────────────────────────────────

SUPPORTED_INPUT_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".tif"}

# Standard Indonesian formal-photo background colours
BG_COLORS: dict[str, tuple[int, int, int]] = {
    "merah": (204, 0,   0),    # Red  — paling umum untuk dokumen pemerintah
    "biru":  (0,   51, 153),   # Blue — KTP, SIM, paspor
    "abu":   (128, 128, 128),  # Gray — CV / lamaran kerja
}

# Standard Indonesian photo sizes (width_px, height_px) @ 300 DPI
# Formula: cm × 300 DPI / 2.54 cm/inch = pixels
PHOTO_SIZES: dict[str, tuple[int, int]] = {
    "2x3": (236, 354),   # 2 cm wide × 3 cm tall
    "3x4": (354, 472),   # 3 cm wide × 4 cm tall  ← default
    "4x6": (472, 709),   # 4 cm wide × 6 cm tall
}


# ─── Core image processing ────────────────────────────────────────────────────

def _load_rembg_session():
    """Create a rembg session using u2net_human_seg (portrait-optimised)."""
    try:
        from rembg import new_session
        # u2net_human_seg is trained specifically for portrait / ID photos.
        # It handles skin, hair, and clothing edges better than the default u2net.
        return new_session("u2net_human_seg")
    except ImportError:
        raise ImportError(
            "rembg is not installed.\n"
            "Install with:  pip install rembg[cpu] onnxruntime\n"
            "GPU (NVIDIA):  pip install rembg[gpu] onnxruntime-gpu"
        )


def remove_background(
    img,                   # PIL.Image
    session,               # rembg session (reused across calls)
    refine_edges: bool,
):
    """Return a PIL RGBA image with the background removed."""
    from rembg import remove

    if refine_edges:
        # Alpha matting: smoother transition at hair / fine-detail edges.
        # Thresholds tuned for typical studio portrait conditions.
        #   foreground_threshold=270  — treat bright pixels as definite foreground
        #   background_threshold=20   — treat dark pixels as definite background
        #   erode_size=11             — shrink the initial mask slightly before matting
        return remove(
            img,
            session=session,
            alpha_matting=True,
            alpha_matting_foreground_threshold=270,
            alpha_matting_background_threshold=20,
            alpha_matting_erode_size=11,
            post_process_mask=True,
        )
    else:
        # Standard removal — faster, good enough for clean studio shots
        return remove(img, session=session, post_process_mask=True)


def composite_background(
    fg_rgba,               # PIL RGBA image (foreground with alpha)
    color_name: str,
    target_size: tuple[int, int] | None,
    strip_exif: bool,
) -> "Image":
    """Paste the foreground onto a solid-colour background.

    Args:
        fg_rgba:      RGBA image with transparent background.
        color_name:   Key in BG_COLORS ('merah', 'biru', 'abu').
        target_size:  (width, height) in pixels, or None to keep original size.
        strip_exif:   If True, drop all metadata.

    Returns:
        RGB PIL image ready for saving as JPG.
    """
    from PIL import Image

    rgb = BG_COLORS[color_name]

    if target_size:
        # Resize the foreground (with its alpha) to fit the target size,
        # preserving aspect ratio and centring it on the canvas.
        fg_w, fg_h = fg_rgba.size
        tw, th = target_size

        scale = min(tw / fg_w, th / fg_h)
        new_w = int(fg_w * scale)
        new_h = int(fg_h * scale)

        fg_resized = fg_rgba.resize((new_w, new_h), Image.LANCZOS)

        canvas = Image.new("RGBA", (tw, th), (*rgb, 255))
        # Centre the resized foreground on the canvas
        paste_x = (tw - new_w) // 2
        paste_y = (th - new_h) // 2
        canvas.paste(fg_resized, (paste_x, paste_y), mask=fg_resized.split()[3])
    else:
        canvas = Image.new("RGBA", fg_rgba.size, (*rgb, 255))
        canvas.paste(fg_rgba, mask=fg_rgba.split()[3])

    result = canvas.convert("RGB")

    if strip_exif:
        clean = Image.new("RGB", result.size)
        clean.paste(result)
        result = clean

    return result


def process_single_image(
    input_path: Path,
    output_path: Path,
    color_name: str,
    target_size: tuple[int, int] | None,
    strip_exif: bool,
    refine_edges: bool,
    session,
    dry_run: bool,
    verbose: bool,
) -> tuple[int, int]:
    """Process one image file.

    Returns:
        (original_size_bytes, output_size_bytes) — both 0 in dry-run mode.
    """
    from PIL import Image

    original_size = input_path.stat().st_size

    if dry_run:
        tag = f"[dry-run] {input_path.name} → {output_path.name}  (bg={color_name}"
        if target_size:
            tag += f", {target_size[0]}×{target_size[1]}px"
        tag += ")"
        if verbose:
            print(f"  {tag}")
        return original_size, 0

    img = Image.open(input_path).convert("RGBA")
    fg_rgba = remove_background(img, session, refine_edges)
    result   = composite_background(fg_rgba, color_name, target_size, strip_exif)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Always save as JPEG for formal photo compatibility
    save_path = output_path.with_suffix(".jpg")
    result.save(save_path, format="JPEG", quality=92, optimize=True)

    output_size = save_path.stat().st_size

    if verbose:
        ratio = (1 - output_size / original_size) * 100 if original_size else 0
        print(
            f"  {input_path.name} → {save_path.name}  "
            f"({_fmt_bytes(original_size)} → {_fmt_bytes(output_size)}, "
            f"{ratio:+.1f}%,  bg={color_name})"
        )

    return original_size, output_size


# ─── Batch orchestration ──────────────────────────────────────────────────────

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


def _output_path_for(
    input_file: Path,
    input_root: Path,
    output_root: Path,
    color_name: str,
    all_colors: bool,
) -> Path:
    """Compute output path, optionally placing each colour in its own subfolder."""
    relative = input_file.relative_to(input_root)
    if all_colors:
        return output_root / color_name / relative
    return output_root / relative


def swap_background(
    input_path: str,
    output_path: str | None,
    color_names: list[str],
    size_key: str | None,
    strip_exif: bool,
    refine_edges: bool,
    recursive: bool,
    dry_run: bool,
    verbose: bool,
) -> tuple[int, int, int]:
    """Main entry point: handle single file or directory.

    Returns:
        (files_processed, total_original_bytes, total_output_bytes)
    """
    target_size = PHOTO_SIZES.get(size_key) if size_key else None
    all_colors  = len(color_names) > 1
    inp = Path(input_path)

    if not dry_run:
        print("  Loading AI model (u2net_human_seg)…", flush=True)

    session = None if dry_run else _load_rembg_session()

    total_orig = total_out = file_count = 0

    # ── Single file ────────────────────────────────────────────────────────────
    if inp.is_file():
        if inp.suffix.lower() not in SUPPORTED_INPUT_EXTS:
            raise ValueError(f"Unsupported image format: '{inp.suffix}'")

        for color in color_names:
            if output_path:
                out = Path(output_path)
                if all_colors:
                    # Insert colour suffix before extension
                    out = out.with_stem(f"{out.stem}_{color}")
            else:
                suffix = f"_{color}" if all_colors else ""
                out = Path("output") / f"{inp.stem}{suffix}.jpg"

            orig, compressed = process_single_image(
                inp, out, color, target_size, strip_exif,
                refine_edges, session, dry_run, verbose,
            )
            total_orig += orig
            total_out  += compressed
            file_count += 1

    # ── Directory ──────────────────────────────────────────────────────────────
    elif inp.is_dir():
        out_root = Path(output_path) if output_path else Path("output")
        images   = _collect_images(inp, recursive)

        if not images:
            raise ValueError(f"No supported image files found in '{inp}'.")

        for img_file in images:
            for color in color_names:
                out_file = _output_path_for(img_file, inp, out_root, color, all_colors)
                out_file = out_file.with_suffix(".jpg")

                orig, compressed = process_single_image(
                    img_file, out_file, color, target_size, strip_exif,
                    refine_edges, session, dry_run, verbose,
                )
                total_orig += orig
                total_out  += compressed
                file_count += 1

    else:
        raise FileNotFoundError(f"Input not found: '{input_path}'")

    return file_count, total_orig, total_out


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _fmt_bytes(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def _color_swatch(name: str) -> str:
    """ASCII colour label for terminal display."""
    labels = {"merah": "Merah/Red", "biru": "Biru/Blue", "abu": "Abu-abu/Gray"}
    rgb    = BG_COLORS[name]
    return f"{labels[name]}  RGB{rgb}"


# ─── CLI ──────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="swap_bg.py",
        description=(
            "Ganti latar belakang foto formal Indonesia.\n"
            "Swap background colour for Indonesian formal/ID photos."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Background colours (--color / -c):
  merah   Red  (#CC0000)  — Dokumen pemerintah, ijazah, dll.
  biru    Blue (#003399)  — KTP, SIM, paspor, SKCK
  abu     Gray (#808080)  — CV, lamaran kerja

Standard photo sizes (--size / -s):
  2x3     2 × 3 cm  →  236 × 354 px @ 300 DPI
  3x4     3 × 4 cm  →  354 × 472 px @ 300 DPI  (default)
  4x6     4 × 6 cm  →  472 × 709 px @ 300 DPI

Supported input formats:  jpg, jpeg, png, webp, bmp, tiff

Examples:
  python swap_bg.py foto.jpg
  python swap_bg.py foto.jpg --color biru --size 3x4
  python swap_bg.py foto.jpg --all-colors --size 4x6 --strip-exif
  python swap_bg.py ./fotos/ ./hasil/ --color merah --recursive
  python swap_bg.py ./fotos/ ./hasil/ --all-colors --refine-edges --dry-run -v
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
            "Defaults to ./output/ (preserves input directory structure)."
        ),
    )
    parser.add_argument(
        "--color", "-c",
        dest="color",
        choices=list(BG_COLORS),
        default="merah",
        metavar="COLOR",
        help="Background colour: merah (red), biru (blue), abu (gray). Default: merah.",
    )
    parser.add_argument(
        "--all-colors",
        action="store_true",
        help=(
            "Generate all three colour variants at once. "
            "Each colour is saved in its own sub-folder (merah/, biru/, abu/)."
        ),
    )
    parser.add_argument(
        "--size", "-s",
        dest="size",
        choices=list(PHOTO_SIZES),
        default=None,
        metavar="SIZE",
        help=(
            "Resize output to standard Indonesian photo size: "
            "2x3, 3x4 (most common), 4x6.  Omit to keep original resolution."
        ),
    )
    parser.add_argument(
        "--refine-edges",
        action="store_true",
        help=(
            "Enable alpha matting for smoother hair / fine-edge transitions. "
            "Recommended for studio portraits. Slower (~2–3× processing time)."
        ),
    )
    parser.add_argument(
        "--strip-exif",
        action="store_true",
        help="Remove EXIF / metadata from output images (privacy).",
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
        help="Print per-file progress.",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args   = parser.parse_args(argv)

    colors = list(BG_COLORS) if args.all_colors else [args.color]

    # ── Banner ────────────────────────────────────────────────────────────────
    print("=" * 58)
    print("  swap_bg.py — Foto Formal Indonesia Background Swapper")
    print("=" * 58)
    print(f"  Input          : {args.input}")
    print(f"  Output         : {args.output or './output/'}")
    if args.all_colors:
        print( "  Colours        : merah + biru + abu  (all three)")
    else:
        print(f"  Colour         : {_color_swatch(args.color)}")
    if args.size:
        w, h = PHOTO_SIZES[args.size]
        print(f"  Photo size     : {args.size} cm  ({w} × {h} px @ 300 DPI)")
    else:
        print( "  Photo size     : original resolution (no resize)")
    print(f"  Refine edges   : {'yes (alpha matting)' if args.refine_edges else 'no'}")
    print(f"  Strip EXIF     : {'yes' if args.strip_exif else 'no'}")
    if args.dry_run:
        print( "  Mode           : DRY RUN — no files will be written")
    print()

    try:
        count, total_orig, total_out = swap_background(
            input_path   = args.input,
            output_path  = args.output,
            color_names  = colors,
            size_key     = args.size,
            strip_exif   = args.strip_exif,
            refine_edges = args.refine_edges,
            recursive    = args.recursive,
            dry_run      = args.dry_run,
            verbose      = args.verbose,
        )
    except (FileNotFoundError, ValueError) as e:
        print(f"\nError: {e}", file=sys.stderr)
        return 1
    except ImportError as e:
        print(f"\nError: {e}", file=sys.stderr)
        return 1

    if args.dry_run:
        print(f"\n  [dry-run] Would process {count} operation(s).\n")
    else:
        saved = total_orig - total_out
        ratio = (saved / total_orig * 100) if total_orig else 0
        print(f"\n  Selesai! {count} file(s) processed. "
              f"Size change: {ratio:+.1f}%\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
