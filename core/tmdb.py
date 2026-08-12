import os
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests

import config

BASE_URL = "https://api.themoviedb.org/3"
IMG_BASE = "https://image.tmdb.org/t/p"
ALLOWED_HOSTS = {"api.themoviedb.org", "image.tmdb.org"}
TIMEOUT = 15
MAX_REDIRECTS = 3
MAX_IMAGE_SIZE = 50 * 1024 * 1024  # 50MB


class TMDBError(Exception):
    pass


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

    current = url
    for _ in range(MAX_REDIRECTS + 1):
        _validate_url(current)
        resp = session.get(current, params=params, stream=stream, timeout=TIMEOUT,
                           allow_redirects=False, headers=headers)
        if resp.status_code in (301, 302, 303, 307, 308) and resp.headers.get("Location"):
            next_url = urljoin(current, resp.headers["Location"])
            # Authorization header must not travel across hosts; it is safe
            # to keep it when the redirect stays within the same host.
            if urlparse(next_url).hostname != urlparse(current).hostname:
                headers.pop("Authorization", None)
            params = {}
            current = next_url
            resp.close()
            continue
        _validate_url(resp.url)
        resp.raise_for_status()
        return resp
    raise TMDBError("Too many redirects")


def _validate_url(url: str):
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise TMDBError("Blocked non-HTTPS URL")
    if parsed.hostname not in ALLOWED_HOSTS:
        raise TMDBError("Blocked URL from untrusted host")


def search(query: str, media_type: str = "multi") -> list[dict]:
    if not config.get("tmdb_api_key"):
        raise TMDBError("No API key set")

    if media_type not in ("multi", "movie", "tv"):
        raise TMDBError("Invalid media type")

    import re
    year_match = re.search(r'\((\d{4})\)|\b(19|20)\d{2}\b', query)
    year = ""
    if year_match:
        year = year_match.group(1) or year_match.group(0)
        year = year.strip("() ")
        query = re.sub(r'\(?\d{4}\)?|\b(19|20)\d{2}\b', '', query).strip()

    if not query:
        raise TMDBError("Empty search query")

    params = {"query": query}
    if year:
        params["year"] = year
    resp = _fetch(f"{BASE_URL}/search/{media_type}", params=params)
    results = resp.json().get("results", [])

    filtered = []
    for r in results:
        mt = r.get("media_type") or media_type
        if mt not in ("movie", "tv"):
            continue
        filtered.append({
            "id": r["id"],
            "title": r.get("title") or r.get("name"),
            "year": (r.get("release_date") or r.get("first_air_date") or "")[:4],
            "media_type": mt,
            "overview": r.get("overview", ""),
            "poster_path": r.get("poster_path"),
        })
    return filtered


def get_posters(media_id: int, media_type: str) -> list[dict]:
    if not config.get("tmdb_api_key"):
        raise TMDBError("No API key set")

    if media_type not in ("movie", "tv"):
        raise TMDBError("Invalid media type")

    resp = _fetch(f"{BASE_URL}/{media_type}/{media_id}/images")

    posters = []
    for p in resp.json().get("posters", []):
        file_path = p.get("file_path", "")
        if not file_path or ".." in file_path:
            continue
        url = f"{IMG_BASE}/original{file_path}"
        thumb_url = f"{IMG_BASE}/w500{file_path}"
        _validate_url(url)
        _validate_url(thumb_url)
        posters.append({
            "file_path": file_path,
            "width": p["width"],
            "height": p["height"],
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
        metadata["directors"] = sorted({c.get("name") for c in crew if c.get("job") == "Director"})
        metadata["writers"] = sorted(
            {c.get("name") for c in crew if c.get("job") in ("Writer", "Screenplay")}
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
    from core import parser

    parsed = parser.parse_filename(path)
    results = search(parser.build_search_query(parsed))
    if not results:
        raise TMDBError(f"No TMDB match for {Path(path).name}")
    top = results[0]
    return get_details(top["id"], top["media_type"])


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
        except requests.HTTPError as e:
            status = e.response.status_code if e.response is not None else None
            if status and 500 <= status < 600 and attempt < 2:
                time.sleep(2 ** attempt)
                continue
            if status == 503:
                raise TMDBError("TMDB is busy")
            if status:
                raise TMDBError(f"TMDB returned HTTP {status}")
            raise

    content_type = resp.headers.get("content-type", "").lower().split(";")[0].strip()
    if content_type not in VALID_IMAGE_TYPES:
        raise TMDBError(f"Unexpected content type: {content_type}")

    content_length = int(resp.headers.get("content-length", 0))
    if content_length > MAX_IMAGE_SIZE:
        raise TMDBError("Image too large")

    downloaded = 0
    with open(dest, "wb") as f:
        for chunk in resp.iter_content(8192):
            downloaded += len(chunk)
            if downloaded > MAX_IMAGE_SIZE:
                f.close()
                raise TMDBError("Image exceeded size limit during download")
            f.write(chunk)

    mime = _sniff_image_mime(dest)
    if mime not in VALID_IMAGE_TYPES:
        os.unlink(dest)
        raise TMDBError("Downloaded content is not a valid image")
