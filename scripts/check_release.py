#!/usr/bin/env python3
# Copyright 2026 Axel Voitier
# Invoke with Python; report local release checks on stdout.
# ruff: noqa: EXE001, T201
# Keep archive validation in its existing function.
# ruff: noqa: C901, PLR0912, PLR0915
# Keep validation messages in the existing raise expressions.
# ruff: noqa: EM101, EM102, TRY003
# Retain the existing blocker-collection loop.
# ruff: noqa: PERF401

"""Inspect local release archives and report unresolved publication decisions.

This script performs no uploads, network requests, tagging, or release creation.
By default, unresolved decisions are reported separately from artifact errors.
--strict also fails when those decisions or publishing placeholders remain.
"""

import argparse
import configparser
import hashlib
import json
import re
import subprocess
import sys
import tarfile
import tomllib
import zipfile
from email.parser import BytesParser
from email.policy import default
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from typing import BinaryIO, cast
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parent.parent


def source_version(root: Path) -> str:
    """Ask the configured Hatch backend for the source version."""
    return subprocess.run(
        [sys.executable, '-m', 'hatchling', 'version'],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def git(root: Path, *arguments: str) -> str:
    """Run a Git query in the selected source checkout."""
    return subprocess.run(  # noqa: S603 - Git queries use argv without a shell
        ['git', '-C', str(root), *arguments],  # noqa: S607 - Git is required on PATH
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def verify_tag(root: Path, tag: str, version: str) -> dict[str, str | int]:
    """Require a complete, clean checkout at the exact version tag."""
    check_tag(version, tag)
    if tag != f'v{version}':
        raise ValueError('Release tags must use the vVERSION form')
    if git(root, 'rev-parse', '--is-shallow-repository') != 'false':
        raise ValueError('Release checks require full Git history and tags')
    commit = git(root, 'rev-parse', '--verify', f'refs/tags/{tag}^{{commit}}')
    if commit != git(root, 'rev-parse', 'HEAD'):
        raise ValueError(f'Tag {tag!r} does not point at the checked-out commit')
    if git(root, 'tag', '--points-at', 'HEAD', '--list', 'v[0-9]*').splitlines() != [tag]:
        raise ValueError('Each release needs its own commit with a single version tag')
    if git(root, 'status', '--porcelain', '--untracked-files=all'):
        raise ValueError('Release checks require a clean checkout, including untracked files')
    return {
        'tag': tag,
        'tag_object': git(root, 'rev-parse', '--verify', f'refs/tags/{tag}'),
        'commit': commit,
        'tree': git(root, 'rev-parse', 'HEAD^{tree}'),
        'source_date_epoch': int(git(root, 'show', '-s', '--format=%ct', 'HEAD')),
    }


def check_tag(version: str, tag: str | None) -> None:
    """Reject a proposed tag that differs from the package version."""
    if tag is not None and tag not in {version, f'v{version}'}:
        raise ValueError(f'Tag {tag!r} does not match package version {version!r}')


def check_licences(
    expected: dict[str, bytes],
    wheel: dict[str, bytes],
    sdist: dict[str, bytes],
    info: str,
) -> None:
    """Check that both archives retain the expected licence files."""
    for path, data in expected.items():
        if wheel.get(f'{info}/licenses/{path}') != data:
            raise ValueError(f'Wheel licence file missing or changed: {path}')
        if sdist.get(path) != data:
            raise ValueError(f'Source archive licence file missing or changed: {path}')


class Images(HTMLParser):
    def __init__(self) -> None:
        """Initialise the parser and its collected page data."""
        super().__init__()
        self.sources: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Collect the relevant attributes from an opening HTML tag."""
        if tag == 'img' and (source := dict(attrs).get('src')):
            self.sources.append(source)


def readme_images(text: str) -> list[str]:
    """Collect image references from HTML and Markdown in the README."""
    parsed = Images()
    parsed.feed(text)
    return parsed.sources + re.findall(r'!\[[^\]]*\]\(([^\s)]+)\)', text)


def inspect_archives(root: Path, directory: Path, tag: str | None) -> dict[str, object]:
    """Validate local distribution contents and return their metadata."""
    project = tomllib.loads((root / 'pyproject.toml').read_text(encoding='utf-8'))['project']
    version = source_version(root)
    provenance = verify_tag(root, tag, version) if tag is not None else None
    wheels, sources = list(directory.glob('*.whl')), list(directory.glob('*.tar.gz'))
    if len(wheels) != 1 or len(sources) != 1:
        raise ValueError('Use a directory containing exactly one wheel and one source archive')
    with zipfile.ZipFile(wheels[0]) as archive:
        names = [name for name in archive.namelist() if not name.endswith('/')]
        if len(names) != len(set(names)):
            raise ValueError('Duplicate paths in wheel')
        wheel = {name: archive.read(name) for name in names}
    with tarfile.open(sources[0]) as archive:
        members = [member for member in archive.getmembers() if member.isfile()]
        prefixes = {PurePosixPath(member.name).parts[0] for member in members}
        if len(prefixes) != 1 or any(
            PurePosixPath(member.name).is_absolute() or '..' in PurePosixPath(member.name).parts
            for member in members
        ):
            raise ValueError('Invalid source archive paths')
        (prefix,) = prefixes
        sdist = {
            member.name.removeprefix(prefix + '/'): cast(
                'BinaryIO',
                archive.extractfile(member),
            ).read()
            for member in members
        }
        if len(sdist) != len(members):
            raise ValueError('Duplicate paths in source archive')
    metadata_paths = [name for name in wheel if name.endswith('.dist-info/METADATA')]
    if len(metadata_paths) != 1 or 'PKG-INFO' not in sdist:
        raise ValueError('Missing distribution metadata')
    info = metadata_paths[0].removesuffix('/METADATA')
    expected = {
        'Name': project['name'],
        'Version': version,
        'Requires-Python': project['requires-python'],
        'License-Expression': project['license'],
        'Description-Content-Type': 'text/markdown',
    }
    metadata = BytesParser(policy=default).parsebytes(wheel[metadata_paths[0]])
    for label, data in (('wheel', wheel[metadata_paths[0]]), ('sdist', sdist['PKG-INFO'])):
        parsed = BytesParser(policy=default).parsebytes(data)
        for key, value in expected.items():
            if parsed[key] != value:
                raise ValueError(f'{label} {key} mismatch: expected {value!r}, got {parsed[key]!r}')
        if sorted(parsed.get_all('Requires-Dist', [])) != sorted(project['dependencies']):
            raise ValueError(f'{label} dependencies differ from pyproject.toml')
        if parsed['Author'] != ', '.join(author['name'] for author in project['authors']):
            raise ValueError(f'{label} author differs from pyproject.toml')
        if sorted(parsed.get_all('Project-URL', [])) != sorted(
            f'{name}, {url}' for name, url in project['urls'].items()
        ):
            raise ValueError(f'{label} project URLs differ from pyproject.toml')
    entry_points = configparser.ConfigParser()
    entry_points.read_string(wheel[f'{info}/entry_points.txt'].decode())
    if dict(entry_points['mkdocs.themes']) != {'tarn': 'zensical_tarn'}:
        raise ValueError('Incorrect installed-theme entry point')
    for path in (root / 'src/zensical_tarn').rglob('*'):
        if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc':
            name = path.relative_to(root / 'src').as_posix()
            if (
                wheel.get(name) != path.read_bytes()
                or sdist.get(f'src/{name}') != path.read_bytes()
            ):
                raise ValueError(f'Theme resource missing or stale in an archive: {name}')
    if any('__pycache__' in name or name.endswith(('.pyc', '.pyo')) for name in wheel):
        raise ValueError('Bytecode cache in wheel')
    licences: dict[str, bytes] = {}
    for pattern in project['license-files']:
        matches = [path for path in root.glob(pattern) if path.is_file()]
        if not matches:
            raise ValueError(f'Licence file pattern has no matches: {pattern}')
        licences.update({path.relative_to(root).as_posix(): path.read_bytes() for path in matches})
    if 'LICENSES/zensical-ui.MIT.txt' not in licences:
        raise ValueError('Upstream template licence is not declared for distribution')
    check_licences(licences, wheel, sdist, info)
    for name, target in (
        ('LICENSE', 'LICENSE.txt'),
        ('NOTICE', 'NOTICE.txt'),
        ('LICENSES/zensical-ui.MIT.txt', 'zensical-ui.MIT.txt'),
    ):
        asset = f'zensical_tarn/assets/licenses/tarn/{target}'
        if wheel.get(asset) != licences[name] or sdist.get(f'src/{asset}') != licences[name]:
            raise ValueError(f'Generated-site licence copy missing or stale: {target}')
    for image in readme_images((root / 'README.md').read_text(encoding='utf-8')):
        url = urlsplit(image)
        if url.netloc == 'raw.githubusercontent.com':
            parts = unquote(url.path).strip('/').split('/')
            path = '/'.join(parts[3:])
        elif not url.scheme and not url.netloc:
            path = unquote(url.path)
        else:
            continue
        if not path or not (root / path).is_file() or path not in sdist:
            raise ValueError(f'README image missing from source archive: {path or image}')
    return {
        'git': provenance,
        'version': version,
        'tag': tag,
        'tag_object': git(root, 'rev-parse', '--verify', f'refs/tags/{tag}'),
        'licence_files': sorted(licences),
        'licence_expression': metadata['License-Expression'],
        'author': metadata['Author'],
        'project_urls': project['urls'],
        'python': metadata['Requires-Python'],
        'dependencies': metadata.get_all('Requires-Dist', []),
        'artifacts': [
            {
                'file': path.name,
                'bytes': path.stat().st_size,
                'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            }
            for path in (wheels[0], sources[0])
        ],
    }


def release_blockers(root: Path) -> list[str]:
    """List unconfirmed decisions and remaining publication placeholders."""
    blockers: list[str] = []
    review = tomllib.loads((root / 'release-review.toml').read_text(encoding='utf-8'))['review']
    for decision in ('licence', 'ownership', 'branding', 'fonts'):
        if review.get(decision) is not True:
            blockers.append(f'Unconfirmed decision: {decision}')
    for name in (
        'pyproject.toml',
        'README.md',
        'zensical.toml',
        'CHANGELOG.md',
        'docs/about/index.md',
        'docs/contributing/index.md',
        'design/README.md',
        'src/zensical_tarn/partials/tarn.html',
    ):
        for number, line in enumerate((root / name).read_text(encoding='utf-8').splitlines(), 1):
            if re.search(r'\b(?:OWNER|TODO)\b', line):
                blockers.append(f'Publishing placeholder: {name}:{number}')
    return blockers


def main() -> int:
    """Report local archive errors and unresolved release decisions."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dist', type=Path, default=ROOT / 'dist')
    parser.add_argument(
        '--tag',
        help='Require this existing version tag at a clean HEAD; never creates a tag',
    )
    parser.add_argument(
        '--strict',
        action='store_true',
        help='Also fail on unresolved decisions and placeholders',
    )
    parser.add_argument(
        '--require-tag',
        action='store_true',
        help='Require --tag for a release check',
    )
    parser.add_argument('--report', type=Path, help='Write a local JSON report')
    args = parser.parse_args()
    if args.require_tag and args.tag is None:
        parser.error('--require-tag requires --tag')
    report: dict[str, object] = {
        'artifact_errors': [],
        'release_blockers': [],
        'publication_performed': False,
    }
    try:
        report.update(inspect_archives(ROOT, args.dist, args.tag))
        print('Local distribution checks passed')
    except (
        ValueError,
        OSError,
        KeyError,
        zipfile.BadZipFile,
        tarfile.TarError,
        subprocess.CalledProcessError,
    ) as error:
        cast('list[str]', report['artifact_errors']).append(str(error))
    report['release_blockers'] = release_blockers(ROOT)
    for kind in ('artifact_errors', 'release_blockers'):
        for message in cast('list[str]', report[kind]):
            print(f'{kind}: {message}')
    report['preflight_passed'] = not report['artifact_errors'] and not report['release_blockers']
    if args.report:
        args.report.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print('No publication performed')
    return int(bool(report['artifact_errors'] or (args.strict and report['release_blockers'])))


if __name__ == '__main__':
    sys.exit(main())
