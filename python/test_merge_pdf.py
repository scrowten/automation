"""Tests for merge_pdf.py — PDF merger."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from merge_pdf import _collect_pdf_files, main


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def make_pdf(path: Path) -> Path:
    """Create a minimal valid PDF file for testing."""
    try:
        import pymupdf
        doc = pymupdf.open()
        doc.new_page()
        doc.save(str(path))
        doc.close()
    except ImportError:
        # Fallback: write a minimal PDF header (won't open but satisfies file existence)
        path.write_bytes(
            b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\n"
            b"xref\n0 2\n0000000000 65535 f\n0000000009 00000 n\n"
            b"trailer<</Size 2/Root 1 0 R>>\nstartxref\n9\n%%EOF\n"
        )
    return path


# ─────────────────────────────────────────────
# Unit: _collect_pdf_files
# ─────────────────────────────────────────────

class TestCollectPdfFiles:
    def test_collect_from_files(self, tmp_path):
        a = make_pdf(tmp_path / "a.pdf")
        b = make_pdf(tmp_path / "b.pdf")
        result = _collect_pdf_files([str(a), str(b)], sort="none")
        assert result == [a, b]

    def test_collect_from_directory(self, tmp_path):
        make_pdf(tmp_path / "a.pdf")
        make_pdf(tmp_path / "b.pdf")
        result = _collect_pdf_files([str(tmp_path)], sort="name")
        assert len(result) == 2

    def test_sort_by_name(self, tmp_path):
        make_pdf(tmp_path / "c.pdf")
        make_pdf(tmp_path / "a.pdf")
        make_pdf(tmp_path / "b.pdf")
        result = _collect_pdf_files([str(tmp_path)], sort="name")
        assert [p.name for p in result] == ["a.pdf", "b.pdf", "c.pdf"]

    def test_sort_none_preserves_order(self, tmp_path):
        a = make_pdf(tmp_path / "a.pdf")
        b = make_pdf(tmp_path / "b.pdf")
        result = _collect_pdf_files([str(b), str(a)], sort="none")
        assert result == [b, a]

    def test_non_pdf_file_raises(self, tmp_path):
        txt = tmp_path / "file.txt"
        txt.write_text("hello")
        with pytest.raises(ValueError, match="Not a PDF"):
            _collect_pdf_files([str(txt)], sort="none")

    def test_missing_path_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            _collect_pdf_files([str(tmp_path / "missing.pdf")], sort="none")

    def test_empty_directory_raises(self, tmp_path):
        with pytest.raises(ValueError, match="No PDF files found"):
            _collect_pdf_files([str(tmp_path)], sort="name")


# ─────────────────────────────────────────────
# CLI tests
# ─────────────────────────────────────────────

class TestMainCLI:
    def test_missing_args_exits_nonzero(self):
        with pytest.raises(SystemExit) as exc:
            main([])
        assert exc.value.code != 0

    def test_single_input_no_output_exits_nonzero(self, tmp_path):
        pdf = make_pdf(tmp_path / "a.pdf")
        with pytest.raises(SystemExit) as exc:
            main([str(pdf)])
        assert exc.value.code != 0

    def test_output_must_end_with_pdf(self, tmp_path):
        a = make_pdf(tmp_path / "a.pdf")
        b = make_pdf(tmp_path / "b.pdf")
        with pytest.raises(SystemExit) as exc:
            main([str(a), str(b), str(tmp_path / "output.txt")])
        assert exc.value.code != 0

    def test_nonexistent_input_exits_nonzero(self, tmp_path):
        result = main([str(tmp_path / "missing.pdf"), str(tmp_path / "out.pdf")])
        assert result != 0

    def test_merge_two_pdfs(self, tmp_path):
        """Integration: actually merges two PDFs."""
        pytest.importorskip("pymupdf")
        a = make_pdf(tmp_path / "a.pdf")
        b = make_pdf(tmp_path / "b.pdf")
        out = str(tmp_path / "merged.pdf")
        result = main([str(a), str(b), out])
        assert result == 0
        assert Path(out).is_file()

    def test_merge_directory(self, tmp_path):
        """Integration: merges all PDFs in a directory."""
        pytest.importorskip("pymupdf")
        make_pdf(tmp_path / "a.pdf")
        make_pdf(tmp_path / "b.pdf")
        make_pdf(tmp_path / "c.pdf")
        out = str(tmp_path / "merged.pdf")
        result = main([str(tmp_path), out])
        assert result == 0

    def test_verbose_flag(self, tmp_path, capsys):
        pytest.importorskip("pymupdf")
        a = make_pdf(tmp_path / "a.pdf")
        b = make_pdf(tmp_path / "b.pdf")
        out = str(tmp_path / "merged.pdf")
        main([str(a), str(b), out, "--verbose"])
        captured = capsys.readouterr()
        assert "Merging" in captured.out or "Added" in captured.out

    def test_sort_date(self, tmp_path):
        pytest.importorskip("pymupdf")
        a = make_pdf(tmp_path / "a.pdf")
        b = make_pdf(tmp_path / "b.pdf")
        out = str(tmp_path / "merged.pdf")
        result = main([str(a), str(b), out, "--sort", "date"])
        assert result == 0

    def test_output_directory_created(self, tmp_path):
        pytest.importorskip("pymupdf")
        a = make_pdf(tmp_path / "a.pdf")
        b = make_pdf(tmp_path / "b.pdf")
        out = str(tmp_path / "nested" / "output.pdf")
        result = main([str(a), str(b), out])
        assert result == 0
        assert Path(out).is_file()
