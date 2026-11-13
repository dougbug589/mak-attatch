import difflib
import os
import re
import time
import unicodedata
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests

from mak_attatch import config

BASE_URL = "https://api.themoviedb.org/3"
IMG_BASE = "https://image.tmdb.org/t/p"
ALLOWED_HOSTS = {"api.themoviedb.org", "image.tmdb.org"}
TIMEOUT = 15
MAX_REDIRECTS = 3
MAX_IMAGE_SIZE = 50 * 1024 * 1024  # 50MB


class TMDBError(Exception):
    def __init__(self, message: str = "", status: int | None = None):
        super().__init__(message)
        self.status = status


MAX_RATE_LIMIT_RETRIES = 2
MAX_RETRY_AFTER = 10  # seconds

_SECRET_RE = re.compile(r"(api_key=)[^&\s'\"]+", re.IGNORECASE)


def redact(text: str) -> str:
    """Remove a v3 API key from text that may contain a request URL."""
    return _SECRET_RE.sub(r"\1[REDACTED]", str(text))


def _http_error_message(status: int) -> str:
    if status == 401:
        return "TMDB rejected the API key (HTTP 401)"
    if status == 404:
        return "Not found on TMDB (HTTP 404)"
    if status == 429:
        return "TMDB rate limit hit (HTTP 429); try again shortly"
    return f"TMDB returned HTTP {status}"


def _retry_after(resp) -> float:
    try:
        return min(MAX_RETRY_AFTER, max(0.0, float(resp.headers.get("Retry-After", 1))))
    except (TypeError, ValueError):
        return 1.0


_session = None


def _get_session() -> requests.Session:
    global _session
    if _session is None:
        _session = requests.Session()
        _session.max_redirects = MAX_REDIRECTS
        _session.headers["User-Agent"] = "mak-attatch/1.0"
    return _session


def _fetch(url: str, stream: bool = False, params: dict = None) -> requests.Response:
    session = _get_session()
    headers = {}
    params = dict(params or {})
    if urlparse(url).hostname == "api.themoviedb.org":
        api_key = config.get("tmdb_api_key")
        if api_key and "." in api_key and len(api_key) > 40:
            headers["Authorization"] = f"Bearer {api_key}"
        else:
            params["api_key"] = api_key

    # Errors raised from here never carry the request URL: with a v3 key the
    # URL contains ?api_key=..., and requests puts the URL into both HTTPError
    # and ConnectionError messages, which the CLI/GUI/TUI display verbatim.
    current = url
    redirects = 0
    rate_limited = 0
    while True:
        _validate_url(current)
        try:
            resp = session.get(current, params=params, stream=stream, timeout=TIMEOUT,
                               allow_redirects=False, headers=headers)
        except requests.RequestException as e:
            raise TMDBError(f"Could not reach TMDB ({type(e).__name__})") from None
        if resp.status_code in (301, 302, 303, 307, 308) and resp.headers.get("Location"):
            redirects += 1
            if redirects > MAX_REDIRECTS:
                resp.close()
                raise TMDBError("Too many redirects")
            next_url = urljoin(current, resp.headers["Location"])
            # Credentials must not travel across hosts; keep them when the
            # redirect stays on the same host (dropping the v3 key there
            # would turn a harmless redirect into a 401).
            same_host = urlparse(next_url).hostname == urlparse(current).hostname
            if not same_host:
                headers.pop("Authorization", None)
            params = {"api_key": params["api_key"]} if same_host and "api_key" in params else {}
            current = next_url
            resp.close()
            continue
        if resp.status_code == 429 and rate_limited < MAX_RATE_LIMIT_RETRIES:
            rate_limited += 1
            wait = _retry_after(resp)
            resp.close()
            time.sleep(wait)
            continue
        _validate_url(resp.url)
        if resp.status_code >= 400:
            status = resp.status_code
            resp.close()
            raise TMDBError(_http_error_message(status), status=status)
        return resp


def _validate_url(url: str):
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise TMDBError("Blocked non-HTTPS URL")
    if parsed.hostname not in ALLOWED_HOSTS:
        raise TMDBError("Blocked URL from untrusted host")


def _plausible_release_year(year: str) -> bool:
    if not year.isdigit():
        return False
    return 1888 <= int(year) <= time.localtime().tm_year + 2


def _split_query_year(query: str) -> tuple[str, str]:
    """Split a trailing year from a search query.

    Only a year at the very end counts, so numeric titles such as ``1917``,
    ``2012`` and ``Blade Runner 2049`` keep their full title. A future year
    beyond the current release window is treated as part of the title.
    """
    import re

    text = query.strip()
    explicit = re.search(r"\((\d{4})\)\s*$", text)
    if explicit:
        title = text[:explicit.start()].strip()
        if title and _plausible_release_year(explicit.group(1)):
            return title, explicit.group(1)
    trailing = re.search(r"(?<=\s)((?:19|20)\d{2})\s*$", text)
    if trailing:
        title = text[:trailing.start()].strip()
        if title and _plausible_release_year(trailing.group(1)):
            return title, trailing.group(1)
    return text, ""


