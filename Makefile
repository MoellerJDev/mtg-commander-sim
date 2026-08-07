PYTHON ?= python
DB ?= data/scryfall-20260728-compact.sqlite3

.PHONY: test demo compile wheel clean

compile:
	$(PYTHON) -m compileall -q quorune tests scripts simctl.py

test: compile
	MTG_CARD_DB=$(DB) $(PYTHON) -m unittest discover -s tests -p 'test_*.py' -v

demo:
	$(PYTHON) scripts/demo_four_player_protocol.py --db $(DB) --out demo

wheel:
	$(PYTHON) -m pip wheel . --no-deps --no-build-isolation --wheel-dir dist

clean:
	rm -rf build dist *.egg-info .pytest_cache
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
