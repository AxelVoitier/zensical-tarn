# Update Tarn to a new Zensical version

## Goal

Update the engine dependency, reconcile Tarn's copied templates, and verify the
installed package and rendered documentation. This procedure is for maintainers
and AI coding agents working on zensical-tarn. It assumes Bash on Linux or macOS.
Use equivalent paths and commands on another platform.

Treat an engine update as local preparation. It does not authorise publication
to PyPI or TestPyPI, a GitHub release, a tag, a push, a workflow dispatch, or a
documentation deployment. Those actions need a separate instruction.

## Prerequisites

- Work in the zensical-tarn checkout, not a neighbouring project.
- Read applicable `AGENTS.md` files and preserve existing user changes.
- Have a Python interpreter compatible with Tarn and the requested engine.
- Have network access for upstream packages, source, build dependencies,
  Chromium if needed, and Google Fonts during screenshot capture.
- Have enough temporary space for the test environment, packages and screenshots.

The confirmed baseline on 27 October 2026 is Zensical 0.0.73 with UI 0.0.39.
Tarn requires Python 3.11 or newer; CI covers Python 3.11–3.15. Read the current
files before relying on those values. The commands use 0.0.73 as an example,
not as the version to select for every future update.

## Steps

### 1. Record the checkout and the requested target

Run from the repository root:

~~~bash
pwd -P
git status --short
git diff --stat
git diff --cached --stat
~~~

Record staged and unstaged changes before editing. In an initial checkout,
many files can already be staged without any commit. Do not reset, unstage or
overwrite those files to obtain a clean baseline.

Use the version requested by the user. Do not substitute the latest release,
broaden the dependency range, or change Tarn's own version automatically.

Keep the following commands in one Bash session. Replace the example target:

~~~bash
TARN_TARGET_VERSION='0.0.73'
TARN_SOURCE_ROOT="$(pwd -P)"
TARN_UPGRADE_ROOT="$(mktemp -d /tmp/tarn-zensical-upgrade.XXXXXX)"
python3 --version
python3 -m venv "$TARN_UPGRADE_ROOT/venv"
TARN_PYTHON="$TARN_UPGRADE_ROOT/venv/bin/python"
export TARN_TARGET_VERSION TARN_SOURCE_ROOT TARN_UPGRADE_ROOT TARN_PYTHON
"$TARN_PYTHON" -m pip install build twine playwright
~~~

If `python3` is incompatible, select a suitable installed interpreter when
creating the environment. Do not change the system Python or another project's
environment. Temporary paths from an earlier AI run are not prerequisites.

Read the current pin and check that the public release decisions are present:

~~~bash
"$TARN_PYTHON" - <<'PY'
from pathlib import Path
import tomllib

project = tomllib.loads(Path("pyproject.toml").read_text())["project"]
pins = [item for item in project["dependencies"] if item.startswith("zensical==")]
assert len(pins) == 1, pins
print("Current engine pin:", pins[0])
print("Python requirement:", project["requires-python"])
review = tomllib.loads(Path("release-review.toml").read_text())["review"]
print("Release decisions:", review)
PY
~~~

`release-review.toml` is a small public file used by tests and release checks.
Private planning notes can live under ignored `ai-works/`, but that private
folder must not become a CI dependency. During the 0.0.73 update, moving the
flags file there broke a regression test. The owner authorised restoring the
public file while keeping the private copy unchanged. If a later checkout lacks
it, establish whether removal was intentional before restoring it. Never invent
approval flags or copy private assessment documents into the package.

### 2. Inspect the upstream release before installing it

Read the exact release and its tagged source:

