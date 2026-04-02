#!/usr/bin/env python3
"""
Duplicate File Finder — finds and optionally removes duplicate files by content.

Uses two-phase detection: fast size pre-filter, then SHA-256 content hashing.
No pip dependencies — standard library only.

Usage examples:
    # Report duplicates in a directory
    python dedup_files.py ./downloads/

    # Recursive scan with verbose output
    python dedup_files.py ./photos/ --recursive --verbose

    # Only check image files
    python dedup_files.py ./photos/ --ext .jpg,.png,.webp

    # Move duplicates to a staging folder (safe — originals kept)
    python dedup_files.py ./downloads/ --action move --move-to ./duplicates/

    # Delete duplicates (dry-run first to preview)
    python dedup_files.py ./downloads/ --action delete --dry-run
    python dedup_files.py ./downloads/ --action delete

    # Ignore files smaller than 10 KB
    python dedup_files.py ./downloads/ --min-size 10240
"""

import argparse
import hashlib
import os
import shutil
import sys
from collections import defaultdict
from pathlib import Path


# ─────────────────────────────────────────────
# 1. Hashing
# ─────────────────────────────────────────────

def _file_hash(path: Path, chunk_size: int = 65536) -> str:
    """Return the SHA-256 hex digest of a file's contents."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(chunk_size):
            h.update(chunk)
    return h.hexdigest()


# ─────────────────────────────────────────────
# 2. Detection
# ─────────────────────────────────────────────

def find_duplicates(
    directory: str,
    recursive: bool = True,
    min_size: int = 1,
    extensions: set[str] | None = None,
    verbose: bool = False,
) -> dict[str, list[Path]]:
    """Scan a directory and return groups of duplicate files.

    Args:
        directory: Root directory to scan.
        recursive: Scan subdirectories when True.
        min_size: Minimum file size in bytes to consider (default: 1).
        extensions: Optional set of lowercase extensions to check (e.g. {'.jpg', '.png'}).
        verbose: Print progress messages.

    Returns:
        Dict mapping SHA-256 hash → list of duplicate Paths (groups with 2+ files).
    """
    root = Path(directory)
    if not root.is_dir():
        raise FileNotFoundError(f"Directory not found: '{directory}'")

    # Collect candidate files
    if recursive:
        all_files = [p for p in root.rglob("*") if p.is_file()]
    else:
        all_files = [p for p in root.iterdir() if p.is_file()]

    # Filter by extension
    if extensions:
        all_files = [p for p in all_files if p.suffix.lower() in extensions]

    # Filter by size
    candidates: list[Path] = []
    for p in all_files:
        try:
            size = p.stat().st_size
            if size >= min_size:
                candidates.append(p)
        except OSError:
            pass  # skip unreadable files

    if verbose:
        print(f"  Scanning {len(candidates)} file(s)...")

    # Phase 1: group by file size (fast pre-filter)
    by_size: dict[int, list[Path]] = defaultdict(list)
    for p in candidates:
        by_size[p.stat().st_size].append(p)

    size_dupes = [group for group in by_size.values() if len(group) > 1]

    if verbose:
        total_to_hash = sum(len(g) for g in size_dupes)
        print(f"  {total_to_hash} file(s) share sizes — hashing for exact matches...")

    # Phase 2: hash files with matching sizes
    by_hash: dict[str, list[Path]] = defaultdict(list)
    for group in size_dupes:
        for p in group:
            try:
                digest = _file_hash(p)
                by_hash[digest].append(p)
            except OSError as e:
                print(f"  Warning: Could not read '{p}': {e}", file=sys.stderr)

    # Return only groups with 2+ files (true duplicates)
    return {h: paths for h, paths in by_hash.items() if len(paths) > 1}


# ─────────────────────────────────────────────
# 3. Actions
# ─────────────────────────────────────────────

def _keep_file(paths: list[Path]) -> Path:
    """Choose which file to keep — earliest modification time wins."""
    return min(paths, key=lambda p: p.stat().st_mtime)


def report_duplicates(groups: dict[str, list[Path]], verbose: bool = False) -> None:
    """Print a human-readable report of duplicate groups."""
    total_dupes = sum(len(v) - 1 for v in groups.values())
    wasted = sum(
        p.stat().st_size * (len(v) - 1)
        for v in groups.values()
        for p in [v[0]]
    )

    print(f"  Found {len(groups)} duplicate group(s), {total_dupes} redundant file(s).")
    print(f"  Wasted space: {_fmt_bytes(wasted)}\n")

    for i, (digest, paths) in enumerate(groups.items(), 1):
        keep = _keep_file(paths)
        print(f"  Group {i}  [{digest[:12]}...]  ({_fmt_bytes(paths[0].stat().st_size)} each)")
        for p in paths:
            marker = "  KEEP" if p == keep else "  dupe"
            print(f"    {marker}  {p}")
        print()


def move_duplicates(
    groups: dict[str, list[Path]],
    move_to: str,
    dry_run: bool,
    verbose: bool,
) -> int:
    """Move duplicate files (keeping one per group) to a staging directory.

    Returns number of files moved.
    """
    dest_root = Path(move_to)
    moved = 0

    for paths in groups.values():
        keep = _keep_file(paths)
        for p in paths:
            if p == keep:
                continue
            dest = dest_root / p.name
            # Avoid collision in destination
            counter = 1
            while dest.exists():
                dest = dest_root / f"{p.stem}_{counter}{p.suffix}"
                counter += 1

            if dry_run:
                print(f"  [dry-run] move  {p}  →  {dest}")
            else:
                dest_root.mkdir(parents=True, exist_ok=True)
                shutil.move(str(p), str(dest))
                if verbose:
                    print(f"  Moved  {p}  →  {dest}")
            moved += 1

    return moved


def delete_duplicates(
    groups: dict[str, list[Path]],
    dry_run: bool,
    verbose: bool,
) -> int:
    """Delete duplicate files, keeping one per group.

    Returns number of files deleted.
    """
    deleted = 0

    for paths in groups.values():
        keep = _keep_file(paths)
        for p in paths:
            if p == keep:
                continue
            if dry_run:
                print(f"  [dry-run] delete  {p}")
            else:
                try:
                    p.unlink()
                    if verbose:
                        print(f"  Deleted  {p}")
                except OSError as e:
                    print(f"  Warning: Could not delete '{p}': {e}", file=sys.stderr)
            deleted += 1

    return deleted


def _fmt_bytes(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


# ─────────────────────────────────────────────
# 4. CLI
# ─────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Find and optionally remove duplicate files by content hash.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Strategy: files are compared by SHA-256 hash, not filename.
The file with the earliest modification time is kept in each group.

Examples:
  python dedup_files.py ./downloads/
  python dedup_files.py ./photos/ --recursive --ext .jpg,.png
  python dedup_files.py ./downloads/ --action move --move-to ./dupes/
  python dedup_files.py ./downloads/ --action delete --dry-run
        """,
    )

    parser.add_argument(
        "directory",
        metavar="DIRECTORY",
        help="Directory to scan for duplicate files.",
    )
    parser.add_argument(
        "--recursive", "-r",
        action="store_true",
        default=False,
        help="Scan subdirectories recursively.",
    )
    parser.add_argument(
        "--min-size",
        type=int,
        default=1,
        metavar="BYTES",
        help="Ignore files smaller than this many bytes. (default: 1)",
    )
    parser.add_argument(
        "--ext",
        default=None,
        metavar="EXT[,EXT...]",
        help="Only check files with these extensions, e.g. .jpg,.png,.pdf",
    )
    parser.add_argument(
        "--action",
        choices=["report", "move", "delete"],
        default="report",
        help="What to do with duplicates: report (default), move, or delete.",
    )
    parser.add_argument(
        "--move-to",
        default="./duplicates",
        metavar="DIR",
        help="Destination directory when --action=move. (default: ./duplicates)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would happen without making any changes.",
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

    if args.action == "move" and args.dry_run is False and args.move_to is None:
        parser.error("--action=move requires --move-to <directory>.")

    extensions: set[str] | None = None
    if args.ext:
        raw = [e.strip() for e in args.ext.split(",")]
        extensions = {e if e.startswith(".") else f".{e}" for e in raw if e}

    print("=" * 54)
    print("  Duplicate File Finder")
    print("=" * 54)
    print(f"  Directory     : {args.directory}")
    print(f"  Recursive     : {'yes' if args.recursive else 'no'}")
    if extensions:
        print(f"  Extensions    : {', '.join(sorted(extensions))}")
    if args.min_size > 1:
        print(f"  Min size      : {_fmt_bytes(args.min_size)}")
    print(f"  Action        : {args.action}")
    if args.action == "move":
        print(f"  Move to       : {args.move_to}")
    if args.dry_run:
        print("  Mode          : DRY RUN (no files will be changed)")
    print()

    try:
        groups = find_duplicates(
            directory=args.directory,
            recursive=args.recursive,
            min_size=args.min_size,
            extensions=extensions,
            verbose=args.verbose,
        )
    except FileNotFoundError as e:
        print(f"\nError: {e}", file=sys.stderr)
        return 1

    if not groups:
        print("  No duplicate files found.\n")
        return 0

    if args.action == "report":
        report_duplicates(groups, verbose=args.verbose)

    elif args.action == "move":
        report_duplicates(groups, verbose=False)
        count = move_duplicates(groups, args.move_to, args.dry_run, args.verbose)
        verb = "Would move" if args.dry_run else "Moved"
        print(f"  {verb} {count} duplicate(s) → {args.move_to}\n")

    elif args.action == "delete":
        report_duplicates(groups, verbose=False)
        if not args.dry_run:
            confirm = input("  Confirm deletion? [y/N] ").strip().lower()
            if confirm not in ("y", "yes"):
                print("  Aborted.\n")
                return 0
        count = delete_duplicates(groups, args.dry_run, args.verbose)
        verb = "Would delete" if args.dry_run else "Deleted"
        print(f"  {verb} {count} duplicate(s).\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
