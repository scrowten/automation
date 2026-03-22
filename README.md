# automation

Collection of scripts for automating tasks.

## Prerequisites

- Python 3.10+
- pip packages: `pip install yt-dlp pymupdf`
- System dependencies: `ffmpeg` (required for YouTube Downloader segment extraction)

## Scripts

### Document Tools

| Script | Description |
|--------|-------------|
| [convert_html_to_pdf.py](python/convert_html_to_pdf.py) | Convert HTML file(s) to PDF |
| [img2pdf.py](python/img2pdf.py) | Convert image(s) to PDF |
| [pdf2img.py](python/pdf2img.py) | Convert PDF to image(s) |
| [split_pdf.py](python/split_pdf.py) | Split PDF into parts or extract page ranges |
| [rename_file.py](python/rename_file.py) | Rename multiple files with pattern matching |
| [translate_pdf.py](python/translate_pdf.py) | Translate PDF content (WIP) |

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
