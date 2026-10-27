---
tarn:
  type: none
---
# Contributing

Use this guide to set up a local Tarn checkout, preview changes and choose the
checks for your contribution. Run the commands from the repository root unless
a step says otherwise.

## Work on the theme

Start with an existing source checkout. You need Python 3.11 or newer and its
`venv` module. Tarn installs Zensical 0.0.73 as a pinned dependency.

Create and activate a virtual environment with the commands for your terminal:

=== "Linux / macOS (Bash)"

    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    ```

=== "Windows (PowerShell)"

    ```powershell
    py -3 -m venv .venv
    .\.venv\Scripts\Activate.ps1
    ```

Then install Tarn in editable mode so that the preview uses your source files:

```sh
python -m pip install -e .
zensical serve
```

Open the local address printed by Zensical. Edit a documentation page or theme
file and inspect the preview. Stop the server with Ctrl+C before running other
commands in that terminal.

If you use Make, `make serve-doc` opens this documentation preview in your
browser. Use `make serve-example` to preview `examples/minimal-site/` instead.
Both commands require the activated environment.

## Change a colour or size

Edit the relevant value in `design/tokens.json`, then regenerate the stylesheet:

```sh
python scripts/build_css.py
python scripts/build_css.py --check
```

The generator writes `src/zensical_tarn/assets/stylesheets/tarn.css`. It checks
the configured text contrast pairs and writes no CSS if a pair fails.
The `--check` command compares the generated CSS with the existing file without
writing to it. It fails if the stylesheet is missing or stale.

Preview the affected pages in light and dark modes. Include the token file and
regenerated stylesheet together in your contribution. Consult the
[design sources](https://github.com/AxelVoitier/zensical-tarn/blob/main/design/README.md)
for the supplied tokens and artwork. To change only your own site's colours,
follow [Adjust a colour](../how-to/adjust-colours.md).

## After a Zensical upgrade

For the complete maintainer procedure, follow
[Update Tarn to a new Zensical version](https://github.com/AxelVoitier/zensical-tarn/blob/main/UPGRADING_ZENSICAL.md).
It covers release inspection, copied templates and licences, installed-wheel
checks, browser checks, screenshots and final local artifacts.

Tarn maintains three copied Zensical UI partials in
`src/zensical_tarn/partials/`: `nav-item.html`, `tabs-item.html` and
`copyright.html`. The navigation partials add Tarn attributes, and the copyright
partial adds the optional Tarn footer credit. Their Tarn additions call helpers
in `partials/tarn.html`.

When proposing a dependency upgrade, review the new upstream templates and
update the Zensical pin in `pyproject.toml`. Install that version in your local
environment, then reconcile the copied partials with it. Retain the upstream
attribution and licence notices.

Run the comparison against the installed theme and Zensical:

```sh
python scripts/check_upstream.py
```

The script removes the leading file comments and the exact Tarn additions
recorded in `scripts/check_upstream.py` before comparing the files. If an
intentional change alters those additions, update the comparison script too.
Any other difference fails with a diff. The command works with your editable
installation and needs no network access.

A matching comparison confirms template agreement. Run the package,
configuration and browser checks in the
[script guide](https://github.com/AxelVoitier/zensical-tarn/blob/main/scripts/README.md)
to assess the upgraded theme's behaviour as well.

If you are extending a template for one documentation project, use
[local templates](../reference/configuration.md#local-templates) instead of
changing Tarn's copied partials.

## Choose checks for your change

For a documentation change, build the site and inspect the affected pages:

```sh
zensical build --strict --clean
```

A successful command writes the site to `site/`. For theme logic changes, also
run the regression tests:

```sh
python -m unittest discover -s tests -v
```

For changes to packaged files, configuration or templates, follow the
[script guide](https://github.com/AxelVoitier/zensical-tarn/blob/main/scripts/README.md).
It covers package builds, configuration fixtures, browser checks and screenshot
capture, including their extra dependencies.

The installed-theme checks, `check_package.py` and `check_config.py`, require a
built wheel installed in place of the editable installation. This checks the
files that the distribution actually contains. An editable preview alone does
not test package contents. Use a separate test environment if you want to keep
your editable preview environment.

For release preparation, use the complete procedure in the
[release guide](https://github.com/AxelVoitier/zensical-tarn/blob/main/RELEASING.md).
The current documentation workflow builds a downloadable site artifact.
Documentation deployment is disabled while the first release is in preparation.
