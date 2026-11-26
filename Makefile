PYTHON := .venv/bin/python

.PHONY: install smoke validate radio film regen test clean

SHOT ?= s03
STAGE ?= keyframes

install:
	python3 -m venv .venv
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -r requirements.txt

smoke:
	$(PYTHON) heritage_studio.py smoke

validate:
	$(PYTHON) heritage_studio.py validate

radio:
	$(PYTHON) heritage_studio.py radio $(if $(FORCE),--force,)

film:
	$(PYTHON) heritage_studio.py run

regen:
	$(PYTHON) heritage_studio.py regen --stage $(STAGE) --shot $(SHOT)
	$(PYTHON) heritage_studio.py run

test:
	$(PYTHON) -m pytest -v

clean:
	rm -rf outputs runs.jsonl
