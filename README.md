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

*Search TMDB, browse posters, preview, attach — all in one window.*

### Terminal TUI (Textual)

*Keyboard-driven workflow with `yazi` file browser integration.*

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

**Folder Scan (Ctrl+F):** Pick a directory. mak-attatch recursively scans, groups files by title/season, auto-matches TMDB entries, and shows a review list. Hit **Attach All** to process everything. Toggle **Embed metadata** to write tags, or **Convert MP4 to MKV** for a lossless remux.

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
mak-attatch-cli scan ~/Videos --skip-existing --embed-metadata
```

Requires a configured TMDB API key (see [API Key](#api-key)). Attach and scan fail fast with a clear message if the key or a required tool (ffmpeg/mkvtoolnix) is missing.

---

## Keyboard Shortcuts

### TUI

| Key | Action |
|-----|--------|
| `q` | Quit |
| `Tab` / `Shift+Tab` | Cycle panels |
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
| `Ctrl+A` | Attach poster |

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

yazi is not in the default repos — enable its apt repo first:
```bash
curl -fsSL https://yazi-rs.github.io/builds/yazi-keyring.gpg | sudo tee /usr/share/keyrings/yazi-keyring.gpg >/dev/null
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
├── main.py              # Desktop GUI entry point
├── poster-tui           # Terminal TUI entry point
├── cli.py               # Headless CLI entry point (mak-attatch-cli)
├── poster_tui/          # TUI application code
│   ├── __init__.py
│   └── app.py
├── ui/                  # PyQt6 desktop GUI widgets
├── core/                # Shared core modules
│   ├── tmdb.py          # TMDB API client
│   ├── attacher.py      # MKV/MP4 attachment engine
│   ├── parser.py        # Filename title extraction
│   ├── scanner.py       # Recursive folder scan & grouping
│   ├── autoattach.py    # Title matching & bulk attach
│   └── deps.py          # Distro-aware dependency detection & install hints
├── config.py            # Configuration management
├── convert.sh           # Standalone bash utility (single file)
├── requirements.txt     # Python dependencies
├── setup.sh             # Virtual environment setup
├── PKGBUILD             # Arch Linux package build
├── Makefile             # Install/uninstall targets
├── tests/               # Test suite (117 tests)
│   ├── test_attacher.py
│   ├── test_autoattach.py
│   ├── test_cli.py
│   ├── test_deps.py
│   ├── test_hotfixes.py
│   ├── test_scanner.py
│   └── test_tmdb.py
└── assets/              # Logos and screenshots
```

---

## Changelog

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

---

## License

MIT License — see [LICENSE](LICENSE) for details.
