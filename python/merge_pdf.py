#!/usr/bin/env python3
"""
PDF Merger — combines multiple PDF files into a single document.

Requirements:
    pip install pymupdf

Usage examples:
    # Merge all PDFs in a directory (sorted by name)
    python merge_pdf.py ./docs/ output.pdf

    # Merge specific files
    python merge_pdf.py a.pdf b.pdf c.pdf output.pdf

    # Merge in a specific order, sorted by modification date
    python merge_pdf.py ./docs/ output.pdf --sort date

    # Keep original file order (no sorting)
    python merge_pdf.py a.pdf b.pdf c.pdf output.pdf --sort none

    # Verbose output
    python merge_pdf.py ./docs/ output.pdf --verbose
"""

import argparse
import os
import sys
from pathlib import Path


def _collect_pdf_files(inputs: list[str], sort: str) -> list[Path]:
    """Collect and optionally sort PDF files from a list of paths/directories."""
    paths: list[Path] = []

    for item in inputs:
        p = Path(item)
        if p.is_dir():
            paths.extend(f for f in p.iterdir() if f.suffix.lower() == ".pdf")
        elif p.is_file():
            if p.suffix.lower() != ".pdf":
                raise ValueError(f"Not a PDF file: '{item}'")
            paths.append(p)
        else:
            raise FileNotFoundError(f"Input not found: '{item}'")

    if not paths:
        raise ValueError("No PDF files found in the provided inputs.")

    if sort == "name":
        paths.sort(key=lambda p: p.name.lower())
    elif sort == "date":
        paths.sort(key=lambda p: p.stat().st_mtime)
    # sort == "none": preserve original order

    return paths


def merge_pdfs(
    inputs: list[str],
    output_path: str,
    sort: str = "name",
    verbose: bool = False,
) -> int:
    """Merge multiple PDF files into a single output PDF.

    Args:
        inputs: List of PDF file paths or directories containing PDFs.
        output_path: Destination PDF file path.
        sort: Sort order for input files — 'name', 'date', or 'none'.
        verbose: Print progress messages.

    Returns:
        Number of pages in the merged output.
    """
    try:
        import pymupdf
    except ImportError:
        raise RuntimeError("pymupdf is not installed. Run:  pip install pymupdf")

    pdf_files = _collect_pdf_files(inputs, sort)

    if verbose:
        print(f"  Merging {len(pdf_files)} file(s):")
        for f in pdf_files:
            print(f"    {f}")

    merged = pymupdf.open()

    for pdf_path in pdf_files:
        try:
            src = pymupdf.open(str(pdf_path))
        except Exception as e:
            raise RuntimeError(f"Could not open '{pdf_path}': {e}")

        merged.insert_pdf(src)
        src.close()

        if verbose:
            print(f"  Added: {pdf_path.name}  ({src.page_count} pages)")

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    try:
        merged.save(output_path)
    except Exception as e:
        raise RuntimeError(f"Could not save output PDF '{output_path}': {e}")
    finally:
        merged.close()

    return sum(
        pymupdf.open(str(p)).page_count for p in pdf_files
    )


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Merge multiple PDF files into a single document.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python merge_pdf.py a.pdf b.pdf c.pdf output.pdf
  python merge_pdf.py ./docs/ output.pdf
  python merge_pdf.py ./docs/ output.pdf --sort date
  python merge_pdf.py a.pdf b.pdf output.pdf --sort none --verbose
        """,
    )

    parser.add_argument(
        "inputs",
        nargs="+",
        metavar="INPUT",
        help=(
            "PDF files or directories to merge. "
            "When a directory is given, all .pdf files inside are included. "
            "The last argument is always treated as the output path."
        ),
    )
    parser.add_argument(
        "--sort",
        choices=["name", "date", "none"],
        default="name",
        help="Sort order for input files: name (default), date (modification time), none.",
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

    if len(args.inputs) < 2:
        parser.error("Provide at least one input PDF/directory and an output path.")

    *input_paths, output_path = args.inputs

    if not output_path.lower().endswith(".pdf"):
        parser.error(f"Output path must end with .pdf, got: '{output_path}'")

    print("=" * 54)
    print("  PDF Merger")
    print("=" * 54)
    print(f"  Output        : {output_path}")
    print(f"  Sort          : {args.sort}")
    print()

    try:
        total_pages = merge_pdfs(
            inputs=input_paths,
            output_path=output_path,
            sort=args.sort,
            verbose=args.verbose,
        )
    except (FileNotFoundError, ValueError, RuntimeError) as e:
        print(f"\nError: {e}", file=sys.stderr)
        return 1

    print(f"\n  Done! {total_pages} pages merged → {output_path}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
