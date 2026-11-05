#!/usr/bin/env python3
# Copyright 2026 Axel Voitier
# ruff: noqa: EXE001, S603, S607, T201, EM101, TRY003, TRY301, TRY004
# Fixed argv queries and isolated command entry point; short errors belong at failure sites.
"""Select frozen source and sdist evidence without executing package code."""

import argparse
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tomllib
import zipfile
from collections.abc import Mapping
from pathlib import Path
from typing import cast

REPOSITORY = 'AxelVoitier/zensical-tarn'
COORDINATOR = '.github/workflows/release-preparation.yml'
BUILDER = '.github/workflows/release-build.yml'
SDIST_MAX_BYTES = 1_048_576
TRANSPORT_MAX_BYTES = 2_097_152
VERSION = re.compile(
    r'v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:(?:a|b|rc)(?:0|[1-9][0-9]*))?(?:\.post(?:0|[1-9][0-9]*))?',
)


def git(root: Path, *arguments: str) -> str:
    """Query Git without importing any package-controlled Python modules."""
    return subprocess.run(
        ['git', '-C', str(root), *arguments],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def source_identity(
    root: Path,
    tag: str,
    commit: str,
    *,
    tag_ref_target: str | None = None,
    tag_ref_type: str | None = None,
) -> dict[str, object]:
    """Resolve the tagged source using metadata only, with no backend hooks."""
    if not VERSION.fullmatch(tag):
        raise ValueError('Unsupported release version')
    if not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise ValueError('Expected a frozen commit SHA')
    ref = f'refs/tags/{tag}'
    if git(root, 'rev-parse', '--is-shallow-repository') != 'false':
        raise ValueError('Expected full source history')
    if (
        git(root, 'rev-parse', f'{ref}^{{commit}}') != commit
        or git(root, 'rev-parse', 'HEAD') != commit
    ):
        raise ValueError('Unexpected source revision')
    if git(root, 'status', '--porcelain', '--untracked-files=all'):
        raise ValueError('Expected clean frozen source')
    target = git(root, 'rev-parse', ref)
    target_type = git(root, 'cat-file', '-t', ref)
    if (tag_ref_target is not None or tag_ref_type is not None) and (
        tag_ref_target != target or tag_ref_type != target_type
    ):
        raise ValueError('Frozen tag target or type changed')
    config = tomllib.loads(git(root, 'show', f'{commit}:pyproject.toml'))
    tools: dict[str, str] = {}
    for requirement in config['dependency-groups']['release']:
        if not re.fullmatch(r'[A-Za-z0-9_.-]+==[A-Za-z0-9_.+-]+', requirement):
            raise ValueError('Release toolchain must be pinned')
        name, version = requirement.split('==')
        tools[name] = version
    return {
        'repository': REPOSITORY,
        'version': tag[1:],
        'tag': tag,
        'tag_ref_target': target,
        'tag_ref_type': target_type,
        'commit': commit,
        'tree': git(root, 'rev-parse', f'{commit}^{{tree}}'),
        'source_date_epoch': int(git(root, 'show', '-s', '--format=%ct', commit)),
        'coordinator': {'path': COORDINATOR, 'revision': commit},
        'builder': {'path': BUILDER, 'revision': commit},
        'toolchain': tools,
        'runtime': {
            'python': '3.12.12',
            'hatch': '1.18.1',
            'gh': '2.99.0',
            'cosign': '3.1.4',
            'runner': 'ubuntu-24.04',
        },
    }


def select_files(
    data: bytes,
    metadata: Mapping[str, object],
    expected: Mapping[str, int],
    kind: str,
    *,
    commit: str,
    run: str,
    attempt: str,
    repository_id: str,
    artifact_id: str,
) -> tuple[dict[str, bytes], dict[str, str]]:
    """Validate platform artifact metadata and transport before copying one member."""
    if not all(
        re.fullmatch(r'[1-9][0-9]*', item) for item in (run, attempt, repository_id, artifact_id)
    ):
        raise ValueError('Invalid platform identity')
    producer_value = metadata.get('workflow_run')
    if not isinstance(producer_value, dict):
        raise ValueError('Missing artifact producer')
    producer = cast('dict[str, object]', producer_value)
    if any(
        (
            metadata.get('id') != int(artifact_id),
            metadata.get('name') != f'{kind}-{run}-{attempt}',
            metadata.get('expired') is not False,
            producer.get('id') != int(run),
            producer.get('head_sha') != commit,
            producer.get('repository_id') != int(repository_id),
            producer.get('head_repository_id') != int(repository_id),
        ),
    ):
        raise ValueError('Unexpected artifact producer identity')
    digest = 'sha256:' + hashlib.sha256(data).hexdigest()
    if metadata.get('digest') != digest:
        raise ValueError('Artifact transport digest differs')
    if len(data) > TRANSPORT_MAX_BYTES:
        raise ValueError('Unexpected transport size')
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = archive.namelist()
        if len(names) != len(expected) or set(names) != set(expected):
            raise ValueError('Expected only the selected artifact files')
        files: dict[str, bytes] = {}
        for name, limit in expected.items():
            member = archive.getinfo(name)
            if not 0 < member.file_size <= limit:
                raise ValueError('Artifact member size outside the supported bounds')
            files[name] = archive.read(member)
    return files, {
        'run_id': run,
        'run_attempt': attempt,
        'artifact_id': artifact_id,
        'artifact_name': f'{kind}-{run}-{attempt}',
        'transport_digest': digest,
    }


def select_archive(
    data: bytes,
    metadata: Mapping[str, object],
    output: Path,
    version: str,
    *,
    commit: str,
    run: str,
    attempt: str,
    repository_id: str,
    artifact_id: str,
) -> tuple[Path, dict[str, str]]:
    """Copy only the independently selected source archive."""
    name = f'zensical_tarn-{version}.tar.gz'
    files, transport = select_files(
        data,
        metadata,
        {name: SDIST_MAX_BYTES},
        'sdist',
        commit=commit,
        run=run,
        attempt=attempt,
        repository_id=repository_id,
        artifact_id=artifact_id,
    )
    output.mkdir()
    selected = output / name
    selected.write_bytes(files[name])
    return selected, transport


PREDICATE_TYPE = 'https://slsa.dev/provenance/v1'
BUILD_TYPE = (
    'https://github.com/AxelVoitier/zensical-tarn/blob/main/scripts/release/sdist-build-v1.md'
)


def statement(
    identity: Mapping[str, object],
    archive: Path,
    transport: Mapping[str, str],
) -> dict[str, object]:
    """Construct one SLSA subject and its protected inputs from trusted selection."""
    if archive.name != f'zensical_tarn-{identity["version"]}.tar.gz' or archive.is_symlink():
        raise ValueError('Unexpected archive subject')
    return {
        '_type': 'https://in-toto.io/Statement/v1',
        'predicateType': PREDICATE_TYPE,
        'subject': [
            {
                'name': archive.name,
                'digest': {'sha256': hashlib.sha256(archive.read_bytes()).hexdigest()},
            },
        ],
        'predicate': {
            'buildDefinition': {
                'buildType': BUILD_TYPE,
                'externalParameters': {'source': dict(identity)},
                'internalParameters': {'transport': dict(transport)},
                'resolvedDependencies': [
                    {
                        'uri': f'git+https://github.com/{REPOSITORY}@refs/tags/{identity["tag"]}',
                        'digest': {'gitCommit': identity['commit']},
                    },
                ],
            },
            'runDetails': {
                'builder': {
                    'id': f'https://github.com/{REPOSITORY}/{BUILDER}@{identity["commit"]}',
                },
                'metadata': {
                    'invocationId': f'https://github.com/{REPOSITORY}/actions/runs/{transport["run_id"]}/attempts/{transport["run_attempt"]}',
                },
            },
        },
    }


def check_statement(
    verified: object,
    identity: Mapping[str, object],
    archive: Path,
    transport: Mapping[str, str],
) -> None:
    """Enforce exact protected fields on the cryptographically verified statement."""
    if verified != statement(identity, archive, transport):
        raise ValueError('Signed statement differs from frozen source, builder or subject policy')


def verified_statement(
    archive: Path,
    bundle: Path,
    identity: Mapping[str, object],
    *,
    timeout: float | None = None,
) -> object:
    """Require GitHub signature/certificate policy, then validate the signed payload."""
    result = subprocess.run(
        [
            'gh',
            'attestation',
            'verify',
            str(archive),
            '--bundle',
            str(bundle),
            '--repo',
            REPOSITORY,
            '--signer-workflow',
            f'{REPOSITORY}/{BUILDER}',
            '--signer-digest',
            str(identity['commit']),
            '--source-digest',
            str(identity['commit']),
            '--source-ref',
            f'refs/tags/{identity["tag"]}',
            '--deny-self-hosted-runners',
            '--predicate-type',
            PREDICATE_TYPE,
            '--format',
            'json',
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    records = json.loads(result.stdout)
    if not isinstance(records, list) or len(cast('list[object]', records)) != 1:
        raise ValueError('Expected one verified signed statement')
    record = cast('dict[str, object]', records[0])
    verification = cast('dict[str, object]', record['verificationResult'])
    return verification['statement']


def verify_bundle(
    archive: Path,
    bundle: Path,
    identity: Mapping[str, object],
    transport: Mapping[str, str],
) -> None:
    """Check certificate and exact protected source policy."""
    check_statement(verified_statement(archive, bundle, identity), identity, archive, transport)


def platform_context(environment: Mapping[str, str], tag: str, commit: str) -> tuple[str, str, str]:
    """Bind protected metadata to the caller's frozen tagged platform context."""
    expected = {
        'GITHUB_REPOSITORY': REPOSITORY,
        'GITHUB_SHA': commit,
        'GITHUB_REF': f'refs/tags/{tag}',
        'GITHUB_WORKFLOW_SHA': commit,
        'GITHUB_WORKFLOW_REF': f'{REPOSITORY}/{COORDINATOR}@refs/tags/{tag}',
    }
    if any(environment.get(key) != value for key, value in expected.items()):
        raise ValueError('Unexpected source or coordinating workflow revision')
    values = tuple(
        environment.get(key, '')
        for key in ('GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT', 'GITHUB_REPOSITORY_ID')
    )
    if any(not re.fullmatch(r'[1-9][0-9]*', value) for value in values):
        raise ValueError('Invalid platform execution identity')
    return values[0], values[1], values[2]


def fetch_files(
    identity: Mapping[str, object],
    artifact_id: str,
    kind: str,
    expected: Mapping[str, int],
    output: Path,
) -> dict[str, str]:
    """Read the exact platform artifact and independently verify its envelope."""
    run, attempt, repository_id = platform_context(
        os.environ,
        str(identity['tag']),
        str(identity['commit']),
    )
    if not re.fullmatch(r'[1-9][0-9]*', artifact_id):
        raise ValueError('Invalid artifact ID')
    endpoint = f'repos/{REPOSITORY}/actions/artifacts/{artifact_id}'
    response = subprocess.run(['gh', 'api', endpoint], capture_output=True, text=True, check=True)
    metadata = cast('dict[str, object]', json.loads(response.stdout))
    size = metadata.get('size_in_bytes')
    if not isinstance(size, int) or not 0 < size <= TRANSPORT_MAX_BYTES:
        raise ValueError('Unexpected transport size')
    data = subprocess.run(['gh', 'api', endpoint + '/zip'], capture_output=True, check=True).stdout
    if len(data) > TRANSPORT_MAX_BYTES:
        raise ValueError('Unexpected transport size')
    files, transport = select_files(
        data,
        metadata,
        expected,
        kind,
        commit=str(identity['commit']),
        run=run,
        attempt=attempt,
        repository_id=repository_id,
        artifact_id=artifact_id,
    )

    output.mkdir()
    for name, content in files.items():
        (output / name).write_bytes(content)
    return transport


def fetch_selected(
    identity: Mapping[str, object],
    artifact_id: str,
    output: Path,
) -> tuple[Path, dict[str, str]]:
    """Read and independently verify the selected source artifact."""
    name = f'zensical_tarn-{identity["version"]}.tar.gz'
    transfer = fetch_files(identity, artifact_id, 'sdist', {name: SDIST_MAX_BYTES}, output)
    return output / name, transfer


def main() -> int:
    """Expose trusted source selection, predicate generation and verification."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=['identity', 'predicate', 'verify'])
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--tag', required=True)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--tag-ref-target')
    parser.add_argument('--tag-ref-type', choices=['tag', 'commit'])
    parser.add_argument('--artifact-id')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--bundle', type=Path)
    args = parser.parse_args()
    try:
        if args.stage != 'identity' and (args.tag_ref_target is None or args.tag_ref_type is None):
            raise ValueError('Frozen tag target and type are required')
        identity = source_identity(
            args.root,
            args.tag,
            args.commit,
            tag_ref_target=args.tag_ref_target,
            tag_ref_type=args.tag_ref_type,
        )
        if args.stage == 'identity':
            print(json.dumps(identity, sort_keys=True))
            return 0
        if args.artifact_id is None or args.output is None:
            raise ValueError('Artifact ID and fresh output directory are required')
        archive, transport = fetch_selected(identity, args.artifact_id, args.output)
        if args.stage == 'verify':
            if args.bundle is None:
                raise ValueError('Signed bundle is required')
            verify_bundle(archive, args.bundle, identity, transport)
        else:
            expected = statement(identity, archive, transport)
            (args.output / 'statement.json').write_text(
                json.dumps(expected, sort_keys=True) + '\n',
                encoding='utf-8',
            )
            (args.output / 'predicate.json').write_text(
                json.dumps(expected['predicate'], sort_keys=True) + '\n',
                encoding='utf-8',
            )
            (args.output / 'selection.json').write_text(
                json.dumps(
                    {'source': identity, 'transport': transport, 'statement': expected},
                    sort_keys=True,
                )
                + '\n',
                encoding='utf-8',
            )
            # Fixed safe filename; consumed by the pinned single-subject attestation action.
            with Path(os.environ['GITHUB_OUTPUT']).open('a', encoding='utf-8') as stream:
                stream.write(f'archive={archive}\n')
        print('Sdist stage passed; no package publication performed')
    except (
        ValueError,
        OSError,
        KeyError,
        TypeError,
        zipfile.BadZipFile,
        subprocess.CalledProcessError,
    ) as error:
        print(f'Sdist stage failed: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
