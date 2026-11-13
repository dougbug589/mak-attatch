import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

REQUIRED_TOOLS = ("ffmpeg", "ffprobe", "mkvpropedit", "mkvmerge")


def check_tools() -> list[str]:
    """Names of required media tools that are not on PATH.

    ffprobe and mkvmerge are used for probing and cover detection; without
    them operations failed later with a bare "[Errno 2]".
    """
    return [tool for tool in REQUIRED_TOOLS if not shutil.which(tool)]


def _validate_path(path: str, allowed_suffixes: set = None) -> Path:
    """Resolve a user-supplied path to an existing file.

    Callers must pass the *returned* absolute path to external tools. An
    absolute path can never start with '-' (option injection) or '@'
    (mkvtoolnix option file), so no name-based filtering is needed; earlier
    '..' / leading-'-' checks rejected real titles such as
    "Tick, Tick... Boom! (2021).mkv".
    """
    p = Path(path).resolve()
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
MP4_COMPAT_EXTS = {".mp4", ".mov", ".m4v"}

# mkvpropedit edits in place; never SIGKILL it mid-write on a slow mount.
MKVPROPEDIT_TIMEOUT = 600
# Full-file ffmpeg rewrites are I/O bound; allow >= 5 MB/s before giving up.
_MIN_REWRITE_TIMEOUT = 300
_MIN_REWRITE_RATE = 5 * 1024 * 1024


def _rewrite_timeout(size: int) -> int:
    return max(_MIN_REWRITE_TIMEOUT, int(size / _MIN_REWRITE_RATE))


def _rewrite_temp(video_path: str, tag: str) -> str:
    """Hidden, non-video-named sibling temp file for a full rewrite.

    Media servers and this app's own scanner index files by video extension,
    so a half-written or orphaned ``.tmp.mp4`` would show up in libraries.
    The output format is always passed explicitly (``-f mp4``).
    """
    return _secure_temp_in_dir(os.path.dirname(video_path), ".part", prefix=f".{tag}-")


def _isobmff_output_opts(src: Path) -> list[str]:
    """Muxer options for rewriting an MP4/MOV/M4V file.

    ffmpeg's MOV and iPod (m4v) muxers silently drop attached_pic/covr, so
    always write with the MP4 muxer. For MOV/M4V keep the source major brand
    so QuickTime/iTunes/camera files stay what they were.
    """
    ext = src.suffix.lower()
    opts = ["-f", "mp4"]
    if ext in (".mov", ".m4v"):
        fallback = "qt  " if ext == ".mov" else "M4V "
        opts += ["-brand", _probe_major_brand(str(src)) or fallback]
    if _is_faststart(str(src)):
        # Keep web/DLNA progressive playback working: ffmpeg would otherwise
        # move the index to the end of the file.
        opts += ["-movflags", "+faststart"]
    return opts


_INVALID_TEXT_RE = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff]")


def _clean_text(value) -> str:
    """Drop characters XML cannot carry (and NUL, which argv cannot either).

    TMDB text occasionally contains stray control characters; left in, they
    make mkvpropedit reject the tags file or ffmpeg's argv invalid.
    """
    return _INVALID_TEXT_RE.sub("", str(value))


def _require_writable(p: Path) -> None:
    # os.replace would happily swap out a read-only file; respect the bit.
    if not os.access(p, os.W_OK):
        raise RuntimeError(f"{p.name} is read-only; not modifying it")


def _is_faststart(path: str) -> bool:
    """True when the MP4 index (moov) sits before the media data (mdat)."""
    try:
        with open(path, "rb") as f:
            while True:
                header = f.read(8)
                if len(header) < 8:
                    return False
                size = int.from_bytes(header[:4], "big")
                kind = header[4:8]
                if kind == b"moov":
                    return True
                if kind == b"mdat":
                    return False
                if size == 1:
                    size = int.from_bytes(f.read(8), "big")
                    f.seek(size - 16, os.SEEK_CUR)
                elif size < 8:
                    return False
                else:
                    f.seek(size - 8, os.SEEK_CUR)
    except OSError:
        return False


