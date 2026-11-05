#!/usr/bin/env python3
# Copyright 2026 Axel Voitier
# ruff: noqa: EXE001, EM101, TRY003
"""Authenticated, ID-addressed GitHub release storage transport."""

import json
import os
import re
import subprocess
from typing import cast
from urllib.parse import quote

from release.candidate import ARCHIVE_MAX_BYTES
from release.sdist import REPOSITORY
from release.storage import Asset, Release


def number(value: object) -> int:
    """Reject booleans, missing IDs and coercible strings from API metadata."""
    if type(value) is not int or value < 1:
        raise ValueError('Expected a positive API identifier')
    return value


def document(value: object) -> dict[str, object]:
    """Require a JSON object before reading metadata fields."""
    if not isinstance(value, dict):
        raise TypeError('Expected API object')
    return cast('dict[str, object]', value)


def text(value: object) -> str:
    """Do not coerce malformed API fields into plausible names or identities."""
    if not isinstance(value, str):
        raise TypeError('Expected API string')
    return value


def release_info(value: object) -> Release:
    """Decode only the metadata that storage policy independently checks."""
    item = document(value)
    draft = item.get('draft')
    if type(draft) is not bool:
        raise ValueError('Expected explicit draft state')
    return Release(
        number(item.get('id')),
        text(item.get('tag_name')),
        text(item.get('target_commitish')),
        text(item.get('body')),
        draft,
    )


def asset_info(value: object) -> Asset:
    """A starter or empty asset cannot stand in for verified uploaded bytes."""
    item = document(value)
    return Asset(
        number(item.get('id')),
        text(item.get('name')),
        number(item.get('size')),
        text(item.get('state')),
    )


class GitHubAPI:
    """Use explicit job-token authentication and fixed repository/host endpoints."""

    def request(
        self,
        endpoint: str,
        *,
        data: bytes | None = None,
        binary: bool = False,
        json_body: bool = False,
    ) -> bytes:
        """Never put a credential in arguments, Git metadata, logs or filenames."""
        if not (os.environ.get('GH_TOKEN') or os.environ.get('GITHUB_TOKEN')):
            raise ValueError('Explicit authenticated job token required')
        argv = [
            'gh',
            'api',
            '--hostname',
            'github.com',
            endpoint,
            '-H',
            'Accept: application/octet-stream' if binary else 'Accept: application/vnd.github+json',
            '-H',
            'X-GitHub-Api-Version: 2026-03-10',
        ]
        if data is not None:
            argv.extend(
                [
                    '--method',
                    'POST',
                    '--input',
                    '-',
                    '-H',
                    'Content-Type: application/json'
                    if json_body
                    else 'Content-Type: application/octet-stream',
                    '-H',
                    f'Content-Length: {len(data)}',
                ],
            )
        return subprocess.run(  # noqa: S603 - Fixed gh binary, hosts, endpoints; no shell.
            argv,
            input=data,
            capture_output=True,
            check=True,
            timeout=120,
        ).stdout

    def create_product(self, tag: str, target: str, body: str) -> Release:
        """Create only an unpublished product draft at an existing frozen tag."""
        data = json.dumps(
            {
                'tag_name': tag,
                'target_commitish': target,
                'name': tag,
                'body': body,
                'draft': True,
                'prerelease': True,
            },
        ).encode()
        return release_info(
            json.loads(
                self.request(
                    f'repos/{REPOSITORY}/releases',
                    data=data,
                    json_body=True,
                ),
            ),
        )

    def tag_identity(self, tag: str) -> tuple[str, str, str]:
        """Resolve actual ref and peeled commit rather than target_commitish alone."""
        if not (tag == 'release-records' or re.fullmatch(r'v[0-9][A-Za-z0-9.]*', tag)):
            raise ValueError('Unexpected storage tag')
        ref = document(
            json.loads(self.request(f'repos/{REPOSITORY}/git/ref/tags/{quote(tag, safe="")}')),
        )
        target = document(ref.get('object'))
        original_sha, original_type = text(target.get('sha')), text(target.get('type'))
        seen: set[str] = set()
        while True:
            sha, kind = text(target.get('sha')), text(target.get('type'))
            if not re.fullmatch(r'[0-9a-f]{40}', sha) or sha in seen:
                raise ValueError('Malformed storage tag identity')
            if kind == 'commit':
                return original_sha, original_type, sha
            if kind != 'tag':
                raise ValueError('Storage tag does not identify a commit')
            seen.add(sha)
            annotation = document(json.loads(self.request(f'repos/{REPOSITORY}/git/tags/{sha}')))
            target = document(annotation.get('object'))

    def repository_id(self) -> str:
        """Bind the repository name to its retained numeric identity."""
        return str(number(document(json.loads(self.request(f'repos/{REPOSITORY}'))).get('id')))

    def release(self, identifier: int) -> Release:
        """Read a retained release ID through the authenticated API."""
        return release_info(
            json.loads(self.request(f'repos/{REPOSITORY}/releases/{number(identifier)}')),
        )

    def releases_page(self, page: int) -> list[Release]:
        """Return one page; the policy layer reads through the final empty page."""
        data: object = json.loads(
            self.request(f'repos/{REPOSITORY}/releases?per_page=100&page={number(page)}'),
        )
        if not isinstance(data, list):
            raise TypeError('Expected release page')
        return [release_info(item) for item in cast('list[object]', data)]

    def assets_page(self, release: int, page: int) -> list[Asset]:
        """Do not rely on the possibly truncated assets embedded in a release."""
        endpoint = (
            f'repos/{REPOSITORY}/releases/{number(release)}/assets?per_page=100&page={number(page)}'
        )
        data: object = json.loads(self.request(endpoint))
        if not isinstance(data, list):
            raise TypeError('Expected asset page')
        return [asset_info(item) for item in cast('list[object]', data)]

    def asset(self, identifier: int) -> Asset:
        """Read exact metadata without trusting caller-provided URLs."""
        return asset_info(
            json.loads(self.request(f'repos/{REPOSITORY}/releases/assets/{number(identifier)}')),
        )

    def download(self, identifier: int) -> bytes:
        """The authenticated binary endpoint handles download redirects via gh."""
        return self.request(f'repos/{REPOSITORY}/releases/assets/{number(identifier)}', binary=True)

    def upload(self, release: int, name: str, data: bytes) -> None:
        """Create once by release ID; no --clobber, edit or delete operation exists."""
        if (
            not re.fullmatch(r'[A-Za-z0-9_.-]{1,255}', name)
            or not 0 < len(data) <= ARCHIVE_MAX_BYTES
        ):
            raise ValueError('Invalid retained asset name or size')
        endpoint = (
            f'https://uploads.github.com/repos/{REPOSITORY}/releases/'
            f'{number(release)}/assets?name={quote(name, safe="")}'
        )
        self.request(endpoint, data=data)
