PREFIX ?= /usr/local
APP = mak-attatch
PYTHON ?= python3
LIBDIR = $(PREFIX)/lib/$(APP)
VENV_DIR = $(LIBDIR)/.venv
ICONDIR = $(PREFIX)/share/icons/hicolor/256x256/apps

all: venv

venv:
	$(PYTHON) -m venv .venv
	.venv/bin/pip install -q --upgrade pip
	.venv/bin/pip install -q -r requirements.txt

# Launchers prefer the private venv and fall back to the system python3.
define launcher
printf '#!/bin/sh\nDIR="%s"\nif [ -x "$$DIR/.venv/bin/python" ]; then exec "$$DIR/.venv/bin/python" "$$DIR/%s" "$$@"; fi\nexec python3 "$$DIR/%s" "$$@"\n' "$(LIBDIR)" "$(2)" "$(2)" > "$(DESTDIR)$(PREFIX)/bin/$(1)"
chmod +x "$(DESTDIR)$(PREFIX)/bin/$(1)"
endef

install:
	mkdir -p "$(DESTDIR)$(LIBDIR)" "$(DESTDIR)$(PREFIX)/bin" \
		"$(DESTDIR)$(PREFIX)/share/applications" "$(DESTDIR)$(ICONDIR)"
	cp -r mak_attatch main.py cli.py poster-tui requirements.txt "$(DESTDIR)$(LIBDIR)/"
	# hicolor is where desktop environments look for app icons under any PREFIX.
	cp mak_attatch/assets/icon.png "$(DESTDIR)$(ICONDIR)/$(APP).png"
	@if [ -z "$(DESTDIR)" ]; then \
		$(PYTHON) -m venv "$(VENV_DIR)"; \
		"$(VENV_DIR)/bin/pip" install -q --upgrade pip; \
		"$(VENV_DIR)/bin/pip" install -q -r "$(LIBDIR)/requirements.txt"; \
	else \
		echo "DESTDIR set: skipping in-tree venv; launchers fall back to python3"; \
	fi
	$(call launcher,$(APP),main.py)
	$(call launcher,$(APP)-tui,poster-tui)
	$(call launcher,$(APP)-cli,cli.py)
	cp mak-attatch.desktop "$(DESTDIR)$(PREFIX)/share/applications/"
	@# Package builds (DESTDIR) must not ship an icon cache; distros regenerate it.
	@if [ -z "$(DESTDIR)" ]; then \
		gtk-update-icon-cache -q -t "$(PREFIX)/share/icons/hicolor" 2>/dev/null || true; \
	fi

uninstall:
	rm -rf "$(DESTDIR)$(LIBDIR)"
	rm -f "$(DESTDIR)$(PREFIX)/bin/$(APP)" "$(DESTDIR)$(PREFIX)/bin/$(APP)-tui" \
		"$(DESTDIR)$(PREFIX)/bin/$(APP)-cli"
	rm -f "$(DESTDIR)$(PREFIX)/share/applications/mak-attatch.desktop"
	rm -f "$(DESTDIR)$(ICONDIR)/$(APP).png"
	# Icon location used by releases up to 1.3.5.
	rm -f "$(DESTDIR)$(PREFIX)/share/pixmaps/$(APP).png"

clean:
	rm -rf .venv build dist *.egg-info
	find . -name __pycache__ -type d -prune -exec rm -rf {} +

.PHONY: all venv install uninstall clean
