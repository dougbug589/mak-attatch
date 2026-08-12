import unittest
from io import StringIO
from unittest import mock
from unittest.mock import MagicMock

import requests

from core import attacher, autoattach, tmdb
from core.scanner import MediaGroup


class FetchRedirectAuthTest(unittest.TestCase):
    """Issue 1: Authorization header must survive same-host redirects."""

    API_KEY = "k" * 40 + "."

    def _make_redirect(self, location):
        redirect_resp = MagicMock()
        redirect_resp.status_code = 302
        redirect_resp.headers = {"Location": location}
        redirect_resp.close = MagicMock()
        return redirect_resp

    def _make_final(self, url):
        final_resp = MagicMock()
        final_resp.status_code = 200
        final_resp.headers = {"content-type": "image/jpeg"}
        final_resp.url = url
        final_resp.raise_for_status = MagicMock()
        return final_resp

    def test_same_host_redirect_keeps_authorization(self):
        redirect_resp = self._make_redirect("/p/w500/new.jpg")
        final_resp = self._make_final("https://api.themoviedb.org/p/w500/new.jpg")
        seen = []

        def fake_get(url, **kwargs):
            seen.append((url, dict(kwargs.get("headers", {}))))
            if len(seen) == 1:
                return redirect_resp
            return final_resp

        mock_session = MagicMock()
        mock_session.get.side_effect = fake_get

        with mock.patch("core.tmdb._get_session", return_value=mock_session), \
             mock.patch("core.tmdb._validate_url"), \
             mock.patch("core.tmdb.config.get", return_value=self.API_KEY):
            tmdb._fetch("https://api.themoviedb.org/p/w500/old.jpg")

        self.assertEqual(seen[0][1]["Authorization"], f"Bearer {self.API_KEY}")
        self.assertEqual(seen[1][1]["Authorization"], f"Bearer {self.API_KEY}")

    def test_cross_host_redirect_strips_authorization(self):
        redirect_resp = self._make_redirect("https://image.tmdb.org/p/w500/new.jpg")
        final_resp = self._make_final("https://image.tmdb.org/p/w500/new.jpg")
        seen = []

        def fake_get(url, **kwargs):
            seen.append((url, dict(kwargs.get("headers", {}))))
            if len(seen) == 1:
                return redirect_resp
            return final_resp

        mock_session = MagicMock()
        mock_session.get.side_effect = fake_get

        with mock.patch("core.tmdb._get_session", return_value=mock_session), \
             mock.patch("core.tmdb._validate_url"), \
             mock.patch("core.tmdb.config.get", return_value=self.API_KEY):
            tmdb._fetch("https://api.themoviedb.org/p/w500/old.jpg")

        self.assertEqual(seen[0][1]["Authorization"], f"Bearer {self.API_KEY}")
        self.assertNotIn("Authorization", seen[1][1])


def _http_error(status):
    err = requests.HTTPError("boom")
    err.response = MagicMock()
    err.response.status_code = status
    return err


