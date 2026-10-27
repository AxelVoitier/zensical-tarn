# Release Tarn

For an engine dependency change, first follow
[Update Tarn to a new Zensical version](UPGRADING_ZENSICAL.md).

Release version 1.0.0 from the existing Git tag `v1.0.0`. Build and test that
exact source, upload its archives to TestPyPI, then promote the same files to
PyPI after review. The maintainer runs each upload command. CI has no package
upload credentials. Documentation deployment is separate.

## Prerequisites

Install [Hatch](https://hatch.pypa.io/latest/install/). Its `doc` environment
installs the local theme for previews. Its detached `check` environment runs CSS
and regression checks. Its detached `release` environment uses Python 3.12 and
the pinned `release` dependency group in `pyproject.toml`. Hatch can install the
required interpreter if it is absent. Install Playwright and Chromium separately
in the environment used for installed-wheel browser checks.

Use a complete Git checkout with all tags. Release preparation rejects shallow
history, modified tracked files, staged changes, and untracked files. Commit
release inputs, including this guide. Ignore personal editor files instead of
adding them to the release. Build outputs belong under ignored `dist/`.

Use separate accounts and API tokens for [TestPyPI](https://test.pypi.org/) and
[PyPI](https://pypi.org/). Sign in, verify your email address, and complete any
required two-factor authentication setup. TestPyPI accounts can be removed when
its database is reset. Register again if your previous account no longer exists.

Create an API token under each account's settings. If `zensical-tarn` does not
exist in your account yet, its first upload needs an account-wide token. After
that upload, replace it with a project-scoped token. Keep tokens in your password
manager or keyring. Twine uses `__token__` as its username and the API token as
its password. Enter the token at Twine's prompt, never in a committed file,
command argument, GitHub issue, or chat message.

See the [TestPyPI guide](https://packaging.python.org/en/latest/guides/using-testpypi/)
and [PyPI token instructions](https://pypi.org/help/#apitoken).

## Agreed package settings

| Item | Decision |
| --- | --- |
| Original Tarn code, documentation and design assets | Apache License 2.0; no additional branding restrictions. Standard trademark exclusions apply. |
| Public author and copyright holder | Axel Voitier. |
| Bundled third-party templates | MIT; full upstream text and attribution retained. |
| Font delivery | Google Fonts by default, with documented self-hosting. |
| Repository | https://github.com/AxelVoitier/zensical-tarn |
| Documentation | https://axelvoitier.github.io/zensical-tarn/ |
| Release version/date | `1.0.0`; no release date is assigned until publication. |

`release-review.toml` records these decisions. Its flags do not authorise an
upload. Package metadata uses `Apache-2.0 AND MIT` because the distribution
contains original Apache-licensed material and MIT-derived templates, rather
than offering a choice of licences for all files.

## Licence review

The wheel contains Tarn's own Python, CSS, configuration and templates, plus
three modified Zensical UI partials. The source archive also contains docs,
examples, design assets and screenshots. Neither archive bundles font binaries,
Zensical's JavaScript, or its icon library. Zensical is installed separately as
a dependency and retains its own licences. Referenced Lucide icons are supplied
by Zensical under ISC terms.

The copied UI templates retain the full MIT text in
`LICENSES/zensical-ui.MIT.txt`, checked against Zensical UI tag `v0.0.39`.
MIT and ISC appear in the Apache Software Foundation's
[compatible third-party licence list](https://www.apache.org/legal/resolved.html#category-a).
The [Apache 2.0 terms](https://www.apache.org/licenses/LICENSE-2.0) permit use,
modification and redistribution, including commercial use. Redistribution
requires the licence and applicable notices, and modified files must carry
change notices. There is no requirement to publish a user's documentation or
application source. Tarn copies the licence texts and NOTICE into generated sites under
`assets/licenses/tarn/`; keep these files when distributing sites. The optional
footer credit is independent of those duties.

If a root licence or NOTICE changes, update its counterpart in
`src/zensical_tarn/assets/licenses/tarn/`. The release check rejects stale copies.

Both Atkinson families use SIL OFL 1.1, as verified in the Google Fonts
[Next](https://github.com/google/fonts/blob/main/ofl/atkinsonhyperlegiblenext/OFL.txt)
and [Mono](https://github.com/google/fonts/blob/main/ofl/atkinsonhyperlegiblemono/OFL.txt)
sources. OFL requires its own copyright/licence notices when redistributing
font files; it does not relicense documents or screenshot text. Self-hosting
instructions retain these requirements. No font files are relicensed as Apache.

This review covers the files distributed by Tarn and the directly referenced
assets. The original design export is retained as supplied; adopting a licence
does not independently establish the provenance of AI-assisted artwork.

## Supported environment

- Zensical is pinned to `0.0.73`; the copied partials are checked against that
  installed version. MkDocs itself is not a supported engine.
- Python 3.11 or newer is required. The configured CI matrix covers 3.11–3.15;
  local verification results are reported separately from CI configuration.
  Python 3.15.1 has passed local package builds, regression tests, installed-wheel
  documentation/example builds, configuration checks and strict release checks
  with Zensical 0.0.73.
- The package follows the system colour preference by default. Tarn's own
  documentation deliberately starts light and retains the palette toggle.
- Fonts currently load from Google Fonts. Projects can disable loading or
  self-host them as described in the documentation.
- Zensical currently copies Python package internals into generated sites.
  The documented project-level exclusion workaround removes them. The package
  check reproduces this limitation and verifies the workaround.

## 1. Tag the reviewed source, then prepare its archives

The version comes from Git through `hatch-vcs`. A clean `v1.0.0` tag gives
version 1.0.0. Between tags, Hatch gives a development version. The package's
runtime `__version__` reads installed metadata and contains no hard-coded release
number. `CHANGELOG.md` still describes the intended release.

Review and commit all release inputs. Run the checks before creating a tag:

```bash
hatch run check:all
hatch run doc:build
git status --short
```

When you approve that commit, create an annotated tag and push it:

```bash
git tag -a v1.0.0 -m "Tarn 1.0.0"
git push origin main
git push origin v1.0.0
```

You run these commands yourself. They do not upload a package. Configure a
GitHub tag ruleset for `v*` to restrict tag updates and deletion. Do not move a
tag after its release files are reviewed or uploaded. Give each release its own
commit, even if only the changelog changes. Preparation rejects multiple version
tags on one commit because they make VCS version inference ambiguous.
The release report records
the commit and tree so that the source remains identifiable if a ref changes.

There are two ways to prepare the tagged artifacts.

For local preparation, check out the tag in a separate worktree. This leaves
your working branch available for development:

```bash
git worktree add --detach ../zensical-tarn-v1.0.0 v1.0.0
cd ../zensical-tarn-v1.0.0
hatch run release:prepare v1.0.0
```

The command writes `dist/v1.0.0/` with one wheel, one source archive and
`release-report.json`. It refuses an existing output directory. It requires the
named tag to exist and resolve to a clean HEAD. No version overrides are allowed.

Preparation clones the tagged source twice into different temporary paths. Each
build produces an sdist, then builds its wheel from that sdist without Git
metadata. Both builds use the pinned backend toolchain and the source commit's
timestamp as `SOURCE_DATE_EPOCH`. Both pairs of archives must match byte for byte.
The report records the tag name and object, commit, tree, timestamp, Python version, platform,
build tool versions and artifact hashes. It performs no upload.

Install that wheel in a separate environment before checking the rendered site:

```bash
python -m pip install dist/v1.0.0/zensical_tarn-1.0.0-py3-none-any.whl playwright
python -m playwright install chromium
python scripts/check_package.py
python scripts/check_config.py
python scripts/check_browser.py --artifacts browser-artifacts
hatch run release:check --dist dist/v1.0.0 --tag v1.0.0
```

For CI preparation, run Actions → Release preparation from the reviewed workflow
on `main`, with `v1.0.0` as its tag input. The input selects the actual source tag
once, then freezes its commit for every matrix and browser checkout. The final
job checks out that same commit and requires the tag to still point to it. It
reproduces both archives twice, and requires them to match the tested Python 3.12
artifacts. A mismatched tag, dirty source, differing build, or differing tested
archive fails preparation.

After all jobs pass, download the `release-dist` and `release-report` artifacts.
Extract their contents into `dist/v1.0.0/`. Upload only these approved files.
The intermediate `dist` artifact is the matrix result used for comparison.
No workflow uploads to either package index or creates a tag.

### Reproduce an earlier build

Use the recorded tag and Python version with the same dependency group and a
new output directory:

```bash
hatch run release:prepare v1.0.0 --output dist/reproduced-v1.0.0
```

Compare both hashes with the original report. Preparation proves two independent
builds agree under the recorded toolchain. It does not promise identical output
under arbitrary Python, operating system or build-tool versions. Update the
pinned group deliberately, along with its matching `build-system.requires` pins.
Runtime dependencies and font downloads are outside the package-build toolchain.
The pinned packages come from the configured package index; this is not an
air-gapped build or a dependency lock with download hashes.

## 2. Upload to TestPyPI

Before running this command, review the two filenames and the TestPyPI account.
This command uploads only to TestPyPI:

```bash
python -m twine upload --repository-url https://test.pypi.org/legacy/ --username __token__ dist/v1.0.0/zensical_tarn-1.0.0-py3-none-any.whl dist/v1.0.0/zensical_tarn-1.0.0.tar.gz
```

At the password prompt, enter your TestPyPI API token. Open
[the TestPyPI project](https://test.pypi.org/project/zensical-tarn/1.0.0/).
Inspect the README, images, links, author, licences, dependencies, and uploaded files.

TestPyPI and PyPI are independent registries. Version 1.0.0 on TestPyPI does not
publish or reserve that version on PyPI. Use 1.0.0 on TestPyPI to test the exact
files intended for the final release.

If a test upload needs changes, stop this promotion sequence. An index does not
allow uploaded filenames to be reused, even after deletion. Use a new candidate
version such as `1.0.0rc1` for further tests. Tag that source as `v1.0.0rc1` and
use matching archives and commands. Do not move an existing tag. When returning
to 1.0.0, repeat the full checks and record new hashes.
If TestPyPI already contains 1.0.0, revised final files need a separate review
before PyPI upload. They cannot replace the earlier TestPyPI files and must not
be described as the same tested archives.

## 3. Install the TestPyPI release in a fresh environment

Use a separate environment so the checkout and an earlier installation cannot
hide missing package files. On macOS or Linux:

```bash
python -m venv /tmp/tarn-testpypi-1.0.0
/tmp/tarn-testpypi-1.0.0/bin/python -m pip install --index-url https://pypi.org/simple/ "zensical==0.0.73"
/tmp/tarn-testpypi-1.0.0/bin/python -m pip install --index-url https://test.pypi.org/simple/ --no-deps "zensical-tarn==1.0.0"
/tmp/tarn-testpypi-1.0.0/bin/python -m pip check
/tmp/tarn-testpypi-1.0.0/bin/python scripts/check_package.py
/tmp/tarn-testpypi-1.0.0/bin/python scripts/check_config.py
```

On Windows, use the environment's `Scripts/python.exe` instead of `bin/python`.
Install Zensical from PyPI first, then fetch only Tarn from TestPyPI. This keeps
the test package source explicit and avoids resolving dependencies across two
indexes. The installed-wheel checks build the main documentation and minimal
example outside the checkout. Inspect their output and try the theme yourself.

Compare the installed or downloaded wheel's SHA-256 hash with
`release-report.json` before promotion. Download the tested wheel with:

```bash
python -m pip download --index-url https://test.pypi.org/simple/ --no-deps --only-binary=:all: --dest dist/testpypi-download "zensical-tarn==1.0.0"
```

Calculate its hash with `python -m pip hash` and compare it with the report's
wheel hash. PyPI's file details also show hashes for both uploaded archives.

## 4. Upload the reviewed files to PyPI

Proceed only after TestPyPI installation and site checks pass. Review the exact
files, their hashes, version, release commit, and production account again.
If the source changes, build and review a new set of archives before uploading.

The source tag already exists from step 1. Confirm that it still resolves to
the report's commit. Do not create or move it at upload time. A GitHub release
can be created separately from that same tag.

The following command publishes to the real PyPI. The maintainer runs it as a
separate decision after the test release:

```bash
python -m twine upload --repository-url https://upload.pypi.org/legacy/ --username __token__ dist/v1.0.0/zensical_tarn-1.0.0-py3-none-any.whl dist/v1.0.0/zensical_tarn-1.0.0.tar.gz
```

At the password prompt, enter your production PyPI API token. Use the exact
archives tested above. Do not rebuild them or use `--skip-existing` to hide a
collision. Uploaded filenames cannot be replaced, even after deletion. See
[PyPI's filename policy](https://pypi.org/help/#file-name-reuse).

## 5. Confirm the production release

Open [the PyPI project](https://pypi.org/project/zensical-tarn/1.0.0/). Compare its
file hashes with the reviewed report. In another fresh environment, install
`zensical-tarn==1.0.0` from PyPI, run `python -m pip check`, and repeat the
installed-theme checks from step 3 with that environment's Python interpreter.

Keep the release commit, tag, archives, report, and registry links together.
Record the publication date once the upload succeeds.

## Workflow behaviour

| Workflow | Automatic runs | Manual runs |
| --- | --- | --- |
| Package checks (`check.yml`) | Pushes to `main` affecting package inputs, examples, design assets, screenshots, scripts, tests, or its workflow files. | Available directly; also called in full by Release preparation. |
| Documentation (`docs.yml`) | Pushes to `main` affecting documentation, site configuration, theme source, package metadata, or its workflow file. | Available on `main`; builds and deploys the site to GitHub Pages. |
| Release preparation (`release-preparation.yml`) | None. | Requires an existing tag, checks that exact source, reproduces its archives twice and compares them with the tested archives. |

Documentation-only changes run the docs build without the full Python matrix
or browser checks. Changes to administrative notes such as `HANDOFF.md`,
`PACKAGE_REVIEW.md`, and this guide do not start automatic runs. Manual and
reusable calls bypass the push path filters and run their complete workflow.

New runs cancel older runs of the same workflow on the same branch. Called
package checks have a separate concurrency group for each calling workflow,
so release preparation cannot cancel itself or an ordinary package-check run.
Jobs have time limits as well. All jobs still use GitHub-hosted Ubuntu runners;
browser checks still use Chromium on Python 3.12.

Package and release checks produce downloadable archives, browser screenshots,
and reports. They do not upload to PyPI or TestPyPI or create GitHub releases.
The separate Documentation workflow deploys the main site to GitHub Pages.
Package uploads remain the maintainer's explicit commands in steps 2 and 4.
An untagged build or the older `dist/1.0.0` preparation output is not a release
candidate under this procedure. Prepare fresh tagged archives.

## Pull requests and workflow security

Automatic PR runs are disabled. There are no `pull_request`,
`pull_request_target`, or `workflow_run` triggers. Automatic pushes are limited
to `main`; pushing a contributor branch does not start these workflows.
Building and testing a contribution executes its Python, build hooks, templates
and scripts, so a read-only token cannot guarantee that contributed code is
harmless. This follows the owner's preference to avoid automatic PR execution.

Review contributions before merging them into `main`. A manual run can select
another branch, so review that branch's code and workflow changes before
starting it. Release preparation uses the selected branch's workflow definition
but checks out the tag input for all source builds. Review both that workflow
and the selected tag. It never creates a Git tag.

Package and release workflows request only `contents: read`. The documentation
build also reads Pages configuration. Its separate deployment job requests
`pages: write` and `id-token: write`, restricted to `main` and the `github-pages`
environment. These workflows do not use package-upload credentials.
Checkout does not persist Git credentials, and all
external actions are pinned to verified commits from their official
repositories. Update these pins deliberately after reviewing upstream changes.
The selected tag enters the shell through a quoted environment variable.
These measures reduce risk; they do not prove dependencies or merged code are
free of malware. See GitHub's
[secure-use guidance](https://docs.github.com/en/actions/reference/security/secure-use).

These YAML files do not enforce repository settings or prevent a contribution
from proposing new workflows. In GitHub settings, protect `main`, require review
of workflow changes, and require approval for workflows from all outside
contributors. Those repository settings have not been changed here. Disabling
the existing PR triggers is not a repository-wide ban on future PR workflows.

If uploads later move into CI, use
[PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/using-a-publisher/)
with a dedicated environment and a manual approval step. Configure separate
publishers for TestPyPI and PyPI. Review the repository's available environment
protection rules before relying on them. No package-upload workflow is installed
by this procedure.

The metadata format follows the
[Python Packaging User Guide](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/#license-and-license-files).
