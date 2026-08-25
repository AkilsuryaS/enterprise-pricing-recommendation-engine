PYTHON := .venv/bin/python

.PHONY: install data train test api package

install:
	python -m venv .venv
	.venv/bin/pip install -e '.[dev]'

data:
	$(PYTHON) scripts/download_public_data.py --catalog-size 17000

train:
	$(PYTHON) scripts/run_pipeline.py --config configs/base.yaml

test:
	$(PYTHON) -m pytest -q

api:
	PYTHONPATH=src $(PYTHON) -m uvicorn pricing_engine.api:app --host 0.0.0.0 --port 8000

package:
	bash scripts/package_project.sh

