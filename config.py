import json
import os
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "poster-attacher"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULTS = {
    "tmdb_api_key": "",
    "default_poster_size": "w500",
    "auto_convert_video": True,
    "last_dir": "",
}


def load() -> dict:
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE) as f:
                data = json.load(f)
        except (json.JSONDecodeError, PermissionError):
            return DEFAULTS.copy()
        for key, val in DEFAULTS.items():
            data.setdefault(key, val)
        return data
    return DEFAULTS.copy()


def save(config: dict):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    CONFIG_FILE.touch(exist_ok=True)
    os.chmod(CONFIG_FILE, 0o600)
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)
    os.chmod(CONFIG_FILE, 0o600)


def get(key: str):
    return load().get(key, DEFAULTS.get(key))


def set(key: str, value):
    if key == "tmdb_api_key" and value:
        value = str(value).strip()
        if len(value) < 10 or len(value) > 50:
            raise ValueError("Invalid API key format")
    config = load()
    config[key] = value
    save(config)
