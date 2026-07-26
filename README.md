<p align="center">
  <img src="assets/P.png" alt="Poster Attacher" width="120">
</p>

<h1 align="center">Poster Attacher</h1>

<p align="center">
  Search TMDB for movie and TV posters, preview them, and attach cover art to your video files — all from a simple desktop app.
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
.venv/bin/python main.py
```

## How to use it

1. Open the app
2. Enter your TMDB API key when prompted (grab one for free at [themoviedb.org/settings/api](https://www.themoviedb.org/settings/api))
3. Browse for a video file, or just type a movie/show name and hit search
4. The app will try to guess the title from the filename, but you can always search manually
5. Double-click a result to browse available posters
6. Click a poster to preview it full-size, then select it
7. Hit **Attach Poster** and you're done

You can also drag and drop a video file directly onto the app window.

## Features

- Pulls posters from TMDB (movies and TV shows)
- Auto-detects title from video filenames
- Browse, preview, and pick from all available poster versions
- Drag and drop support
- Converts non-MKV videos and non-JPG images automatically
- Follows your system theme (works nicely on KDE, GNOME, etc.)

## License

[MIT](LICENSE)
