import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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


try:
    from ui.main_window import BatchWorker, MainWindow
except Exception:  # PyQt6 not installed (CI test runner)
    BatchWorker = None
    MainWindow = None


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


class TestBatchWorker(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="mak-attatch-batch-test-"))
        cls.img = cls.tmp / "poster.jpg"
        _make_image(cls.img)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    @unittest.skipIf(BatchWorker is None, "PyQt6 not installed")
    def test_batch_attach_all_succeed(self):
        v1 = self.tmp / "one.mkv"
        v2 = self.tmp / "two.mkv"
        _make_video(v1)
        _make_video(v2)
        worker = BatchWorker([str(v1), str(v2)], str(self.img))
        worker.run()
        self.assertTrue(all(r["ok"] for r in worker.results), worker.results)
        self.assertEqual(_pic_count(str(v1)), 1)
        self.assertEqual(_pic_count(str(v2)), 1)

    @unittest.skipIf(BatchWorker is None, "PyQt6 not installed")
    def test_batch_cleans_up_temp_poster_after_use(self):
        v1 = self.tmp / "three.mkv"
        _make_video(v1)
        temp_poster = self.tmp / "temp_poster.jpg"
        shutil.copyfile(self.img, temp_poster)
        worker = BatchWorker([str(v1)], str(temp_poster), cleanup_poster=True)
        worker.run()
        self.assertTrue(all(r["ok"] for r in worker.results), worker.results)
        self.assertFalse(temp_poster.exists(), "temp poster should be cleaned up after use")

    @unittest.skipIf(BatchWorker is None, "PyQt6 not installed")
    def test_batch_keeps_local_poster(self):
        v1 = self.tmp / "four.mkv"
        _make_video(v1)
        worker = BatchWorker([str(v1)], str(self.img), cleanup_poster=False)
        worker.run()
        self.assertTrue(all(r["ok"] for r in worker.results), worker.results)
        self.assertTrue(self.img.exists(), "user-selected local poster must not be deleted")


class TestBatchAttachTargets(unittest.TestCase):
    @unittest.skipIf(MainWindow is None, "PyQt6 not installed")
    def test_batch_attach_uses_selected_targets_not_all_files(self):
        from unittest.mock import Mock

        from ui import main_window as mw

        captured = {}

        class FakeWorker:
            def __init__(self, paths, poster_path, metadata, cleanup_poster=False):
                captured["paths"] = list(paths)
                captured["poster"] = poster_path
                captured["cleanup"] = cleanup_poster
                self.progress = Mock()
                self.finished = Mock()

            def start(self):
                pass

        window = mw.MainWindow.__new__(mw.MainWindow)
        window.video_paths = ["/tmp/all-a.mkv", "/tmp/all-b.mkv", "/tmp/all-c.mkv"]
        window.selected_video_paths = {"/tmp/all-b.mkv"}
        window.video_path = None
        window.local_poster_path = None
        window.progress = Mock()
        window.status_label = Mock()

        with patch.object(mw, "BatchWorker", FakeWorker):
            window._batch_attach(["/tmp/all-b.mkv"], "/tmp/poster.jpg")

        self.assertEqual(captured["paths"], ["/tmp/all-b.mkv"])
        self.assertEqual(captured["poster"], "/tmp/poster.jpg")


class TestPosterTuiPosterGallery(unittest.TestCase):
    def test_reloading_posters_does_not_collide_cell_ids(self):
        try:
            import asyncio
            import types

            from textual.widgets import ListItem

            import poster_tui.app as tui_app
        except ImportError:
            self.skipTest("textual not installed")

        app = tui_app.PosterTuiApp()
        app._show_image_preview = lambda *args, **kwargs: None
        posters = [
            {"width": 2000, "height": 3000, "lang": "en", "thumb_url": "", "url": ""},
            {"width": 500, "height": 750, "lang": "fr", "thumb_url": "", "url": ""},
        ]

        async def run():
            async with app.run_test():
                app._on_posters_loaded(posters)
                await asyncio.sleep(0.05)
                ids1 = sorted(i.id for i in app.query_one("#poster_gallery").query(ListItem))
                app._on_posters_loaded(posters)
                await asyncio.sleep(0.05)
                ids2 = sorted(i.id for i in app.query_one("#poster_gallery").query(ListItem))
                self.assertEqual(len(ids1), 2)
                self.assertEqual(len(ids2), 2, f"stale cells collided: {ids2}")
                self.assertEqual(len(set(ids2)), 2, f"duplicate cell ids: {ids2}")
                self.assertNotEqual(ids1, ids2, "regeneration did not change cell ids")

                app.on_poster_selected(
                    types.SimpleNamespace(item=types.SimpleNamespace(id=ids2[1]))
                )
                self.assertIs(app.selected_poster, posters[1])

        asyncio.run(run())


