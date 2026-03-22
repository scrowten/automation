import os
import re
import sys
import hashlib
import argparse
import subprocess
import yt_dlp


# Characters not allowed in filenames
UNSAFE_FILENAME_CHARS = re.compile(r'[\\/:*?"<>|]')

# Timestamp patterns: supports M:SS, MM:SS, H:MM:SS, HH:MM:SS
TIMESTAMP_RE = re.compile(r'(\d{1,2}:\d{2}(?::\d{2})?)')

# Batch line: everything before first timestamp is the label
BATCH_LINE_RE = re.compile(
    r'^(.+?)\s+(\d{1,2}:\d{2}(?::\d{2})?)\s*[–\-—]+\s*(\d{1,2}:\d{2}(?::\d{2})?)\s*$'
)


def timestamp_to_seconds(ts):
    """Convert a timestamp string (M:SS, MM:SS, H:MM:SS) to total seconds."""
    parts = ts.strip().split(':')
    if len(parts) == 2:
        minutes, seconds = int(parts[0]), int(parts[1])
        return minutes * 60 + seconds
    elif len(parts) == 3:
        hours, minutes, seconds = int(parts[0]), int(parts[1]), int(parts[2])
        return hours * 3600 + minutes * 60 + seconds
    else:
        raise ValueError(f"Invalid timestamp format: '{ts}'")


def seconds_to_timestamp(total_seconds):
    """Convert total seconds to H:MM:SS format."""
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    if hours > 0:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


def sanitize_filename(name):
    """Remove or replace characters unsafe for filenames."""
    return UNSAFE_FILENAME_CHARS.sub('_', name).strip().rstrip('.')


