#!/usr/bin/env python3
# Copyright 2026 Axel Voitier
# ruff: noqa: EXE001, T201, EM101, TRY003, TRY301
"""Trusted fixed artifact transfer and candidate verification; no package execution."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from release.candidate import (
    ARCHIVE_MAX_BYTES,
    EVIDENCE_MAX_BYTES,
    archive_names,
    check_wheel_statement,
    manifest_bytes,
    sha256,
    verify_candidate,
    wheel_statement,
)
from release.sdist import (
    SDIST_MAX_BYTES,
    fetch_files,
    platform_context,
    source_identity,
    statement,
    verified_statement,
    verify_bundle,
)


def select_source(
    identity: dict[str, object],
    sdist_id: str,
    signed_id: str,
    output: Path,
) -> tuple[Path, dict[str, str]]:
    """Rehash the raw source and verify its original signed evidence independently."""
    sdist, _ = archive_names(identity)
    transfer = fetch_files(identity, sdist_id, 'sdist', {sdist: SDIST_MAX_BYTES}, output / 'source')
    fetch_files(
        identity,
        signed_id,
        'signed-sdist',
        {
            sdist: SDIST_MAX_BYTES,
            'selection.json': EVIDENCE_MAX_BYTES,
            'sdist.sigstore.json': EVIDENCE_MAX_BYTES,
        },
        output / 'signed-source',
    )
    source = output / 'source' / sdist
    if source.read_bytes() != (output / 'signed-source' / sdist).read_bytes():
        raise ValueError('Signed source transfer differs from selected original')
    expected = {
        'source': identity,
        'transport': transfer,
        'statement': statement(identity, source, transfer),
    }
    report = json.loads((output / 'signed-source/selection.json').read_bytes())
    if report != expected:
        raise ValueError('Source selection report differs from independent protected policy')
    verify_bundle(source, output / 'signed-source/sdist.sigstore.json', identity, transfer)
    return source, transfer


def set_output(name: str, value: str) -> None:
    """Expose only fixed names and verified paths/digests to the workflow graph."""
    with Path(os.environ['GITHUB_OUTPUT']).open('a', encoding='utf-8') as stream:
        stream.write(f'{name}={value}\n')


def freeze_selection(  # noqa: PLR0917 - Separate original files and evidence identities.
    identity: dict[str, object],
    sdist: Path,
    wheel: Path,
    transfers: dict[str, dict[str, str]],
    evidence_ids: dict[str, str],
    output: Path,
) -> None:
    """Keep original evidence and bytes together before exposing a candidate identity."""
    signed_wheel_id = evidence_ids['wheel']
    signed_sdist_id = evidence_ids['sdist']
    source_transfer, wheel_transfer = transfers['sdist'], transfers['wheel']
    wheel_name = wheel.name
    fetch_files(
        identity,
        signed_wheel_id,
        'signed-wheel',
        {
            wheel_name: ARCHIVE_MAX_BYTES,
            'wheel.sigstore.json': EVIDENCE_MAX_BYTES,
        },
        output / 'signed-wheel',
    )
    if wheel.read_bytes() != (output / 'signed-wheel' / wheel_name).read_bytes():
        raise ValueError('Signed wheel transfer differs from selected original')
    files = output / 'candidate/files'
    files.mkdir(parents=True)
    for original in (
        sdist,
        wheel,
        output / 'signed-source/sdist.sigstore.json',
        output / 'signed-wheel/wheel.sigstore.json',
    ):
        (files / original.name).write_bytes(original.read_bytes())
    data = manifest_bytes(
        identity,
        files,
        {'sdist': source_transfer, 'wheel': wheel_transfer},
        {'sdist': signed_sdist_id, 'wheel': signed_wheel_id},
    )
    digest = hashlib.sha256(data).hexdigest()
    verify_candidate(data, digest, identity, files)
    (files.parent / 'candidate.json').write_bytes(data)
    set_output('manifest-digest', digest)


def main() -> int:
    """Run a fixed trusted stage from the same frozen source as the builder."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        'stage',
        choices=['input', 'predicate', 'verify-wheel', 'freeze', 'verify-candidate'],
    )
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--tag', required=True)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--tag-ref-target', required=True)
    parser.add_argument('--tag-ref-type', required=True, choices=['tag', 'commit'])
    parser.add_argument('--sdist-id')
    parser.add_argument('--signed-sdist-id')
    parser.add_argument('--wheel-id')
    parser.add_argument('--signed-wheel-id')
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--bundle', type=Path)
    parser.add_argument('--manifest-digest')
    args = parser.parse_args()
    try:
        identity = source_identity(
            args.root,
            args.tag,
            args.commit,
            tag_ref_target=args.tag_ref_target,
            tag_ref_type=args.tag_ref_type,
        )
        if args.stage == 'verify-candidate':
            verify_candidate(
                (args.output / 'candidate.json').read_bytes(),
                args.manifest_digest or '',
                identity,
                args.output / 'files',
            )
            print('Original candidate files and both signed statements verified')
            return 0
        platform_context(os.environ, args.tag, args.commit)
        if args.sdist_id is None or args.signed_sdist_id is None:
            raise ValueError('Both original source artifact IDs are required')
        args.output.mkdir()
        sdist, source_transfer = select_source(
            identity,
            args.sdist_id,
            args.signed_sdist_id,
            args.output,
        )
        if args.stage == 'input':
            set_output('sdist', str(sdist))
            set_output('sdist-sha256', sha256(sdist))
            return 0
        if args.wheel_id is None:
            raise ValueError('Original wheel artifact ID is required')
        _, wheel_name = archive_names(identity)
        wheel_transfer = fetch_files(
            identity,
            args.wheel_id,
            'wheel',
            {wheel_name: ARCHIVE_MAX_BYTES},
            args.output / 'wheel',
        )
        wheel = args.output / 'wheel' / wheel_name
        expected = wheel_statement(identity, sdist, wheel, source_transfer, wheel_transfer)
        if args.stage == 'predicate':
            (args.output / 'statement.json').write_text(
                json.dumps(expected, sort_keys=True) + '\n',
                encoding='utf-8',
            )
            (args.output / 'predicate.json').write_text(
                json.dumps(expected['predicate'], sort_keys=True) + '\n',
                encoding='utf-8',
            )
            set_output('archive', str(wheel))
        elif args.stage == 'verify-wheel':
            if args.bundle is None:
                raise ValueError('Original wheel bundle is required')
            check_wheel_statement(
                verified_statement(wheel, args.bundle, identity),
                identity,
                sdist,
                wheel,
                source_transfer,
                wheel_transfer,
            )
        else:
            if args.signed_wheel_id is None:
                raise ValueError('Original signed wheel artifact ID is required')
            freeze_selection(
                identity,
                sdist,
                wheel,
                {'sdist': source_transfer, 'wheel': wheel_transfer},
                {'sdist': args.signed_sdist_id, 'wheel': args.signed_wheel_id},
                args.output,
            )
        print('Trusted candidate stage passed; no publication performed')
    except (
        ValueError,
        OSError,
        KeyError,
        TypeError,
        zipfile.BadZipFile,
        subprocess.CalledProcessError,
    ) as error:
        print(f'Candidate stage failed: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
