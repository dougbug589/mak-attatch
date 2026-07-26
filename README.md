# Poster Attacher

Desktop app to search, preview, and attach cover art posters to video files using TMDB.

## Dependencies

- Python 3.10+
- ffmpeg
- mkvtoolnix (mkvpropedit)

```bash
# Arch
sudo pacman -S python python-pyqt6 python-requests python-guessit ffmpeg mkvtoolnix-cli

# Debian/Ubuntu
sudo apt install python3 python3-pyqt6 python3-requests python3-guessit ffmpeg mkvtoolnix

# Fedora
sudo dnf install python3 python3-pyqt6 python3-requests python3-guessit ffmpeg mkvtoolnix
```

## Install

### Manual

```bash
git clone https://github.com/dougbug589/poster-attacher
cd poster-attacher
make
sudo make install
```

### AUR

```bash
yay -S poster-attacher
```

### Run without installing

```bash
./setup.sh
.venv/bin/python main.py
```

## Uninstall

```bash
sudo make uninstall
```

## Usage

1. Launch `poster-attacher`
2. Enter your TMDB API key on first run (free at https://www.themoviedb.org/settings/api)
3. Browse a video file or type a movie/show name
4. Double-click a result to see posters
5. Click a poster to preview, then select it
6. Click "Attach Poster"

## Features

- Auto-detects title from video filename
- Manual search for any movie/show
- Browse all available posters from TMDB
- Preview full-size before selecting
- Attach or remove poster
- Converts video to MKV and image to JPG automatically
- Dark theme
