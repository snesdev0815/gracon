DESTDIR?=
PREFIX ?= /usr/local
BINDIR := $(PREFIX)/bin

install:
	@echo Installing gracon python scripts
	@install -m 755 *.py $(DESTDIR)$(BINDIR)/
	@echo gracon installation completed