class TestDetailsForPath(unittest.TestCase):
    def test_uses_explicit_media(self):
        with patch("core.tmdb.get_details", return_value={"title": "X"}) as gd, \
                patch("core.tmdb.search", return_value=[{"id": 1, "media_type": "movie"}]) as sr:
            meta = tmdb.details_for_path("/a/b/Movie (2000).mkv", {"id": 7, "media_type": "tv"})
        self.assertEqual(meta, {"title": "X"})
        gd.assert_called_once_with(7, "tv")
        sr.assert_not_called()

    def test_auto_searches_by_filename(self):
        with patch("core.tmdb.get_details",
                   side_effect=lambda i, t: {"id": i, "type": t}) as gd, \
                patch("core.tmdb.search",
                      return_value=[{"id": 42, "media_type": "movie"}]) as sr:
            meta = tmdb.details_for_path("/a/b/The Matrix (1999).mkv")
        sr.assert_called_once()
        self.assertIn("matrix", sr.call_args[0][0].lower())
        gd.assert_called_once_with(42, "movie")
        self.assertEqual(meta, {"id": 42, "type": "movie"})

    def test_no_match_raises(self):
        with patch("core.tmdb.search", return_value=[]):
            with self.assertRaises(tmdb.TMDBError):
                tmdb.details_for_path("/a/b/Unknown (1999).mkv")


class TestMetadataOnly(unittest.TestCase):
    @unittest.skipUnless(_have("ffmpeg") and _have("mkvpropedit"), "ffmpeg/mkvtoolnix required")
    def test_write_metadata_without_poster(self):
        d = Path(tempfile.mkdtemp(prefix="mak-metadata-only-"))
        try:
            v = d / "movie.mkv"
            _make_video(v)
            meta = {"title": "Test Movie", "year": 2001, "overview": "desc",
                    "genres": ["Drama"], "rating": 7.5, "directors": ["A"], "cast": []}
            attacher.write_metadata(str(v), meta)
            out = subprocess.run(["mkvinfo", str(v)], capture_output=True).stdout.decode()
            self.assertIn("Test Movie", out)
            self.assertIsNone(attacher._find_attached_pic(str(v)))
        finally:
            shutil.rmtree(d, ignore_errors=True)


