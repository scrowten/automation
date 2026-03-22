import os
import tempfile
import pytest
from yt_downloader import (
    timestamp_to_seconds,
    seconds_to_timestamp,
    sanitize_filename,
    parse_batch_file,
    validate_time_range,
    parse_args,
)


class TestTimestampToSeconds:
    def test_minutes_seconds(self):
        assert timestamp_to_seconds("9:48") == 588

    def test_hours_minutes_seconds(self):
        assert timestamp_to_seconds("1:30:36") == 5436

    def test_zero(self):
        assert timestamp_to_seconds("0:00") == 0

    def test_single_digit_minutes(self):
        assert timestamp_to_seconds("1:05") == 65

    def test_double_digit_hours(self):
        assert timestamp_to_seconds("10:05:30") == 36330

    def test_invalid_format(self):
        with pytest.raises(ValueError, match="Invalid timestamp"):
            timestamp_to_seconds("1:2:3:4")


class TestSecondsToTimestamp:
    def test_minutes_seconds(self):
        assert seconds_to_timestamp(588) == "9:48"

    def test_hours_minutes_seconds(self):
        assert seconds_to_timestamp(5436) == "1:30:36"

    def test_zero(self):
        assert seconds_to_timestamp(0) == "0:00"

    def test_exact_hour(self):
        assert seconds_to_timestamp(3600) == "1:00:00"


class TestSanitizeFilename:
    def test_normal_name(self):
        assert sanitize_filename("Juz 16 — Usth Ulfiya") == "Juz 16 — Usth Ulfiya"

    def test_unsafe_chars(self):
        assert sanitize_filename('test/file:name*"bad') == "test_file_name__bad"

    def test_trailing_dot(self):
        assert sanitize_filename("name.") == "name"

    def test_preserves_spaces_and_dashes(self):
        assert sanitize_filename("Juz 20 — Usth Fathimah Umar") == "Juz 20 — Usth Fathimah Umar"


class TestValidateTimeRange:
    def test_valid_range(self):
        # Should not raise
        validate_time_range(100, 500, 600)

    def test_negative_start(self):
        with pytest.raises(ValueError, match="cannot be negative"):
            validate_time_range(-1, 500, 600)

    def test_end_before_start(self):
        with pytest.raises(ValueError, match="must be after"):
            validate_time_range(500, 100, 600)

    def test_end_equals_start(self):
        with pytest.raises(ValueError, match="must be after"):
            validate_time_range(100, 100, 600)

    def test_end_exceeds_duration(self):
        with pytest.raises(ValueError, match="exceeds video duration"):
            validate_time_range(100, 700, 600)

    def test_zero_duration_skips_check(self):
        # duration=0 means unknown, skip end-of-video check
        validate_time_range(100, 500, 0)


class TestParseBatchFile:
    def _write_temp(self, content):
        f = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8')
        f.write(content)
        f.close()
        return f.name

    def test_standard_format(self):
        path = self._write_temp(
            "Juz 16 — Usth Ulfiya 9:48 – 46:55\n"
            "Juz 17 — Usth Anisah 46:58 – 1:30:36\n"
        )
        try:
            segments = parse_batch_file(path)
            assert len(segments) == 2
            assert segments[0]['label'] == "Juz 16 — Usth Ulfiya"
            assert segments[0]['start'] == 588
            assert segments[0]['end'] == 2815
            assert segments[1]['label'] == "Juz 17 — Usth Anisah"
            assert segments[1]['start'] == 2818
            assert segments[1]['end'] == 5436
        finally:
            os.unlink(path)

    def test_hyphen_separator(self):
        path = self._write_temp("Part 1 0:00 - 5:00\n")
        try:
            segments = parse_batch_file(path)
            assert len(segments) == 1
            assert segments[0]['label'] == "Part 1"
            assert segments[0]['start'] == 0
            assert segments[0]['end'] == 300
        finally:
            os.unlink(path)

    def test_em_dash_separator(self):
        path = self._write_temp("Segment A 1:00:00 — 1:30:00\n")
        try:
            segments = parse_batch_file(path)
            assert segments[0]['start'] == 3600
            assert segments[0]['end'] == 5400
        finally:
            os.unlink(path)

    def test_skips_blank_lines(self):
        path = self._write_temp(
            "Part 1 0:00 – 5:00\n"
            "\n"
            "Part 2 5:00 – 10:00\n"
        )
        try:
            segments = parse_batch_file(path)
            assert len(segments) == 2
        finally:
            os.unlink(path)

    def test_invalid_line_raises(self):
        path = self._write_temp("This is not a valid line\n")
        try:
            with pytest.raises(ValueError, match="Could not parse"):
                parse_batch_file(path)
        finally:
            os.unlink(path)

    def test_empty_file_raises(self):
        path = self._write_temp("\n\n")
        try:
            with pytest.raises(ValueError, match="No segments found"):
                parse_batch_file(path)
        finally:
            os.unlink(path)

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            parse_batch_file("/nonexistent/file.txt")

    def test_full_example(self):
        """Test the exact format from the user's example."""
        path = self._write_temp(
            "Juz 16 — Usth Ulfiya 9:48 – 46:55\n"
            "Juz 17 — Usth Anisah 46:58 – 1:30:36\n"
            "Juz 18 — Usth Wafa' 1:30:40 – 2:15:10\n"
            "Juz 19 — Usth Mariah 2:15:17 – 3:00:50\n"
            "Juz 20 — Usth Fathimah Umar 3:00:53 – 3:40:47\n"
        )
        try:
            segments = parse_batch_file(path)
            assert len(segments) == 5
            assert segments[0]['label'] == "Juz 16 — Usth Ulfiya"
            assert segments[4]['label'] == "Juz 20 — Usth Fathimah Umar"
            assert segments[4]['start'] == timestamp_to_seconds("3:00:53")
            assert segments[4]['end'] == timestamp_to_seconds("3:40:47")
        finally:
            os.unlink(path)


class TestParseArgs:
    def test_download_command(self):
        args = parse_args(["download", "https://youtube.com/watch?v=abc", "-o", "/tmp"])
        assert args.command == "download"
        assert args.url == "https://youtube.com/watch?v=abc"
        assert args.output_dir == "/tmp"
        assert args.audio_only is False

    def test_download_audio_only(self):
        args = parse_args(["download", "URL", "--audio-only"])
        assert args.audio_only is True

    def test_segment_command(self):
        args = parse_args(["segment", "URL", "--start", "9:48", "--end", "46:55", "-o", "/tmp"])
        assert args.command == "segment"
        assert args.start == "9:48"
        assert args.end == "46:55"

    def test_batch_command(self):
        args = parse_args(["batch", "URL", "--timestamps", "file.txt", "--audio-only"])
        assert args.command == "batch"
        assert args.timestamps == "file.txt"
        assert args.audio_only is True
