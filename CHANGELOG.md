# Changelog

## v1.4.0 — 2026-11-13

### Changed — packaging (read before upgrading)

- **All code now lives in the `mak_attatch` package.** pip used to install generic top-level modules (`config`, `cli`, `main`, `core`, `ui`), which could overwrite or shadow other packages. The commands are unchanged: `mak-attatch`, `mak-attatch-cli`, and the new **`mak-attatch-tui`** entry point. `python main.py` / `cli.py` / `poster-tui` still work from a checkout. A plain `pip install` without the `[gui]`/`[tui]` extras now prints an install hint instead of crashing.
- **Scans keep existing posters by default** (`--no-skip-existing` in the CLI, or the setting in the GUI/TUI, replaces them). A saved config that sets `scan_skip_existing` keeps its value.
- `setup.sh` installs only the required tools. The TUI extras (yazi, chafa) are opt-in with `--with-tui`, so GUI/CLI users no longer get a third-party apt repository. Adding the yazi repository now checks the keyring download and runs `apt-get update`.
- **Windows support removed:** `setup.ps1`, the Windows CI job and the Windows PATH workaround are gone. mak-attatch targets Linux (and macOS via `setup.sh`).
- `convert.sh` is now an interactive wrapper around `mak-attatch-cli`. Removing a poster no longer creates an MKV copy, and upper-case extensions work.
- Makefile and PKGBUILD: square 256×256 icon in the hicolor theme, `arch=any`, LICENSE installed, bytecode precompiled, a `check()` that runs the tests, and quoted paths.
- CI: read-only token, actions pinned by commit, pinned requirements tested, a wheel build/install smoke test, shellcheck, and bandit over the whole package.
- SECURITY.md links to GitHub private vulnerability reporting.

### Fixed — matching

- **Batch scans no longer attach an unrelated title's poster.** A TMDB result is used only when its title (or original title) actually resembles the file's title; otherwise the group shows as unmatched for review, with the closest candidate named. The same applies to per-file auto lookups in the CLI and to Scrape.
- Extras are skipped: `Featurettes`, `Behind The Scenes`, `Deleted Scenes`, `Interviews`, `Trailers`, `Sample(s)`, `Extras` and `Bonus` folders, plus `-trailer`/`-sample`-style files.
- `Show/Season 1/S01E01 - Pilot.mkv` groups under the show folder instead of becoming a show called "Pilot". `Specials`/`Downloads` folders are no longer taken as show names, and folder names keep their dots (`The.Matrix.1999`).
- CLI: an unmatched file in a multi-file `attach` is reported and skipped instead of aborting the batch. When nothing matches, `scan` says why (e.g. a rejected API key). An API delay of 0 is respected.
- Cancelling an auto-attach stops the whole run, not just the current group.
- `check_tools()` also requires `ffprobe` and `mkvmerge`, which were already used.

### Fixed — robustness

- MP4 rewrites keep the "fast start" layout (index before media), so web/DLNA progressive playback keeps working.
- Read-only files are refused instead of being silently replaced. Remuxing a symlinked library entry puts the MKV next to the link, not next to its target.
- Control characters in TMDB text no longer break mkvpropedit's tags file or ffmpeg's arguments.
- "Already has a poster" means a `cover.*` attachment, matching what attach/remove manage. mkvmerge warnings no longer count as "no poster".
- TMDB: posters without dimensions and crew without names no longer crash a batch. A rejected or oversized download leaves no partial file. "Wonder Woman 1984"-style titles are retried without treating the number as a year.
- Config: an unreadable `config.json` is moved aside as `config.json.bad-<timestamp>` instead of being overwritten (which lost the API key). `"false"`/`"0"` strings read as false.
- `--dry-run` reports missing or unsupported files instead of promising success.
- Multi-episode files (`S01E01E02`) no longer crash the parser.
- After an auto-attach that remuxed files, both UIs list the new `.mkv` paths.

### Fixed — GUI and TUI responsiveness and correctness

