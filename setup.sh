#!/bin/bash
# mak-attatch setup: creates the venv, installs Python deps, and checks for
# required system packages. By default it only PRINTS install commands and
# does not touch system packages; use --auto-install to opt in.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$HERE/.venv"
DEPS="$HERE/mak_attatch/core/deps.py"
AUTO_INSTALL=0
WITH_TUI=0

usage() {
    echo "Usage: $0 [--auto-install] [--with-tui]"
    echo
    echo "  --auto-install   install missing system packages (asks for sudo)"
    echo "  --with-tui       also set up the optional TUI tools (yazi file browser,"
    echo "                   chafa image previews); on Debian/Ubuntu this adds the"
    echo "                   yazi apt repository"
}

for arg in "$@"; do
    case "$arg" in
        --auto-install) AUTO_INSTALL=1 ;;
        --with-tui) WITH_TUI=1 ;;
        -h|--help) usage; exit 0 ;;
        *)
            echo "Unknown option: $arg" >&2
            usage >&2
            exit 2
            ;;
    esac
done

echo "== mak-attatch setup =="
echo

# --- Python + venv ---------------------------------------------------------
if ! command -v python3 >/dev/null 2>&1; then
    echo "ERROR: python3 not found."
    echo "Install it first, e.g.:  sudo apt install -y python3 python3-venv"
    exit 1
fi

# --- System dependencies -----------------------------------------------------
TUI_FLAG=()
[ "$WITH_TUI" = "1" ] && TUI_FLAG=(--with-tui)

PM="$(python3 "$DEPS" --pm 2>/dev/null || echo unknown)"
INSTALL_CMD="$(python3 "$DEPS" --install-cmd ${TUI_FLAG[@]+"${TUI_FLAG[@]}"} 2>/dev/null || true)"
MISSING=()
while IFS= read -r bin; do
    [ -n "$bin" ] && MISSING+=("$bin")
done < <(python3 "$DEPS" --missing ${TUI_FLAG[@]+"${TUI_FLAG[@]}"} 2>/dev/null || true)

needs_yazi_repo() {
    [[ " ${MISSING[*]:-} " == *" yazi "* ]]
}

# Print (or run) the commands that enable the yazi package repository.
yazi_repo_commands() {
    if [ "$PM" = "apt" ]; then
        python3 "$DEPS" --yazi-keyring
    elif [ "$PM" = "dnf" ]; then
        python3 "$DEPS" --yazi-copr
    fi
}

echo "Distro package manager: ${PM:-unknown}"
if [ ${#MISSING[@]} -eq 0 ]; then
    echo "System dependencies: all present"
else
    echo "System dependencies missing: ${MISSING[*]}"
    echo
    if [ "$AUTO_INSTALL" = "1" ] && [ -n "$INSTALL_CMD" ]; then
        echo "Installing missing system packages (--auto-install)..."
        if needs_yazi_repo; then
            echo "Enabling the yazi package repository..."
            REPO_CMDS=()
            while IFS= read -r c; do
                [ -n "$c" ] && REPO_CMDS+=("$c")
            done < <(yazi_repo_commands)
            # Run each step on its own with pipefail, so a failed download
            # stops here instead of registering a broken repository.
            for c in "${REPO_CMDS[@]}"; do
                bash -c "set -euo pipefail; $c"
            done
        fi
        bash -c "set -euo pipefail; $INSTALL_CMD"
        echo
    elif [ -n "$INSTALL_CMD" ]; then
        echo "To install them, run:"
        if needs_yazi_repo; then
            echo "  # yazi needs its package repository first:"
            yazi_repo_commands | sed 's/^/  /'
        fi
        echo "  $INSTALL_CMD"
        echo
        echo "Then re-run: $0 $*"
        echo
    else
        echo "Could not determine your package manager."
        echo "Install the missing packages manually, then re-run: $0 $*"
        echo
    fi
fi

if [ "$WITH_TUI" = "0" ]; then
    OPTIONAL="$(python3 "$DEPS" --missing --with-tui 2>/dev/null | grep -E '^(yazi|chafa)$' || true)"
    if [ -n "$OPTIONAL" ]; then
        echo "Optional TUI tools not installed: $(echo "$OPTIONAL" | tr '\n' ' ')"
        echo "  The TUI works without them; re-run with --with-tui to add them."
        echo
    fi
fi

# --- Python venv --------------------------------------------------------------
if [ ! -x "$VENV_DIR/bin/python" ]; then
    echo "Creating venv..."
    if ! python3 -m venv "$VENV_DIR"; then
        echo
        echo "ERROR: python3 -m venv failed."
        echo "On Ubuntu/Debian, install python3-venv first:"
        echo "  sudo apt install -y python3-venv"
        exit 1
    fi
fi

echo "Installing Python dependencies..."
"$VENV_DIR/bin/pip" install -q --upgrade pip
"$VENV_DIR/bin/pip" install -q -r "$HERE/requirements.txt"

echo
echo "Done."
echo "  GUI: $VENV_DIR/bin/python $HERE/main.py"
echo "  TUI: $VENV_DIR/bin/python $HERE/poster-tui"
echo "  CLI: $VENV_DIR/bin/python $HERE/cli.py --help"
