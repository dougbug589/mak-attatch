PREFIX ?= /usr/local
APP = mak-attatch
PYTHON = python3

all: venv

venv:
	$(PYTHON) -m venv .venv
	.venv/bin/pip install -q --upgrade pip
	.venv/bin/pip install -q -r requirements.txt

install:
	mkdir -p $(DESTDIR)$(PREFIX)/lib/$(APP)
	mkdir -p $(DESTDIR)$(PREFIX)/bin
	mkdir -p $(DESTDIR)$(PREFIX)/share/applications
	mkdir -p $(DESTDIR)$(PREFIX)/share/pixmaps
	cp -r core ui poster_tui config.py main.py cli.py poster-tui requirements.txt assets $(DESTDIR)$(PREFIX)/lib/$(APP)/
	cp assets/logo.png $(DESTDIR)$(PREFIX)/share/pixmaps/$(APP).png
	printf '#!/bin/sh\nexec python3 $(PREFIX)/lib/$(APP)/main.py "$$@"\n' > $(DESTDIR)$(PREFIX)/bin/$(APP)
	chmod +x $(DESTDIR)$(PREFIX)/bin/$(APP)
	printf '#!/bin/sh\nexec python3 $(PREFIX)/lib/$(APP)/poster-tui "$$@"\n' > $(DESTDIR)$(PREFIX)/bin/$(APP)-tui
	chmod +x $(DESTDIR)$(PREFIX)/bin/$(APP)-tui
	printf '#!/bin/sh\nexec python3 $(PREFIX)/lib/$(APP)/cli.py "$$@"\n' > $(DESTDIR)$(PREFIX)/bin/$(APP)-cli
	chmod +x $(DESTDIR)$(PREFIX)/bin/$(APP)-cli
	cp mak-attatch.desktop $(DESTDIR)$(PREFIX)/share/applications/

uninstall:
	rm -rf $(DESTDIR)$(PREFIX)/lib/$(APP)
	rm -f $(DESTDIR)$(PREFIX)/bin/$(APP)
	rm -f $(DESTDIR)$(PREFIX)/bin/$(APP)-tui
	rm -f $(DESTDIR)$(PREFIX)/bin/$(APP)-cli
	rm -f $(DESTDIR)$(PREFIX)/share/applications/mak-attatch.desktop
	rm -f $(DESTDIR)$(PREFIX)/share/pixmaps/$(APP).png

clean:
	rm -rf .venv __pycache__ ui/__pycache__ core/__pycache__ poster_tui/__pycache__

.PHONY: all venv install uninstall clean
