"""Regression tests for the v1.3.5 audit fixes (data safety + key redaction)."""
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import requests

from mak_attatch.core import attacher, tmdb


def _have(cmd: str) -> bool:
    return shutil.which(cmd) is not None


requires_media_tools = unittest.skipUnless(
    _have("ffmpeg") and _have("ffprobe") and _have("mkvpropedit") and _have("mkvmerge"),
    "ffmpeg/mkvtoolnix required",
)

CHAPTERS = """;FFMETADATA1
[CHAPTER]
TIMEBASE=1/1000
START=0
END=1000
title=Opening
[CHAPTER]
TIMEBASE=1/1000
START=1000
END=2000
title=Ending
"""


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _probe(path: Path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json",
         "-show_streams", "-show_chapters", "-show_format", str(path)],
        capture_output=True, check=True,
    ).stdout
    return json.loads(out)


def _tags(d: dict) -> dict:
    return {k.lower(): v for k, v in (d.get("tags") or {}).items()}


def _make_image(path: Path):
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=blue:s=100x150",
         "-frames:v", "1", str(path)],
        check=True, capture_output=True,
    )


def _make_rich(path: Path, title: str = "Pilot"):
    """2 s video + Japanese audio + two named chapters, like a real episode."""
    meta = path.with_suffix(".ffmeta")
    meta.write_text(CHAPTERS)
    ext = path.suffix.lower()
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "testsrc=duration=2:size=160x120:rate=10",
        "-f", "lavfi", "-i", "sine=duration=2",
        "-i", str(meta),
        "-map", "0", "-map", "1", "-map_metadata", "2", "-map_chapters", "2",
        "-c:v", "mpeg4", "-c:a", "aac",
        "-metadata:s:a:0", "language=jpn",
        "-metadata", f"title={title}",
    ]
    if ext == ".mkv":
        cmd += ["-f", "matroska"]
    elif ext == ".m4v":
        cmd += ["-f", "mp4", "-brand", "M4V "]
    elif ext == ".mov":
        cmd += ["-f", "mov"]
    else:
        cmd += ["-f", "mp4"]
    subprocess.run(cmd + [str(path)], check=True, capture_output=True)
    meta.unlink()


def _movie_meta() -> dict:
    return {"title": "Test Movie", "year": "2024", "overview": "Movie overview.",
            "genres": ["Drama"], "media_type": "movie", "directors": ["Alice"]}


def _tv_meta() -> dict:
    return {"title": "Breaking Bad", "year": "2008", "overview": "Series overview.",
            "genres": ["Drama", "Crime"], "media_type": "tv", "creators": ["Vince"]}


@requires_media_tools
class StreamMetadataPreservationTest(unittest.TestCase):
    """HIGH-1: MP4/MOV metadata writes must not wipe stream/chapter metadata."""

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="mak-audit-"))

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _assert_streams_and_chapters_intact(self, path: Path):
        info = _probe(path)
        audio = [s for s in info["streams"] if s.get("codec_type") == "audio"]
        self.assertEqual(_tags(audio[0]).get("language"), "jpn")
        titles = [_tags(c).get("title") for c in info.get("chapters", [])]
        self.assertEqual(titles, ["Opening", "Ending"])

    def test_write_metadata_keeps_languages_and_chapters(self):
        for ext in (".mp4", ".mov", ".m4v"):
            with self.subTest(ext=ext):
                v = self.dir / f"movie{ext}"
                _make_rich(v)
                attacher.write_metadata(str(v), _movie_meta())
                self._assert_streams_and_chapters_intact(v)
                self.assertEqual(_tags(_probe(v)["format"]).get("title"), "Test Movie")

    def test_remove_metadata_keeps_languages_and_chapters(self):
        for ext in (".mp4", ".mov"):
            with self.subTest(ext=ext):
                v = self.dir / f"movie{ext}"
                _make_rich(v)
                attacher.remove_metadata(str(v))
                self._assert_streams_and_chapters_intact(v)
                self.assertNotIn("title", _tags(_probe(v)["format"]))

    def test_mov_metadata_write_keeps_cover(self):
        # MEDIUM-4: the MOV muxer used to drop attached_pic on metadata writes.
        img = self.dir / "p.jpg"
        _make_image(img)
        v = self.dir / "clip.mov"
        _make_rich(v)
        attacher.full_attach(str(v), str(img))
        attacher.write_metadata(str(v), _movie_meta())
        self.assertIsNotNone(attacher._find_attached_pic(str(v)))

    def test_no_temp_files_left_behind(self):
        img = self.dir / "p.jpg"
        _make_image(img)
        v = self.dir / "movie.mp4"
        _make_rich(v)
        before = sorted(os.listdir(self.dir))
        attacher.full_attach(str(v), str(img), metadata=_movie_meta())
        attacher.remove_poster(str(v))
        attacher.remove_metadata(str(v))
        self.assertEqual(sorted(os.listdir(self.dir)), before)


