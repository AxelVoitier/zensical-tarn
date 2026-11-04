#!/usr/bin/env python3
# Copyright 2026 Axel Voitier
# ruff: noqa: EXE001, EM101, TRY003
"""Retain originals and append verified private history without replacing assets."""

import hashlib
import json
import re
import subprocess
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal, Protocol

from release.candidate import (
    ARCHIVE_MAX_BYTES,
    EVIDENCE_MAX_BYTES,
    archive_names,
    canonical,
    verify_candidate,
)
from release.sdist import REPOSITORY, VERSION

EVENT_VERSION_MAX_LENGTH = 64
EVENT_SEQUENCE_MAX = 9_223_372_036_854_775_807


def digest(data: bytes) -> str:
    """Hash downloaded content independently of API digest metadata."""
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class Draft:
    """Retained setup identity, never discovered by a human-readable title."""

    id: int
    role: Literal['administrative', 'product']
    tag: str
    target: str
    repository_id: str

    @property
    def body(self) -> str:
        """Fixed public-safe role marker; private records belong only in assets."""
        return canonical(
            {
                'schema': 'tarn-storage-v1',
                'repository': REPOSITORY,
                'repository_id': self.repository_id,
                'role': self.role,
                'tag': self.tag,
                'target': self.target,
            },
        ).decode()


@dataclass(frozen=True)
class Release:
    """Release metadata returned by the authenticated repository endpoint."""

    id: int
    tag: str
    target: str
    body: str
    draft: bool


@dataclass(frozen=True)
class Asset:
    """Metadata addressed by asset ID and membership of an identified release."""

    id: int
    name: str
    size: int
    state: str


class ReleaseAPI(Protocol):
    """Authenticated service boundary; no replace, delete or publish operations."""

    def create_product(self, tag: str, target: str, body: str) -> Release: ...
    def repository_id(self) -> str: ...
    def tag_identity(self, tag: str) -> tuple[str, str, str]: ...
    def release(self, identifier: int) -> Release: ...
    def releases_page(self, page: int) -> list[Release]: ...
    def assets_page(self, release: int, page: int) -> list[Asset]: ...
    def asset(self, identifier: int) -> Asset: ...
    def download(self, identifier: int) -> bytes: ...
    def upload(self, release: int, name: str, data: bytes) -> None: ...


@dataclass(frozen=True)
class Event:
    """One logical transition; sequence and predecessor span a product version."""

    version: str
    candidate: str | None
    source: str
    run: str
    attempt: str
    sequence: int
    kind: str
    predecessor: str | None
    details: dict[str, object]

    def content(self) -> bytes:
        """Validate fields used in logical identity and conservative asset names."""
        if (
            not VERSION.fullmatch('v' + self.version)
            or len(self.version) > EVENT_VERSION_MAX_LENGTH
            or (self.candidate is not None and not re.fullmatch(r'[0-9a-f]{64}', self.candidate))
            or not re.fullmatch(r'[0-9a-f]{40}', self.source)
            or any(not re.fullmatch(r'[1-9][0-9]*', item) for item in (self.run, self.attempt))
            or type(self.sequence) is not int
            or self.sequence < 1
            or self.sequence > EVENT_SEQUENCE_MAX
            or type(self.details) is not dict
            or not re.fullmatch(r'[a-z][a-z0-9-]{0,47}', self.kind)
            or (
                self.predecessor is not None and not re.fullmatch(r'[0-9a-f]{64}', self.predecessor)
            )
        ):
            raise ValueError('Invalid operational event identity')
        data = canonical({'schema': 'tarn-event-v1', 'repository': REPOSITORY, **asdict(self)})
        if len(data) > EVIDENCE_MAX_BYTES:
            raise ValueError('Operational event too large')
        return data

    @property
    def name(self) -> str:
        """Keep logical identity and content digest separately recognisable."""
        identity = {
            key: value
            for key, value in asdict(self).items()
            if key not in ('details', 'predecessor')
        }
        return f'event-{self.version}-{digest(canonical(identity))}-{digest(self.content())}.json'


@dataclass(frozen=True)
class Record:
    """Verified event with retained remote asset identity and content digest."""

    event: Event
    asset_id: int
    digest: str


@dataclass(frozen=True)
class RecoveryCopy:
    """Retain these identities in the administrative event before publication."""

    product: Draft
    candidate: str
    assets: dict[str, Asset]


