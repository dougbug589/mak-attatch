import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from mak_attatch.core import attacher, parser


@dataclass
class MediaGroup:
    kind: str  # "show" | "movie"
    title: str
    year: str
    season: int | None
    files: list[str] = field(default_factory=list)
    key: str = ""


_GENERIC_TITLE_RE = re.compile(
    r"(?i)^(?:s\d+e\d+|e\d+|ep\d+|ep\s*\d+|s\d+|\d+[xxe]\d+|\d+|episode\s*\d+)$"
)
_SEASON_FOLDER_RE = re.compile(
    r"(?i)(?:^|[\s.\-_])(?:season|s)\s*(\d{1,2})(?:$|[\s.\-_])"
)
# "S01E01 - Pilot.mkv": the name starts with the episode marker, so whatever
# guessit calls the title ("Pilot") is the episode title, not the series.
_LEADING_EPISODE_RE = re.compile(
    r"(?i)^\s*(?:s\d{1,2}\s*e\d{1,3}|\d{1,2}x\d{1,3}|ep?\s*\d{1,3}|episode\s*\d{1,3})\b"
)
_NON_SERIES_FOLDERS = {
    "", "season", "seasons", "series", "tv", "tv shows", "shows", "show",
    "movies", "movie", "videos", "video", "films", "anime", "animes",
    "cartoons", "documentaries", "kids", "children",
    "specials", "special", "downloads", "download", "media", "library",
}

# Extras are not the title the folder is named after: matching them on their
# own name ("Sample", "Behind the Scenes") attaches some unrelated title's
# poster. Folder names follow Plex/Jellyfin conventions.
_EXTRAS_FOLDERS = {
    "extras", "featurettes", "behind the scenes", "deleted scenes",
    "interviews", "scenes", "trailers", "sample", "samples", "bonus",
}
# Plex/Jellyfin extras suffixes ("Movie-trailer.mkv") and scene samples
# ("release.sample.mkv"). Deliberately narrow so real titles such as
# "The Interview.mkv" or "Deleted.mkv" are still scanned.
_EXTRAS_FILE_RE = re.compile(
    r"(?i)(?:-(?:trailer|sample|featurette|behindthescenes|deleted|interview|scene|short|other)"
    r"|[\s._\-]sample)$"
)


def _is_extra_file(name: str) -> bool:
    stem = Path(name).stem
    return stem.lower() == "sample" or bool(_EXTRAS_FILE_RE.search(stem))


def iter_video_files(root: str) -> list[str]:
    """Recursively collect video files under root, sorted by path."""
    root = os.path.expanduser(root)
    if not os.path.isdir(root):
        return []
    files: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        # Prune extras folders below the scan root (never the root itself).
        dirnames[:] = sorted(d for d in dirnames if d.lower() not in _EXTRAS_FOLDERS)
        for name in sorted(filenames):
            full = os.path.join(dirpath, name)
            if parser.is_video(full) and not _is_extra_file(name):
                files.append(full)
    return files


def _is_generic_title(title: str) -> bool:
    if not title:
        return True
    if not re.search(r"[A-Za-z]{2,}", title):
        return True
    return bool(_GENERIC_TITLE_RE.fullmatch(title.strip()))


def _series_and_season_from_folders(path: str) -> tuple[str | None, int | None]:
    """Guess series name and season from the parent folder names.

    Handles layouts like:
      Series/Season 1/EP01.mkv
      Series Season 1/Series Season 1 EP 1.mkv
      Series/Series S01E01.mkv
    """
    parent = Path(path).parent
    season: int | None = None
    series: str | None = None

    match = _SEASON_FOLDER_RE.search(parent.name)
    if match:
        season = int(match.group(1))
        series = _SEASON_FOLDER_RE.sub(" ", parent.name).strip(" ._-") or None
        if not series:
            series = parent.parent.name.strip(" ._-") or None
    else:
        series = parent.name.strip(" ._-") or None

    if not series or series.lower() in _NON_SERIES_FOLDERS:
        candidate = parent.parent.name.strip(" ._-")
        if candidate and candidate.lower() not in _NON_SERIES_FOLDERS:
            series = candidate

    return series, season