def _require_free_space(p: Path, factor: float = 1.05) -> None:
    if shutil.disk_usage(p.parent).free < p.stat().st_size * factor:
        raise RuntimeError(f"Not enough free space in {p.parent} to rewrite {p.name}")


def _run_mkvpropedit(cmd: list[str]) -> None:
    """Run mkvpropedit; exit 1 means warnings, but the changes were written."""
    result = subprocess.run(cmd, capture_output=True, timeout=MKVPROPEDIT_TIMEOUT)
    if result.returncode not in (0, 1):
        # mkvtoolnix prints its errors on stdout.
        out = (result.stdout + result.stderr).decode(errors="ignore").strip()
        raise RuntimeError(f"mkvpropedit failed: {out[-500:] or f'exit {result.returncode}'}")


def _mkvpropedit(p: Path, args: list[str]) -> None:
    """Run mkvpropedit on an MKV without touching other hard links to it.

    mkvpropedit edits the inode in place. With a hardlinked file (typical
    for torrent clients + media managers) that also changes the seeding
    copy and breaks its piece hashes. In that case edit a private copy and
    swap it in, which leaves the other links with the original bytes.
    """
    _require_writable(p)
    if p.stat().st_nlink <= 1:
        _run_mkvpropedit(["mkvpropedit", str(p), *args])
        return
    _require_free_space(p)
    tmp = _rewrite_temp(str(p), "mkvedit")
    try:
        shutil.copyfile(p, tmp)
        _run_mkvpropedit(["mkvpropedit", tmp, *args])
        _publish_preserving_metadata(tmp, str(p))
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)

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
        ET.SubElement(simple, "String").text = _clean_text(value)


def _is_series(metadata: dict) -> bool:
    """TMDB TV details describe the whole show, not the episode in the file."""
    return metadata.get("media_type") == "tv"


def build_mkv_tags_xml(metadata: dict) -> str:
    root = ET.Element("Tags")
    tag = ET.SubElement(root, "Tag")
    targets = ET.SubElement(tag, "Targets")
    # Matroska target levels: 50 = movie/episode, 70 = collection (the show).
    # Series details must not masquerade as the episode's own title/synopsis.
    ET.SubElement(targets, "TargetTypeValue").text = "70" if _is_series(metadata) else "50"

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
        ET.SubElement(simple, "String").text = _clean_text(actor["name"])
        if actor.get("character"):
            child = ET.SubElement(simple, "Simple")
            ET.SubElement(child, "Name").text = "CHARACTER"
            ET.SubElement(child, "String").text = _clean_text(actor["character"])

    return ET.tostring(root, encoding="unicode", xml_declaration=False)


def write_metadata_mkv(video_path: str, metadata: dict):
    p = _validate_path(video_path, VIDEO_EXTS)
    tags_path = None
    try:
        fd, tags_path = tempfile.mkstemp(suffix=".xml")
        os.close(fd)
        os.chmod(tags_path, 0o600)
        with open(tags_path, "w", encoding="utf-8") as f:
            f.write(build_mkv_tags_xml(metadata))

        args = []
        # The segment title is the episode's own title for TV files; only a
        # movie's TMDB title belongs there.
        if metadata.get("title") and not _is_series(metadata):
            args += ["--edit", "info", "--set", f"title={_clean_text(metadata['title'])}"]
        # Global tags only: `all:` also replaces track-level tags/statistics.
        args += ["--tags", f"global:{tags_path}"]
        _mkvpropedit(p, args)
    finally:
        if tags_path:
            try:
                os.unlink(tags_path)
            except OSError:
                pass


def _mp4_metadata_flags(metadata: dict) -> list[str]:
    """ffmpeg -metadata arguments, with characters argv cannot carry removed."""
    return [_clean_text(arg) for arg in _raw_mp4_metadata_flags(metadata)]