- Poster check marks are computed in the background instead of freezing the file list.
- Thumbnails load on a shared pool of 6 threads (was one thread per poster, often 100–300 at once). Previews are size-limited and closing a preview or poster dialog no longer waits for the download.
- Clicking search results quickly can no longer show one title's posters while another is selected. A newer search supersedes an older one.
- Loading a new set of files forgets the previous title's poster and metadata.
- TUI: names and titles that look like markup (`[SubsPlease] …`) are shown literally and can no longer crash the file list or the scan review. Leaving yazi open no longer kills it after 5 minutes, and non-UTF-8 file names are accepted.
- An API key from `MAK_ATTATCH_TMDB_API_KEY` is no longer written to disk by the settings dialogs.
- GUI: a portal file dialog that never answered no longer blocks every Browse button. Status text is shown as plain text, never as HTML.

### Fixed — hardlinks, cancel and close

- **Hardlinked MKVs** (torrent client + media manager setups) are edited as a private copy and swapped in, so the seeding file is never modified.
- **GUI:** a Cancel button (and Esc) stops the running batch after the current file. Closing the window during an operation asks first, then cancels and finishes the current file, instead of freezing until the whole batch is done.

### Fixed — data safety

- **TUI deleted the user's own image**: picking a poster with "Local Image" previewed the file and then deleted it. Only temp files downloaded for a preview are removed now.
- **MP4/MOV metadata wiped stream metadata**: writing or removing metadata used `-map_metadata -1`, which also cleared per-stream and per-chapter metadata. Audio and subtitle languages became `und`, and track names and chapter titles were lost. Only global tags are reset now (`-map_metadata:g -1`).
- **MOV/M4V metadata editing failed**: writing or removing metadata on `.mov` and `.m4v` used ffmpeg's MOV/iPod muxers, which fail or drop the cover. All MP4-family rewrites now use the MP4 muxer and keep the source brand.
- **TV metadata overwrote episode titles**: show-level TMDB details replaced every episode's own title and synopsis. Series data is now written at show level: Matroska collection tags (`TargetTypeValue 70`) and the MP4 `show` atom. The episode's title, date and description are left alone.
- **Rewrites are verified before replacing the original**: MP4/MOV/M4V rewrites check stream count and duration, fsync the new file, use hidden non-video temp names, scale their timeout with file size, and check free space first. A truncated ffmpeg output can no longer replace the original.
- **mkvpropedit**: exit code 1 (warnings, changes written) is no longer reported as a failure. Errors now show mkvpropedit's own message. The kill timeout for in-place edits is 600 s.
- **`--to-mkv` rescans** no longer fully rewrite the MP4 before discovering the `.mkv` already exists.
- **Remove metadata (MKV)** keeps mkvmerge's per-track statistics tags.

### Fixed — safety in the GUI and TUI

- **GUI Ctrl+A attached the poster to every file**: Attach is now Ctrl+Return. Ctrl+O and Ctrl+F work again; they were registered twice and Qt ignored both.
- **One write operation at a time** in both GUI and TUI. Two batches can no longer edit the same files concurrently.
- **Actions on all files need explicit confirmation** when nothing is selected. The TUI now confirms Remove, Rm Meta and Scrape.
- **GUI selection survives list refreshes**: a background job finishing no longer turns "attach to 3 selected files" into "attach to all".
- **GUI poster removal runs in the background** instead of freezing the window.
- **GUI no longer aborts on unexpected errors**: an invalid API key or a slot exception shows a dialog instead.
- **TUI batch Scrape** resolves each file itself instead of writing one title's metadata to every file. After Convert, the selection follows the new `.mkv` files.

### Security

- **TMDB API key no longer appears in error messages**: network and HTTP errors used to include the request URL, which contains `?api_key=`. The CLI, GUI and TUI showed it verbatim.

### Other

- File names containing `...` (`Tick, Tick... Boom! (2021).mkv`) or starting with `-` are no longer rejected. Every tool receives an absolute path.
- `.m4v` is tagged in place like MP4 instead of being remuxed to MKV.
- TMDB: HTTP 429 is retried (honouring `Retry-After`, capped at 10 s), and same-host redirects keep the v3 key.
- Tests: a misplaced skip decorator hid about 60 tests on machines without ffmpeg or mkvtoolnix. 66 new regression tests; full suite 215 passed.

## v1.3.5 — 2026-10-20

### Fixed

- **Poster cache invalidation**: `clear_poster_cache()` now resolves paths the same way `has_poster()` does. Cache entries are correctly dropped for relative, symlinked, or non-normalized paths (including Windows), so an added or removed poster is picked up immediately.
- **CI**: fixed the gui-tui runner's stale Microsoft apt source, made the Windows smoke tests platform-aware, and isolated the TUI selection tests from the developer's local TMDB key.

