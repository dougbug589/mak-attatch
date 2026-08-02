<p align="center">
  <img src="assets/logo.png" alt="mak-attatch" width="120">
</p>

<h1 align="center">mak-attatch</h1>

<p align="center">
  Search TMDB for movie and TV posters, preview them, and embed cover art into your video files.
</p>

<p align="center">
  <b>Desktop GUI</b> (PyQt6) &nbsp;·&nbsp; <b>Terminal TUI</b> (Textual)
</p>

<p align="center">
  <a href="#desktop-gui">GUI</a> ·
  <a href="#terminal-tui">TUI</a> ·
  <a href="#installing">Install</a> ·
  <a href="#requirements">Requirements</a> ·
  <a href="#features">Features</a> ·
  <a href="#keyboard-shortcuts">Shortcuts</a>
</p>

<p align="center">
  <img src="https://github.com/dougbug589/mak-attatch/actions/workflows/ci.yml/badge.svg" alt="CI">
  <img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License">
  <img src="https://img.shields.io/badge/python-3.10%2B-blue.svg" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/GUI-PyQt6-orange.svg" alt="PyQt6">
  <img src="https://img.shields.io/badge/TUI-Textual-green.svg" alt="Textual">
</p>

---

## What it does

Point it at a video file (or just type a title), pull up posters from TMDB, pick one — it gets embedded as cover art in the file. MKV is native; other formats are converted automatically.

No more manually downloading posters and figuring out `mkvpropedit` flags.

### The story

Honestly, I built this out of necessity. I didn't have the money or the hardware to set up a proper server for my media collection, so everything just lived on local drives. To make it look good I turned to Kodi for the library view — but Kodi pulls posters over the network and caches them server-side, and for me it never really worked the way I wanted. Scrapes failed, titles changed, files moved, and suddenly half my library had missing or wrong artwork. It was doing the opposite of keeping things presentable.

So I said fine, I'll just do it myself. I started gluing posters straight onto the files with `mkvpropedit --add-attachment` — and you know what, it actually worked. The thumbnail showed up right there in my file browser. But typing those flags out for every single file? That got old fast. And between re-downloading posters and guessing which one matched, it was still a chore.

So I figured I'd build a small tool that does all of this for me — search TMDB, preview the posters, attach with one click — and while I was at it, why not share it with everyone else who's in the same boat. That's mak-attatch. The art gets embedded *inside* the file, so it moves with the video, works offline, and you don't need a server, a scraper, or anything else running to keep your library looking right.

### Why mak-attatch?

Poster art makes your media library browseable at a glance — but attaching it is fiddly:
`mkvpropedit` flags for MKV, ffmpeg `attached_pic` dispositions for MP4, and every format has different rules. mak-attatch wraps all of that up so you can:

- **Search TMDB** for the exact movie or show and pick the right poster by previewing it first — no guessing which of 20 similar posters matches.
- **Run it from anywhere** — a full desktop GUI (PyQt6) or a lightweight terminal TUI (Textual) for headless/SSH/library-server boxes.
- **Fix a whole folder in one go** — add several files, pick one poster, attach to all; or strip posters/metadata from everything at once.
- **Go beyond the artwork** — optionally embed full TMDB metadata (title, overview, genres, cast) as MKV/MP4 tags so your library's info stays with the file even if it moves.
- **Stay format-safe** — MKV stays MKV, MP4 stays MP4, and oddball formats (AVI, etc.) are converted to MKV automatically; nothing is lost in the process.
- **Work offline, without infrastructure** — art lives in the file, so no server, scraper, or online service is needed to keep your library looking right.

---

## Requirements

| Dependency | Version | Notes |
|---|---|---|
| Python | 3.10+ | |
| ffmpeg | latest | MP4/MOV poster attachment and removal |
| mkvtoolnix-cli | latest | `mkvpropedit` for MKV attachment |
| TMDB API key | free | Enter on first launch; stored in `~/.config/mak-attatch/` |

### TUI-only extras

| Dependency | Role |
|---|---|
| python-textual | Terminal UI framework |
| yazi | File browser (optional, falls back to manual path input) |
| chafa | Poster preview rendering in the terminal |

### Install system deps

```bash
# Arch
sudo pacman -S python python-pyqt6 python-requests python-guessit ffmpeg mkvtoolnix-cli

# TUI extras (Arch)
sudo pacman -S python-textual yazi chafa
```

```bash
# Debian/Ubuntu
sudo apt install python3 python3-pyqt6 python3-requests python3-guessit ffmpeg mkvtoolnix
```

```bash
# Fedora
sudo dnf install python3 python3-pyqt6 python3-requests python3-guessit ffmpeg mkvtoolnix
```

---

## Installing

### Via AUR (Arch)

```bash
yay -S mak-attatch
```

Or build it manually:

```bash
git clone https://aur.archlinux.org/mak-attatch.git
cd mak-attatch
makepkg -si
```

### From source

```bash
git clone https://github.com/dougbug589/mak-attatch
cd mak-attatch
sudo make install
```