- [Zensical releases](https://github.com/zensical/zensical/releases).
- [Zensical source](https://github.com/zensical/zensical).
- [Zensical UI source](https://github.com/zensical/ui).
- [Theme packaging documentation](https://zensical.org/docs/customization/#packaging-themes).

For target `X.Y.Z`, inspect the release at `/releases/tag/vX.Y.Z`.
Identify the bundled UI version separately; engine and UI version numbers
are different. Confirm it through the release notes or tagged build source.
Do not infer it from the previous mapping.

Review changes to templates, CSS classes, JavaScript components, navigation,
search, code/content tabs, Markdown rendering, plugins and asset handling.
Inspect the actual downloaded wheel as well as release notes. Current online
documentation can describe a later release than the target.

Download the compatible wheel into the fresh temporary directory:

~~~bash
"$TARN_PYTHON" -m pip download --only-binary=:all: --no-deps --dest "$TARN_UPGRADE_ROOT/upstream" "zensical==$TARN_TARGET_VERSION"
~~~

If no compatible wheel is available, inspect the supported Python versions and
platforms. Do not bypass `Requires-Python` or silently build an unreviewed
fallback. Report the constraint and choose an appropriate test interpreter or
assess a source build explicitly.

Inspect wheel metadata and compare the three copied partials without importing
the new engine:

~~~bash
"$TARN_PYTHON" - <<'PY'
from email.parser import BytesParser
from email.policy import default
from pathlib import Path
import difflib
import os
import sys
import zipfile

root = Path(os.environ["TARN_SOURCE_ROOT"])
wheels = list((Path(os.environ["TARN_UPGRADE_ROOT"]) / "upstream").glob("*.whl"))
assert len(wheels) == 1, wheels
sys.path.insert(0, str(root / "scripts"))
from check_upstream import upstream_form, without_header

changed = []
with zipfile.ZipFile(wheels[0]) as archive:
    metadata_paths = [name for name in archive.namelist()
                      if name.endswith(".dist-info/METADATA")]
    assert len(metadata_paths) == 1, metadata_paths
    metadata = BytesParser(policy=default).parsebytes(archive.read(metadata_paths[0]))
    assert metadata["Version"] == os.environ["TARN_TARGET_VERSION"]
    print("Requires-Python:", metadata["Requires-Python"])
    print("Requires-Dist:", metadata.get_all("Requires-Dist", []))
    for name in ("nav-item.html", "tabs-item.html", "copyright.html"):
        current = upstream_form(
            name, (root / "src/zensical_tarn/partials" / name).read_text()
        )
        target = without_header(
            archive.read("zensical/templates/partials/" + name).decode()
        )
        difference = "".join(difflib.unified_diff(
            current.splitlines(True), target.splitlines(True),
            fromfile="Tarn upstream form/" + name,
            tofile="Target Zensical/" + name,
        ))
        print(difference or name + ": unchanged")
        if difference:
            changed.append(name)
if changed:
    raise SystemExit("Review and rebase these overrides: " + ", ".join(changed))
PY
~~~

A non-zero result with a template diff is a review checkpoint. Follow the next
step, then repeat the comparison. A missing wheel path or changed template
layout also needs investigation; do not suppress the error.

If dependencies or the Python minimum changed, assess the consequences before
editing Tarn's compatibility claims. Keep the supported-version matrix aligned
with the real engine requirements and testing.

### 3. Reconcile templates and verify upstream licensing

Tarn copies these upstream partials:

| File | Tarn's additions to preserve |
| --- | --- |
| `partials/nav-item.html` | Import of `partials/tarn.html`, the `tarn_first` assignment, and navigation attributes on top-level entries |
| `partials/tabs-item.html` | Import of the helper and navigation attributes on tab entries |
| `partials/copyright.html` | Import of the helper and the optional Tarn credit |

Use `scripts/check_upstream.py` as the exact inventory of additions and their
expected occurrence counts. The shared classifier, badges and credit live in
`partials/tarn.html`; stylesheet loading and page blocks live in `tarn.html`
and `main.html`. Preserve those integrations.

If upstream changed a copied partial:

1. Start from that partial in the target wheel.
2. Reapply the smallest Tarn additions compatible with the new structure.
3. Preserve the provenance comment and upstream attribution.
4. Update `upstream_form()` only when Tarn's actual additions change.
5. Keep the negative regression checks that detect upstream drift and missing
   Tarn additions. Do not make the comparison ignore arbitrary differences.
6. Inspect CSS selectors and browser behaviour affected by the new DOM.

A patch release can still require a template rebase. Identical templates also
do not establish JavaScript or CSS compatibility.

Once the UI version is confirmed, set it explicitly:

~~~bash
TARN_UI_VERSION='0.0.39'
export TARN_UI_VERSION
~~~

Fetch and compare its licence before changing the attribution:

~~~bash
"$TARN_PYTHON" - <<'PY'
from pathlib import Path
from urllib.request import Request, urlopen
import os

tag = "v" + os.environ["TARN_UI_VERSION"]
url = "https://raw.githubusercontent.com/zensical/ui/" + tag + "/LICENSE"
request = Request(url, headers={"User-Agent": "Tarn-upstream-review"})
with urlopen(request, timeout=30) as response:
    target = response.read()
download = Path(os.environ["TARN_UPGRADE_ROOT"]) / "upstream-ui-LICENSE.txt"
download.write_bytes(target)
retained = Path("LICENSES/zensical-ui.MIT.txt").read_bytes()
print("Downloaded:", url)
print("Byte-identical to retained licence:", target == retained)
print("Review copy:", download)
PY
~~~

If the licence or copyright notice changed, review its redistribution conditions
and compatibility. Retain the full applicable text; do not silently relicense
third-party material. Update the licence filename and package licence expression
if the actual licensing requires it. The comparison script alone is not a legal
compatibility assessment.

Update template provenance to the tag actually inspected. Preserve historical
origin information if it differs from the version now checked. For 0.0.73,
all three partials and the retained MIT licence matched UI 0.0.39 without
functional changes.

### 4. Update the pin and all current compatibility references

Edit the exact `zensical==…` dependency in `pyproject.toml`. Keep a single
verified release unless broader support is separately requested and tested.

Review this file inventory:

| Location | Required review |
| --- | --- |
| `pyproject.toml` | Engine pin, Python minimum, classifiers and source-archive inclusions |
| `README.md` | Current engine support statement |
| `docs/reference/configuration.md` | Current pin and verified site-output limitation |
| `docs/contributing/index.md` | Contributor environment and engine version |
| `RELEASING.md` | Supported environment, UI attribution and accurate local test evidence |
| `CHANGELOG.md` | Current unreleased upgrade entry; do not invent a release date |
| `zensical.toml` | Version-specific comments and any configuration affected by the upgrade |
| `scripts/README.md` | Current engine/UI mapping and verification instructions |
| `scripts/check_package.py` | Version-specific limitation messages and assumptions about copied files |
| `screenshots/README.md` | Engine actually used for regenerated captures |
| Three copied partials | Checked upstream tag and corresponding engine |
| `NOTICE` and its site copy | Correct upstream attribution and licence source |
| `LICENSES/zensical-ui.MIT.txt` and its site copy | Full applicable upstream licence |
| This procedure | New pitfalls or changed steps; retain dated upgrade examples as history |

Search for the former engine version and UI tag with `rg`. Review each result
rather than replacing every occurrence. For example:

~~~bash
rg -n --hidden -g '!.git/**' -g '!ai-works/**' -g '!site/**' -g '!site-*/**' -g '!dist/**' -g '!browser-artifacts/**' -g '!examples/minimal-site/site/**' '0[.]0[.]72|v0[.]0[.]38' .
~~~

Replace the example search values with the versions being upgraded. Old source
links can remain valid historical evidence. In `scripts/README.md`, the original
site-file investigation links to 0.0.72 source, while its current verification
statement names 0.0.73. Do not rewrite a historical claim as a new test result.

Synchronise changed licence/notice copies used by generated sites:

~~~bash
"$TARN_PYTHON" - <<'PY'
from pathlib import Path
import shutil

destination = Path("src/zensical_tarn/assets/licenses/tarn")
for source, name in (
    ("LICENSE", "LICENSE.txt"),
    ("NOTICE", "NOTICE.txt"),
    ("LICENSES/zensical-ui.MIT.txt", "zensical-ui.MIT.txt"),
):
    shutil.copyfile(source, destination / name)
PY
~~~

Adjust this mapping if a reviewed licence filename changes. The release checker
also names the upstream licence explicitly, so review it in that case.

Do not change unrelated choices during an engine update. Current decisions are:

- Tarn's package features are only `navigation.tabs` and `navigation.indexes`.
- Tarn's own site explicitly adds its convenience features and starts light.
  The package still follows the system colour preference.
- The own-site tutorial uses linked OS tabs. It does not use code annotations.
- Fonts come from Google Fonts, with documented self-hosting.
- Original Tarn material is Apache 2.0; copied MIT material retains its notices.
- GitHub workflows have no PR triggers or package publication steps. The
  documentation workflow deploys the main site to GitHub Pages from `main`.

An upstream release adding a feature does not justify enabling it in Tarn.

### 5. Build and install the candidate that users would receive

Build both formats in a fresh directory:

~~~bash
TARN_INITIAL_DIST="$TARN_UPGRADE_ROOT/dist-initial"
"$TARN_PYTHON" -m build --outdir "$TARN_INITIAL_DIST"
"$TARN_PYTHON" -m twine check --strict "$TARN_INITIAL_DIST"/*
"$TARN_PYTHON" -m pip install "$TARN_UPGRADE_ROOT/upstream/"*.whl "$TARN_INITIAL_DIST/"*.whl
"$TARN_PYTHON" -m pip check
"$TARN_PYTHON" --version
"$TARN_PYTHON" -m pip show zensical zensical-tarn
~~~

By default, [build](https://build.pypa.io/en/stable/) creates a source archive
and builds the wheel from that archive. Do not replace this with a wheel-only
build for final verification. Do not mix distributions from different attempts.

Use build isolation by default. `--no-isolation` is an alternative only when the
selected environment already satisfies `[build-system].requires`; record that
choice. Do not use it to hide missing or incompatible build requirements.

Verify that the installation is the reviewed engine and a normal Tarn wheel:

~~~bash
"$TARN_PYTHON" - <<'PY'
from importlib import metadata
from pathlib import Path
import os
import zensical
import zensical_tarn

assert metadata.version("zensical") == os.environ["TARN_TARGET_VERSION"]
root = Path(os.environ["TARN_SOURCE_ROOT"]).resolve()
theme = Path(zensical_tarn.__file__).resolve().parent
assert not theme.is_relative_to(root), theme
print("Engine:", zensical.__file__)
print("Installed theme:", theme)
PY
~~~

An editable installation is useful for development but does not prove which
resources ship in a wheel. After changing runtime files again, build a fresh
candidate and reinstall it before repeating affected checks.

### 6. Run package, template and configuration checks

~~~bash
"$TARN_PYTHON" scripts/build_css.py --check
"$TARN_PYTHON" -m unittest discover -s tests -v
"$TARN_PYTHON" scripts/check_upstream.py
"$TARN_PYTHON" scripts/check_package.py
"$TARN_PYTHON" scripts/check_config.py
~~~

These checks cover different failure modes:

| Check | Evidence |
| --- | --- |
| CSS check | Contrast checks and equality with the generated stylesheet |
| Regression tests | Check failures are detected, including template drift, missing notices and mismatched tags |
| Upstream comparison | Copied templates differ only by the maintained Tarn additions |
| Package check | Installed-wheel theme discovery, real docs/example builds, assets, notices and generated-site files |
| Configuration check | Classifications, badges, switches, URL forms, palette/font overrides and custom templates |

Do not edit generated CSS directly. If an upstream DOM change requires a style
change, edit the generator, regenerate, then check the result. A version-string
edit alone normally does not require CSS regeneration.

At the 0.0.73 baseline, the tests report six regression cases. Use the current
suite's count in the final report rather than treating six as a permanent target.

#### Assess theme-file copying instead of assuming it disappeared

Zensical 0.0.73 still copies `__init__.py`, Python bytecode and
`mkdocs_theme.yml` from the theme directory into an ordinary generated site.
The minimal example deliberately reproduces this. The main documentation and a
second example build use this project-level workaround:

~~~toml
[project.plugins.exclude]
glob = ["__init__.py", "__pycache__/*", "mkdocs_theme.yml"]
~~~

`check_package.py` permits only those exact known paths in the plain example.
It requires clean output for the other two builds and verifies licence assets.
This is a documented upstream limitation, not an unrestricted clean-output pass.

If a later release fixes copying, reproduce the new behaviour before updating
the checker, documentation and exclusions. Do not broaden the allowlist to
silence new leaks. Do not remove the workaround while the engine still needs it.
Theme defaults merge into `project.theme` and cannot set this project-level
plugin configuration.

### 7. Check browser behaviour on the new UI

Choose either a Playwright-managed Chromium or an existing executable.
[Playwright browser versions](https://playwright.dev/python/docs/browsers) are
coupled to the installed Playwright package.

~~~bash
TARN_BROWSER_ARGS=()
if [[ -n "${TARN_CHROMIUM:-}" ]]; then
  TARN_BROWSER_ARGS=(--executable "$TARN_CHROMIUM")
else
  export PLAYWRIGHT_BROWSERS_PATH="$TARN_UPGRADE_ROOT/playwright-browsers"
  "$TARN_PYTHON" -m playwright install chromium
fi
"$TARN_PYTHON" scripts/check_browser.py "${TARN_BROWSER_ARGS[@]}" --artifacts "$TARN_UPGRADE_ROOT/browser-artifacts"
~~~

Set `TARN_CHROMIUM` to a real executable before this block if using an existing
browser. Do not copy an old AI run's cache path or revision number blindly.
On a prepared CI runner, `playwright install --with-deps chromium` can also
install OS dependencies. Do not run system package installation unnecessarily.

The browser script starts a local HTTP server. If the sandbox blocks sockets
or browser launch, use the environment's permission mechanism for that local
check. Do not silently omit the check or disable browser security features.

The current suite covers 22 cases across tabbed, sidebar and classic layouts,
light/dark modes, viewport sizes and configuration overrides. It exercises
drawers, focus, search, content tabs and overflow. It blocks external requests,
so it does not verify downloaded Google Fonts or perform pixel comparisons.
Keep Linux/Chromium coverage; other OS/browser matrices are not required here.

Also inspect the actual documentation when a relevant upstream component changes.
In particular, verify that choosing Windows or macOS/Linux in the first-site
tutorial selects that OS in both tab groups. Test copy controls and the
back-to-top button on the own-site configuration, not by adding them back to
the package defaults. Test any changed upstream component the generic fixtures
do not cover.

### 8. Refresh the real-font screenshots and final site

~~~bash
"$TARN_PYTHON" scripts/capture_screenshots.py "${TARN_BROWSER_ARGS[@]}"
"$TARN_PYTHON" -m zensical build --strict --clean
~~~

Full capture refreshes the authored guide results, site pages, component crops
and images embedded in `docs/assets/screenshots/`. It needs Google Fonts access.
Do not report real-font screenshot success when the fonts failed to load.
`--guide-results` refreshes only guide examples and is not a substitute for a
full capture after an engine/UI upgrade.

The sidebar capture must replace `navigation.tabs` in the existing site feature
list with `navigation.sections`. It must retain the other site features and
write one valid TOML list. Do not inject a second `features` key under
`[project.theme]`. The current script parses the list and replaces it in place.

Inspect the resulting images for readable text, intact tabs/sidebar, correct
palettes and settled scroll positions. A successful screenshot command alone
does not prove the page looks correct.

Do not regenerate original logo artwork or restore private export assets.
The supplied logos were deliberately stripped of provider provenance metadata.
Raster screenshots flatten the visible page; they do not need the original
embedded SVG credentials. Keep private `ai-works/` files out of the site and
distribution.

The package check already builds the example in a temporary directory. If a
persistent example preview exists and needs refreshing, build from
`examples/minimal-site/` as well. This does not justify changing its defaults.

### 9. Check the supported Python versions

Read `.github/workflows/check.yml` and the classifiers in `pyproject.toml`.
At this baseline, the package matrix covers 3.11–3.15 and the browser job uses
3.12. Run the package checks on available supported interpreters in separate
environments. Repeat browser checks only when a distinct environment or failure
needs them.

At minimum, test a current supported interpreter. Test the minimum version when
the release changes Python requirements, dependencies or compatibility-sensitive
code. A configured CI matrix is not evidence that CI ran.

If CI/workflow files change, validate their syntax and local workflow calls
with `actionlint` when available. Preserve read-only permissions, pinned action
commits, disabled persisted credentials, path filters, cancellation groups, and
the absence of PR execution and publication. Do not dispatch CI without the
user's instruction.

Record exact local interpreter and installed dependency versions. Distinguish
local results, configured coverage, unavailable interpreters and remote runs.

### 10. Rebuild the final archives and run strict preflight

Screenshot changes must be in the source archive that is finally reviewed.
Build again in a different fresh directory:

~~~bash
TARN_FINAL_DIST="$TARN_UPGRADE_ROOT/dist-final"
"$TARN_PYTHON" -m build --outdir "$TARN_FINAL_DIST"
"$TARN_PYTHON" -m twine check --strict "$TARN_FINAL_DIST"/*
"$TARN_PYTHON" -m pip install --force-reinstall --no-deps "$TARN_FINAL_DIST/"*.whl
"$TARN_PYTHON" -m pip check
"$TARN_PYTHON" scripts/check_release.py --dist "$TARN_FINAL_DIST" --strict --report "$TARN_UPGRADE_ROOT/release-report.json"
~~~

`--no-deps` here retains the engine/dependencies already installed and checked.
If dependency requirements changed after the initial installation, resolve them
again instead. If runtime files changed after successful tests, repeat the
affected installed-wheel checks before calling the final candidate verified.

The final directory must contain exactly one wheel and one source archive.
The preflight compares metadata, dependencies, theme resources, licence files,
generated-site notice copies and README image paths with the source. It records
artifact sizes and SHA-256 hashes. `publication_performed` must remain false,
and strict preflight must report no artifact errors or release blockers.

A normal dependency update does not require a proposed release tag. If checking
one is useful, pass `--tag` with Tarn's current version, not the Zensical version.
Read Tarn's version from `src/zensical_tarn/__init__.py`; do not assume `0.1.0`
forever. The flag checks a string and creates no tag.

Inspect archive paths when packaging rules change. Confirm that maintainer
instructions and all referenced assets are included, licence copies match, and
private assessment files are excluded. A text mention of `ai-works/` inside this
guide is not the same as shipping that directory.

### 11. Review the diff and report the result

~~~bash
git diff --check
git diff --stat
git status --short
~~~

Inspect new untracked files as well as the diff. Do not stage, commit, push,
delete environments or remove prior artifacts unless requested. Keep evidence
until the user finishes reviewing it. If placing final packages in the checkout,
use an unambiguous ignored directory and state its path.

Report the following:

- Exact engine and UI versions, Python environments and dependency changes.
- Whether template bodies changed, and how any Tarn adaptations were tested.
- Licence comparison and attribution/notice updates.
- Package/configuration/browser results, screenshots and any manual checks.
- Final artifact/report paths, unresolved limitations and tests not run.
- Whether the public review file needed restoration.
- That no publication, deployment, tag, push or remote workflow occurred.

## Final Result

The requested engine is pinned in metadata and installed in the test environment.
Current compatibility statements name the verified release. Templates agree
with the inspected upstream UI apart from Tarn's deliberate additions. The
strict builds, applicable tests, screenshots and final archive checks pass.
Historical evidence and unrelated user changes remain intact.

Do not claim completion if an upgrade regression is unresolved. Report a
pre-existing failure separately rather than weakening tests or attributing it
to the new engine without evidence. If an update is incompatible, leave a
reviewable diagnosis and preserve user work.

## Troubleshoot failed steps

| Symptom | Action |
| --- | --- |
| Release page is unavailable | Check official package metadata and tagged source. Record the unavailable source; do not guess the UI mapping. |
| Wheel unavailable or Python rejected | Inspect the target's compatibility metadata and select a supported interpreter/platform. |
| Unit test cannot find `release-review.toml` | Check whether the public flags were moved into private notes; resolve its public status without publishing private documents. |
| Upstream comparison fails | Review and rebase the partial; preserve exact Tarn additions and drift detection. |
| Checks import source from the checkout | Replace the editable install with the built wheel and verify its path. |
| Known package files appear in plain output | Verify the existing limitation and exclusion builds. New paths are not automatically permitted. |
| Browser launch/socket fails | Use the environment's normal permission mechanism or a compatible existing Chromium; report any remaining block. |
| Sidebar screenshot build reports duplicate keys | Replace the existing feature list instead of inserting another one. |
| Font download fails | Retry the capture when the configured fonts can load; do not substitute fallback-font images silently. |
| Strict preflight reports stale resource/licence bytes | Synchronise reviewed source copies, rebuild and reinstall the candidate, then repeat affected checks. |
| Only README/preview images changed | Rebuild the source archive before generating the final hashes. |

## Next Steps

Use [the script guide](scripts/README.md) for individual checker details and
[release preparation](RELEASING.md) for package decisions and workflow behaviour.
A later publishing request is a separate task.

