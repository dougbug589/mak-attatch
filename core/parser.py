import re
from pathlib import Path

try:
    import guessit
except ImportError:
    guessit = None


VIDEO_EXTS = {".mkv", ".avi", ".mp4", ".mov", ".webm", ".flv", ".wmv", ".ts", ".m4v", ".mpeg", ".mpg"}
YEAR_RE = re.compile(r'[\.\s\-_\(](19|20)\d{2}[\.\s\-_\)]?')


def parse_filename(filepath: str) -> dict:
    path = Path(filepath)
    name = path.stem

    result = {"title": name, "year": "", "season": None, "episode": None, "type": "movie"}

    if guessit:
        try:
            info = guessit.guessit(name)
            result["title"] = info.get("title", name)
            result["year"] = str(info.get("year", ""))
            if info.get("type") == "episode":
                result["type"] = "episode"
                result["season"] = info.get("season")
                result["episode"] = info.get("episode")
        except Exception:  # nosec B110
            pass

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