Install the system dependencies from the [Requirements](#requirements) section first.

### Uninstall

```bash
sudo make uninstall
```

### Try without installing

```bash
git clone https://github.com/dougbug589/mak-attatch
cd mak-attatch
./setup.sh
.venv/bin/python main.py       # desktop GUI
.venv/bin/python poster-tui    # terminal TUI
```

---

## Desktop GUI

```
mak-attatch
```

1. Enter your TMDB API key on first launch
2. **Browse** for a video file, or **type** a movie/show name and search
3. **Double-click** a result to browse available posters
4. **Click** a poster to preview it, then select it
5. Hit **Attach Poster**

**Supports:** drag-and-drop, batch mode, local image files.

---

## Terminal TUI

```
mak-attatch-tui
```

### Quick start

1. Enter your TMDB API key on first launch
2. **Search** for a movie or TV show
3. **Click** a result or press `Enter` to load posters
4. **Arrow keys** to navigate the poster list, `Enter` to preview
5. `Enter` again to close preview, then **Attach Poster**

### File browsing

Press `Ctrl+F` or click **Browse (yazi)** to open **yazi** as a file browser. Mark several files with `Space`, then press `Enter` — all of them are added to the files panel. You can also paste multiple paths into the path field (newline- or space-separated) or type them in.

### Batch mode

Add multiple files to the files panel (via yazi or manual path input), then run **Attach Poster** or **Remove Poster** once — it processes them all.

---

## Keyboard Shortcuts

### TUI

| Key | Action |
|---|---|
| `Tab` / `Shift+Tab` | Cycle panels forward / backward |
| `Ctrl+L` | Jump to **Search** panel |
| `Ctrl+M` | Jump to **Posters** panel |
| `Ctrl+R` | Jump to **Files** panel |
| `Ctrl+F` | Open **yazi** file browser |
| `Ctrl+Q` | Quit |

Panels cycle in order: Search → Results → Posters → Files → Buttons.

### GUI

Standard desktop shortcuts — `Ctrl+O` to open files, `Ctrl+V` to paste, etc.

---

## Features

| | |
|---|---|
| **TMDB search** | Movies and TV shows — full poster selection with language and resolution info |
| **Smart parsing** | Auto-detects title and year from video filenames (via guessit) |
| **Poster preview** | Full-resolution preview before attaching (TUI: suspend-based preview) |
| **Format support** | MKV (native), MP4, MOV, AVI — keeps original container when possible |
| **Batch attach** | Select multiple files, attach the same poster to all at once |
| **Batch remove** | Strip cover art from multiple files in one go |
| **Metadata embed** | Optionally scrape title/tagline/overview/genres/cast from TMDB and embed (MKV tags / MP4 tags) |
| **Metadata remove** | Strip all title/tags metadata (MKV + MP4); re-embedding overwrites stale tags |
| **Local images** | Use any JPEG/PNG/etc as a poster (auto-converts to JPG for MKV) |
| **Two interfaces** | Full desktop GUI (PyQt6) or lightweight terminal TUI (Textual) |
| **Self-contained art** | Posters live *in* the file — survive moves, renames, backups, and work offline, with no server or scraper involved |

### Metadata

Tick **Scrape metadata** before attaching to fetch title, year, tagline, overview, genres, rating, directors/writers (movies) or creators/seasons/episodes (TV), and cast from TMDB. Written as Matroska tags for MKV and ffmpeg tags for MP4/MOV.

**Remove Metadata** (GUI button / `Rm Metadata` in TUI) strips the segment title and all tag elements from MKV files via `mkvpropedit`, and rewrites MP4/MOV without any global tags via ffmpeg. Poster artwork is kept.

Re-attaching with metadata always overwrites any previously embedded tags — stale titles/genres are discarded before the new ones are written.

### What happens per format

| Format | Attach | Remove |
|---|---|---|
| **MKV** | `mkvpropedit --add-attachment` | `mkvpropedit --delete-attachment` |
| **MP4/MOV** | `ffmpeg -disposition:v:1 attached_pic` | ffprobe detect + ffmpeg remux strip |
| **Other** (AVI, etc.) | Convert to MKV first, then attach | Convert to MKV first, then remove |

Metadata removal: MKV uses `mkvpropedit --edit info --delete title --tags all:`; MP4/MOV uses an ffmpeg remux with `-map_metadata -1`.

---

## API Key

Your TMDB API key is stored in:

```
~/.config/mak-attatch/config.json
```

You get one free at [themoviedb.org/settings/api](https://www.themoviedb.org/settings/api). Both the GUI and TUI prompt for it on first launch.

---

## Standalone utility

A bash script `convert.sh` is included for quick attach/remove without the app:

```bash
./convert.sh
```

Prompts for add/remove mode, video path, and optional poster image path. Handles format conversion and attachment natively.

---

## Project structure

```
mak-attatch/
├── main.py              # Desktop GUI entry point
├── poster-tui           # Terminal TUI entry point
├── poster_tui/          # TUI application
│   ├── app.py
│   └── core/
│       ├── tmdb.py      # TMDB API client
│       ├── attacher.py  # MKV/MP4 attachment logic
│       └── parser.py    # Title extraction from filenames
├── ui/                  # PyQt6 desktop GUI
├── core/                # Shared core modules
├── config.py            # Root-level configuration
├── convert.sh           # Standalone bash utility
├── requirements.txt     # Python dependencies
├── setup.sh             # Virtual environment setup
├── PKGBUILD             # Arch Linux package build
├── Makefile             # Install/uninstall targets
└── assets/              # Logos and screenshots
```

---

## License

[MIT](LICENSE)