@requires_media_tools
class SeriesMetadataTest(unittest.TestCase):
    """HIGH-3: show-level TMDB data must not overwrite each episode's title."""

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="mak-audit-"))

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_mkv_episode_title_survives(self):
        v = self.dir / "Show S01E01.mkv"
        _make_rich(v, title="Pilot")
        attacher.write_metadata(str(v), _tv_meta())
        info = json.loads(subprocess.run(["mkvmerge", "-J", str(v)],
                                         capture_output=True, check=True).stdout)
        self.assertEqual(info["container"]["properties"].get("title"), "Pilot")

    def test_mp4_episode_title_survives_and_show_is_set(self):
        v = self.dir / "Show S01E01.mp4"
        _make_rich(v, title="Pilot")
        attacher.write_metadata(str(v), _tv_meta())
        fmt = _tags(_probe(v)["format"])
        self.assertEqual(fmt.get("title"), "Pilot")
        self.assertEqual(fmt.get("show"), "Breaking Bad")


class SeriesTagLevelTest(unittest.TestCase):
    def test_tv_tags_target_collection_level(self):
        self.assertIn("<TargetTypeValue>70</TargetTypeValue>",
                      attacher.build_mkv_tags_xml(_tv_meta()))
        self.assertIn("<TargetTypeValue>50</TargetTypeValue>",
                      attacher.build_mkv_tags_xml(_movie_meta()))

    def test_tv_mp4_flags_do_not_set_title(self):
        flags = attacher._mp4_metadata_flags(_tv_meta())
        self.assertIn("show=Breaking Bad", flags)
        self.assertFalse(any(f.startswith(("title=", "date=", "description="))
                             for f in flags))


@requires_media_tools
class RewriteSafetyTest(unittest.TestCase):
    """MEDIUM-5/8/10: verification, .m4v handling, no rewrite before skip."""

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="mak-audit-"))
        self.img = self.dir / "p.jpg"
        _make_image(self.img)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_failed_verification_keeps_original_byte_identical(self):
        v = self.dir / "movie.mp4"
        _make_rich(v)
        digest = _sha(v)
        before = sorted(os.listdir(self.dir))
        with patch("mak_attatch.core.attacher._verify_rewrite",
                   side_effect=RuntimeError("Rewrite verification failed")):
            with self.assertRaises(RuntimeError):
                attacher.attach_poster_mp4(str(v), str(self.img))
        self.assertEqual(_sha(v), digest)
        self.assertEqual(sorted(os.listdir(self.dir)), before)

    def test_truncated_output_is_rejected(self):
        v = self.dir / "movie.mp4"
        _make_rich(v)
        with patch("mak_attatch.core.attacher._probe_duration", side_effect=[10.0, 2.0]):
            with self.assertRaises(RuntimeError):
                attacher._verify_rewrite(str(v), str(v), len(attacher._probe_streams(str(v))))

    def test_m4v_is_tagged_in_place(self):
        v = self.dir / "episode.m4v"
        _make_rich(v)
        out = attacher.full_attach(str(v), str(self.img))
        self.assertEqual(out, str(v))
        self.assertFalse(v.with_suffix(".mkv").exists())
        self.assertIsNotNone(attacher._find_attached_pic(str(v)))
        self.assertEqual(attacher._probe_major_brand(str(v)), "M4V ")

    def test_hardlinked_mkv_other_link_is_untouched(self):
        # MEDIUM-2: torrent client + media manager setups hardlink the same
        # file; editing it in place would change the seeding copy too.
        v = self.dir / "library.mkv"
        _make_rich(v)
        seed = self.dir / "seeding.mkv"
        os.link(v, seed)
        digest = _sha(seed)
        attacher.full_attach(str(v), str(self.img), metadata=_movie_meta())
        self.assertEqual(_sha(seed), digest)
        self.assertEqual(os.stat(seed).st_nlink, 1)
        self.assertEqual(attacher._cover_attachment_names(str(v)), ["cover.jpg"])
        self.assertEqual(attacher._cover_attachment_names(str(seed)), [])

    def test_to_mkv_skips_without_rewriting_when_mkv_exists(self):
        v = self.dir / "movie.mp4"
        _make_rich(v)
        _make_rich(v.with_suffix(".mkv"))
        digest = _sha(v)
        with self.assertRaises(RuntimeError):
            attacher.full_attach(str(v), str(self.img), to_mkv=True)
        self.assertEqual(_sha(v), digest)


class MkvpropeditExitCodeTest(unittest.TestCase):
    """MEDIUM-6: exit 1 = warnings with changes written; errors keep their text."""

    def _result(self, code, out=b""):
        r = MagicMock()
        r.returncode, r.stdout, r.stderr = code, out, b""
        return r

    def test_warning_exit_is_success(self):
        with patch("mak_attatch.core.attacher.subprocess.run",
                   return_value=self._result(1, b"Warning: x")):
            attacher._run_mkvpropedit(["mkvpropedit", "/x.mkv"])

    def test_error_exit_reports_mkvpropedit_message(self):
        with patch("mak_attatch.core.attacher.subprocess.run",
                   return_value=self._result(2, b"Error: The file is read-only")):
            with self.assertRaises(RuntimeError) as ctx:
                attacher._run_mkvpropedit(["mkvpropedit", "/x.mkv"])
        self.assertIn("read-only", str(ctx.exception))

    def test_rewrite_timeout_scales_with_size(self):
        self.assertEqual(attacher._rewrite_timeout(1024), 300)
        self.assertGreater(attacher._rewrite_timeout(20 * 1024 ** 3), 3000)


