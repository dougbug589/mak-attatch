#!/usr/bin/env python3
"""mak-attatch CLI — headless poster attachment, removal, and folder scans.

Shares the core/ pipeline with the GUI and TUI, but stays Qt-free so it can
run in scripts, cron jobs, and file-manager actions.

Examples:
    mak-attatch-cli attach -f movie.mkv -s "The Matrix" --embed-metadata
    mak-attatch-cli attach -f movie.mkv -p poster.jpg
    mak-attatch-cli attach -f "show S01E01.mkv"
    mak-attatch-cli remove -f movie.mkv
    mak-attatch-cli remove -f movie.mkv --metadata-only
    mak-attatch-cli scan ~/Videos --embed-metadata --skip-existing
"""

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import requests

import config
from config import VERSION
from core import attacher, autoattach, deps, parser, scanner, tmdb

# Exceptions these operations can legitimately raise; anything else is a bug
# and should propagate instead of being swallowed.
OPERATION_ERRORS = (
    tmdb.TMDBError,
    requests.RequestException,
    ValueError,
    OSError,
    RuntimeError,
    subprocess.SubprocessError,
)


def _fail(message: str, code: int = 1) -> None:
    print(f"Error: {message}", file=sys.stderr)
    sys.exit(code)


def _require_api_key() -> None:
    if not config.get("tmdb_api_key"):
        _fail(
            "No TMDB API key configured.\n"
            "Set one via: mak-attatch (GUI) or mak-attatch-tui (TUI)\n"
            "Or edit: ~/.config/mak-attatch/config.json"
        )


def _check_tools() -> None:
    missing = attacher.check_tools()
    if missing:
        _fail(f"Missing required tools: {', '.join(missing)}. {deps.hint(missing)}")


def _resolve_match(search: str | None, filepath: str) -> dict:
    if search:
        query, year = search, ""
    else:
        parsed = parser.parse_filename(filepath)
        query, year = parser.build_search_query(parsed), parsed.get("year", "")
    try:
        results = tmdb.search(query, "multi")
    except OPERATION_ERRORS as e:
        _fail(f"TMDB search failed for {query!r}: {e}")
    match = autoattach._best_match(results, year)
    if match is None:
        _fail(f"No TMDB match found for {query!r}")
    return match


def _download_first_poster(match: dict) -> str:
    try:
        posters = tmdb.get_posters(match["id"], match["media_type"])
    except OPERATION_ERRORS as e:
        _fail(f"Failed to fetch posters: {e}")
    if not posters:
        _fail(f"No posters available for {match['title']}")
    url = posters[0].get("url") or posters[0].get("thumb_url")
    if not url:
        _fail(f"Poster for {match['title']} has no image URL")
    fd, poster_path = tempfile.mkstemp(suffix=".jpg")
    os.close(fd)
    os.chmod(poster_path, 0o600)
    try:
        tmdb.download_image(url, poster_path)
    except OPERATION_ERRORS as e:
        try:
            os.unlink(poster_path)
        except OSError:
            pass
        _fail(f"Failed to download poster: {e}")
    return poster_path


def _scrape_metadata(match: dict) -> dict:
    try:
        return tmdb.get_details(match["id"], match["media_type"])
    except OPERATION_ERRORS as e:
        _fail(f"Failed to scrape metadata: {e}")


def _cmd_attach(args) -> None:
    # Attaching a local poster without metadata never touches TMDB, so it must
    # not require an API key.
    if args.search or args.embed_metadata:
        _require_api_key()
    _check_tools()

    files = [os.path.expanduser(f) for f in args.file]
    local_poster = os.path.expanduser(args.poster) if args.poster else None

    if args.dry_run:
        for filepath in files:
            print(f"[dry-run] Would attach poster to {filepath}")
        return

    own_posters: list[str] = []
    ok = fail = 0
    first_error = None

    def attach(filepath: str, poster_path: str, metadata: dict | None) -> None:
        nonlocal ok, fail, first_error
        try:
            out = attacher.full_attach(
                filepath, poster_path, metadata=metadata, to_mkv=args.to_mkv
            )
            if out != filepath:
                print(f"{filepath} -> {out}")
            ok += 1
        except OPERATION_ERRORS as e:
            fail += 1
            if first_error is None:
                first_error = f"{Path(filepath).name}: {e}"

    try:
        if args.search:
            # An explicit query names one title, so it applies to the batch.
            match = _resolve_match(args.search, files[0])
            metadata = _scrape_metadata(match) if args.embed_metadata else None
            poster_path = local_poster or _download_first_poster(match)
            if not local_poster:
                own_posters.append(poster_path)
            for filepath in files:
                attach(filepath, poster_path, metadata)
        else:
            # No explicit source: resolve each file on its own so a batch of
            # different titles does not inherit the first file's poster/metadata.
            for filepath in files:
                match = None
                if local_poster is None or args.embed_metadata:
                    match = _resolve_match(None, filepath)
                poster_path = local_poster
                if poster_path is None:
                    poster_path = _download_first_poster(match)
                    own_posters.append(poster_path)
                metadata = _scrape_metadata(match) if args.embed_metadata else None
                attach(filepath, poster_path, metadata)

        if fail:
            _fail(f"Attached {ok}, failed {fail} — {first_error}")
        print(f"Attached poster to {ok} file(s)")
    finally:
        for path in own_posters:
            try:
                os.unlink(path)
            except OSError:
                pass


