# Tarn maintenance

For local development, use the existing pyenv virtual environment named `tarn`.
Run commands with `PYENV_VERSION=tarn pyenv exec <command>` so they use that
environment even when the shell has not activated it. See
[scripts/README.md](scripts/README.md) for validation commands.

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