def search(query: str, media_type: str = "multi") -> list[dict]:
    if not config.get("tmdb_api_key"):
        raise TMDBError("No API key set")

    if media_type not in ("multi", "movie", "tv"):
        raise TMDBError("Invalid media type")

    original_query = query.strip()
    query, year = _split_query_year(query)
    if not query:
        raise TMDBError("Empty search query")

    params = {"query": query}
    if year:
        if media_type == "movie":
            params["year"] = year
        elif media_type == "tv":
            params["first_air_date_year"] = year
    resp = _fetch(f"{BASE_URL}/search/{media_type}", params=params)
    results = resp.json().get("results", [])
    if not results and year and not original_query.endswith(")"):
        # A bare trailing number may be part of the title ("Wonder Woman
        # 1984", "Space 1999"): retry it as plain text before giving up.
        query, year = original_query, ""
        resp = _fetch(f"{BASE_URL}/search/{media_type}", params={"query": query})
        results = resp.json().get("results", [])

    filtered = []
    for r in results:
        mt = r.get("media_type") or media_type
        if mt not in ("movie", "tv"):
            continue
        filtered.append({
            "id": r["id"],
            "title": r.get("title") or r.get("name"),
            "original_title": r.get("original_title") or r.get("original_name") or "",
            "year": (r.get("release_date") or r.get("first_air_date") or "")[:4],
            "media_type": mt,
            "overview": r.get("overview", ""),
            "poster_path": r.get("poster_path"),
        })

    if year and media_type == "multi":
        # /search/multi does not accept a year parameter, so narrow locally
        # when the caller provided one (e.g. Dune (1984) vs Dune (2021)).
        year_filtered = [r for r in filtered if r["year"] == year]
        if year_filtered:
            filtered = year_filtered

    return filtered


# A result whose title is less similar than this to the parsed filename title
# is treated as "no match" (left for the user to review) instead of attaching
# some unrelated title's poster. TMDB's first result is a popularity guess,
# not a confirmation: "Sample", "trailer" or "Birthday Party 2019" all return
# *something*.
MIN_TITLE_SIMILARITY = 0.75

_LEADING_ARTICLE_RE = re.compile(r"^(?:the|a|an)\s+")


def normalize_title(title: str) -> str:
    text = unicodedata.normalize("NFKD", str(title or ""))
    text = text.encode("ascii", "ignore").decode().lower().replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text).strip()
    return _LEADING_ARTICLE_RE.sub("", text)


def title_similarity(wanted: str, candidate: str) -> float:
    a, b = normalize_title(wanted), normalize_title(candidate)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    score = difflib.SequenceMatcher(None, a, b).ratio()
    ta, tb = a.split(), b.split()
    n = min(len(ta), len(tb))
    if n and ta[:n] == tb[:n]:
        # "Star Wars" vs "Star Wars: A New Hope", "Show" vs "Show (US)".
        score = max(score, 0.8)
    return score


def best_match(results: list[dict], title: str, year: str = "") -> dict | None:
    """Pick the result that plausibly *is* this title, or None.

    Among results similar enough to ``title`` (by title or original title),
    prefer one whose year matches, then the most similar; ties keep TMDB's
    order.
    """
    scored = []
    for index, r in enumerate(results):
        score = max(title_similarity(title, r.get("title") or ""),
                    title_similarity(title, r.get("original_title") or ""))
        if score >= MIN_TITLE_SIMILARITY:
            scored.append((score, index, r))
    if not scored:
        return None
    if year:
        same_year = [s for s in scored if str(s[2].get("year") or "").startswith(str(year))]
        if same_year:
            scored = same_year
    return max(scored, key=lambda s: (s[0], -s[1]))[2]


def get_posters(media_id: int, media_type: str) -> list[dict]:
    if not config.get("tmdb_api_key"):
        raise TMDBError("No API key set")

    if media_type not in ("movie", "tv"):
        raise TMDBError("Invalid media type")

    resp = _fetch(f"{BASE_URL}/{media_type}/{media_id}/images")

    posters = []
    for p in resp.json().get("posters", []):
        if not isinstance(p, dict):
            continue
        file_path = p.get("file_path", "")
        if not file_path or ".." in file_path:
            continue
        url = f"{IMG_BASE}/original{file_path}"
        thumb_url = f"{IMG_BASE}/w500{file_path}"
        _validate_url(url)
        _validate_url(thumb_url)
        posters.append({
            "file_path": file_path,
            "width": int(p.get("width") or 0),
            "height": int(p.get("height") or 0),
            "lang": p.get("iso_639_1", ""),
            "url": url,
            "thumb_url": thumb_url,
        })

    posters.sort(key=lambda x: (x["lang"] != "en", -x["width"]))
    return posters


