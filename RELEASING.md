# Release Tarn

For an engine dependency change, first follow
[Update Tarn to a new Zensical version](UPGRADING_ZENSICAL.md).

The tagged coordinator is implemented for local verification. Hosted activation,
registry uploads and final GitHub publication remain disabled pending separate
setup and remote proof. The existing `1.0.0` files and tag are outside this work.
The manual procedure below records the earlier release path.

## Tagged start and recovery

A candidate is a frozen selection of source, archives and build evidence.
A recovery copy holds the original archives and their signed build evidence.
The coordinator uses the instructions in the selected product tag.
It rejects dispatch from `main` with an old tag supplied as data.
Keep `workflow_dispatch` available on the default branch so historical tags remain selectable.

After hosted setup and proof, the intended normal start is website tag creation.
The website route must persist the tag without publishing a GitHub release.
Actual website events and permitted tag-update delivery remain unproven.
Use the remote-tag CLI fallback only if the website route proves unavailable.
Do not recreate or move `v1.0.0` to test this process.

The coordinator accepts tag `create` and tag-filtered `push` events.
It validates the complete supported version format and excludes administrative tags.
Release publication does not start preparation.
Overlapping events for the same retained identity become no-ops.
A permitted tag move repeats preparation and invalidates older attempts.
After any package upload or production approval, changed source requires a new version.

For a recorded candidate, use the generated recovery command.
For example, a retained `v1.2.3rc1` candidate produces:

```bash
gh workflow run release-preparation.yml --repo AxelVoitier/zensical-tarn --ref v1.2.3rc1 -f mode=resume
```

The example selects the original tag as the workflow ref.
Do not execute it until setup and remote tests are authorised.
Resume retrieves and verifies originals and history without building archives or regenerating build evidence.
It does not depend on ordinary reruns or temporary Actions artifacts.
Future PyPI uploads on resume still require fresh production approval.
Approval and publication jobs belong to the later implementation stages.

Recovery does not depend on the final reporting job.
If cancellation interrupts the history append, resume can reconcile a complete verified storage copy.
An incomplete copy stops recovery without replacement builds.
If no originals ever existed, inspect the retained history and both indexes first.
Under pre-upload rules, a deliberate full preparation uses the original ref and `-f mode=prepare`.
Lost originals or required evidence must not be replaced for an existing candidate.

All coordinator runs share one fixed queue through completion and future approval waits.
The configuration uses `cancel-in-progress: false` and `queue: max`.
GitHub documents a limit of 100 pending runs per group.
If a request exceeds the limit, inspect current state before starting a deliberate new request.
Queue order is not guaranteed.
The coordinator rechecks source, tag, history and destinations before advancing.
Manual or API changes outside the queue can stop an attempt.
Hosted queue scheduling and approval-wait behaviour remain pending remote proof.
See [GitHub concurrency controls](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency).

The activation switch `TARN_RELEASE_PREPARATION_ENABLED` defaults to disabled.
Its retained storage configuration needs separately authorised setup.
The coordinator now connects verified builder outputs to product-draft storage and verified read-back.
That wiring remains unproven on GitHub until the authorised hosted tests.
The isolated resume path can consume recovery copies already retained by the storage helper.
No current coordinator job uploads packages or publishes a GitHub release.
The dedicated `testpypi` publisher job has a hard disable and its CLI refuses hosted uploads.
Local controlled destinations exercise normal publication, partial recovery and retrieval.
The separate installation job consumes the retrieved candidate's exact wheel in a fresh environment.
Live registry transport, certificate identities and registry acceptance remain pending.
Changing an activation variable cannot enable the TestPyPI publisher.


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
`LICENSES/zensical-ui.MIT.txt`, checked against Zensical UI tag `v0.0.41`.
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

- Zensical is pinned to `0.0.74`; the copied partials are checked against that
  installed version. MkDocs itself is not a supported engine.
- Python 3.11 or newer is required. The configured CI matrix covers 3.11–3.15;
  local verification results are reported separately from CI configuration.
  Local checks on 3 November 2026 passed all 16 regression tests, installed-wheel
  documentation/example builds and configuration checks on Python 3.11.13,
  3.12.11, 3.13.5, 3.14.8 and 3.15.0 with Zensical 0.0.74 and UI 0.0.41.
  The isolated archive builds and browser checks used Python 3.14.8.
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

For the new coordinator, follow [Tagged start and recovery](#tagged-start-and-recovery).
Its reusable builder checks and reproduces the exact selected candidate.
The old `main` workflow plus tag-input route is removed.
Hosted activation and the publication path remain pending separate authorisation.

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
| Release preparation (`release-preparation.yml`) | Product-tag create/push after separate activation. | Select the original tag and `resume` or pre-upload `prepare`. |

Documentation-only changes run the docs build without the full Python matrix
or browser checks. Changes to administrative notes such as `HANDOFF.md`,
`PACKAGE_REVIEW.md`, and this guide do not start automatic runs. Manual and
reusable calls bypass the push path filters and run their complete workflow.

Ordinary checks cancel older runs on the same branch. Release preparation and recovery share a non-cancelling queue. Called
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
`pull_request_target`, or `workflow_run` triggers. Ordinary package and documentation pushes are limited
to `main`. The coordinator also accepts product-tag pushes after activation.
Building and testing a contribution executes its Python, build hooks, templates
and scripts, so a read-only token cannot guarantee that contributed code is
harmless. This follows the owner's preference to avoid automatic PR execution.

Review contributions before merging them into `main`. A manual run can select
another branch, so review that branch's code and workflow changes before
starting it. Release preparation requires the selected product tag as its workflow ref.
Review that tag's source and workflow together. The coordinator never creates a Git tag.

Package jobs use read permissions. Isolated coordinator jobs use `contents: write`
for private draft access and append-only history. Build attestation jobs request
`id-token: write` and `attestations: write`. They have no publisher environment. The documentation
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
