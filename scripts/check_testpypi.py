#!/usr/bin/env python3
# Copyright 2026 Axel Voitier
# ruff: noqa: EXE001, EM101, TRY003, S603
"""Install a verified retrieved candidate in a fresh environment and check its sites.

Run only in an unprivileged package job. Dependencies come from PyPI; the theme
itself is installed by its exact verified local wheel path, never by index name.
"""

import argparse
import os
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path

from release.candidate import archive_names, verify_candidate
from release.sdist import source_identity


def install(
    root: Path,
    candidate: Path,
    source: Mapping[str, object],
    manifest_digest: str,
    output: Path,
) -> None:
    """Verify before execution and keep the environment outside the source checkout."""
    verify_candidate(
        (candidate / 'candidate.json').read_bytes(),
        manifest_digest,
        source,
        candidate / 'files',
    )
    if output.exists():
        raise ValueError('Clean installation requires a fresh output directory')
    _, wheel = archive_names(source)
    environment = {
        key: value
        for key, value in os.environ.items()
        if key
        not in {
            'GH_TOKEN',
            'GITHUB_TOKEN',
            'ACTIONS_ID_TOKEN_REQUEST_TOKEN',
            'ACTIONS_ID_TOKEN_REQUEST_URL',
            'PYTHONPATH',
            'PYTHONHOME',
        }
    }
    subprocess.run([sys.executable, '-I', '-m', 'venv', str(output)], check=True, env=environment)
    python = output / 'bin/python'
    subprocess.run(
        [
            str(python),
            '-I',
            '-m',
            'pip',
            '--isolated',
            'install',
            '--no-cache-dir',
            str((candidate / 'files' / wheel).resolve()),
        ],
        check=True,
        env=environment,
    )
    for script in ('check_package.py', 'check_config.py'):
        subprocess.run(
            [str(python), str(root / 'scripts' / script)],
            check=True,
            env=environment,
            cwd=output,
        )


def main() -> None:
    """Use frozen source identity and a selected manifest digest from trusted retrieval."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--tag', required=True)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--manifest-digest', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    source = source_identity(args.root, args.tag, args.commit)
    install(
        args.root.resolve(),
        args.candidate.resolve(),
        source,
        args.manifest_digest,
        args.output.resolve(),
    )


if __name__ == '__main__':
    main()
