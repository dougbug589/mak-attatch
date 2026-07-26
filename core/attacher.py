import os
import shutil
import subprocess
import tempfile
from pathlib import Path


def check_tools():
    missing = []
    if not shutil.which("ffmpeg"):
        missing.append("ffmpeg")
    if not shutil.which("mkvpropedit"):
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
MKV_COMPAT_EXTS = {".mkv"}
MP4_COMPAT_EXTS = {".mp4", ".mov"}

MIME_MAP = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".bmp": "image/bmp",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".tiff": "image/tiff",
}


def _get_mime(image_path: str) -> str:
    ext = Path(image_path).suffix.lower()
    return MIME_MAP.get(ext, "image/jpeg")


def to_mkv(video_path: str) -> str:
    p = _validate_path(video_path, VIDEO_EXTS)
    if p.suffix.lower() in MKV_COMPAT_EXTS:
        return video_path

    out = str(p.with_suffix(".mkv"))
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(p), "-codec", "copy", out],
        check=True, capture_output=True, timeout=600,
    )
    return out


def attach_poster_mkv(video_path: str, poster_path: str):
    _validate_path(video_path, VIDEO_EXTS)
    _validate_path(poster_path, IMAGE_EXTS)
    remove_poster(video_path)
    mime = _get_mime(poster_path)
    subprocess.run(
        [
            "mkvpropedit", video_path,
            "--attachment-mime-type", mime,
            "--attachment-name", Path(poster_path).name,
            "--add-attachment", poster_path,
        ],
        check=True, capture_output=True, timeout=60,
    )


def attach_poster_mp4(video_path: str, poster_path: str):
    _validate_path(video_path, VIDEO_EXTS)
    _validate_path(poster_path, IMAGE_EXTS)
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", video_path,
            "-i", poster_path,
            "-map", "0", "-map", "1",
            "-c", "copy",
            "-disposition:v:1", "attached_pic",
            video_path + ".tmp.mp4",
        ],
        check=True, capture_output=True, timeout=60,
    )
    os.replace(video_path + ".tmp.mp4", video_path)


def _find_attached_pic(video_path: str) -> int | None:
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", video_path],
        capture_output=True, timeout=30,
    )
    if result.returncode != 0:
        return None
    import json
    try:
        streams = json.loads(result.stdout).get("streams", [])
    except json.JSONDecodeError:
        return None
    for s in streams:
        tags = {k.lower(): v for k, v in s.get("tags", {}).items()}
        disp = s.get("disposition", {})
        if "attached_pic" in tags or disp.get("attached_pic"):
            return s["index"]
    return None


def remove_poster(video_path: str):
    _validate_path(video_path, VIDEO_EXTS)
    ext = Path(video_path).suffix.lower()
    if ext in MKV_COMPAT_EXTS:
        result = subprocess.run(
            ["mkvpropedit", video_path, "--delete-attachment", "name:cover.jpg"],
            capture_output=True,
        )
        if result.returncode != 0:
            stderr = result.stderr.decode(errors='ignore').lower()
            if stderr and "not found" not in stderr and "no such" not in stderr:
                raise RuntimeError(f"Failed to remove poster: {result.stderr.decode(errors='ignore')}")
    elif ext in MP4_COMPAT_EXTS:
        pic_idx = _find_attached_pic(video_path)
        if pic_idx is None:
            return
        tmp = str(Path(video_path).with_suffix(".poster_rm_tmp.mp4"))
        try:
            result = subprocess.run(
                [
                    "ffmpeg", "-y", "-i", video_path,
                    "-map", "0", f"-map", f"-0:{pic_idx}",
                    "-map_metadata", "0",
                    "-c", "copy", tmp,
                ],
                capture_output=True, timeout=60,
            )
            if result.returncode != 0:
                raise RuntimeError(result.stderr.decode(errors='ignore')[-300:])
            os.replace(tmp, video_path)
        except Exception:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise
    else:
        raise RuntimeError("Remove poster is only supported for MKV and MP4 files")


def full_attach(video_path: str, poster_path: str) -> str:
    p = Path(video_path)
    ext = p.suffix.lower()

    if ext in MKV_COMPAT_EXTS:
        attach_poster_mkv(video_path, poster_path)
        return video_path

    if ext in MP4_COMPAT_EXTS:
        attach_poster_mp4(video_path, poster_path)
        return video_path

    mkv = to_mkv(video_path)
    attach_poster_mkv(mkv, poster_path)
    return mkv