### Tests

- Full suite: 151 passed on Linux and on Python 3.12.

## v1.3.4 — 2026-10-20

### Fixed

- **MOV poster attach**: ffmpeg's `mov` muxer silently discards `attached_pic`/`covr`, so attaching a poster to a `.mov` reported success but left the file unchanged. MOV output now uses the MP4 muxer with the source major brand (for example `qt  ` or `mp42`), and removal uses the same path so the brand survives.
- **Tests**: added MOV cover regression coverage (attach, reattach, remove, brand preservation). 151 total.

## v1.3.3 — 2026-10-19

### Fixed

- **MKV remux (`--to-mkv`)**: streams are copied with `-map 0` instead of dropping subtitles and extra audio; output is published atomically, so a failed ffmpeg run no longer leaves a partial `.mkv`.
- **MP4/MOV poster attach**: existing metadata is preserved (only `covr` is replaced) and poster updates are transactional.
- **MKV cover replacement**: only `cover.*` attachments are removed; other attachments (fonts, subtitles) are kept.
- **Numeric titles**: `1917.mkv` / `2012.mkv` are no longer mistaken for release years; `Blade Runner 2049` and `2001: A Space Odyssey` stay intact.
- **Scanner grouping**: movies with the same title and different years (`Dune` 1984/2021, `The Thing` 1982/2011) are separate groups.
- **TMDB search**: trailing years are split only when explicit, TV searches use `first_air_date_year`, and multi-search results are filtered by year.
- **CLI**: a local poster (`-p`) no longer needs an API key; `~` paths are expanded; batches without `-s` resolve each file independently; `--dry-run` added to `attach`, `remove`, and `scan`.
- **GUI/TUI**: poster download, metadata scraping/removal, and single-file attach run off the main thread; batch metadata no longer reuses the first file's match; poster-grid selection works; the TUI preview temp file no longer races its cleanup; “Skip unmatched” is honored.
- **`convert.sh`**: transactional remux with ffmpeg failure checks, correct MIME types, and accurate add/remove reporting.
- **Config**: version now matches the release, values are validated/clamped, and `MAK_ATTATCH_TMDB_API_KEY` overrides the on-disk key.

### Improved

- **Packaging**: `pyproject.toml` now has PEP 621 metadata, so `pip install .` works; Makefile launchers prefer an installed venv.
- **CI**: added GUI/TUI (offscreen) and Windows smoke jobs.
- **README**: corrected TUI shortcuts and test count, and added the required TMDB attribution.
- **Tests**: 150 total.

## v1.3.2 — 2026-08-14

### Fixed

- **Fedora/EL installs of yazi failed**: `sudo dnf install -y ffmpeg mkvtoolnix chafa yazi curl` errored with `No match for argument: yazi` because yazi is only in the `lihaohong/yazi` COPR. setup.sh now enables that COPR first (via new `core/deps.py --yazi-copr`), both in print mode and `--auto-install`.
- **README "From Source"**: now documents running the app via the venv Python (`.venv/bin/python ...` or activating the venv), since `./main.py`'s `#!/usr/bin/env python3` shebang resolves to system Python and fails with `ModuleNotFoundError: No module named 'PyQt6'` on distros that don't use the venv by default.

### Improved

- **core/deps.py**: Added `yazi_copr_commands()` (dnf mirror of the apt keyring step) and included it in the runtime `hint()` so the TUI/GUI/CLI dependency gate also mentions the COPR step on Fedora/EL.
- **tests/test_deps.py**: +3 tests (117 total) for the COPR commands, hint output, and CLI flag.

## v1.3.1 — 2026-08-13

### Improved

- **setup.sh**: Distro-aware dependency detection (apt/pacman/dnf) with per-distro install commands. Prints commands by default; `--auto-install` opts into running them.
- **core/deps.py**: Shared helper used by setup.sh and the runtime gates for consistent, distro-specific "missing dependency" messages (including the yazi apt-repo keyring step on Debian/Ubuntu).
- **poster_tui/app.py**: Terminal poster preview now probes sixel/kitty capability (DEC DA1) and falls back gracefully, so posters render on any terminal.

### Fixed

- **README**: Updated changelog through v1.3.1, corrected test count (114), documented `mak-attatch-cli`.

## v1.3.0 — 2026-08-13

### Added

