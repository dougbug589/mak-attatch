<p align="center">
  <img src="assets/logo.png" alt="mak-attatch" width="140">
</p>

<h1 align="center">mak-attatch</h1>

<p align="center">
  <b>Embed TMDB poster art into your video files.</b><br>
  Search, preview, attach — <b>MKV</b> native, <b>MP4 / MOV / AVI</b> converted automatically.
</p>

<p align="center">
  Desktop GUI (PyQt6) &nbsp;·&nbsp; Terminal TUI (Textual) &nbsp;·&nbsp; Linux (Arch · AUR)
</p>

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
  <img src="https://img.shields.io/badge/-Features-7c3aed?style=flat-square" alt="features">
  <a href="#quick-start"><img src="https://img.shields.io/badge/-Quick%20start-4f46e5?style=flat-square" alt="quick start"></a>
  <a href="#usage"><img src="https://img.shields.io/badge/-Usage-4f46e5?style=flat-square" alt="usage"></a>
  <a href="#shortcuts"><img src="https://img.shields.io/badge/-Shortcuts-06b6d4?style=flat-square" alt="shortcuts"></a>
  <a href="#story"><img src="https://img.shields.io/badge/-The%20story-06b6d4?style=flat-square" alt="the story"></a>
  <a href="#requirements"><img src="https://img.shields.io/badge/-Requirements-22c55e?style=flat-square" alt="requirements"></a>
  <a href="#license"><img src="https://img.shields.io/badge/-License-7c3aed?style=flat-square" alt="license"></a>
</p>

<p align="center">
  <sub>Linux is supported today — <b>Windows &amp; Android are on the way</b>.</sub>
</p>

---

<h2 align="center">Features</h2>

| | | | |
|---|---|---|---|
| **TMDB search** — movies & TV with full poster selection | **Poster preview** — full-res preview before attaching | **Batch attach** — many files, one poster | **Batch remove** — strip art & metadata |
| **Smart parsing** — title & year from filenames | **Metadata embed** — title / overview / genres / cast | **Local images** — any JPEG/PNG as a poster | **Format-safe** — MKV stays MKV, MP4 stays MP4 |
| **Desktop GUI** — PyQt6 | **Terminal TUI** — Textual, for headless / SSH boxes | **yazi integration** — multi-select in the TUI | **Self-contained art** — lives *in* the file, works offline |

<h4 align="center">How it works</h4>

<p align="center">
  <code>Type a title</code> &nbsp;→&nbsp; <code>Search TMDB</code> &nbsp;→&nbsp; <code>Preview posters</code> &nbsp;→&nbsp; <code>Pick one</code> &nbsp;→&nbsp; <code>Attach</code>
</p>

<p align="center">
  <sub>The poster is embedded <b>inside</b> the file — rename it, move it, back it up, and it stays with the video.</sub>
</p>

