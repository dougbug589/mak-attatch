import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import requests
from rich.text import Text
from textual import events, on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.content import Content
from textual.css.query import NoMatches
from textual.screen import ModalScreen, Screen
from textual.widgets import (
    Button,
    Checkbox,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    ProgressBar,
    Static,
)

from mak_attatch import config
from mak_attatch.config import VERSION
from mak_attatch.core import attacher, autoattach, deps, parser, scanner, tmdb

# Exceptions these operations can legitimately raise; anything else is a bug
# and should propagate instead of being swallowed.
OPERATION_ERRORS = (
    tmdb.TMDBError,
    requests.RequestException,
    ValueError,
    OSError,
    RuntimeError,
    subprocess.SubprocessError,
)


class FileCheckbox(Checkbox):
    def _on_click(self, event: events.Click) -> None:
        event.stop()


class PathInput(Input):
    def _on_paste(self, event: events.Paste) -> None:
        if event.text:
            self.value = event.text
        event.prevent_default()
        event.stop()


CSS = """
Screen {
    layout: grid;
    grid-size: 3 1;
    grid-columns: 1fr 2fr 2fr;
    background: #1e1e2e;
    color: #cdd6f4;
}
#left_col, #mid_col, #right_col {
    border: solid $primary;
    padding: 0 1;
}
ListView { height: 1fr; }
#poster_gallery { height: 4fr; }
#file_list { height: 3fr; }
#path_row, #action_row { height: auto; }
#btn_row { height: 3; }
ProgressBar > .bar {
    background: $primary;
}
#review_screen {
    width: 100%;
    height: 100%;
    background: #1e1e2e;
    color: #cdd6f4;
    padding: 0 1;
}
#review_screen DataTable { height: 1fr; }
#review_screen > #review_header {
    text-style: bold;
    height: 1;
    margin-bottom: 1;
}
#review_screen > #review_summary {
    height: 1;
    margin-bottom: 1;
    color: #a6adc8;
}
#review_screen > #review_status {
    height: 1;
    color: #a6adc8;
}
#review_options {
    height: auto;
    margin-bottom: 1;
}
#review_buttons {
    height: 3;
    dock: bottom;
}
#poster_screen {
    width: 100%;
    height: 100%;
    background: #1e1e2e;
    color: #cdd6f4;
    padding: 0 1;
}
#poster_screen DataTable { height: 1fr; }
#poster_screen > #pp_header {
    text-style: bold;
    height: 1;
    margin-bottom: 1;
}
#poster_screen > #pp_status {
    height: 1;
    margin-bottom: 1;
    color: #a6adc8;
}
#poster_screen #pp_preview {
    height: 1fr;
    border: solid $primary;
    padding: 1;
    margin: 0 0 1 0;
}
#poster_screen #pp_buttons {
    height: 3;
    dock: bottom;
}
"""


