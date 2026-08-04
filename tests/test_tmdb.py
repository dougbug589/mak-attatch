import unittest
from unittest import mock

from core import tmdb


class _FakeResp:
    def __init__(self, json_data):
        self._json = json_data

    def json(self):
        return self._json


def _result(media_id, name, date, media_type=""):
    item = {"id": media_id, "name": name,
            "release_date": date, "first_air_date": date}
    if media_type:
        item["media_type"] = media_type
    return item


class SearchTest(unittest.TestCase):
    def test_scoped_tv_search_sets_media_type(self):
        with mock.patch("core.tmdb._fetch") as fetch, \
             mock.patch("core.tmdb.config.get", return_value="k" * 32):
            fetch.return_value = _FakeResp({
                "results": [_result(1, "Breaking Bad", "2008-01-20")],
            })
            results = tmdb.search("Breaking Bad", "tv")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["media_type"], "tv")
        self.assertEqual(results[0]["title"], "Breaking Bad")
        self.assertEqual(results[0]["year"], "2008")

    def test_scoped_movie_search_sets_media_type(self):
        with mock.patch("core.tmdb._fetch") as fetch, \
             mock.patch("core.tmdb.config.get", return_value="k" * 32):
            fetch.return_value = _FakeResp({
                "results": [_result(2, "Inception", "2010-07-16")],
            })
            results = tmdb.search("Inception", "movie")
        self.assertEqual(results[0]["media_type"], "movie")
        self.assertEqual(results[0]["year"], "2010")

    def test_multi_search_keeps_provided_media_type(self):
        with mock.patch("core.tmdb._fetch") as fetch, \
             mock.patch("core.tmdb.config.get", return_value="k" * 32):
            fetch.return_value = _FakeResp({
                "results": [
                    _result(1, "Show", "2008-01-20", media_type="tv"),
                    _result(2, "Film", "2010-07-16", media_type="movie"),
                ],
            })
            results = tmdb.search("anything", "multi")
        self.assertEqual(
            [(r["title"], r["media_type"]) for r in results],
            [("Show", "tv"), ("Film", "movie")],
        )

    def test_year_parsed_from_query(self):
        with mock.patch("core.tmdb._fetch") as fetch, \
             mock.patch("core.tmdb.config.get", return_value="k" * 32):
            fetch.return_value = _FakeResp({"results": []})
            tmdb.search("The Godfather (1972)", "movie")
        url, params = fetch.call_args.args[0], fetch.call_args.kwargs["params"]
        self.assertIn("The Godfather", params["query"])
        self.assertEqual(params.get("year"), "1972")


if __name__ == "__main__":
    unittest.main()
