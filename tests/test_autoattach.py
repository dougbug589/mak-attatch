import unittest
from unittest import mock

from core import autoattach, scanner


def _group(kind, title, files, season=None, year=""):
    return scanner.MediaGroup(
        kind=kind, title=title, year=year, season=season,
        files=files, key=f"{kind}|{title}|{season or 0}",
    )


POSTER_URL = "https://image.tmdb.org/t/p/original/x.jpg"


class ResolveGroupsTest(unittest.TestCase):
    @mock.patch("core.autoattach.tmdb.search")
    def test_resolve_year_match_wins(self, search):
        groups = [_group("show", "Series", ["/x/Series S01E01.mkv"],
                         season=1, year="2022")]
        search.return_value = [
            {"id": 2, "title": "Series", "year": "2023", "media_type": "tv"},
            {"id": 1, "title": "Series", "year": "2022", "media_type": "tv"},
        ]
        resolved = autoattach.resolve_groups(groups, api_delay=0)
        self.assertEqual(resolved[0]["status"], "ok")
        self.assertEqual(resolved[0]["match"]["id"], 1)
        search.assert_called_once_with("Series (2022)", "tv")

    @mock.patch("core.autoattach.tmdb.search")
    def test_no_match(self, search):
        search.return_value = []
        groups = [_group("movie", "Nope", ["/x/nope.mkv"], year="1999")]
        resolved = autoattach.resolve_groups(groups, api_delay=0)
        self.assertEqual(resolved[0]["status"], "no-match")
        self.assertIsNone(resolved[0]["match"])

    @mock.patch("core.autoattach.tmdb.search", side_effect=RuntimeError("boom"))
    def test_search_error_is_recorded(self, search):
        groups = [_group("movie", "Boom", ["/x/b.mkv"])]
        resolved = autoattach.resolve_groups(groups, api_delay=0)
        self.assertEqual(resolved[0]["status"], "error")
        self.assertIn("boom", resolved[0]["error"])

    @mock.patch("core.autoattach.tmdb.search")
    def test_scoped_media_type(self, search):
        search.return_value = []
        autoattach.resolve_groups(
            [_group("show", "Show", ["/x/s.mkv"]),
             _group("movie", "Film", ["/x/f.mkv"])],
            api_delay=0,
        )
        calls = [c.args for c in search.call_args_list]
        self.assertIn(("Show", "tv"), calls)
        self.assertIn(("Film", "movie"), calls)

    @mock.patch("core.autoattach.tmdb.search")
    def test_progress_receives_index_total_group(self, search):
        search.return_value = []
        seen = []
        autoattach.resolve_groups(
            [_group("movie", "A", ["/x/a.mkv"]),
             _group("movie", "B", ["/x/b.mkv"])],
            api_delay=0,
            progress=lambda *args: seen.append(args),
        )
        self.assertEqual(len(seen), 2)
        self.assertEqual(seen[0], (1, 2, seen[0][2]))
        self.assertEqual(seen[1], (2, 2, seen[1][2]))


