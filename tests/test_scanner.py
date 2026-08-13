import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core import scanner


def _have(cmd: str) -> bool:
    return shutil.which(cmd) is not None


class ScanTreeTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="mak-scan-")
        self.root = self._tmp

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _touch(self, rel: str) -> str:
        p = Path(self.root) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.touch()
        return str(p)

    def test_iter_video_files_recursive_sorted(self):
        a = self._touch("Series/Season 1/Series S01E01.mkv")
        b = self._touch("Series/Season 1/Series S01E02.mkv")
        self._touch("readme.txt")
        self._touch("Series/Season 1/cover.png")
        self.assertEqual([a, b], scanner.iter_video_files(self.root))

    def test_iter_video_files_ignores_missing_root(self):
        self.assertEqual([], scanner.iter_video_files("/nonexistent/nope"))

    def test_classify_series_seasons_and_movies(self):
        self._touch("Series/Season 1/Series S01E01.mkv")
        self._touch("Series/Season 1/Series S01E02.mkv")
        self._touch("Series/Season 2/Series S02E01.mkv")
        self._touch("Movie (2020)/Movie (2020).mkv")
        groups = scanner.classify(scanner.iter_video_files(self.root))
        by_key = {g.key: g for g in groups}
        self.assertIn("show|series|1", by_key)
        self.assertIn("show|series|2", by_key)
        self.assertIn("movie|movie|0", by_key)
        self.assertEqual(len(by_key["show|series|1"].files), 2)
        self.assertEqual(by_key["show|series|1"].season, 1)
        self.assertEqual(by_key["show|series|2"].season, 2)
        self.assertEqual(by_key["movie|movie|0"].year, "2020")

    def test_classify_folder_fallback_episode_markers(self):
        self._touch("Series Two Season 3/EP01.mkv")
        self._touch("A Real Movie (2019)/12345.mkv")
        groups = scanner.classify(scanner.iter_video_files(self.root))
        by_key = {g.key: g for g in groups}
        self.assertIn("show|series two|3", by_key)
        self.assertIn("movie|a real movie|0", by_key)
        self.assertEqual(by_key["movie|a real movie|0"].year, "2019")

    def test_classify_series_without_season_number(self):
        self._touch("Test Show S01E01.mkv")
        self._touch("Random Show Episode 2.mkv")
        groups = scanner.classify(scanner.iter_video_files(self.root))
        self.assertEqual([g.kind for g in groups], ["show", "show"])
        by_title = {g.title.lower(): g for g in groups}
        self.assertIsNone(by_title["random show"].season)
        self.assertEqual(by_title["test show"].season, 1)

    def test_classify_preserves_order(self):
        self._touch("B Movie (2018).mkv")
        self._touch("A Show S01E01.mkv")
        groups = scanner.classify(scanner.iter_video_files(self.root))
        self.assertEqual([g.key for g in groups],
                         ["show|a show|1", "movie|b movie|0"])


@unittest.skipUnless(
    _have("ffmpeg") and _have("mkvpropedit") and _have("mkvmerge"),
    "ffmpeg/mkvtoolnix required",
)
class HasPosterTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="mak-poster-")

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _video(self, name: str) -> str:
        p = Path(self._tmp) / name
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i",
             "testsrc=duration=1:size=320x240:rate=10",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", str(p)],
            check=True, capture_output=True,
        )
        return str(p)

    def _image(self, name: str) -> str:
        p = Path(self._tmp) / name
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=blue:s=100x150",
             "-frames:v", "1", str(p)],
            check=True, capture_output=True,
        )
        return str(p)

    def test_mkv_plain_false(self):
        self.assertFalse(scanner.has_poster(self._video("plain.mkv")))

    def test_mkv_with_attachment_true(self):
        video = self._video("art.mkv")
        img = self._image("cover.jpg")
        subprocess.run(
            ["mkvpropedit", video, "--attachment-mime-type", "image/jpeg",
             "--attachment-name", "cover.jpg", "--add-attachment", img],
            check=True, capture_output=True,
        )
        self.assertTrue(scanner.has_poster(video))

    def test_mp4_plain_false_then_with_pic_true(self):
        video = self._video("plain.mp4")
        self.assertFalse(scanner.has_poster(video))
        img = self._image("cover.jpg")
        out = video + ".out.mp4"
        subprocess.run(
            ["ffmpeg", "-y", "-i", video, "-i", img, "-map", "0", "-map", "1",
             "-c", "copy", "-disposition:v:1", "attached_pic", out],
            check=True, capture_output=True,
        )
        os.replace(out, video)
        self.assertTrue(scanner.has_poster(video))

    def test_unsupported_extension_false(self):
        self.assertFalse(scanner.has_poster(os.path.join(self._tmp, "clip.avi")))


class HasPosterCacheTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="mak-cache-")
        self.video = str(Path(self._tmp) / "clip.mkv")
        Path(self.video).touch()
        scanner.clear_poster_cache()

    def tearDown(self):
        scanner.clear_poster_cache()
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _no_attachments_result(self):
        result = mock.Mock()
        result.stdout = b'{"attachments": []}'
        return result

    def test_repeat_lookup_hits_cache(self):
        with mock.patch.object(scanner.subprocess, "run",
                               return_value=self._no_attachments_result()) as run:
            self.assertFalse(scanner.has_poster(self.video))
            self.assertFalse(scanner.has_poster(self.video))
            self.assertEqual(run.call_count, 1)

    def test_mtime_change_invalidates_entry(self):
        with mock.patch.object(scanner.subprocess, "run",
                               return_value=self._no_attachments_result()) as run:
            self.assertFalse(scanner.has_poster(self.video))
            self.assertFalse(scanner.has_poster(self.video))
            self.assertEqual(run.call_count, 1)
            os.utime(self.video, ns=(1_700_000_000, 1_700_000_000))
            self.assertFalse(scanner.has_poster(self.video))
            self.assertEqual(run.call_count, 2)

    def test_clear_poster_cache_single_path(self):
        other = str(Path(self._tmp) / "other.mkv")
        Path(other).touch()
        with mock.patch.object(scanner.subprocess, "run",
                               return_value=self._no_attachments_result()) as run:
            self.assertFalse(scanner.has_poster(self.video))
            self.assertFalse(scanner.has_poster(other))
            self.assertEqual(run.call_count, 2)
            scanner.clear_poster_cache(self.video)
            self.assertFalse(scanner.has_poster(self.video))
            self.assertFalse(scanner.has_poster(other))
            self.assertEqual(run.call_count, 3)


if __name__ == "__main__":
    unittest.main()
