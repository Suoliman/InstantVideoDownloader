import copy
import io
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from functools import partial

from yt_dlp import YoutubeDL

from companion.core import (
    Cancelled, RequestError, add_cookies, friendly_error, options,
    public_metadata, run_job, validate_url, verify_output,
)
from companion.host import read_message, write_message

ROOT = Path(__file__).resolve().parent.parent


class UrlTests(unittest.TestCase):
    def test_supported_links_and_tracking_removal(self):
        cases = [
            ("https://www.facebook.com/reel/123/?tracking=secret#x", "facebook", "https://www.facebook.com/reel/123/"),
            ("https://m.facebook.com/watch/?v=123&ref=feed", "facebook", "https://m.facebook.com/watch/?v=123"),
            ("https://www.facebook.com/share/r/AbCd/", "facebook", "https://www.facebook.com/share/r/AbCd/"),
            ("https://www.instagram.com/reel/A_b-C/?igsh=secret", "instagram", "https://www.instagram.com/reel/A_b-C/"),
            ("https://www.tiktok.com/@creator/video/123", "tiktok", "https://www.tiktok.com/@creator/video/123"),
            ("https://vm.tiktok.com/AbCd/", "tiktok", "https://vm.tiktok.com/AbCd/"),
        ]
        for value, platform, normalized in cases:
            with self.subTest(value=value):
                self.assertEqual(validate_url(value), (platform, normalized))

    def test_rejects_untrusted_or_non_video_urls(self):
        for url in [
            "https://facebook.com.evil.test/reel/123/", "https://youtube.com/shorts/123",
            "http://facebook.com/reel/123/", "file:///etc/passwd", "https://localhost/reel/123/",
            "https://user:password@facebook.com/reel/123/", "https://facebook.com:999/reel/123/",
            "https://instagram.com/accounts/login/", "https://tiktok.com/@someone",
            "https://www.facebook.com/", "https://[invalid", None,
        ]:
            with self.subTest(url=url), self.assertRaises(RequestError):
                validate_url(url)


class SessionTests(unittest.TestCase):
    def test_only_selected_platform_cookies_enter_memory_jar(self):
        records = [
            {"domain": ".instagram.com", "name": "sessionid", "value": "test-secret", "path": "/", "secure": True},
            {"domain": "instagram.com.evil.test", "name": "bad", "value": "bad"},
            {"domain": ".facebook.com", "name": "other", "value": "other"},
        ]
        with YoutubeDL(options(tempfile.gettempdir())) as ydl:
            add_cookies(ydl, records, "instagram")
            self.assertEqual([(c.name, c.value) for c in ydl.cookiejar], [("sessionid", "test-secret")])
            self.assertIsNone(ydl.cookiejar.filename)

    def test_error_does_not_disclose_extractor_secrets(self):
        error = Exception("403 https://cdn.example/video?session=secret-cookie")
        message = friendly_error(error)
        self.assertNotIn("secret-cookie", message)
        self.assertNotIn("cdn.example", message)
        self.assertIn("rejected", message)

    def test_portrait_dimensions_are_not_mislabeled_as_1920p(self):
        data = public_metadata({"title": "Portrait", "formats": [{"height": 1920, "width": 1080, "vcodec": "h264"}]}, "instagram")
        self.assertEqual(data["qualities"], [{"value": "1920", "label": "1080 × 1920"}])


class ProtocolTests(unittest.TestCase):
    def test_unicode_round_trip(self):
        stream = io.BytesIO()
        value = {"id": "123", "title": "فيديو · 🎬"}
        write_message(stream, value)
        stream.seek(0)
        self.assertEqual(read_message(stream), value)
        self.assertIsNone(read_message(stream))

    def test_rejects_oversized_and_truncated_frames(self):
        for payload in [b"x", struct.pack("=I", 2**21), struct.pack("=I", 20) + b"{}", struct.pack("=I", 2) + b"[]"]:
            with self.subTest(payload=payload), self.assertRaises(RequestError):
                read_message(io.BytesIO(payload))

    def test_real_host_health_check(self):
        frame = io.BytesIO()
        write_message(frame, {"id": "health", "action": "ping"})
        process = subprocess.run([sys.executable, str(ROOT / "companion/host.py")], input=frame.getvalue(), capture_output=True, timeout=15)
        self.assertEqual(process.returncode, 0)
        reply = read_message(io.BytesIO(process.stdout))
        self.assertEqual(reply["id"], "health")
        self.assertEqual(reply["type"], "result")
        self.assertTrue(reply["data"]["ffmpeg"])
        self.assertEqual(reply["data"]["version"], "0.2.0")
        self.assertIn("quicktime-source", reply["data"]["capabilities"])
        self.assertEqual(process.stderr, b"")

    def test_installer_registers_only_specified_extension(self):
        with tempfile.TemporaryDirectory() as folder:
            subprocess.run([
                sys.executable, str(ROOT / "scripts/install_companion.py"),
                "--extension-id", "a" * 32, "--manifest-dir", folder, "--skip-deps", "--no-register",
            ], check=True, capture_output=True)
            manifest = json.loads((Path(folder) / "com.instantvideodownloader.companion.json").read_text())
            self.assertEqual(manifest["allowed_origins"], ["chrome-extension://" + "a" * 32 + "/"])
            self.assertTrue(Path(manifest["path"]).is_file())
            if sys.platform != "win32":
                self.assertEqual(Path(manifest["path"]).stat().st_mode & 0o777, 0o700)


class SilentHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_):
        pass


class MediaIntegrationTests(unittest.TestCase):
    """Use real HTTP, yt-dlp and FFmpeg; replace only unavailable social extraction."""

    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.directory = Path(cls.temporary.name)
        for name, size in [("low", "64x48"), ("high", "128x96")]:
            subprocess.run([
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                f"testsrc=size={size}:rate=10:duration=0.8", "-an", "-c:v", "libx264",
                "-threads", "1", "-pix_fmt", "yuv420p", str(cls.directory / f"{name}.mp4"),
            ], check=True)
        subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
            "sine=frequency=440:duration=0.8", "-vn", "-c:a", "aac", "-threads", "1",
            str(cls.directory / "audio.m4a"),
        ], check=True)
        for extension in ("mp4", "mkv"):
            subprocess.run([
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(cls.directory / "high.mp4"),
                "-i", str(cls.directory / "audio.m4a"), "-map", "0:v:0", "-map", "1:a:0",
                "-c", "copy", str(cls.directory / f"combined.{extension}"),
            ], check=True)
        subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
            "testsrc=size=128x96:rate=10:duration=0.8", "-an", "-c:v", "libaom-av1",
            "-cpu-used", "8", "-threads", "1", "-pix_fmt", "yuv420p", str(cls.directory / "av1.mp4"),
        ], check=True)
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), partial(SilentHandler, directory=str(cls.directory)))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        base = f"http://127.0.0.1:{cls.server.server_port}"
        cls.info = {
            "id": "fixture", "title": "Original stream fixture", "extractor": "Instagram", "extractor_key": "Instagram",
            "webpage_url": "https://www.instagram.com/reel/Test/", "duration": .8,
            "formats": [
                {"format_id": "low", "url": f"{base}/low.mp4", "ext": "mp4", "height": 48, "width": 64, "fps": 10, "vcodec": "avc1", "acodec": "none", "protocol": "http"},
                {"format_id": "high", "url": f"{base}/high.mp4", "ext": "mp4", "height": 96, "width": 128, "fps": 10, "vcodec": "avc1", "acodec": "none", "protocol": "http"},
                {"format_id": "audio", "url": f"{base}/audio.m4a", "ext": "m4a", "abr": 128, "vcodec": "none", "acodec": "mp4a.40.2", "protocol": "http"},
            ],
        }

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cls.temporary.cleanup()

    def job(self, action, quality="best", emit=None, cancelled=None, info=None, output_mode="original"):
        fixture = info if info is not None else self.info
        output = self.directory / f"out-{action}-{quality}-{fixture['id']}"
        output.mkdir(exist_ok=True)
        def extract_fixture(ydl, *_args, **_kwargs):
            # Mirror the real extract_info(download=False) boundary: yt-dlp has
            # already normalized and selected formats before run_job receives it.
            return ydl.process_ie_result(copy.deepcopy(fixture), download=False)

        with patch.object(YoutubeDL, "extract_info", autospec=True, side_effect=extract_fixture):
            return run_job(
                {"action": action, "url": "https://www.instagram.com/reel/Test/", "quality": quality, "outputMode": output_mode},
                emit or (lambda *_: None), cancelled or threading.Event(), directory=output,
            )

    def packet_hashes(self, path, stream="v:0"):
        result = subprocess.run([
            "ffprobe", "-v", "error", "-select_streams", stream, "-show_packets",
            "-show_data_hash", "sha256", "-of", "json", str(path),
        ], check=True, capture_output=True, text=True)
        return [packet["data_hash"] for packet in json.loads(result.stdout)["packets"]]

    def verify_media(self, result, source, height):
        path = Path(result["path"])
        self.assertEqual(path.suffix, ".mp4")
        probe = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)], capture_output=True, text=True, check=True)
        media = json.loads(probe.stdout)
        self.assertIn("mp4", media["format"]["format_name"].split(","), "Output must be an MP4 container, not just a renamed file")
        streams = media["streams"]
        self.assertEqual({s["codec_type"] for s in streams}, {"video", "audio"})
        self.assertEqual(next(s for s in streams if s["codec_type"] == "video")["height"], height)
        self.assertEqual(self.packet_hashes(path), self.packet_hashes(self.directory / source), "Video packets must be byte-identical: no re-encoding")
        self.assertEqual(self.packet_hashes(path, "a:0"), self.packet_hashes(self.directory / "audio.m4a", "a:0"), "Audio packets must be byte-identical: no re-encoding")
        subprocess.run([
            "ffmpeg", "-v", "error", "-i", str(path), "-map", "0:v:0", "-frames:v", "1", "-f", "null", "-",
        ], check=True, capture_output=True, timeout=15)

    def test_highest_quality_download_merges_audio_without_reencoding(self):
        events = []
        result = self.job("download", emit=lambda kind, data: events.append((kind, data)))
        self.verify_media(result, "high.mp4", 96)
        self.assertTrue(any(data["stage"] == "processing" for _, data in events))
        self.assertTrue(any(data["stage"] == "downloading" for _, data in events))

    def test_quality_ceiling_downloads_requested_source(self):
        self.verify_media(self.job("download", quality="48"), "low.mp4", 48)

    def mixed_codec_info(self):
        info = copy.deepcopy(self.info)
        info["id"] = "mixed-codecs"
        info["formats"][1].update({
            "format_id": "av1-high", "vcodec": "av01.0.04M.08",
            "url": f"http://127.0.0.1:{self.server.server_port}/av1.mp4",
        })
        return info

    def test_quicktime_selects_h264_aac_without_transcoding_and_original_keeps_av1(self):
        info = self.mixed_codec_info()
        original = self.job("download", info=info)
        self.verify_media(original, "av1.mp4", 96)
        self.assertFalse(original["media"]["quicktimeCompatible"])
        compatible = self.job("download", info=info, output_mode="quicktime")
        self.verify_media(compatible, "low.mp4", 48)
        self.assertEqual(compatible["media"]["videoCodec"], "h264")
        self.assertEqual(compatible["media"]["audioCodec"], "aac")
        self.assertTrue(compatible["media"]["quicktimeCompatible"])
        self.assertIn("[H264]" if sys.platform == "win32" else "[QuickTime]", compatible["filename"])
        self.assertEqual(Path(original["path"]).parent, Path(compatible["path"]).parent)
        self.assertNotEqual(original["path"], compatible["path"], "QuickTime must not reuse the incompatible original file")
        self.assertEqual(compatible["metadata"]["quicktime"]["qualities"], [{"value": "48", "label": "64 × 48"}])

    def test_quicktime_reports_when_no_compatible_source_is_offered(self):
        info = self.mixed_codec_info()
        info["formats"] = info["formats"][1:]
        with self.assertRaisesRegex(RequestError, "does not offer an H.264/AAC source"):
            self.job("download", info=info, output_mode="quicktime")

    def test_audio_only_output_is_rejected(self):
        with self.assertRaisesRegex(RequestError, "no usable video track"):
            verify_output(self.directory / "audio.m4a")

    def test_missing_expected_audio_is_rejected(self):
        with self.assertRaisesRegex(RequestError, "missing its audio track"):
            verify_output(self.directory / "high.mp4", require_audio=True)

    def test_quicktime_rejects_an_incompatible_video_codec(self):
        with self.assertRaisesRegex(RequestError, "not a standard 8-bit H.264/AAC"):
            verify_output(self.directory / "av1.mp4", output_mode="quicktime")

    def single_source_info(self, extension):
        info = copy.deepcopy(self.info)
        info["id"] = f"single-{extension}"
        info["formats"] = [{
            **info["formats"][1], "format_id": "combined", "ext": extension,
            "acodec": "mp4a.40.2",
            "url": f"http://127.0.0.1:{self.server.server_port}/combined.{extension}",
        }]
        return info

    def test_single_mkv_source_is_remuxed_to_real_mp4_without_reencoding(self):
        self.verify_media(self.job("download", info=self.single_source_info("mkv")), "high.mp4", 96)

    def test_single_mp4_source_remains_original_mp4(self):
        result = self.job("download", info=self.single_source_info("mp4"))
        self.verify_media(result, "high.mp4", 96)
        self.assertEqual(Path(result["path"]).read_bytes(), (self.directory / "combined.mp4").read_bytes())

    def test_repeated_mp4_download_returns_existing_file(self):
        info = self.single_source_info("mp4")
        first = self.job("download", info=info)
        original_stat = Path(first["path"]).stat()
        second = self.job("download", info=info)
        self.assertEqual(first["path"], second["path"])
        self.assertEqual(original_stat.st_mtime_ns, Path(second["path"]).stat().st_mtime_ns)

    def test_inspection_returns_metadata_without_downloading(self):
        metadata = self.job("inspect")
        self.assertEqual(metadata["heights"], [96, 48])
        self.assertFalse(list((self.directory / "out-inspect-best-fixture").iterdir()))

    def test_cancellation_stops_before_download(self):
        cancelled = threading.Event()
        with self.assertRaises(Cancelled):
            self.job("download", emit=lambda *_: cancelled.set(), cancelled=cancelled)


if __name__ == "__main__":
    unittest.main()
