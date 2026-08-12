import os
import tempfile
import time
from pathlib import Path

from core import attacher, scanner, tmdb


def _best_match(results: list[dict], year: str) -> dict | None:
    if not results:
        return None
    if year:
        for r in results:
            if str(r.get("year") or "").startswith(str(year)):
                return r
    return results[0]


def resolve_groups(groups: list[scanner.MediaGroup], api_delay: float = 0.25,
                   progress=None, cancel=None) -> list[dict]:
    """One scoped TMDB search per group; returns list of resolved entries.

    Entry shape:
      {"group", "match": {"id", "media_type", "title", "year"} | None,
       "status": "ok" | "no-match" | "error", "error": str}
    """
    resolved: list[dict] = []
    total = len(groups)
    for index, group in enumerate(groups):
        if cancel and cancel():
            break
        entry = {"group": group, "match": None, "status": "error", "error": ""}
        query = group.title
        if group.year:
            query = f"{query} ({group.year})"
        media_type = "tv" if group.kind == "show" else "movie"
        try:
            results = tmdb.search(query, media_type)
            match = _best_match(results, group.year)
            if match:
                entry["match"] = {
                    "id": match["id"],
                    "media_type": media_type,
                    "title": match["title"],
                    "year": match["year"],
                }
                entry["status"] = "ok"
            else:
                entry["status"] = "no-match"
        except Exception as e:  # nosec B110
            entry["error"] = str(e)
        resolved.append(entry)
        if progress:
            progress(index + 1, total, group)
        time.sleep(api_delay)
    return resolved


def attach_groups(resolved: list[dict], skip_existing: bool = True,
                  scrape_metadata: bool = False, api_delay: float = 0.25,
                  to_mkv: bool = False, progress=None, cancel=None) -> dict:
    """Attach the resolved posters to every file in every matched group.

    A resolved entry may carry a "poster" dict (a choice made during review);
    otherwise the first available poster from TMDB is used.

    When ``to_mkv`` is True, non-MKV sources are first remuxed to MKV with a
    lossless stream copy before the poster is attached.

    Returns a summary dict: {"ok", "fail", "skipped", "errors"}.
    """
    summary = {"ok": 0, "fail": 0, "skipped": 0, "errors": []}
    MAX_ERRORS = 20
    ok_groups = [r for r in resolved if r["status"] == "ok"]
    total_files = sum(len(r["group"].files) for r in ok_groups)
    done = 0

    for entry in ok_groups:
        group = entry["group"]
        match = entry["match"]
        poster_path = None
        try:
            posters = tmdb.get_posters(match["id"], match["media_type"])
            if not posters:
                summary["fail"] += len(group.files)
                if len(summary["errors"]) < MAX_ERRORS:
                    summary["errors"].append(f"{group.title}: no posters available")
                continue
            chosen = entry.get("poster") or posters[0]
            url = chosen.get("url") or chosen.get("thumb_url")
            if not url:
                summary["fail"] += len(group.files)
                if len(summary["errors"]) < MAX_ERRORS:
                    summary["errors"].append(f"{group.title}: poster has no image URL")
                continue
            fd, poster_path = tempfile.mkstemp(suffix=".jpg")
            os.close(fd)
            os.chmod(poster_path, 0o600)
            tmdb.download_image(url, poster_path)

            metadata = None
            if scrape_metadata:
                metadata = tmdb.get_details(match["id"], match["media_type"])

            for filepath in group.files:
                if cancel and cancel():
                    break
                done += 1
                if skip_existing and scanner.has_poster(filepath):
                    summary["skipped"] += 1
                    if progress:
                        progress(done, total_files, filepath, "skip")
                    continue
                try:
                    attacher.full_attach(filepath, poster_path, metadata=metadata,
                                         to_mkv=to_mkv)
                    summary["ok"] += 1
                    if progress:
                        progress(done, total_files, filepath, "ok")
                except Exception as e:  # nosec B110
                    summary["fail"] += 1
                    if len(summary["errors"]) < MAX_ERRORS:
                        summary["errors"].append(f"{Path(filepath).name}: {e}")
                    if progress:
                        progress(done, total_files, filepath, "fail")
            time.sleep(api_delay)
        except Exception as e:  # nosec B110
            summary["fail"] += len(group.files)
            if len(summary["errors"]) < MAX_ERRORS:
                summary["errors"].append(f"{group.title}: {e}")
        finally:
            if poster_path:
                try:
                    os.unlink(poster_path)
                except OSError:
                    pass

    return summary
