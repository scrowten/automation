"""Tests for dedup_files.py — duplicate file finder."""

import shutil
from pathlib import Path

import pytest

from dedup_files import (
    _file_hash,
    _fmt_bytes,
    _keep_file,
    delete_duplicates,
    find_duplicates,
    move_duplicates,
    main,
)


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def write_file(path: Path, content: bytes = b"hello") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


# ─────────────────────────────────────────────
# Unit: _file_hash
# ─────────────────────────────────────────────

class TestFileHash:
    def test_same_content_same_hash(self, tmp_path):
        a = write_file(tmp_path / "a.txt", b"hello")
        b = write_file(tmp_path / "b.txt", b"hello")
        assert _file_hash(a) == _file_hash(b)

    def test_different_content_different_hash(self, tmp_path):
        a = write_file(tmp_path / "a.txt", b"hello")
        b = write_file(tmp_path / "b.txt", b"world")
        assert _file_hash(a) != _file_hash(b)

    def test_empty_file(self, tmp_path):
        f = write_file(tmp_path / "empty.txt", b"")
        digest = _file_hash(f)
        assert len(digest) == 64  # SHA-256 hex length


class TestFmtBytes:
    def test_bytes(self):
        assert "B" in _fmt_bytes(100)

    def test_kilobytes(self):
        assert "KB" in _fmt_bytes(2048)

    def test_megabytes(self):
        assert "MB" in _fmt_bytes(3 * 1024 * 1024)


class TestKeepFile:
    def test_keeps_oldest_by_mtime(self, tmp_path):
        import time
        old = write_file(tmp_path / "old.txt", b"data")
        time.sleep(0.05)
        new = write_file(tmp_path / "new.txt", b"data")
        assert _keep_file([new, old]) == old


# ─────────────────────────────────────────────
# Unit: find_duplicates
# ─────────────────────────────────────────────

