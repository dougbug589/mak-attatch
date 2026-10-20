import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path


def _ensure_windows_tool_path() -> None:
    """Make media tools resolvable on Windows from a stale terminal.

    winget installs Gyan.FFmpeg and MKVToolNix without refreshing the PATH
    of already-open terminals, so the GUI can be launched from a session
    whose PATH lacks the install directories. Prepend the known locations
    so check_tools() and subprocess calls find the tools anyway.
    """
    if sys.platform != "win32":
        return
    dirs = []
    for var in ("ProgramFiles", "ProgramFiles(x86)"):
        base = os.environ.get(var)
        if base:
            dirs.append(os.path.join(base, "MKVToolNix"))
    local = os.environ.get("LOCALAPPDATA")
    if local:
        dirs.append(os.path.join(local, "Microsoft", "WinGet", "Links"))
    path = os.environ.get("PATH", "")
    for d in dirs:
        if d and os.path.isdir(d) and d not in path:
            path = d + os.pathsep + path
    os.environ["PATH"] = path


_ensure_windows_tool_path()


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


def _sibling_temp(video_path: str, suffix: str, prefix: str = "tmp") -> str:
    """Random temp file in the video's own directory (same filesystem)."""
    return _secure_temp_in_dir(os.path.dirname(video_path), suffix, prefix)


def _secure_temp_in_dir(directory: str, suffix: str, prefix: str = "tmp") -> str:
    fd, path = tempfile.mkstemp(dir=directory, suffix=suffix, prefix=prefix)
    os.close(fd)
    os.chmod(path, 0o600)
    return path


