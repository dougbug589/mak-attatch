<p align="center">
  <img src="assets/logo.png" alt="mak-attatch" width="140">
</p>

<h1 align="center">mak-attatch</h1>

<p align="center">
  <img src="https://img.shields.io/github/v/release/dougbug589/mak-attatch?style=flat-square&label=release&color=7c3aed" alt="release">
  <img src="https://img.shields.io/github/stars/dougbug589/mak-attatch?style=flat-square&label=stars&color=7c3aed&logo=github&logoColor=white" alt="stars">
  <img src="https://img.shields.io/github/license/dougbug589/mak-attatch?style=flat-square&label=license&color=7c3aed" alt="license">
  <img src="https://img.shields.io/badge/Python-3.10%2B-4f46e5?style=flat-square&logo=python&logoColor=white" alt="python">
  <img src="https://img.shields.io/badge/GUI-PyQt6-4f46e5?style=flat-square&logo=qt&logoColor=white" alt="gui">
  <img src="https://img.shields.io/badge/TUI-Textual-06b6d4?style=flat-square" alt="tui">
  <img src="https://img.shields.io/badge/AUR-mak--attatch-06b6d4?style=flat-square&logo=archlinux&logoColor=white" alt="aur">
  <img src="https://github.com/dougbug589/mak-attatch/actions/workflows/ci.yml/badge.svg" alt="ci">
</p>

<p align="center">
  Search <b>TMDB</b> · Preview posters · Attach cover art to your video files — <b>MKV</b> native, <b>MP4 / MOV / AVI</b> converted automatically.
</p>

<p align="center">
  <a href="#features">Features</a> ·
  <a href="#quick-start">Quick start</a> ·
  <a href="#usage">Usage</a> ·
  <a href="#shortcuts">Shortcuts</a> ·
  <a href="#story">The story</a> ·
  <a href="#requirements">Requirements</a> ·
  <a href="#license">License</a>
</p>

<p align="center">
  <sub>Linux today · <b>Windows &amp; Android on the way</b></sub>
</p>

---

## 🎬 Features

| | |
|---|---|
| 🎬 **TMDB search** — movies & TV with full poster selection | 🖼️ **Poster preview** — full-resolution preview before attaching |
| 📦 **Batch attach** — add many files, one poster attaches to all | 🧹 **Batch remove** — strip art & metadata in one go |
| 🧠 **Smart parsing** — title & year auto-detected from filenames | 📚 **Metadata embed** — title, overview, genres, cast tags |
| 🖌️ **Local images** — use any JPEG/PNG as a poster | 🧊 **Format-safe** — MKV stays MKV, MP4 stays MP4 |
| 🖥️ **Desktop GUI** — PyQt6 | 💻 **Terminal TUI** — Textual, for headless / SSH boxes |
| 🧩 **yazi integration** — multi-select files in the TUI | 🏝️ **Self-contained art** — lives *in* the file, works offline |

**How it works:**

```
Type a title → Search TMDB → Preview posters → Pick one → Attach
```

The poster is embedded **inside** the file — rename it, move it, back it up, and it stays with the video. No server, no scraper, nothing running in the background.

---

## ⚡ Quick start

**💠 Arch (AUR)**

```bash
yay -S mak-attatch
```

Or build it manually:

```bash
git clone https://aur.archlinux.org/mak-attatch.git
cd mak-attatch
makepkg -si
```

**🧩 From source**

```bash
git clone https://github.com/dougbug589/mak-attatch
cd mak-attatch
sudo make install
```

**🚀 Try without installing**

```bash
git clone https://github.com/dougbug589/mak-attatch
cd mak-attatch
./setup.sh
.venv/bin/python main.py       # desktop GUI
.venv/bin/python poster-tui    # terminal TUI
```

**🗑️ Uninstall**

```bash
sudo make uninstall
```

