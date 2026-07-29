#!/bin/bash

VIDEO_EXTS="mkv|avi|mp4|mov|webm|flv|wmv|ts|m4v|mpeg|mpg"
IMAGE_EXTS="jpg|jpeg|png|bmp|webp|gif|tiff"

if ! command -v ffmpeg &>/dev/null; then
    echo "Error: ffmpeg not found"
    exit 1
fi

if ! command -v mkvpropedit &>/dev/null; then
    echo "Error: mkvpropedit not found"
    exit 1
fi

while true; do
    read -p "Add or remove poster? (add/remove): " CHOICE
    case "$CHOICE" in
        add|remove) break ;;
        *) echo "Error: enter 'add' or 'remove'" ;;
    esac
done

while true; do
    read -p "Video file path: " VIDEO
    [[ -z "$VIDEO" ]] && continue
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
        read -p "$OUT already exists. Overwrite? (y/n): " CONFIRM
        [[ "$CONFIRM" != "y" ]] && echo "Aborted" && exit 1
    fi
    echo "Video not in mkv, converting to mkv..."
    ffmpeg -i "$VIDEO" -codec copy "$OUT"
    echo "Video converted to $OUT"
else
    OUT="$VIDEO"
    echo "Video already in mkv, skipping"
fi

if [[ "$CHOICE" == "add" ]]; then
    while true; do
        read -p "Poster/cover art path: " POSTER
        [[ -z "$POSTER" ]] && continue
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

    if [[ "$POSTER" != *.jpg ]]; then
        OUT_P="${POSTER%.*}.jpg"
        if [[ -f "$OUT_P" ]]; then
            read -p "$OUT_P already exists. Overwrite? (y/n): " CONFIRM
            [[ "$CONFIRM" != "y" ]] && echo "Aborted" && exit 1
        fi
        echo "Image not in jpg, converting to jpg..."
        ffmpeg -i "$POSTER" "$OUT_P"
        echo "Image converted to $OUT_P"
    else
        OUT_P="$POSTER"
        echo "Image already in jpg, skipping"
    fi

    echo "Attaching poster to video..."
    mkvpropedit "$OUT" --attachment-mime-type image/jpeg --attachment-name cover.jpg --add-attachment "$OUT_P"
    echo "Poster attached to video"
else
    echo "Removing poster from video..."
    mkvpropedit "$OUT" --delete-attachment name:cover.jpg
    echo "Poster removed from video"
fi

echo "Done"
