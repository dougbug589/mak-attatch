import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from core import attacher, parser


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
_NON_SERIES_FOLDERS = {
    "", "season", "seasons", "series", "tv", "tv shows", "shows", "show",
    "movies", "movie", "videos", "video", "films", "anime", "animes",
    "cartoons", "documentaries", "kids", "children",
}


def iter_video_files(root: str) -> list[str]:
    """Recursively collect video files under root, sorted by path."""
    root = os.path.expanduser(root)
    if not os.path.isdir(root):
        return []
    files: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for name in sorted(filenames):
            full = os.path.join(dirpath, name)
            if parser.is_video(full):
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
            if not _is_generic_title(info["title"]):
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


def has_poster(path: str) -> bool:
    """Return True when the video already carries attached cover art."""
    try:
        path = str(attacher._validate_path(path, attacher.VIDEO_EXTS))
    except (ValueError, FileNotFoundError):
        return False
    ext = Path(path).suffix.lower()
    if ext in attacher.MP4_COMPAT_EXTS:
        return attacher._find_attached_pic(path) is not None
    if ext in attacher.MKV_COMPAT_EXTS:
        try:
            result = subprocess.run(
                ["mkvmerge", "-J", path],
                capture_output=True, timeout=30, check=True,
            )
            data = json.loads(result.stdout)
        except Exception:  # nosec B110
            return False
        mimes = set(attacher.MIME_MAP.values())
        for att in data.get("attachments", []):
            if att.get("content_type") in mimes or att.get("mime_type") in mimes:
                return True
        return False
    return False
