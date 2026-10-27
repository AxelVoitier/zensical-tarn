serve-doc:
	zensical serve --open

serve-example:
	zensical serve -f examples/minimal-site/zensical.toml --open

.PHONY: serve-doc serve-example release-check

PYTHON ?= python

release-check:
	$(PYTHON) scripts/check_release.py --report release-report.json
