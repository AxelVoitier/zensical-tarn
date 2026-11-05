#!/usr/bin/env python3
# Copyright 2026 Axel Voitier
# ruff: noqa: EXE001, EM101, TRY003
"""Bind local production authorisation to one reviewed candidate and execution.

No live approval or registry adapters are provided. Check receipts and source
reads must come from trusted orchestration, never from package-provided claims.
"""

import json
import re
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from release.candidate import archive_names, canonical
from release.reconciliation import UNCERTAINTY_SECONDS, Destination, Outcome, Publisher, Reconciler
from release.sdist import COORDINATOR, REPOSITORY
from release.storage import digest
from release.storage_api import document
from release.testpypi import retrieve

REQUIRED_CHECKS = {'preparation', 'reproducibility', 'archive-checks', 'testpypi-installation'}
REPORT_FORMAT = {
    'schema': 'tarn-public-verification-v1',
    'fields': ['source', 'archives', 'build_evidence', 'publishing_evidence', 'checks', 'attempts'],
    'production_results': 'pending; fill only from verified PyPI retrieval',
}


@dataclass(frozen=True)
class CheckResult:
    """Trusted unprivileged-job receipt, bound to candidate and frozen source."""

    candidate: str
    source_digest: str
    run: str
    attempt: str
    status: str
    evidence_digest: str


@dataclass(frozen=True)
class ReviewMaterial:
    """Fresh remote-tag identity, frozen changelog and authenticated check receipts."""

    source: Mapping[str, object]
    changelog: str
    checks: Mapping[str, CheckResult]


def changelog_section(changelog: str, version: str) -> str:
    """Select one complete version section, rejecting absent, empty or duplicate entries."""
    headings = list(re.finditer(r'^##\s+(.+)$', changelog, re.MULTILINE))
    selected = [
        index
        for index, match in enumerate(headings)
        if re.fullmatch(
            rf'(?:\[{re.escape(version)}\]|{re.escape(version)})(?:\s+-\s+\d{{4}}-\d{{2}}-\d{{2}})?',
            match[1],
        )
    ]
    mentions = [
        match
        for match in headings
        if re.match(
            rf'(?:\[{re.escape(version)}\]|{re.escape(version)})(?:\s|$)',
            match[1],
        )
    ]
    if len(selected) != 1 or len(mentions) != 1:
        raise ValueError('Missing or ambiguous tagged-version changelog')
    index = selected[0]
    end = headings[index + 1].start() if index + 1 < len(headings) else len(changelog)
    section = changelog[headings[index].end() : end].strip()
    if not section:
        raise ValueError('Empty tagged-version changelog')
    return section


def publisher(reconciler: Reconciler, target: str) -> Publisher:
    """Use the original coordinator revision and destination-specific identity."""
    return Publisher(REPOSITORY, Path(COORDINATOR).name, str(reconciler.source['commit']), target)


