#!/usr/bin/env python3
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import (
    Button, Footer, Header, Input, Label, ListItem, ListView, ProgressBar, Static,
)

import config
from core import attacher, parser, tmdb


CSS = """
Screen {
    layout: grid;
    grid-size: 3 1;
    grid-columns: 1fr 2fr 2fr;
}
#left_col, #mid_col, #right_col {
    border: solid $primary;
    padding: 0 1;
}
ListView { height: 1fr; }
#poster_gallery { height: 4fr; }
#file_list { height: 3fr; }
#path_row, #btn_row, #action_row { height: 3; }
"""


YOCTO_FILE = "/tmp/pa-yazi-choice"


class PosterTuiApp(App):
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("ctrl+tab", "focus_next_panel", "Next Panel"),
        Binding("ctrl+shift+tab", "focus_prev_panel", "Prev Panel"),
        Binding("ctrl+l", "focus_left_panel", "Left (Search)"),
        Binding("ctrl+m", "focus_mid_panel", "Mid (Posters)"),
        Binding("ctrl+r", "focus_right_panel", "Right (Files)"),
    ]

    TITLE = "mak-attatch TUI"
    CSS = CSS

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
            with Horizontal(id="path_row"):
                yield Input(placeholder="Paste video path(s)...", id="path_input")
                yield Button("Add", id="add_path_btn")
            with Horizontal(id="btn_row"):
                yield Button("Local Image", id="local_img_btn")
                yield Button("Settings", id="settings_btn")
            with Horizontal(id="action_row"):
                yield Button("Attach", id="attach_btn", disabled=True)
                yield Button("Remove", id="remove_btn")
            yield ProgressBar(id="progress", show_eta=False)
            yield Label("Ready", id="status")
        yield Footer()

    def __init__(self):
        super().__init__()
        self.video_paths: list[str] = []
        self.results: list[dict] = []
        self.posters: list[dict] = []
        self.selected_poster: dict | None = None
        self.local_poster_path: str | None = None

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
        try:
            os.unlink(YOCTO_FILE)
        except FileNotFoundError:
            pass
        proc = subprocess.run(
            ["yazi", "--chooser-file", YOCTO_FILE, start_dir],
            timeout=300,
        )
        if proc.returncode == 0 and os.path.exists(YOCTO_FILE):
            path = Path(YOCTO_FILE).read_text().strip()
            if path:
                return path
        return None

    @on(Button.Pressed, "#browse_btn")
    def on_browse(self):
        try:
            with self.suspend():
                path = self._yazi_pick()
        except FileNotFoundError:
            self.query_one("#status").update("yazi not found. Install: sudo pacman -S yazi")
            return
        if path:
            self._add_video_path(path)

    def _add_video_path(self, path: str):
        if not os.path.isfile(path):
            self.query_one("#status").update(f"Not a file: {path}")
            return
        p = os.path.abspath(path)
        if p in self.video_paths:
            self.query_one("#status").update(f"Already added: {Path(p).name}")
            return
        self.video_paths.append(p)
        self.query_one("#file_list").append(ListItem(Label(Path(p).name)))
        self.query_one("#files_label").update(f"Video Files ({len(self.video_paths)}):")
        config.set("last_dir", str(Path(p).parent))
        if len(self.video_paths) == 1:
            parsed = parser.parse_filename(p)
            self.query_one("#search_input").value = parser.build_search_query(parsed)
            self.action_search()

    @on(Input.Submitted, "#path_input")
    @on(Button.Pressed, "#add_path_btn")
    def on_add_path(self):
        raw = self.query_one("#path_input").value.strip()
        if not raw:
            return
        for line in raw.splitlines():
            line = line.strip().strip("\"'")
            if line:
                expanded = os.path.expanduser(line)
                if os.path.isfile(expanded):
                    self._add_video_path(expanded)
                else:
                    self.query_one("#status").update(f"Not found: {line}")
        self.query_one("#path_input").value = ""

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
                subprocess.run(["clear"])
                for fmt in ("kitty", "sixel", "symbols"):
                    args = ["chafa", "--format=" + fmt, path]
                    if fmt == "symbols":
                        args = ["chafa", "--format=symbols", "--size=80x40",
                                "--color-space=rgb", "--dither=fs", path]
                    ret = subprocess.run(args, timeout=10).returncode
                    if ret == 0:
                        break
                if info:
                    print(f"\n{info}")
                print("\nPress Enter to return...")
                input()
        except FileNotFoundError:
            pass
        except Exception:
            pass

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
        except Exception as e:
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
        self.query_one("#status").update(f"Loading posters for {data['title']}...")
        self._load_posters(data["id"], data["media_type"])

    @work(thread=True)
    def _load_posters(self, media_id: int, media_type: str):
        try:
            posters = tmdb.get_posters(media_id, media_type)
            self.call_from_thread(self._on_posters_loaded, posters)
        except Exception as e:
            self.call_from_thread(self._on_search_error, str(e))

    def _on_posters_loaded(self, posters):
        self.posters = posters
        self.query_one("#poster_label").update(f"Posters ({len(posters)}):")
        gallery = self.query_one("#poster_gallery")
        gallery.clear()
        for idx, p in enumerate(posters):
            gallery.append(
                ListItem(
                    Label(
                        f"{p['width']}x{p['height']} [{p.get('lang') or '??'}]",
                    ),
                    id=f"cell_{idx}",
                )
            )
        self.query_one("#status").update("Posters: click to select")

    @on(ListView.Selected, "#poster_gallery")
    def on_poster_selected(self, event: ListView.Selected):
        item = event.item
        if not item.id or not item.id.startswith("cell_"):
            return
        try:
            idx = int(item.id.split("_")[1])
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
            tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
            tmp.write(resp.content)
            tmp.close()
            self.call_from_thread(self._preview_native, tmp.name, info)
        except Exception:
            pass
        finally:
            if tmp:
                try:
                    os.unlink(tmp.name)
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
        try:
            if self.local_poster_path:
                poster_path = self.local_poster_path
            else:
                fd, poster_path = tempfile.mkstemp(suffix=".jpg")
                os.close(fd)
                os.chmod(poster_path, 0o600)
                tmdb.download_image(self.selected_poster["url"], poster_path)

            total = len(self.video_paths)
            ok = 0
            fail = 0
            for i, path in enumerate(self.video_paths):
                self.call_from_thread(
                    lambda i=i, p=path: self.query_one("#status").update(
                        f"Attaching {i+1}/{total}: {Path(p).name}"
                    )
                )
                try:
                    attacher.full_attach(path, poster_path)
                    ok += 1
                except Exception:
                    fail += 1

            msg = f"Attached to {ok} file(s)" if fail == 0 else f"Attached: {ok}, Failed: {fail}"
            self.call_from_thread(lambda: self.query_one("#status").update(msg))
        except Exception as e:
            self.call_from_thread(lambda: self.query_one("#status").update(f"Error: {e}"))
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
        total = len(self.video_paths)
        ok = 0
        fail = 0
        for i, path in enumerate(self.video_paths):
            self.call_from_thread(
                lambda i=i, p=path: self.query_one("#status").update(
                    f"Removing {i+1}/{total}: {Path(p).name}"
                )
            )
            try:
                attacher.remove_poster(path)
                ok += 1
            except Exception:
                fail += 1
        msg = f"Removed from {ok} file(s)" if fail == 0 else f"Removed: {ok}, Failed: {fail}"
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
            with Horizontal():
                yield Button("Save", id="save_btn")
                yield Button("Cancel", id="cancel_btn")

    @on(Button.Pressed, "#save_btn")
    def on_save(self):
        key = self.query_one("#api_key_input").value.strip()
        config.set("tmdb_api_key", key)
        self.notify("Settings saved!")
        self.dismiss()

    @on(Button.Pressed, "#cancel_btn")
    def on_cancel(self):
        self.dismiss()


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