class TestPosterTuiFileSelection(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="mak-tui-sel-"))
        cls.v1 = str(cls.tmp / "One (2001).mkv")
        cls.v2 = str(cls.tmp / "Two (2002).mkv")
        _make_video(Path(cls.v1))
        _make_video(Path(cls.v2))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_selection_semantics(self):
        try:
            import asyncio
            import types

            import poster_tui.app as tui_app
        except ImportError:
            self.skipTest("textual not installed")

        async def run():
            app = tui_app.PosterTuiApp()
            with patch.object(tui_app.tmdb, "search", return_value=[]):
                async with app.run_test() as pilot:
                    app._add_video_path(self.v1)
                    app._add_video_path(self.v2)
                    await asyncio.sleep(0.1)
                    self.assertEqual(app._targets(), [self.v1, self.v2])

                    async def wait_targets(expected):
                        for _ in range(100):
                            if app._targets() == expected:
                                return
                            await asyncio.sleep(0.02)
                        self.assertEqual(app._targets(), expected)

                    app.query_one("#file_list").index = 0
                    app.action_toggle_file_selection()
                    self.assertEqual(app._targets(), [self.v1])
                    app.action_toggle_file_selection()
                    self.assertEqual(app._targets(), [self.v1, self.v2])

                    app.on_file_selected(
                        types.SimpleNamespace(list_view=types.SimpleNamespace(index=1))
                    )
                    self.assertEqual(app._targets(), [self.v2])
                    app.action_clear_selection()
                    self.assertEqual(app._targets(), [self.v1, self.v2])

                    app.query_one("#file_cb_0").value = True
                    await wait_targets([self.v1])
                    app.query_one("#file_cb_0").value = False
                    await wait_targets([self.v1, self.v2])

        asyncio.run(run())

    def test_keyboard_space_multi_select_from_unfocused_list(self):
        try:
            import asyncio

            import poster_tui.app as tui_app
        except ImportError:
            self.skipTest("textual not installed")

        async def run():
            app = tui_app.PosterTuiApp()
            with patch.object(tui_app.tmdb, "search", return_value=[]):
                async with app.run_test(size=(120, 40)) as pilot:
                    app._add_video_path(self.v1)
                    app._add_video_path(self.v2)
                    await asyncio.sleep(0.1)
                    await pilot.press("ctrl+r")
                    await asyncio.sleep(0.1)
                    lv = app.query_one("#file_list")
                    self.assertIsNone(lv.index)
                    await pilot.press("space")
                    await asyncio.sleep(0.1)
                    self.assertEqual(app._targets(), [self.v1])
                    self.assertEqual(lv.index, 0)
                    await pilot.press("down")
                    await asyncio.sleep(0.1)
                    await pilot.press("space")
                    await asyncio.sleep(0.1)
                    self.assertEqual(app._targets(), [self.v1, self.v2])
                    self.assertEqual(lv.index, 1)
                    await pilot.press("space")
                    await asyncio.sleep(0.1)
                    self.assertEqual(app._targets(), [self.v1])

        asyncio.run(run())

    def test_mouse_click_multi_select(self):
        try:
            import asyncio

            import poster_tui.app as tui_app
        except ImportError:
            self.skipTest("textual not installed")

        async def run():
            app = tui_app.PosterTuiApp()
            with patch.object(tui_app.tmdb, "search", return_value=[]):
                async with app.run_test(size=(120, 40)) as pilot:
                    app._add_video_path(self.v1)
                    app._add_video_path(self.v2)
                    await asyncio.sleep(0.1)
                    await pilot.press("ctrl+r")
                    await asyncio.sleep(0.1)
                    cb0 = app.query_one("#file_cb_0")
                    cb1 = app.query_one("#file_cb_1")
                    await pilot.click(cb0)
                    await asyncio.sleep(0.1)
                    self.assertEqual(app._targets(), [self.v1])
                    await pilot.click(cb1)
                    await asyncio.sleep(0.1)
                    self.assertEqual(app._targets(), [self.v1, self.v2])
                    self.assertIsNone(app.query_one("#file_list").index)
                    await pilot.click(cb0)
                    await asyncio.sleep(0.1)
                    self.assertEqual(app._targets(), [self.v2])

        asyncio.run(run())

    def test_empty_list_status_message(self):
        try:
            import asyncio

            import poster_tui.app as tui_app
        except ImportError:
            self.skipTest("textual not installed")

        async def run():
            app = tui_app.PosterTuiApp()
            with patch.object(tui_app.tmdb, "search", return_value=[]):
                async with app.run_test() as pilot:
                    app._update_selection_status()
                    await asyncio.sleep(0.1)
                    self.assertEqual(
                        str(app.query_one("#status").content), "No video files loaded"
                    )

        asyncio.run(run())

    @unittest.skipUnless(_have("ffmpeg") and _have("mkvpropedit"), "ffmpeg/mkvtoolnix required")
    def test_scrape_metadata_only_flow(self):
        try:
            import asyncio

            import poster_tui.app as tui_app
        except ImportError:
            self.skipTest("textual not installed")

        meta = {"title": "Scraped Title", "year": 2005, "overview": "o",
                "genres": ["Drama"], "rating": 8.0, "directors": ["D"], "cast": []}

        async def run():
            app = tui_app.PosterTuiApp()
            with patch.object(tui_app.tmdb, "search", return_value=[]), \
                    patch.object(tui_app.tmdb, "details_for_path", return_value=meta):
                async with app.run_test():
                    app._add_video_path(self.v1)
                    app._add_video_path(self.v2)
                    await asyncio.sleep(0.1)
                    app.on_scrape_metadata()
                    for _ in range(100):
                        if str(app.query_one("#status").content).startswith("Metadata written to 2"):
                            break
                        await asyncio.sleep(0.05)
                    status = str(app.query_one("#status").content)
                    self.assertTrue(status.startswith("Metadata written to 2"), status)
                    out = subprocess.run(["mkvinfo", self.v1], capture_output=True).stdout.decode()
                    self.assertIn("Scraped Title", out)
                    self.assertIsNone(attacher._find_attached_pic(self.v1))

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main(verbosity=2)
