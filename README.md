# mak-attatch

> Embed TMDB movie & TV cover art directly into your video files.
> Search, preview, attach — the poster lives *inside* the file.

[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![AUR](https://img.shields.io/badge/AUR-mak--attatch-1793D1?logo=arch-linux)](https://aur.archlinux.org/packages/mak-attatch)
[![Release](https://img.shields.io/github/v/release/dougbug589/mak-attatch)](https://github.com/dougbug589/mak-attatch/releases)

**mak-attatch** fetches high-quality poster art from [The Movie Database](https://www.themoviedb.org) and embeds it into your MKV, MP4, and MOV files. The art travels with the video — no external scrapers, no network dependency, no server required.

**Two interfaces:** a polished **PyQt6 desktop GUI** and a keyboard-driven **Textual TUI** for terminals and SSH sessions.

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
- [License](#license)

---

## Features

| Feature | Description |
|---------|-------------|
| **TMDB Search** | Search movies and TV shows with full poster browsing |
| **Poster Preview** | Full-resolution preview before committing |
| **Smart Filename Parsing** | Auto-detects title and year from filenames (via `guessit`) |
| **Batch Processing** | Attach one poster to many files, or scan an entire folder |
| **Recursive Folder Scan** | Walks directories, groups by series & season, auto-matches titles |
| **Metadata Embedding** | Writes title, overview, genres, rating, cast into file tags |
| **Local Images** | Use any JPEG/PNG as a custom poster |
| **Format Safe** | MKV stays MKV; MP4/MOV keep their container (optional MKV remux) |
| **Batch Remove** | Strip art & metadata in one operation |
| **Offline Ready** | Once attached, the art is self-contained in the file |

**Supported formats:**
- **MKV** — native attachment via `mkvpropedit`
- **MP4 / MOV** — embedded `attached_pic` stream + `covr` metadata atom
- **Other formats** (AVI, etc.) — losslessly remuxed to MKV first

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
makepkg -si
```

This installs the full package: `/usr/bin/mak-attatch`, `/usr/bin/mak-attatch-tui`, `/usr/bin/mak-attatch-cli`, `.desktop` entry, and icon.

### From Source

```bash
git clone https://github.com/dougbug589/mak-attatch.git
cd mak-attatch
./setup.sh          # creates .venv and installs Python deps
```

`setup.sh` only checks for the required tools (ffmpeg, mkvtoolnix) and prints the install command. Add `--auto-install` to run it (asks for sudo) and `--with-tui` to also set up the optional TUI tools (yazi, chafa).

### With pip

```bash
git clone https://github.com/dougbug589/mak-attatch.git
pipx install "./mak-attatch[gui,tui]"   # or: pip install "./mak-attatch[gui,tui]"
```

This installs `mak-attatch`, `mak-attatch-tui` and `mak-attatch-cli`. Leave out `gui` or `tui` for a lighter install; the CLI needs neither. ffmpeg and mkvtoolnix still come from your system packages.

Run the app using the virtual environment Python (required on Fedora, Ubuntu, and other distros where the shebang resolves to system Python):

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

Do NOT use `./main.py` or `./poster-tui` directly — the shebang (`#!/usr/bin/env python3`) finds system Python, which lacks the installed dependencies.

### Uninstall

**AUR install:**

```bash
sudo pacman -Rns mak-attatch   # removes package + config + unused deps
```

**Source install:**

```bash
cd ~/mak-attatch
sudo make uninstall            # if you ran `make install`
cd ~ && rm -rf mak-attatch ~/.config/mak-attatch
```

---

## Usage

### Desktop GUI

```bash
mak-attatch
```

1. **First launch:** Enter your free TMDB API key (prompted automatically).
2. **Add files:** Browse or drag-and-drop video files.
3. **Search:** Type a title and hit **Search TMDB**.
4. **Pick a poster:** Double-click a result, browse posters, click to preview.
5. **Attach:** Hit **Attach Poster**.

**Folder Scan (Ctrl+F):** Pick a directory. mak-attatch recursively scans (skipping extras such as featurettes, trailers and samples), groups files by title/season, auto-matches TMDB entries, and shows a review list. Groups whose closest TMDB result doesn't match the title are listed as unmatched for you to review. Hit **Attach All** to process everything. Toggle **Embed metadata** to write tags, or **Convert MP4 to MKV** for a lossless remux.

### Terminal TUI

```bash
mak-attatch-tui
```

1. **Search:** Type a title, press `Enter`.
2. **Browse posters:** Arrow keys to navigate, `Enter` to preview.
3. **Attach:** Close preview, select **Attach Poster**.

**File browser:** Click the **Browse (yazi)** button (or use the button in the Files panel). Multi-select files with `Space`, press `Enter` to load them.

**Folder scan (Ctrl+S):** Scan a directory, review auto-matches, attach in bulk.

### Command-Line Interface

Qt-free, headless CLI for scripts, cron jobs, and file-manager actions.

```bash
mak-attatch-cli attach -f movie.mkv -s "The Matrix" --embed-metadata
mak-attatch-cli attach -f movie.mkv -p poster.jpg
mak-attatch-cli attach -f "Show S01E01.mkv"           # query derived from filename
mak-attatch-cli remove -f movie.mkv                   # remove poster (default)
mak-attatch-cli remove -f movie.mkv --metadata-only   # remove metadata only
mak-attatch-cli scan ~/Videos --embed-metadata
mak-attatch-cli scan ~/Videos --no-skip-existing      # also replace existing posters
```

Folder scans skip files that already have a poster unless you pass `--no-skip-existing`. They also skip extras: `Featurettes`, `Behind The Scenes`, `Trailers` and `Sample(s)` folders, plus `-trailer`/`-sample` files. A TMDB result is only used when its title actually matches the file; anything else is reported as unmatched instead of getting a random poster. In a multi-file `attach`, a file that can't be matched is reported and skipped without stopping the rest.

Requires a configured TMDB API key (see [API Key](#api-key)) for search, metadata scraping, and folder scans. Attaching a local poster with `-p` does not need a key. Attach and scan fail fast with a clear message if a required tool (ffmpeg/mkvtoolnix) is missing.

---

## Keyboard Shortcuts

### TUI

| Key | Action |
|-----|--------|
| `q` | Quit |
| `Ctrl+Tab` / `Ctrl+Shift+Tab` | Cycle panels |
| `Ctrl+L` | Focus Search panel |
| `Ctrl+M` | Focus Posters panel |
| `Ctrl+R` | Focus Files panel |
| `Ctrl+S` | Scan folder & auto-attach |
| `Space` | Toggle file selection |
| `d` | Clear selection |

### GUI

| Key | Action |
|-----|--------|
| `Ctrl+O` | Open files |
| `Ctrl+F` | Scan folder |
| `Ctrl+Return` | Attach poster |
| `Esc` | Cancel the running operation (after the current file) |

---

## How It Works

### Poster Attachment by Format

| Format | Method | Removal |
|--------|--------|---------|
| **MKV** | `mkvpropedit --add-attachment` | `mkvpropedit --delete-attachment` |
| **MP4 / MOV** | `ffmpeg -disposition:v:1 attached_pic` + `covr` atom | `ffprobe` detect + `ffmpeg` remux strip |
| **Other** (AVI, etc.) | Convert to MKV, then attach | Remux to MKV, then remove |

### Metadata Tags

| Field | MKV | MP4/MOV |
|-------|-----|---------|
| Title | `TITLE` tag | `title` metadata |
| Year | `DATE_RELEASED` | `date` |
| Overview | `SYNOPSIS` | `description` |
| Genres | `GENRE` | `genre` |
| Rating | `RATING` | — |
| Cast | `ACTOR` + `CHARACTER` | — |
| Directors | `DIRECTOR` | `author` |

### Poster Lifecycle

1. **Search** — Query TMDB API for title matches.
2. **Select** — User picks a poster from available sizes.
3. **Download** — Image fetched to a temp file (validated for size & type).
4. **Attach** — Embedded into the video container.
5. **Cleanup** — Temp files removed; original poster file preserved.

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

### "No TMDB match found"

- Check your API key at [themoviedb.org/settings/api](https://www.themoviedb.org/settings/api)
- Try simplifying the filename (remove extra tags like `1080p`, `BluRay`, etc.)
- Use the manual search box to type the exact title

### Batch scan groups files wrong

The scanner parses filenames with `guessit` and falls back to folder names for series. If a file is misgrouped:
- Ensure season folders are named clearly (`Season 1`, `S01`, etc.)
- Avoid generic filenames like `episode01.mkv` without a parent folder name

---

## Requirements

| Dependency | Version | Purpose |
|------------|---------|---------|
| Python | 3.10+ | Runtime |
| ffmpeg | latest | MP4/MOV attach & remove |
| mkvtoolnix-cli | latest | `mkvpropedit` for MKV |
| python-pyqt6 | latest | Desktop GUI |
| python-requests | latest | TMDB API client |
| python-guessit | latest | Filename parsing |
| TMDB API key | free | Poster search (prompted on first launch) |

**TUI extras:** `python-textual` · `yazi` (file browser) · `chafa` (terminal image preview)

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

---

## Changelog

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

For single-file operations without launching the full app:

```bash
./convert.sh
```

Interactive prompts for add/remove mode, video path, and poster image. Handles format conversion automatically.

---

## API Key

Get a free key at [themoviedb.org/settings/api](https://www.themoviedb.org/settings/api). Both the GUI and TUI prompt for it on first launch. Stored locally in:

```
~/.config/mak-attatch/config.json
```

To avoid storing the key on disk, set `MAK_ATTATCH_TMDB_API_KEY` in the environment; it overrides the config file.

This product uses the TMDB API but is not endorsed or certified by TMDB. Poster images and metadata are provided by [The Movie Database](https://www.themoviedb.org); please follow the [TMDB terms of use](https://www.themoviedb.org/documentation/api/terms-of-use).

---

## License

MIT License — see [LICENSE](LICENSE) for details.
