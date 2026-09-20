PYTHON ?= python3
export PYTHONPATH := $(CURDIR)/src

.PHONY: check test demo
check: test

test:
	$(PYTHON) -m unittest discover -s tests -v

demo:
	$(PYTHON) -m wavebridge demo