def review_snapshot(
    reconciler: Reconciler,
    testpypi: Destination,
    pypi: Destination,
    read: Callable[[], ReviewMaterial],
    history_head: str,
) -> bytes:
    """Re-read every prerequisite without advancing history or writing destinations."""
    material = read()
    source = dict(reconciler.source)
    if dict(material.source) != source:
        raise ValueError('Remote tag or frozen source/workflow changed')
    if set(material.checks) != REQUIRED_CHECKS:
        raise ValueError('Missing or unrecognised prerequisite checks')
    for check in material.checks.values():
        if (
            check.candidate != reconciler.retained.candidate
            or check.source_digest != digest(canonical(source))
            or check.status != 'pass'
            or not re.fullmatch(r'[0-9a-f]{64}', check.evidence_digest)
            or not re.fullmatch(r'[1-9][0-9]*', check.run)
            or not re.fullmatch(r'[1-9][0-9]*', check.attempt)
        ):
            raise ValueError('Invalid prerequisite check receipt')
    records = reconciler.storage.history(str(source['version']), reconciler.head)
    if not any(
        record.event.kind == 'testpypi-retrieved'
        and record.event.candidate == reconciler.retained.candidate
        for record in records
    ):
        raise ValueError('Verified TestPyPI retrieval required before review')
    notes = changelog_section(material.changelog, str(source['version']))
    with TemporaryDirectory() as directory:
        originals = Path(directory) / 'originals'
        reconciler.storage.recover(reconciler.retained, source, originals)
        manifest = document(json.loads((originals / 'candidate.json').read_bytes()))
        observations, _snapshots = reconciler.observe(
            {'testpypi': testpypi, 'pypi': pypi},
            {target: publisher(reconciler, target) for target in ('testpypi', 'pypi')},
            originals / 'files',
            reconciler.clock.monotonic() + UNCERTAINTY_SECONDS,
            retain_observation=False,
        )
    if read() != material:
        raise ValueError('Source or check receipts changed while collecting review')
    reconciler.storage.history(str(source['version']), reconciler.head)
    names = archive_names(source)
    test_files = document(observations['testpypi'])
    production_files = document(observations['pypi'])
    if any(document(test_files.get(name)).get('status') != 'verified' for name in names):
        raise ValueError('TestPyPI bytes and both evidence types must be verified')
    if any(
        document(production_files.get(name)).get('status') not in ('missing', 'verified')
        for name in names
    ):
        raise ValueError('Current PyPI state is uncertain; review blocked')
    assets = sorted(
        [
            *names,
            'sdist.sigstore.json',
            'wheel.sigstore.json',
            'SHA256SUMS',
            'verification-report.json',
            *(name + '.publish.json' for name in names),
        ],
    )
    links = (
        '\n\n### Verification\n\n'
        f'- [Packages](https://pypi.org/project/zensical-tarn/{source["version"]}/)\n'
        '- Checks and evidence: see the attached `verification-report.json`, '
        '`SHA256SUMS`, build bundles and per-file publishing bundles.\n'
    )
    return canonical(
        {
            'schema': 'tarn-production-review-v1',
            'candidate': reconciler.retained.candidate,
            'manifest': manifest,
            'recovery': asdict(reconciler.retained),
            'history_head': history_head,
            'execution': {'run': reconciler.run, 'attempt': reconciler.attempt},
            'checks': {name: asdict(check) for name, check in material.checks.items()},
            'changelog': notes,
            'notes': notes + links,
            'assets': assets,
            'report_format': REPORT_FORMAT,
            'prerelease': bool(re.search(r'(?:a|b|rc)\d+', str(source['version']))),
            'make_latest': 'false'
            if re.search(r'(?:a|b|rc)\d+', str(source['version']))
            else 'true',
            'observations': observations,
            'remaining_pypi': [
                name for name in names if document(production_files[name])['status'] == 'missing'
            ],
            'production_verification': 'pending',
        },
    )


def prepare_review(
    reconciler: Reconciler,
    testpypi: Destination,
    pypi: Destination,
    read: Callable[[], ReviewMaterial],
) -> bytes:
    """Retain the exact private summary before the external production approval gate."""
    summary = review_snapshot(reconciler, testpypi, pypi, read, reconciler.head)
    reconciler.record(
        'review-prepared',
        {'summary': json.loads(summary), 'digest': digest(summary)},
    )
    return summary


@dataclass(frozen=True)
class Approval:
    """Local stand-in for an authenticated environment-gate result, not a live gate."""

    summary_digest: str
    run: str
    attempt: str


def publish_production(  # noqa: PLR0917 - Explicit approval and trusted service boundaries.
    reconciler: Reconciler,
    testpypi: Destination,
    pypi: Destination,
    read: Callable[[], ReviewMaterial],
    summary: bytes,
    approval: Approval,
    output: Path,
) -> Outcome:
    """Revalidate after the gate, then advance only missing originals and verify retrieval."""
    if output.exists():
        raise ValueError('Production retrieval requires a fresh output path')
    records = reconciler.storage.history(str(reconciler.source['version']), reconciler.head)
    last = records[-1].event
    if (
        approval != Approval(digest(summary), reconciler.run, reconciler.attempt)
        or last.kind != 'review-prepared'
        or (last.run, last.attempt) != (reconciler.run, reconciler.attempt)
        or last.details != {'summary': json.loads(summary), 'digest': digest(summary)}
    ):
        raise ValueError('Fresh approval for the exact summary and execution required')
    reviewed = document(json.loads(summary))
    if (
        review_snapshot(
            reconciler,
            testpypi,
            pypi,
            read,
            str(reviewed['history_head']),
        )
        != summary
    ):
        raise ValueError('Reviewed source, files, notes, checks or destination state changed')
    reconciler.record('production-approved', {'summary_digest': digest(summary)})
    expected = publisher(reconciler, 'pypi')
    deadline = reconciler.clock.monotonic() + UNCERTAINTY_SECONDS
    result = reconciler.reconcile({'pypi': pypi}, {'pypi': expected})
    if result.status != 'complete':
        return result
    try:
        result = retrieve(reconciler, pypi, expected, output, deadline, target='pypi')
        if dict(read().source) != dict(reconciler.source):
            raise ValueError('Source changed before finalisation')  # noqa: TRY301 - Screen failure below.
    except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError):
        reconciler.record(
            'production-incomplete',
            {'reason': 'Final PyPI retrieval or source check failed'},
        )
        return Outcome('incomplete', 'PyPI verification incomplete; GitHub finalisation blocked')
    reconciler.record(
        'production-verified',
        {'summary_digest': digest(summary), 'candidate': reconciler.retained.candidate},
    )
    return result
