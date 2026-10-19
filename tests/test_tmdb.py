import unittest
from unittest import mock
from unittest.mock import MagicMock

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
        self.assertIn("search/movie", url)

    def test_numeric_title_is_not_stripped(self):
        with mock.patch("core.tmdb._fetch") as fetch, \
             mock.patch("core.tmdb.config.get", return_value="k" * 32):
            fetch.return_value = _FakeResp({"results": []})
            tmdb.search("1917", "movie")
        params = fetch.call_args.kwargs["params"]
        self.assertEqual(params["query"], "1917")
        self.assertNotIn("year", params)

    def test_trailing_number_stays_in_title(self):
        with mock.patch("core.tmdb._fetch") as fetch, \
             mock.patch("core.tmdb.config.get", return_value="k" * 32):
            fetch.return_value = _FakeResp({"results": []})
            tmdb.search("Blade Runner 2049", "movie")
        params = fetch.call_args.kwargs["params"]
        self.assertEqual(params["query"], "Blade Runner 2049")
        self.assertNotIn("year", params)

    def test_numeric_title_with_parenthesised_year(self):
        with mock.patch("core.tmdb._fetch") as fetch, \
             mock.patch("core.tmdb.config.get", return_value="k" * 32):
            fetch.return_value = _FakeResp({"results": []})
            tmdb.search("1917 (2019)", "movie")
        params = fetch.call_args.kwargs["params"]
        self.assertEqual(params["query"], "1917")
        self.assertEqual(params.get("year"), "2019")

    def test_tv_search_uses_first_air_date_year(self):
        with mock.patch("core.tmdb._fetch") as fetch, \
             mock.patch("core.tmdb.config.get", return_value="k" * 32):
            fetch.return_value = _FakeResp({"results": []})
            tmdb.search("Breaking Bad (2008)", "tv")
        params = fetch.call_args.kwargs["params"]
        self.assertEqual(params["query"], "Breaking Bad")
        self.assertEqual(params.get("first_air_date_year"), "2008")
        self.assertNotIn("year", params)

    def test_multi_search_narrows_by_year(self):
        with mock.patch("core.tmdb._fetch") as fetch, \
             mock.patch("core.tmdb.config.get", return_value="k" * 32):
            fetch.return_value = _FakeResp({
                "results": [
                    _result(1, "Dune", "1984-12-14", media_type="movie"),
                    _result(2, "Dune", "2021-10-22", media_type="movie"),
                ],
            })
            results = tmdb.search("Dune (2021)", "multi")
        self.assertEqual([r["year"] for r in results], ["2021"])


class FetchRedirectTest(unittest.TestCase):
    def test_fetch_follows_302_redirect(self):
        redirect_resp = MagicMock()
        redirect_resp.status_code = 302
        redirect_resp.headers = {"Location": "/p/w500/new.jpg"}
        redirect_resp.close = MagicMock()

        final_resp = MagicMock()
        final_resp.status_code = 200
        final_resp.headers = {"content-type": "image/jpeg"}
        final_resp.url = "https://image.tmdb.org/p/w500/new.jpg"
        final_resp.raise_for_status = MagicMock()

        mock_session = MagicMock()
        mock_session.get.side_effect = [redirect_resp, final_resp]

        with mock.patch("core.tmdb._get_session", return_value=mock_session), \
             mock.patch("core.tmdb._validate_url"):
            result = tmdb._fetch("https://image.tmdb.org/p/w500/old.jpg")

        self.assertEqual(mock_session.get.call_count, 2)
        self.assertEqual(mock_session.get.call_args_list[1][0][0],
                         "https://image.tmdb.org/p/w500/new.jpg")
        self.assertEqual(result, final_resp)
        redirect_resp.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