VIDEO_EXTS = {
    ".mkv", ".avi", ".mp4", ".mov", ".webm", ".flv", ".wmv", ".ts", ".m4v",
    ".mpeg", ".mpg",
}
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
    """Detect the image MIME type from magic bytes, falling back to extension."""
    try:
        with open(image_path, "rb") as f:
            head = f.read(12)
    except OSError:
        head = b""
    if head[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if head[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    if head[:2] == b"BM":
        return "image/bmp"
    if head[:4] in (b"II*\x00", b"MM\x00*"):
        return "image/tiff"
    ext = Path(image_path).suffix.lower()
    return MIME_MAP.get(ext, "image/jpeg")


def _image_ext_for_mime(mime: str) -> str:
    return {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/gif": ".gif",
        "image/webp": ".webp",
        "image/bmp": ".bmp",
        "image/tiff": ".tiff",
    }.get(mime, ".jpg")


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
        # Global tags only: `all:` also replaces track-level tags/statistics.
        cmd += ["--tags", f"global:{tags_path}"]
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
    p = _validate_path(video_path, VIDEO_EXTS)
    video_path = str(p)
    tmp = _sibling_temp(video_path, f".meta_tmp{p.suffix}")
    try:
        result = subprocess.run(
            [
                "ffmpeg", "-y", "-nostdin", "-i", video_path,
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
        _publish_preserving_metadata(tmp, video_path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def write_metadata(video_path: str, metadata: dict):
    ext = Path(video_path).suffix.lower()
    if ext in MKV_COMPAT_EXTS:
        write_metadata_mkv(video_path, metadata)
    elif ext in MP4_COMPAT_EXTS:
        write_metadata_mp4(video_path, metadata)
    else:
        raise RuntimeError("Metadata writing is only supported for MKV and MP4 files")


def remove_metadata(video_path: str):
    p = _validate_path(video_path, VIDEO_EXTS)
    video_path = str(p)
    ext = p.suffix.lower()
    if ext in MKV_COMPAT_EXTS:
        subprocess.run(
            ["mkvpropedit", video_path, "--edit", "info", "--delete", "title", "--tags", "all:"],
            check=True, capture_output=True, timeout=60,
        )
    elif ext in MP4_COMPAT_EXTS:
        tmp = _sibling_temp(video_path, f".meta_rm_tmp{p.suffix}")
        try:
            result = subprocess.run(
                [
                    "ffmpeg", "-y", "-nostdin", "-i", video_path,
                    "-map", "0",
                    "-map_metadata", "-1",
                    "-c", "copy",
                    tmp,
                ],
                capture_output=True, timeout=300,
            )
            if result.returncode != 0:
                raise RuntimeError(result.stderr.decode(errors='ignore')[-300:])
            _publish_preserving_metadata(tmp, video_path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
    else:
        raise RuntimeError("Metadata removal is only supported for MKV and MP4 files")


# Subtitle codecs Matroska stores as-is, and ones that must be converted.
# Anything else is dropped with a warning instead of failing the whole remux.
_MKV_COPY_SUBS = frozenset({
    "subrip", "ass", "ssa", "webvtt",
    "hdmv_pgs_subtitle", "dvd_subtitle", "dvb_subtitle",
})
_MKV_CONVERT_SUBS = {"mov_text": "srt"}  # source codec -> ffmpeg encoder


def _probe_streams(path: str) -> list[dict]:
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", path],
        capture_output=True, timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(
            result.stderr.decode(errors="ignore")[-300:] or "ffprobe failed"
        )
    try:
        return json.loads(result.stdout).get("streams", [])
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Invalid ffprobe output: {e}") from e


def _probe_major_brand(path: str) -> str:
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format_tags=major_brand",
             "-of", "default=nw=1:nk=1", path],
            capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    # Keep trailing spaces: fourcc brands such as "qt  " are exactly 4 chars.
    return result.stdout.rstrip("\r\n")


def _mkv_attachment_names(video_path: str) -> list[str]:
    """Return attachment names via mkvmerge, falling back to ffprobe tags."""
    try:
        result = subprocess.run(
            ["mkvmerge", "-J", video_path],
            capture_output=True, timeout=60,
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            return [
                a["file_name"] for a in data.get("attachments", [])
                if a.get("file_name")
            ]
    except (OSError, json.JSONDecodeError):
        pass

    names = []
    for stream in _probe_streams(video_path):
        tags = {k.lower(): v for k, v in stream.get("tags", {}).items()}
        name = tags.get("filename")
        if name:
            names.append(name)
    return names


def _cover_attachment_names(video_path: str) -> list[str]:
    return [
        name for name in _mkv_attachment_names(video_path)
        if Path(name).name.lower().startswith("cover.")
    ]


def _plan_mkv_streams(
    streams: list[dict], drop_attached_pic: bool = False
) -> tuple[list[tuple[int, str | None]], list[str]]:
    """Decide what happens to each source stream.

    Returns (keep, dropped): keep is [(source_index, encoder_or_None)] in
    source order (None = stream copy); dropped is human-readable strings.
    Pure function, so it can be unit-tested without ffmpeg.
    """
    keep: list[tuple[int, str | None]] = []
    dropped: list[str] = []
    for s in streams:
        idx = s["index"]
        kind = s.get("codec_type")
        codec = s.get("codec_name", "unknown")
        if kind == "video":
            # In full_attach the MP4/MOV cover is reattached to the MKV after
            # remuxing, so carrying the attached_pic stream would duplicate it.
            if drop_attached_pic and s.get("disposition", {}).get("attached_pic"):
                dropped.append(f"cover image #{idx} ({codec}); reattached separately")
            else:
                keep.append((idx, None))
        elif kind in ("audio", "attachment"):
            keep.append((idx, None))
        elif kind == "subtitle":
            if codec in _MKV_COPY_SUBS:
                keep.append((idx, None))
            elif codec in _MKV_CONVERT_SUBS:
                keep.append((idx, _MKV_CONVERT_SUBS[codec]))
            else:
                dropped.append(f"subtitle #{idx} ({codec})")
        else:
            dropped.append(f"{kind or 'unknown'} #{idx} ({codec})")
    return keep, dropped


def _publish_preserving_metadata(tmp: str, dest: str) -> None:
    """Atomically replace dest while keeping its mode, timestamps and owner."""
    st = os.stat(dest)
    if hasattr(os, "chown"):
        try:
            os.chown(tmp, st.st_uid, st.st_gid)
        except OSError:
            pass
    try:
        shutil.copystat(dest, tmp)
    except OSError:
        os.chmod(tmp, stat.S_IMODE(st.st_mode))
    os.replace(tmp, dest)


def _publish_no_clobber(tmp: str, out: str) -> None:
    """Move tmp to out, failing if out already exists.

    ``os.replace`` would silently overwrite an existing file. Linking first
    closes the check-then-replace race: ``os.link`` fails atomically if the
    destination exists.
    """
    exists_msg = f"Target already exists, refusing to overwrite: {out}"
    try:
        os.link(tmp, out)  # atomic, and fails if `out` exists
    except FileExistsError:
        raise RuntimeError(exists_msg) from None
    except OSError:
        # Filesystem without hard links (FAT/exFAT, some network mounts).
        if os.path.lexists(out):
            raise RuntimeError(exists_msg) from None
        os.replace(tmp, out)
        return
    os.unlink(tmp)


def remux_to_mkv(video_path: str, drop_attached_pic: bool = False) -> str:
    p = _validate_path(video_path, VIDEO_EXTS)
    if p.suffix.lower() in MKV_COMPAT_EXTS:
        return video_path  # unchanged: callers compare this with their input

    out = str(p.with_suffix(".mkv"))
    if os.path.lexists(out):
        raise RuntimeError(f"Target already exists, refusing to overwrite: {out}")

    src_stat = p.stat()
    if shutil.disk_usage(p.parent).free < src_stat.st_size * 1.05:
        raise RuntimeError(f"Not enough free space in {p.parent} to remux {p.name}")

    streams = _probe_streams(str(p))
    if not any(s.get("codec_type") in ("video", "audio") for s in streams):
        raise RuntimeError(f"No audio or video streams found in {p.name}")
    keep, dropped = _plan_mkv_streams(streams, drop_attached_pic=drop_attached_pic)
    if dropped:
        print(
            "Warning: not carried into the MKV: " + "; ".join(dropped),
            file=sys.stderr,
        )

    # Hidden, non-.mkv name so library scanners never index a half-written file.
    tmp = _sibling_temp(str(p), ".mkv.part", prefix=".remux-")
    try:
        cmd = ["ffmpeg", "-y", "-nostdin", "-i", str(p)]
        for idx, _ in keep:
            cmd += ["-map", f"0:{idx}"]
        cmd += ["-map_metadata", "0", "-map_chapters", "0", "-c", "copy"]
        for out_idx, (_, encoder) in enumerate(keep):
            if encoder:
                cmd += [f"-c:{out_idx}", encoder]
        cmd += ["-f", "matroska", tmp]

        # Pure stream copy is I/O bound; allow >= 5 MB/s before giving up.
        timeout = max(600, int(src_stat.st_size / (5 * 1024 * 1024)))
        result = subprocess.run(cmd, capture_output=True, timeout=timeout)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.decode(errors="ignore")[-500:])

        if len(_probe_streams(tmp)) != len(keep):
            raise RuntimeError("Remux verification failed: stream count mismatch")

        os.chmod(tmp, stat.S_IMODE(src_stat.st_mode))
        _publish_no_clobber(tmp, out)
        return out
    finally:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass


def attach_poster_mkv(video_path: str, poster_path: str):
    p = _validate_path(video_path, VIDEO_EXTS)
    poster = _validate_path(poster_path, IMAGE_EXTS)
    mime = _get_mime(str(poster))
    name = f"cover{_image_ext_for_mime(mime)}"

    # Remove only covers this app created, then add the new one in the same
    # mkvpropedit invocation. mkvpropedit does not write any changes if an
    # action fails, so a failed add leaves the old cover in place.
    cmd = ["mkvpropedit", str(p)]
    for old in _cover_attachment_names(str(p)):
        cmd += ["--delete-attachment", f"name:{old}"]
    cmd += [
        "--attachment-mime-type", mime,
        "--attachment-name", name,
        "--add-attachment", str(poster),
    ]
    subprocess.run(cmd, check=True, capture_output=True, timeout=60)


def attach_poster_mp4(video_path: str, poster_path: str, metadata: dict = None):
    p = _validate_path(video_path, VIDEO_EXTS)
    poster = _validate_path(poster_path, IMAGE_EXTS)
    video_path = str(p)

    # Rebuild the file once: old cover out, new cover in. This avoids the
    # previous remove-then-add sequence, so a failed ffmpeg run leaves the
    # original file untouched.
    pic_idx = _find_attached_pic(video_path)
    video_count = sum(
        1 for s in _probe_streams(video_path) if s.get("codec_type") == "video"
    )
    poster_index = video_count - (1 if pic_idx is not None else 0)

    poster_codec = next(
        (s.get("codec_name") for s in _probe_streams(str(poster))
         if s.get("codec_type") == "video"),
        "",
    )
    # MP4 attached_pic supports JPEG and PNG directly. GIF/WebP/TIFF/BMP are
    # not valid MP4 cover codecs, so transcode those to JPEG.
    poster_encoder = "copy" if poster_codec in ("mjpeg", "png") else "mjpeg"

    tmp = _sibling_temp(video_path, f".tmp{p.suffix}")
    cmd = [
        "ffmpeg", "-y", "-nostdin",
        "-i", video_path,
        "-i", str(poster),
        "-map", "0",
    ]
    if pic_idx is not None:
        cmd += ["-map", f"-0:{pic_idx}"]
    cmd += [
        "-map", "1",
        "-c", "copy",
        f"-c:v:{poster_index}", poster_encoder,
        f"-disposition:v:{poster_index}", "attached_pic",
        f"-metadata:s:v:{poster_index}", "comment=Cover (front)",
    ]
    if metadata:
        cmd += _mp4_metadata_flags(metadata)
    if p.suffix.lower() == ".mov":
        # ffmpeg's MOV muxer silently drops attached_pic/covr. The MP4 muxer
        # writes the same ISO-BMFF cover atom; keep the source major brand so
        # QuickTime/camera files stay what they were.
        cmd += ["-f", "mp4", "-brand", _probe_major_brand(video_path) or "qt  "]
    cmd += [tmp]
    try:
        subprocess.run(
            cmd,
            check=True, capture_output=True, timeout=120,
        )
        _publish_preserving_metadata(tmp, video_path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _find_attached_pic(video_path: str) -> int | None:
    try:
        video_path = str(_validate_path(video_path, VIDEO_EXTS))
    except (ValueError, FileNotFoundError) as e:
        print(f"Warning: skipping invalid path {video_path}: {e}", file=sys.stderr)
        return None
    try:
        streams = _probe_streams(video_path)
    except RuntimeError:
        return None

    video_streams = [s for s in streams if s.get("codec_type") == "video"]
    for stream in video_streams:
        if stream.get("disposition", {}).get("attached_pic"):
            return stream["index"]

    # Fallback for containers that do not expose the attached_pic flag.
    image_codecs = {"mjpeg", "png", "bmp", "gif", "webp", "tiff"}
    image_streams = [
        s for s in video_streams if s.get("codec_name") in image_codecs
    ]
    if len(image_streams) == 1 and len(video_streams) >= 2:
        return image_streams[0]["index"]
    return None


def remove_poster(video_path: str):
    p = _validate_path(video_path, VIDEO_EXTS)
    ext = p.suffix.lower()
    if ext in MKV_COMPAT_EXTS:
        names = _cover_attachment_names(str(p))
        if not names:
            return
        cmd = ["mkvpropedit", str(p)]
        for name in names:
            cmd += ["--delete-attachment", f"name:{name}"]
        result = subprocess.run(cmd, capture_output=True, timeout=60)
        if result.returncode != 0:
            raise RuntimeError(
                f"Failed to remove poster: {result.stderr.decode(errors='ignore')}"
            )
    elif ext in MP4_COMPAT_EXTS:
        video_path = str(p)
        pic_idx = _find_attached_pic(video_path)
        if pic_idx is None:
            return
        tmp = _sibling_temp(video_path, f".poster_rm_tmp{p.suffix}")
        try:
            out_opts = []
            if ext == ".mov":
                # Match attach_poster_mp4: the MOV muxer would rewrite the brand.
                out_opts = ["-f", "mp4", "-brand",
                            _probe_major_brand(video_path) or "qt  "]
            result = subprocess.run(
                [
                    "ffmpeg", "-y", "-nostdin", "-i", video_path,
                    "-map", "0", "-map", f"-0:{pic_idx}",
                    "-map_metadata", "0",
                    "-c", "copy", *out_opts, tmp,
                ],
                capture_output=True, timeout=120,
            )
            if result.returncode != 0:
                raise RuntimeError(result.stderr.decode(errors='ignore')[-300:])
            _publish_preserving_metadata(tmp, video_path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
    else:
        raise RuntimeError("Remove poster is only supported for MKV and MP4 files")


def full_attach(video_path: str, poster_path: str, metadata: dict = None,
                to_mkv: bool = False) -> str:
    p = Path(video_path)
    ext = p.suffix.lower()

    if ext in MKV_COMPAT_EXTS:
        attach_poster_mkv(video_path, poster_path)
        if metadata:
            write_metadata_mkv(video_path, metadata)
        return video_path

    if to_mkv:
        # Attaching to the MP4 first preserves the existing behaviour of
        # keeping a poster on both files. Non-MP4 sources must be remuxed
        # first: attach_poster_mp4 cannot operate on AVI/WebM/FLV inputs.
        if ext in MP4_COMPAT_EXTS:
            attach_poster_mp4(video_path, poster_path)
        mkv = remux_to_mkv(
            video_path, drop_attached_pic=(ext in MP4_COMPAT_EXTS)
        )
        attach_poster_mkv(mkv, poster_path)
        if metadata:
            write_metadata_mkv(mkv, metadata)
        return mkv

    if ext in MP4_COMPAT_EXTS:
        attach_poster_mp4(video_path, poster_path, metadata=metadata)
        return video_path

    mkv = remux_to_mkv(video_path)
    attach_poster_mkv(mkv, poster_path)
    if metadata:
        write_metadata_mkv(mkv, metadata)
    return mkv
