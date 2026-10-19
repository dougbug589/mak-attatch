import re
from pathlib import Path

try:
    import guessit
except ImportError:
    guessit = None


VIDEO_EXTS = {
    ".mkv", ".avi", ".mp4", ".mov", ".webm", ".flv", ".wmv", ".ts", ".m4v",
    ".mpeg", ".mpg",
}
YEAR_RE = re.compile(r'[\.\s\-_\(](19|20)\d{2}[\.\s\-_\)]?')
EXPLICIT_EPISODE_RE = re.compile(
    r"(?i)(?:^|[^a-z0-9])"
    r"(?:s\d{1,2}e\d{1,3}|\d{1,2}x\d{1,3}|ep?\s*\d{1,3}|episode\s*\d{1,3})"
    r"(?:[^a-z0-9]|$)"
)
LEADING_YEAR_RE = re.compile(r"^((?:19|20)\d{2})(?=$|[\s._:\-])")


def _only_digits(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def _is_numeric_title_episode(name: str, info: dict) -> bool:
    """Detect titles guessit mistakes for episode markers.

    ``Blade Runner 2049`` is parsed as S20E49; the digits 2049 are really the
    end of the title. Only treat it as an episode when guessit does not also
    offer a movie title containing those digits.
    """
    season = info.get("season")
    episode = info.get("episode")
    if season is None or episode is None or guessit is None:
        return False
    candidates = {f"{season:02d}{episode:02d}", f"{season}{episode:02d}"}
    stem_digits = _only_digits(name)
    if not any(candidate and candidate in stem_digits for candidate in candidates):
        return False
    try:
        movie = guessit.guessit(name, {"type": "movie"})
    except (TypeError, ValueError):
        return False
    if movie.get("type") != "movie":
        return False
    title_digits = _only_digits(movie.get("title", ""))
    return any(candidate and candidate in title_digits for candidate in candidates)


def parse_filename(filepath: str) -> dict:
    path = Path(filepath)
    name = path.stem

    result = {"title": name, "year": "", "season": None, "episode": None, "type": "movie"}

    if guessit:
        try:
            info = guessit.guessit(name)
        except (TypeError, ValueError):
            info = {}
        if info:
            is_episode = info.get("type") == "episode"
            if (is_episode and not EXPLICIT_EPISODE_RE.search(name)
                    and _is_numeric_title_episode(name, info)):
                is_episode = False
                info = {}
            if is_episode:
                result["type"] = "episode"
                result["title"] = info.get("title") or name
                result["season"] = info.get("season")
                result["episode"] = info.get("episode")
                result["year"] = str(info.get("year") or "")
                return result

            # Parse as a movie. This keeps titles such as "Blade Runner 2049"
            # intact, which the default (episode-tolerant) guessit pass breaks.
            try:
                movie = guessit.guessit(name, {"type": "movie"})
            except (TypeError, ValueError):
                movie = info
            title = movie.get("title") or ""
            year = str(movie.get("year") or "")
            leading = LEADING_YEAR_RE.match(name)
            if leading:
                lead = leading.group(1)
                if not title:
                    # A numeric title such as "1917" or "2012": the number is
                    # the title, not the release year. Strip any trailing
                    # quality tags by using just the leading number.
                    title = lead if year == lead else name
                    year = "" if year == lead else year
                elif lead not in re.findall(r"\d{4}", title):
                    # "2001: A Space Odyssey" is not released in 2001.
                    title = f"{lead} {title}".strip()
                    if year == lead:
                        year = ""
            result["title"] = title or name
            result["year"] = year
            result["type"] = "movie"
            return result

    if not result["year"]:
        match = YEAR_RE.search(name)
        if match:
            result["year"] = match.group(0).strip(" .-_()")

    return result


def is_video(filepath: str) -> bool:
    return Path(filepath).suffix.lower() in VIDEO_EXTS


def build_search_query(parsed: dict) -> str:
    title = parsed["title"]
    if parsed.get("year"):
        return f"{title} ({parsed['year']})"
    return title
