#!/usr/bin/env python3
# Copyright 2026 Axel Voitier
#
# spell-checker:ignore hardlinks
# Run with Python; status belongs on stdout and Git/build commands use fixed argv.
# ruff: noqa: EXE001, T201, S603, S607
# Keep short validation errors at their point of failure.
# ruff: noqa: EM101, EM102, TRY003
"""Build a tagged release twice, require matching bytes, and record its provenance.

No upload, Git tag, commit, push, or remote workflow is performed.
"""

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tomllib
from importlib import metadata
from pathlib import Path
from tempfile import TemporaryDirectory

from check_release import git, inspect_archives, release_blockers, source_version, verify_tag

ROOT = Path(__file__).resolve().parent.parent


def artifact_hashes(directory: Path) -> dict[str, str]:
    """Hash exactly one wheel and one source archive."""
    wheels = list(directory.glob('*.whl'))
    sources = list(directory.glob('*.tar.gz'))
    if len(wheels) != 1 or len(sources) != 1:
        raise ValueError('Expected exactly one wheel and one source archive')
    return {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in wheels + sources}


def check_toolchain(root: Path) -> dict[str, str]:
    """Require the pinned build tools and reject version override variables."""
    overrides = [name for name in os.environ if name.startswith(('SETUPTOOLS_SCM_', 'HATCH_VCS_'))]
    if overrides:
        raise ValueError(f'Release version overrides are not allowed: {sorted(overrides)}')
    config = tomllib.loads((root / 'pyproject.toml').read_text(encoding='utf-8'))
    tools: dict[str, str] = {}
    for requirement in config['dependency-groups']['release']:
        name, expected = requirement.split('==')
        actual = metadata.version(name)
        if actual != expected:
            raise ValueError(f'Release tool {name}: expected {expected}, found {actual}')
        tools[name] = actual
    if not set(config['build-system']['requires']) <= set(config['dependency-groups']['release']):
        raise ValueError('The release toolchain must include all pinned build requirements')
    return tools


def build_once(root: Path, tag: str, directory: Path, epoch: str) -> Path:
    """Build the sdist and its wheel from a fresh clone of the exact tag."""
    directory.mkdir()
    source = directory / 'source'
    output = directory / 'dist'
    subprocess.run(
        ['git', 'clone', '--quiet', '--no-hardlinks', '--no-checkout', str(root), str(source)],
        check=True,
    )
    git(source, 'checkout', '--quiet', '--detach', f'refs/tags/{tag}')
    environment = dict(os.environ, SOURCE_DATE_EPOCH=epoch, PYTHONHASHSEED='0', TZ='UTC')
    subprocess.run(
        [sys.executable, '-m', 'build', '--no-isolation', '--outdir', str(output)],
        cwd=source,
        env=environment,
        check=True,
    )
    subprocess.run(
        [sys.executable, '-m', 'twine', 'check', '--strict', *map(str, sorted(output.iterdir()))],
        check=True,
    )
    inspect_archives(source, output, tag)
    return output


def prepare(root: Path, tag: str, output: Path, tested: Path | None = None) -> dict[str, object]:
    """Copy release artifacts only after two independent builds agree."""
    tools = check_toolchain(root)
    provenance = verify_tag(root, tag, source_version(root))
    if release_blockers(root):
        raise ValueError('Resolve the release blockers before preparing artifacts')
    if output.exists():
        raise ValueError(f'Release output already exists: {output}; use a fresh directory')
    with TemporaryDirectory(prefix='tarn-reproduce-') as directory:
        work = Path(directory)
        first = build_once(root, tag, work / 'first', str(provenance['source_date_epoch']))
        second = build_once(root, tag, work / 'second', str(provenance['source_date_epoch']))
        hashes = artifact_hashes(first)
        if hashes != artifact_hashes(second):
            raise ValueError('Independent builds differ; release artifacts were not copied')
        if tested is not None and hashes != artifact_hashes(tested):
            raise ValueError('Reproduced archives differ from the CI-tested artifacts')
        # Detect changes to HEAD, the tag or source while the builds were running.
        if provenance != verify_tag(root, tag, source_version(root)):
            raise ValueError('Release source changed during preparation')
        report = inspect_archives(root, first, tag)
        report.update(
            {
                'reproducible': True,
                'builds_compared': 2,
                'ci_artifacts_compared': tested is not None,
                'build_python': sys.version,
                'platform': platform.platform(),
                'build_tools': tools,
                'publication_performed': False,
                'preflight_passed': True,
                'artifact_errors': [],
                'release_blockers': [],
                'git_version': git(root, '--version'),
            },
        )
        output.mkdir(parents=True)
        for name in hashes:
            shutil.copyfile(first / name, output / name)
        (output / 'release-report.json').write_text(
            json.dumps(report, indent=2) + '\n',
            encoding='utf-8',
        )
    return report


def main() -> int:
    """Prepare a named Git tag without uploading or altering the repository."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('tag', help='Existing release tag, for example v1.0.0')
    parser.add_argument('--output', type=Path, help='New output directory; defaults to dist/TAG')
    parser.add_argument('--tested-dist', type=Path, help='Also require these CI archives to match')
    args = parser.parse_args()
    try:
        prepare(ROOT, args.tag, args.output or ROOT / 'dist' / args.tag, args.tested_dist)
    except (
        ValueError,
        OSError,
        metadata.PackageNotFoundError,
        subprocess.CalledProcessError,
    ) as error:
        print(f'Release preparation failed: {error}', file=sys.stderr)
        return 1
    print(f'Reproducible release prepared from {args.tag}; no upload performed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
