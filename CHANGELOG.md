# Changelog

## v1.1.3

### Fixed

- **MP4 posters are now written to the `covr` metadata atom** (in addition to the attached-picture stream) when attaching, and stripped when removing — so cover-aware players and tools (VLC, mpv, taglib readers) always show the current poster
- **Convert MP4 to MKV no longer orphans the original file**: the poster is attached in place to the original MP4 first, then the lossless remux runs — both the new MKV and the original MP4 keep the poster

### Changed

- README install/uninstall now documents the proper Arch commands (`makepkg -si` from a clone, `sudo pacman -U`, uninstall via `sudo pacman -Rns mak-attatch`) instead of the Makefile dev flow
- README explains why MP4 cover art can be invisible in some file managers (video-frame thumbnails) and how to verify it (`ffprobe -show_streams`, VLC, mpv)

## v1.1.2

### Changed

- `scan_skip_existing` now defaults to `False` — folder scans overwrite an existing poster instead of skipping the file. Restore the old behavior with Settings → "Skip files that already have a poster"

## v1.1.1

### Documentation

- **Poster lifecycle doc** (`docs/poster-lifecycle.md`) — describes how posters are fetched, staged in `/tmp`, embedded into video files and cleaned up after use, plus the crash-orphan limitation
- README now links to the poster lifecycle doc from the "How it works per format" section

## v1.1.0

### New Features

- **Recursive folder scan** (`scanner.py`) — walk a directory, classify video files into groups by title/season, auto-resolve via TMDB
- **Auto-attach workflow** (`autoattach.py`) — scan → review matches → attach posters in bulk from the TUI
- **Lossless MP4→MKV remux** — optional auto-convert or one-click Convert button; keeps original MP4, no re-encoding
- **Scan review screen** — full-screen modal with per-season selection, status indicators, and bulk attach/cancel
- **Poster picker screen** — full-screen modal with TMDB poster list, resolution/language info, chafa preview
- **Metadata embedding** — title, overview, genres, cast tags written into video file tags
- **GUI Convert to MKV button** — lossless remux from the Qt interface
- **GUI Scan Review dialog** — full scan workflow with progress, review, and bulk operations
- **Batch metadata removal** — strip embedded metadata from selected files
- **Batch poster removal** — strip poster art from selected files
- **yazi file browser integration** — multi-select files in the TUI via yazi
- **Local image picker** — use any JPEG/PNG as a poster via yazi

### Improvements

- TUI full-screen modals for review and poster selection (was cramped dialog)
- Per-season toggle selection in scan review (checkbox-style ●/○ indicators)
- Shortened button labels for compact layout (Attach, Convert, Rm Meta, Scrape, etc.)
- Buttons docked to bottom for easier navigation
- Checkbox auto-height in review options
- Poster info displayed in preview panel on row highlight
- `sys.path` fix for running TUI directly (`python3 poster_tui/app.py`)

### Bug Fixes

- Fixed `ModuleNotFoundError: No module named 'config'` when running TUI directly
- Fixed `update_cell_at` not visually refreshing in DataTable after cell updates

### Config

- New `convert_to_mkv` setting (default `False`) — persists auto-convert toggle
- New `scan_skip_existing` setting (default `True`) — skip files that already have a poster
- New `scan_api_delay` setting (default `0.25`) — delay between TMDB API lookups during scan

### Tests

- 68 tests passing (attacher, autoattach, scanner, tmdb)
- Bandit security scan clean

---

## v1.0.5

- CI bumps (actions/checkout@7, actions/setup-python@7)
- README polish and showcase videos

## v1.0.4

- README redesign with themed layout and collapsible sections

## v1.0.3

- Badge and documentation updates

## v1.0.2

- Initial AUR release

## v1.0.1

- Bug fixes and improvements

## v1.0.0

- Initial release — TMDB search, poster preview, batch attach, MKV native / MP4+MOV via ffmpeg
