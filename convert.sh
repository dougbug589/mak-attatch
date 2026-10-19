#!/bin/bash
#
# Standalone single-file poster helper. All edits go through mkvpropedit, and
# a failed ffmpeg remux never publishes a partial .mkv or continues to attach
# a poster to a broken file.
set -euo pipefail

VIDEO_EXTS="mkv|avi|mp4|mov|webm|flv|wmv|ts|m4v|mpeg|mpg"
IMAGE_EXTS="jpg|jpeg|png|bmp|webp|gif|tiff|tif"

if ! command -v ffmpeg &>/dev/null; then
    echo "Error: ffmpeg not found" >&2
    exit 1
fi

if ! command -v mkvpropedit &>/dev/null; then
    echo "Error: mkvpropedit not found" >&2
    exit 1
fi

while true; do
    read -rp "Add or remove poster? (add/remove): " CHOICE
    case "$CHOICE" in
        add|remove) break ;;
        *) echo "Error: enter 'add' or 'remove'" ;;
    esac
done

while true; do
    read -rp "Video file path: " VIDEO
    [[ -z "$VIDEO" ]] && continue
    VIDEO="${VIDEO/#\~/$HOME}"
    if [[ ! -f "$VIDEO" ]]; then
        echo "Error: file not found"
        continue
    fi
    if [[ ! "$VIDEO" =~ \.($VIDEO_EXTS)$ ]]; then
        echo "Error: not a video file extension"
        continue
    fi
    break
done

if [[ "$VIDEO" != *.mkv ]]; then
    OUT="${VIDEO%.*}.mkv"
    if [[ -f "$OUT" ]]; then
        read -rp "$OUT already exists. Overwrite? (y/n): " CONFIRM
        if [[ "$CONFIRM" != "y" ]]; then
            echo "Aborted"
            exit 1
        fi
    fi
    TMP_OUT="${OUT%.mkv}.part.$$.mkv"
    echo "Video not in mkv, converting to mkv..."
    if ! ffmpeg -nostdin -i "$VIDEO" -map 0 -c copy "$TMP_OUT"; then
        rm -f "$TMP_OUT"
        echo "Error: ffmpeg failed; $OUT was not written" >&2
        exit 1
    fi
    mv -f "$TMP_OUT" "$OUT"
    echo "Video converted to $OUT"
else
    OUT="$VIDEO"
    echo "Video already in mkv, skipping"
fi

# Remove any cover images this script may have created. Each delete is allowed
# to fail when that name is absent; the final add/remove is the real operation.
delete_covers() {
    local changed=0
    local name
    for name in cover.jpg cover.jpeg cover.png cover.webp cover.gif cover.bmp cover.tiff; do
        if mkvpropedit "$OUT" --delete-attachment "name:$name" >/dev/null 2>&1; then
            changed=1
        fi
    done
    return "$((1 - changed))"
}

if [[ "$CHOICE" == "add" ]]; then
    while true; do
        read -rp "Poster/cover art path: " POSTER
        [[ -z "$POSTER" ]] && continue
        POSTER="${POSTER/#\~/$HOME}"
        if [[ ! -f "$POSTER" ]]; then
            echo "Error: file not found"
            continue
        fi
        if [[ ! "$POSTER" =~ \.($IMAGE_EXTS)$ ]]; then
            echo "Error: not an image file extension"
            continue
        fi
        break
    done

    case "${POSTER,,}" in
        *.jpg|*.jpeg) MIME="image/jpeg"; NAME="cover.jpg" ;;
        *.png) MIME="image/png"; NAME="cover.png" ;;
        *.webp) MIME="image/webp"; NAME="cover.webp" ;;
        *.gif) MIME="image/gif"; NAME="cover.gif" ;;
        *.bmp) MIME="image/bmp"; NAME="cover.bmp" ;;
        *.tiff|*.tif) MIME="image/tiff"; NAME="cover.tiff" ;;
        *) echo "Error: unsupported image type" >&2; exit 1 ;;
    esac

    echo "Attaching poster to video..."
    delete_covers || true
    if ! mkvpropedit "$OUT" \
        --attachment-mime-type "$MIME" \
        --attachment-name "$NAME" \
        --add-attachment "$POSTER"; then
        echo "Error: failed to attach poster" >&2
        exit 1
    fi
    echo "Poster attached to video"
else
    echo "Removing poster from video..."
    if delete_covers; then
        echo "Poster removed from video"
    else
        echo "No cover attachment found"
    fi
fi

echo "Done"
