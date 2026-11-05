#!/usr/bin/env python3
# Copyright 2026 Axel Voitier
# ruff: noqa: EXE001, EM101, TRY003
"""Advance retained originals through a controlled TestPyPI destination."""

import base64
import json
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Protocol, cast

from release.candidate import EVIDENCE_MAX_BYTES, archive_names, canonical, verify_candidate
from release.reconciliation import (
    UNCERTAINTY_SECONDS,
    Destination,
    Outcome,
    Publisher,
    PublishingVerifier,
    Reconciler,
    RemoteFile,
    check_publication,
)
from release.sdist import COORDINATOR, REPOSITORY
from release.storage_api import document, text


def publish(
    reconciler: Reconciler,
    destination: Destination,
    publisher: Publisher,
    output: Path,
) -> Outcome:
    """Retrieve and verify selected registry bytes before offering them to package jobs.

    The caller enforces coordinator admission and supplies a trusted adapter.
    There is no live upload adapter in this local implementation.
    """
    expected = Publisher(
        REPOSITORY,
        Path(COORDINATOR).name,
        str(reconciler.source['commit']),
        'testpypi',
    )
    if publisher != expected:
        raise ValueError('TestPyPI requires the frozen coordinator and dedicated environment')
    if output.exists():
        raise ValueError('Retrieved candidate output must be a fresh directory')
    deadline = reconciler.clock.monotonic() + UNCERTAINTY_SECONDS
    result = reconciler.reconcile({'testpypi': destination}, {'testpypi': publisher})
    if result.status != 'complete':
        return result
    try:
        return retrieve(reconciler, destination, publisher, output, deadline)
    except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError):
        reason = (
            'Final TestPyPI retrieval incomplete; verify originals '
            'and destination state, then retry'
        )
        reconciler.record('testpypi-incomplete', {'reason': reason})
        return Outcome('incomplete', reason)


def retrieve(
    reconciler: Reconciler,
    destination: Destination,
    publisher: Publisher,
    output: Path,
    deadline: float,
    *,
    target: str = 'testpypi',
) -> Outcome:
    """Export only a freshly verified snapshot; conflicting or delayed retrieval stops."""
    with TemporaryDirectory(dir=output.parent) as directory:
        staging = Path(directory)
        originals = staging / 'originals'
        reconciler.storage.recover(reconciler.retained, reconciler.source, originals)
        _summary, snapshots = reconciler.observe(
            {target: destination},
            {target: publisher},
            originals / 'files',
            deadline,
        )
        snapshot = snapshots.get(target, {})
        names = archive_names(reconciler.source)
        if set(snapshot) != set(names) or any(
            any(item is None for item in (remote.archive, remote.build, remote.publish))
            for remote in snapshot.values()
        ):
            raise ValueError('Registry retrieval became unavailable')
        selected = staging / 'selected'
        (selected / 'files').mkdir(parents=True)
        (selected / 'publishing').mkdir()
        manifest = (originals / 'candidate.json').read_bytes()
        (selected / 'candidate.json').write_bytes(manifest)
        # Retain the original build bundles for canonical manifest verification.
        # Retrieved build evidence was independently checked above and is kept separately.
        (selected / 'retrieved-build').mkdir()
        for name, remote in snapshot.items():
            if remote.archive is None or remote.build is None or remote.publish is None:
                raise ValueError('Missing retrieved evidence')
            kind = 'sdist' if name.endswith('.tar.gz') else 'wheel'
            (selected / 'files' / name).write_bytes(remote.archive)
            (selected / 'files' / f'{kind}.sigstore.json').write_bytes(
                (originals / 'files' / f'{kind}.sigstore.json').read_bytes(),
            )
            (selected / 'retrieved-build' / f'{kind}.sigstore.json').write_bytes(remote.build)
            (selected / 'publishing' / (name + '.json')).write_bytes(remote.publish)
        verify_candidate(
            manifest,
            reconciler.retained.candidate,
            reconciler.source,
            selected / 'files',
        )
        if output.exists():
            raise ValueError('Retrieved output appeared during selection')
        reconciler.record(target + '-retrieved', {'candidate': reconciler.retained.candidate})
        selected.rename(output)
    return Outcome(
        'complete',
        f'{target} bytes and both evidence types retrieved and verified',
    )