class ApiKeyRedactionTest(unittest.TestCase):
    """HIGH-2: errors must never contain the v3 api_key."""

    KEY = "SECRETv3key1234567890"

    def _session(self, side_effect):
        s = MagicMock()
        s.get.side_effect = side_effect
        return s

    def _resp(self, status, url="https://api.themoviedb.org/3/search/multi", headers=None):
        r = MagicMock()
        r.status_code = status
        r.url = url
        r.headers = headers or {}
        return r

    def _fetch(self, session):
        with patch("mak_attatch.core.tmdb._get_session", return_value=session), \
             patch("mak_attatch.core.tmdb.config.get", return_value=self.KEY), \
             patch("mak_attatch.core.tmdb.time.sleep"):
            return tmdb._fetch("https://api.themoviedb.org/3/search/multi",
                               params={"query": "x"})

    def test_connection_error_hides_key(self):
        err = requests.ConnectionError(
            f"Max retries exceeded with url: /3/search/multi?query=x&api_key={self.KEY}")
        with self.assertRaises(tmdb.TMDBError) as ctx:
            self._fetch(self._session(err))
        self.assertNotIn(self.KEY, str(ctx.exception))
        self.assertIsNone(ctx.exception.__cause__)
        self.assertTrue(ctx.exception.__suppress_context__)

    def test_http_error_hides_url_and_keeps_status(self):
        with self.assertRaises(tmdb.TMDBError) as ctx:
            self._fetch(self._session([self._resp(401)]))
        self.assertEqual(ctx.exception.status, 401)
        self.assertNotIn("api_key", str(ctx.exception))
        self.assertIn("401", str(ctx.exception))

    def test_rate_limit_is_retried(self):
        ok = self._resp(200)
        session = self._session([self._resp(429, headers={"Retry-After": "0"}), ok])
        self.assertIs(self._fetch(session), ok)
        self.assertEqual(session.get.call_count, 2)

    def test_same_host_redirect_keeps_v3_key(self):
        redirect = self._resp(302, headers={"Location": "/3/search/multi?page=1"})
        session = self._session([redirect, self._resp(200)])
        self._fetch(session)
        self.assertEqual(session.get.call_args_list[1].kwargs["params"].get("api_key"),
                         self.KEY)

    def test_redact_helper(self):
        self.assertEqual(tmdb.redact("for url: /3/x?query=a&api_key=abc123&page=2"),
                         "for url: /3/x?query=a&api_key=[REDACTED]&page=2")


class TuiSafetyTest(unittest.TestCase):
    """C1/H2/H4/M3: TUI must not delete user files or run unconfirmed batches."""

    def setUp(self):
        try:
            import mak_attatch.poster_tui.app as tui_app
        except ImportError:
            self.skipTest("textual not installed")
        self.tui = tui_app
        self.dir = Path(tempfile.mkdtemp(prefix="mak-audit-tui-"))
        self.files = []
        for name in ("a.mkv", "b.mkv"):
            f = self.dir / name
            f.write_bytes(b"\x1aE\xdf\xa3 not really a video")
            self.files.append(str(f))

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _run(self, body):
        import asyncio

        async def run():
            app = self.tui.PosterTuiApp()
            with patch.object(self.tui.config, "get", return_value="k" * 32):
                async with app.run_test() as pilot:
                    for f in self.files:
                        app._add_video_path(f)
                    await pilot.pause()
                    await body(app, pilot)

        asyncio.run(run())

    def test_local_image_survives_preview(self):
        import contextlib
        img = self.dir / "my poster.jpg"
        img.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 16)

        async def body(app, pilot):
            with patch.object(app, "suspend", return_value=contextlib.nullcontext()), \
                 patch.object(app, "_yazi_pick", return_value=str(img)), \
                 patch.object(app, "_draw_preview"):
                app.on_local_image()
            self.assertTrue(img.exists(), "user's image was deleted")
            self.assertEqual(app.local_poster_path, str(img))

        self._run(body)

    def test_downloaded_preview_temp_is_still_cleaned_up(self):
        tmp = self.dir / "preview.jpg"
        tmp.write_bytes(b"\xff\xd8\xff")

        async def body(app, pilot):
            with patch.object(app, "_draw_preview"):
                app._preview_native(str(tmp))
            self.assertFalse(tmp.exists())

        self._run(body)

    def test_remove_on_all_files_asks_and_no_cancels(self):
        async def body(app, pilot):
            with patch.object(self.tui.attacher, "remove_poster") as remove:
                app.on_remove()
                await pilot.pause()
                self.assertIsInstance(app.screen, self.tui.ConfirmScreen)
                await pilot.press("n")
                await pilot.pause()
                remove.assert_not_called()
                self.assertFalse(app._busy)

        self._run(body)

    def test_second_job_is_refused_while_busy(self):
        async def body(app, pilot):
            app._busy = True
            with patch.object(self.tui.attacher, "remove_poster") as remove:
                app.on_remove()
                await pilot.pause()
                self.assertNotIsInstance(app.screen, self.tui.ConfirmScreen)
                remove.assert_not_called()
            self.assertIn("still running", str(app.query_one("#status").content))

        self._run(body)

    def test_batch_scrape_resolves_each_file_itself(self):
        async def body(app, pilot):
            app.current_media = {"id": 1, "media_type": "movie", "title": "Wrong For All"}
            with patch.object(self.tui.tmdb, "details_for_path", return_value={}) as det, \
                 patch.object(self.tui.attacher, "write_metadata"):
                app.on_scrape_metadata()
                await pilot.pause()
                await pilot.press("y")
                for _ in range(100):
                    if det.call_count == 2 and not app._busy:
                        break
                    await pilot.pause(0.05)
            self.assertEqual(det.call_count, 2)
            for call in det.call_args_list:
                self.assertIsNone(call.args[1])

        self._run(body)


