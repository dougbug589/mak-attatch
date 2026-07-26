import requests
from urllib.parse import urlparse
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
        _session.headers["User-Agent"] = "poster-attacher/1.0"
    _session.params["api_key"] = config.get("tmdb_api_key")
    return _session


def _validate_url(url: str):
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise TMDBError(f"Blocked non-HTTPS URL: {url}")
    if parsed.hostname not in ALLOWED_HOSTS:
        raise TMDBError(f"Blocked URL from untrusted host: {parsed.hostname}")


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

    session = _get_session()
    params = {"query": query}
    if year:
        params["year"] = year
    resp = session.get(f"{BASE_URL}/search/{media_type}", params=params, timeout=TIMEOUT)
    resp.raise_for_status()
    results = resp.json().get("results", [])

    filtered = []
    for r in results:
        if r.get("media_type") not in ("movie", "tv"):
            continue
        filtered.append({
            "id": r["id"],
            "title": r.get("title") or r.get("name"),
            "year": (r.get("release_date") or r.get("first_air_date") or "")[:4],
            "media_type": r["media_type"],
            "overview": r.get("overview", ""),
            "poster_path": r.get("poster_path"),
        })
    return filtered


def get_posters(media_id: int, media_type: str) -> list[dict]:
    if not config.get("tmdb_api_key"):
        raise TMDBError("No API key set")

    if media_type not in ("movie", "tv"):
        raise TMDBError("Invalid media type")

    session = _get_session()
    resp = session.get(f"{BASE_URL}/{media_type}/{media_id}/images", timeout=TIMEOUT)
    resp.raise_for_status()

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


def download_image(url: str, dest: str):
    _validate_url(url)
    resp = requests.get(url, stream=True, timeout=TIMEOUT, verify=True)
    resp.raise_for_status()

    content_length = int(resp.headers.get("content-length", 0))
    if content_length > MAX_IMAGE_SIZE:
        raise TMDBError(f"Image too large: {content_length} bytes")

    downloaded = 0
    with open(dest, "wb") as f:
        for chunk in resp.iter_content(8192):
            downloaded += len(chunk)
            if downloaded > MAX_IMAGE_SIZE:
                f.close()
                raise TMDBError("Image exceeded size limit during download")
            f.write(chunk)
