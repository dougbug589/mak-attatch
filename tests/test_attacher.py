import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from core import attacher, parser, tmdb


def _have(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def _make_video(path: Path, codec: str = None, size: str = "320x240"):
    cmd = ["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=duration=1:size=%s:rate=10" % size]
    if codec:
        cmd += ["-c", codec]
    cmd += [str(path)]
    subprocess.run(cmd, check=True, capture_output=True)


def _make_image(path: Path):
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=blue:s=100x150",
         "-frames:v", "1", str(path)],
        check=True, capture_output=True,
    )


def _pic_count(path: str) -> int:
    probe = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", path],
        capture_output=True, timeout=30,
    )
    streams = json.loads(probe.stdout)["streams"]
    return sum(1 for s in streams if s.get("codec_name") in ("mjpeg", "png"))


def _meta() -> dict:
    return {
        "title": "Test Movie",
        "year": "2024",
        "overview": "A test overview.",
        "tagline": "Test tagline",
        "genres": ["Action", "Drama"],
        "rating": 8.2,
        "media_type": "movie",
        "directors": ["Alice"],
        "writers": ["Bob"],
        "cast": [{"name": "Carol", "character": "Hero"}],
    }


@unittest.skipUnless(_have("ffmpeg") and _have("mkvpropedit"), "ffmpeg/mkvtoolnix required")
def _have_ffmpeg_codec(codec: str) -> bool:
    if not _have("ffmpeg"):
        return False
    try:
        out = subprocess.run(["ffmpeg", "-hide_banner", "-codecs"], capture_output=True).stdout.decode()
        return any(line.startswith(" ") and codec in line for line in out.splitlines())
    except Exception:
        return False