<p align="right">[Back to top](#)</p>

---

<h2 align="center">Quick start</h2>

<details>
  <summary><b>Arch (AUR)</b></summary>

  ```bash
  yay -S mak-attatch
  ```

  Or build it manually:

  ```bash
  git clone https://aur.archlinux.org/mak-attatch.git
  cd mak-attatch
  makepkg -si
  ```
</details>

<details>
  <summary><b>From source</b></summary>

  ```bash
  git clone https://github.com/dougbug589/mak-attatch
  cd mak-attatch
  sudo make install
  ```

  Install the system dependencies from [Requirements](#requirements) first.
</details>

<details>
  <summary><b>Try without installing</b></summary>

  ```bash
  git clone https://github.com/dougbug589/mak-attatch
  cd mak-attatch
  ./setup.sh
  .venv/bin/python main.py       # desktop GUI
  .venv/bin/python poster-tui    # terminal TUI
  ```
</details>

<details>
  <summary><b>Uninstall</b></summary>

  ```bash
  sudo make uninstall
  ```
</details>

<p align="right">[Back to top](#)</p>

---

<h2 align="center">Usage</h2>

<details>
  <summary><b>Desktop GUI</b></summary>

  ```bash
  mak-attatch
  ```

  1. Enter your TMDB API key on first launch
  2. **Browse** for a video file, or **type** a movie/show name and search
  3. **Double-click** a result to browse its posters
  4. **Click** a poster to preview, then select it
  5. Hit **Attach Poster**

  <sub>Drag-and-drop, batch mode and local image posters are supported.</sub>
</details>

<details>
  <summary><b>Terminal TUI</b></summary>

  ```bash
  mak-attatch-tui
  ```

  1. Enter your TMDB API key on first launch
  2. **Search** for a movie or TV show
  3. Press <kbd>Enter</kbd> to load posters
  4. **Arrow keys** to navigate, <kbd>Enter</kbd> to preview
  5. Press <kbd>Enter</kbd> again to close, then **Attach Poster**

  <sub><b>Browse (yazi):</b> press <kbd>Ctrl</kbd>+<kbd>F</kbd>, mark files with <kbd>Space</kbd>, press <kbd>Enter</kbd> — all of them are added. Multiple paths can be pasted too (newline- or space-separated).</sub>
</details>

<p align="right">[Back to top](#)</p>

---

<h2 align="center" id="shortcuts">Keyboard shortcuts (TUI)</h2>

| Key | Action |
|---|---|
| <kbd>Tab</kbd> / <kbd>Shift</kbd>+<kbd>Tab</kbd> | Cycle panels forward / backward |
| <kbd>Ctrl</kbd>+<kbd>L</kbd> | Jump to **Search** panel |
| <kbd>Ctrl</kbd>+<kbd>M</kbd> | Jump to **Posters** panel |
| <kbd>Ctrl</kbd>+<kbd>R</kbd> | Jump to **Files** panel |
| <kbd>Ctrl</kbd>+<kbd>F</kbd> | Open **yazi** file browser |
| <kbd>Ctrl</kbd>+<kbd>Q</kbd> | Quit |

<p align="center"><sub>Panels cycle in order: Search → Results → Posters → Files → Buttons. The GUI uses standard desktop shortcuts.</sub></p>

<p align="right">[Back to top](#)</p>

---

<h2 align="center" id="story">The story</h2>

> This tool was born out of necessity. There wasn't the budget or the hardware for a proper media server, so the collection just lives on local drives. Kodi handled the library view, but it pulls posters over the network and caches them server-side — and the scrapers would fail or grab the wrong poster for a file. Half the time the library ended up looking worse than a plain file browser.
>
> Manual attachment via `mkvpropedit --add-attachment` worked — the thumbnail showed up right in the file browser. But typing those flags out for every single file got old fast, and between re-downloading posters and guessing which one matched, it was still a chore.
>
> mak-attatch is a small tool that puts it all in one place: search TMDB, preview the posters, attach with one click. The art gets embedded *inside* the file, so it moves with the video, works offline, and no server or scraper has to be running to keep the library looking right.

<p align="right">[Back to top](#)</p>

---

<h2 align="center" id="requirements">Requirements</h2>

| Dependency | Version | Notes |
|---|---|---|
| Python | 3.10+ | |
| ffmpeg | latest | MP4/MOV poster attach & remove |
| mkvtoolnix-cli | latest | `mkvpropedit` for MKV |
| TMDB API key | free | Prompted on first launch; stored in `~/.config/mak-attatch/` |

<p align="center"><sub><b>TUI extras:</b> <code>python-textual</code> (framework) · <code>yazi</code> (file browser, optional) · <code>chafa</code> (terminal preview)</sub></p>

<details>
  <summary><b>Install system dependencies</b></summary>

  ```bash
  # Arch
  sudo pacman -S python python-pyqt6 python-requests python-guessit ffmpeg mkvtoolnix-cli
  sudo pacman -S python-textual yazi chafa          # TUI extras

  # Debian/Ubuntu
  sudo apt install python3 python3-pyqt6 python3-requests python3-guessit ffmpeg mkvtoolnix

  # Fedora
  sudo dnf install python3 python3-pyqt6 python3-requests python3-guessit ffmpeg mkvtoolnix
  ```
</details>

<p align="right">[Back to top](#)</p>

---

<h2 align="center">How it works per format</h2>

| Format | Attach | Remove |
|---|---|---|
| **MKV** | `mkvpropedit --add-attachment` | `mkvpropedit --delete-attachment` |
| **MP4/MOV** | `ffmpeg -disposition:v:1 attached_pic` | ffprobe detect + ffmpeg remux strip |
| **Other** (AVI, etc.) | Convert to MKV, then attach | Convert to MKV, then remove |

<p align="center"><sub><b>Metadata:</b> tick <b>Scrape metadata</b> to embed title, year, overview, genres, rating and cast (Matroska tags for MKV, ffmpeg tags for MP4/MOV). <b>Remove Metadata</b> strips title + tags while keeping the poster. Re-attaching always overwrites stale tags.</sub></p>

<p align="right">[Back to top](#)</p>

---

<h2 align="center">API key</h2>

Get a free key at [themoviedb.org/settings/api](https://www.themoviedb.org/settings/api). Both apps prompt for it on first launch. Stored in:

```
~/.config/mak-attatch/config.json
```

<p align="right">[Back to top](#)</p>

---

<h2 align="center">Standalone utility</h2>

No app? `convert.sh` attaches or removes a poster from a single file:

```bash
./convert.sh
```

Prompts for add/remove mode, video path and an optional poster image. Handles format conversion and attachment natively.

<p align="right">[Back to top](#)</p>

---

<h2 align="center">Project structure</h2>

<details>
  <summary><b>Show layout</b></summary>

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
</details>

<p align="right">[Back to top](#)</p>

---

<h2 align="center" id="license">License</h2>

<p align="center"><a href="LICENSE">MIT</a></p>
