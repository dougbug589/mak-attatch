import os
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path


def check_tools():
    missing = []
    if not shutil.which("ffmpeg"):
        missing.append("ffmpeg")
    if not shutil.which("mkvpropedit"):
        missing.append("mkvtoolnix (mkvpropedit)")
    return missing


def _validate_path(path: str, allowed_suffixes: set = None) -> Path:
    if path.startswith("-"):
        raise ValueError(f"Path starts with '-', possible argument injection: {path}")
    raw = Path(path)
    if ".." in str(raw):
        raise ValueError(f"Path traversal detected: {path}")
    p = raw.resolve()
    if not p.exists():
        raise FileNotFoundError(f"File not found: {path}")
    if not p.is_file():
        raise ValueError(f"Not a file: {path}")
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


def _add_simple(parent: ET.Element, name: str, value: str):
    simple = ET.SubElement(parent, "Simple")
    ET.SubElement(simple, "Name").text = name
    if value:
        ET.SubElement(simple, "String").text = str(value)


def build_mkv_tags_xml(metadata: dict) -> str:
    root = ET.Element("Tags")
    tag = ET.SubElement(root, "Tag")
    targets = ET.SubElement(tag, "Targets")
    ET.SubElement(targets, "TargetTypeValue").text = "50"

    if metadata.get("title"):
        _add_simple(tag, "TITLE", metadata["title"])
    if metadata.get("year"):
        _add_simple(tag, "DATE_RELEASED", metadata["year"])
    if metadata.get("genres"):
        _add_simple(tag, "GENRE", ", ".join(metadata["genres"]))
    if metadata.get("rating"):
        _add_simple(tag, "RATING", f"{metadata['rating']:.1f}")
    if metadata.get("tagline"):
        _add_simple(tag, "COMMENT", metadata["tagline"])
    if metadata.get("overview"):
        _add_simple(tag, "SYNOPSIS", metadata["overview"])

    for role in ("directors", "writers", "creators"):
        for name in metadata.get(role) or []:
            tag_name = "DIRECTOR" if role == "directors" else "WRITTEN_BY"
            _add_simple(tag, tag_name, name)

    for actor in metadata.get("cast") or []:
        simple = ET.SubElement(tag, "Simple")
        ET.SubElement(simple, "Name").text = "ACTOR"
        ET.SubElement(simple, "String").text = str(actor["name"])
        if actor.get("character"):
            child = ET.SubElement(simple, "Simple")
            ET.SubElement(child, "Name").text = "CHARACTER"
            ET.SubElement(child, "String").text = str(actor["character"])

    return ET.tostring(root, encoding="unicode", xml_declaration=False)


def write_metadata_mkv(video_path: str, metadata: dict):
    _validate_path(video_path, VIDEO_EXTS)
    tags_path = None
    try:
        fd, tags_path = tempfile.mkstemp(suffix=".xml")
        os.close(fd)
        os.chmod(tags_path, 0o600)
        with open(tags_path, "w", encoding="utf-8") as f:
            f.write(build_mkv_tags_xml(metadata))

        cmd = ["mkvpropedit", video_path]
        if metadata.get("title"):
            cmd += ["--edit", "info", "--set", f"title={metadata['title']}"]
        cmd += ["--tags", f"all:{tags_path}"]
        subprocess.run(cmd, check=True, capture_output=True, timeout=60)
    finally:
        if tags_path:
            try:
                os.unlink(tags_path)
            except OSError:
                pass


def _mp4_metadata_flags(metadata: dict) -> list[str]:
    flags = []
    if metadata.get("title"):
        flags += ["-metadata", f"title={metadata['title']}"]
    if metadata.get("year"):
        flags += ["-metadata", f"date={metadata['year']}"]
    if metadata.get("overview"):
        flags += ["-metadata", f"description={metadata['overview']}"]
    if metadata.get("genres"):
        flags += ["-metadata", f"genre={', '.join(metadata['genres'])}"]
    if metadata.get("tagline"):
        flags += ["-metadata", f"comment={metadata['tagline']}"]
    directors = ", ".join(metadata.get("directors") or [])
    if directors:
        flags += ["-metadata", f"author={directors}"]
    return flags