Install the system dependencies from [Requirements](#requirements) first.

---

## 🚀 Usage

**🖥️ Desktop GUI**

```bash
mak-attatch
```

1. Enter your TMDB API key on first launch
2. **Browse** for a video file, or **type** a movie/show name and search
3. **Double-click** a result to browse its posters
4. **Click** a poster to preview, then select it
5. Hit **Attach Poster**

Drag-and-drop, batch mode and local image posters are supported.

**⌨️ Terminal TUI**

```bash
mak-attatch-tui
```

1. Enter your TMDB API key on first launch
2. **Search** for a movie or TV show
3. Press <kbd>Enter</kbd> to load posters
4. **Arrow keys** to navigate, <kbd>Enter</kbd> to preview
5. Press <kbd>Enter</kbd> again to close, then **Attach Poster**

**Browse (yazi):** press <kbd>Ctrl</kbd>+<kbd>F</kbd>, mark several files with <kbd>Space</kbd>, press <kbd>Enter</kbd> — all of them are added to the files panel. Multiple paths can also be pasted (newline- or space-separated) or typed in.

---

## ⌨️ Keyboard shortcuts (TUI)

| Key | Action |
|---|---|
| <kbd>Tab</kbd> / <kbd>Shift</kbd>+<kbd>Tab</kbd> | Cycle panels forward / backward |
| <kbd>Ctrl</kbd>+<kbd>L</kbd> | Jump to **Search** panel |
| <kbd>Ctrl</kbd>+<kbd>M</kbd> | Jump to **Posters** panel |
| <kbd>Ctrl</kbd>+<kbd>R</kbd> | Jump to **Files** panel |
| <kbd>Ctrl</kbd>+<kbd>F</kbd> | Open **yazi** file browser |
| <kbd>Ctrl</kbd>+<kbd>Q</kbd> | Quit |

Panels cycle in order: Search → Results → Posters → Files → Buttons. The GUI uses standard desktop shortcuts (<kbd>Ctrl</kbd>+<kbd>O</kbd> to open files, <kbd>Ctrl</kbd>+<kbd>V</kbd> to paste).

---

## 🎞️ The story

> This tool was born out of necessity. There wasn't the budget or the hardware for a proper media server, so the collection just lives on local drives. Kodi handled the library view, but it pulls posters over the network and caches them server-side — and the scrapers would fail or grab the wrong poster for a file. Half the time the library ended up looking worse than a plain file browser.
>
> Manual attachment via `mkvpropedit --add-attachment` worked — the thumbnail showed up right in the file browser. But typing those flags out for every single file got old fast, and between re-downloading posters and guessing which one matched, it was still a chore.
>
> mak-attatch is a small tool that puts it all in one place: search TMDB, preview the posters, attach with one click. The art gets embedded *inside* the file, so it moves with the video, works offline, and no server or scraper has to be running to keep the library looking right.

---

## 📦 Requirements

| Dependency | Version | Notes |
|---|---|---|
| Python | 3.10+ | |
| ffmpeg | latest | MP4/MOV poster attach & remove |
| mkvtoolnix-cli | latest | `mkvpropedit` for MKV |
| TMDB API key | free | Prompted on first launch; stored in `~/.config/mak-attatch/` |

**TUI extras:** `python-textual` (framework) · `yazi` (file browser, optional) · `chafa` (terminal poster preview)

```bash
# Arch
sudo pacman -S python python-pyqt6 python-requests python-guessit ffmpeg mkvtoolnix-cli
sudo pacman -S python-textual yazi chafa          # TUI extras

# Debian/Ubuntu
sudo apt install python3 python3-pyqt6 python3-requests python3-guessit ffmpeg mkvtoolnix

# Fedora
sudo dnf install python3 python3-pyqt6 python3-requests python3-guessit ffmpeg mkvtoolnix
```

---

## 🛠️ How it works per format

| Format | Attach | Remove |
|---|---|---|
| **MKV** | `mkvpropedit --add-attachment` | `mkvpropedit --delete-attachment` |
| **MP4/MOV** | `ffmpeg -disposition:v:1 attached_pic` | ffprobe detect + ffmpeg remux strip |
| **Other** (AVI, etc.) | Convert to MKV, then attach | Convert to MKV, then remove |

**Metadata:** tick **Scrape metadata** to embed title, year, overview, genres, rating and cast (Matroska tags for MKV, ffmpeg tags for MP4/MOV). **Remove Metadata** strips the segment title + tags while keeping the poster. Re-attaching always overwrites stale tags.

---

## 🔑 API key

Get a free key at [themoviedb.org/settings/api](https://www.themoviedb.org/settings/api). Both apps prompt for it on first launch. Stored in:

```
~/.config/mak-attatch/config.json
```

---

## 🧰 Standalone utility

No app? `convert.sh` attaches or removes a poster from a single file:

```bash
./convert.sh
```

Prompts for add/remove mode, video path and an optional poster image. Handles format conversion and attachment natively.

---

## 📁 Project structure

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

## 📄 License

[MIT](LICENSE)
