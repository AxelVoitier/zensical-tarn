# Tarn maintenance

Hatch is available through the existing pyenv environment named `tarn`.
Before installing tools or creating an environment, check the Hatch environments
in `pyproject.toml` for one that meets the task's needs. Run Hatch with
`PYENV_VERSION=tarn pyenv exec hatch <command>`, even when the shell has not
activated `tarn`. Use `typing:check` for strict typechecking, `check:all` for
regression and CSS checks, and `release` for the pinned release toolchain.
If none fits, add a dedicated Hatch environment for recurring needs or use a
temporary environment for a one-off check. See
[scripts/README.md](scripts/README.md) for validation commands and environment scope.
Keep machine-specific setup instructions in this file. Public documentation and
scripts must use portable commands, such as `hatch run typing:check`.
Local Ruff checks use `$HOME/.config/ruff/ruff.toml` with `--config`.

For a Zensical dependency update, read and follow
[UPGRADING_ZENSICAL.md](UPGRADING_ZENSICAL.md) before editing the pin. It covers
upstream templates and licences, installed-wheel checks, browser verification,
screenshots and final artifacts.

An engine update is local preparation. Publishing, deployment, tags, pushes and
remote workflow runs require separate user instructions. Preserve existing user
changes and keep ignored `ai-works/` planning documents private. The small public
`release-review.toml` file is required by tests and release checks.

For a package release, follow RELEASING.md and use
`hatch run release:prepare TAG`. The version comes from Git through hatch-vcs.
Do not hard-code it, override it through the environment, or promote archives
from an untagged checkout. Creating or moving real tags and uploading packages
remain separate maintainer decisions.

## Agent skills

### Issue tracker

Track issues and specs as local Markdown files under `ai-works/.scratch/<feature>/`.
Read `ai-works/docs/agents/issue-tracker.md` before creating or updating tickets.

### Triage labels

Use the five default triage roles.
Read `ai-works/docs/agents/triage-labels.md` when assigning triage status.

### Domain docs

Use a single-context layout.
Read `ai-works/docs/agents/domain.md` before exploring the codebase.
