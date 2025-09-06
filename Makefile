PY = python
PIP = pip

.PHONY: setup test lint format run

setup:
	$(PIP) install -e .[dev]

test:
	pytest

lint:
	ruff check .
	mypy .

format:
	black .
	ruff check . --fix

run:
	$(PY) -m cli.main --help

