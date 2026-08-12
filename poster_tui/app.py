import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests
from textual import events, on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
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

import config
from config import VERSION
from core import attacher, autoattach, parser, scanner, tmdb

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
            yield Label("", id="preview_info")
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
            yield Label("Ready", id="status")
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
            proc = subprocess.run(
                ["yazi", "--chooser-file", chooser, "--", start_dir],
                timeout=300,
            )
            if proc.returncode == 0 and os.path.exists(chooser):
                return Path(chooser).read_text().strip()
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
        self._append_file_rows([p])
        config.set("last_dir", str(Path(p).parent))
        if len(self.video_paths) == 1:
            parsed = parser.parse_filename(p)
            self.query_one("#search_input").value = parser.build_search_query(parsed)
            self.action_search()

    def _append_file_rows(self, paths: list[str]) -> int:
        added = 0
        for path in paths:
            p = os.path.realpath(path)
            if p in self.video_paths:
                continue
            self.video_paths.append(p)
            idx = len(self.video_paths) - 1
            row = ListItem(FileCheckbox(Path(p).name, id=f"file_cb_{idx}"), id=f"file_row_{idx}")
            self.query_one("#file_list").append(row)
            added += 1
        self.query_one("#files_label").update(f"Video Files ({len(self.video_paths)}):")
        return added

    def _refresh_file_glyphs(self):
        for i, p in enumerate(self.video_paths):
            has = scanner.has_poster(p)
            checkbox = self.query_one(f"#file_cb_{i}")
            checkbox.label = ("✓ " + Path(p).name) if has else Path(p).name

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
            delay = config.get("scan_api_delay") or 0.25
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
            self.query_one("#status").update(f"Attaching posters to {len(paths)} files...")
            self._do_auto_attach(entries, scrape_metadata=embed_meta)

        self.push_screen(ReviewScreen(resolved), callback=handler)

    @work(thread=True)
    def _do_auto_attach(self, entries: list, scrape_metadata: bool = False):
        try:
            skip = config.get("scan_skip_existing")
            delay = config.get("scan_api_delay") or 0.25
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
        except (tmdb.TMDBError, requests.RequestException, ValueError,
                OSError) as e:
            msg = f"Auto-attach failed: {e}"
            self.call_from_thread(lambda: self.query_one("#status").update(msg))

    def _on_auto_attach_done(self, summary: dict):
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
        return self.video_paths

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
        self._preview_native(path)
        self.query_one("#attach_btn").disabled = False

    def _preview_native(self, path: str, info: str = ""):
        if not shutil.which("chafa"):
            self.query_one("#status").update("Install chafa for preview")
            return
        try:
            with self.suspend():
                print("\033[2J\033[H", end="", flush=True)
                for fmt in ("kitty", "sixel", "symbols"):
                    args = ["chafa", "--format=" + fmt, "--", path]
                    if fmt == "symbols":
                        args = ["chafa", "--format=symbols", "--size=80x40",
                                "--color-space=rgb", "--dither=fs", "--", path]
                    ret = subprocess.run(args, timeout=10).returncode
                    if ret == 0:
                        break
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
        self._update_selection_status()

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
        self._do_search(query)

    @work(thread=True)
    def _do_search(self, query: str):
        try:
            results = tmdb.search(query)
            self.call_from_thread(self._on_search_done, results)
        except (tmdb.TMDBError, requests.RequestException, ValueError,
                OSError) as e:
            self.call_from_thread(self._on_search_error, str(e))

    def _on_search_done(self, results):
        self.results = results
        self.query_one("#results_list").clear()
        for r in results:
            label = f"{r['title']} ({r['year']}) [{r['media_type']}]"
            self.query_one("#results_list").append(ListItem(Label(label)))
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
        self._load_posters(data["id"], data["media_type"])

    @work(thread=True)
    def _load_posters(self, media_id: int, media_type: str):
        try:
            posters = tmdb.get_posters(media_id, media_type)
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
            resp = tmdb._fetch(url)
            fd, tmp = tempfile.mkstemp(suffix=".jpg")
            os.close(fd)
            with open(tmp, "wb") as f:
                f.write(resp.content)
            os.chmod(tmp, 0o600)
            self.call_from_thread(self._preview_native, tmp, info)
        except (tmdb.TMDBError, requests.RequestException, OSError):
            print(f"Warning: poster preview failed: {url}", file=sys.stderr)
        finally:
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
        self._do_attach()

    @work(thread=True)
    def _do_attach(self):
        poster_path = None
        metadata = None
        to_mkv = bool(config.get("convert_to_mkv"))
        conversions: dict[str, str] = {}
        try:
            if self.local_poster_path:
                poster_path = self.local_poster_path
            else:
                fd, poster_path = tempfile.mkstemp(suffix=".jpg")
                os.close(fd)
                os.chmod(poster_path, 0o600)
                tmdb.download_image(self.selected_poster["url"], poster_path)

            if self.query_one("#meta_check").value and self.current_media:
                self.call_from_thread(
                    lambda: self.query_one("#status").update("Scraping metadata...")
                )
                metadata = tmdb.get_details(
                    self.current_media["id"], self.current_media["media_type"]
                )

            total = len(self._targets())
            ok = 0
            fail = 0
            first_error = None
            self.call_from_thread(self._set_progress, 0, total)
            for i, path in enumerate(self._targets()):
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
                for old, new in conversions.items():
                    if old in self.video_paths:
                        self.video_paths[self.video_paths.index(old)] = new
                self.call_from_thread(self._refresh_file_glyphs)

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
            if poster_path and poster_path != self.local_poster_path:
                try:
                    os.unlink(poster_path)
                except OSError:
                    pass

    @on(Button.Pressed, "#remove_btn")
    def on_remove(self):
        if not self.video_paths:
            self.query_one("#status").update("No video files loaded")
            return
        self._do_remove()

    @work(thread=True)
    def _do_remove(self):
        total = len(self._targets())
        ok = 0
        fail = 0
        self.call_from_thread(self._set_progress, 0, total)
        for i, path in enumerate(self._targets()):
            self.call_from_thread(
                lambda i=i, p=path: self.query_one("#status").update(
                    f"Removing {i+1}/{total}: {Path(p).name}"
                )
            )
            self.call_from_thread(self._set_progress, i + 1, total)
            try:
                attacher.remove_poster(path)
                ok += 1
            except OPERATION_ERRORS:
                fail += 1
        msg = f"Removed from {ok} file(s)" if fail == 0 else f"Removed: {ok}, Failed: {fail}"
        self.call_from_thread(lambda: self.query_one("#status").update(msg))

    @on(Button.Pressed, "#remove_meta_btn")
    def on_remove_metadata(self):
        if not self.video_paths:
            self.query_one("#status").update("No video files loaded")
            return
        self._do_remove_metadata()

    @work(thread=True)
    def _do_remove_metadata(self):
        total = len(self._targets())
        ok = 0
        fail = 0
        self.call_from_thread(self._set_progress, 0, total)
        for i, path in enumerate(self._targets()):
            self.call_from_thread(
                lambda i=i, p=path: self.query_one("#status").update(
                    f"Removing metadata {i+1}/{total}: {Path(p).name}"
                )
            )
            self.call_from_thread(self._set_progress, i + 1, total)
            try:
                attacher.remove_metadata(path)
                ok += 1
            except OPERATION_ERRORS:
                fail += 1
        if fail == 0:
            msg = f"Removed metadata from {ok} file(s)"
        else:
            msg = f"Removed metadata: {ok}, Failed: {fail}"
        self.call_from_thread(lambda: self.query_one("#status").update(msg))

    @on(Button.Pressed, "#convert_btn")
    def on_convert(self):
        if not self.video_paths:
            self.query_one("#status").update("No video files loaded")
            return
        self._do_convert()

    @work(thread=True)
    def _do_convert(self):
        total = len(self._targets())
        ok = 0
        fail = 0
        conversions: dict[str, str] = {}
        first_error = None
        self.call_from_thread(self._set_progress, 0, total)
        for i, path in enumerate(self._targets()):
            self.call_from_thread(
                lambda i=i, p=path: self.query_one("#status").update(
                    f"Converting {i+1}/{total}: {Path(p).name}"
                )
            )
            self.call_from_thread(self._set_progress, i + 1, total)
            try:
                out = attacher.remux_to_mkv(path)
                if out != path:
                    conversions[path] = out
                ok += 1
            except OPERATION_ERRORS as e:
                fail += 1
                if first_error is None:
                    first_error = f"{Path(path).name}: {e}"
        if conversions:
            for old, new in conversions.items():
                if old in self.video_paths:
                    self.video_paths[self.video_paths.index(old)] = new
            self.call_from_thread(self._refresh_file_glyphs)
        if fail == 0:
            msg = f"Converted {ok} file(s) to MKV"
        elif first_error:
            msg = f"Converted: {ok}, Skipped/Failed: {fail} — {first_error}"
        else:
            msg = f"Converted: {ok}, Skipped/Failed: {fail}"
        self.call_from_thread(lambda: self.query_one("#status").update(msg))
        if fail:
            self.call_from_thread(
                lambda: self.notify(f"{fail} file(s) not converted — {first_error}",
                                    severity="warning")
            )
        else:
            self.call_from_thread(lambda: self.notify(f"Converted {ok} file(s) to MKV"))

    @on(Button.Pressed, "#scrape_meta_btn")
    def on_scrape_metadata(self):
        if not self.video_paths:
            self.query_one("#status").update("No video files loaded")
            return
        self._do_scrape_metadata()

    @work(thread=True)
    def _do_scrape_metadata(self):
        targets = self._targets()
        total = len(targets)
        ok = 0
        fail = 0
        errors = []
        self.call_from_thread(self._set_progress, 0, total)
        for i, path in enumerate(targets):
            self.call_from_thread(
                lambda i=i, p=path: self.query_one("#status").update(
                    f"Scraping metadata {i+1}/{total}: {Path(p).name}"
                )
            )
            self.call_from_thread(self._set_progress, i + 1, total)
            try:
                metadata = tmdb.details_for_path(path, self.current_media)
                attacher.write_metadata(path, metadata)
                ok += 1
            except OPERATION_ERRORS as e:
                fail += 1
                errors.append(f"{Path(path).name}: {e}")
        if fail == 0:
            msg = f"Metadata written to {ok} file(s)"
        else:
            detail = " | ".join(errors)[:2000]
            msg = f"Metadata: {ok} ok, {fail} failed — {detail}"
        self.call_from_thread(lambda: self.query_one("#status").update(msg))

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
                value=str(config.get("scan_api_delay") or 0.25),
                placeholder="0.25",
                id="api_delay_input",
            )
            with Horizontal():
                yield Button("Save", id="save_btn")
                yield Button("Cancel", id="cancel_btn")

    @on(Button.Pressed, "#save_btn")
    def on_save(self):
        key = self.query_one("#api_key_input").value.strip()
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
            table.add_row(marker, g.title, season, str(len(g.files)), status, poster)
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
        entries = [self.resolved[i] for i in sorted(self._selected)]
        if not entries:
            self.notify("No groups selected", severity="warning")
            return
        embed = self.query_one("#embed_meta").value
        self.dismiss(("attach", entries, embed))

    @on(Button.Pressed, "#review_add")
    def on_add_to_list(self):
        entries = [self.resolved[i] for i in sorted(self._selected)]
        if not entries:
            self.notify("No groups selected", severity="warning")
            return
        self.dismiss(("add", entries))

    @on(Button.Pressed, "#review_cancel")
    def on_cancel(self):
        self.dismiss(None)


def main():
    missing = attacher.check_tools()
    if not shutil.which("yazi"):
        missing.append("yazi")
    if not shutil.which("chafa"):
        missing.append("chafa")
    if missing:
        print(f"Missing: {', '.join(missing)}")
        print("Install with your package manager")
        sys.exit(1)
    app = PosterTuiApp()
    app.run()


if __name__ == "__main__":
    main()