class DownloadImageTest(unittest.TestCase):
    """Issues 3/6: retries on 5xx, magic-byte verification of the payload."""

    def _resp(self, content_type="image/jpeg", payload=b"MZ..."):
        resp = MagicMock()
        resp.headers = {"content-type": content_type, "content-length": str(len(payload))}
        resp.iter_content = lambda size: [payload]
        resp.raise_for_status = MagicMock()
        return resp

    def _dest(self):
        import tempfile
        fd, path = tempfile.mkstemp(suffix=".jpg")
        import os
        os.close(fd)
        try:
            os.unlink(path)
        except OSError:
            pass
        return path

    def test_valid_jpeg_magic_bytes_accepted(self):
        payload = b"\xff\xd8\xff\xe0" + b"\x00" * 16
        dest = self._dest()
        resp = self._resp(content_type="image/jpeg", payload=payload)
        with mock.patch("core.tmdb._fetch", return_value=resp), \
             mock.patch("core.tmdb._validate_url"):
            tmdb.download_image("https://image.tmdb.org/t/p/x.jpg", dest)
        with open(dest, "rb") as f:
            self.assertEqual(f.read(), payload)

    def test_retries_503_then_succeeds(self):
        dest = self._dest()
        resp = self._resp(payload=b"\xff\xd8\xff\xe0" + b"\x00" * 8)
        with mock.patch("core.tmdb._fetch",
                        side_effect=[_http_error(503), _http_error(503), resp]) as fetch, \
             mock.patch("core.tmdb._validate_url"), \
             mock.patch("core.tmdb.time.sleep"):
            tmdb.download_image("https://image.tmdb.org/t/p/x.jpg", dest)
        self.assertEqual(fetch.call_count, 3)

    def test_503_after_all_retries_raises_busy(self):
        dest = self._dest()
        with mock.patch("core.tmdb._fetch", side_effect=[_http_error(503)] * 3), \
             mock.patch("core.tmdb._validate_url"), \
             mock.patch("core.tmdb.time.sleep"):
            with self.assertRaises(tmdb.TMDBError) as ctx:
                tmdb.download_image("https://image.tmdb.org/t/p/x.jpg", dest)
        self.assertEqual(str(ctx.exception), "TMDB is busy")

    def test_other_5xx_after_retries_raises_status(self):
        dest = self._dest()
        with mock.patch("core.tmdb._fetch",
                        side_effect=[_http_error(500)] * 3), \
             mock.patch("core.tmdb._validate_url"), \
             mock.patch("core.tmdb.time.sleep"):
            with self.assertRaises(tmdb.TMDBError) as ctx:
                tmdb.download_image("https://image.tmdb.org/t/p/x.jpg", dest)
        self.assertEqual(str(ctx.exception), "TMDB returned HTTP 500")

    def test_non_image_payload_rejected_and_deleted(self):
        import os
        dest = self._dest()
        resp = self._resp(content_type="image/jpeg", payload=b"MZ\x90\x00")
        with mock.patch("core.tmdb._fetch", return_value=resp), \
             mock.patch("core.tmdb._validate_url"):
            with self.assertRaises(tmdb.TMDBError):
                tmdb.download_image("https://image.tmdb.org/t/p/x.jpg", dest)
        self.assertFalse(os.path.exists(dest))
        del resp, dest


class FindAttachedPicTest(unittest.TestCase):
    """Issue 2: invalid paths are logged to stderr, not swallowed silently."""

    def test_invalid_path_returns_none_and_warns(self):
        stderr = StringIO()
        with mock.patch("core.attacher._validate_path",
                        side_effect=ValueError("Path traversal detected: ../x")), \
             mock.patch("core.attacher.subprocess.run") as run, \
             mock.patch("sys.stderr", stderr):
            result = attacher._find_attached_pic("../x")
        self.assertIsNone(result)
        run.assert_not_called()
        self.assertIn("Warning: skipping invalid path", stderr.getvalue())


class ErrorCapTest(unittest.TestCase):
    """Issue 4: error list stays bounded at 20 while failing files keep counting."""

    def test_errors_capped_at_20(self):
        group = MediaGroup(kind="movie", title="Boom Town", year="2020",
                           season=None, files=[f"/x/file{i}.mkv" for i in range(25)])
        resolved = [{
            "group": group, "status": "ok",
            "match": {"id": 1, "media_type": "movie", "title": "Boom Town", "year": "2020"},
        }]

        with mock.patch("core.autoattach.tmdb.get_posters",
                        return_value=[{"url": "https://image.tmdb.org/t/p/x.jpg"}]), \
             mock.patch("core.autoattach.tmdb.download_image"), \
             mock.patch("core.autoattach.attacher.full_attach",
                        side_effect=RuntimeError("boom")), \
             mock.patch("core.autoattach.scanner.has_poster", return_value=False), \
             mock.patch("core.autoattach.time.sleep"):
            summary = autoattach.attach_groups(resolved)

        self.assertEqual(summary["fail"], 25)
        self.assertEqual(len(summary["errors"]), 20)
        self.assertEqual(summary["ok"], 0)


if __name__ == "__main__":
    unittest.main()