def _raw_mp4_metadata_flags(metadata: dict) -> list[str]:
    flags = []
    if _is_series(metadata):
        # Show-level data goes into the TV-show atom; the episode's own
        # title, air date and description are left alone.
        if metadata.get("title"):
            flags += ["-metadata", f"show={metadata['title']}"]
        if metadata.get("genres"):
            flags += ["-metadata", f"genre={', '.join(metadata['genres'])}"]
        return flags
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


def _ffmpeg_rewrite(p: Path, tag: str, args: list[str], expected_streams: int) -> None:
    """Rewrite an MP4/MOV/M4V file via a verified, fsynced sibling temp file.

    ``args`` are the ffmpeg inputs/mapping/codec options; the muxer options
    and output path are added here so every rewrite path behaves the same.
    The original is only replaced after the output has been verified.
    """
    _require_writable(p)
    _require_free_space(p)
    muxer = _isobmff_output_opts(p)
    tmp = _rewrite_temp(str(p), tag)
    try:
        result = subprocess.run(
            ["ffmpeg", "-y", "-nostdin", *args, *muxer, tmp],
            capture_output=True, timeout=_rewrite_timeout(p.stat().st_size),
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.decode(errors="ignore")[-300:] or "ffmpeg failed")
        _verify_rewrite(str(p), tmp, expected_streams)
        _publish_preserving_metadata(tmp, str(p))
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


# `-map_metadata:g -1` drops only the *global* tags. A bare `-map_metadata -1`
# would also wipe per-stream and per-chapter metadata (audio/subtitle
# languages, track titles, chapter names) on every metadata write.
_DROP_GLOBAL_METADATA = ["-map_metadata:g", "-1"]


def write_metadata_mp4(video_path: str, metadata: dict):
    p = _validate_path(video_path, VIDEO_EXTS)
    # A movie's tags are replaced wholesale so stale ones don't linger. For a
    # TV episode keep its own global tags (title, air date, description) and
    # only add the show-level ones.
    reset = [] if _is_series(metadata) else _DROP_GLOBAL_METADATA
    _ffmpeg_rewrite(
        p, "meta",
        ["-i", str(p), "-map", "0", *reset,
         *_mp4_metadata_flags(metadata), "-c", "copy"],
        expected_streams=len(_probe_streams(str(p))),
    )


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
        # `global:` with no file removes the global tags only; `all:` would
        # also delete mkvmerge's per-track statistics tags.
        _mkvpropedit(p, ["--edit", "info", "--delete", "title", "--tags", "global:"])
    elif ext in MP4_COMPAT_EXTS:
        _ffmpeg_rewrite(
            p, "meta-rm",
            ["-i", video_path, "-map", "0", *_DROP_GLOBAL_METADATA, "-c", "copy"],
            expected_streams=len(_probe_streams(video_path)),
        )
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
        if result.returncode in (0, 1):  # 1 = warnings
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


def _probe_duration(path: str) -> float | None:
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", path],
            capture_output=True, text=True, timeout=60,
        )
        return float(result.stdout.strip())
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def _verify_rewrite(src: str, tmp: str, expected_streams: int) -> None:
    """Refuse to publish a rewrite that lost streams or got truncated.

    ffmpeg can exit 0 after a mid-file demux error and leave a shorter file,
    which would otherwise silently replace the user's original.
    """
    got = len(_probe_streams(tmp))
    if got != expected_streams:
        raise RuntimeError(
            f"Rewrite verification failed: expected {expected_streams} streams, got {got}"
        )
    d_src, d_out = _probe_duration(src), _probe_duration(tmp)
    if d_src and d_out is not None and abs(d_src - d_out) > max(1.0, d_src * 0.005):
        raise RuntimeError(
            f"Rewrite verification failed: duration {d_out:.1f}s vs original {d_src:.1f}s"
        )


