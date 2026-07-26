PREFIX ?= /usr/local
APP = poster-attacher
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
	cp -r core ui config.py main.py requirements.txt P.png $(DESTDIR)$(PREFIX)/lib/$(APP)/
	cp -r .venv $(DESTDIR)$(PREFIX)/lib/$(APP)/
	echo '#!/bin/sh' > $(DESTDIR)$(PREFIX)/bin/$(APP)
	echo 'exec $(PREFIX)/lib/$(APP)/.venv/bin/python $(PREFIX)/lib/$(APP)/main.py "$$@"' >> $(DESTDIR)$(PREFIX)/bin/$(APP)
	chmod +x $(DESTDIR)$(PREFIX)/bin/$(APP)
	cp poster-attacher.desktop $(DESTDIR)$(PREFIX)/share/applications/

uninstall:
	rm -rf $(DESTDIR)$(PREFIX)/lib/$(APP)
	rm -f $(DESTDIR)$(PREFIX)/bin/$(APP)
	rm -f $(DESTDIR)$(PREFIX)/share/applications/poster-attacher.desktop

clean:
	rm -rf .venv __pycache__ ui/__pycache__ core/__pycache__

.PHONY: all venv install uninstall clean
