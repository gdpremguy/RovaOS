PYTHON ?= python3

.PHONY: test iso verify refresh website

test:
	$(PYTHON) -B -m unittest discover -s tests

# Requires the pinned Niri package; see linux/README.md for a clean first build.
iso:
	ROVA_DESKTOP=niri bash linux/build.sh

verify:
	$(PYTHON) -B linux/verify.py rovaos.iso

refresh:
	bash linux/refresh_niri.sh

website:
	$(PYTHON) -B website/build.py
