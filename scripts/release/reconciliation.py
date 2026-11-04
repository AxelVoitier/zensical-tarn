#!/usr/bin/env python3
# Copyright 2026 Axel Voitier
# ruff: noqa: EXE001, EM101, TRY003
"""Reconcile original archives through trusted, deadline-aware destination adapters."""

import subprocess
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Protocol, cast

from release.candidate import archive_names
from release.sdist import verified_statement
from release.storage import Event, RecoveryCopy, Storage, digest
from release.storage_api import document

UNCERTAINTY_SECONDS = 900
POLL_SECONDS = 30


class ReconciliationError(ValueError):
    """A screened recovery explanation, safe to retain in private history."""


@dataclass(frozen=True)
class Publisher:
    """Expected certificate identity from reviewed, destination-specific policy."""

    repository: str
    workflow: str
    revision: str
    environment: str


@dataclass(frozen=True)
class Publication:
    """Cryptographically verified statement and certificate identity, never raw claims."""

    publisher: Publisher
    statement: object


class PublishingVerifier(Protocol):
    """Trusted signature, certificate and transparency-log verifier boundary."""

    def verify(self, bundle: bytes, deadline: float) -> Publication: ...


@dataclass(frozen=True)
class RemoteFile:
    """Downloaded bytes; None denotes delayed bytes or evidence, not invalid evidence."""

    archive: bytes | None
    build: bytes | None
    publish: bytes | None


class Destination(Protocol):
    """Return a complete version listing; absence requires a successful authoritative read.

    Adapters must enforce the monotonic deadline on every request and transfer.
    Transient failures raise OSError; malformed/conflicting state raises ValueError.
    Upload attaches the original build bundle and generates separate publish evidence.
    No overwrite, evidence repair or rebuild operation is available.
    """

    def observe(self, deadline: float) -> Mapping[str, RemoteFile]: ...
    def upload(self, name: str, archive: bytes, build: bytes, deadline: float) -> None: ...


class Clock(Protocol):
    """Monotonic time and bounded waiting, replaceable for local simulations."""

    def monotonic(self) -> float: ...
    def sleep(self, seconds: float) -> None: ...


@dataclass(frozen=True)
class Outcome:
    """Completion refers only to the explicitly selected destinations."""

    status: str
    reason: str


