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
| [merge_pdf.py](python/merge_pdf.py) | Merge multiple PDFs into one |
| [split_pdf.py](python/split_pdf.py) | Split PDF into parts or extract page ranges |
| [img2pdf.py](python/img2pdf.py) | Convert image(s) to PDF |
| [pdf2img.py](python/pdf2img.py) | Convert PDF to image(s) |
| [rename_file.py](python/rename_file.py) | Rename multiple files with pattern matching |
| [translate_pdf.py](python/translate_pdf.py) | Translate PDF content (WIP) |

### File Management Tools

| Script | Description |
|--------|-------------|
| [compress_img.py](python/compress_img.py) | Batch compress, resize, and convert images |
| [dedup_files.py](python/dedup_files.py) | Find and remove duplicate files by content hash |

#### HTML to Image

```bash
python html2img.py page.html output.png
python html2img.py page.html output.png --no-background   # transparent
python html2img.py https://example.com screenshot.png     # URL support
python html2img.py page.html output.png --full-page --scale 2.0
```

#### Merge / Split PDFs

```bash
python merge_pdf.py a.pdf b.pdf c.pdf output.pdf
python merge_pdf.py ./docs/ output.pdf --sort date
python split_pdf.py split input.pdf ./parts/
python split_pdf.py extract input.pdf pages_1_to_5.pdf 1 5
```

#### Compress Images

```bash
python compress_img.py photo.jpg output.jpg --quality 75
python compress_img.py ./photos/ ./compressed/ --max-width 1920 --strip-exif
python compress_img.py ./photos/ ./out/ --format webp --recursive
```

#### Find Duplicates

```bash
python dedup_files.py ./downloads/                        # report only
python dedup_files.py ./photos/ --recursive --ext .jpg,.png
python dedup_files.py ./downloads/ --action move --move-to ./dupes/
python dedup_files.py ./downloads/ --action delete --dry-run
```

See [python/README.md](python/README.md) for the full option reference for each script.

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