class MatchingConfidenceTest(unittest.TestCase):
    """MEDIUM-1: never attach an unrelated title's poster in bulk."""

    RESULTS = [
        {"id": 1, "title": "Smile", "year": "2022", "media_type": "movie"},
        {"id": 2, "title": "The Matrix", "year": "1999", "media_type": "movie"},
        {"id": 3, "title": "The Matrix", "year": "2021", "media_type": "movie"},
    ]

    def test_unrelated_top_result_is_rejected(self):
        self.assertIsNone(tmdb.best_match(self.RESULTS[:1], "Birthday Party 2019", ""))

    def test_article_punctuation_and_year_are_handled(self):
        self.assertEqual(tmdb.best_match(self.RESULTS, "Matrix", "1999")["id"], 2)
        self.assertEqual(tmdb.best_match(self.RESULTS, "the matrix", "2021")["id"], 3)

    def test_original_title_counts(self):
        res = [{"id": 9, "title": "Spirited Away", "original_title": "Sen to Chihiro",
                "year": "2001"}]
        self.assertEqual(tmdb.best_match(res, "Sen to Chihiro", "")["id"], 9)

    def test_resolve_groups_flags_unrelated_match_for_review(self):
        from mak_attatch.core import autoattach
        from mak_attatch.core.scanner import MediaGroup
        group = MediaGroup(kind="movie", title="Birthday Party", year="", season=None,
                           files=["/v/Birthday Party.mp4"])
        with patch.object(autoattach.tmdb, "search", return_value=self.RESULTS[:1]), \
             patch.object(autoattach.time, "sleep"):
            entry = autoattach.resolve_groups([group])[0]
        self.assertEqual(entry["status"], "no-match")
        self.assertIn("Smile", entry["error"])

    def test_details_for_path_refuses_unrelated_result(self):
        with patch.object(tmdb, "search", return_value=self.RESULTS[:1]), \
             patch.object(tmdb, "get_details") as details:
            with self.assertRaises(tmdb.TMDBError):
                tmdb.details_for_path("/v/Birthday Party 2019.mp4")
        details.assert_not_called()

    def test_attach_groups_cancel_stops_remaining_groups(self):
        from mak_attatch.core import autoattach
        from mak_attatch.core.scanner import MediaGroup
        entries = [{"group": MediaGroup("movie", f"T{i}", "", None, [f"/v/{i}.mkv"]),
                    "match": {"id": i, "media_type": "movie"}, "status": "ok"}
                   for i in range(3)]
        with patch.object(autoattach.tmdb, "get_posters") as posters:
            autoattach.attach_groups(entries, cancel=lambda: True)
        posters.assert_not_called()