class AttachGroupsTest(unittest.TestCase):
    def _resolved(self, n_files=2):
        group = _group("show", "Series", [f"/x/ep{i}.mkv" for i in range(n_files)],
                       season=1, year="2022")
        return [{
            "group": group,
            "match": {"id": 7, "media_type": "tv",
                      "title": "Series", "year": "2022"},
            "status": "ok",
            "error": "",
        }]

    @mock.patch("core.autoattach.scanner.has_poster", return_value=False)
    @mock.patch("core.autoattach.attacher.full_attach")
    @mock.patch("core.autoattach.tmdb.download_image")
    @mock.patch("core.autoattach.tmdb.get_posters",
                return_value=[{"url": POSTER_URL}])
    def test_attach_ok(self, get_posters, download_image, full_attach, has_poster):
        summary = autoattach.attach_groups(self._resolved(2), api_delay=0)
        self.assertEqual(summary["ok"], 2)
        self.assertEqual(summary["fail"], 0)
        self.assertEqual(summary["skipped"], 0)
        self.assertEqual(full_attach.call_count, 2)
        self.assertEqual(download_image.call_count, 1)

    def test_skips_existing_posters(self):
        with mock.patch("core.autoattach.scanner.has_poster",
                        return_value=True), \
             mock.patch("core.autoattach.tmdb.get_posters",
                        return_value=[{"url": POSTER_URL}]), \
             mock.patch("core.autoattach.tmdb.download_image"), \
             mock.patch("core.autoattach.attacher.full_attach") as full:
            summary = autoattach.attach_groups(self._resolved(2), api_delay=0)
        self.assertEqual(summary["skipped"], 2)
        self.assertEqual(summary["ok"], 0)
        full.assert_not_called()

    def test_scrapes_metadata_once_per_group(self):
        with mock.patch("core.autoattach.scanner.has_poster",
                        return_value=False), \
             mock.patch("core.autoattach.tmdb.get_posters",
                        return_value=[{"url": POSTER_URL}]), \
             mock.patch("core.autoattach.tmdb.download_image"), \
             mock.patch("core.autoattach.tmdb.get_details",
                        return_value={"title": "Series"}) as details, \
             mock.patch("core.autoattach.attacher.full_attach") as full:
            summary = autoattach.attach_groups(
                self._resolved(2), scrape_metadata=True, api_delay=0)
        self.assertEqual(summary["ok"], 2)
        self.assertEqual(details.call_count, 1)
        for call in full.call_args_list:
            self.assertEqual(call.kwargs["metadata"], {"title": "Series"})

    def test_to_mkv_flag_passed_to_full_attach(self):
        with mock.patch("core.autoattach.scanner.has_poster",
                        return_value=False), \
             mock.patch("core.autoattach.tmdb.get_posters",
                        return_value=[{"url": POSTER_URL}]), \
             mock.patch("core.autoattach.tmdb.download_image"), \
             mock.patch("core.autoattach.attacher.full_attach") as full:
            summary = autoattach.attach_groups(self._resolved(1), api_delay=0,
                                               to_mkv=True)
        self.assertEqual(summary["ok"], 1)
        for call in full.call_args_list:
            self.assertTrue(call.kwargs["to_mkv"])

    def test_to_mkv_off_by_default(self):
        with mock.patch("core.autoattach.scanner.has_poster",
                        return_value=False), \
             mock.patch("core.autoattach.tmdb.get_posters",
                        return_value=[{"url": POSTER_URL}]), \
             mock.patch("core.autoattach.tmdb.download_image"), \
             mock.patch("core.autoattach.attacher.full_attach") as full:
            autoattach.attach_groups(self._resolved(1), api_delay=0)
        for call in full.call_args_list:
            self.assertFalse(call.kwargs.get("to_mkv", False))

    def test_counts_failures_per_file(self):
        def boom(*_a, **_k):
            raise RuntimeError("bad file")

        with mock.patch("core.autoattach.scanner.has_poster",
                        return_value=False), \
             mock.patch("core.autoattach.tmdb.get_posters",
                        return_value=[{"url": POSTER_URL}]), \
             mock.patch("core.autoattach.tmdb.download_image"), \
             mock.patch("core.autoattach.attacher.full_attach",
                        side_effect=boom) as full:
            summary = autoattach.attach_groups(self._resolved(2), api_delay=0)
        self.assertEqual(summary["ok"], 0)
        self.assertEqual(summary["fail"], 2)
        self.assertEqual(full.call_count, 2)

    def test_unmatched_groups_are_skipped(self):
        with mock.patch("core.autoattach.attacher.full_attach") as full:
            summary = autoattach.attach_groups(
                [{"group": _group("movie", "X", ["/x/a.mkv"]),
                  "match": None, "status": "no-match", "error": ""}],
                api_delay=0,
            )
        self.assertEqual(summary["ok"], 0)
        full.assert_not_called()

    def test_uses_custom_poster_from_entry(self):
        resolved = self._resolved(1)
        resolved[0]["poster"] = {"url": "file:///custom.jpg",
                                 "width": 100, "height": 100}
        with mock.patch("core.autoattach.scanner.has_poster",
                        return_value=False), \
             mock.patch("core.autoattach.tmdb.get_posters",
                        return_value=[{"url": "file:///default.jpg"}]), \
             mock.patch("core.autoattach.tmdb.download_image") as dl, \
             mock.patch("core.autoattach.attacher.full_attach"):
            autoattach.attach_groups(resolved, api_delay=0)
        self.assertEqual(dl.call_args.args[0], "file:///custom.jpg")

    def test_progress_receives_done_total_path_status(self):
        seen = []
        with mock.patch("core.autoattach.scanner.has_poster",
                        return_value=False), \
             mock.patch("core.autoattach.tmdb.get_posters",
                        return_value=[{"url": POSTER_URL}]), \
             mock.patch("core.autoattach.tmdb.download_image"), \
             mock.patch("core.autoattach.attacher.full_attach"):
            autoattach.attach_groups(
                self._resolved(2), api_delay=0,
                progress=lambda *args: seen.append(args),
            )
        self.assertEqual(len(seen), 2)
        for i, call in enumerate(seen):
            self.assertEqual(len(call), 4)
            self.assertEqual(call[0], i + 1)
            self.assertEqual(call[1], 2)
            self.assertEqual(call[3], "ok")


if __name__ == "__main__":
    unittest.main()
