# Python Automation Scripts

A collection of command-line utilities for common file automation tasks.

---

## Scripts

### `html2img.py` — HTML to Image

Renders an HTML file or URL to an image using a headless Chromium browser (Playwright).

**Requirements**
```bash
pip install playwright Pillow
playwright install chromium
```

**Usage**
```
python html2img.py <INPUT> <OUTPUT> [options]
```

| Argument | Description |
|---|---|
| `INPUT` | Path to an HTML file or an `http(s)://` URL |
| `OUTPUT` | Destination image file path |
| `--format FORMAT` | Output format: `png`, `jpg`, `webp`, `bmp`, `tiff`. Inferred from `OUTPUT` extension when omitted; defaults to `png`. |
| `--no-background` | Transparent background. Supported for `png`, `webp`, `tiff` only. |
| `--width PX` | Viewport width in pixels (default: `1280`) |
| `--height PX` | Viewport height in pixels (default: `720`) |
| `--full-page` | Capture the full scrollable page, not just the viewport |
| `--wait MS` | Extra milliseconds to wait after page load (default: `2000`) |
| `--quality 1-100` | Output quality for `jpg`/`webp` (default: `90`). Ignored for `png`. |
| `--scale FACTOR` | Device scale factor; use `2.0` for high-DPI/retina output (default: `1.0`) |
| `--verbose` | Print progress messages |

**Examples**
```bash
# Basic screenshot (format inferred as PNG from extension)
python html2img.py page.html output.png

# Transparent background PNG
python html2img.py page.html output.png --no-background

# JPEG with quality control
python html2img.py page.html output.jpg --quality 85

# WEBP with transparent background
python html2img.py page.html output.webp --no-background

# Screenshot a URL
python html2img.py https://example.com screenshot.png

# Full page at 2x (retina) resolution
python html2img.py page.html output.png --full-page --scale 2.0

# Custom viewport size
python html2img.py page.html output.png --width 1920 --height 1080
```

**Format support**

| Format | Transparent background | Notes |
|---|---|---|
| `png` | Yes | Lossless, best for transparency |
| `jpg` / `jpeg` | No | Lossy, no alpha channel |
| `webp` | Yes | Lossy/lossless, good compression |
| `bmp` | No | Uncompressed, large files |
| `tiff` | Yes | Lossless with LZW compression |

---

### `merge_pdf.py` — Merge PDFs

Combines multiple PDF files into a single document. Natural companion to `split_pdf.py`.

**Requirements**
```bash
pip install pymupdf
```

**Usage**
```
python merge_pdf.py <INPUT [INPUT ...]> <OUTPUT> [options]
```

| Argument | Description |
|---|---|
| `INPUT ...` | PDF files or directories to merge. Last argument is always the output path. |
| `--sort {name,date,none}` | Sort order: `name` (default, alphabetical), `date` (modification time), `none` (preserve given order) |
| `--verbose` | Print per-file progress |

**Examples**
```bash
# Merge specific files
python merge_pdf.py a.pdf b.pdf c.pdf output.pdf

# Merge all PDFs in a directory (sorted by name)
python merge_pdf.py ./docs/ output.pdf

# Merge sorted by modification date
python merge_pdf.py ./docs/ output.pdf --sort date

# Preserve exact argument order
python merge_pdf.py c.pdf a.pdf b.pdf output.pdf --sort none
```

---

### `compress_img.py` — Batch Image Compressor

Compresses, resizes, and converts images. Supports single files or entire directories.

**Requirements**
```bash
pip install Pillow
```

**Usage**
```
python compress_img.py <INPUT> [OUTPUT] [options]
```

| Argument | Description |
|---|---|
| `INPUT` | Image file or directory |
| `OUTPUT` | Output file or directory (default: `./compressed/`) |
| `--format {jpg,png,webp}` | Convert to this format |
| `--max-width PX` | Scale down images wider than this (aspect ratio preserved) |
| `--max-height PX` | Scale down images taller than this (aspect ratio preserved) |
| `--quality 1-100` | JPEG/WebP quality (default: `80`) |
| `--strip-exif` | Remove EXIF/metadata for privacy |
| `--recursive` | Process subdirectories |
| `--dry-run` | Preview without writing files |
| `--verbose` | Show per-file size savings |

