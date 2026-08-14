#!/bin/bash
# mak-attatch setup: creates the venv, installs Python deps, and checks for
# required system packages. By default it only PRINTS install commands and
# does not touch system packages; use --auto-install to opt in.
set -e

HERE="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$HERE/.venv"
AUTO_INSTALL=0

for arg in "$@"; do
    case "$arg" in
        --auto-install) AUTO_INSTALL=1 ;;
        -h|--help)
            echo "Usage: $0 [--auto-install]"
            echo
            echo "  --auto-install   install missing system packages (asks for sudo)"
            exit 0
            ;;
        *)
            echo "Unknown option: $arg" >&2
            echo "Usage: $0 [--auto-install]" >&2
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
PM="$(python3 "$HERE/core/deps.py" --pm 2>/dev/null || echo unknown)"
INSTALL_CMD="$(python3 "$HERE/core/deps.py" --install-cmd 2>/dev/null || true)"
MISSING=()
for bin in $(python3 "$HERE/core/deps.py" --missing 2>/dev/null); do
    MISSING+=("$bin")
done

echo "Distro package manager: ${PM:-unknown}"
if [ ${#MISSING[@]} -eq 0 ]; then
    echo "System dependencies: all present"
else
    echo "System dependencies missing: ${MISSING[*]}"
    echo
    if [ "$AUTO_INSTALL" = "1" ] && [ -n "$INSTALL_CMD" ]; then
        echo "Installing missing system packages (--auto-install)..."
        if [[ " ${MISSING[*]} " == *" yazi "* ]] && [ "$PM" = "apt" ]; then
            echo "Adding yazi apt repository keyring..."
            python3 "$HERE/core/deps.py" --yazi-keyring | while IFS= read -r c; do
                eval "$c"
            done
        fi
        if [[ " ${MISSING[*]} " == *" yazi "* ]] && [ "$PM" = "dnf" ]; then
            echo "Enabling yazi COPR repository..."
            python3 "$HERE/core/deps.py" --yazi-copr | while IFS= read -r c; do
                eval "$c"
            done
        fi
        eval "$INSTALL_CMD"
        echo
    elif [ -n "$INSTALL_CMD" ]; then
        echo "To install them, run:"
        echo "  $INSTALL_CMD"
        if [[ " ${MISSING[*]} " == *" yazi "* ]] && [ "$PM" = "apt" ]; then
            echo
            echo "yazi also needs its apt repository keyring first:"
            python3 "$HERE/core/deps.py" --yazi-keyring | while IFS= read -r c; do
                echo "  $c"
            done
        fi
        if [[ " ${MISSING[*]} " == *" yazi "* ]] && [ "$PM" = "dnf" ]; then
            echo
            echo "yazi also needs its COPR repository enabled first:"
            python3 "$HERE/core/deps.py" --yazi-copr | while IFS= read -r c; do
                echo "  $c"
            done
        fi
        echo
        echo "Then re-run: $0"
        echo
    else
        echo "Could not determine your package manager."
        echo "Install the missing packages manually, then re-run: $0"
        echo
    fi
fi

# --- Python venv --------------------------------------------------------------
if [ ! -d "$VENV_DIR" ]; then
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
echo "  GUI: $VENV_DIR/bin/python main.py"
echo "  TUI: $VENV_DIR/bin/python poster-tui"
echo "  CLI: $VENV_DIR/bin/python cli.py --help"
