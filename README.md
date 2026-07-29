<p align="center">
  <img src="assets/P.png" alt="Poster Attacher" width="120">
</p>

<h1 align="center">Poster Attacher</h1>

<p align="center">
  Search TMDB for movie and TV posters, preview them, and attach cover art to your video files — desktop GUI or terminal TUI.
</p>

---

## What it does

You point it at a video file (or just type a title), it pulls up posters from TMDB, you pick one, and it gets embedded as cover art in the file. Works with MKV natively, and converts other formats automatically.

No more manually downloading posters and figuring out `mkvpropedit` commands.

## Screenshots

*Coming soon.*

## Requirements

- Python 3.10+
- ffmpeg
- mkvtoolnix (for `mkvpropedit`)

Install the system dependencies for your distro:

```bash
# Arch
sudo pacman -S python python-pyqt6 python-requests python-guessit ffmpeg mkvtoolnix-cli

# Debian/Ubuntu
sudo apt install python3 python3-pyqt6 python3-requests python3-guessit ffmpeg mkvtoolnix

# Fedora
sudo dnf install python3 python3-pyqt6 python3-requests python3-guessit ffmpeg mkvtoolnix
```

For the **TUI** (terminal) interface, also install:

```bash
# Arch
sudo pacman -S python-textual yazi chafa
```

## Installing

The quickest way on Arch:

```bash
yay -S poster-attacher
```

Or build from source:

```bash
git clone https://github.com/dougbug589/poster-attacher
cd poster-attacher
make
sudo make install
```

To uninstall:

```bash
sudo make uninstall
```

### Try it without installing

```bash
git clone https://github.com/dougbug589/poster-attacher
cd poster-attacher
./setup.sh
.venv/bin/python main.py     # desktop GUI
.venv/bin/python poster-tui   # terminal TUI
```

## Desktop GUI

Run `poster-attacher` (or `python main.py`):

1. Enter your TMDB API key when prompted
2. Browse for a video file, or type a movie/show name and search
3. Double-click a result to browse available posters
4. Click a poster to preview it, then select it
5. Hit **Attach Poster** and you're done

Supports drag-and-drop, batch mode, and local images.

## Terminal TUI

Run `poster-attacher-tui` (or `python poster-tui`):

1. Enter your TMDB API key when prompted
2. Search for a movie/show, then click a result
3. Navigate the poster list with arrow keys, press Enter to preview
4. Press Enter again to return, then attach

File browsing via yazi, paste paths manually for batch mode. See keybindings in the footer (`Ctrl+L`/`Ctrl+M`/`Ctrl+R` to jump between panels).

## Features

- Pulls posters from TMDB (movies and TV shows)
- Auto-detects title from video filenames
- Browse, preview, and pick from all available poster versions
- Batch attach/remove for multiple files
- Use your own local images as posters
- Works with MKV, MP4, MOV, AVI, and more — keeps original format when possible
- Two interfaces: desktop GUI (PyQt6) or terminal TUI (Textual)

## License

[MIT](LICENSE)