- **cli.py**: Headless Qt-free CLI (`mak-attatch-cli`) with `attach`, `remove`, and `scan` subcommands. Shares the `core/` pipeline with the GUI and TUI, so it works in scripts, cron jobs, and file-manager actions. New `mak-attatch-cli` binary wired into the Makefile and PKGBUILD.
  - `attach -f FILE [-s QUERY | -p IMAGE] [--embed-metadata] [--to-mkv]` — attach a poster by TMDB search or from a local image (search query is derived from the filename when neither is given).
  - `remove -f FILE [--poster-only | --metadata-only]` — remove the attached poster (default) or embedded metadata.
  - `scan DIR [--skip-existing] [--embed-metadata] [--to-mkv]` — scan a folder, resolve titles against TMDB, and auto-attach posters with live progress.
  - Missing TMDB API key is a hard-fail with a clear "how to set it" message; missing ffmpeg/mkvtoolnix fail up front via `check_tools()`.
- **tests/test_cli.py**: 19 tests covering argument dispatch, attach-by-search/local-poster, temp-poster cleanup, metadata scraping, error paths, and the scan pipeline.

## v1.2.0 — 2026-08-13

### Added

- **core/scanner.py**: mtime-keyed session cache for `has_poster()`. Repeat lookups across consecutive batch attach runs skip ffprobe/mkvmerge; modified or re-attached files self-invalidate via their stat key.
- **.github/workflows/ci.yml**: CI now runs pytest (Python 3.10–3.13) plus a dedicated ruff job (E/F/I + BLE001/S110) on every push and PR.

### Fixed

- **core/** and **poster_tui/app.py**: Replaced broad `except Exception` with specific exception types (`TMDBError`, `RequestException`, `ValueError`, `OSError`, `SubprocessError`, `RuntimeError`). Unexpected errors now propagate instead of being silently swallowed. Temp-file cleanup in `core/attacher.py` rewritten as `try/finally` so it also runs on unexpected exceptions.
- **poster_tui/app.py**: Fixed latent late-binding bugs where the `except` variable was referenced inside deferred lambdas.
- **ui/main_window.py** and **ui/poster_grid.py**: All 16 broad `except Exception` sites narrowed to a shared `OPERATION_ERRORS` tuple; worker boundaries and per-file loops keep catching legitimate operation errors.

### Improved

- **ui/**: Removed the ruff exclusion for `ui/` and fixed the lint debt it had been hiding (unused imports, import sorting, over-long lines, an empty f-string, an unused local). Extracted shared `VIDEO_FILTER`/`IMAGE_FILTER` dialog filter constants.
- **ui/main_window.py** and **ui/poster_grid.py**: Unbounded thread waits on dialog/application shutdown so in-flight workers are never killed mid-write; the file list context menu now removes multiple selected files at once.

## v1.1.6 — 2026-08-12

### Fixed

- **core/tmdb.py**: Authorization header stripped on same-host redirects. Now only stripped when a redirect crosses hosts.
- **core/attacher.py**: `_find_attached_pic` now logs validation errors to stderr instead of silently returning `None`.
- **core/tmdb.py**: `download_image()` now verifies magic bytes after download, rejecting non-image files.
- **core/autoattach.py**: Error list now bounded to 20 entries during accumulation, preventing unbounded memory growth on large batches.
- **poster_tui/app.py**: `_preview_native` now logs chafa failures to stderr instead of silently swallowing them. Added `--` separator before the path in the chafa invocation.

### Improved

- **core/tmdb.py**: `download_image()` now retries (up to 2) 5xx responses from the image host, with specific handling for 503 ("TMDB is busy").

## v1.1.5

### Fixed

- **TMDB redirect handling crashed with `AttributeError`**: `_fetch()` used `resp.urljoin()` which does not exist on `requests.Response`. Replaced with `urllib.parse.urljoin()`, so a 301/302/307/308 redirect from TMDB's API or image CDN is followed correctly instead of crashing. (Bug introduced in v1.1.2, now resolved.)

### Added

- Regression test for the redirect path in `tests/test_tmdb.py` — mocks a 302 response and verifies the resolved URL is fetched without crashing.

## v1.1.4

### Added

- The app version now shows on the app itself: GUI window title (`mak-attatch v1.1.4`) and TUI header subtitle (`v1.1.4`), sourced from a single `VERSION` constant in `config.py`

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