def get_video_info(url, verbose=False):
    """Fetch video metadata using yt-dlp."""
    opts = {
        'quiet': not verbose,
        'no_warnings': not verbose,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    return {
        'title': info.get('title', 'video'),
        'duration': info.get('duration', 0),
        'url': url,
    }


def validate_time_range(start_sec, end_sec, duration):
    """Validate that the time range is within the video duration."""
    if start_sec < 0:
        raise ValueError(f"Start time ({seconds_to_timestamp(start_sec)}) cannot be negative.")
    if end_sec <= start_sec:
        raise ValueError(
            f"End time ({seconds_to_timestamp(end_sec)}) must be after "
            f"start time ({seconds_to_timestamp(start_sec)})."
        )
    if duration > 0 and end_sec > duration:
        raise ValueError(
            f"End time ({seconds_to_timestamp(end_sec)}) exceeds "
            f"video duration ({seconds_to_timestamp(duration)})."
        )


def parse_batch_file(filepath):
    """Parse a batch timestamp file into a list of segments.

    Each line should be in the format:
        Label START_TIME – END_TIME

    Examples:
        Juz 16 — Usth Ulfiya 9:48 – 46:55
        Juz 17 — Usth Anisah 46:58 – 1:30:36

    Returns:
        list of dicts with keys: label, start, end (in seconds)
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Timestamp file not found: {filepath}")

    segments = []
    with open(filepath, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue

            match = BATCH_LINE_RE.match(line)
            if not match:
                raise ValueError(
                    f"Line {line_num}: Could not parse '{line}'. "
                    f"Expected format: 'Label START – END' (e.g., 'Juz 16 — Usth Ulfiya 9:48 – 46:55')"
                )

            label = match.group(1).strip()
            start_ts = match.group(2)
            end_ts = match.group(3)

            segments.append({
                'label': label,
                'start': timestamp_to_seconds(start_ts),
                'end': timestamp_to_seconds(end_ts),
            })

    if not segments:
        raise ValueError(f"No segments found in '{filepath}'.")

    return segments


def check_ffmpeg():
    """Check that ffmpeg is available on the system."""
    try:
        subprocess.run(
            ['ffmpeg', '-version'],
            capture_output=True, check=True,
        )
    except FileNotFoundError:
        raise RuntimeError(
            "ffmpeg is not installed or not in PATH. "
            "Install it with: sudo apt-get install ffmpeg"
        )


def download_full(url, output_dir, audio_only=False, verbose=False):
    """Download a full video or audio from a YouTube URL."""
    os.makedirs(output_dir, exist_ok=True)

    opts = {
        'outtmpl': os.path.join(output_dir, '%(title)s.%(ext)s'),
        'quiet': not verbose,
        'no_warnings': not verbose,
    }

    if audio_only:
        opts['format'] = 'bestaudio/best'
        opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }]
    else:
        opts['format'] = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
        opts['merge_output_format'] = 'mp4'

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)

    title = info.get('title', 'video')
    ext = 'mp3' if audio_only else 'mp4'
    print(f"Downloaded: {title}.{ext}")


def download_segment(url, output_dir, start_sec, end_sec, label=None,
                     audio_only=False, verbose=False):
    """Download a segment of a video between start and end timestamps.

    Uses yt-dlp to get the stream URL, then ffmpeg to extract the segment.
    """
    check_ffmpeg()
    os.makedirs(output_dir, exist_ok=True)

    info = get_video_info(url, verbose=verbose)
    duration = info['duration']
    title = info['title']

    validate_time_range(start_sec, end_sec, duration)

    filename_base = sanitize_filename(label if label else title)
    ext = 'mp3' if audio_only else 'mp4'
    output_path = os.path.join(output_dir, f"{filename_base}.{ext}")

    # Get direct stream URL via yt-dlp
    opts = {
        'quiet': True,
        'no_warnings': True,
    }
    if audio_only:
        opts['format'] = 'bestaudio/best'
    else:
        opts['format'] = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'

    with yt_dlp.YoutubeDL(opts) as ydl:
        info_full = ydl.extract_info(url, download=False)

    # For merged formats, download full then cut; for single format, stream-cut
    stream_url = info_full.get('url')
    if not stream_url:
        # Merged format: download full video to temp, then extract segment
        return _download_and_cut(url, output_dir, output_path, start_sec,
                                 end_sec, audio_only, verbose)

    # Direct stream: use ffmpeg to extract segment without full download
    start_ts = seconds_to_timestamp(start_sec)
    duration_sec = end_sec - start_sec

    cmd = [
        'ffmpeg', '-y',
        '-ss', str(start_sec),
        '-i', stream_url,
        '-t', str(duration_sec),
    ]

    if audio_only:
        cmd.extend(['-vn', '-acodec', 'libmp3lame', '-q:a', '2'])
    else:
        cmd.extend(['-c', 'copy', '-avoid_negative_ts', 'make_zero'])

    cmd.append(output_path)

    if verbose:
        print(f"Extracting segment: {start_ts} to {seconds_to_timestamp(end_sec)}")

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        # Fallback: download full then cut
        if verbose:
            print("Direct stream cut failed, falling back to download-then-cut...")
        return _download_and_cut(url, output_dir, output_path, start_sec,
                                 end_sec, audio_only, verbose)

    print(f"Saved: {os.path.basename(output_path)}")
    return output_path


def _temp_filename(url, audio_only):
    """Generate a unique temp filename based on URL to avoid collisions."""
    url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
    ext = 'm4a' if audio_only else 'mp4'
    return f'_temp_{url_hash}.{ext}'


def _download_and_cut(url, output_dir, output_path, start_sec, end_sec,
                      audio_only, verbose):
    """Fallback: download the full video, then extract segment with ffmpeg."""
    temp_path = os.path.join(output_dir, _temp_filename(url, audio_only))

    if audio_only:
        opts = {
            'outtmpl': temp_path,
            'format': 'bestaudio/best',
            'quiet': not verbose,
            'no_warnings': not verbose,
        }
    else:
        opts = {
            'outtmpl': temp_path,
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'merge_output_format': 'mp4',
            'quiet': not verbose,
            'no_warnings': not verbose,
        }

    if verbose:
        print("Downloading full video for segment extraction...")

    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])

    duration_sec = end_sec - start_sec
    cmd = [
        'ffmpeg', '-y',
        '-ss', str(start_sec),
        '-i', temp_path,
        '-t', str(duration_sec),
    ]

    if audio_only:
        cmd.extend(['-vn', '-acodec', 'libmp3lame', '-q:a', '2'])
    else:
        cmd.extend(['-c', 'copy', '-avoid_negative_ts', 'make_zero'])

    cmd.append(output_path)

    result = subprocess.run(cmd, capture_output=True, text=True)

    # Clean up temp file
    if os.path.exists(temp_path):
        os.remove(temp_path)

    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg segment extraction failed:\n{result.stderr}")

    print(f"Saved: {os.path.basename(output_path)}")
    return output_path


def download_batch(url, output_dir, timestamps_file, audio_only=False, verbose=False):
    """Download multiple segments from a video using a timestamp file."""
    check_ffmpeg()

    segments = parse_batch_file(timestamps_file)
    info = get_video_info(url, verbose=verbose)
    duration = info['duration']
    title = info['title']

    print(f"Video: {title} (duration: {seconds_to_timestamp(duration)})")
    print(f"Segments to extract: {len(segments)}")

    # Validate all segments before downloading
    for i, seg in enumerate(segments, 1):
        try:
            validate_time_range(seg['start'], seg['end'], duration)
        except ValueError as e:
            raise ValueError(f"Segment {i} ({seg['label']}): {e}")

    # Download full video once, then extract all segments
    os.makedirs(output_dir, exist_ok=True)
    temp_path = os.path.join(output_dir, _temp_filename(url, audio_only))

    if audio_only:
        opts = {
            'outtmpl': temp_path,
            'format': 'bestaudio/best',
            'quiet': not verbose,
            'no_warnings': not verbose,
        }
    else:
        opts = {
            'outtmpl': temp_path,
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'merge_output_format': 'mp4',
            'quiet': not verbose,
            'no_warnings': not verbose,
        }

    if verbose:
        print("Downloading full video...")

    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])

    print("Extracting segments...")

    ext = 'mp3' if audio_only else 'mp4'
    for i, seg in enumerate(segments, 1):
        filename = sanitize_filename(seg['label'])
        output_path = os.path.join(output_dir, f"{filename}.{ext}")
        duration_sec = seg['end'] - seg['start']

        cmd = [
            'ffmpeg', '-y',
            '-ss', str(seg['start']),
            '-i', temp_path,
            '-t', str(duration_sec),
        ]

        if audio_only:
            cmd.extend(['-vn', '-acodec', 'libmp3lame', '-q:a', '2'])
        else:
            cmd.extend(['-c', 'copy', '-avoid_negative_ts', 'make_zero'])

        cmd.append(output_path)

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            print(f"  [{i}/{len(segments)}] FAILED: {seg['label']} — {result.stderr.strip()}", file=sys.stderr)
        else:
            print(f"  [{i}/{len(segments)}] Saved: {filename}.{ext}")

    # Clean up temp file
    if os.path.exists(temp_path):
        os.remove(temp_path)

    print("Batch extraction complete.")


def parse_args(argv=None):
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Download YouTube videos, audio, or segments by timestamp."
    )
    subparsers = parser.add_subparsers(dest="command", required=True, help="Available commands")

    # --- download command ---
    parser_dl = subparsers.add_parser("download", help="Download a full video or audio.")
    parser_dl.add_argument("url", help="YouTube video URL.")
    parser_dl.add_argument("-o", "--output-dir", default=".", help="Output directory (default: current dir).")
    parser_dl.add_argument("--audio-only", action="store_true", help="Download audio only as MP3.")
    parser_dl.add_argument("--verbose", action="store_true", help="Print progress messages.")

    # --- segment command ---
    parser_seg = subparsers.add_parser("segment", help="Download a specific time segment.")
    parser_seg.add_argument("url", help="YouTube video URL.")
    parser_seg.add_argument("--start", required=True, help="Start timestamp (e.g., 9:48 or 1:30:40).")
    parser_seg.add_argument("--end", required=True, help="End timestamp (e.g., 46:55 or 2:15:10).")
    parser_seg.add_argument("--label", help="Output filename label (default: video title).")
    parser_seg.add_argument("-o", "--output-dir", default=".", help="Output directory (default: current dir).")
    parser_seg.add_argument("--audio-only", action="store_true", help="Extract audio only as MP3.")
    parser_seg.add_argument("--verbose", action="store_true", help="Print progress messages.")

    # --- batch command ---
    parser_batch = subparsers.add_parser("batch", help="Extract multiple segments from a timestamp file.")
    parser_batch.add_argument("url", help="YouTube video URL.")
    parser_batch.add_argument("--timestamps", required=True, help="Path to timestamp file.")
    parser_batch.add_argument("-o", "--output-dir", default=".", help="Output directory (default: current dir).")
    parser_batch.add_argument("--audio-only", action="store_true", help="Extract audio only as MP3.")
    parser_batch.add_argument("--verbose", action="store_true", help="Print progress messages.")

    return parser.parse_args(argv)


def main(argv=None):
    """Main function to execute the script from the command line."""
    args = parse_args(argv)

    try:
        if args.command == "download":
            download_full(args.url, args.output_dir, args.audio_only, args.verbose)

        elif args.command == "segment":
            start_sec = timestamp_to_seconds(args.start)
            end_sec = timestamp_to_seconds(args.end)
            download_segment(
                args.url, args.output_dir, start_sec, end_sec,
                label=args.label, audio_only=args.audio_only, verbose=args.verbose,
            )

        elif args.command == "batch":
            download_batch(
                args.url, args.output_dir, args.timestamps,
                audio_only=args.audio_only, verbose=args.verbose,
            )

    except (FileNotFoundError, ValueError, RuntimeError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