@dataclass
class Reconciler:
    """One serial attempt against a retained history head; no live adapters supplied."""

    storage: Storage
    retained: RecoveryCopy
    source: Mapping[str, object]
    run: str
    attempt: str
    head: str
    verifier: PublishingVerifier
    clock: Clock

    def record(self, kind: str, details: dict[str, object]) -> None:
        """Preserve the retained chain and reject a newer or outside writer."""
        records = self.storage.history(str(self.source['version']), self.head)
        self.storage.product(self.retained.product, self.source)
        event = Event(
            str(self.source['version']),
            self.retained.candidate,
            str(self.source['commit']),
            self.run,
            self.attempt,
            len(records) + 1,
            kind,
            self.head,
            details,
        )
        self.head = self.storage.append(event).digest

    def remaining(self, deadline: float) -> float:
        """Never start another evidence operation after the observation window."""
        seconds = deadline - self.clock.monotonic()
        if seconds <= 0:
            raise ReconciliationError('Uncertainty reached 15 minutes; explicitly retry')
        return seconds

    def check_file(
        self,
        name: str,
        remote: RemoteFile,
        files: Path,
        publisher: Publisher,
        deadline: float,
    ) -> str:
        """Validate every available component, even while another remains delayed."""
        original = (files / name).read_bytes()
        kind = 'sdist' if name.endswith('.tar.gz') else 'wheel'
        if remote.archive is not None and remote.archive != original:
            raise ReconciliationError(
                'Conflicting archive bytes; stop recovery and use a new version',
            )
        if remote.build is not None:
            bundle = files.parent / 'remote-build.json'
            bundle.write_bytes(remote.build)
            expected = verified_statement(
                files / name,
                files / f'{kind}.sigstore.json',
                self.source,
                timeout=self.remaining(deadline),
            )
            if (
                verified_statement(
                    files / name,
                    bundle,
                    self.source,
                    timeout=self.remaining(deadline),
                )
                != expected
            ):
                raise ReconciliationError('Build evidence differs from original signed statement')
        if remote.publish is not None:
            self.remaining(deadline)
            publication = self.verifier.verify(remote.publish, deadline)
            self.remaining(deadline)
            payload = document(publication.statement)
            if (
                publication.publisher != publisher
                or payload.get('_type') != 'https://in-toto.io/Statement/v1'
                or payload.get('subject')
                != [{'name': name, 'digest': {'sha256': digest(original)}}]
                or payload.get('predicateType') != 'https://docs.pypi.org/attestations/publish/v1'
                or payload.get('predicate') not in ({}, None)
            ):
                raise ReconciliationError(
                    'Unexpected publishing identity or signed publication subject',
                )
        return (
            'verified'
            if all(item is not None for item in (remote.archive, remote.build, remote.publish))
            else 'uncertain'
        )

    def observe(
        self,
        destinations: Mapping[str, Destination],
        publishers: Mapping[str, Publisher],
        files: Path,
        deadline: float,
    ) -> tuple[dict[str, object], dict[str, Mapping[str, RemoteFile]]]:
        """Keep screened per-component digests and validate monotonic observations."""
        summary: dict[str, object] = {}
        snapshots: dict[str, Mapping[str, RemoteFile]] = {}
        names = archive_names(self.source)
        for target, destination in destinations.items():
            try:
                snapshot = dict(destination.observe(deadline))
            except OSError:
                summary[target] = {'status': 'unavailable'}
                continue
            if set(snapshot) - set(names):
                raise ReconciliationError(
                    'Unexpected destination file; outside writer changed the release',
                )
            snapshots[target] = snapshot
            observed: dict[str, object] = {}
            for name in names:
                remote = snapshot.get(name)
                observed[name] = (
                    {'status': 'missing'}
                    if remote is None
                    else {
                        'status': self.check_file(
                            name,
                            remote,
                            files,
                            publishers[target],
                            deadline,
                        ),
                        **{
                            key: digest(data) if data is not None else None
                            for key, data in asdict(remote).items()
                        },
                    }
                )
            summary[target] = observed
        records = self.storage.history(str(self.source['version']), self.head)
        for record in records:
            if record.event.candidate != self.retained.candidate:
                continue
            if record.event.kind != 'destination-observed':
                continue
            previous = cast(
                'dict[str, dict[str, dict[str, object]]]',
                record.event.details['files'],
            )
            for target, snapshot in snapshots.items():
                for name in names:
                    old = previous.get(target, {}).get(name, {})
                    new = cast('dict[str, dict[str, object]]', summary[target])[name]
                    if old.get('status') in ('verified', 'uncertain') and name not in snapshot:
                        raise ReconciliationError(
                            'Previously observed file disappeared; outside writer change',
                        )
                    for component in ('archive', 'build', 'publish'):
                        if old.get(component) is not None and old[component] != new.get(component):
                            raise ReconciliationError(
                                'Previously observed bytes or evidence changed',
                            )
        self.record('destination-observed', {'files': summary})
        return summary, snapshots

    def check_policy(
        self,
        destinations: Mapping[str, Destination],
        publishers: Mapping[str, Publisher],
    ) -> None:
        """A later attempt cannot accept a different publishing identity as a repair."""
        if (
            not destinations
            or set(destinations) != set(publishers)
            or set(destinations) - {'testpypi', 'pypi', 'github'}
        ):
            raise ReconciliationError('Explicit destination and publishing policies required')
        selected = {target: asdict(publisher) for target, publisher in publishers.items()}
        records = self.storage.history(str(self.source['version']), self.head)
        for record in records:
            if (
                record.event.kind != 'reconciliation-started'
                or record.event.candidate != self.retained.candidate
            ):
                continue
            previous = document(record.event.details['publishers'])
            for target, publisher in selected.items():
                if target in previous and previous[target] != publisher:
                    raise ReconciliationError('Publishing policy changed during recovery')
        self.record('reconciliation-started', {'publishers': selected})

    def reconcile(
        self,
        destinations: Mapping[str, Destination],
        publishers: Mapping[str, Publisher],
    ) -> Outcome:
        """Advance only missing originals; uncertainty never permits duplicate submission."""
        try:
            self.check_policy(destinations, publishers)
            with TemporaryDirectory() as directory:
                recovered = Path(directory) / 'originals'
                self.storage.recover(self.retained, self.source, recovered)
                deadline = self.clock.monotonic() + UNCERTAINTY_SECONDS
                return self.advance(destinations, publishers, recovered / 'files', deadline)
        except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError) as error:
            reason = (
                str(error)
                if isinstance(error, ReconciliationError)
                else 'Recovery blocked; verify originals, signatures and destination responses.'
            ) + ' '
            reason += 'No replacement build or evidence bypass; a fresh build needs a new version.'
            # Never include raw transport errors, which may contain credentials.
            self.record('reconciliation-finished', {'status': 'incomplete', 'reason': reason})
            return Outcome('incomplete', reason)

    def advance(
        self,
        destinations: Mapping[str, Destination],
        publishers: Mapping[str, Publisher],
        files: Path,
        deadline: float,
    ) -> Outcome:
        """Record intent durably before a write, including cancellation/lost responses."""
        records = self.storage.history(str(self.source['version']), self.head)
        attempted: set[tuple[str, str]] = set()
        for record in records:
            if record.event.candidate != self.retained.candidate:
                continue
            details = record.event.details
            if record.event.kind == 'upload-started':
                attempted.add((str(details['destination']), str(details['file'])))
            elif record.event.kind == 'upload-outcome' and details['outcome'] == 'not-sent':
                attempted.discard((str(details['destination']), str(details['file'])))
        while True:
            summary, snapshots = self.observe(destinations, publishers, files, deadline)
            complete = all(
                all(
                    value.get('status') == 'verified'
                    for value in cast('dict[str, dict[str, object]]', summary[target]).values()
                )
                for target in destinations
                if target in snapshots
            ) and len(snapshots) == len(destinations)
            if complete and self.clock.monotonic() <= deadline:
                self.record(
                    'reconciliation-finished',
                    {'status': 'complete', 'destinations': summary},
                )
                return Outcome(
                    'complete',
                    'Selected destination files and both evidence types verified',
                )
            if self.clock.monotonic() >= deadline:
                self.record(
                    'reconciliation-finished',
                    {
                        'status': 'incomplete',
                        'reason': 'Uncertainty reached 15 minutes; explicitly retry. '
                        'Missing evidence cannot be repaired by duplicate upload; '
                        'a fresh build needs a new version.',
                    },
                )
                return Outcome('incomplete', 'Uncertainty reached 15 minutes; explicitly retry')
            missing = next(
                (
                    (target, name)
                    for target in destinations
                    for name in archive_names(self.source)
                    if target in snapshots
                    and name not in snapshots[target]
                    and (target, name) not in attempted
                ),
                None,
            )
            if missing is None:
                self.clock.sleep(min(POLL_SECONDS, deadline - self.clock.monotonic()))
                continue
            target, name = missing
            self.record(
                'upload-started',
                {'destination': target, 'file': name, 'publisher': asdict(publishers[target])},
            )
            attempted.add(missing)
            # Re-read after writing intent: the shared queue does not exclude outsiders.
            _summary, fresh = self.observe(destinations, publishers, files, deadline)
            if target not in fresh or name in fresh[target] or self.clock.monotonic() >= deadline:
                self.record(
                    'upload-outcome',
                    {'destination': target, 'file': name, 'outcome': 'not-sent'},
                )
                attempted.discard(missing)
                self.clock.sleep(max(0, min(POLL_SECONDS, deadline - self.clock.monotonic())))
                continue
            kind = 'sdist' if name.endswith('.tar.gz') else 'wheel'
            outcome = 'returned'
            try:
                destinations[target].upload(
                    name,
                    (files / name).read_bytes(),
                    (files / f'{kind}.sigstore.json').read_bytes(),
                    deadline,
                )
            except (OSError, subprocess.SubprocessError):
                outcome = 'uncertain'
            self.record('upload-outcome', {'destination': target, 'file': name, 'outcome': outcome})