class TestFindDuplicates:
    def test_finds_exact_duplicates(self, tmp_path):
        write_file(tmp_path / "a.txt", b"same content")
        write_file(tmp_path / "b.txt", b"same content")
        write_file(tmp_path / "c.txt", b"different")
        result = find_duplicates(str(tmp_path))
        assert len(result) == 1
        group = next(iter(result.values()))
        assert len(group) == 2

    def test_no_duplicates_returns_empty(self, tmp_path):
        write_file(tmp_path / "a.txt", b"aaa")
        write_file(tmp_path / "b.txt", b"bbb")
        result = find_duplicates(str(tmp_path))
        assert result == {}

    def test_three_identical_files_one_group(self, tmp_path):
        for name in ("a.txt", "b.txt", "c.txt"):
            write_file(tmp_path / name, b"triple")
        result = find_duplicates(str(tmp_path))
        assert len(result) == 1
        group = next(iter(result.values()))
        assert len(group) == 3

    def test_min_size_filter(self, tmp_path):
        write_file(tmp_path / "small_a.txt", b"x")
        write_file(tmp_path / "small_b.txt", b"x")
        result = find_duplicates(str(tmp_path), min_size=100)
        assert result == {}

    def test_extension_filter(self, tmp_path):
        write_file(tmp_path / "a.txt", b"same")
        write_file(tmp_path / "b.txt", b"same")
        write_file(tmp_path / "c.pdf", b"same")
        result = find_duplicates(str(tmp_path), extensions={".pdf"})
        assert result == {}  # only one .pdf, can't be a dupe

    def test_recursive_finds_dupes_in_subdirs(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        write_file(tmp_path / "a.txt", b"dupe content")
        write_file(sub / "b.txt", b"dupe content")
        result = find_duplicates(str(tmp_path), recursive=True)
        assert len(result) == 1

    def test_non_recursive_misses_subdirs(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        write_file(tmp_path / "a.txt", b"dupe content")
        write_file(sub / "b.txt", b"dupe content")
        result = find_duplicates(str(tmp_path), recursive=False)
        assert result == {}

    def test_missing_directory_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            find_duplicates(str(tmp_path / "missing"))


# ─────────────────────────────────────────────
# Unit: actions
# ─────────────────────────────────────────────

class TestMoveDuplicates:
    def test_moves_dupes_keeps_one(self, tmp_path):
        import time
        orig = write_file(tmp_path / "orig.txt", b"content")
        time.sleep(0.05)
        dupe = write_file(tmp_path / "dupe.txt", b"content")
        groups = {_file_hash(orig): [orig, dupe]}
        dest = tmp_path / "moved"

        count = move_duplicates(groups, str(dest), dry_run=False, verbose=False)

        assert count == 1
        assert orig.exists()        # kept
        assert not dupe.exists()    # moved
        assert (dest / "dupe.txt").exists()

    def test_dry_run_does_not_move(self, tmp_path):
        a = write_file(tmp_path / "a.txt", b"dup")
        b = write_file(tmp_path / "b.txt", b"dup")
        groups = {_file_hash(a): [a, b]}
        dest = tmp_path / "moved"

        move_duplicates(groups, str(dest), dry_run=True, verbose=False)

        assert a.exists() and b.exists()
        assert not dest.exists()

    def test_collision_renamed_in_destination(self, tmp_path):
        import time
        orig = write_file(tmp_path / "a.txt", b"dup")
        time.sleep(0.05)
        dupe = write_file(tmp_path / "b.txt", b"dup")
        dest = tmp_path / "moved"
        # Pre-create a file with the expected destination name to force collision
        dest.mkdir()
        (dest / "b.txt").write_bytes(b"already here")
        groups = {_file_hash(orig): [orig, dupe]}

        move_duplicates(groups, str(dest), dry_run=False, verbose=False)

        # Should have renamed the moved file to avoid collision
        files_in_dest = list(dest.iterdir())
        assert len(files_in_dest) == 2


class TestDeleteDuplicates:
    def test_deletes_dupes_keeps_one(self, tmp_path):
        import time
        orig = write_file(tmp_path / "orig.txt", b"content")
        time.sleep(0.05)
        dupe = write_file(tmp_path / "dupe.txt", b"content")
        groups = {_file_hash(orig): [orig, dupe]}

        count = delete_duplicates(groups, dry_run=False, verbose=False)

        assert count == 1
        assert orig.exists()
        assert not dupe.exists()

    def test_dry_run_does_not_delete(self, tmp_path):
        a = write_file(tmp_path / "a.txt", b"dup")
        b = write_file(tmp_path / "b.txt", b"dup")
        groups = {_file_hash(a): [a, b]}

        delete_duplicates(groups, dry_run=True, verbose=False)

        assert a.exists() and b.exists()


# ─────────────────────────────────────────────
# CLI tests
# ─────────────────────────────────────────────

class TestMainCLI:
    def test_missing_directory_exits_nonzero(self, tmp_path):
        result = main([str(tmp_path / "missing")])
        assert result == 1

    def test_no_duplicates_exits_zero(self, tmp_path):
        write_file(tmp_path / "a.txt", b"aaa")
        write_file(tmp_path / "b.txt", b"bbb")
        result = main([str(tmp_path)])
        assert result == 0

    def test_report_action_exits_zero(self, tmp_path):
        write_file(tmp_path / "a.txt", b"same")
        write_file(tmp_path / "b.txt", b"same")
        result = main([str(tmp_path), "--action", "report"])
        assert result == 0

    def test_move_dry_run(self, tmp_path):
        write_file(tmp_path / "a.txt", b"dup")
        write_file(tmp_path / "b.txt", b"dup")
        dest = tmp_path / "moved"
        result = main([
            str(tmp_path), "--action", "move",
            "--move-to", str(dest), "--dry-run",
        ])
        assert result == 0
        assert not dest.exists()

    def test_move_action(self, tmp_path):
        import time
        write_file(tmp_path / "a.txt", b"dup")
        time.sleep(0.05)
        write_file(tmp_path / "b.txt", b"dup")
        dest = tmp_path / "moved"
        result = main([
            str(tmp_path), "--action", "move",
            "--move-to", str(dest),
        ])
        assert result == 0
        assert dest.exists()
        assert len(list(dest.iterdir())) == 1

    def test_delete_dry_run(self, tmp_path):
        write_file(tmp_path / "a.txt", b"dup")
        write_file(tmp_path / "b.txt", b"dup")
        result = main([str(tmp_path), "--action", "delete", "--dry-run"])
        assert result == 0
        assert (tmp_path / "a.txt").exists()
        assert (tmp_path / "b.txt").exists()

    def test_ext_filter(self, tmp_path):
        write_file(tmp_path / "a.txt", b"dup")
        write_file(tmp_path / "b.txt", b"dup")
        write_file(tmp_path / "c.pdf", b"dup")
        # Only check .pdf — only one .pdf so no dupes
        result = main([str(tmp_path), "--ext", ".pdf"])
        assert result == 0

    def test_min_size_filter(self, tmp_path):
        write_file(tmp_path / "a.txt", b"x")
        write_file(tmp_path / "b.txt", b"x")
        result = main([str(tmp_path), "--min-size", "1000"])
        assert result == 0

    def test_recursive_flag(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        write_file(tmp_path / "a.txt", b"dup")
        write_file(sub / "b.txt", b"dup")
        result = main([str(tmp_path), "--recursive"])
        assert result == 0
