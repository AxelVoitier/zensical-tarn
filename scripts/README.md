# Package checks

For an engine dependency update, follow the complete
[Zensical upgrade procedure](../UPGRADING_ZENSICAL.md). The commands below
describe individual checks rather than the full upgrade sequence.

Use Python 3.11 or newer in a virtual environment. From the repository root:

```bash
python -m pip install "pip>=25.1"
python -m pip install --group release
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
The tagged release coordinator calls the reusable builder and its selected-file checks.
It remains disabled pending separately authorised setup and hosted proof. The documentation workflow deploys the main
site to GitHub Pages. See the [release guide](../RELEASING.md) for package checks
and the separate, manual TestPyPI and PyPI upload steps.
Its workflow file is `.github/workflows/release-preparation.yml`. It checks out
an existing Git tag, checks that exact source across the matrix, and requires
two independent release builds to match the tested archives byte for byte.
Review a
branch's code and workflows before manually running checks on it; builds and
tests execute that code. See the guide's security section for repository settings
that need separate configuration on GitHub.

`python scripts/check_release.py --report release-report.json` checks local
archives and reports unresolved release decisions. Add `--strict` to fail on
those decisions and placeholder URLs as well as artifact errors. `--tag v1.0.0`
requires that existing tag at a clean HEAD, checks its version and records the
commit and tree. It never creates a tag or uploads a package.

Use `hatch run release:prepare v1.0.0` for the complete release preparation. The
detached Python 3.12 environment uses the pinned `release` dependency group.
The script requires a clean, complete Git checkout at the tag, builds from two
independent clones, and compares both archive hashes. It records the toolchain,
Python version, source commit, tree, timestamp and hashes in
`dist/v1.0.0/release-report.json`. Existing output directories are refused.
`--tested-dist` additionally compares the artifacts from the CI matrix.

## Shared preparation stages

`scripts/prepare_release.py` exposes the stages used by the local command.
Hosted builders can call the same Python functions from a frozen helper revision.
Add the checkout's `scripts/` directory to the Python import path first.
Use `Path` objects for paths and fresh output directories with existing parents.

| Function | Inputs | Output |
| --- | --- | --- |
| `validate_source(root, tag)` | Complete, clean checkout at the release tag; installed pinned tools | Tool versions and verified tag, commit, tree and source timestamp |
| `build_sdist(root, tag, directory)` | The same checkout and tag; new work directory | Path to the sole sdist in `directory/dist/`; independent clone in `directory/source/` |
| `build_wheel(root, sdist, expected_sha256, output, epoch)` | Toolchain configuration from the frozen checkout; selected sdist path and SHA-256 digest; new output directory; frozen source timestamp as a string | Path to the sole wheel in `output/` |
| `compare_archives(selected, reproduced)` | Two directories, each with exactly one wheel and one sdist | Mapping of filenames to SHA-256 digests; raises `ValueError` on different names or bytes |

`build_sdist` validates the toolchain, release decisions and tagged source.
It checks source identity before and after construction and derives the timestamp from the source commit.
`build_wheel` checks the selected digest before extraction and uses a private copy of those bytes.
It checks the pinned toolchain and builds from that extraction outside Git.
Its `root` supplies toolchain configuration only, not package sources.
Both build stages set `SOURCE_DATE_EPOCH`, `PYTHONHASHSEED=0` and `TZ=UTC`.

The caller must supply the wheel stage's digest and timestamp from trusted orchestration.
An archive or build report cannot authorise its own identity.
These function results are local build outputs, not signed evidence.
Later hosted jobs must independently select and hash transferred files and bind them to the frozen source and builder.

The local `prepare` function composes both build stages twice in separate temporary directories.
Each build runs strict Twine checks and archive inspection.
It compares both archive pairs and any selected `--tested-dist` pair before copying files or writing the existing report.
Source identity is checked again before the final copy.
`compare_archives` reads archive bytes without extracting or executing them.
It does not run installation, browser or matrix checks.

Run source validation, builds, archive inspection and package tests only in jobs without signing, publishing or release-write authority.
Source validation asks Hatch for the version, which can execute package-controlled build code.
Signing and publishing jobs must use separate reviewed helpers under `scripts/release/` from the frozen workflow revision.
They must treat archives and build reports as data and must not call these package-executing stages.
Keep their environments and caches separate from build jobs, with checkout credentials unpersisted.
Hosted permission and transfer enforcement require separate workflow implementation and verification.

The main preview commands are `hatch run doc:serve`, `hatch run doc:example`,
and `hatch run doc:build`. Use `hatch run check:all` for the CSS and regression
checks. The detached check environment needs no third-party Python packages;
the tag tests require Git on PATH. `hatch run release:check --dist dist/v1.0.0 --tag v1.0.0`
rechecks existing tagged archives without building or uploading them.

## Standalone source archives

The source archive supports wheel builds, CSS regeneration and the regression
suite outside a Git checkout. Its compressed size must be at most 1 MiB
(1,048,576 bytes). It contains the theme, generated CSS, token source, scripts,
tests, licences and metadata. Three small documentation pages remain as test
inputs. Full documentation, examples, screenshots and design exports are
available from the repository.

Extract the archive into a new directory, then run these commands there:

```bash
python -m build --wheel
python scripts/build_css.py
python scripts/build_css.py --check
python -m unittest discover -s tests -v
```

Install `build` in your Python environment first. It installs the declared
backend requirements in an isolated build environment. The archive's generated
`PKG-INFO` retains the tag-derived version; no version override or Git checkout
is needed. The regression suite uses the standard library and needs Git on PATH
for tests that create temporary repositories. Missing test inputs fail the suite.

Full-site, browser and official tagged release preparation checks require the
repository. `check_release.py` checks README images against the frozen checkout
without HTTP requests or requiring images in the source archive. It also rejects
oversized source archives, excluded content and missing or changed source inputs.
Its report records archive hashes, byte counts and the complete source member list.

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
to select an existing Chromium installation. Rebuild the documentation afterwards to include the refreshed images. Logo exports are maintained separately from the documentation screenshots.

## Upstream template overrides

`check_upstream.py` compares the installed Tarn navigation and copyright
overrides with the templates located by `zensical_ui.get_theme_dir()`. It removes only the leading
file comments and Tarn's documented additions. Missing additions and any other
differences fail with a diff. It needs no network access.

Tarn pins Zensical to 0.0.74, which depends on `zensical-ui==0.0.41`.
The templates and browser assets ship in that separate UI package. To support another Zensical release, review its templates,
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

Zensical 0.0.74 copies theme files into generated sites, including
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
installed-wheel checks with Zensical 0.0.74:

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

Use the `typing` Hatch environment for strict typechecking across scripts,
tests and package sources. It uses Python 3.12 with pinned Pyright and Playwright
versions and installs the project and its declared Zensical dependency.
Hatch stores it outside the checkout in its normal environment directory.
Pyright discovers dependencies from the active Hatch environment.
`pyrightconfig.json` still checks compatibility with the minimum supported
Python version, 3.11.

With Hatch installed, run these commands from the repository root:

```bash
hatch run typing:check
hatch run check:all
```

To check specific files, append their paths to `typing:check`.
Hatch creates the environment and installs its dependencies on first use.
The `check` environment runs the standard-library regression suite and CSS checks.
The detached `release` environment supplies the pinned build toolchain for
`release:prepare` and `release:check`. Reuse that environment for release-stage
commands, for example `hatch run release:python -m twine --version`.
The `doc` environment supplies Zensical for documentation builds and previews.

The typing environment uses an editable project installation for import resolution.
Package and browser validation still require a built wheel installed outside the checkout.

For Ruff, replace `/path/to/ruff.toml` below with the location of your maintenance configuration:

```bash
python -m pip install ruff
ruff format --config /path/to/ruff.toml --target-version py311 scripts tests src
ruff check --config /path/to/ruff.toml --target-version py311 --extend-ignore COM812 scripts tests src
```

`COM812` is excluded because it conflicts with Ruff's formatter. The source files
explain their other lint exceptions. These preserve existing control flow,
inline validation messages, command-line output, literal CSS and fixture data,
and unittest assertions. The two HTTP handlers retain their original positional
no-op overrides, with a specific Pyright exception for the inherited keyword
signature. Do not use automatic fixes that extract functions, replace loops or
lambdas, or change the test framework as part of a formatting pass.

## Isolated source archive evidence

The reusable `.github/workflows/release-build.yml` contains the source archive
build and its separate signing job. The coordinator calls it only for newly admitted preparation.
The [versioned build type](release/sdist-build-v1.md) describes its inputs,
protected evidence fields and verification policy.

The unprivileged command calls the existing `prepare_release.build_sdist`:

```bash
hatch run release:python -I scripts/release/build_sdist.py TAG COMMIT NEW_WORK_DIRECTORY --tag-ref-target OID --tag-ref-type TYPE
```

`TAG` is an existing canonical product tag. `COMMIT` is its full peeled commit SHA.
Freeze the tag ref target `OID` and its `TYPE` (`tag` or `commit`) before building.
The reusable workflow requires these values from trusted caller resolution.
Both build and signing jobs independently compare them with Git metadata.
Use a clean, complete checkout at that commit and a fresh directory outside it.
The command creates `NEW_WORK_DIRECTORY/dist/zensical_tarn-VERSION.tar.gz`.
It does not sign or upload anything.

The trusted helper can inspect source metadata without running the backend:

```bash
python -I scripts/release/sdist.py identity --root . --tag TAG --commit COMMIT
```

Its `predicate` and `verify` stages require the tagged coordinator's platform
context, the frozen tag target/type, producer artifact ID and a fresh output
directory outside the checkout. Supply the frozen tag through `--tag-ref-target`
and `--tag-ref-type`. A changed annotated tag object is rejected even if its
peeled commit stays the same.
They read the platform artifact API and download the identified archive.
The `verify` stage additionally requires the original signed bundle.
They execute fixed Git/GitHub CLI queries and handle package content as data.
These stages do not install tools or run package hooks.
They must run only from a reviewed frozen helper revision, with the workflow's
pinned runtimes and separate fresh-job boundary.
A supplied commit is an expected identity, not permission to trust arbitrary code.

Run the local regression seam with:

```bash
hatch run check:python -m unittest discover -s tests -p test_signed_sdist.py -v
hatch run typing:check scripts/release tests/test_signed_sdist.py
```

The local signature fixture needs OpenSSL. That test is skipped if OpenSSL is
absent. It substitutes the external verifier with local signature verification.
Actual GitHub certificate verification and hosted isolation remain unrun until
separate remote proof. No SLSA level is claimed by these local checks.

## Selected release candidate

The reusable builder now includes wheel construction, wheel signing, selected-file
checks and independent reproduction. The coordinator calls this builder only on the preparation path.
The [wheel build profile](release/wheel-build-v1.md) describes the controlled input
and signing boundary. Hosted execution requires separate authorisation.

`release/control.py` provides fixed stages for trusted workflow roles:

- `input` retrieves and verifies the exact original signed sdist before wheel construction.
- `predicate` independently selects both files and describes the wheel's exact sdist input.
- `verify-wheel` checks the original wheel bundle against those selected files and identities.
- `freeze` verifies both original bundles and creates the canonical candidate selection.
- `verify-candidate` checks the manifest, original files, signatures and signed input relationship.

The transfer stages require the tagged platform context and artifact IDs from the
workflow dependency graph. They accept no build command or caller predicate.
`build_wheel.py` runs separately in the unprivileged wheel job.
It calls the same `prepare_release.build_wheel` function as local preparation.

A frozen selection contains `candidate.json` and a `files/` directory.
That directory contains exactly the expected sdist, wheel and two original signed bundles.
The `tarn-candidate-v1` manifest uses UTF-8 JSON, sorted keys, compact separators
and one trailing newline. Its SHA-256 identifies the candidate.
It records frozen source identities, archive filenames/sizes/digests, original
build-evidence artifact IDs/filenames/digests and both archive transport identities.
It also records the exact sdist digest as `wheel_input_sha256`.
The builder returns the manifest digest separately through trusted job outputs.

Changing observations, test logs and reproduction reports remain outside the manifest.
Freezing a selection does not mark it as tested.
The builder exposes its candidate outputs only after shared checks and reproduction pass.
The shared release path checks and installs selected files across Python 3.11–3.15.
The browser job installs that same wheel.
Frozen-checkout checks keep their separate purpose and do not substitute a new wheel.

For local policy regression checks, run:

```bash
hatch run check:python -m unittest discover -s tests -p test_candidate.py -v
hatch run typing:check scripts/release tests/test_candidate.py
```

The signature fixtures require OpenSSL and use local keys at the external verifier boundary.
They do not prove hosted certificates, permissions or platform isolation.
For independent reproduction against an existing selected pair, run:

```bash
hatch run release:prepare TAG --tested-dist SELECTED_FILES --output NEW_OUTPUT
```

Use a clean checkout of the existing `TAG` and the pinned release environment.
`SELECTED_FILES` must contain the original wheel and sdist.
This command builds twice independently and rejects any byte difference from the selected pair.
It leaves original selected files and signed evidence untouched.

## Recovery storage and operational history

`release/storage.py` retains original candidate files and private operational events.
`release/storage_api.py` supplies the authenticated GitHub API transport.
The coordinator CLI uses these helpers for admission history, retention and resume.
Hosted product-draft creation and automatic retention remain later publication work.
Use them only from reviewed, frozen trusted code in the separate storage role.
They handle package files as data and do not execute package hooks.

Setup must retain the numeric repository ID and administrative release ID.
The shared administrative draft uses the `release-records` tag at an already-public commit.
Its fixed body is `Draft.body` with the `administrative` role.
Keep that draft unpublished, independently of every product draft.
The product draft uses its own retained release ID, canonical product tag,
frozen source commit and `product` role marker.
The helpers accept those identities explicitly and never choose a release by title.
Creating drafts and configuring permissions belong to later orchestration and authorised remote setup.
Missing administrative storage stops work. The helper never creates replacement administrative storage.

Construct `Storage(GitHubAPI(), administrative_draft)` with these retained identities.
The transport requires `GH_TOKEN` or `GITHUB_TOKEN` in the job environment.
It uses authenticated release and asset endpoints under the fixed Tarn repository.
It reads all release and asset pages, including pages after a short page.
It checks repository identity, release ID, role marker, tag, target commit and draft state.
It also resolves the actual tag ref, rather than trusting `target_commitish` alone.
No credential belongs in a Git ref, tag annotation, event, filename or command argument.

Call `Storage.retain(product, source, manifest, candidate, files, event)` before TestPyPI publication.
Supply the trusted source identity, original manifest bytes, separately retained candidate digest
and original candidate `files/` directory from the preceding verification stage.
The event must identify that candidate and source with kind `recovery-stored` and empty details.
Retention checks the original signatures and exact source-to-wheel relationship before uploading.
It stores only `candidate.json`, the two archives and their two original signed bundles.
It downloads them by asset ID, checks their identities and bytes, and repeats candidate verification.
It then appends an administrative event containing all recovery locations and asset identities.
Only successful read-back of both files and that event permits the caller to advance.
The returned `RecoveryCopy` contains the same retained identities.
Call `Storage.recover(copy, source, fresh_output)` to retrieve those originals without rebuilding.

`Storage.append(event)` writes one canonical `tarn-event-v1` JSON asset per transition.
Each event identifies its version, candidate digest, source commit, run, attempt, sequence,
event kind and preceding event digest. Its details contain screened operational data.
Before a candidate exists, its digest is `None`. Record the need for full preparation
if a failure occurs before recoverable originals exist.
Do not store credentials or raw logs in event details.
Each filename contains separate hashes of the logical identity and complete contents.
Conflicting sequences or predecessors stop advancement across every version in the shared store.
`Storage.history(version, expected_head)` verifies every event and returns the selected version in chain order.
Retain the returned head digest outside the draft when detecting later history deletion is required.
A mutable store cannot independently prove that its entire history was not removed.

An uncertain upload triggers a fresh authenticated read before any retry.
An already-stored match is reused only after byte verification.
If acceptance remains uncertain, the operation stops. A later explicit call checks again.
Interrupted retention keeps partial files and can reuse them on retry.
There is no overwrite, cleanup, delete, publish or Git-ref mutation operation.
Keep incomplete copies indefinitely and published originals for the life of the release.
Deleting an abandoned product draft requires a maintainer decision and preserves the independent history.
Read access to drafts is intentional here. Final public-release handling belongs to later finalisation work.

The caller must serialise state-changing runs through the shared release queue.
Draft assets supply no transactional lock or independent immutable archive.
Local scenarios cover read-back, pagination, cancellation, conflicts and separation of the two stores:

```bash
hatch run check:python -m unittest discover -s tests -p test_storage.py -v
hatch run typing:check scripts/release tests/test_storage.py
```

The signature-verifier response fixture exercises candidate policy, not hosted certificate validity.
Actual token permissions, authenticated draft reads and exclusion of ordinary readers remain pending remote checks.
The transport follows the [release API](https://docs.github.com/en/rest/releases/releases),
[asset API](https://docs.github.com/en/rest/releases/assets) and
[GitHub CLI API interface](https://cli.github.com/manual/gh_api).


## Tagged coordinator

`scripts/release/coordinator.py` runs only trusted control and verification code.
It does not import or execute package code.
The CLI reads platform event and workflow identity from the `GITHUB_*` environment.
It requires the original product tag as `GITHUB_REF` and the matching workflow revision.
It rechecks the actual remote tag, retained history and both package indexes.

The `admit` stage appends one admission to the administrative draft.
It deduplicates automatic events for the same frozen identity.
It writes a local receipt and exposes only action, history digest and tag identity as job outputs.
Private event contents stay in administrative storage.
Later jobs pass `--head DIGEST` to reconstruct the admission from durable history.
They do not depend on a temporary receipt artifact.

The `guard` stage rejects changed source, history, destinations or execution identity.
The `recover` stage accepts only a resume admission and a fresh `--output` directory.
It retrieves and verifies the original manifest, archives and signed build evidence.
The `retain` stage requires preparation and `--candidate-dir`.
Supply the builder output as `--candidate-digest` and the retained draft ID as `--product-id`.
Both archive transports must identify the admitted producer run and attempt.
Its caller must supply the already-created, correctly identified product draft.
It verifies originals and records `retention-started` before writing product assets.
That event retains the builder digest and product ID across cancellation.
It uses the storage helper before appending `recovery-stored`.
Cancellation recovery requires that retained selection before accepting an unrecorded storage copy.
The `report` stage attempts to record an outcome and prints the original-tag command.
It never marks publication complete.

All stages require `--root`, `--admin-id`, `--admin-target` and `--repository-id`.
The numeric repository identity must match the platform context.
The administrative draft must already exist with its retained ID and private role.
Missing or changed administrative history stops work.
There is no automatic replacement of administrative storage.

The workflow reads `TARN_RELEASE_RECORD_ID`, `TARN_RELEASE_RECORD_TARGET` and
`TARN_RELEASE_REPOSITORY_ID` from repository variables.
`TARN_RELEASE_PREPARATION_ENABLED` must equal `true` to admit hosted work.
These variables, draft setup and activation require separate authorisation.
The workflow contains no registry upload or release publication step.
Product-draft creation and automatic retention belong to the later publication path.

Run local service scenarios with external writes disabled:

```bash
hatch run check:python -m unittest discover -s tests -p test_coordinator.py -v
hatch run typing:check
```

The scenarios use real temporary Git repositories and external API response fixtures.
Signed-statement verification uses an external verifier response fixture.
It proves policy invocation and rejection behaviour, not a hosted certificate or SLSA level.
The workflow queue, actual events and original-tag dispatch still need hosted proof.
See [Tagged start and recovery](../RELEASING.md#tagged-start-and-recovery) for operating limits.
