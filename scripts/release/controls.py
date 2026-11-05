#!/usr/bin/env python3
# Copyright 2026 Axel Voitier
# ruff: noqa: EXE001, EM101, TRY003, S607, T201
"""Probe real job-token boundaries using an unpublished, disposable fixture.

This is a hosted integration test, not a publisher or a package check.
Only prepare and cleanup need release-write access. Never execute package code.
Private draft bodies, assets and raw API errors must not enter public logs.
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from http import HTTPStatus
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from release.candidate import canonical
from release.sdist import REPOSITORY
from release.storage import Draft, Storage
from release.storage_api import GitHubAPI, document, number


def identity() -> Draft:
    """Use retained setup, never discover authority from a release title."""
    if os.environ['GITHUB_REPOSITORY'] != REPOSITORY:
        raise ValueError('Unexpected repository')
    if os.environ['GITHUB_REPOSITORY_ID'] != os.environ['RECORD_REPOSITORY_ID']:
        raise ValueError('Repository identity differs from retained setup')
    commit = os.environ['GITHUB_SHA']
    if not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise ValueError('Invalid setup source identity')
    if os.environ['GITHUB_REF'] != f'refs/tags/v0-release-controls-{commit}':
        raise ValueError('Probes require an exact frozen setup ref')
    if os.environ['PREPARATION_ENABLED'] != 'false':
        raise ValueError('Release preparation must remain disabled during setup')
    return Draft(
        int(os.environ['RECORD_ID']),
        'administrative',
        'release-records',
        os.environ['RECORD_TARGET'],
        os.environ['RECORD_REPOSITORY_ID'],
    )


def fixture_tag() -> str:
    """A setup-only name cannot be mistaken for a package version."""
    run, attempt = os.environ['GITHUB_RUN_ID'], os.environ['GITHUB_RUN_ATTEMPT']
    if not re.fullmatch(r'[1-9][0-9]*', run) or not re.fullmatch(r'[1-9][0-9]*', attempt):
        raise ValueError('Invalid run identity')
    return f'release-controls-probe-{run}-{attempt}'


def fixture_body() -> str:
    return canonical({'schema': 'tarn-controls-probe-v1', 'tag': fixture_tag()}).decode()


def output(name: str, value: int | str) -> None:
    with Path(os.environ['GITHUB_OUTPUT']).open('a') as stream:
        stream.write(f'{name}={value}\n')


def snapshot(storage: Storage) -> str:
    """Keep an opaque fingerprint of the independent administrative history."""
    storage.validate(storage.administrative)
    assets = sorted(
        (
            asset.id,
            asset.name,
            asset.size,
            hashlib.sha256(storage.read(storage.administrative, asset)).hexdigest(),
        )
        for asset in storage.assets(storage.administrative)
    )
    return hashlib.sha256(canonical(assets)).hexdigest()


def fixture(api: GitHubAPI, identifier: int, record: Draft, tag: str) -> None:
    """Deletion authority never includes the shared record or a product release."""
    if identifier == record.id:
        raise ValueError('The administrative record is not a disposable fixture')
    current = api.release(identifier)
    if (
        not current.draft
        or current.tag != tag
        or current.target != record.target
        or current.body != fixture_body()
    ):
        raise ValueError('Disposable fixture identity changed')


def draft_payload(record: Draft, tag: str) -> bytes:
    """Use the same valid request for allowed and denied creation probes."""
    return canonical(
        {
            'tag_name': tag,
            'target_commitish': record.target,
            'name': 'Disposable release-control probe',
            'body': fixture_body(),
            'draft': True,
            'prerelease': True,
            'make_latest': 'false',
        }
    )


def create_fixture(api: GitHubAPI, record: Draft, tag: str) -> int:
    """A lost creation response requires inspection, never a blind retry."""
    response = document(
        json.loads(
            api.request(
                f'repos/{REPOSITORY}/releases',
                data=draft_payload(record, tag),
                json_body=True,
            )
        )
    )
    return number(response.get('id'))


def prepare(api: GitHubAPI, record: Draft) -> None:
    """Read the real record, then exercise draft/asset writes on fixtures only."""
    storage = Storage(api, record)
    output('snapshot', snapshot(storage))
    identifier = create_fixture(api, record, fixture_tag())
    output('fixture_id', identifier)
    fixture(api, identifier, record, fixture_tag())
    payload = fixture_body().encode()
    api.upload(identifier, 'controls-proof.json', payload)
    assets = api.assets_page(identifier, 1)
    if len(assets) != 1 or assets[0].name != 'controls-proof.json':
        raise ValueError('Unexpected fixture asset set')
    if api.download(assets[0].id) != payload:
        raise ValueError('Authenticated fixture read-back differs')
    output('asset_id', assets[0].id)
    product = create_fixture(api, record, fixture_tag() + '-product')
    output('product_fixture_id', product)
    if product == identifier:
        raise ValueError('Disposable product and record fixtures must be independent')
    fixture(api, product, record, fixture_tag() + '-product')


def denied(
    api: GitHubAPI,
    endpoint: str,
    *,
    data: bytes | None = None,
    statuses: tuple[int, ...] = (HTTPStatus.FORBIDDEN, HTTPStatus.NOT_FOUND),
) -> None:
    """Only an observed permission denial passes; network errors never do."""
    try:
        api.request(endpoint, data=data, json_body=data is not None)
    except subprocess.CalledProcessError as error:
        status = re.search(rb'\(HTTP ([0-9]{3})\)', error.stderr or b'')
        if status is None or int(status[1]) not in statuses:
            raise ValueError('Expected a permission denial, not a transport error') from None
        if int(status[1]) != HTTPStatus.FORBIDDEN or (
            b'Resource not accessible by integration' in (error.stderr or b'')
        ):
            return
        raise ValueError('Expected a permission denial, not a transport error') from None
    raise ValueError('A package job unexpectedly gained privileged access')


def package(api: GitHubAPI, record: Draft) -> None:
    """Use the actual read-only job token, without executing any package code."""
    if os.environ.get('ACTIONS_ID_TOKEN_REQUEST_TOKEN') or os.environ.get(
        'ACTIONS_ID_TOKEN_REQUEST_URL'
    ):
        raise ValueError('A package job unexpectedly gained signing identity access')
    identifier = int(os.environ['FIXTURE_ID'])
    if identifier == record.id:
        raise ValueError('Cannot use the real record as a write probe')
    # Use a valid, harmless draft payload so a validation error cannot pass.
    denied(
        api,
        f'repos/{REPOSITORY}/releases',
        data=draft_payload(record, fixture_tag() + '-denied'),
    )


def public(record: Draft) -> None:
    """The requests deliberately contain no token, even on an authenticated runner."""
    for endpoint in (
        f'releases/{record.id}',
        f'releases/{int(os.environ["FIXTURE_ID"])}',
        f'releases/assets/{int(os.environ["ASSET_ID"])}',
    ):
        request = urllib.request.Request(
            f'https://api.github.com/repos/{REPOSITORY}/{endpoint}',
            headers={
                'Accept': 'application/vnd.github+json',
                'User-Agent': 'tarn-release-controls',
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30):  # noqa: S310 - Fixed HTTPS API host.
                pass
        except urllib.error.HTTPError as error:
            if error.code == HTTPStatus.NOT_FOUND:
                continue
            raise ValueError('Anonymous request did not return the required denial') from None
        raise ValueError('Anonymous readers can access an unpublished draft or asset')


def delete_fixture(api: GitHubAPI, record: Draft, identifier: int, tag: str) -> None:
    """Guard deletion by numeric ID, source, role marker, run and draft state."""
    fixture(api, identifier, record, tag)
    subprocess.run(  # noqa: S603 - Fixed gh command, endpoint and validated numeric ID.
        ['gh', 'api', '--method', 'DELETE', f'repos/{REPOSITORY}/releases/{identifier}'],
        check=True,
        capture_output=True,
        timeout=120,
    )
    denied(api, f'repos/{REPOSITORY}/releases/{identifier}', statuses=(HTTPStatus.NOT_FOUND,))


def cleanup(api: GitHubAPI, record: Draft) -> None:
    """Delete a product fixture; prove nonempty independent records survive."""
    identifier = int(os.environ['FIXTURE_ID'])
    product = int(os.environ['PRODUCT_FIXTURE_ID'])
    if product == identifier:
        raise ValueError('Disposable product and record fixtures must be independent')
    fixture(api, identifier, record, fixture_tag())
    delete_fixture(api, record, product, fixture_tag() + '-product')
    fixture(api, identifier, record, fixture_tag())
    assets = api.assets_page(identifier, 1)
    if len(assets) != 1 or assets[0].id != int(os.environ['ASSET_ID']):
        raise ValueError('Independent fixture history changed after product deletion')
    if api.download(assets[0].id) != fixture_body().encode():
        raise ValueError('Independent fixture history bytes changed after product deletion')
    delete_fixture(api, record, identifier, fixture_tag())
    if snapshot(Storage(api, record)) != os.environ['RECORD_SNAPSHOT']:
        raise ValueError('Administrative history changed after fixture deletion')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=('prepare', 'package', 'public', 'cleanup'))
    args = parser.parse_args()
    try:
        record = identity()
        if args.stage == 'public':
            public(record)
        else:
            api = GitHubAPI()
            if args.stage == 'prepare':
                prepare(api, record)
            elif args.stage == 'package':
                package(api, record)
            else:
                cleanup(api, record)
    except (ValueError, KeyError, TypeError, OSError, subprocess.SubprocessError):
        # API responses and exceptions can contain private draft content. Never log them.
        message = (
            f'Release-control probe {args.stage} failed. Inspect private state before retrying.'
        )
        raise SystemExit(message) from None
    print(f'Release-control probe {args.stage} passed.')


if __name__ == '__main__':
    main()