class PosterTuiApp(App):
    TITLE = "mak-attatch TUI"
    SUB_TITLE = f"v{VERSION}"
    CSS = CSS

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("ctrl+tab", "focus_next_panel", "Next Panel"),
        Binding("ctrl+shift+tab", "focus_prev_panel", "Prev Panel"),
        Binding("ctrl+l", "focus_left_panel", "Left (Search)"),
        Binding("ctrl+m", "focus_mid_panel", "Mid (Posters)"),
        Binding("ctrl+r", "focus_right_panel", "Right (Files)"),
        Binding("space", "toggle_file_selection", "Toggle Selected"),
        Binding("d", "clear_selection", "Clear Selection"),
        Binding("ctrl+s", "scan_folder", "Scan Folder"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="left_col"):
            yield Input(placeholder="Search movie/show...", id="search_input")
            yield Button("Search", id="search_btn")
            yield Label("Results:", id="results_label")
            yield ListView(id="results_list")
        with Vertical(id="mid_col"):
            yield Label("Posters:", id="poster_label")
            yield ListView(id="poster_gallery")
            yield Label("", id="preview_info", markup=False)
        with Vertical(id="right_col"):
            yield Label("Video Files:", id="files_label")
            yield ListView(id="file_list")
            yield Button("Browse (yazi)", id="browse_btn")
            yield Button("Scan Folder", id="scan_btn")
            with Horizontal(id="path_row"):
                yield PathInput(placeholder="Paste video path(s)...", id="path_input")
                yield Button("Add", id="add_path_btn")
            with Horizontal(id="btn_row"):
                yield Button("Local Image", id="local_img_btn")
                yield Button("Clear Files", id="clear_btn")
                yield Button("Settings", id="settings_btn")
            with Horizontal(id="action_row"):
                yield Button("Attach", id="attach_btn", disabled=True)
                yield Button("Convert", id="convert_btn")
                yield Button("Remove", id="remove_btn")
                yield Button("Rm Meta", id="remove_meta_btn")
                yield Button("Scrape", id="scrape_meta_btn")
                yield Checkbox("Scrape metadata", id="meta_check")
            yield ProgressBar(id="progress", show_eta=False)
            # Filenames/titles/errors go here; "[SubsPlease]" is not markup.
            yield Label("Ready", id="status", markup=False)
        yield Footer()

    def __init__(self):
        super().__init__()
        self.video_paths: list[str] = []
        self.selected_files: set[str] = set()
        self.results: list[dict] = []
        self.posters: list[dict] = []
        self.selected_poster: dict | None = None
        self.local_poster_path: str | None = None
        self.current_media: dict | None = None
        self._yazi_chooser: str | None = None
        self._poster_gen = 0
        self._search_gen = 0
        self._poster_req = 0
        self._probe_gen = 0
        # One file-writing job at a time: two batches editing the same files
        # concurrently can corrupt MKVs (mkvpropedit does no locking) or
        # silently undo each other's MP4 rewrites.
        self._busy = False

    def on_mount(self):
        if not config.get("tmdb_api_key"):
            self.push_screen(SettingsScreen())

    PANEL_IDS = ["left_col", "mid_col", "right_col"]

    def _focus_panel(self, panel_id: str):
        panel = self.query_one(f"#{panel_id}")
        for child in panel.walk_children(with_self=False):
            if hasattr(child, "focus") and child.focusable:
                child.focus()
                break

    def action_focus_left_panel(self):
        self._focus_panel("left_col")

    def action_focus_mid_panel(self):
        self._focus_panel("mid_col")

    def action_focus_right_panel(self):
        self._focus_panel("right_col")

    def action_focus_next_panel(self):
        focused = self.focused
        if focused is None:
            self._focus_panel("left_col")
            return
        for ancestor in focused.ancestors_with_self:
            if ancestor.id in self.PANEL_IDS:
                idx = self.PANEL_IDS.index(ancestor.id)
                next_idx = (idx + 1) % len(self.PANEL_IDS)
                self._focus_panel(self.PANEL_IDS[next_idx])
                return
        self._focus_panel("left_col")

    def action_focus_prev_panel(self):
        focused = self.focused
        if focused is None:
            self._focus_panel("left_col")
            return
        for ancestor in focused.ancestors_with_self:
            if ancestor.id in self.PANEL_IDS:
                idx = self.PANEL_IDS.index(ancestor.id)
                prev_idx = (idx - 1) % len(self.PANEL_IDS)
                self._focus_panel(self.PANEL_IDS[prev_idx])
                return
        self._focus_panel("left_col")

    def _yazi_pick(self) -> str | None:
        start_dir = config.get("last_dir") or str(Path.home())
        fd, chooser = tempfile.mkstemp(prefix="yazi-chooser-")
        os.close(fd)
        self._yazi_chooser = chooser
        try:
            # No timeout: yazi is interactive, and killing it mid-session left
            # the terminal in yazi's screen and crashed the app.
            proc = subprocess.run(["yazi", "--chooser-file", chooser, "--", start_dir])
            if proc.returncode == 0 and os.path.exists(chooser):
                # File names are bytes on Linux; keep undecodable ones usable.
                return Path(chooser).read_text(errors="surrogateescape").strip()
            return None
        finally:
            try:
                os.unlink(chooser)
            except OSError:
                pass

    @on(Button.Pressed, "#browse_btn")
    def on_browse(self):
        try:
            with self.suspend():
                text = self._yazi_pick()
        except FileNotFoundError:
            self.query_one("#status").update("yazi not found. Install: sudo pacman -S yazi")
            return
        if not text:
            return
        valid, invalid = self._expand_paths(text)
        for p in valid:
            self._add_video_path(p)
        if invalid:
            names = ", ".join(Path(p).name for p in invalid[:3])
            self.query_one("#status").update(f"Not found: {names}")

    def _add_video_path(self, path: str):
        if not os.path.isfile(path):
            self.query_one("#status").update(f"Not a file: {path}")
            return
        p = os.path.realpath(path)
        if p in self.video_paths:
            self.query_one("#status").update(f"Already added: {Path(p).name}")
            return
        if not self.video_paths:
            self._reset_poster_choice()
        self._append_file_rows([p])
        config.set("last_dir", str(Path(p).parent))
        if len(self.video_paths) == 1:
            parsed = parser.parse_filename(p)
            self.query_one("#search_input").value = parser.build_search_query(parsed)
            self.action_search()

    def _reset_poster_choice(self):
        """A new file list must not inherit the previous title's poster."""
        self.selected_poster = None
        self.local_poster_path = None
        self.current_media = None
        self.query_one("#attach_btn").disabled = True

    def _append_file_rows(self, paths: list[str]) -> int:
        added = 0
        for path in paths:
            p = os.path.realpath(path)
            if p in self.video_paths:
                continue
            self.video_paths.append(p)
            idx = len(self.video_paths) - 1
            row = ListItem(FileCheckbox(Content(Path(p).name), id=f"file_cb_{idx}"),
                           id=f"file_row_{idx}")
            self.query_one("#file_list").append(row)
            added += 1
        self.query_one("#files_label").update(f"Video Files ({len(self.video_paths)}):")
        return added

    def _refresh_file_glyphs(self):
        # Cached answers show at once; the rest are probed in a worker (one
        # mkvmerge/ffprobe per file used to block the UI).
        unknown = []
        for i, p in enumerate(self.video_paths):
            has = scanner.cached_has_poster(p)
            if has is None:
                unknown.append((i, p))
            self._set_glyph(i, p, bool(has))
        if unknown:
            self._probe_gen += 1
            self._probe_posters(unknown, self._probe_gen)

    def _set_glyph(self, index: int, path: str, has: bool):
        try:
            checkbox = self.query_one(f"#file_cb_{index}")
        except NoMatches:
            return
        name = Path(path).name
        checkbox.label = Content(("✓ " + name) if has else name)

    @work(thread=True)
    def _probe_posters(self, items: list, gen: int):
        for index, path in items:
            if gen != self._probe_gen:
                return
            has = scanner.has_poster(path)
            if gen == self._probe_gen:
                self.call_from_thread(self._set_glyph, index, path, has)

    def _set_progress(self, current: int, total: int):
        progress = self.query_one("#progress")
        progress.total = total
        progress.progress = current

    @on(Button.Pressed, "#scan_btn")
    def on_scan_folder(self):
        try:
            with self.suspend():
                picked = self._yazi_pick()
        except FileNotFoundError:
            self.query_one("#status").update("yazi not found. Install: sudo pacman -S yazi")
            return
        if not picked:
            return
        path = picked.splitlines()[0].strip()
        if not os.path.isdir(path):
            self.query_one("#status").update("Scan needs a folder, not a file")
            return
        self.query_one("#status").update(f"Scanning {path}...")
        self._do_scan(path)

    def action_scan_folder(self):
        self.on_scan_folder()

    @work(thread=True)
    def _do_scan(self, root: str):
        try:
            files = scanner.iter_video_files(root)

            def cb(current, total, group):
                self.call_from_thread(
                    lambda: self.query_one("#status").update(
                        f"Resolving {current}/{total}: {group.title}"
                    )
                )

            groups = scanner.classify(files)
            delay = config.get("scan_api_delay")
            resolved = autoattach.resolve_groups(groups, api_delay=delay, progress=cb)
            self.call_from_thread(self._on_scan_resolved, resolved)
        except (tmdb.TMDBError, requests.RequestException, ValueError,
                OSError) as e:
            msg = f"Scan failed: {e}"
            self.call_from_thread(lambda: self.query_one("#status").update(msg))

    def _on_scan_resolved(self, resolved: list):
        ok = sum(1 for e in resolved if e["status"] == "ok")
        self.query_one("#status").update(f"Matched {ok}/{len(resolved)} titles")

        def handler(result):
            if not result:
                self.query_one("#status").update("Scan cancelled")
                return
            action = result[0]
            if action == "add":
                _, entries = result
                paths = [p for e in entries for p in e["group"].files]
                added = self._append_file_rows(paths)
                self.query_one("#status").update(
                    f"Added {added} file(s) to the list — select them and attach posters"
                )
                return
            _, entries, embed_meta = result
            paths = [p for e in entries for p in e["group"].files]
            self._append_file_rows(paths)
            if not self._begin_job():
                return
            self.query_one("#status").update(f"Attaching posters to {len(paths)} files...")
            self._do_auto_attach(entries, scrape_metadata=embed_meta)

        self.push_screen(ReviewScreen(resolved), callback=handler)

    @work(thread=True)
    def _do_auto_attach(self, entries: list, scrape_metadata: bool = False):
        try:
            skip = config.get("scan_skip_existing")
            delay = config.get("scan_api_delay")
            to_mkv = bool(config.get("convert_to_mkv"))

            def cb(done, total, filepath, status):
                self.call_from_thread(
                    lambda: self.query_one("#status").update(
                        f"Attaching {done}/{total}: {Path(filepath).name}"
                    )
                )

            summary = autoattach.attach_groups(
                entries, skip_existing=skip, scrape_metadata=scrape_metadata,
                api_delay=delay, to_mkv=to_mkv, progress=cb,
            )
            self.call_from_thread(self._on_auto_attach_done, summary)
        except OPERATION_ERRORS as e:
            msg = f"Auto-attach failed: {e}"
            self.call_from_thread(lambda: self.query_one("#status").update(msg))
        finally:
            self.call_from_thread(self._end_job)

    def _on_auto_attach_done(self, summary: dict):
        if summary.get("converted"):
            self._apply_conversions(summary["converted"])
        self._refresh_file_glyphs()
        ok, fail, skipped = summary["ok"], summary["fail"], summary["skipped"]
        msg = f"Auto-attach: {ok} ok, {skipped} skipped, {fail} failed"
        self.query_one("#status").update(msg)
        if fail:
            detail = " | ".join(summary["errors"][:5])[:2000]
            self.notify(f"Auto-attach: {fail} failed — {detail}", severity="error")
        else:
            self.notify(f"Posters attached to {ok} files")

    @on(Input.Submitted, "#path_input")
    @on(Button.Pressed, "#add_path_btn")
    def on_add_path(self):
        raw = self.query_one("#path_input").value.strip()
        if not raw:
            return
        valid, invalid = self._expand_paths(raw)
        for p in valid:
            self._add_video_path(p)
        if invalid:
            names = ", ".join(Path(p).name for p in invalid[:3])
            self.query_one("#status").update(f"Not found: {names}")
        self.query_one("#path_input").value = ""

    def _expand_paths(self, raw: str) -> tuple[list[str], list[str]]:
        valid: list[str] = []
        invalid: list[str] = []
        for line in raw.splitlines():
            line = line.strip().strip("\"'")
            if not line:
                continue
            expanded = os.path.expanduser(line)
            if os.path.isfile(expanded):
                valid.append(expanded)
            else:
                invalid.append(line)
        return valid, invalid

    @on(Button.Pressed, "#clear_btn")
    def on_clear_files(self):
        self.video_paths.clear()
        self.selected_files.clear()
        self.query_one("#file_list").clear()
        self.query_one("#files_label").update("Video Files:")
        self.query_one("#attach_btn").disabled = True
        self.query_one("#status").update("File list cleared")

    def _file_row(self, idx: int) -> ListItem:
        return self.query_one(f"#file_row_{idx}")

    def _set_file_selected(self, idx: int, selected: bool):
        self._file_row(idx).query_one(Checkbox).value = selected

    def _selection_summary(self) -> str:
        n = len(self.selected_files)
        if n == 0:
            return f"operations apply to all {len(self.video_paths)} file(s)"
        if n == 1:
            return f"selected: {Path(next(iter(self.selected_files))).name}"
        return f"{n} file(s) selected"

    def _update_selection_status(self):
        if not self.video_paths:
            self.query_one("#status").update("No video files loaded")
            return
        self.query_one("#status").update(self._selection_summary() + " (d to clear)")

    @on(Checkbox.Changed)
    def on_file_checkbox_changed(self, event: Checkbox.Changed):
        checkbox = event.control
        if not checkbox.id or not checkbox.id.startswith("file_cb_"):
            return
        try:
            idx = int(checkbox.id.split("_")[-1])
        except (IndexError, ValueError):
            return
        if 0 <= idx < len(self.video_paths):
            if event.value:
                self.selected_files.add(self.video_paths[idx])
            else:
                self.selected_files.discard(self.video_paths[idx])
            self._update_selection_status()

    @on(ListView.Highlighted, "#file_list")
    def on_file_highlighted(self, event: ListView.Highlighted):
        idx = event.list_view.index
        if idx is None or idx >= len(self.video_paths):
            return
        parsed = parser.parse_filename(self.video_paths[idx])
        self.query_one("#search_input").value = parser.build_search_query(parsed)

    @on(ListView.Selected, "#file_list")
    def on_file_selected(self, event: ListView.Selected):
        idx = event.list_view.index
        if idx is None or idx >= len(self.video_paths):
            return
        self.selected_files = {self.video_paths[idx]}
        for i in range(len(self.video_paths)):
            self._set_file_selected(i, i == idx)
        self._update_selection_status()

    def action_toggle_file_selection(self):
        idx = self.query_one("#file_list").index
        if idx is None:
            self.query_one("#file_list").index = 0
            idx = 0
        if idx >= len(self.video_paths):
            return
        path = self.video_paths[idx]
        if path in self.selected_files:
            self.selected_files.discard(path)
        else:
            self.selected_files.add(path)
        self._set_file_selected(idx, path in self.selected_files)
        self._update_selection_status()

    def action_clear_selection(self):
        self.selected_files.clear()
        for i in range(len(self.video_paths)):
            self._set_file_selected(i, False)
        self.query_one("#file_list").index = None
        self.query_one("#status").update(
            f"Selection cleared — operations apply to all {len(self.video_paths)} files"
        )

    def _targets(self) -> list[str]:
        if self.selected_files:
            return sorted(self.selected_files)
        return list(self.video_paths)

    def _begin_job(self) -> bool:
        if self._busy:
            self.query_one("#status").update(
                "Another operation is still running — wait for it to finish"
            )
            return False
        self._busy = True
        return True

    def _end_job(self):
        self._busy = False

    def _confirm_then(self, action: str, targets: list[str], run) -> None:
        """Ask before a destructive batch, spelling out when it hits ALL files."""
        if self._busy:
            self._begin_job()  # shows the "still running" message
            return
        targets = list(targets)
        if self.selected_files:
            scope = f"{len(targets)} selected file(s)"
        else:
            scope = f"ALL {len(targets)} loaded file(s) — nothing is selected"

        def done(confirmed: bool | None):
            if confirmed and self._begin_job():
                run(targets)

        self.push_screen(ConfirmScreen(f"{action} on {scope}?"), callback=done)

    async def action_quit(self) -> None:
        if not self._busy:
            self.exit()
            return

        def done(confirmed: bool | None):
            if confirmed:
                self.exit()

        self.push_screen(
            ConfirmScreen("An operation is still running. Quit anyway? "
                          "The file being processed right now may be left unfinished."),
            callback=done,
        )

    @on(Button.Pressed, "#local_img_btn")
    def on_local_image(self):
        try:
            with self.suspend():
                path = self._yazi_pick()
        except FileNotFoundError:
            self.query_one("#status").update("yazi not found. Install: sudo pacman -S yazi")
            return
        if not path:
            return
        path = path.splitlines()[0].strip()
        ext = Path(path).suffix.lower()
        if ext not in (".jpg", ".jpeg", ".png", ".bmp", ".webp"):
            self.query_one("#status").update("Not a supported image format")
            return
        self.local_poster_path = path
        self.selected_poster = None
        self.query_one("#status").update(f"Local image: {Path(path).name}")
        # The user's own file: preview it, never delete it.
        self._preview_native(path, owned=False)
        self.query_one("#attach_btn").disabled = False

    @staticmethod
    def _terminal_supports_sixel() -> bool:
        """Live-probe the terminal for sixel support (DEC DA1).

        Writes ``ESC [ c`` and looks for private parameter 4 in the reply.
        Reliable across SSH, where env vars like KONSOLE_VERSION do not
        propagate. Returns False when the probe cannot complete.
        """
        import select
        import termios
        try:
            fd = sys.stdin.fileno()
            old = termios.tcgetattr(fd)
            tty = termios.tcgetattr(fd)
            tty[3] &= ~(termios.ICANON | termios.ECHO)
            tty[6][termios.VMIN] = 1
            tty[6][termios.VTIME] = 0
            termios.tcsetattr(fd, termios.TCSANOW, tty)
            sys.stdout.write("\x1b[c")
            sys.stdout.flush()
            resp = b""
            r, _, _ = select.select([fd], [], [], 0.5)
            if r:
                resp = os.read(fd, 1024)
            termios.tcsetattr(fd, termios.TCSANOW, old)
            m = re.search(rb"\x1b\[\?([0-9;]*)c", resp)
            return bool(m and "4" in m.group(1).decode().split(";"))
        except Exception:  # noqa: BLE001 - probe failure means "no sixel", fall back safely
            return False

    @staticmethod
    def _pick_preview_format() -> str:
        """Choose the best chafa format the terminal actually supports.

        kitty/sixel graphics protocols only render in terminals that
        implement them, yet chafa still exits 0 on unsupported terminals
        (e.g. GNOME Terminal), so support is probed instead of trusting the
        return code.
        """
        term = os.environ.get("TERM", "")
        if os.environ.get("KITTY_WINDOW_ID") or "kitty" in term:
            return "kitty"
        if (os.environ.get("KONSOLE_VERSION")
                or os.environ.get("TERM_PROGRAM") == "WezTerm"
                or "sixel" in term
                or os.environ.get("COLORTERM") == "sixel"
                or PosterTuiApp._terminal_supports_sixel()):
            return "sixel"
        return "symbols"

    def _preview_native(self, path: str, info: str = "", owned: bool = True):
        """Draw an image preview; delete it afterwards only if we own it.

        owned=True is for temp files downloaded for the preview. A local image
        picked by the user must pass owned=False, or it would be deleted.
        """
        try:
            self._draw_preview(path, info)
        finally:
            if owned:
                try:
                    os.unlink(path)
                except OSError:
                    pass
            self._update_selection_status()

    def _draw_preview(self, path: str, info: str):
        if not shutil.which("chafa"):
            self.query_one("#status").update("Install chafa for preview")
            return
        try:
            with self.suspend():
                print("\033[2J\033[H", end="", flush=True)
                fmt = self._pick_preview_format()
                args = ["chafa", "--format=" + fmt, "--", path]
                if fmt == "symbols":
                    cols, rows = shutil.get_terminal_size((120, 40))
                    size = f"{cols - 4}x{rows - 8}"
                    args = ["chafa", "--format=symbols", "--size=" + size,
                            "--color-space=rgb", "--dither=fs", "--", path]
                try:
                    subprocess.run(args, timeout=10)
                except subprocess.SubprocessError:
                    pass
                if info:
                    safe = re.sub(r"[\x00-\x1f\x7f]", "", info)
                    print(f"\n{safe}", flush=True)
                targets = self._targets()
                if targets:
                    print(
                        f"\nWill attach to {len(targets)} file(s): "
                        + ", ".join(Path(p).name for p in targets[:5])
                        + (" ..." if len(targets) > 5 else ""),
                        flush=True,
                    )
                print("\nPress Enter to return...", flush=True)
                input()
                print("\033[2J\033[H", end="", flush=True)
                print("\x1b_Ga=d,d=a\x1b\\", end="", flush=True)
        except FileNotFoundError:
            print("Warning: chafa exited unexpectedly during preview", file=sys.stderr)
        except OPERATION_ERRORS as e:
            print(f"Warning: preview failed: {e}", file=sys.stderr)

    @on(Input.Submitted, "#search_input")
    @on(Button.Pressed, "#search_btn")
    def action_search(self):
        query = self.query_one("#search_input").value.strip()
        if not query:
            return
        if not config.get("tmdb_api_key"):
            self.query_one("#status").update("No API key set. Press Settings.")
            return
        self.query_one("#status").update("Searching...")
        self._search_gen += 1
        self._do_search(query, self._search_gen)

    @work(thread=True)
    def _do_search(self, query: str, gen: int):
        try:
            results = tmdb.search(query)
            if gen == self._search_gen:  # a newer search supersedes this one
                self.call_from_thread(self._on_search_done, results)
        except (tmdb.TMDBError, requests.RequestException, ValueError,
                OSError) as e:
            self.call_from_thread(self._on_search_error, str(e))

    def _on_search_done(self, results):
        self.results = results
        self.query_one("#results_list").clear()
        for r in results:
            label = f"{r['title']} ({r['year']}) [{r['media_type']}]"
            self.query_one("#results_list").append(ListItem(Label(label, markup=False)))
        self.query_one("#results_label").update(f"Results ({len(results)}):")
        self.query_one("#status").update(f"Found {len(results)} results")

    def _on_search_error(self, err):
        self.query_one("#status").update(f"Search failed: {err}")

    @on(ListView.Selected, "#results_list")
    def on_result_selected(self, event: ListView.Selected):
        idx = event.list_view.index
        if idx is None or idx >= len(self.results):
            return
        data = self.results[idx]
        self.current_media = {"id": data["id"], "media_type": data["media_type"]}
        self.query_one("#status").update(f"Loading posters for {data['title']}...")
        self._poster_req += 1
        self._load_posters(data["id"], data["media_type"], self._poster_req)

    @work(thread=True)
    def _load_posters(self, media_id: int, media_type: str, req: int):
        try:
            posters = tmdb.get_posters(media_id, media_type)
            # Clicking result A then B must never show A's posters for B.
            if req == self._poster_req:
                self.call_from_thread(self._on_posters_loaded, posters)
        except (tmdb.TMDBError, requests.RequestException, ValueError,
                OSError) as e:
            self.call_from_thread(self._on_search_error, str(e))

    def _on_posters_loaded(self, posters):
        self.posters = posters
        self.query_one("#poster_label").update(f"Posters ({len(posters)}):")
        gallery = self.query_one("#poster_gallery")
        gallery.clear()
        self._poster_gen += 1
        gen = self._poster_gen
        for idx, p in enumerate(posters):
            gallery.append(
                ListItem(
                    Label(
                        f"{p['width']}x{p['height']} [{p.get('lang') or '??'}]",
                        markup=False,
                    ),
                    id=f"cell_{gen}_{idx}",
                )
            )
        self.query_one("#status").update("Posters: click to select")

    @on(ListView.Selected, "#poster_gallery")
    def on_poster_selected(self, event: ListView.Selected):
        item = event.item
        if not item.id or not item.id.startswith("cell_"):
            return
        try:
            idx = int(item.id.split("_")[-1])
        except (IndexError, ValueError):
            return
        if 0 <= idx < len(self.posters):
            self._select_poster(idx)

    def _select_poster(self, idx: int):
        self.selected_poster = self.posters[idx]
        self.local_poster_path = None
        self.query_one("#attach_btn").disabled = False
        p = self.selected_poster
        info = f"Resolution: {p['width']}x{p['height']}  Language: {p.get('lang') or '??'}"
        self.query_one("#preview_info").update(info)
        self._show_image_preview(p["thumb_url"], info)

    @work(thread=True)
    def _show_image_preview(self, url: str, info: str):
        tmp = None
        try:
            fd, tmp = tempfile.mkstemp(suffix=".jpg")
            os.close(fd)
            os.chmod(tmp, 0o600)
            # Same host, size and image-type checks as poster downloads.
            tmdb.download_image(url, tmp)
            # The temp file is deleted by _preview_native once it has drawn it,
            # so the GUI thread never races the worker's cleanup.
            self.call_from_thread(self._preview_native, tmp, info)
        except (tmdb.TMDBError, requests.RequestException, OSError):
            print(f"Warning: poster preview failed: {url}", file=sys.stderr)
            if tmp:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass

    @on(Button.Pressed, "#attach_btn")
    def on_attach(self):
        if not self.video_paths:
            self.query_one("#status").update("No video files loaded")
            return
        if not self.selected_poster and not self.local_poster_path:
            self.query_one("#status").update("No poster selected")
            return
        # Snapshot everything on the UI thread; the worker only sees plain
        # data, so changing the selection mid-batch cannot redirect it (and
        # ownership of the poster file is decided here, not at the end).
        targets = list(self._targets())
        poster_url = None if self.local_poster_path else self.selected_poster["url"]
        local_path = self.local_poster_path
        media = dict(self.current_media) if self.current_media else None
        scrape = self.query_one("#meta_check").value

        def run():
            self._do_attach(targets, scrape, poster_url, local_path, media)

        if self.selected_files or len(targets) == 1:
            if self._begin_job():
                run()
        else:
            self._confirm_then("Attach this poster", targets, run)

    @work(thread=True)
    def _do_attach(self, targets: list[str], scrape_metadata: bool,
                   poster_url: str | None, local_path: str | None,
                   media: dict | None):
        poster_path = None
        owned = local_path is None  # only ever delete a file we downloaded
        to_mkv = bool(config.get("convert_to_mkv"))
        conversions: dict[str, str] = {}
        try:
            if local_path:
                poster_path = local_path
            else:
                fd, poster_path = tempfile.mkstemp(suffix=".jpg")
                os.close(fd)
                os.chmod(poster_path, 0o600)
                tmdb.download_image(poster_url, poster_path)

            metadata = None
            if scrape_metadata and media:
                self.call_from_thread(
                    lambda: self.query_one("#status").update("Scraping metadata...")
                )
                metadata = tmdb.get_details(media["id"], media["media_type"])

            total = len(targets)
            ok = 0
            fail = 0
            first_error = None
            self.call_from_thread(self._set_progress, 0, total)
            for i, path in enumerate(targets):
                self.call_from_thread(
                    lambda i=i, p=path: self.query_one("#status").update(
                        f"Attaching {i+1}/{total}: {Path(p).name}"
                    )
                )
                self.call_from_thread(self._set_progress, i + 1, total)
                try:
                    out = attacher.full_attach(path, poster_path, metadata=metadata,
                                               to_mkv=to_mkv)
                    if out != path:
                        conversions[path] = out
                    ok += 1
                except OPERATION_ERRORS as e:
                    fail += 1
                    if first_error is None:
                        first_error = f"{Path(path).name}: {e}"

            if conversions:
                self.call_from_thread(self._apply_conversions, conversions)

            if fail == 0:
                msg = f"Attached to {ok} file(s)"
            elif first_error:
                msg = f"Attached: {ok}, Failed: {fail} — {first_error}"
            else:
                msg = f"Attached: {ok}, Failed: {fail}"
            self.call_from_thread(lambda: self.query_one("#status").update(msg))
        except OPERATION_ERRORS as e:
            msg = f"Error: {e}"
            self.call_from_thread(lambda: self.query_one("#status").update(msg))
        finally:
            if owned and poster_path:
                try:
                    os.unlink(poster_path)
                except OSError:
                    pass
            self.call_from_thread(self._end_job)

    def _apply_conversions(self, conversions: dict[str, str]):
        for old, new in conversions.items():
            if old in self.video_paths:
                self.video_paths[self.video_paths.index(old)] = new
            # Keep the selection pointing at the new MKV, not the original
            # (which still exists), so later operations hit the right file.
            if old in self.selected_files:
                self.selected_files.discard(old)
                self.selected_files.add(new)
        self._refresh_file_glyphs()

    def _run_batch(self, targets: list[str], verb: str, fn) -> tuple[int, int, list[str]]:
        """Apply fn to each target with progress; returns (ok, fail, errors)."""
        total = len(targets)
        ok = 0
        fail = 0
        errors: list[str] = []
        self.call_from_thread(self._set_progress, 0, total)
        for i, path in enumerate(targets):
            self.call_from_thread(
                lambda i=i, p=path: self.query_one("#status").update(
                    f"{verb} {i+1}/{total}: {Path(p).name}"
                )
            )
            self.call_from_thread(self._set_progress, i + 1, total)
            try:
                fn(path)
                ok += 1
            except OPERATION_ERRORS as e:
                fail += 1
                errors.append(f"{Path(path).name}: {e}")
        return ok, fail, errors

    @on(Button.Pressed, "#remove_btn")
    def on_remove(self):
        if not self.video_paths:
            self.query_one("#status").update("No video files loaded")
            return
        self._confirm_then("Remove posters", self._targets(), self._do_remove)

    @work(thread=True)
    def _do_remove(self, targets: list[str]):
        try:
            ok, fail, errors = self._run_batch(targets, "Removing", attacher.remove_poster)
            if fail == 0:
                msg = f"Removed from {ok} file(s)"
            else:
                msg = f"Removed: {ok}, Failed: {fail} — {errors[0]}"
            self.call_from_thread(lambda: self.query_one("#status").update(msg))
            self.call_from_thread(self._refresh_file_glyphs)
        finally:
            self.call_from_thread(self._end_job)

    @on(Button.Pressed, "#remove_meta_btn")
    def on_remove_metadata(self):
        if not self.video_paths:
            self.query_one("#status").update("No video files loaded")
            return
        self._confirm_then("Remove all metadata", self._targets(), self._do_remove_metadata)

    @work(thread=True)
    def _do_remove_metadata(self, targets: list[str]):
        try:
            ok, fail, errors = self._run_batch(
                targets, "Removing metadata", attacher.remove_metadata
            )
            if fail == 0:
                msg = f"Removed metadata from {ok} file(s)"
            else:
                msg = f"Removed metadata: {ok}, Failed: {fail} — {errors[0]}"
            self.call_from_thread(lambda: self.query_one("#status").update(msg))
        finally:
            self.call_from_thread(self._end_job)

    @on(Button.Pressed, "#convert_btn")
    def on_convert(self):
        if not self.video_paths:
            self.query_one("#status").update("No video files loaded")
            return
        # Convert keeps the originals, so it needs no confirmation, only the
        # single-job guard.
        if self._begin_job():
            self._do_convert(list(self._targets()))

    @work(thread=True)
    def _do_convert(self, targets: list[str]):
        conversions: dict[str, str] = {}

        def convert(path: str):
            out = attacher.remux_to_mkv(path)
            if out != path:
                conversions[path] = out

        try:
            ok, fail, errors = self._run_batch(targets, "Converting", convert)
            if conversions:
                self.call_from_thread(self._apply_conversions, conversions)
            if fail == 0:
                msg = f"Converted {ok} file(s) to MKV"
            else:
                msg = f"Converted: {ok}, Skipped/Failed: {fail} — {errors[0]}"
            self.call_from_thread(lambda: self.query_one("#status").update(msg))
            if fail:
                self.call_from_thread(
                    lambda: self.notify(f"{fail} file(s) not converted — {errors[0]}",
                                        severity="warning", markup=False)
                )
            else:
                self.call_from_thread(lambda: self.notify(f"Converted {ok} file(s) to MKV"))
        finally:
            self.call_from_thread(self._end_job)

    @on(Button.Pressed, "#scrape_meta_btn")
    def on_scrape_metadata(self):
        if not self.video_paths:
            self.query_one("#status").update("No video files loaded")
            return
        targets = list(self._targets())
        # The selected search result only describes a single file. A batch
        # must resolve each filename on its own (same rule as the GUI);
        # otherwise one title's metadata would be written to every file.
        media = dict(self.current_media) if self.current_media and len(targets) == 1 else None
        self._confirm_then(
            "Overwrite metadata", targets,
            lambda t: self._do_scrape_metadata(t, media),
        )

    @work(thread=True)
    def _do_scrape_metadata(self, targets: list[str], media: dict | None):
        def scrape(path: str):
            attacher.write_metadata(path, tmdb.details_for_path(path, media))

        try:
            ok, fail, errors = self._run_batch(targets, "Scraping metadata", scrape)
            if fail == 0:
                msg = f"Metadata written to {ok} file(s)"
            else:
                detail = " | ".join(errors)[:2000]
                msg = f"Metadata: {ok} ok, {fail} failed — {detail}"
            self.call_from_thread(lambda: self.query_one("#status").update(msg))
        finally:
            self.call_from_thread(self._end_job)

    @on(Button.Pressed, "#settings_btn")
    def on_settings(self):
        self.push_screen(SettingsScreen())


