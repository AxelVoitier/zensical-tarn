# Package checks

For an engine dependency update, follow the complete
[Zensical upgrade procedure](../UPGRADING_ZENSICAL.md). The commands below
describe individual checks rather than the full upgrade sequence.

Use Python 3.11 or newer in a virtual environment. From the repository root:

```bash
python -m pip install build twine
python scripts/build_css.py --check
python -m unittest discover -s tests -v
python -m build
python -m twine check --strict dist/*
python -m pip install --force-reinstall dist/*.whl
python scripts/check_package.py
python scripts/check_config.py
```

Use an empty `dist/` directory for a new build. By default, `python -m build`
creates a source archive and builds the wheel from that archive. The package
check requires a wheel installation outside the checkout; an editable install
does not verify which files would reach users.

CI runs these checks on Python 3.11, 3.12, 3.13, 3.14, and 3.15 for relevant
pushes to `main`, or when invoked manually. PRs and contributor branch pushes
do not trigger checks automatically. Documentation-only changes run the docs
workflow instead. New runs cancel older runs on the same branch.
The manual release
preparation workflow calls the same checks and inspects the tested Python 3.12
artifacts without publishing them. Documentation deployment is also disabled.
See [release preparation](../RELEASING.md) for agreed package settings and local checks.
Its workflow file is `.github/workflows/release-preparation.yml`. Review a
branch's code and workflows before manually running checks on it; builds and
tests execute that code. See the guide's security section for repository settings
that need separate configuration on GitHub.

`python scripts/check_release.py --report release-report.json` checks local
archives and reports unresolved release decisions. Add `--strict` to fail on
those decisions and placeholder URLs as well as artifact errors. `--tag v0.1.0`
checks version agreement without creating a tag. Nothing is uploaded.

## Generated CSS

`build_css.py --check` runs the contrast checks and compares the generated result
with the committed stylesheet without writing to it. Missing or stale CSS fails
the check. Run `python scripts/build_css.py` to regenerate it after a token change.
Neither mode writes CSS if a contrast check fails.

To refresh the rendered documentation images after regenerating CSS, install
the updated wheel, then run:

```bash
python scripts/capture_screenshots.py
```

This requires Playwright, Chromium, and internet access for the configured
Google fonts. It refreshes `screenshots/site/`, `screenshots/components/`, and
the screenshots embedded in `docs/assets/screenshots/`. Use `--executable`
to select an existing Chromium installation. Rebuild the documentation and
source archive afterwards to include the refreshed images. Original design
preview cards and logo exports have no regeneration sources in this repository.

## Upstream template overrides

`check_upstream.py` compares the installed Tarn navigation and copyright
overrides with the templates in the installed Zensical distribution. It removes only the leading
file comments and Tarn's documented additions. Missing additions and any other
differences fail with a diff. It needs no network access.

Tarn pins Zensical to 0.0.73, whose navigation templates were exported
from UI v0.0.39. To support another Zensical release, review its templates,
update the dependency constraint, and run the package checks with that version.
A matching template comparison alone does not establish browser compatibility.

## Configuration and browser checks

`check_config.py` builds fixtures for independent decoration switches, translated
labels, custom section mappings, nested sections, direct pages, flat URLs,
sidebar navigation, disabled/custom fonts, palette replacement, and a local
template override. It uses the installed theme's real MiniJinja templates.

The section alias map is defined only in `partials/tarn.html`. Both navigation
partials and the badge call its helpers; generated CSS selects the resulting
`data-tarn-type` values. New aliases do not require CSS changes.

For browser checks, install Playwright and Chromium in the test environment:

```bash
python -m pip install playwright
python -m playwright install chromium
python scripts/check_browser.py --artifacts browser-artifacts
```

The script runs a local HTTP server and checks light/dark appearances at mobile,
tablet, and desktop widths, drawer opening/closing, keyboard focus, search,
content tabs, font settings, named palette colours, and project CSS overrides.
It saves screenshots and a JSON report. External requests are blocked, so these
checks do not establish the appearance of downloaded Google fonts. Use
`--executable /path/to/chromium` to select an existing Chromium installation.

The browser job also runs before publication. These regression checks do not
establish full accessibility conformance.

## Generated site contents

`check_package.py` copies the documentation and example into a temporary
directory and builds them in strict mode using the installed wheel. It checks
the actual stylesheet link and copied CSS, four navigation tab attributes,
the how-to badge, and generated output for package internals.

Zensical 0.0.73 copies theme files into generated sites, including
`__init__.py`, `__pycache__/__init__.cpython-<version>.pyc`, and
`mkdocs_theme.yml`. The check reports these exact known paths for the unmodified
minimal example and fails on additional Python or YAML files. They are a known
output limitation, not a clean-output pass.

The following **project-level** setting removes those files:

```toml
[project.plugins.exclude]
glob = ["__init__.py", "__pycache__/*", "mkdocs_theme.yml"]
```

Merge these patterns into an existing exclusion configuration if necessary.
They also exclude documentation assets with these paths. This repository's
documentation uses the setting; the minimal example keeps a plain theme
selection so the check continues to reproduce the original behaviour. The check
also rebuilds that example with the exclusions and requires clean output from
both this build and Tarn's documentation.

The original investigation used the tagged Zensical 0.0.72 source below.
The same output limitation and exclusion workaround are verified by the
installed-wheel checks with Zensical 0.0.73:

- [Theme directory discovery](https://github.com/zensical/zensical/blob/v0.0.72/python/zensical/config.py)
  uses the entry point module's `__file__`. Moving files to a normal subpackage
  would leave another Python initializer in the theme directory.
- [Resource exclusion](https://github.com/zensical/zensical/blob/v0.0.72/crates/zensical/src/compat/mkdocs/plugin/exclude.rs)
  filters effective assets, including theme resources. The project-level
  workaround was verified with a built wheel.

The packaged theme's defaults are merged into `project.theme`, so they cannot
set `project.plugins.exclude` for consuming projects. There is no automatic
package-level fix in this batch. Avoid altering Python module metadata or
monkey-patching Zensical to change its asset handling.

## Python maintenance checks

Use an environment with the built Tarn wheel, Playwright, Ruff and Pyright
installed. `pyrightconfig.json` checks every Python source file in strict mode
against the minimum supported Python version, 3.11. Point Pyright at the same
interpreter that has the check scripts' dependencies installed.

The following commands use Axel's global Ruff configuration. Replace the config
path if your settings are stored elsewhere:

```bash
python -m pip install ruff pyright playwright
ruff format --config "$HOME/.config/ruff/ruff.toml" --target-version py311 scripts tests src
ruff check --config "$HOME/.config/ruff/ruff.toml" --target-version py311 --extend-ignore COM812 scripts tests src
pyright --pythonpath "$(python -c 'import sys; print(sys.executable)')"
python -m unittest discover -s tests -v
python scripts/build_css.py --check
```

`COM812` is excluded because it conflicts with Ruff's formatter. The source files
explain their other lint exceptions. These preserve existing control flow,
inline validation messages, command-line output, literal CSS and fixture data,
and unittest assertions. The two HTTP handlers retain their original positional
no-op overrides, with a specific Pyright exception for the inherited keyword
signature. Do not use automatic fixes that extract functions, replace loops or
lambdas, or change the test framework as part of a formatting pass.