def get_details(media_id: int, media_type: str) -> dict:
    if not config.get("tmdb_api_key"):
        raise TMDBError("No API key set")

    if media_type not in ("movie", "tv"):
        raise TMDBError("Invalid media type")

    details = _fetch(f"{BASE_URL}/{media_type}/{media_id}").json()
    credits = _fetch(f"{BASE_URL}/{media_type}/{media_id}/credits").json()

    metadata = {
        "title": details.get("title") or details.get("name"),
        "original_title": details.get("original_title") or details.get("original_name"),
        "year": (details.get("release_date") or details.get("first_air_date") or "")[:4],
        "overview": details.get("overview", ""),
        "tagline": details.get("tagline", ""),
        "genres": [g.get("name", "") for g in details.get("genres", []) if g.get("name")],
        "rating": details.get("vote_average"),
        "media_type": media_type,
    }

    if media_type == "movie":
        crew = credits.get("crew", [])
        metadata["runtime"] = details.get("runtime")
        metadata["directors"] = sorted(
            {c.get("name") for c in crew if c.get("job") == "Director" and c.get("name")}
        )
        metadata["writers"] = sorted(
            {c.get("name") for c in crew
             if c.get("job") in ("Writer", "Screenplay") and c.get("name")}
        )
    else:
        metadata["runtime"] = None
        metadata["creators"] = [
            c.get("name") for c in details.get("created_by", []) if c.get("name")
        ]
        metadata["seasons"] = details.get("number_of_seasons")
        metadata["episodes"] = details.get("number_of_episodes")

    cast = []
    for c in credits.get("cast", [])[:10]:
        if c.get("name"):
            cast.append({"name": c["name"], "character": c.get("character", "")})
    metadata["cast"] = cast

    return metadata


def details_for_path(path: str, current_media: dict = None) -> dict:
    """Return TMDB details for a video path.

    Prefers an explicit media selection (dict with "id" and "media_type").
    Otherwise auto-searches the file's filename and uses the top result.
    Raises TMDBError when no match is found.
    """
    if current_media:
        return get_details(current_media["id"], current_media["media_type"])
    from mak_attatch.core import parser

    parsed = parser.parse_filename(path)
    results = search(parser.build_search_query(parsed))
    if not results:
        raise TMDBError(f"No TMDB match for {Path(path).name}")
    match = best_match(results, parsed["title"], parsed.get("year", ""))
    if match is None:
        raise TMDBError(
            f"No confident TMDB match for {Path(path).name} "
            f"(closest: {results[0].get('title')!r})"
        )
    return get_details(match["id"], match["media_type"])


VALID_IMAGE_TYPES = {
    "image/jpeg", "image/png", "image/webp", "image/bmp", "image/gif", "image/tiff",
}


def _sniff_image_mime(image_path: str) -> str | None:
    """Strict magic-byte sniff. Returns None when the payload looks like no image."""
    try:
        with open(image_path, "rb") as f:
            head = f.read(12)
    except OSError:
        return None
    if head[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if head[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    if head[:2] == b"BM":
        return "image/bmp"
    if head[:4] in (b"II*\x00", b"MM\x00*"):
        return "image/tiff"
    return None


def download_image(url: str, dest: str):
    _validate_url(url)
    resp = None
    for attempt in range(3):
        try:
            resp = _fetch(url, stream=True)
            break
        except (TMDBError, requests.HTTPError) as e:
            if isinstance(e, TMDBError):
                status = e.status
            else:
                status = e.response.status_code if e.response is not None else None
            if status and 500 <= status < 600 and attempt < 2:
                time.sleep(2 ** attempt)
                continue
            if status == 503:
                raise TMDBError("TMDB is busy", status=503) from None
            if status:
                raise TMDBError(f"TMDB returned HTTP {status}", status=status) from None
            raise

    try:
        content_type = resp.headers.get("content-type", "").lower().split(";")[0].strip()
        if content_type not in VALID_IMAGE_TYPES:
            raise TMDBError(f"Unexpected content type: {content_type}")

        content_length = int(resp.headers.get("content-length", 0) or 0)
        if content_length > MAX_IMAGE_SIZE:
            raise TMDBError("Image too large")

        downloaded = 0
        with open(dest, "wb") as f:
            for chunk in resp.iter_content(8192):
                downloaded += len(chunk)
                if downloaded > MAX_IMAGE_SIZE:
                    raise TMDBError("Image exceeded size limit during download")
                f.write(chunk)

        mime = _sniff_image_mime(dest)
        if mime not in VALID_IMAGE_TYPES:
            raise TMDBError("Downloaded content is not a valid image")
    except BaseException:
        # Callers own dest, but a half-written image must never be attached.
        try:
            os.unlink(dest)
        except OSError:
            pass
        raise
    finally:
        close = getattr(resp, "close", None)
        if close:
            close()