class ScanLayoutTest(unittest.TestCase):
    """Extras skipped; episode/folder naming fixes."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="mak-audit-scan-"))

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _touch(self, rel: str) -> str:
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"")
        return str(p)

    def test_extras_are_not_scanned(self):
        from mak_attatch.core import scanner
        keep = [self._touch("Movie (2019)/Movie (2019).mkv"),
                self._touch("The Interview.mkv")]
        for rel in ["Movie (2019)/Featurettes/Making of.mkv",
                    "Movie (2019)/Behind The Scenes/x.mkv",
                    "Movie (2019)/Movie-trailer.mkv",
                    "Release.2019.1080p/release.sample.mkv",
                    "Sample/sample.mkv"]:
            self._touch(rel)
        self.assertEqual(sorted(scanner.iter_video_files(str(self.root))), sorted(keep))

    def test_marker_first_episodes_group_under_show_folder(self):
        from mak_attatch.core import scanner
        files = [self._touch("Breaking Bad/Season 1/S01E01 - Pilot.mkv"),
                 self._touch("Breaking Bad/Season 1/S01E02 - Cat's in the Bag.mkv")]
        groups = scanner.classify(files)
        self.assertEqual(len(groups), 1)
        self.assertEqual((groups[0].title, groups[0].season), ("Breaking Bad", 1))

    def test_specials_folder_is_not_a_series_name(self):
        from mak_attatch.core import scanner
        series, _ = scanner._series_and_season_from_folders(
            str(self.root / "Doctor Who" / "Specials" / "E01.mkv"))
        self.assertEqual(series, "Doctor Who")

    def test_folder_names_keep_their_dots(self):
        from mak_attatch.core import parser
        info = parser.parse_filename("/lib/The.Matrix.1999")
        self.assertEqual((info["title"], info["year"]), ("The Matrix", "1999"))


class CliBatchTest(unittest.TestCase):
    """An unmatched file must not abort a CLI batch; scan skips postered files."""

    def setUp(self):
        from mak_attatch import cli
        self.cli = cli
        for target, value in (("mak_attatch.cli.attacher.check_tools", []),):
            p = patch(target, return_value=value)
            p.start()
            self.addCleanup(p.stop)
        p = patch("mak_attatch.cli.config")
        cfg = p.start()
        self.addCleanup(p.stop)
        cfg.get.side_effect = lambda k: {"tmdb_api_key": "k" * 32,
                                         "scan_api_delay": 0.0}.get(k)

    def _run(self, argv):
        try:
            self.cli.main(argv)
        except SystemExit as e:
            return e.code
        return 0

    def test_unmatched_file_does_not_abort_batch(self):
        def search(query, media_type):
            if "Unknown" in query:
                return []
            return [{"id": 1, "title": "The Matrix", "year": "1999", "media_type": "movie"}]

        with patch("mak_attatch.cli.tmdb.search", side_effect=search), \
             patch("mak_attatch.cli._download_first_poster", return_value="/tmp/p.jpg"), \
             patch("mak_attatch.cli.attacher.full_attach",
                   side_effect=lambda f, *a, **k: f) as att, \
             patch("mak_attatch.cli.os.unlink"):
            code = self._run(["attach", "-f", "/v/Unknown Thing.mkv",
                              "-f", "/v/The Matrix (1999).mkv"])
        self.assertEqual(code, 1)
        att.assert_called_once()
        self.assertEqual(att.call_args.args[0], "/v/The Matrix (1999).mkv")

    def test_scan_skips_existing_posters_by_default(self):
        d = tempfile.mkdtemp(prefix="mak-audit-cli-")
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        resolved = [{"group": MagicMock(title="X"), "status": "ok",
                     "match": {"id": 1}, "error": ""}]
        summary = {"ok": 1, "fail": 0, "skipped": 0, "errors": []}
        with patch("mak_attatch.cli.scanner.iter_video_files", return_value=["/v/a.mkv"]), \
             patch("mak_attatch.cli.scanner.classify", return_value=["g"]), \
             patch("mak_attatch.cli.autoattach.resolve_groups", return_value=resolved), \
             patch("mak_attatch.cli.autoattach.attach_groups", return_value=summary) as attach:
            self.assertEqual(self._run(["scan", d]), 0)
            self.assertTrue(attach.call_args.kwargs["skip_existing"])
            self.assertEqual(attach.call_args.kwargs["api_delay"], 0.0)
            self._run(["scan", d, "--no-skip-existing"])
            self.assertFalse(attach.call_args.kwargs["skip_existing"])


class ConfigRobustnessTest(unittest.TestCase):
    def setUp(self):
        from mak_attatch import config
        self.config = config
        self.dir = Path(tempfile.mkdtemp(prefix="mak-audit-cfg-"))
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        for name, value in (("CONFIG_DIR", self.dir), ("CONFIG_FILE", self.dir / "config.json")):
            p = patch.object(config, name, value)
            p.start()
            self.addCleanup(p.stop)

    def test_corrupt_config_is_kept_not_overwritten(self):
        self.config.CONFIG_FILE.write_text('{"tmdb_api_key": "precious-key-123", oops')
        self.config.set("convert_to_mkv", True)  # e.g. a GUI checkbox toggle
        backups = list(self.dir.glob("config.json.bad-*"))
        self.assertEqual(len(backups), 1)
        self.assertIn("precious-key-123", backups[0].read_text())

    def test_boolean_strings(self):
        self.config.CONFIG_FILE.write_text(json.dumps({"convert_to_mkv": "false",
                                                       "scan_skip_existing": "yes"}))
        self.assertFalse(self.config.get("convert_to_mkv"))
        self.assertTrue(self.config.get("scan_skip_existing"))


class TmdbRobustnessTest(unittest.TestCase):
    def test_poster_without_dimensions_and_nameless_crew(self):
        posters = MagicMock()
        posters.json.return_value = {"posters": [{"file_path": "/a.jpg"}, "junk"]}
        with patch.object(tmdb, "_fetch", return_value=posters), \
             patch.object(tmdb.config, "get", return_value="k" * 32):
            out = tmdb.get_posters(1, "movie")
        self.assertEqual((out[0]["width"], out[0]["height"]), (0, 0))

        details, credits = MagicMock(), MagicMock()
        details.json.return_value = {"title": "X"}
        credits.json.return_value = {"crew": [{"job": "Director"},
                                              {"job": "Director", "name": "A"}]}
        with patch.object(tmdb, "_fetch", side_effect=[details, credits]), \
             patch.object(tmdb.config, "get", return_value="k" * 32):
            self.assertEqual(tmdb.get_details(1, "movie")["directors"], ["A"])

    def test_rejected_download_leaves_no_partial_file(self):
        d = Path(tempfile.mkdtemp(prefix="mak-audit-dl-"))
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        dest = d / "p.jpg"
        resp = MagicMock()
        resp.headers = {"content-type": "image/jpeg", "content-length": "0"}
        resp.iter_content = lambda n: [b"\xff\xd8\xff" + b"x" * 10, b"y" * (60 * 1024 * 1024)]
        with patch.object(tmdb, "_fetch", return_value=resp), \
             patch.object(tmdb, "_validate_url"):
            with self.assertRaises(tmdb.TMDBError):
                tmdb.download_image("https://image.tmdb.org/t/p/x.jpg", str(dest))
        self.assertFalse(dest.exists())
        resp.close.assert_called()

    def test_trailing_number_retried_as_title(self):
        empty, found = MagicMock(), MagicMock()
        empty.json.return_value = {"results": []}
        found.json.return_value = {"results": [{"id": 7, "title": "Wonder Woman 1984",
                                                "media_type": "movie",
                                                "release_date": "2020-12-16"}]}
        with patch.object(tmdb, "_fetch", side_effect=[empty, found]) as fetch, \
             patch.object(tmdb.config, "get", return_value="k" * 32):
            res = tmdb.search("Wonder Woman 1984", "movie")
        self.assertEqual(res[0]["id"], 7)
        self.assertEqual(fetch.call_args.kwargs["params"], {"query": "Wonder Woman 1984"})


@requires_media_tools
class RewriteDetailsTest(unittest.TestCase):
    """Fast start, read-only, symlinks, control characters, cover detection."""

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="mak-audit-rw-"))
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.img = self.dir / "p.jpg"
        _make_image(self.img)

    def test_faststart_layout_is_kept(self):
        v = self.dir / "web.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                        "testsrc=duration=1:size=160x120:rate=10", "-c:v", "mpeg4",
                        "-movflags", "+faststart", str(v)], check=True)
        self.assertTrue(attacher._is_faststart(str(v)))
        attacher.full_attach(str(v), str(self.img), metadata=_movie_meta())
        self.assertTrue(attacher._is_faststart(str(v)))

    def test_read_only_file_is_refused(self):
        v = self.dir / "ro.mp4"
        _make_rich(v)
        digest = _sha(v)
        os.chmod(v, 0o444)
        self.addCleanup(os.chmod, v, 0o644)
        with self.assertRaises(RuntimeError):
            attacher.full_attach(str(v), str(self.img))
        self.assertEqual(_sha(v), digest)

    def test_remux_lands_next_to_symlink(self):
        store = self.dir / "store"
        lib = self.dir / "library"
        store.mkdir()
        lib.mkdir()
        target = store / "movie.avi"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                        "testsrc=duration=1:size=160x120:rate=10", "-c:v", "mpeg4",
                        str(target)], check=True)
        link = lib / "movie.avi"
        link.symlink_to(target)
        out = attacher.remux_to_mkv(str(link))
        self.assertEqual(Path(out).parent, lib)
        self.assertFalse((store / "movie.mkv").exists())

    def test_control_characters_are_dropped(self):
        meta = dict(_movie_meta(), title="Bad\x1bTitle\x00", overview="a\x0bb")
        v = self.dir / "m.mkv"
        _make_rich(v)
        attacher.write_metadata(str(v), meta)  # mkvpropedit must accept the tags
        mp4 = self.dir / "m.mp4"
        _make_rich(mp4)
        attacher.write_metadata(str(mp4), meta)  # NUL used to break ffmpeg's argv
        self.assertEqual(_tags(_probe(mp4)["format"]).get("title"), "BadTitle")

    def test_only_cover_attachments_count_as_poster(self):
        from mak_attatch.core import scanner
        v = self.dir / "fonts.mkv"
        _make_rich(v)
        subprocess.run(["mkvpropedit", str(v), "--attachment-name", "preview.jpg",
                        "--attachment-mime-type", "image/jpeg",
                        "--add-attachment", str(self.img)], check=True, capture_output=True)
        scanner.clear_poster_cache()
        self.assertFalse(scanner.has_poster(str(v)))
        attacher.attach_poster_mkv(str(v), str(self.img))
        scanner.clear_poster_cache()
        self.assertTrue(scanner.has_poster(str(v)))


class ParserAndAutoAttachDetailsTest(unittest.TestCase):
    def test_multi_episode_lists_do_not_crash(self):
        from mak_attatch.core import parser
        info = parser.parse_filename("/tv/Show S01E01E02.mkv")
        self.assertEqual((info["season"], info["episode"]), (1, 1))

    def test_attach_groups_reports_remuxed_paths(self):
        from mak_attatch.core import autoattach
        from mak_attatch.core.scanner import MediaGroup
        entry = {"group": MediaGroup("movie", "T", "", None, ["/v/a.mp4"]),
                 "match": {"id": 1, "media_type": "movie"}, "status": "ok"}
        with patch.object(autoattach.tmdb, "get_posters", return_value=[{"url": "u"}]), \
             patch.object(autoattach.tmdb, "download_image"), \
             patch.object(autoattach.scanner, "has_poster", return_value=False), \
             patch.object(autoattach.attacher, "full_attach", return_value="/v/a.mkv"), \
             patch.object(autoattach.time, "sleep"):
            summary = autoattach.attach_groups([entry], to_mkv=True)
        self.assertEqual(summary["converted"], {"/v/a.mp4": "/v/a.mkv"})


class TuiTextAndKeyTest(unittest.TestCase):
    """Names that look like markup must not vanish or crash the TUI."""

    def setUp(self):
        try:
            import mak_attatch.poster_tui.app as tui_app
        except ImportError:
            self.skipTest("textual not installed")
        self.tui = tui_app
        self.dir = Path(tempfile.mkdtemp(prefix="mak-audit-tui2-"))
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)

    def test_markup_like_names_are_shown_literally(self):
        import asyncio
        name = "[SubsPlease] Show - 01 [b].mkv"
        f = self.dir / name
        f.write_bytes(b"")

        async def run():
            app = self.tui.PosterTuiApp()
            with patch.object(self.tui.config, "get", return_value=""), \
                 patch.object(self.tui.config, "set"):
                async with app.run_test() as pilot:
                    app._add_video_path(str(f))
                    await pilot.pause()
                    label = str(app.query_one("#file_cb_0").label)
                    self.assertIn("[SubsPlease]", label)
                    group = MagicMock(title="[Group] Show [/x]", season=1, files=[str(f)])
                    app.push_screen(self.tui.ReviewScreen(
                        [{"group": group, "status": "ok", "match": None}]))
                    await pilot.pause()

        asyncio.run(run())

    def test_environment_key_is_not_saved(self):
        import asyncio

        async def run():
            app = self.tui.PosterTuiApp()
            with patch.dict(os.environ, {"MAK_ATTATCH_TMDB_API_KEY": "env-key-123456"}), \
                 patch.object(self.tui.config, "set") as cfg_set:
                async with app.run_test() as pilot:
                    app.push_screen(self.tui.SettingsScreen())
                    await pilot.pause()
                    screen = app.screen
                    screen.query_one("#api_key_input").value = "env-key-123456"
                    screen.on_save()
                    await pilot.pause()
            self.assertNotIn("tmdb_api_key", [c.args[0] for c in cfg_set.call_args_list])

        asyncio.run(run())


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QKeySequence, QShortcut
    from PyQt6.QtWidgets import QApplication, QListWidget

    from mak_attatch import config as app_config
    from mak_attatch.ui import main_window as mw
except ImportError:
    mw = None


@unittest.skipIf(mw is None, "PyQt6 not installed")
class GuiSafetyTest(unittest.TestCase):
    """H1/H2/H5/H6: GUI shortcuts, job guard, selection, crash handling."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _bare_window(self):
        w = mw.MainWindow.__new__(mw.MainWindow)
        w.status_label = MagicMock()
        return w

    def _config_get(self, key):
        return {"tmdb_api_key": "k" * 32}.get(key, app_config.DEFAULTS.get(key))

    def test_ctrl_a_does_not_attach(self):
        with patch.object(mw.config, "get", side_effect=self._config_get):
            w = mw.MainWindow()
        try:
            keys = {sc.key().toString() for sc in w.findChildren(QShortcut)}
            self.assertNotIn(QKeySequence("Ctrl+A").toString(), keys)
            self.assertIn(QKeySequence("Ctrl+Return").toString(), keys)
            # Registered once only (as toolbar actions), so they actually fire.
            self.assertNotIn(QKeySequence("Ctrl+O").toString(), keys)
            self.assertNotIn(QKeySequence("Ctrl+F").toString(), keys)
        finally:
            w.close()
            w.deleteLater()

    def test_second_job_refused_while_worker_runs(self):
        w = self._bare_window()
        w._job_workers = [MagicMock(isRunning=MagicMock(return_value=True))]
        self.assertFalse(w._begin_job())
        w._job_workers = [MagicMock(isRunning=MagicMock(return_value=False))]
        self.assertTrue(w._begin_job())

    def test_running_search_does_not_block_attach(self):
        w = self._bare_window()
        search = MagicMock(isRunning=MagicMock(return_value=True))
        w._track_worker(search)  # not a job
        self.assertTrue(w._begin_job())

    def test_cancelled_batch_stops_before_next_file(self):
        worker = mw.BatchWorker(["/v/a.mkv", "/v/b.mkv"], "/tmp/p.jpg")
        calls = []

        def attach(path, *a, **k):
            calls.append(path)
            worker.cancel()  # user pressed Cancel while the first file ran
            return path

        with patch.object(mw.attacher, "full_attach", side_effect=attach):
            worker.run()
        self.assertEqual(calls, ["/v/a.mkv"])
        self.assertEqual(len(worker.results), 1)

    def test_close_during_job_can_be_refused(self):
        w = self._bare_window()
        job = MagicMock(isRunning=MagicMock(return_value=True))
        w._job_workers = [job]
        w._active_workers = [job]
        event = MagicMock()
        with patch.object(mw.QMessageBox, "question",
                          return_value=mw.QMessageBox.StandardButton.No):
            w.closeEvent(event)
        event.ignore.assert_called_once()
        job.cancel.assert_not_called()
        job.wait.assert_not_called()

    def test_all_files_action_needs_explicit_yes(self):
        w = self._bare_window()
        w.selected_video_paths = set()
        with patch.object(mw.QMessageBox, "question",
                          return_value=mw.QMessageBox.StandardButton.No) as q:
            self.assertFalse(w._confirm_all_files("Attach to", ["a", "b", "c"]))
        q.assert_called_once()
        w.selected_video_paths = {"a"}
        with patch.object(mw.QMessageBox, "question") as q:
            self.assertTrue(w._confirm_all_files("Attach to", ["a"]))
        q.assert_not_called()

    def test_refresh_keeps_selection(self):
        w = self._bare_window()
        w.file_list = QListWidget()
        w.files_label = MagicMock()
        w.video_paths = ["/v/a.mkv", "/v/b.mkv", "/v/c.mkv"]
        w.selected_video_paths = set()
        # A plain callable: a bare (never __init__-ed) QObject cannot be a
        # signal receiver itself. The real clear() signal still fires.
        w.file_list.itemSelectionChanged.connect(
            lambda: mw.MainWindow._on_file_selection_changed(w)
        )
        with patch.object(mw.scanner, "has_poster", return_value=False):
            w._refresh_file_rows()
            w.file_list.item(1).setSelected(True)
            self.assertEqual(w.selected_video_paths, {"/v/b.mkv"})
            w._refresh_file_rows()  # e.g. a background auto-attach finished
        self.assertEqual(w.selected_video_paths, {"/v/b.mkv"})
        selected = [i.data(Qt.ItemDataRole.UserRole) for i in w.file_list.selectedItems()]
        self.assertEqual(selected, ["/v/b.mkv"])
        self.assertEqual(w._active_targets(), ["/v/b.mkv"])

    def test_invalid_api_key_does_not_crash(self):
        with patch.object(mw.config, "get", return_value=""):
            dlg = mw.ApiKeyDialog()
        dlg.key_input.setText("short")
        with patch.object(mw.config, "set", side_effect=ValueError("Invalid API key format")), \
             patch.object(mw.QMessageBox, "warning") as warn:
            dlg._save()
        warn.assert_called_once()
        self.assertNotEqual(dlg.result(), mw.QDialog.DialogCode.Accepted)

    def test_environment_key_is_not_written(self):
        env = {"MAK_ATTATCH_TMDB_API_KEY": "env-key-123456"}
        with patch.dict(os.environ, env), \
             patch.object(mw.config, "get", return_value="env-key-123456"):
            dlg = mw.ApiKeyDialog()
            dlg.key_input.setText("env-key-123456")
            with patch.object(mw.config, "set") as cfg_set:
                dlg._save()
        cfg_set.assert_not_called()
        self.assertEqual(dlg.result(), mw.QDialog.DialogCode.Accepted)

    def test_stale_poster_results_are_ignored(self):
        w = self._bare_window()
        w.poster_grid = MagicMock()

        class FakeWorker:
            def __init__(self, *args):
                self.finished, self.error = MagicMock(), MagicMock()

            def start(self):
                pass

            def isRunning(self):
                return False

        item = MagicMock()
        with patch.object(mw, "PosterWorker", FakeWorker):
            item.data.return_value = {"id": 1, "media_type": "movie", "title": "A"}
            w._on_result_selected(item)
            first = w._poster_worker
            item.data.return_value = {"id": 2, "media_type": "movie", "title": "B"}
            w._on_result_selected(item)
            second = w._poster_worker
        # [0]: the result handler (_track_worker connects its release hook after it).
        first.finished.connect.call_args_list[0].args[0](["A's posters"])  # arrives late
        w.poster_grid.load_posters.assert_not_called()
        second.finished.connect.call_args_list[0].args[0](["B's posters"])
        w.poster_grid.load_posters.assert_called_once_with(["B's posters"])

    def test_new_files_forget_previous_poster(self):
        w = self._bare_window()
        w.selected_poster, w.local_poster_path = {"url": "x"}, None
        w.current_media = {"id": 1, "media_type": "movie"}
        w.attach_btn, w.local_img_label, w.poster_grid = MagicMock(), MagicMock(), MagicMock()
        w.search_input = MagicMock()
        with patch.object(w, "_append_paths"), patch.object(w, "_search"), \
             patch.object(mw.config, "set"):
            w._load_videos(["/v/Other Show S01E01.mkv"])
        self.assertIsNone(w.selected_poster)
        self.assertIsNone(w.current_media)
        w.attach_btn.setEnabled.assert_called_with(False)

    def test_excepthook_reports_and_redacts(self):
        import sys

        from mak_attatch import main
        old = sys.excepthook
        try:
            main._install_excepthook()
            with patch.object(main.QMessageBox, "critical") as crit, \
                 patch("mak_attatch.main.traceback.print_exception"):
                sys.excepthook(ValueError, ValueError("url?api_key=SECRET1"), None)
            text = crit.call_args.args[2]
            self.assertNotIn("SECRET1", text)
            self.assertIn("[REDACTED]", text)
        finally:
            sys.excepthook = old


if __name__ == "__main__":
    unittest.main(verbosity=2)
