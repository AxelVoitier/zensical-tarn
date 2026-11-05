#!/usr/bin/env python3
# Copyright 2026 Axel Voitier
# ruff: noqa: EXE001, EM101, TRY003, TRY301
"""Finalise unchanged approved contents through a controlled GitHub boundary.

No live release-write adapter is supplied. Callers enforce serial admission and
provide authenticated source and destination observations.
"""

import json
import re
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Protocol, cast

from release.approval import REPORT_FORMAT, ReviewMaterial, changelog_section, publisher
from release.candidate import archive_names, canonical
from release.reconciliation import UNCERTAINTY_SECONDS, Destination, Outcome, Reconciler
from release.storage import Event, Release, digest
from release.storage_api import document


@dataclass(frozen=True)
class PublicRelease:
    """Complete ID-addressed release read-back, including actual downloaded assets."""

    release: Release
    prerelease: bool
    make_latest: str
    assets: Mapping[str, bytes]


class GitHubDestination(Protocol):
    """Bound to the retained product ID; enforce deadlines, pagination and no replacement.

    Observe must reject duplicate names/IDs and incomplete asset downloads.
    Publish changes only notes, draft, prerelease and latest settings, never tags.
    Unsupported attachments or immutable-release changes raise ValueError.
    """

    def observe(self, deadline: float) -> PublicRelease: ...
    def attach(self, name: str, data: bytes, deadline: float) -> None: ...
    def publish(
        self, notes: str, *, prerelease: bool, make_latest: str, deadline: float
    ) -> None: ...


def approved_review(reconciler: Reconciler, summary: bytes) -> dict[str, object]:
    """Require the original retained review, authenticated approval and verified production."""
    records = reconciler.storage.history(str(reconciler.source['version']), reconciler.head)
    review = document(json.loads(summary))
    summary_digest = digest(summary)
    matching = [
        record.event
        for record in records
        if record.event.candidate == reconciler.retained.candidate
        and record.event.source == reconciler.source['commit']
    ]
    reviewed = [
        event
        for event in matching
        if event.kind == 'review-prepared'
        and event.details == {'summary': review, 'digest': summary_digest}
    ]
    if len(reviewed) != 1:
        raise ValueError('Original approved review required')
    execution = {'run': reviewed[0].run, 'attempt': reviewed[0].attempt}
    for kind in ('production-approved', 'production-verified'):
        if not any(
            event.kind == kind
            and event.details.get('summary_digest') == summary_digest
            and {'run': event.run, 'attempt': event.attempt} == execution
            and event.sequence > reviewed[0].sequence
            for event in matching
        ):
            raise ValueError('Approved and verified production required')
    if (
        canonical(review) != summary
        or review.get('candidate') != reconciler.retained.candidate
        or review.get('recovery') != asdict(reconciler.retained)
        or document(review.get('manifest')).get('source') != dict(reconciler.source)
        or review.get('report_format') != REPORT_FORMAT
    ):
        raise ValueError('Approved candidate or report format changed')
    return review


def screen_public(value: object) -> None:
    """Reject known private fields and credential forms in approved public text/JSON.

    This supplements typed report projection. Trusted adapters still screen
    evidence formats; a text pattern cannot establish arbitrary data is public.
    """
    if isinstance(value, dict):
        for key, item in cast('dict[str, object]', value).items():
            normalised = re.sub(r'[^a-z]', '', key.lower())
            if normalised in {
                'approval',
                'privateapproval',
                'approvaldetails',
                'credentials',
                'credential',
                'token',
                'password',
                'secret',
                'rawlogs',
                'rawlog',
                'logs',
                'stdout',
                'stderr',
                'authorization',
                'debug',
            }:
                raise ValueError('Private fields cannot enter public release contents')
            screen_public(item)
    elif isinstance(value, list):
        for item in cast('list[object]', value):
            screen_public(item)
    elif isinstance(value, str) and re.search(
        r'(?:gh[pousr]_[A-Za-z0-9]+|github_pat_[A-Za-z0-9_]+|pypi-[A-Za-z0-9_-]{16,}'
        r'|Authorization:\s*(?:Bearer|Basic)\s+\S+)',
        value,
        re.IGNORECASE,
    ):
        raise ValueError('Credential-shaped text cannot enter public release contents')


def public_assets(
    reconciler: Reconciler,
    review: dict[str, object],
    pypi: Destination,
    originals: Path,
    deadline: float,
) -> dict[str, bytes]:
    """Reverify production; project safe fields rather than serialising private records."""
    observations, snapshots = reconciler.observe(
        {'pypi': pypi},
        {'pypi': publisher(reconciler, 'pypi')},
        originals / 'files',
        deadline,
        retain_observation=False,
    )
    names = archive_names(reconciler.source)
    production = document(observations['pypi'])
    if any(document(production.get(name)).get('status') != 'verified' for name in names):
        raise ValueError('Complete current PyPI bytes and evidence required')
    assets = {path.name: path.read_bytes() for path in (originals / 'files').iterdir()}
    assets['candidate.json'] = (originals / 'candidate.json').read_bytes()
    for name in names:
        evidence = snapshots['pypi'][name].publish
        if evidence is None:
            raise ValueError('Missing publishing evidence')
        assets[name + '.publish.json'] = evidence
    assets['SHA256SUMS'] = ''.join(
        f'{digest(assets[name])}  {name}\n' for name in sorted(names)
    ).encode()
    manifest = document(review['manifest'])
    report = {
        'schema': REPORT_FORMAT['schema'],
        'source': dict(reconciler.source),
        'archives': {
            name: {**document(metadata), 'pypi_verification': 'pass'}
            for name, metadata in document(manifest['archives']).items()
        },
        'build_evidence': manifest['evidence'],
        'publishing_evidence': {
            name: {'file': name + '.publish.json', 'sha256': digest(assets[name + '.publish.json'])}
            for name in names
        },
        'checks': {
            name: {
                key: document(check)[key] for key in ('status', 'run', 'attempt', 'evidence_digest')
            }
            for name, check in document(review['checks']).items()
        },
        'attempts': [
            {'run': record.event.run, 'attempt': record.event.attempt, 'result': record.event.kind}
            for record in reconciler.storage.history(
                str(reconciler.source['version']), reconciler.head
            )
            if record.event.kind
            in (
                'production-verified',
                'production-incomplete',
                'github-incomplete',
                'testpypi-retrieved',
                'pypi-retrieved',
            )
            and record.event.candidate == reconciler.retained.candidate
        ],
    }
    plan = reconciler.storage.finalisation_plan(reconciler.retained.product)
    if plan is not None:
        saved = document(plan['report'])
        if {key: value for key, value in saved.items() if key != 'attempts'} != {
            key: value for key, value in report.items() if key != 'attempts'
        }:
            raise ValueError('Verified public results changed')
        report = saved
    assets['verification-report.json'] = canonical(report)
    if sorted(assets) != review['assets']:
        raise ValueError('Public asset set differs from approved set')
    screen_public(review['notes'])
    for name, data in assets.items():
        if name.endswith('.json'):
            screen_public(json.loads(data))
    return assets