def write_metadata_mp4(video_path: str, metadata: dict):
    _validate_path(video_path, VIDEO_EXTS)
    tmp = str(Path(video_path).with_suffix(".meta_tmp.mp4"))
    try:
        result = subprocess.run(
            [
                "ffmpeg", "-y", "-i", video_path,
                "-map", "0",
                "-map_metadata", "-1",
                *_mp4_metadata_flags(metadata),
                "-c", "copy",
                tmp,
            ],
            capture_output=True, timeout=300,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.decode(errors='ignore')[-300:])
        os.replace(tmp, video_path)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def write_metadata(video_path: str, metadata: dict):
    ext = Path(video_path).suffix.lower()
    if ext in MKV_COMPAT_EXTS:
        write_metadata_mkv(video_path, metadata)
    elif ext in MP4_COMPAT_EXTS:
        write_metadata_mp4(video_path, metadata)
    else:
        raise RuntimeError("Metadata writing is only supported for MKV and MP4 files")


def remove_metadata(video_path: str):
    _validate_path(video_path, VIDEO_EXTS)
    ext = Path(video_path).suffix.lower()
    if ext in MKV_COMPAT_EXTS:
        subprocess.run(
            ["mkvpropedit", video_path, "--edit", "info", "--delete", "title", "--tags", "all:"],
            check=True, capture_output=True, timeout=60,
        )
    elif ext in MP4_COMPAT_EXTS:
        tmp = str(Path(video_path).with_suffix(".meta_rm_tmp.mp4"))
        try:
            result = subprocess.run(
                [
                    "ffmpeg", "-y", "-i", video_path,
                    "-map", "0",
                    "-map_metadata", "-1",
                    "-c", "copy",
                    tmp,
                ],
                capture_output=True, timeout=300,
            )
            if result.returncode != 0:
                raise RuntimeError(result.stderr.decode(errors='ignore')[-300:])
            os.replace(tmp, video_path)
        except Exception:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise
    else:
        raise RuntimeError("Metadata removal is only supported for MKV and MP4 files")


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
            "--attachment-name", "cover.jpg",
            "--add-attachment", poster_path,
        ],
        check=True, capture_output=True, timeout=60,
    )


def attach_poster_mp4(video_path: str, poster_path: str, metadata: dict = None):
    _validate_path(video_path, VIDEO_EXTS)
    _validate_path(poster_path, IMAGE_EXTS)
    remove_poster(video_path)
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-i", poster_path,
        "-map", "0", "-map", "1",
        "-c", "copy",
        "-disposition:v:1", "attached_pic",
    ]
    if metadata:
        cmd += _mp4_metadata_flags(metadata)
    cmd += [video_path + ".tmp.mp4"]
    subprocess.run(
        cmd,
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
    IMAGE_CODECS = {"mjpeg", "png", "bmp", "gif", "webp", "tiff"}
    video_count = 0
    for s in streams:
        if s.get("codec_type") == "video":
            video_count += 1
    if video_count < 2:
        return None
    for s in streams:
        if s.get("codec_type") == "video" and s.get("codec_name") in IMAGE_CODECS:
            return s["index"]
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
        cmd = ["mkvpropedit", video_path]
        for mt in sorted(set(MIME_MAP.values())):
            cmd += ["--delete-attachment", f"mime-type:{mt}"]
        result = subprocess.run(cmd, capture_output=True, timeout=60)
        if result.returncode != 0:
            stderr = result.stderr.decode(errors='ignore').lower()
            if stderr and "no attachment matched" not in stderr:
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


def full_attach(video_path: str, poster_path: str, metadata: dict = None) -> str:
    p = Path(video_path)
    ext = p.suffix.lower()

    if ext in MKV_COMPAT_EXTS:
        attach_poster_mkv(video_path, poster_path)
        if metadata:
            write_metadata_mkv(video_path, metadata)
        return video_path

    if ext in MP4_COMPAT_EXTS:
        attach_poster_mp4(video_path, poster_path, metadata=metadata)
        return video_path

    mkv = to_mkv(video_path)
    attach_poster_mkv(mkv, poster_path)
    if metadata:
        write_metadata_mkv(mkv, metadata)
    return mkv