def classify(files: list[str]) -> list[MediaGroup]:
    """Group video files into shows (by series + season) and movies."""
    groups: dict[str, MediaGroup] = {}
    order: list[str] = []

    def get_group(kind: str, title: str, season: int | None, year: str) -> MediaGroup:
        if kind == "movie":
            # Year disambiguates remakes: The Thing (1982) vs The Thing (2011).
            key = f"{kind}|{title.strip().lower()}|{year or ''}"
        else:
            season_key = season if season is not None else 0
            key = f"{kind}|{title.strip().lower()}|{season_key}"
        group = groups.get(key)
        if group is None:
            group = MediaGroup(kind=kind, title=title, year=year, season=season, key=key)
            groups[key] = group
            order.append(key)
        if year and not group.year:
            group.year = year
        return group

    for path in files:
        stem = Path(path).stem
        info = parser.parse_filename(path)

        if info["type"] == "episode":
            series_in_name = (info.get("title_guessed", True)
                              and not _LEADING_EPISODE_RE.match(stem))
            if series_in_name and not _is_generic_title(info["title"]):
                group = get_group("show", info["title"], info["season"], info["year"])
            else:
                series, season = _series_and_season_from_folders(path)
                if not series or _is_generic_title(series):
                    series = info["title"] or stem
                season = season if season is not None else info["season"]
                group = get_group("show", series, season, info["year"])
            group.files.append(path)
            continue

        # movie
        title = info["title"]
        year = info["year"]
        if _is_generic_title(title):
            folder = Path(path).parent.name.strip(" ._-")
            folder_info = parser.parse_filename(str(Path(path).parent))
            folder_title = folder_info.get("title") or folder
            if folder_title and not _is_generic_title(folder_title):
                title = folder_title
                if not year and folder_info.get("year"):
                    year = folder_info["year"]
        group = get_group("movie", title, None, year)
        group.files.append(path)

    return [groups[key] for key in order]


_poster_cache: dict[str, tuple[int, int, bool]] = {}


def clear_poster_cache(path: str | None = None) -> None:
    """Drop cached poster status for *path*, or for every path when omitted."""
    if path is None:
        _poster_cache.clear()
        return
    try:
        key = str(attacher._validate_path(path, attacher.VIDEO_EXTS))
    except (ValueError, OSError):
        key = str(Path(path).expanduser().resolve())
    _poster_cache.pop(key, None)


def _probe_poster(path: str) -> bool:
    ext = Path(path).suffix.lower()
    if ext in attacher.MP4_COMPAT_EXTS:
        return attacher._find_attached_pic(path) is not None
    if ext in attacher.MKV_COMPAT_EXTS:
        # Same definition of "has a poster" as attach/remove use: a cover.*
        # attachment. Other images (font previews, backdrops) do not count,
        # or --skip-existing would skip MKVs that have no poster at all.
        try:
            return bool(attacher._cover_attachment_names(path))
        except (RuntimeError, OSError, subprocess.SubprocessError):
            return False
    return False


def cached_has_poster(path: str) -> bool | None:
    """The cached answer for *path* if it is still current, else None.

    Never probes, so UIs can show known results instantly and fetch the rest
    with has_poster() off the UI thread.
    """
    try:
        key = str(attacher._validate_path(path, attacher.VIDEO_EXTS))
        st = os.stat(key)
    except (ValueError, OSError):
        return False
    cached = _poster_cache.get(key)
    if cached is not None and (st.st_mtime_ns, st.st_size) == cached[:2]:
        return cached[2]
    return None


def has_poster(path: str) -> bool:
    """Return True when the video already carries attached cover art.

    Results are cached per path keyed on (mtime, size), so a file modified
    or re-attached since the last check invalidates itself on the next
    lookup. The cache lives for the process session to skip repeat ffprobe /
    mkvmerge calls across consecutive batch attach runs.
    """
    try:
        path = str(attacher._validate_path(path, attacher.VIDEO_EXTS))
        st = os.stat(path)
    except (ValueError, FileNotFoundError, OSError):
        return False
    cached = _poster_cache.get(path)
    if cached is not None and (st.st_mtime_ns, st.st_size) == cached[:2]:
        return cached[2]
    result = _probe_poster(path)
    _poster_cache[path] = (st.st_mtime_ns, st.st_size, result)
    return result