class TestAttacher(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="mak-attatch-test-"))
        cls.img = cls.tmp / "poster.jpg"
        _make_image(cls.img)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_injection_guard(self):
        for bad in ["-V", "--version", "../etc/passwd"]:
            with self.assertRaises(ValueError):
                attacher.attach_poster_mkv(bad, str(self.img))

    def test_mkv_attach_and_metadata(self):
        v = self.tmp / "a.mkv"
        _make_video(v)
        attacher.full_attach(str(v), str(self.img), metadata=_meta())
        self.assertEqual(_pic_count(str(v)), 1)
        fmt = subprocess.run(["ffprobe", "-v", "quiet", "-show_format", str(v)],
                             capture_output=True).stdout.decode()
        self.assertIn("Test Movie", fmt)

    def test_mkv_reattach_dedupes(self):
        v = self.tmp / "b.mkv"
        _make_video(v)
        attacher.attach_poster_mkv(str(v), str(self.img))
        attacher.attach_poster_mkv(str(v), str(self.img))
        self.assertEqual(_pic_count(str(v)), 1)

    def test_mkv_remove_poster(self):
        v = self.tmp / "c.mkv"
        _make_video(v)
        attacher.attach_poster_mkv(str(v), str(self.img))
        attacher.remove_poster(str(v))
        self.assertEqual(_pic_count(str(v)), 0)
        attacher.remove_poster(str(v))

    @unittest.skipUnless(_have_ffmpeg_codec("libx264"), "libx264 required")
    def test_mp4_attach_metadata_remove(self):
        v = self.tmp / "d.mp4"
        _make_video(v, "libx264")
        attacher.full_attach(str(v), str(self.img), metadata=_meta())
        self.assertEqual(_pic_count(str(v)), 1)
        fmt = subprocess.run(["ffprobe", "-v", "quiet", "-show_format", str(v)],
                             capture_output=True).stdout.decode()
        self.assertIn("Test Movie", fmt)
        attacher.attach_poster_mp4(str(v), str(self.img))
        self.assertEqual(_pic_count(str(v)), 1)
        attacher.remove_poster(str(v))
        self.assertEqual(_pic_count(str(v)), 0)

    def _tags(self, path: str) -> list:
        fmt = subprocess.run(["ffprobe", "-v", "quiet", "-show_format", path],
                             capture_output=True).stdout.decode()
        skip = ("TAG:major_brand", "TAG:minor_version", "TAG:compatible_brands")
        return sorted(l for l in fmt.splitlines()
                      if l.startswith("TAG:") and not l.startswith(skip))

    def test_mkv_remove_metadata(self):
        v = self.tmp / "rm.mkv"
        _make_video(v)
        attacher.write_metadata(str(v), _meta())
        self.assertIn("TAG:TITLE=Test Movie", self._tags(str(v)))
        attacher.remove_metadata(str(v))
        tags = self._tags(str(v))
        self.assertNotIn("TAG:TITLE=Test Movie", tags)
        self.assertNotIn("TAG:title=Test Movie", tags)

    @unittest.skipUnless(_have_ffmpeg_codec("libx264"), "libx264 required")
    def test_mp4_remove_metadata(self):
        v = self.tmp / "rm.mp4"
        _make_video(v, "libx264")
        subprocess.run(["ffmpeg", "-y", "-i", str(v), "-map", "0",
                        "-metadata", "title=Old Title", "-metadata", "genre=Old Genre",
                        "-c", "copy", str(self.tmp / "rm2.mp4")],
                       check=True, capture_output=True)
        v = self.tmp / "rm2.mp4"
        self.assertIn("TAG:title=Old Title", self._tags(str(v)))
        attacher.remove_metadata(str(v))
        tags = self._tags(str(v))
        self.assertNotIn("TAG:title=Old Title", tags)
        self.assertNotIn("TAG:genre=Old Genre", tags)

    @unittest.skipUnless(_have_ffmpeg_codec("libx264"), "libx264 required")
    def test_mp4_metadata_overwrites_stale(self):
        v = self.tmp / "ow.mp4"
        _make_video(v, "libx264")
        subprocess.run(["ffmpeg", "-y", "-i", str(v), "-map", "0",
                        "-metadata", "title=Stale Title", "-metadata", "genre=Stale Genre",
                        "-c", "copy", str(self.tmp / "ow2.mp4")],
                       check=True, capture_output=True)
        v = self.tmp / "ow2.mp4"
        attacher.write_metadata(str(v), {"title": "Fresh Title", "genres": ["Action"]})
        tags = self._tags(str(v))
        self.assertIn("TAG:title=Fresh Title", tags)
        self.assertNotIn("Stale", " ".join(tags))

    def test_mkv_metadata_overwrites_stale(self):
        v = self.tmp / "ow.mkv"
        _make_video(v)
        attacher.write_metadata(str(v), {"title": "Stale Title", "genres": ["Horror"]})
        attacher.write_metadata(str(v), {"title": "Fresh Title", "genres": ["Action"]})
        tags = self._tags(str(v))
        self.assertIn("TAG:TITLE=Fresh Title", tags)
        self.assertNotIn("Stale", " ".join(tags))

    def test_remove_metadata_injection_guard(self):
        for bad in ("-V", "../x.mkv", "x; rm -rf /"):
            with self.assertRaises((ValueError, FileNotFoundError)):
                attacher.remove_metadata(bad)

    def test_avi_converts_to_mkv(self):
        v = self.tmp / "e.avi"
        _make_video(v)
        out = attacher.full_attach(str(v), str(self.img), metadata=_meta())
        self.assertTrue(str(out).endswith(".mkv"))
        self.assertEqual(_pic_count(str(out)), 1)

    def test_tags_xml(self):
        xml = attacher.build_mkv_tags_xml(_meta())
        self.assertIn("Test Movie", xml)
        self.assertIn("Hero", xml)

    def test_mp4_flags(self):
        flags = attacher._mp4_metadata_flags(_meta())
        self.assertIn("-metadata", flags)
        self.assertIn("title=Test Movie", flags)


class TestParser(unittest.TestCase):
    def test_movie(self):
        p = parser.parse_filename("/v/Interstellar.2014.1080p.mkv")
        self.assertEqual(p["title"], "Interstellar")
        self.assertEqual(p["year"], "2014")

    def test_episode(self):
        p = parser.parse_filename("/v/Breaking.Bad.S01E03.mkv")
        self.assertEqual(p["type"], "episode")
        self.assertEqual(p["season"], 1)
        self.assertEqual(p["episode"], 3)


class TestSharedCore(unittest.TestCase):
    def test_no_vendored_core_in_tui(self):
        tui_core = Path(__file__).resolve().parents[1] / "poster_tui" / "core"
        self.assertFalse(
            tui_core.exists(),
            "poster_tui/ must not carry a vendored core copy; TUI uses the shared core/",
        )

    def test_tui_imports_shared_core(self):
        try:
            import poster_tui.app
        except ImportError:
            self.skipTest("textual not installed")
        self.assertTrue(poster_tui.app.attacher.__name__.startswith("core"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
