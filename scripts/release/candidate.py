#!/usr/bin/env python3
# Copyright 2026 Axel Voitier
# ruff: noqa: EXE001, EM101, TRY003
"""Verify the exact archives and original evidence before freezing a candidate."""

import copy
import hashlib
import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from release.sdist import VERSION, statement, verified_statement, verify_bundle

EVIDENCE_MAX_BYTES = 262_144
ARCHIVE_MAX_BYTES = 1_048_576

WHEEL_BUILD_TYPE = (
    'https://github.com/AxelVoitier/zensical-tarn/blob/main/scripts/release/wheel-build-v1.md'
)


def sha256(path: Path) -> str:
    """Hash original file bytes, never a caller-supplied report."""
    if path.is_symlink() or not path.is_file():
        raise ValueError('Expected an original regular file')
    return hashlib.sha256(path.read_bytes()).hexdigest()


def wheel_statement(
    identity: Mapping[str, object],
    sdist: Path,
    wheel: Path,
    source_transfer: Mapping[str, str],
    wheel_transfer: Mapping[str, str],
) -> dict[str, object]:
    """Describe the fixed wheel build with its controlled, exact source input."""
    if wheel.name != f'zensical_tarn-{identity["version"]}-py3-none-any.whl':
        raise ValueError('Unexpected wheel subject')
    result = copy.deepcopy(statement(identity, sdist, wheel_transfer))
    result['subject'] = [{'name': wheel.name, 'digest': {'sha256': sha256(wheel)}}]
    predicate = cast('dict[str, object]', result['predicate'])
    definition = cast('dict[str, object]', predicate['buildDefinition'])
    definition['buildType'] = WHEEL_BUILD_TYPE
    definition['internalParameters'] = {
        'transport': dict(wheel_transfer),
        'sdistTransport': dict(source_transfer),
    }
    dependencies = cast('list[object]', definition['resolvedDependencies'])
    dependencies.append({'uri': sdist.name, 'digest': {'sha256': sha256(sdist)}})
    return result


def check_wheel_statement(  # noqa: PLR0917 - Explicit source and output evidence boundaries.
    verified: object,
    identity: Mapping[str, object],
    sdist: Path,
    wheel: Path,
    source_transfer: Mapping[str, str],
    wheel_transfer: Mapping[str, str],
) -> None:
    """Two signed outputs cannot replace the signed archive input relationship."""
    if verified != wheel_statement(identity, sdist, wheel, source_transfer, wheel_transfer):
        raise ValueError('Signed wheel statement differs from controlled input or frozen policy')


def archive_names(identity: Mapping[str, object]) -> tuple[str, str]:
    """Return the only two supported release filenames."""
    version = str(identity['version'])
    if not VERSION.fullmatch('v' + version):
        raise ValueError('Unsupported release version')
    return f'zensical_tarn-{version}.tar.gz', f'zensical_tarn-{version}-py3-none-any.whl'


def canonical(value: object) -> bytes:
    """Encode versioned manifest data using one stable JSON representation."""
    return (
        json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n'
    ).encode()


def manifest_bytes(
    identity: Mapping[str, object],
    files: Path,
    transfers: Mapping[str, Mapping[str, str]],
    evidence_ids: Mapping[str, str],
) -> bytes:
    """Describe exact original files; mutable check results belong elsewhere."""
    sdist, wheel = archive_names(identity)
    expected = {sdist, wheel, 'sdist.sigstore.json', 'wheel.sigstore.json'}
    if {path.name for path in files.iterdir()} != expected:
        raise ValueError('Expected exact candidate files')
    for name in expected:
        path = files / name
        limit = EVIDENCE_MAX_BYTES if name.endswith('.json') else ARCHIVE_MAX_BYTES
        if not 0 < path.stat().st_size <= limit:
            raise ValueError('Candidate file size outside supported bounds')
    if set(transfers) != {'sdist', 'wheel'} or set(evidence_ids) != {'sdist', 'wheel'}:
        raise ValueError('Expected both original evidence identities')
    for kind, transfer in transfers.items():
        if set(transfer) != {
            'run_id',
            'run_attempt',
            'artifact_id',
            'artifact_name',
            'transport_digest',
        } or any(
            not re.fullmatch(r'[1-9][0-9]*', transfer[key])
            for key in ('run_id', 'run_attempt', 'artifact_id')
        ):
            raise ValueError('Invalid producer identity')
        if transfer['artifact_name'] != f'{kind}-{transfer["run_id"]}-{transfer["run_attempt"]}':
            raise ValueError('Unexpected producer artifact name')
        if not re.fullmatch(r'sha256:[0-9a-f]{64}', transfer['transport_digest']):
            raise ValueError('Invalid transport digest')
        if not re.fullmatch(r'[1-9][0-9]*', evidence_ids[kind]):
            raise ValueError('Invalid original evidence identifier')
    if any(transfers['sdist'][key] != transfers['wheel'][key] for key in ('run_id', 'run_attempt')):
        raise ValueError('Wheel and source must belong to the same execution')
    return canonical(
        {
            'schema': 'tarn-candidate-v1',
            'source': dict(identity),
            'archives': {
                name: {'size': (files / name).stat().st_size, 'sha256': sha256(files / name)}
                for name in (sdist, wheel)
            },
            'evidence': {
                kind: {
                    'artifact_id': evidence_ids[kind],
                    'file': f'{kind}.sigstore.json',
                    'sha256': sha256(files / f'{kind}.sigstore.json'),
                }
                for kind in ('sdist', 'wheel')
            },
            'transports': {kind: dict(value) for kind, value in transfers.items()},
            'wheel_input_sha256': sha256(files / sdist),
        }
    )


def validate_manifest(
    data: bytes, digest: str, identity: Mapping[str, object], files: Path
) -> dict[str, object]:
    """Reject noncanonical data, changed identities and substituted original bytes."""
    if not re.fullmatch(r'[0-9a-f]{64}', digest) or hashlib.sha256(data).hexdigest() != digest:
        raise ValueError('Candidate manifest digest differs')
    try:
        document = json.loads(data)
        transfers = document['transports']
        evidence_ids = {
            kind: document['evidence'][kind]['artifact_id'] for kind in ('sdist', 'wheel')
        }
        if data != manifest_bytes(identity, files, transfers, evidence_ids):
            raise ValueError('Candidate manifest differs from canonical frozen policy')
    except (KeyError, TypeError, AttributeError) as error:
        raise ValueError('Malformed candidate manifest') from error
    return cast('dict[str, object]', document)


def verify_candidate(data: bytes, digest: str, identity: Mapping[str, object], files: Path) -> None:
    """Verify both original signatures and the exact signed wheel input relationship."""
    document = validate_manifest(data, digest, identity, files)
    transfers = cast('dict[str, dict[str, str]]', document['transports'])
    sdist_name, wheel_name = archive_names(identity)
    sdist, wheel = files / sdist_name, files / wheel_name
    verify_bundle(sdist, files / 'sdist.sigstore.json', identity, transfers['sdist'])
    verified = verified_statement(wheel, files / 'wheel.sigstore.json', identity)
    check_wheel_statement(verified, identity, sdist, wheel, transfers['sdist'], transfers['wheel'])
