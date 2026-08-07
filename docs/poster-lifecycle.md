# Poster lifecycle

This document describes how posters are fetched, staged, attached and cleaned up. It is an internal detail; the README covers the user-facing behaviour ("the art gets embedded *inside* the file").

## Overview

Posters are **never stored persistently** anywhere on disk as standalone files. The full flow is:

1. TMDB is queried for poster metadata (URLs only).
2. The chosen image is downloaded to a **temporary file** in `/tmp`.
3. The image is **embedded inside the video file** (Matroska attachment or MP4 attached picture) via `attacher.full_attach`.
4. The temporary file is **deleted** once attachment is done.

The only persistent copy of the art lives inside the video file itself.

## Where posters are staged

| Path | Location | Notes |
|---|---|---|
| CLI / auto-attach | `core/autoattach.py:93` | `tempfile.mkstemp(suffix=".jpg")`, permissions set to `0o600` (`:95`) |
| TUI poster preview | `poster_tui/app.py:669` | Thumbnail temp file for the native/chafa preview |
| TUI poster detail preview | `poster_tui/app.py:1148` | Full-resolution preview in the poster page |
| TUI attach | `poster_tui/app.py:704` | Full-resolution image used for the actual attachment |

The TUI gallery (`_load_posters`, `app.py:618`) holds **only URLs and metadata in memory** — no images are downloaded until a poster is previewed or attached. No cache directory is ever written.

## Deletion after use

Every download path removes its temporary file in a `finally` block, so cleanup runs even on errors:

| Path | Location |
|---|---|
| CLI / auto-attach | `core/autoattach.py:129` |
| TUI poster preview | `poster_tui/app.py:680` |
| TUI poster detail preview | `poster_tui/app.py:1162` |
| TUI attach | `poster_tui/app.py:758` |

## What is NOT deleted

- **User-selected local posters** — when the user picks their own image file (JPEG/PNG), `local_poster_path` is used directly and is never removed (`app.py:756` skips unlink when the path matches `local_poster_path`).
- **Local images passed to the CLI / batch flow** with `cleanup_poster=False` are kept.

## Security

- Temporary files are written with `0o600` permissions (owner-only) so poster images aren't world-readable in `/tmp`.
- Downloads are validated before writing: content type must be a known image type and size is capped (`core/tmdb.py:190`).

## Known limitation

If the process is killed hard (`SIGKILL`, power loss) between the download and the `finally` cleanup, a stray `0o600` `.jpg` can be left in `/tmp`. There is no startup sweep to remove these; the OS clears `/tmp` on reboot, so the impact is minimal.
