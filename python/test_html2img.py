"""Tests for html2img.py — HTML to image converter."""

import io
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from html2img import (
    SUPPORTED_FORMATS,
    infer_format_from_path,
    validate_args,
    main,
)


# ─────────────────────────────────────────────
# Unit: format inference
# ─────────────────────────────────────────────

class TestInferFormatFromPath:
    def test_png(self):
        assert infer_format_from_path("output.png") == "png"

    def test_jpg(self):
        assert infer_format_from_path("output.jpg") == "jpg"

    def test_jpeg(self):
        assert infer_format_from_path("output.jpeg") == "jpeg"

    def test_webp(self):
        assert infer_format_from_path("output.webp") == "webp"

    def test_bmp(self):
        assert infer_format_from_path("output.bmp") == "bmp"

    def test_tiff(self):
        assert infer_format_from_path("output.tiff") == "tiff"

    def test_tif_alias(self):
        assert infer_format_from_path("output.tif") == "tiff"

    def test_unknown_extension_defaults_to_png(self):
        assert infer_format_from_path("output.xyz") == "png"

    def test_no_extension_defaults_to_png(self):
        assert infer_format_from_path("output") == "png"

    def test_uppercase_extension(self):
        assert infer_format_from_path("output.PNG") == "png"

    def test_path_with_directories(self):
        assert infer_format_from_path("/some/dir/output.jpg") == "jpg"


# ─────────────────────────────────────────────
# Unit: validate_args
# ─────────────────────────────────────────────

class TestValidateArgs:
    def test_valid_png(self, tmp_path):
        html_file = tmp_path / "page.html"
        html_file.write_text("<h1>Hello</h1>")
        errors = validate_args(str(html_file), "output.png", "png", False, 90)
        assert errors == []

    def test_valid_png_with_transparency(self, tmp_path):
        html_file = tmp_path / "page.html"
        html_file.write_text("<h1>Hello</h1>")
        errors = validate_args(str(html_file), "output.png", "png", True, 90)
        assert errors == []

    def test_transparent_jpg_is_error(self, tmp_path):
        html_file = tmp_path / "page.html"
        html_file.write_text("<h1>Hello</h1>")
        errors = validate_args(str(html_file), "output.jpg", "jpg", True, 90)
        assert len(errors) == 1
        assert "--no-background" in errors[0]

    def test_transparent_bmp_is_error(self, tmp_path):
        html_file = tmp_path / "page.html"
        html_file.write_text("<h1>Hello</h1>")
        errors = validate_args(str(html_file), "output.bmp", "bmp", True, 90)
        assert len(errors) == 1

    def test_transparent_webp_is_valid(self, tmp_path):
        html_file = tmp_path / "page.html"
        html_file.write_text("<h1>Hello</h1>")
        errors = validate_args(str(html_file), "output.webp", "webp", True, 90)
        assert errors == []

    def test_invalid_format(self, tmp_path):
        html_file = tmp_path / "page.html"
        html_file.write_text("<h1>Hello</h1>")
        errors = validate_args(str(html_file), "output.png", "gif", False, 90)
        assert len(errors) == 1
        assert "gif" in errors[0]

    def test_quality_too_low(self, tmp_path):
        html_file = tmp_path / "page.html"
        html_file.write_text("<h1>Hello</h1>")
        errors = validate_args(str(html_file), "output.jpg", "jpg", False, 0)
        assert len(errors) == 1
        assert "quality" in errors[0].lower()

    def test_quality_too_high(self, tmp_path):
        html_file = tmp_path / "page.html"
        html_file.write_text("<h1>Hello</h1>")
        errors = validate_args(str(html_file), "output.jpg", "jpg", False, 101)
        assert len(errors) == 1

    def test_missing_input_file(self, tmp_path):
        errors = validate_args(
            str(tmp_path / "missing.html"), "output.png", "png", False, 90
        )
        assert len(errors) == 1
        assert "not found" in errors[0]

    def test_url_input_skips_file_check(self):
        # URLs are not checked for existence
        errors = validate_args(
            "https://example.com", "output.png", "png", False, 90
        )
        assert errors == []

    def test_multiple_errors(self, tmp_path):
        # bad format + bad quality + missing file → multiple errors (format error stops early)
        errors = validate_args(
            str(tmp_path / "missing.html"), "output.png", "gif", False, 0
        )
        assert len(errors) >= 1


# ─────────────────────────────────────────────
# Unit: CLI argument parsing and main() exit codes
# ─────────────────────────────────────────────

