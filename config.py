import json
import os
import tempfile
from pathlib import Path

VERSION = "1.2.0"

CONFIG_DIR = Path.home() / ".config" / "mak-attatch"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULTS = {
    "tmdb_api_key": "",
    "default_poster_size": "w500",
    "auto_convert_video": True,
    "last_dir": "",
    "scan_skip_existing": False,
    "scan_api_delay": 0.25,
    "convert_to_mkv": False,
}


def load() -> dict:
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE) as f:
                data = json.load(f)
        except (json.JSONDecodeError, PermissionError, OSError):
            return DEFAULTS.copy()
        for key, val in DEFAULTS.items():
            data.setdefault(key, val)
        return data
    return DEFAULTS.copy()


def save(config: dict):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, tmp = tempfile.mkstemp(dir=CONFIG_DIR, prefix="config.", suffix=".json")
    os.close(fd)
    try:
        with open(tmp, "w") as f:
            json.dump(config, f, indent=2)
        os.chmod(tmp, 0o600)
        os.replace(tmp, CONFIG_FILE)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def get(key: str):
    return load().get(key, DEFAULTS.get(key))


def set(key: str, value):
    if key == "tmdb_api_key" and value:
        value = str(value).strip()
        if len(value) < 10 or len(value) > 500:
            raise ValueError("Invalid API key format")
    config = load()
    config[key] = value
    save(config)