class Storage:
    """Fail closed on lost identity or conflicting history; callers serialise runs."""

    def __init__(self, api: ReleaseAPI, administrative: Draft) -> None:
        self.api = api
        self.administrative = administrative
        if administrative.role != 'administrative':
            raise ValueError('Expected independent administrative storage')
        self.validate(administrative)

    def validate(self, expected: Draft) -> None:
        """Check retained ID, role, repository, privacy and duplicate tag identities."""
        if (
            type(expected.id) is not int
            or expected.id < 1
            or not re.fullmatch(r'[1-9][0-9]*', expected.repository_id)
            or not re.fullmatch(r'[0-9a-f]{40}', expected.target)
            or (expected.role == 'administrative' and expected.tag != 'release-records')
            or (expected.role == 'product' and not VERSION.fullmatch(expected.tag))
            or expected.role not in ('administrative', 'product')
            or self.api.repository_id() != expected.repository_id
        ):
            raise ValueError('Invalid storage role or repository identity')
        actual = self.api.release(expected.id)
        if actual != Release(expected.id, expected.tag, expected.target, expected.body, draft=True):
            raise ValueError('Storage identity changed or unexpectedly public')
        if self.api.tag_identity(expected.tag)[2] != expected.target:
            raise ValueError('Storage tag target changed')
        matching: list[int] = []
        seen: set[int] = set()
        page = 1
        while batch := self.api.releases_page(page):
            if any(item.id in seen for item in batch):
                raise ValueError('Repeated release page')
            seen.update(item.id for item in batch)
            matching.extend(item.id for item in batch if item.tag == expected.tag)
            page += 1
        if matching != [expected.id]:
            raise ValueError('Missing or duplicated storage identity')

    def assets(self, draft: Draft) -> list[Asset]:
        """Enumerate every page and reject duplicate names or IDs."""
        self.validate(draft)
        assets: list[Asset] = []
        page = 1
        while batch := self.api.assets_page(draft.id, page):
            if {item.id for item in assets} & {item.id for item in batch}:
                raise ValueError('Repeated asset page')
            assets.extend(batch)
            page += 1
        if len({item.id for item in assets}) != len(assets) or len(
            {item.name for item in assets},
        ) != len(assets):
            raise ValueError('Duplicated asset identity')
        return assets

    def read(self, draft: Draft, asset: Asset) -> bytes:
        """Verify ID-addressed metadata before and after authenticated download."""
        if (
            type(asset.id) is not int
            or asset.id < 1
            or asset.state != 'uploaded'
            or not 0 < asset.size <= ARCHIVE_MAX_BYTES
            or self.api.asset(asset.id) != asset
            or asset not in self.assets(draft)
        ):
            raise ValueError('Invalid retained asset metadata')
        data = self.api.download(asset.id)
        if len(data) != asset.size or self.api.asset(asset.id) != asset:
            raise ValueError('Retained asset changed during download')
        self.validate(draft)
        return data

    def history(self, version: str, expected_head: str | None = None) -> list[Record]:
        """Verify all versions; derive order from explicit chains, never list order."""
        if not VERSION.fullmatch('v' + version):
            raise ValueError('Invalid history version')
        chains: dict[str, list[Record]] = {}
        for asset in self.assets(self.administrative):
            data = self.read(self.administrative, asset)
            try:
                document = json.loads(data)
                fields = {
                    key: value
                    for key, value in document.items()
                    if key not in ('schema', 'repository')
                }
                event = Event(**fields)
                if data != event.content() or asset.name != event.name:
                    raise ValueError('Event bytes or identity differ')
            except (TypeError, KeyError, AttributeError) as error:
                raise ValueError('Malformed operational event') from error
            chains.setdefault(event.version, []).append(Record(event, asset.id, digest(data)))
        for records in chains.values():
            records.sort(key=lambda item: item.event.sequence)
            predecessor = None
            for sequence, record in enumerate(records, 1):
                if record.event.sequence != sequence or record.event.predecessor != predecessor:
                    raise ValueError('Conflicting or broken operational history')
                predecessor = record.digest
        selected = chains.get(version, [])
        if expected_head is not None and (not selected or selected[-1].digest != expected_head):
            raise ValueError('Retained history head missing or changed')
        return selected

    def put(self, draft: Draft, name: str, data: bytes) -> Asset:
        """Reconcile uncertain writes; never blindly retry or clobber originals."""

        def existing() -> Asset | None:
            matches = [asset for asset in self.assets(draft) if asset.name == name]
            if not matches:
                return None
            asset = matches[0]
            if self.read(draft, asset) != data:
                raise ValueError('Conflicting stored bytes')
            return asset

        found = existing()
        if found is not None:
            return found
        try:
            self.api.upload(draft.id, name, data)
        except (OSError, subprocess.SubprocessError):
            # A lost response may still have committed. A later explicit call rereads.
            found = existing()
            if found is None:
                raise
            return found
        found = existing()
        if found is None:
            raise ValueError('Write not visible; stop and reconcile on explicit retry')
        return found

    def append(self, event: Event) -> Record:
        """Append once, preserving every earlier transition and rejecting stale writers."""
        data = event.content()
        records = self.history(event.version)
        if event.sequence <= len(records):
            existing = records[event.sequence - 1]
            if existing.event.content() != data:
                raise ValueError('Conflicting logical event')
            return existing
        predecessor = records[-1].digest if records else None
        if event.sequence != len(records) + 1 or event.predecessor != predecessor:
            raise ValueError('Stale or broken operational predecessor')
        asset = self.put(self.administrative, event.name, data)
        records = self.history(event.version, digest(data))
        if records[-1].asset_id != asset.id:
            raise ValueError('Stored event identity changed')
        return records[-1]

    def product(self, draft: Draft, source: Mapping[str, object]) -> None:
        """Product storage may never alias the shared private record draft."""
        self.validate(self.administrative)
        if (
            draft.role != 'product'
            or draft.id == self.administrative.id
            or draft.repository_id != self.administrative.repository_id
            or source.get('repository') != REPOSITORY
            or draft.tag != source.get('tag')
            or draft.target != source.get('commit')
            or draft.tag != 'v' + str(source.get('version'))
        ):
            raise ValueError('Mismatched administrative or product identity')
        self.validate(draft)
        if 'tag_ref_target' in source and self.api.tag_identity(draft.tag) != (
            source['tag_ref_target'],
            source.get('tag_ref_type'),
            source.get('commit'),
        ):
            raise ValueError('Frozen product tag object changed')

    def retain(  # noqa: PLR0917 - Separate originals, source, product and attempt trust boundaries.
        self,
        product: Draft,
        source: Mapping[str, object],
        manifest: bytes,
        candidate: str,
        files: Path,
        event: Event,
    ) -> RecoveryCopy:
        """Verify originals, store without replacement, then independently recover."""
        self.product(product, source)
        if (
            event.version != source.get('version')
            or event.candidate != candidate
            or event.source != source.get('commit')
            or event.kind != 'recovery-stored'
            or event.details
        ):
            raise ValueError('Recovery event differs from original candidate')
        event.content()
        verify_candidate(manifest, candidate, source, files)
        names = (*archive_names(source), 'sdist.sigstore.json', 'wheel.sigstore.json')
        # Only these five public-safe assets may enter product storage.
        expected = {
            'candidate.json': manifest,
            **{name: (files / name).read_bytes() for name in names},
        }
        if any(asset.name not in expected for asset in self.assets(product)):
            raise ValueError('Unexpected product recovery asset')
        assets = {name: self.put(product, name, data) for name, data in expected.items()}
        retained = RecoveryCopy(product, candidate, assets)
        with TemporaryDirectory() as directory:
            self.recover(retained, source, Path(directory) / 'read-back')
        self.append(
            Event(
                event.version,
                event.candidate,
                event.source,
                event.run,
                event.attempt,
                event.sequence,
                event.kind,
                event.predecessor,
                {'recovery': asdict(retained)},
            ),
        )
        return retained

    def recover(self, retained: RecoveryCopy, source: Mapping[str, object], output: Path) -> None:
        """Retrieve original IDs and signatures; no build or evidence regeneration."""
        self.product(retained.product, source)
        names = {*archive_names(source), 'sdist.sigstore.json', 'wheel.sigstore.json'}
        if set(retained.assets) != names | {'candidate.json'}:
            raise ValueError('Missing retained original identities')
        actual = {asset.name: asset for asset in self.assets(retained.product)}
        if actual != retained.assets:
            raise ValueError('Recovery asset identities differ')
        downloaded = {name: self.read(retained.product, asset) for name, asset in actual.items()}
        # Incomplete local directories are never offered as verified recovery output.
        with TemporaryDirectory() as directory:
            staging = Path(directory)
            for name in names:
                (staging / name).write_bytes(downloaded[name])
            verify_candidate(downloaded['candidate.json'], retained.candidate, source, staging)
        self.product(retained.product, source)
        output.mkdir()
        (output / 'candidate.json').write_bytes(downloaded['candidate.json'])
        (output / 'files').mkdir()
        for name in names:
            (output / 'files' / name).write_bytes(downloaded[name])
