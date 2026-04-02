# automation

Collection of scripts for automating tasks.

## Prerequisites

- Python 3.10+
- pip packages: `pip install yt-dlp pymupdf playwright Pillow`
- System dependencies: `ffmpeg` (required for YouTube Downloader segment extraction)
- Playwright browser: `playwright install chromium` (required for `html2img.py` and `convert_html_to_pdf.py`)

## Scripts

### Document Tools

| Script | Description |
|--------|-------------|
| [html2img.py](python/html2img.py) | Convert HTML file or URL to image (PNG, JPG, WEBP, BMP, TIFF) |
| [convert_html_to_pdf.py](python/convert_html_to_pdf.py) | Convert HTML file(s) to PDF |
| [img2pdf.py](python/img2pdf.py) | Convert image(s) to PDF |
| [pdf2img.py](python/pdf2img.py) | Convert PDF to image(s) |
| [split_pdf.py](python/split_pdf.py) | Split PDF into parts or extract page ranges |
| [rename_file.py](python/rename_file.py) | Rename multiple files with pattern matching |
| [translate_pdf.py](python/translate_pdf.py) | Translate PDF content (WIP) |

#### HTML to Image

Convert an HTML file or URL to an image using a headless Chromium browser.

```bash
# Basic screenshot
python html2img.py page.html output.png

# Transparent background (PNG/WEBP only)
python html2img.py page.html output.png --no-background

# Screenshot a URL
python html2img.py https://example.com screenshot.png

# Full page at retina resolution
python html2img.py page.html output.png --full-page --scale 2.0

# JPEG with quality control
python html2img.py page.html output.jpg --quality 85
```

See [python/README.md](python/README.md) for the full option reference.

### Media Tools

| Script | Description |
|--------|-------------|
| [yt_downloader.py](python/yt_downloader.py) | Download YouTube videos, audio, or segments by timestamp |

#### YouTube Downloader

Download full videos/audio or extract specific segments using timestamps.

**Full download:**

```bash
# Video (MP4)
python yt_downloader.py download "URL" -o ./output

# Audio only (MP3)
python yt_downloader.py download "URL" -o ./output --audio-only
```

**Single segment:**

```bash
python yt_downloader.py segment "URL" --start 9:48 --end 46:55 -o ./output
python yt_downloader.py segment "URL" --start 9:48 --end 46:55 --label "My Clip" -o ./output --audio-only
```

**Batch segments from timestamp file:**

```bash
python yt_downloader.py batch "URL" --timestamps timestamps.txt -o ./output --audio-only
```

Timestamp file format — each line is `Label START – END`:

```
Juz 16 — Usth Ulfiya 9:48 – 46:55
Juz 17 — Usth Anisah 46:58 – 1:30:36
Juz 18 — Usth Wafa' 1:30:40 – 2:15:10
```

Supported timestamp formats: `M:SS`, `MM:SS`, `H:MM:SS`. Separators: `-`, `–`, `—`.

Each segment is saved as a separate file named after the label (e.g., `Juz 16 — Usth Ulfiya.mp3`).
