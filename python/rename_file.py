# Python script to recursively list files in a folder and rename them without opening them.
# Usage examples:
#   python rename_files.py ./myfolder --mode slugify --recursive --change-ext .jpg
#   python rename_files.py ./myfolder --only-ext .png --src-ext .txt,.md --dry-run
import os
import re
import argparse
from pathlib import Path

def slugify(name: str) -> str:
    name = re.sub(r'[^\w\-\.]', '_', name)          # keep dots and dashes
    name = re.sub(r'_{2,}', '_', name)              # collapse repeated underscores
    return name.strip('_')

def unique_path(dest: Path) -> Path:
    if not dest.exists():
        return dest
    stem, suffix = dest.stem, dest.suffix
    i = 1
    while True:
        candidate = dest.with_name(f"{stem}_{i}{suffix}")
        if not candidate.exists():
            return candidate
        i += 1

def collect_files(root: Path, recursive: bool):
    files = []
    if recursive:
        for p in root.rglob('*'):
            if p.is_file():
                files.append(p)
    else:
        for p in root.iterdir():
            if p.is_file():
                files.append(p)
    return sorted(files)

def norm_ext(ext: str) -> str:
    if not ext:
        return ""
    return ext if ext.startswith('.') else f".{ext}"

def parse_src_exts(s: str):
    # Accept comma-separated extensions or a single extension; normalize to set of lowercase with dot
    if not s:
        return None
    parts = [p.strip() for p in s.split(',') if p.strip()]
    return set(norm_ext(p).lower() for p in parts)

def main():
    p = argparse.ArgumentParser(description="Batch rename files without opening them")
    p.add_argument("folder", help="Target folder")
    p.add_argument("--mode", choices=["sequential", "slugify", "lowercase", "replace"], default="slugify")
    p.add_argument("--prefix", default="", help="Prefix for new names (sequential mode uses this)")
    p.add_argument("--replace-from", help="String to replace (replace mode)")
    p.add_argument("--replace-to", help="Replacement string (replace mode)")
    p.add_argument("--start", type=int, default=1, help="Start index for sequential mode")
    p.add_argument("--recursive", action="store_true", help="Recurse into subfolders")
    p.add_argument("--dry-run", action="store_true", help="Print changes without renaming")
    p.add_argument("--change-ext", "-e", help="Change resulting filenames' extension to EXT (e.g. .jpg or jpg)")
    p.add_argument("--only-ext", action="store_true", help="Only change the file extension, keep existing stems")
    p.add_argument("--src-ext", "-s", help="Only operate on files with these source extensions (comma-separated, e.g. .txt,.md or txt,md)")
    args = p.parse_args()

    root = Path(args.folder)
    if not root.exists() or not root.is_dir():
        raise SystemExit(f"Folder not found: {root}")

    files = collect_files(root, args.recursive)
    if not files:
        print("No files found.")
        return

    src_exts = parse_src_exts(args.src_ext)  # None or set of extensions
    if src_exts is not None:
        files = [f for f in files if f.suffix.lower() in src_exts]
        if not files:
            print("No files matched the given source extension(s).")
            return

    change_ext = norm_ext(args.change_ext) if args.change_ext else ""

    mapping = {}
    if args.only_ext:
        if not change_ext:
            raise SystemExit("--only-ext requires --change-ext to be provided")
        for f in files:
            mapping[f] = f.with_suffix(change_ext)
    else:
        if args.mode == "sequential":
            total = len(files)
            width = max(3, len(str(total + args.start)))
            idx = args.start
            for f in files:
                new_name = f"{args.prefix}{str(idx).zfill(width)}{f.suffix}"
                dest = f.with_name(new_name)
                if change_ext:
                    dest = dest.with_suffix(change_ext)
                mapping[f] = dest
                idx += 1
        else:
            for f in files:
                if args.mode == "slugify":
                    new_stem = slugify(f.stem)
                elif args.mode == "lowercase":
                    new_stem = f.stem.lower()
                elif args.mode == "replace":
                    if args.replace_from is None:
                        raise SystemExit("replace mode requires --replace-from")
                    new_stem = f.stem.replace(args.replace_from, args.replace_to or "")
                else:
                    new_stem = f.stem
                new_suffix = change_ext if change_ext else f.suffix
                mapping[f] = f.with_name(new_stem + new_suffix)

    # Ensure uniqueness and perform rename
    for src, tentative_dest in mapping.items():
        dest = unique_path(tentative_dest)
        if src.resolve() == dest.resolve():
            continue
        print(f"{src} -> {dest}")
        if not args.dry_run:
            dest.parent.mkdir(parents=True, exist_ok=True)
            os.rename(src, dest)

if __name__ == "__main__":
    main()