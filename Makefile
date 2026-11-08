PY := $(CURDIR)/.venv/bin/python

setup:  ## create the venv with the exact versions in task2/requirements-lock.txt
	uv venv --clear --python $$(cat .python-version) .venv && uv pip install -q --python $(PY) -r task2/requirements-lock.txt

test:  ## Task 2 offline tests (no network, no model)
	cd task2 && $(PY) -m pytest -q test_baseline.py test_parsing.py test_facts.py test_traps.py test_safety.py
