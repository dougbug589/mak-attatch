import json
import os
import tempfile
from pathlib import Path

VERSION = "1.3.4"

CONFIG_DIR = Path.home() / ".config" / "mak-attatch"
CONFIG_FILE = CONFIG_DIR / "config.json"

# Overrides config.json so the API key never has to touch disk.
API_KEY_ENV = "MAK_ATTATCH_TMDB_API_KEY"

POSTER_SIZES = {"w92", "w154", "w185", "w342", "w500", "w780", "original"}
BOOL_KEYS = {"auto_convert_video", "scan_skip_existing", "convert_to_mkv"}

DEFAULTS = {
    "tmdb_api_key": "",
    "default_poster_size": "w500",
    "auto_convert_video": True,
    "last_dir": "",
    "scan_skip_existing": False,
    "scan_api_delay": 0.25,
    "convert_to_mkv": False,
}


def _normalize(data: dict) -> dict:
    """Coerce stored values into the types the rest of the app expects."""
    for key, val in DEFAULTS.items():
        data.setdefault(key, val)

    data["tmdb_api_key"] = str(data.get("tmdb_api_key") or "").strip()

    if data.get("default_poster_size") not in POSTER_SIZES:
        data["default_poster_size"] = DEFAULTS["default_poster_size"]

    try:
        data["scan_api_delay"] = max(0.0, float(data.get("scan_api_delay")))
    except (TypeError, ValueError):
        data["scan_api_delay"] = DEFAULTS["scan_api_delay"]

    for key in BOOL_KEYS:
        data[key] = bool(data.get(key))

    data["last_dir"] = str(data.get("last_dir") or "")
    return data


def load() -> dict:
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE) as f:
                data = json.load(f)
        except (json.JSONDecodeError, PermissionError, OSError):
            return DEFAULTS.copy()
        if not isinstance(data, dict):
            return DEFAULTS.copy()
        return _normalize(data)
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
    if key == "tmdb_api_key":
        env_key = os.environ.get(API_KEY_ENV, "").strip()
        if env_key:
            return env_key
    return load().get(key, DEFAULTS.get(key))


def set(key: str, value):
    if key == "tmdb_api_key":
        value = str(value or "").strip()
        if value and not 10 <= len(value) <= 500:
            raise ValueError("Invalid API key format")
    elif key == "default_poster_size":
        if value not in POSTER_SIZES:
            raise ValueError(
                f"Invalid poster size {value!r}; expected one of {sorted(POSTER_SIZES)}"
            )
    elif key == "scan_api_delay":
        try:
            value = max(0.0, float(value))
        except (TypeError, ValueError):
            raise ValueError("scan_api_delay must be a number") from None
    elif key in BOOL_KEYS:
        value = bool(value)
    config = load()
    config[key] = value
    save(config)