class SettingsScreen(Screen):
    def compose(self) -> ComposeResult:
        with Vertical(id="settings_dialog"):
            yield Label("TMDB API Key")
            yield Label("Get one free at https://www.themoviedb.org/settings/api")
            yield Input(
                value=config.get("tmdb_api_key") or "",
                password=True,
                placeholder="Paste API key here...",
                id="api_key_input",
            )
            yield Checkbox(
                "Skip files that already have a poster",
                value=bool(config.get("scan_skip_existing")),
                id="skip_existing_check",
            )
            yield Checkbox(
                "Convert MP4 to MKV (lossless remux)",
                value=bool(config.get("convert_to_mkv")),
                id="convert_mkv_check",
            )
            yield Label("API delay between lookups (seconds)")
            yield Input(
                value=str(config.get("scan_api_delay")),
                placeholder="0.25",
                id="api_delay_input",
            )
            with Horizontal():
                yield Button("Save", id="save_btn")
                yield Button("Cancel", id="cancel_btn")

    @on(Button.Pressed, "#save_btn")
    def on_save(self):
        key = self.query_one("#api_key_input").value.strip()
        env_key = os.environ.get(config.API_KEY_ENV, "").strip()
        if not (env_key and key == env_key):
            # A key from the environment must never be written to disk.
            try:
                config.set("tmdb_api_key", key)
            except ValueError:
                self.notify("Invalid API key (10-500 characters)", severity="error")
                return
        config.set("scan_skip_existing", self.query_one("#skip_existing_check").value)
        config.set("convert_to_mkv", self.query_one("#convert_mkv_check").value)
        try:
            delay = float(self.query_one("#api_delay_input").value.strip())
            config.set("scan_api_delay", max(0.0, delay))
        except ValueError:
            pass
        self.notify("Settings saved!")
        self.dismiss()

    @on(Button.Pressed, "#cancel_btn")
    def on_cancel(self):
        self.dismiss()


