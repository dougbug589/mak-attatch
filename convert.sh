#!/bin/bash
#
# Interactive single-file poster helper.
#
# All work is done by mak-attatch-cli, so this script gets the same safety as
# the app: verified MP4/MOV/M4V rewrites that never replace the original with
# a broken file, cover replacement that keeps other MKV attachments, no
# full-file MKV copy just to remove a poster, and hardlink-safe MKV edits.
set -euo pipefail
shopt -s nocasematch

HERE="$(cd "$(dirname "$0")" && pwd)"
VIDEO_EXTS="mkv|avi|mp4|mov|webm|flv|wmv|ts|m4v|mpeg|mpg"
IMAGE_EXTS="jpg|jpeg|png|bmp|webp|gif|tiff|tif"

if command -v mak-attatch-cli >/dev/null 2>&1; then
    CLI=(mak-attatch-cli)
elif [[ -x "$HERE/.venv/bin/python" ]]; then
    CLI=("$HERE/.venv/bin/python" "$HERE/cli.py")
else
    CLI=(python3 "$HERE/cli.py")
fi

ask_path() {  # $1 = prompt, $2 = extension regex; prints the chosen path
    local prompt="$1" exts="$2" path
    while true; do
        read -rp "$prompt" path
        [[ -z "$path" ]] && continue
        path="${path/#\~/$HOME}"
        if [[ ! -f "$path" ]]; then
            echo "Error: file not found" >&2
            continue
        fi
        if [[ ! "$path" =~ \.($exts)$ ]]; then
            echo "Error: unsupported file extension" >&2
            continue
        fi
        printf '%s\n' "$path"
        return
    done
}

while true; do
    read -rp "Add or remove poster? (add/remove): " CHOICE
    case "$CHOICE" in
        add|remove) break ;;
        *) echo "Error: enter 'add' or 'remove'" ;;
    esac
done

VIDEO="$(ask_path "Video file path: " "$VIDEO_EXTS")"

if [[ "$CHOICE" == "remove" ]]; then
    "${CLI[@]}" remove -f "$VIDEO"
    echo "Done"
    exit 0
fi

POSTER="$(ask_path "Poster/cover art path: " "$IMAGE_EXTS")"
ARGS=(attach -f "$VIDEO" -p "$POSTER")

# MP4/MOV/M4V take a cover natively; other containers are remuxed to MKV
# (losslessly, keeping the original) by the CLI itself.
if [[ "$VIDEO" =~ \.(mp4|mov|m4v)$ ]]; then
    read -rp "Also convert to MKV (keeps the original)? (y/N): " TO_MKV
    [[ "$TO_MKV" == "y" ]] && ARGS+=(--to-mkv)
fi

"${CLI[@]}" "${ARGS[@]}"
echo "Done"