def _cmd_remove(args) -> None:
    _check_tools()
    if args.poster_only and args.metadata_only:
        _fail("--poster-only and --metadata-only are mutually exclusive")
    files = [os.path.expanduser(f) for f in args.file]
    if args.dry_run:
        what = "metadata" if args.metadata_only else "poster"
        for filepath in files:
            print(f"[dry-run] Would remove {what} from {filepath}")
        return
    fail = 0
    first_error = None
    for filepath in files:
        try:
            if args.metadata_only:
                attacher.remove_metadata(filepath)
                print(f"Removed metadata from {filepath}")
            else:
                attacher.remove_poster(filepath)
                print(f"Removed poster from {filepath}")
        except OPERATION_ERRORS as e:
            fail += 1
            if first_error is None:
                first_error = f"{Path(filepath).name}: {e}"
    if fail:
        _fail(f"Removed from {len(files) - fail} file(s), failed {fail} — {first_error}")


def _cmd_scan(args) -> None:
    _require_api_key()
    _check_tools()
    root = os.path.expanduser(args.directory)
    if not os.path.isdir(root):
        _fail(f"Not a directory: {root}")

    files = scanner.iter_video_files(root)
    if not files:
        print(f"No video files found in {root}")
        return

    groups = scanner.classify(files)

    def resolve_progress(current, total, group):
        print(f"Resolving {current}/{total}: {group.title}")

    delay = config.get("scan_api_delay") or 0.25
    resolved = autoattach.resolve_groups(groups, api_delay=delay, progress=resolve_progress)
    ok = sum(1 for e in resolved if e["status"] == "ok")

    if args.dry_run:
        for entry in resolved:
            group = entry["group"]
            match = entry.get("match")
            if entry["status"] == "ok" and match:
                print(f"[dry-run] {group.title} -> {match['title']} "
                      f"({match.get('year') or '?'}) [{match['media_type']}]")
            else:
                print(f"[dry-run] {group.title} -> no match")
        print(f"[dry-run] {ok} of {len(resolved)} group(s) matched; nothing attached")
        return

    if ok == 0:
        _fail("No groups matched on TMDB")

    def attach_progress(done, total, filepath, status):
        print(f"Attaching {done}/{total}: {Path(filepath).name} [{status}]")

    summary = autoattach.attach_groups(
        resolved,
        skip_existing=args.skip_existing,
        scrape_metadata=args.embed_metadata,
        api_delay=delay,
        to_mkv=args.to_mkv,
        progress=attach_progress,
    )
    print(
        f"Auto-attach complete: {summary['ok']} ok, "
        f"{summary['skipped']} skipped, {summary['fail']} failed"
    )
    for err in summary["errors"][:10]:
        print(f"  - {err}", file=sys.stderr)
    if summary["fail"]:
        sys.exit(1)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="mak-attatch-cli",
        description="Attach TMDB cover art posters to video files (headless).",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    sub = parser.add_subparsers(dest="command", required=True)

    attach = sub.add_parser("attach", help="attach a poster to one or more videos")
    attach.add_argument("-f", "--file", action="append", required=True,
                        help="video file(s) to attach to")
    source = attach.add_mutually_exclusive_group()
    source.add_argument("-s", "--search", help="TMDB search query")
    source.add_argument("-p", "--poster", help="local poster image to attach")
    attach.add_argument("--embed-metadata", action="store_true",
                        help="scrape TMDB metadata and embed it with the poster")
    attach.add_argument("--to-mkv", action="store_true",
                        help="remux non-MKV sources to MKV before attaching")
    attach.add_argument("--dry-run", action="store_true",
                        help="show what would be attached without changing files")
    attach.set_defaults(func=_cmd_attach)

    remove = sub.add_parser("remove", help="remove posters and/or metadata")
    remove.add_argument("-f", "--file", action="append", required=True,
                        help="video file(s) to remove from")
    remove.add_argument("--poster-only", action="store_true",
                        help="remove only the attached poster (default)")
    remove.add_argument("--metadata-only", action="store_true",
                        help="remove only the embedded metadata")
    remove.add_argument("--dry-run", action="store_true",
                        help="show what would be removed without changing files")
    remove.set_defaults(func=_cmd_remove)

    scan = sub.add_parser("scan", help="scan a folder and auto-attach posters")
    scan.add_argument("directory", help="folder containing video files")
    scan.add_argument("--embed-metadata", action="store_true",
                      help="scrape and embed metadata during attachment")
    scan.add_argument("--to-mkv", action="store_true",
                      help="remux non-MKV sources to MKV before attaching")
    scan.add_argument("--skip-existing", action="store_true",
                      help="skip files that already have a poster")
    scan.add_argument("--dry-run", action="store_true",
                      help="resolve matches and preview them without attaching")
    scan.set_defaults(func=_cmd_scan)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
