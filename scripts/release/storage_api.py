#!/usr/bin/env python3
# Copyright 2026 Axel Voitier
# ruff: noqa: EXE001, EM101, TRY003
"""Authenticated, ID-addressed GitHub release storage transport."""

import json
import os
import re
import subprocess
import time
from collections.abc import Callable, Generator
from contextlib import contextmanager
from copy import deepcopy
from typing import TypeVar, cast
from urllib.parse import quote

from release.candidate import ARCHIVE_MAX_BYTES
from release.sdist import REPOSITORY
from release.storage import Asset, Release

T = TypeVar('T')
CREATE_VISIBILITY_READS = 6
CREATE_VISIBILITY_INTERVAL_SECONDS = 2


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

    def __init__(self) -> None:
        self._reads: dict[tuple[str, bool], tuple[object, Callable[[], object]]] | None = None

    @contextmanager
    def consistent_reads(self) -> Generator[None]:
        """Reuse decoded facts within one operation, with fresh checks at its boundaries.

        Every write checks all observed facts and invalidates affected collection
        pages before sending its request. A successful read-only result also
        requires a fresh check. Nothing survives a command or approval wait.
        """
        if self._reads is not None:
            raise ValueError('Nested storage read scopes are unsupported')
        self._reads = {}
        try:
            yield
            self._verify_reads()
        finally:
            self._reads = None

    def _verify_reads(self) -> None:
        if self._reads is not None:
            for expected, query in self._reads.values():
                if query() != expected:
                    raise ValueError('Remote release state changed during operation')

    def _invalidate(self, changes: str | None) -> None:
        if self._reads is not None:
            self._reads = {
                key: value
                for key, value in self._reads.items()
                if changes is not None and not key[0].startswith(changes)
            }

    def _read(self, key: tuple[str, bool], query: Callable[[], T]) -> T:
        if self._reads is None:
            return query()
        if key not in self._reads:
            self._reads[key] = (query(), query)
        # Callers may change returned lists without changing the checked snapshot.
        return deepcopy(cast('T', self._reads[key][0]))

    def _decoded(self, endpoint: str, decode: Callable[[bytes], T], *, binary: bool = False) -> T:
        return self._read((endpoint, binary), lambda: decode(self.request(endpoint, binary=binary)))

    def request(
        self,
        endpoint: str,
        *,
        data: bytes | None = None,
        binary: bool = False,
        json_body: bool = False,
        changes: str | None = None,
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
            self._verify_reads()
            if self._reads is not None:
                # The only supported writes create releases or append assets.
                # All retained facts still receive fresh comparisons at every
                # barrier. Unknown write types conservatively discard everything.
                self._invalidate(changes)
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

    def create_product(
        self,
        tag: str,
        target: str,
        body: str,
        *,
        on_created: Callable[[int], None] | None = None,
    ) -> Release:
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
        created = release_info(
            json.loads(
                self.request(
                    f'repos/{REPOSITORY}/releases',
                    data=data,
                    json_body=True,
                    changes=f'repos/{REPOSITORY}/releases?',
                ),
            ),
        )
        # Preserve a known write receipt before any subsequent read can fail.
        if on_created is not None:
            on_created(created.id)
        self._confirm_created_release(created)
        return created

    def _confirm_created_release(self, created: Release) -> None:
        """A known successful creation can precede its first release-list response.

        Never keep a missing-list observation as the validation snapshot after
        our own write. Retry only reads, then retain the confirmed full listing
        with its normal fresh comparisons before further writes or success.
        """
        for attempt in range(CREATE_VISIBILITY_READS):
            if attempt:
                self._invalidate(f'repos/{REPOSITORY}/releases?')
                time.sleep(CREATE_VISIBILITY_INTERVAL_SECONDS)
            matches: list[Release] = []
            seen: set[int] = set()
            page = 1
            while batch := self.releases_page(page):
                if seen.intersection(item.id for item in batch):
                    raise ValueError('Repeated release page after creation')
                seen.update(item.id for item in batch)
                matches.extend(item for item in batch if item.tag == created.tag)
                page += 1
            if matches == [created]:
                return
            if matches:
                raise ValueError('Created draft conflicts with listed identity')
        message = (
            f'Created release {created.id} is not visible in listings; inspect before retrying'
        )
        raise ValueError(message)

    def tag_identity(self, tag: str) -> tuple[str, str, str]:
        """Resolve actual ref and peeled commit rather than target_commitish alone."""
        return self._read((f'tag:{tag}', False), lambda: self._resolve_tag(tag))

    def _resolve_tag(self, tag: str) -> tuple[str, str, str]:
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
        return self._decoded(
            f'repos/{REPOSITORY}',
            lambda data: str(number(document(json.loads(data)).get('id'))),
        )

    def release(self, identifier: int) -> Release:
        """Read a retained release ID through the authenticated API."""
        return self._decoded(
            f'repos/{REPOSITORY}/releases/{number(identifier)}',
            lambda data: release_info(json.loads(data)),
        )

    def releases_page(self, page: int) -> list[Release]:
        """Return one page; the policy layer reads through the final empty page."""

        def decode(raw: bytes) -> list[Release]:
            data: object = json.loads(raw)
            if not isinstance(data, list):
                raise TypeError('Expected release page')
            return [release_info(item) for item in cast('list[object]', data)]

        return self._decoded(
            f'repos/{REPOSITORY}/releases?per_page=100&page={number(page)}',
            decode,
        )

    def assets_page(self, release: int, page: int) -> list[Asset]:
        """Do not rely on the possibly truncated assets embedded in a release."""
        endpoint = (
            f'repos/{REPOSITORY}/releases/{number(release)}/assets?per_page=100&page={number(page)}'
        )

        def decode(raw: bytes) -> list[Asset]:
            data: object = json.loads(raw)
            if not isinstance(data, list):
                raise TypeError('Expected asset page')
            return [asset_info(item) for item in cast('list[object]', data)]

        return self._decoded(endpoint, decode)

    def asset(self, identifier: int) -> Asset:
        """Read exact metadata without trusting caller-provided URLs."""
        return self._decoded(
            f'repos/{REPOSITORY}/releases/assets/{number(identifier)}',
            lambda data: asset_info(json.loads(data)),
        )

    def download(self, identifier: int) -> bytes:
        """The authenticated binary endpoint handles download redirects via gh."""
        return self._decoded(
            f'repos/{REPOSITORY}/releases/assets/{number(identifier)}',
            lambda data: data,
            binary=True,
        )

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
        self.request(
            endpoint,
            data=data,
            changes=f'repos/{REPOSITORY}/releases/{number(release)}/assets?',
        )
