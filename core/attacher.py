import os
import shutil
import subprocess
import tempfile
from pathlib import Path


def check_tools():
    missing = []
    if not shutil.which("ffmpeg"):
        missing.append("ffmpeg")
    if not shutil.which("mkvtoolnix (mkvpropedit)"):
        missing.append("mkvtoolnix (mkvpropedit)")
    return missing


def _validate_path(path: str, allowed_suffixes: set = None) -> Path:
    p = Path(path).resolve()
    if not p.exists():
        raise FileNotFoundError(f"File not found: {path}")
    if not p.is_file():
        raise ValueError(f"Not a file: {path}")
    if ".." in str(p):
        raise ValueError(f"Path traversal detected: {path}")
    if allowed_suffixes and p.suffix.lower() not in allowed_suffixes:
        raise ValueError(f"Unexpected file type: {p.suffix}")
    return p


def _secure_temp(suffix: str) -> str:
    fd, path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    os.chmod(path, 0o600)
    return path


VIDEO_EXTS = {".mkv", ".avi", ".mp4", ".mov", ".webm", ".flv", ".wmv", ".ts", ".m4v", ".mpeg", ".mpg"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".gif", ".tiff"}


def to_mkv(video_path: str) -> str:
    p = _validate_path(video_path, VIDEO_EXTS)
    if p.suffix.lower() == ".mkv":
        return video_path

    out = str(p.with_suffix(".mkv"))
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(p), "-codec", "copy", out],
        check=True, capture_output=True, timeout=600,
    )
    return out


def to_jpg(image_path: str) -> str:
    p = _validate_path(image_path, IMAGE_EXTS)
    if p.suffix.lower() in (".jpg", ".jpeg"):
        return image_path

    out = str(p.with_suffix(".jpg"))
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(p), out],
        check=True, capture_output=True, timeout=60,
    )
    return out


def attach_poster(video_path: str, poster_path: str):
    _validate_path(video_path, VIDEO_EXTS)
    _validate_path(poster_path, IMAGE_EXTS)
    remove_poster(video_path)
    subprocess.run(
        [
            "mkvpropedit", video_path,
            "--attachment-mime-type", "image/jpeg",
            "--attachment-name", "cover.jpg",
            "--add-attachment", poster_path,
        ],
        check=True, capture_output=True, timeout=60,
    )


def remove_poster(video_path: str):
    _validate_path(video_path, VIDEO_EXTS)
    result = subprocess.run(
        ["mkvpropedit", video_path, "--delete-attachment", "name:cover.jpg"],
        capture_output=True,
    )
    if result.returncode != 0 and b"not found" not in result.stderr.lower():
        raise RuntimeError(f"Failed to remove poster: {result.stderr.decode(errors='ignore')}")


def full_attach(video_path: str, poster_path: str) -> str:
    mkv = to_mkv(video_path)
    jpg = to_jpg(poster_path)
    attach_poster(mkv, jpg)
    return mkv