class ConfirmScreen(ModalScreen[bool]):
    """Yes/No confirmation for destructive or all-files operations."""

    BINDINGS = [
        Binding("y", "answer(True)", "Yes"),
        Binding("n", "answer(False)", "No"),
        Binding("escape", "answer(False)", "Cancel"),
    ]

    CSS = """
    ConfirmScreen {
        align: center middle;
    }
    #confirm_box {
        width: 70;
        height: auto;
        border: thick $warning;
        padding: 1 2;
        background: $surface;
    }
    #confirm_buttons {
        height: auto;
        margin-top: 1;
    }
    """

    def __init__(self, message: str):
        super().__init__()
        self.message = message

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm_box"):
            # markup=False: file counts are safe, but keep any future text
            # (titles, paths) from being interpreted as Textual markup.
            yield Static(self.message, markup=False)
            with Horizontal(id="confirm_buttons"):
                yield Button("No", id="confirm_no")
                yield Button("Yes", id="confirm_yes", variant="warning")

    def on_mount(self):
        self.query_one("#confirm_no").focus()

    def action_answer(self, value: bool):
        self.dismiss(value)

    @on(Button.Pressed, "#confirm_yes")
    def on_yes(self):
        self.dismiss(True)

    @on(Button.Pressed, "#confirm_no")
    def on_no(self):
        self.dismiss(False)