**Examples**
```bash
# Compress a single image
python compress_img.py photo.jpg output.jpg --quality 75

# Convert to WebP
python compress_img.py photo.jpg output.webp --format webp

# Resize and strip EXIF from entire directory
python compress_img.py ./photos/ ./compressed/ --max-width 1920 --strip-exif

# Recursive batch, dry run first
python compress_img.py ./photos/ ./out/ --recursive --dry-run
python compress_img.py ./photos/ ./out/ --recursive
```

---

### `dedup_files.py` — Duplicate File Finder

Finds duplicate files by content (SHA-256 hash), not by filename. No pip dependencies.

**Requirements**
```
None — standard library only
```

**Usage**
```
python dedup_files.py <DIRECTORY> [options]
```

| Argument | Description |
|---|---|
| `DIRECTORY` | Directory to scan |
| `--recursive` | Scan subdirectories |
| `--min-size BYTES` | Ignore files smaller than this (default: `1`) |
| `--ext .jpg,.png` | Only check files with these extensions |
| `--action {report,move,delete}` | What to do with duplicates (default: `report`) |
| `--move-to DIR` | Destination when using `--action move` (default: `./duplicates`) |
| `--dry-run` | Preview without making changes |
| `--verbose` | Show per-file progress |

**Examples**
```bash
# Report duplicates
python dedup_files.py ./downloads/

# Recursive scan, images only
python dedup_files.py ./photos/ --recursive --ext .jpg,.png,.webp

# Move duplicates to staging (safe — originals kept)
python dedup_files.py ./downloads/ --action move --move-to ./dupes/

# Preview deletion first, then delete
python dedup_files.py ./downloads/ --action delete --dry-run
python dedup_files.py ./downloads/ --action delete
```

The file with the **earliest modification time** is kept in each duplicate group.

---

### `convert_html_to_pdf.py` — HTML Slides to PDF

Converts a folder of numbered HTML slide files into a single merged PDF using a headless Chrome browser.

**Requirements**
```bash
pip install pypdf
# Also requires Google Chrome, Chromium, or Microsoft Edge installed
```

**Usage**
```bash
# Defaults: converts all numbered HTML files in the script directory
python convert_html_to_pdf.py

# Custom input/output
python convert_html_to_pdf.py --input ./slides --output ./deck.pdf

# A4 portrait
python convert_html_to_pdf.py --size a4 --orientation portrait

# Custom size (width x height in inches)
python convert_html_to_pdf.py --size 11x8.5
```

---

### `split_pdf.py` — Split PDF

Splits a PDF file into individual pages or ranges.

**Requirements**
```bash
pip install pypdf
```

---

### `img2pdf.py` — Images to PDF

Converts image files (or a directory of images) into a single PDF document.

**Requirements**
```bash
pip install Pillow
```

**Usage**
```bash
# Convert all images in a directory
python img2pdf.py ./images output.pdf

# Convert a single image
python img2pdf.py photo.jpg output.pdf

# Custom DPI
python img2pdf.py ./images output.pdf --dpi 150
```

---

### `pdf2img.py` — PDF to Images

Converts PDF pages to image files.

---

### `yt_downloader.py` — YouTube Downloader

Downloads YouTube videos or extracts audio using `yt-dlp`.

**Requirements**
```bash
pip install yt-dlp
```

**Usage**
```bash
# Download video
python yt_downloader.py <URL>

# Audio only
python yt_downloader.py <URL> --audio-only
```

---

### `rename_file.py` — Batch File Rename

Renames files in bulk based on configurable rules.

---

### `translate_pdf.py` — Translate PDF

Translates the text content of a PDF document.

---

## Running Tests

```bash
# Unit and CLI tests (no browser needed)
pytest test_html2img.py -m "not integration"

# All tests including integration (requires Playwright Chromium)
pytest test_html2img.py

# With coverage
pytest test_html2img.py -m "not integration" --cov=html2img --cov-report=term-missing
```
