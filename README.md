# mak-attatch

> Embed TMDB movie & TV cover art directly into your video files.
> Search, preview, attach — the poster lives *inside* the file.

[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![AUR](https://img.shields.io/badge/AUR-mak--attatch-1793D1?logo=arch-linux)](https://aur.archlinux.org/packages/mak-attatch)
[![Release](https://img.shields.io/github/v/release/dougbug589/mak-attatch)](https://github.com/dougbug589/mak-attatch/releases)

**mak-attatch** fetches high-quality poster art from [The Movie Database](https://www.themoviedb.org) and embeds it into your MKV, MP4, MOV and M4V files. The art travels with the video — no external scrapers, no network dependency, no server required.

**Three interfaces:** a **PyQt6 desktop GUI**, a keyboard-driven **Textual TUI** for terminals and SSH sessions, and a headless **CLI** for scripts. Linux (and macOS from source); Windows is not supported.

---

## Table of Contents

- [Features](#features)
- [Showcase](#showcase)
- [Installation](#installation)
- [Usage](#usage)
- [Keyboard Shortcuts](#keyboard-shortcuts)
- [How It Works](#how-it-works)
- [Troubleshooting](#troubleshooting)
- [Requirements](#requirements)
- [Project Structure](#project-structure)
- [Changelog](#changelog)
- [Standalone Utility](#standalone-utility)
- [API Key](#api-key)
- [License](#license)

---

## Features

| Feature | Description |
|---------|-------------|
| **TMDB Search** | Search movies and TV shows with full poster browsing |
| **Poster Preview** | Full-resolution preview before committing |
| **Smart Filename Parsing** | Auto-detects title, year, season and episode from filenames (via `guessit`) |
| **Batch Processing** | Attach one poster to many files, or scan an entire folder |
| **Recursive Folder Scan** | Walks directories, skips extras, groups by series & season, matches titles on TMDB |
| **Title Matching** | A TMDB result is used only when its title actually matches; anything else is left for you to review |
| **Metadata Embedding** | Writes title, overview, genres, rating, cast into file tags; TV details go in at show level, so each episode keeps its own title |
| **Local Images** | Use any JPEG, PNG, WebP, GIF, BMP or TIFF image as the poster |
| **Format Safe** | MKV stays MKV; MP4/MOV/M4V keep their container (optional lossless MKV remux) |
| **Safe Rewrites** | Edited files are verified before they replace the original; audio/subtitle languages and chapters are kept; hardlinked (seeding) files are never modified |
| **Batch Remove** | Strip posters or metadata from many files at once |
| **Offline Ready** | Once attached, the art is self-contained in the file |

**Supported formats:**
- **MKV** — native attachment via `mkvpropedit`
- **MP4 / MOV / M4V** — embedded `attached_pic` stream + `covr` metadata atom
- **Other formats** (AVI, WebM, …) — losslessly remuxed to a new MKV first; the original is kept

---

## Showcase

### Desktop GUI (PyQt6)





https://github.com/user-attachments/assets/1d7819d9-0271-4886-a8a8-144f8a7a2022


<img width="1920" height="1080" alt="Screenshot_20260815_095708" src="https://github.com/user-attachments/assets/2b121fc0-0a8c-40db-8392-0fb8c7e21e81" />
<img width="1920" height="1080" alt="ubuntu-desktop" src="https://github.com/user-attachments/assets/cc9b8919-a312-45d2-b5d1-e652f2bfd47f" />




### Terminal TUI (Textual)





https://github.com/user-attachments/assets/2920ddbc-59d9-48b2-803f-708c774cf4ca


<img width="1920" height="1080" alt="ubuntu-tui" src="https://github.com/user-attachments/assets/222d006c-21bf-4758-aade-b7efb35c0f5f" />
<img width="1920" height="1080" alt="Screenshot_20260815_100100" src="https://github.com/user-attachments/assets/47e6f5b2-8da1-43d9-85c2-ed4b9500a860" />




---

## Installation

### Arch Linux (AUR) — Recommended

```bash
yay -S mak-attatch
```

Or build manually:

```bash
git clone https://aur.archlinux.org/mak-attatch.git
cd mak-attatch
makepkg -si            # add --nocheck to skip the test suite during the build
```

This installs `/usr/bin/mak-attatch` (GUI), `/usr/bin/mak-attatch-tui`, `/usr/bin/mak-attatch-cli`, a `.desktop` entry and the icon. The build runs the test suite, which pulls in `python-pytest` and `python-textual` as build-only dependencies.

### From Source

```bash
git clone https://github.com/dougbug589/mak-attatch.git
cd mak-attatch
./setup.sh          # creates .venv and installs Python deps
```

`setup.sh` checks for the required tools (ffmpeg, mkvtoolnix) and prints the command to install any that are missing. Add `--auto-install` to run it (asks for sudo) and `--with-tui` to also set up the optional TUI tools (yazi, chafa).

Run the app with the virtual environment's Python:

```bash
# Method 1: explicit venv path (always works)
.venv/bin/python main.py       # GUI
.venv/bin/python poster-tui    # TUI
.venv/bin/python cli.py --help # CLI

# Method 2: activate venv, then use 'python' (not './script')
source .venv/bin/activate
python main.py
python poster-tui
python cli.py --help
```

Do NOT use `./main.py` or `./poster-tui` directly — the shebang (`#!/usr/bin/env python3`) finds the system Python, which lacks the installed dependencies.

To install system-wide from a checkout (launchers in `/usr/local/bin`, a private venv, desktop entry and icon):

```bash
sudo make install
```

### With pip

```bash
git clone https://github.com/dougbug589/mak-attatch.git
pipx install "./mak-attatch[gui,tui]"   # or: pip install "./mak-attatch[gui,tui]"
```

This installs the `mak-attatch`, `mak-attatch-tui` and `mak-attatch-cli` commands. Leave out `gui` or `tui` for a lighter install; the CLI needs neither, and the GUI/TUI commands tell you what to install if their extra is missing. ffmpeg and mkvtoolnix still come from your system packages.

### Uninstall

**AUR install:**

```bash
sudo pacman -Rns mak-attatch   # removes the package and its now-unused dependencies
rm -rf ~/.config/mak-attatch   # your settings and API key (pacman leaves these)
```

**Source install:**

```bash
cd mak-attatch
sudo make uninstall            # only if you ran `sudo make install`
cd .. && rm -rf mak-attatch ~/.config/mak-attatch
```

---

## Usage

### Which files an action applies to

In both the GUI and the TUI, actions apply to the **selected** files. With nothing selected they apply to **all** loaded files, and then mak-attatch asks you to confirm first. Only one file-changing operation runs at a time.

### Desktop GUI

```bash
mak-attatch
```

1. **First launch:** Enter your free TMDB API key (prompted automatically).
2. **Add files:** **Browse Video**, **Browse Multiple**, or drag-and-drop video files.
3. **Search:** The title is filled in from the filename; edit it if needed and hit **Search**.
4. **Pick a poster:** Click a result, browse its posters, click one to preview it, then **Select This Poster**. Or use **Use Local Image**.
5. **Attach:** Hit **Attach Poster**. Tick **Scrape metadata** to embed TMDB metadata too, or **Convert MP4 to MKV** for a lossless remux first.

**Cancel:** While an operation runs, **Cancel** (or `Esc`) stops it after the current file, so no file is left half-written. Closing the window during an operation asks first.

**More menu:** **Remove Metadata** and **Scrape Metadata** (metadata only, no poster). For several files, Scrape looks each file up on its own.

**Folder Scan (Ctrl+F):** Pick a directory. mak-attatch scans it recursively (skipping extras such as featurettes, trailers and samples), groups files by title/season and looks each group up on TMDB. The review list shows the matches; groups whose closest TMDB result doesn't match the title are listed as unmatched. **Choose Poster...** picks a different poster for a group, **Attach All** processes everything, and **Add to List** just loads the files. Options: **Skip unmatched files**, **Embed metadata**, **Convert MP4 to MKV (lossless remux)**. Files that already have a poster are skipped; to replace them, untick **Skip files that already have a poster** in the TUI's Settings, or set `"scan_skip_existing": false` in `~/.config/mak-attatch/config.json`.

### Terminal TUI

```bash
mak-attatch-tui
```

1. **Add files:** **Browse (yazi)**, **Scan Folder**, or paste paths into the path box and press **Add**.
2. **Search:** Type a title, press `Enter` (filled in from the first file's name).
3. **Browse posters:** Arrow keys to navigate, `Enter` to preview (press `Enter` again to return). **Local Image** uses your own picture instead.
4. **Attach:** Press **Attach** (tick **Scrape metadata** to embed metadata too).

Other actions: **Convert** (lossless remux to MKV, keeps originals), **Remove** (posters), **Rm Meta** (metadata), **Scrape** (metadata only). Remove, Rm Meta and Scrape always ask for confirmation (`y`/`n`).

**File browser:** In yazi, multi-select files with `Space` and press `Enter` to load them. yazi is optional; without it, paste paths instead. Image previews use chafa (also optional).

**Folder scan (Ctrl+S):** Scan a directory, review the matches, attach in bulk.

### Command-Line Interface

Qt-free, headless CLI for scripts, cron jobs, and file-manager actions.

```bash
mak-attatch-cli attach -f movie.mkv -s "The Matrix" --embed-metadata
mak-attatch-cli attach -f movie.mkv -p poster.jpg
mak-attatch-cli attach -f "Show S01E01.mkv"           # query derived from filename
mak-attatch-cli attach -f clip.mp4 -p poster.jpg --to-mkv   # remux to MKV first (keeps the MP4)
mak-attatch-cli attach -f a.mkv -f b.mkv --dry-run    # check inputs, change nothing
mak-attatch-cli remove -f movie.mkv                   # remove poster (default)
mak-attatch-cli remove -f movie.mkv --metadata-only   # remove metadata only
mak-attatch-cli scan ~/Videos --embed-metadata
mak-attatch-cli scan ~/Videos --dry-run               # show what would match
mak-attatch-cli scan ~/Videos --no-skip-existing      # also replace existing posters
```

- **Matching:** without `-s`, each file is looked up by its own name, and a TMDB result is only used if its title actually matches. In a multi-file `attach`, a file that can't be matched is reported and skipped without stopping the rest.
- **Scans** skip files that already have a poster (unless `--no-skip-existing`), plus extras: `Featurettes`, `Behind The Scenes`, `Deleted Scenes`, `Interviews`, `Trailers`, `Sample(s)`, `Extras` and `Bonus` folders, and `-trailer`/`-sample` files.
- **API key:** needed for search, metadata scraping and folder scans. Attaching a local poster with `-p` does not need one.
- **Exit codes:** `0` success, `1` if any file failed (or a dry run found a problem), `2` for usage errors. Missing tools (ffmpeg/mkvtoolnix) are reported up front.

---

## Keyboard Shortcuts

### TUI

| Key | Action |
|-----|--------|
| `q` | Quit (asks first while an operation is running) |
| `Ctrl+Tab` / `Ctrl+Shift+Tab` | Cycle panels |
| `Ctrl+L` | Focus Search panel |
| `Ctrl+M` | Focus Posters panel (many terminals send `Enter` for this key) |
| `Ctrl+R` | Focus Files panel |
| `Ctrl+S` | Scan folder & auto-attach |
| `Space` | Toggle file selection |
| `d` | Clear selection |
| `y` / `n` / `Esc` | Answer a confirmation |

### GUI

| Key | Action |
|-----|--------|
| `Ctrl+O` | Browse for a video |
| `Ctrl+F` | Scan folder |
| `Ctrl+Return` | Attach poster |
| `Esc` | Cancel the running operation (after the current file) |

---

## How It Works

### Poster Attachment by Format

| Format | Attach | Remove |
|--------|--------|--------|
| **MKV** | `mkvpropedit` adds a `cover.*` attachment (other attachments are kept) | `mkvpropedit` deletes the `cover.*` attachment |
| **MP4 / MOV / M4V** | `ffmpeg` stream copy adding an `attached_pic` stream + `covr` atom | `ffmpeg` stream copy without the cover stream |
| **Other** (AVI, WebM, …) | Remux to a new MKV (original kept), then attach | — (these formats can't hold a poster) |

**Rewrites are safe:** MP4-family files are rewritten into a hidden temp file next to the original. The result is checked (stream count and duration) and flushed to disk before it atomically replaces the original, so a failed or truncated run never touches your file. Audio/subtitle languages, track names, chapters and the "fast start" layout are kept. Read-only files are refused. A hardlinked MKV (e.g. one a torrent client is seeding) is edited as a copy, so the other link keeps its original bytes.

### Metadata Tags

| Field | MKV (movie) | MP4/MOV (movie) |
|-------|-------------|-----------------|
| Title | segment title + `TITLE` tag | `title` |
| Year | `DATE_RELEASED` | `date` |
| Overview | `SYNOPSIS` | `description` |
| Tagline | `COMMENT` | `comment` |
| Genres | `GENRE` | `genre` |
| Rating | `RATING` | — |
| Cast | `ACTOR` + `CHARACTER` | — |
| Directors / writers | `DIRECTOR` / `WRITTEN_BY` | `author` (directors) |

**TV shows:** TMDB details describe the whole show, not the episode, so they are written at show level. In MKV they go into collection-level tags (`TargetTypeValue 70`) and the segment title is left alone. In MP4 they go into the `show` and `genre` tags, and the episode's own title, date and description are kept.

### Poster Lifecycle

1. **Search** — Query the TMDB API for title matches.
2. **Select** — Pick one of the title's posters (any language or resolution) or a local image.
3. **Download** — The full-resolution image is fetched to a temp file and validated (size limit, image type, magic bytes).
4. **Attach** — Embedded into the video container.
5. **Cleanup** — Downloaded temp files are removed; a local image you chose is never touched.

---

## Troubleshooting

### MP4 covers don't show in my file manager

MP4 cover art is stored as an `attached_pic` video stream plus a `covr` metadata atom. This is fully standards-compliant and works in **VLC**, **mpv**, **iTunes**, and most media players.

However, some file managers (notably **KDE Dolphin** with the `ffmpegthumbnailer` plugin) generate thumbnails from the primary video stream instead of the embedded cover. MKV cover art (a container attachment) does not have this issue.

**Workaround for KDE Dolphin:**
1. Open **Dolphin → Settings → Configure Dolphin → General → Previews**
2. **Uncheck** `Video Files (ffmpegthumbnailer)`
3. **Keep checked** `Video Files (ffmpegthumbs)`
4. Clear cache: `rm -rf ~/.cache/thumbnails/*`
5. Restart Dolphin

Verify your file has the cover embedded:
```bash
ffprobe -show_streams file.mp4 | grep -E "(mjpeg|attached_pic)"
```

### "No TMDB match found" / a scan group shows as unmatched

- Check your API key at [themoviedb.org/settings/api](https://www.themoviedb.org/settings/api). A rejected key is reported as "TMDB rejected the API key (HTTP 401)".
- mak-attatch only uses a result whose title resembles the file's title; the message names the closest result it rejected. Search manually (or use `-s "Exact Title"` in the CLI) to pick it yourself.
- Try simplifying the filename (remove extra tags like `1080p`, `BluRay`, etc.).

### Batch scan groups files wrong

The scanner parses filenames with `guessit` and falls back to folder names for series. If a file is misgrouped:
- Ensure season folders are named clearly (`Season 1`, `S01`, etc.)
- Avoid generic filenames like `episode01.mkv` without a parent folder name
- Episodes named like `S01E01 - Pilot.mkv` are grouped under their show folder (`Show/Season 1/`)

### "… is read-only; not modifying it"

The file (or its permissions) is read-only. mak-attatch doesn't override that; make it writable (`chmod u+w file`) if you want it changed.

### Disk usage went up after tagging a hardlinked file

Editing a hardlinked file splits it into its own copy so the other link (e.g. a seeding torrent) stays byte-identical. MP4 rewrites always create a new file for safety; MKV edits do so only for hardlinked files.

---

## Requirements

| Dependency | Version | Purpose |
|------------|---------|---------|
| Python | 3.10+ | Runtime |
| ffmpeg (incl. `ffprobe`) | latest | MP4/MOV/M4V attach & remove, stream probing, remux |
| mkvtoolnix-cli | latest | `mkvpropedit` / `mkvmerge` for MKV |
| python-pyqt6 | latest | Desktop GUI |
| python-requests | latest | TMDB API client |
| python-guessit | latest | Filename parsing |
| TMDB API key | free | Poster search (prompted on first launch) |

**TUI extras:** `python-textual` (required for the TUI) · `yazi` (file browser, optional) · `chafa` (terminal image preview, optional)

### Install Commands

**Arch:**
```bash
sudo pacman -S python python-pyqt6 python-requests python-guessit ffmpeg mkvtoolnix-cli
sudo pacman -S python-textual yazi chafa  # TUI extras
```

**Debian/Ubuntu:**
```bash
sudo apt install python3 python3-pyqt6 python3-requests python3-guessit ffmpeg mkvtoolnix
sudo apt install python3-textual chafa  # TUI extras
```

yazi is not in the default repos — enable its apt repo first (the keyring is checked before the source is added, so a failed download can't break `apt update`):
```bash
tmp=$(mktemp) && curl -fsSL https://yazi-rs.github.io/builds/yazi-keyring.gpg -o "$tmp" && test -s "$tmp" \
  && sudo install -m 644 "$tmp" /usr/share/keyrings/yazi-keyring.gpg && rm -f "$tmp"
echo 'deb [signed-by=/usr/share/keyrings/yazi-keyring.gpg] https://yazi-rs.github.io/builds/ stable main' | sudo tee /etc/apt/sources.list.d/yazi.list >/dev/null
sudo apt update && sudo apt install yazi
```

**Fedora:**
```bash
sudo dnf copr enable -y lihaohong/yazi   # yazi is not in the default repos
sudo dnf install python3 python3-pyqt6 python3-requests python3-guessit ffmpeg mkvtoolnix
sudo dnf install python3-textual chafa yazi  # TUI extras
```

---

## Project Structure

```
mak-attatch/
├── mak_attatch/             # The application package (all code lives here)
│   ├── main.py              # Desktop GUI entry point (mak-attatch)
│   ├── cli.py               # Headless CLI (mak-attatch-cli)
│   ├── config.py            # Configuration management
│   ├── poster_tui/          # Terminal UI (mak-attatch-tui)
│   ├── ui/                  # PyQt6 desktop GUI widgets
│   ├── core/                # Shared core modules
│   │   ├── tmdb.py          # TMDB API client + title matching
│   │   ├── attacher.py      # MKV/MP4 attachment engine
│   │   ├── parser.py        # Filename title extraction
│   │   ├── scanner.py       # Recursive folder scan & grouping
│   │   ├── autoattach.py    # Bulk resolve & attach
│   │   └── deps.py          # Distro-aware dependency detection & install hints
│   └── assets/              # Logo and app icon
├── main.py, cli.py, poster-tui   # Run-from-checkout launchers
├── convert.sh           # Interactive single-file helper (wraps the CLI)
├── requirements.txt     # Pinned Python dependencies
├── setup.sh             # Linux/macOS setup
├── PKGBUILD             # Arch Linux package build
├── Makefile             # Install/uninstall targets
├── tests/               # Test suite (GUI/TUI tests need PyQt6/textual)
└── assets/showcase/     # Screenshots and demo videos
```

Run the tests with `QT_QPA_PLATFORM=offscreen python -m pytest tests` (needs ffmpeg and mkvtoolnix; GUI/TUI tests are skipped without PyQt6/textual).

---

## Changelog

Full details: [CHANGELOG.md](CHANGELOG.md).

### v1.4.0 — 2026-11-13
- **Fixed** data-safety bugs: TUI deleted the user's own image; MP4/MOV metadata writes wiped audio/subtitle languages and chapter titles; MOV/M4V metadata editing failed; TV metadata overwrote episode titles; unverified rewrites could replace an original with a truncated file; editing hardlinked MKVs changed the seeding copy.
- **Fixed** the TMDB API key could appear in error messages.
- **Fixed** wrong-poster bulk matches: titles must actually match, extras are skipped, and existing posters are kept by default.
- **Fixed** GUI Ctrl+A attached to every file (now Ctrl+Return); one operation at a time with a Cancel button; selection survives refreshes; no crash on unexpected errors.
- **Fixed** GUI/TUI freezes (poster checks, thumbnails, dialogs), TUI crashes on markup-like names, mixed-up results from fast clicks, and a corrupt config wiping the API key.
- **Changed** packaging: all code is in the `mak_attatch` package (no more generic top-level `config`/`core`/`ui` modules), plus a `mak-attatch-tui` entry point. See [CHANGELOG.md](CHANGELOG.md) for details.

### v1.3.5 — 2026-10-20
- **Fixed** Poster cache invalidation: paths are normalized before dropping entries, so relative, symlinked, and non-normalized paths refresh correctly.
- **Improved** CI: fixed the gui-tui apt source, made Windows smoke tests platform-aware, and isolated TUI tests from the local config.

### v1.3.4 — 2026-10-20
- **Fixed** MOV poster attach: ffmpeg's `mov` muxer dropped `covr`, leaving the file silently unchanged. MOV now uses the MP4 muxer with the original brand, and removal preserves it.
- **Improved** Tests: 151 total.

### v1.3.3 — 2026-10-19
- **Fixed** MKV remux (`--to-mkv`): preserves all streams and no longer leaves a partial file on ffmpeg failure.
- **Fixed** MP4/MOV poster attach: keeps existing metadata and writes transactionally.
- **Fixed** MKV covers: replacing the poster keeps unrelated attachments.
- **Fixed** Numeric titles (`1917`, `2012`), `Blade Runner 2049`, and `2001: A Space Odyssey` parse correctly.
- **Fixed** Scanner groups same-title movies by year (e.g. `Dune` 1984 vs 2021).
- **Fixed** TMDB search year handling for movies, TV, and multi-search.
- **Fixed** CLI local-poster attach no longer needs an API key; `~` paths expand; batches resolve per file; `--dry-run` added.
- **Fixed** GUI/TUI blocking work moved off the main thread; batch metadata, poster selection, preview cleanup, and “Skip unmatched” corrected.
- **Fixed** `convert.sh` remux is transactional and reports failures.
- **Fixed** Config validation, `VERSION`, and `MAK_ATTATCH_TMDB_API_KEY` override.
- **Improved** `pip install .` packaging, venv-aware Makefile launchers, GUI/TUI + Windows CI, and README accuracy.
- **Improved** Tests: 150 total.

### v1.3.2 — 2026-08-14
- **Fixed** Fedora/EL yazi install: setup.sh now enables the `lihaohong/yazi` COPR before `dnf install` (via new `core/deps.py --yazi-copr`).
- **Fixed** README "From Source": documents running via the venv Python (`.venv/bin/python ...`), since `./main.py`'s shebang resolves to system Python.
- **Improved** `core/deps.py`: `yazi_copr_commands()` + runtime hint now mention the COPR step on Fedora/EL.
- **Improved** Tests: +3 (117 total).

### v1.3.1 — 2026-08-13
- **Improved** `setup.sh`: Distro-aware dependency detection (apt/pacman/dnf).
- **Improved** `core/deps.py`: Shared helper for runtime dependency messages.
- **Improved** Terminal poster preview: sixel/kitty capability probe with fallback.
- **Fixed** README: Updated changelog, test count, CLI binary documentation.

### v1.3.0 — 2026-08-13
- **Added** `cli.py`: Headless CLI mode (`mak-attatch-cli`) for scripts and automation.

### v1.2.0 — 2026-08-13
- **Fixed** Replaced broad `except Exception` with specific exception types across core, UI, and TUI.
- **Added** `has_poster()` session cache with mtime validation for batch scans.
- **Added** GitHub Actions CI (pytest + ruff).
- **Improved** UI lint cleanup, removed ruff exclusions.

### v1.1.6 — 2026-08-12
- **Fixed** `core/tmdb.py`: Host-aware auth header stripping, magic-byte verification on download, 5xx retry logic.
- **Fixed** `core/attacher.py`: `_find_attached_pic` logs errors to stderr.
- **Fixed** `core/autoattach.py`: Bounded error accumulation (max 20).
- **Fixed** `poster_tui/app.py`: chafa `--` separator, failure logging.

### v1.1.5 — 2026-08-10
- **Fixed** `core/tmdb.py`: Redirect handling used non-existent `resp.urljoin()`. Replaced with `urllib.parse.urljoin()`. Fixes an `AttributeError` crash when TMDB image CDN returns a redirect.
- **Added** Regression test for redirect path in `tests/test_tmdb.py`.

### v1.1.4 — 2026-08-10
- Added version display in GUI window title and TUI header.

### v1.1.3 — 2026-08-10
- Fixed MP4 `covr` atom writing on attach.
- MP4-to-MKV conversion now preserves the poster on both files.

### v1.1.2 — 2026-08-07
- Hardened subprocess temp files (unpredictable names via `mkstemp`).
- Added magic-byte MIME detection for image validation.
- Atomic config writes to prevent corruption.
- Per-hop redirect validation in TMDB fetch.
- Folder scans overwrite existing posters by default.

---

## Standalone Utility

For a quick single-file add or remove without opening the app:

```bash
./convert.sh
```

It prompts for add/remove, the video and the poster image, then runs `mak-attatch-cli`, so it gets the same safety as the app. MP4/MOV/M4V files keep their container (you're asked whether to convert to MKV); other formats are remuxed to MKV automatically. It uses the installed `mak-attatch-cli` if available, otherwise the checkout's `.venv` or `python3`.

---

## API Key

Get a free key at [themoviedb.org/settings/api](https://www.themoviedb.org/settings/api). Both the GUI and TUI prompt for it on first launch. It is stored locally, readable only by you, in:

```
~/.config/mak-attatch/config.json
```

To avoid storing the key on disk, set `MAK_ATTATCH_TMDB_API_KEY` in the environment; it overrides the config file, and the settings dialogs won't write it to disk. Both v3 API keys and v4 read access tokens work (a v4 token is sent as a header instead of in the URL). Error messages never include the key.

If `config.json` becomes unreadable, mak-attatch moves it aside as `config.json.bad-<timestamp>` instead of overwriting it, so you can recover your settings.

This product uses the TMDB API but is not endorsed or certified by TMDB. Poster images and metadata are provided by [The Movie Database](https://www.themoviedb.org); please follow the [TMDB terms of use](https://www.themoviedb.org/documentation/api/terms-of-use).

---

## License

MIT License — see [LICENSE](LICENSE) for details.