class ReviewScreen(ModalScreen[tuple | None]):
    """Full-screen review of scanned groups with per-season selection."""

    CSS = """
    ReviewScreen {
        layout: vertical;
        width: 100%;
        height: 100%;
    }
    """

    def __init__(self, resolved: list):
        super().__init__()
        self.resolved = resolved
        self._selected: set[int] = set()
        self._all_ok = {i for i, e in enumerate(resolved) if e["status"] == "ok"}

    def compose(self) -> ComposeResult:
        with Vertical(id="review_screen"):
            yield Label("Review Scan Results", id="review_header")
            yield Static(self._summary(), id="review_summary")
            with Horizontal(id="review_options"):
                yield Checkbox("Skip unmatched", id="skip_unmatched", value=True)
                yield Checkbox("Embed metadata", id="embed_meta", value=False)
            yield DataTable(id="review_table", cursor_type="row")
            yield Label("", id="review_status")
            with Horizontal(id="review_buttons"):
                yield Button("Cancel", id="review_cancel")
                yield Button("All", id="review_select_all")
                yield Button("None", id="review_deselect_all")
                yield Button("Add to List", id="review_add")
                yield Button("Attach", id="review_attach", variant="primary")

    def on_mount(self):
        table = self.query_one("#review_table")
        table.add_columns("✓", "Title", "Season", "Files", "Status", "Poster")
        status_map = {"ok": "matched", "no-match": "unmatched", "error": "error"}
        for i, e in enumerate(self.resolved):
            g = e["group"]
            season = f"S{g.season}" if g.season is not None else "-"
            status = status_map.get(e["status"], "?")
            poster = "custom" if e.get("poster") else ("TMDB" if e["status"] == "ok" else "-")
            marker = "●" if i in self._all_ok else "○"
            # Text(): titles come from folder/file names and are not markup.
            table.add_row(marker, Text(g.title), season, str(len(g.files)), status, poster)
        self._selected = set(self._all_ok)
        self._update_checkmarks()
        self._update_status()

    def _update_checkmarks(self):
        table = self.query_one("#review_table")
        for i in range(len(self.resolved)):
            marker = "●" if i in self._selected else "○"
            table.update_cell_at((i, 0), marker)

    def _update_status(self):
        n = len(self._selected)
        total = len(self.resolved)
        self.query_one("#review_status").update(f"Selected: {n}/{total} groups")

    def _summary(self) -> str:
        ok = sum(1 for e in self.resolved if e["status"] == "ok")
        unmatched = sum(1 for e in self.resolved if e["status"] == "no-match")
        errs = sum(1 for e in self.resolved if e["status"] == "error")
        return f"{ok} matched, {unmatched} unmatched, {errs} errors"

    @on(DataTable.RowSelected, "#review_table")
    def on_row_selected(self, event: DataTable.RowSelected):
        row_idx = event.cursor_row
        if row_idx is None:
            return
        if row_idx in self._selected:
            self._selected.discard(row_idx)
        elif row_idx in self._all_ok:
            self._selected.add(row_idx)
        self._update_checkmarks()
        self._update_status()

    @on(Button.Pressed, "#review_select_all")
    def on_select_all(self):
        self._selected = set(range(len(self.resolved)))
        self._update_checkmarks()
        self._update_status()

    @on(Button.Pressed, "#review_deselect_all")
    def on_deselect_all(self):
        self._selected.clear()
        self._update_checkmarks()
        self._update_status()

    @on(Button.Pressed, "#review_attach")
    def on_attach(self):
        entries = self._selected_entries()
        if not entries:
            self.notify("No groups selected", severity="warning")
            return
        embed = self.query_one("#embed_meta").value
        self.dismiss(("attach", entries, embed))

    @on(Button.Pressed, "#review_add")
    def on_add_to_list(self):
        entries = self._selected_entries()
        if not entries:
            self.notify("No groups selected", severity="warning")
            return
        self.dismiss(("add", entries))

    def _selected_entries(self) -> list:
        entries = [self.resolved[i] for i in sorted(self._selected)]
        if self.query_one("#skip_unmatched").value:
            entries = [e for e in entries if e["status"] == "ok"]
        return entries

    @on(Button.Pressed, "#review_cancel")
    def on_cancel(self):
        self.dismiss(None)


def main():
    missing = attacher.check_tools()
    if missing:
        print(f"Missing: {', '.join(missing)}")
        print(deps.hint(missing))
        sys.exit(1)
    optional = [tool for tool in ("yazi", "chafa") if not shutil.which(tool)]
    if optional:
        print(f"Optional tools missing: {', '.join(optional)}")
        print("File browsing needs yazi and image previews need chafa; "
              "the TUI still runs without them.")
    app = PosterTuiApp()
    app.run()


if __name__ == "__main__":
    main()