class TestMainCLI:
    def test_missing_required_args(self):
        with pytest.raises(SystemExit) as exc:
            main([])
        assert exc.value.code != 0

    def test_invalid_format_exits_nonzero(self, tmp_path):
        html_file = tmp_path / "page.html"
        html_file.write_text("<h1>Hello</h1>")
        result = main([str(html_file), "output.png", "--format", "gif"])
        assert result == 1

    def test_transparent_jpg_exits_nonzero(self, tmp_path):
        html_file = tmp_path / "page.html"
        html_file.write_text("<h1>Hello</h1>")
        result = main([str(html_file), "output.jpg", "--no-background"])
        assert result == 1

    def test_missing_input_file_exits_nonzero(self, tmp_path):
        result = main([str(tmp_path / "missing.html"), str(tmp_path / "output.png")])
        assert result == 1

    def test_format_inferred_from_output_extension(self, tmp_path):
        """Verify format is inferred from extension without --format flag."""
        html_file = tmp_path / "page.html"
        html_file.write_text("<h1>Hello</h1>")
        output = tmp_path / "output.jpg"

        # Patch html_to_image so we don't need a real browser
        with patch("html2img.html_to_image") as mock_convert:
            result = main([str(html_file), str(output)])
        assert result == 0
        # Confirm 'jpg' was inferred
        assert mock_convert.call_args.kwargs["fmt"] in ("jpg", "jpeg")

    def test_explicit_format_overrides_extension(self, tmp_path):
        html_file = tmp_path / "page.html"
        html_file.write_text("<h1>Hello</h1>")
        output = tmp_path / "output.png"  # extension says png

        with patch("html2img.html_to_image") as mock_convert:
            result = main([str(html_file), str(output), "--format", "webp"])
        assert result == 0
        assert mock_convert.call_args.kwargs["fmt"] == "webp"

    def test_no_background_flag_passed_through(self, tmp_path):
        html_file = tmp_path / "page.html"
        html_file.write_text("<h1>Hello</h1>")
        output = tmp_path / "output.png"

        with patch("html2img.html_to_image") as mock_convert:
            result = main([str(html_file), str(output), "--no-background"])
        assert result == 0
        assert mock_convert.call_args.kwargs["no_background"] is True

    def test_runtime_error_returns_nonzero(self, tmp_path):
        html_file = tmp_path / "page.html"
        html_file.write_text("<h1>Hello</h1>")
        output = tmp_path / "output.png"

        with patch("html2img.html_to_image", side_effect=RuntimeError("Browser crash")):
            result = main([str(html_file), str(output)])
        assert result == 1


# ─────────────────────────────────────────────
# Integration: actual browser rendering
# (requires `playwright install chromium`)
# ─────────────────────────────────────────────

@pytest.mark.integration
class TestHtmlToImageIntegration:
    """Integration tests that launch a real Chromium browser.

    Run with:  pytest -m integration test_html2img.py
    Skip with: pytest -m "not integration" test_html2img.py
    """

    @pytest.fixture
    def html_file(self, tmp_path):
        f = tmp_path / "page.html"
        f.write_text(
            "<html><body style='background:red;margin:0'>"
            "<h1 style='color:white;padding:20px'>Test</h1>"
            "</body></html>"
        )
        return str(f)

    def test_png_output(self, html_file, tmp_path):
        from html2img import html_to_image
        from PIL import Image

        out = str(tmp_path / "output.png")
        html_to_image(html_file, out, "png", False, 400, 200, False, 0, 90, 1.0, False)

        assert Path(out).is_file()
        img = Image.open(out)
        assert img.format == "PNG"
        assert img.width == 400

    def test_jpeg_output(self, html_file, tmp_path):
        from html2img import html_to_image
        from PIL import Image

        out = str(tmp_path / "output.jpg")
        html_to_image(html_file, out, "jpg", False, 400, 200, False, 0, 85, 1.0, False)

        assert Path(out).is_file()
        img = Image.open(out)
        assert img.format == "JPEG"

    def test_png_transparent_background(self, html_file, tmp_path):
        from html2img import html_to_image
        from PIL import Image

        out = str(tmp_path / "output_transparent.png")
        html_to_image(html_file, out, "png", True, 400, 200, False, 0, 90, 1.0, False)

        assert Path(out).is_file()
        img = Image.open(out)
        assert img.mode == "RGBA", "Expected RGBA mode for transparent PNG"

    def test_webp_output(self, html_file, tmp_path):
        from html2img import html_to_image
        from PIL import Image

        out = str(tmp_path / "output.webp")
        html_to_image(html_file, out, "webp", False, 400, 200, False, 0, 80, 1.0, False)

        assert Path(out).is_file()
        img = Image.open(out)
        assert img.format == "WEBP"

    def test_output_directory_created(self, html_file, tmp_path):
        from html2img import html_to_image

        out = str(tmp_path / "nested" / "deep" / "output.png")
        html_to_image(html_file, out, "png", False, 400, 200, False, 0, 90, 1.0, False)
        assert Path(out).is_file()

    def test_url_input(self, tmp_path):
        from html2img import html_to_image

        out = str(tmp_path / "example.png")
        html_to_image(
            "https://example.com", out, "png", False, 800, 600, False, 1000, 90, 1.0, False
        )
        assert Path(out).is_file()
        assert Path(out).stat().st_size > 0
