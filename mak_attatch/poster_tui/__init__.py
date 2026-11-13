"""Terminal UI entry point (``mak-attatch-tui``)."""
import sys

TUI_MISSING = (
    "The terminal UI needs Textual, which is not installed.\n"
    "Install it with:  pip install 'mak-attatch[tui]'   (Arch: python-textual)\n"
    "The CLI (mak-attatch-cli) works without it."
)


def main():
    try:
        import textual  # noqa: F401
    except ImportError:
        print(TUI_MISSING, file=sys.stderr)
        sys.exit(1)
    from mak_attatch.poster_tui.app import main as run

    run()
