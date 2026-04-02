"""Tests for compress_img.py — image compressor."""

from pathlib import Path

import pytest

from compress_img import (
    _collect_images,
    _fmt_bytes,
    _output_path_for,
    compress_batch,
    compress_image,
    main,
)

PIL = pytest.importorskip("PIL", reason="Pillow not installed")
from PIL import Image


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def make_image(path: Path, size=(100, 100), color="red", mode="RGB") -> Path:
    img = Image.new(mode, size, color)
    img.save(str(path))
    return path


# ─────────────────────────────────────────────
# Unit: helpers
# ─────────────────────────────────────────────

class TestFmtBytes:
    def test_bytes(self):
        assert "B" in _fmt_bytes(500)

    def test_kilobytes(self):
        assert "KB" in _fmt_bytes(2048)

    def test_megabytes(self):
        assert "MB" in _fmt_bytes(2 * 1024 * 1024)


class TestOutputPathFor:
    def test_same_format(self, tmp_path):
        inp = tmp_path / "a.jpg"
        out = _output_path_for(inp, tmp_path, Path("/out"), None)
        assert out == Path("/out/a.jpg")

    def test_format_conversion_changes_extension(self, tmp_path):
        inp = tmp_path / "a.jpg"
        out = _output_path_for(inp, tmp_path, Path("/out"), "webp")
        assert out.suffix == ".webp"

    def test_subdirectory_mirrored(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        inp = sub / "photo.jpg"
        out = _output_path_for(inp, tmp_path, Path("/out"), None)
        assert out == Path("/out/sub/photo.jpg")


class TestCollectImages:
    def test_flat_directory(self, tmp_path):
        make_image(tmp_path / "a.jpg")
        make_image(tmp_path / "b.png")
        (tmp_path / "file.txt").write_text("not an image")
        result = _collect_images(tmp_path, recursive=False)
        assert len(result) == 2

    def test_recursive(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        make_image(tmp_path / "a.jpg")
        make_image(sub / "b.jpg")
        result = _collect_images(tmp_path, recursive=True)
        assert len(result) == 2

    def test_non_recursive_skips_subdirs(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        make_image(tmp_path / "a.jpg")
        make_image(sub / "b.jpg")
        result = _collect_images(tmp_path, recursive=False)
        assert len(result) == 1


# ─────────────────────────────────────────────
# Unit: compress_image
# ─────────────────────────────────────────────

class TestCompressImage:
    def test_basic_jpeg_output(self, tmp_path):
        inp = make_image(tmp_path / "photo.jpg", size=(200, 200))
        out = tmp_path / "out.jpg"
        compress_image(inp, out, None, None, 80, None, False, False, False)
        assert out.is_file()
        img = Image.open(out)
        assert img.format == "JPEG"

    def test_resize_max_width(self, tmp_path):
        inp = make_image(tmp_path / "photo.jpg", size=(400, 200))
        out = tmp_path / "out.jpg"
        compress_image(inp, out, 200, None, 80, None, False, False, False)
        result = Image.open(out)
        assert result.width == 200
        assert result.height == 100  # aspect ratio maintained

    def test_resize_max_height(self, tmp_path):
        inp = make_image(tmp_path / "photo.jpg", size=(200, 400))
        out = tmp_path / "out.jpg"
        compress_image(inp, out, None, 100, 80, None, False, False, False)
        result = Image.open(out)
        assert result.height == 100
        assert result.width == 50

    def test_no_upscale(self, tmp_path):
        """Images smaller than max_width should not be enlarged."""
        inp = make_image(tmp_path / "small.jpg", size=(100, 50))
        out = tmp_path / "out.jpg"
        compress_image(inp, out, 500, None, 80, None, False, False, False)
        result = Image.open(out)
        assert result.width == 100  # unchanged

    def test_convert_to_webp(self, tmp_path):
        inp = make_image(tmp_path / "photo.jpg", size=(100, 100))
        out = tmp_path / "out.webp"
        compress_image(inp, out, None, None, 80, "webp", False, False, False)
        assert out.is_file()
        img = Image.open(out)
        assert img.format == "WEBP"

    def test_convert_to_png(self, tmp_path):
        inp = make_image(tmp_path / "photo.jpg", size=(100, 100))
        out = tmp_path / "out.png"
        compress_image(inp, out, None, None, 80, "png", False, False, False)
        img = Image.open(out)
        assert img.format == "PNG"

    def test_rgba_to_jpeg_flattens_alpha(self, tmp_path):
        inp = make_image(tmp_path / "photo.png", size=(100, 100), mode="RGBA", color=(255, 0, 0, 128))
        out = tmp_path / "out.jpg"
        compress_image(inp, out, None, None, 80, "jpg", False, False, False)
        img = Image.open(out)
        assert img.format == "JPEG"
        assert img.mode == "RGB"

    def test_strip_exif(self, tmp_path):
        """Strip-exif should produce a file without metadata."""
        inp = make_image(tmp_path / "photo.jpg", size=(100, 100))
        out = tmp_path / "out.jpg"
        compress_image(inp, out, None, None, 80, None, True, False, False)
        assert out.is_file()

    def test_dry_run_does_not_write(self, tmp_path):
        inp = make_image(tmp_path / "photo.jpg", size=(100, 100))
        out = tmp_path / "out.jpg"
        compress_image(inp, out, None, None, 80, None, False, True, False)
        assert not out.exists()

    def test_output_directory_created(self, tmp_path):
        inp = make_image(tmp_path / "photo.jpg", size=(100, 100))
        out = tmp_path / "nested" / "deep" / "out.jpg"
        compress_image(inp, out, None, None, 80, None, False, False, False)
        assert out.is_file()


# ─────────────────────────────────────────────
# CLI tests
# ─────────────────────────────────────────────

class TestMainCLI:
    def test_missing_input_exits_nonzero(self, tmp_path):
        result = main([str(tmp_path / "missing.jpg")])
        assert result == 1

    def test_invalid_quality_exits_nonzero(self, tmp_path):
        inp = make_image(tmp_path / "photo.jpg")
        result = main([str(inp), "--quality", "0"])
        assert result != 0

    def test_compress_single_file(self, tmp_path):
        inp = make_image(tmp_path / "photo.jpg", size=(200, 200))
        out = tmp_path / "out.jpg"
        result = main([str(inp), str(out)])
        assert result == 0
        assert out.is_file()

    def test_compress_directory(self, tmp_path):
        in_dir = tmp_path / "input"
        in_dir.mkdir()
        out_dir = tmp_path / "output"
        make_image(in_dir / "a.jpg", size=(200, 200))
        make_image(in_dir / "b.png", size=(200, 200))
        result = main([str(in_dir), str(out_dir)])
        assert result == 0
        assert len(list(out_dir.iterdir())) == 2

    def test_dry_run_no_output(self, tmp_path):
        inp = make_image(tmp_path / "photo.jpg", size=(100, 100))
        out = tmp_path / "out.jpg"
        result = main([str(inp), str(out), "--dry-run"])
        assert result == 0
        assert not out.exists()

    def test_format_conversion_via_flag(self, tmp_path):
        inp = make_image(tmp_path / "photo.jpg", size=(100, 100))
        out = tmp_path / "out.webp"
        result = main([str(inp), str(out), "--format", "webp"])
        assert result == 0
        img = Image.open(out)
        assert img.format == "WEBP"

    def test_recursive_flag(self, tmp_path):
        in_dir = tmp_path / "input"
        sub = in_dir / "sub"
        sub.mkdir(parents=True)
        out_dir = tmp_path / "output"
        make_image(in_dir / "a.jpg", size=(100, 100))
        make_image(sub / "b.jpg", size=(100, 100))
        result = main([str(in_dir), str(out_dir), "--recursive"])
        assert result == 0
        outputs = list(out_dir.rglob("*.jpg"))
        assert len(outputs) == 2
