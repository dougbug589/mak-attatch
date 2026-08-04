# Changelog

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