def attestation(bundle: bytes, predicate: str) -> dict[str, object]:
    """Convert a verified v0.3 Sigstore bundle without reserialising signed bytes.

    This is envelope conversion only. Signature and identity verification must
    precede it. Unknown formats stop for review rather than dropping material.
    """
    if not 0 < len(bundle) <= EVIDENCE_MAX_BYTES:
        raise ValueError('Attestation bundle exceeds supported bounds')
    value = document(json.loads(bundle))
    if value.get('mediaType') != 'application/vnd.dev.sigstore.bundle.v0.3+json':
        raise ValueError('Unsupported Sigstore envelope version')
    envelope = document(value['dsseEnvelope'])
    if envelope.get('payloadType') != 'application/vnd.in-toto+json':
        raise ValueError('Unexpected signed payload type')
    payload = text(envelope['payload'])
    if (
        document(json.loads(base64.b64decode(payload, validate=True))).get('predicateType')
        != predicate
    ):
        raise ValueError('Unexpected attestation predicate')
    signatures = envelope['signatures']
    if not isinstance(signatures, list) or len(cast('list[object]', signatures)) != 1:
        raise ValueError('Expected exactly one original signature')
    signature = text(document(cast('list[object]', signatures)[0])['sig'])
    if not base64.b64decode(signature, validate=True):
        raise ValueError('Empty signature')
    material = document(value['verificationMaterial'])
    # Refuse timestamp-only or future material rather than silently discarding it.
    if set(material) != {'certificate', 'tlogEntries'}:
        raise ValueError('Unsupported verification material')
    certificate = text(document(material['certificate'])['rawBytes'])
    entries = material['tlogEntries']
    if not isinstance(entries, list) or not entries:
        raise ValueError('Transparency entries must be a nonempty list')
    if not base64.b64decode(certificate, validate=True):
        raise ValueError('Certificate and transparency evidence required')
    return {
        'version': 1,
        'verification_material': {
            'certificate': certificate,
            'transparency_entries': material['tlogEntries'],
        },
        'envelope': {'statement': payload, 'signature': signature},
    }


def upload_attestations(build: bytes, publishing: bytes) -> bytes:
    """Attach both evidence types to the initial per-file upload."""
    return canonical(
        [
            attestation(build, 'https://slsa.dev/provenance/v1'),
            attestation(publishing, 'https://docs.pypi.org/attestations/publish/v1'),
        ],
    )


class PublishingSigner(Protocol):
    """Trusted signing boundary: no package execution or caller-supplied predicate."""

    def sign(self, name: str, archive: bytes, deadline: float) -> bytes: ...


class UploadTransport(Protocol):
    """Controlled upload boundary receives both attestations in one request."""

    def observe(self, deadline: float) -> Mapping[str, RemoteFile]: ...
    def upload(self, name: str, archive: bytes, attestations: bytes, deadline: float) -> None: ...


@dataclass(frozen=True)
class PreparedDestination:
    """Prepare both attestations before sending any archive bytes to the transport."""

    transport: UploadTransport
    signer: PublishingSigner
    verifier: PublishingVerifier
    publisher: Publisher

    def observe(self, deadline: float) -> Mapping[str, RemoteFile]:
        """The transport retrieves actual archive bytes and both evidence types."""
        return self.transport.observe(deadline)

    def upload(self, name: str, archive: bytes, build: bytes, deadline: float) -> None:
        """Preserve original build evidence; sign only the fixed publishing statement."""
        publishing = self.signer.sign(name, archive, deadline)
        check_publication(self.verifier.verify(publishing, deadline), self.publisher, name, archive)
        evidence = upload_attestations(build, publishing)
        self.transport.upload(name, archive, evidence, deadline)
