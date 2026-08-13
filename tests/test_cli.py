import os
import tempfile
import unittest
from unittest import mock

import cli
from core import parser as core_parser


def _run(argv):
    try:
        cli.main(argv)
    except SystemExit as e:
        return e.code
    return 0


class VersionAndUsageTest(unittest.TestCase):
    def test_version_flag(self):
        self.assertEqual(_run(["--version"]), 0)

    def test_missing_command_is_usage_error(self):
        self.assertEqual(_run([]), 2)

    def test_attach_requires_file(self):
        self.assertEqual(_run(["attach"]), 2)

    def test_search_and_poster_are_mutually_exclusive(self):
        code = _run(["attach", "-f", "m.mkv", "-s", "x", "-p", "p.jpg"])
        self.assertEqual(code, 2)


class AttachTest(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch("cli.config")
        self.config = patcher.start()
        self.config.get.return_value = "test-key"
        self.addCleanup(patcher.stop)
        tools = mock.patch("cli.attacher.check_tools", return_value=[])
        tools.start()
        self.addCleanup(tools.stop)

    @mock.patch("cli.attacher.full_attach")
    def test_local_poster_attaches_directly(self, full_attach):
        full_attach.return_value = "movie.mkv"
        code = _run(["attach", "-f", "movie.mkv", "-p", "poster.jpg"])
        self.assertEqual(code, 0)
        full_attach.assert_called_once_with(
            "movie.mkv", "poster.jpg", metadata=None, to_mkv=False
        )

    @mock.patch("cli.attacher.full_attach")
    @mock.patch("cli.tmdb.download_image")
    @mock.patch("cli.tmdb.get_posters")
    @mock.patch("cli.tmdb.search")
    def test_search_downloads_and_cleans_temp_poster(self, search, get_posters,
                                                     download_image, full_attach):
        search.return_value = [
            {"id": 1, "title": "The Matrix", "year": "1999", "media_type": "movie"},
        ]
        get_posters.return_value = [
            {"url": "https://img/x.jpg", "thumb_url": "https://img/w500/x.jpg"},
        ]
        full_attach.return_value = "movie.mkv"
        seen_dest = []
        download_image.side_effect = lambda url, dest: seen_dest.append(dest)

        code = _run(["attach", "-f", "movie.mkv", "-s", "The Matrix"])
        self.assertEqual(code, 0)
        search.assert_called_once_with("The Matrix", "multi")
        self.assertEqual(len(seen_dest), 1)
        poster_dest = seen_dest[0]
        full_attach.assert_called_once_with(
            "movie.mkv", poster_dest, metadata=None, to_mkv=False
        )
        self.assertFalse(os.path.exists(poster_dest))

    @mock.patch("cli.attacher.full_attach")
    @mock.patch("cli.tmdb.download_image")
    @mock.patch("cli.tmdb.get_details")
    @mock.patch("cli.tmdb.get_posters")
    @mock.patch("cli.tmdb.search")
    def test_embed_metadata_scrapes_details(self, search, get_posters, get_details,
                                            download_image, full_attach):
        search.return_value = [
            {"id": 7, "title": "Boom", "year": "2020", "media_type": "movie"},
        ]
        get_posters.return_value = [{"url": "https://img/x.jpg"}]
        get_details.return_value = {"title": "Boom"}
        full_attach.return_value = "movie.mkv"

        code = _run(["attach", "-f", "movie.mkv", "-s", "Boom", "--embed-metadata"])
        self.assertEqual(code, 0)
        get_details.assert_called_once_with(7, "movie")
        full_attach.assert_called_once_with(
            "movie.mkv", download_image.call_args[0][1],
            metadata={"title": "Boom"}, to_mkv=False,
        )

    @mock.patch("cli.attacher.full_attach")
    @mock.patch("cli.tmdb.download_image")
    @mock.patch("cli.tmdb.get_posters")
    @mock.patch("cli.tmdb.search")
    def test_filename_derived_query_when_no_source(self, search, get_posters,
                                                   download_image, full_attach):
        with mock.patch.object(core_parser, "parse_filename",
                               return_value={"title": "Blade", "year": "1998",
                                             "season": None, "episode": None,
                                             "type": "movie"}), \
                mock.patch.object(core_parser, "build_search_query",
                                  return_value="Blade (1998)"):
            search.return_value = [
                {"id": 3, "title": "Blade", "year": "1998", "media_type": "movie"},
            ]
            get_posters.return_value = [{"url": "https://img/x.jpg"}]
            full_attach.return_value = "movie.mkv"
            code = _run(["attach", "-f", "movie.mkv"])
        self.assertEqual(code, 0)
        search.assert_called_once_with("Blade (1998)", "multi")

    @mock.patch("cli.tmdb.search", return_value=[])
    def test_no_match_exits_nonzero(self, search):
        code = _run(["attach", "-f", "movie.mkv", "-s", "Nope"])
        self.assertEqual(code, 1)

    @mock.patch("cli.tmdb.search")
    @mock.patch("cli.tmdb.get_posters", return_value=[])
    def test_no_posters_exits_nonzero(self, get_posters, search):
        search.return_value = [
            {"id": 1, "title": "Boom", "year": "", "media_type": "movie"},
        ]
        self.assertEqual(_run(["attach", "-f", "m.mkv", "-s", "Boom"]), 1)

    def test_missing_api_key_fails_before_work(self):
        self.config.get.return_value = ""
        with mock.patch("cli.attacher.check_tools") as check_tools:
            code = _run(["attach", "-f", "m.mkv", "-p", "p.jpg"])
        self.assertEqual(code, 1)
        check_tools.assert_not_called()

    @mock.patch("cli.attacher.check_tools", return_value=["ffmpeg"])
    def test_missing_tools_fails(self, check_tools):
        code = _run(["attach", "-f", "m.mkv", "-p", "p.jpg"])
        self.assertEqual(code, 1)
        check_tools.assert_called_once()


class RemoveTest(unittest.TestCase):
    def setUp(self):
        tools = mock.patch("cli.attacher.check_tools", return_value=[])
        tools.start()
        self.addCleanup(tools.stop)

    @mock.patch("cli.attacher.remove_poster")
    def test_default_removes_poster(self, remove_poster):
        self.assertEqual(_run(["remove", "-f", "movie.mkv"]), 0)
        remove_poster.assert_called_once_with("movie.mkv")

    @mock.patch("cli.attacher.remove_poster")
    @mock.patch("cli.attacher.remove_metadata")
    def test_metadata_only(self, remove_metadata, remove_poster):
        code = _run(["remove", "-f", "movie.mkv", "--metadata-only"])
        self.assertEqual(code, 0)
        remove_metadata.assert_called_once_with("movie.mkv")
        remove_poster.assert_not_called()

    def test_both_flags_is_error(self):
        code = _run(["remove", "-f", "m.mkv", "--poster-only", "--metadata-only"])
        self.assertEqual(code, 1)


class ScanTest(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch("cli.config")
        self.config = patcher.start()
        self.config.get.return_value = "test-key"
        self.addCleanup(patcher.stop)
        tools = mock.patch("cli.attacher.check_tools", return_value=[])
        tools.start()
        self.addCleanup(tools.stop)
        self._tmpdirs = []

    def tearDown(self):
        for d in self._tmpdirs:
            try:
                os.rmdir(d)
            except OSError:
                pass

    def _scan_dir(self):
        d = tempfile.mkdtemp(prefix="mak-cli-test-")
        self._tmpdirs.append(d)
        return d

    @mock.patch("cli.autoattach.attach_groups")
    @mock.patch("cli.autoattach.resolve_groups")
    @mock.patch("cli.scanner.classify")
    @mock.patch("cli.scanner.iter_video_files")
    def test_scan_resolves_and_attaches(self, iter_files, classify, resolve,
                                        attach):
        iter_files.return_value = ["/v/a.mkv"]
        classify.return_value = ["group-a"]
        resolve.return_value = [{"group": "group-a", "status": "ok",
                                 "match": {"id": 1}, "error": ""}]
        attach.return_value = {"ok": 1, "fail": 0, "skipped": 0, "errors": []}

        code = _run(["scan", self._scan_dir(), "--skip-existing", "--embed-metadata"])
        self.assertEqual(code, 0)
        classify.assert_called_once_with(["/v/a.mkv"])
        resolve.assert_called_once()
        attach.assert_called_once()
        kwargs = attach.call_args[1]
        self.assertTrue(kwargs["skip_existing"])
        self.assertTrue(kwargs["scrape_metadata"])

    @mock.patch("cli.autoattach.resolve_groups")
    @mock.patch("cli.scanner.classify")
    @mock.patch("cli.scanner.iter_video_files")
    def test_scan_with_no_matches_exits_nonzero(self, iter_files, classify,
                                                resolve):
        iter_files.return_value = ["/v/a.mkv"]
        classify.return_value = ["group-a"]
        resolve.return_value = [{"group": "group-a", "status": "no-match",
                                 "match": None, "error": ""}]
        self.assertEqual(_run(["scan", self._scan_dir()]), 1)

    @mock.patch("cli.scanner.iter_video_files", return_value=[])
    def test_scan_with_no_videos_is_not_an_error(self, iter_files):
        self.assertEqual(_run(["scan", self._scan_dir()]), 0)

    def test_scan_nonexistent_directory(self):
        self.assertEqual(_run(["scan", "/no/such/dir"]), 1)


if __name__ == "__main__":
    unittest.main()
