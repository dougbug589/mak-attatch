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
from core import attacher, autoattach, parser, scanner, tmdb

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
        _fail(f"Missing required tools: {', '.join(missing)}")


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


def _cmd_attach(args) -> None:
    _require_api_key()
    _check_tools()

    metadata = None
    poster_path = None
    own_poster = False
    try:
        if args.poster:
            poster_path = args.poster
            if args.embed_metadata:
                match = _resolve_match(None, args.file[0])
                try:
                    metadata = tmdb.get_details(match["id"], match["media_type"])
                except OPERATION_ERRORS as e:
                    _fail(f"Failed to scrape metadata: {e}")
        else:
            match = _resolve_match(args.search, args.file[0])
            if args.embed_metadata:
                try:
                    metadata = tmdb.get_details(match["id"], match["media_type"])
                except OPERATION_ERRORS as e:
                    _fail(f"Failed to scrape metadata: {e}")
            poster_path = _download_first_poster(match)
            own_poster = True

        ok = fail = 0
        first_error = None
        for filepath in args.file:
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
        if fail:
            _fail(f"Attached {ok}, failed {fail} — {first_error}")
        print(f"Attached poster to {ok} file(s)")
    finally:
        if own_poster and poster_path:
            try:
                os.unlink(poster_path)
            except OSError:
                pass


def _cmd_remove(args) -> None:
    _check_tools()
    if args.poster_only and args.metadata_only:
        _fail("--poster-only and --metadata-only are mutually exclusive")
    fail = 0
    first_error = None
    for filepath in args.file:
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
        _fail(f"Removed from {len(args.file) - fail} file(s), failed {fail} — {first_error}")


def _cmd_scan(args) -> None:
    _require_api_key()
    _check_tools()
    root = args.directory
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
    attach.set_defaults(func=_cmd_attach)

    remove = sub.add_parser("remove", help="remove posters and/or metadata")
    remove.add_argument("-f", "--file", action="append", required=True,
                        help="video file(s) to remove from")
    remove.add_argument("--poster-only", action="store_true",
                        help="remove only the attached poster (default)")
    remove.add_argument("--metadata-only", action="store_true",
                        help="remove only the embedded metadata")
    remove.set_defaults(func=_cmd_remove)

    scan = sub.add_parser("scan", help="scan a folder and auto-attach posters")
    scan.add_argument("directory", help="folder containing video files")
    scan.add_argument("--embed-metadata", action="store_true",
                      help="scrape and embed metadata during attachment")
    scan.add_argument("--to-mkv", action="store_true",
                      help="remux non-MKV sources to MKV before attaching")
    scan.add_argument("--skip-existing", action="store_true",
                      help="skip files that already have a poster")
    scan.set_defaults(func=_cmd_scan)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