def inspect_release(
    reconciler: Reconciler,
    github: GitHubDestination,
    review: dict[str, object],
    assets: Mapping[str, bytes],
    deadline: float,
) -> PublicRelease:
    """Reject outside content or identity changes before any repair or publication."""
    reconciler.remaining(deadline)
    reconciler.storage.product(reconciler.retained.product, reconciler.source)
    observed = github.observe(deadline)
    reconciler.remaining(deadline)
    product = reconciler.retained.product
    release = observed.release
    if (
        (release.id, release.tag, release.target) != (product.id, product.tag, product.target)
        or release.body not in (product.body, review['notes'])
        or (not release.draft and release.body != review['notes'])
        or set(observed.assets) - set(assets)
        or any(data != assets[name] for name, data in observed.assets.items())
        or (
            not release.draft
            and (
                observed.prerelease != review['prerelease']
                or observed.make_latest != review['make_latest']
            )
        )
    ):
        raise ValueError('Conflicting public release identity, contents or settings')
    return observed


def finalise(
    reconciler: Reconciler,
    pypi: Destination,
    read: Callable[[], ReviewMaterial],
    summary: bytes,
    github: GitHubDestination,
) -> Outcome:
    """Publish or deliberately recover unchanged GitHub contents without another PyPI approval."""
    try:
        deadline = reconciler.clock.monotonic() + UNCERTAINTY_SECONDS
        review = approved_review(reconciler, summary)
        material = read()
        if (
            dict(material.source) != dict(reconciler.source)
            or changelog_section(material.changelog, str(reconciler.source['version']))
            != review['changelog']
        ):
            raise ValueError('Approved source or notes changed')
        with TemporaryDirectory() as directory:
            originals = Path(directory) / 'originals'
            reconciler.storage.recover(reconciler.retained, reconciler.source, originals)
            assets = public_assets(reconciler, review, pypi, originals, deadline)
            observed = inspect_release(reconciler, github, review, assets, deadline)
            plan = {
                'product_id': reconciler.retained.product.id,
                'candidate': reconciler.retained.candidate,
                'summary_digest': digest(summary),
                'notes': review['notes'],
                'prerelease': review['prerelease'],
                'make_latest': review['make_latest'],
                'assets': {name: digest(data) for name, data in assets.items()},
                'report': json.loads(assets['verification-report.json']),
            }
            previous = reconciler.storage.finalisation_plan(reconciler.retained.product)
            if previous is None:
                reconciler.record('github-prepared', plan)
            elif previous != plan:
                raise ValueError('Original public finalisation plan changed')
            for name, data in assets.items():
                observed = inspect_release(reconciler, github, review, assets, deadline)
                if name not in observed.assets:
                    github.attach(name, data, deadline)
            observed = inspect_release(reconciler, github, review, assets, deadline)
            if set(observed.assets) != set(assets) or read() != material:
                raise ValueError('Public assets incomplete or source changed')
            if observed.release.draft:
                github.publish(
                    str(review['notes']),
                    prerelease=bool(review['prerelease']),
                    make_latest=str(review['make_latest']),
                    deadline=deadline,
                )
            observed = inspect_release(reconciler, github, review, assets, deadline)
            if observed.release.draft or dict(observed.assets) != assets or read() != material:
                raise ValueError('Final GitHub read-back incomplete')
            reconciler.record(
                'github-complete',
                {'product_id': observed.release.id, 'summary_digest': digest(summary)},
            )
        return Outcome('complete', 'PyPI and public GitHub contents verified')
    except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError):
        # Preserve screened failures even when product state itself is conflicting.
        try:
            records = reconciler.storage.history(str(reconciler.source['version']), reconciler.head)
            event = Event(
                str(reconciler.source['version']),
                reconciler.retained.candidate,
                str(reconciler.source['commit']),
                reconciler.run,
                reconciler.attempt,
                len(records) + 1,
                'github-incomplete',
                reconciler.head,
                {'reason': 'Public finalisation or unchanged recovery could not be verified'},
            )
            reconciler.head = reconciler.storage.append(event).digest
        except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError):
            return Outcome(
                'incomplete',
                'GitHub finalisation and private failure retention unverified. '
                'Inspect retained history.',
            )
        return Outcome(
            'incomplete',
            'GitHub finalisation blocked. Inspect private state and '
            'deliberately retry unchanged contents',
        )