def _fsync_file(path: str) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _fsync_dir(path: str) -> None:
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return  # some filesystems cannot open directories
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def _publish_preserving_metadata(tmp: str, dest: str) -> None:
    """Atomically replace dest while keeping its mode, timestamps and owner.

    The new data is fsynced before the rename so a crash or power loss
    cannot leave a zero-length file in place of the original.
    """
    _fsync_file(tmp)
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
    _fsync_dir(os.path.dirname(os.path.abspath(dest)))


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

    # Put the MKV next to the path the user gave: for a symlinked library
    # entry that is the library folder, not wherever the target lives.
    given = Path(os.path.abspath(os.path.expanduser(video_path)))
    out = str(given.with_suffix(".mkv"))
    if os.path.lexists(out):
        raise RuntimeError(f"Target already exists, refusing to overwrite: {out}")

    src_stat = p.stat()
    if shutil.disk_usage(given.parent).free < src_stat.st_size * 1.05:
        raise RuntimeError(f"Not enough free space in {given.parent} to remux {p.name}")

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
    tmp = _secure_temp_in_dir(str(given.parent), ".mkv.part", prefix=".remux-")
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
    args = []
    for old in _cover_attachment_names(str(p)):
        args += ["--delete-attachment", f"name:{old}"]
    args += [
        "--attachment-mime-type", mime,
        "--attachment-name", name,
        "--add-attachment", str(poster),
    ]
    _mkvpropedit(p, args)


def attach_poster_mp4(video_path: str, poster_path: str, metadata: dict = None):
    p = _validate_path(video_path, VIDEO_EXTS)
    poster = _validate_path(poster_path, IMAGE_EXTS)
    video_path = str(p)

    # Rebuild the file once: old cover out, new cover in. This avoids the
    # previous remove-then-add sequence, so a failed ffmpeg run leaves the
    # original file untouched.
    pic_idx = _find_attached_pic(video_path)
    src_streams = _probe_streams(video_path)
    video_count = sum(1 for s in src_streams if s.get("codec_type") == "video")
    poster_index = video_count - (1 if pic_idx is not None else 0)

    poster_codec = next(
        (s.get("codec_name") for s in _probe_streams(str(poster))
         if s.get("codec_type") == "video"),
        "",
    )
    # MP4 attached_pic supports JPEG and PNG directly. GIF/WebP/TIFF/BMP are
    # not valid MP4 cover codecs, so transcode those to JPEG.
    poster_encoder = "copy" if poster_codec in ("mjpeg", "png") else "mjpeg"

    args = [
        "-i", video_path,
        "-i", str(poster),
        "-map", "0",
    ]
    if pic_idx is not None:
        args += ["-map", f"-0:{pic_idx}"]
    args += [
        "-map", "1",
        "-c", "copy",
        f"-c:v:{poster_index}", poster_encoder,
        f"-disposition:v:{poster_index}", "attached_pic",
        f"-metadata:s:v:{poster_index}", "comment=Cover (front)",
    ]
    if metadata:
        args += _mp4_metadata_flags(metadata)
    expected = len(src_streams) - (1 if pic_idx is not None else 0) + 1
    _ffmpeg_rewrite(p, "poster", args, expected_streams=expected)


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
        args = []
        for name in names:
            args += ["--delete-attachment", f"name:{name}"]
        _mkvpropedit(p, args)
    elif ext in MP4_COMPAT_EXTS:
        video_path = str(p)
        pic_idx = _find_attached_pic(video_path)
        if pic_idx is None:
            return
        _ffmpeg_rewrite(
            p, "poster-rm",
            ["-i", video_path, "-map", "0", "-map", f"-0:{pic_idx}",
             "-map_metadata", "0", "-c", "copy"],
            expected_streams=len(_probe_streams(video_path)) - 1,
        )
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
        target = p.with_suffix(".mkv")
        if os.path.lexists(target):
            # Check before touching the source: otherwise every rescan fully
            # rewrites the MP4 and only then fails on the existing MKV.
            raise RuntimeError(f"Already converted, skipping: {target.name} exists")
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
