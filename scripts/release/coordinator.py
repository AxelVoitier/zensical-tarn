#!/usr/bin/env python3
# Copyright 2026 Axel Voitier
# ruff: noqa: EXE001, T201, EM101, TRY003, TRY301
"""Admit tagged attempts and recover retained originals without package execution."""

import argparse
import json
import os
import shlex
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import asdict
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from release.candidate import canonical, verify_candidate
from release.reconciliation import (
    Clock,
    Destination,
    Outcome,
    Publisher,
    PublishingVerifier,
    Reconciler,
)
from release.sdist import COORDINATOR, REPOSITORY, VERSION, source_identity
from release.storage import Asset, Draft, Event, Record, RecoveryCopy, ReleaseAPI, Storage, digest
from release.storage_api import GitHubAPI, document
from release.testpypi import publish


def selected_source(root: Path) -> dict[str, object]:
    """Require the platform-selected tagged instructions, never main plus an input."""
    ref = os.environ['GITHUB_REF']
    tag = ref.removeprefix('refs/tags/')
    commit = os.environ['GITHUB_SHA']
    if (
        not ref.startswith('refs/tags/')
        or not VERSION.fullmatch(tag)
        or os.environ['GITHUB_REPOSITORY'] != REPOSITORY
        or os.environ['GITHUB_WORKFLOW_SHA'] != commit
        or os.environ['GITHUB_WORKFLOW_REF'] != f'{REPOSITORY}/{COORDINATOR}@{ref}'
    ):
        raise ValueError('Select the original product tag as the workflow ref')
    return source_identity(root, tag, commit)


def entry(source: dict[str, object]) -> str:
    """Validate supported event payloads before admitting any work."""
    event = document(json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_bytes()))
    name, tag = os.environ['GITHUB_EVENT_NAME'], source['tag']
    if name == 'create' and event.get('ref_type') == 'tag' and event.get('ref') == tag:
        return 'automatic'
    if (
        name == 'push'
        and event.get('ref') == 'refs/tags/' + str(tag)
        and event.get('deleted') is False
        and event.get('after') in (source['commit'], source['tag_ref_target'])
    ):
        return 'automatic'
    if name == 'workflow_dispatch':
        mode = document(event.get('inputs')).get('mode')
        if mode in ('prepare', 'resume'):
            return str(mode)
    raise ValueError('Unsupported release entry point or stale event identity')


def observations(api: ReleaseAPI, tag: str) -> dict[str, object]:
    """Read both indexes and product releases; queue ownership cannot exclude outsiders."""
    registries: dict[str, object] = {}
    for name, host in (('testpypi', 'test.pypi.org'), ('pypi', 'pypi.org')):
        url = f'https://{host}/pypi/zensical-tarn/{tag[1:]}/json'
        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                data = document(json.loads(response.read(2_097_153)))
            files = data.get('urls')
            if not isinstance(files, list):
                raise TypeError('Missing registry file observations')
            registries[name] = files
        except urllib.error.HTTPError as error:
            if error.code != 404:  # noqa: PLR2004 - Only explicit absence is safe.
                raise
            registries[name] = []
    releases: list[dict[str, object]] = []
    page = 1
    seen: set[int] = set()
    while batch := api.releases_page(page):
        for release in batch:
            if release.id in seen:
                raise ValueError('Repeated release page')
            seen.add(release.id)
            if release.tag == tag:
                assets: list[dict[str, object]] = []
                asset_page = 1
                asset_ids: set[int] = set()
                while items := api.assets_page(release.id, asset_page):
                    for asset in items:
                        if asset.id in asset_ids:
                            raise ValueError('Repeated product asset page')
                        asset_ids.add(asset.id)
                        data = api.download(asset.id)
                        if len(data) != asset.size or api.asset(asset.id) != asset:
                            raise ValueError('Product asset changed during observation')
                        assets.append({**asdict(asset), 'sha256': digest(data)})
                    asset_page += 1
                releases.append(
                    {
                        **asdict(release),
                        'assets': sorted(assets, key=lambda item: int(str(item['id']))),
                    },
                )
        page += 1
    return {'registries': registries, 'github': releases}


def current(
    root: Path,
    storage: Storage,
) -> tuple[dict[str, object], list[Record], dict[str, object]]:
    """Independently re-read source, tag, operational chain and destinations."""
    source = selected_source(root)
    if storage.api.tag_identity(str(source['tag'])) != (
        source['tag_ref_target'],
        source['tag_ref_type'],
        source['commit'],
    ):
        raise ValueError('Remote tag differs from queued source identity')
    records = storage.history(str(source['version']))
    observed = observations(storage.api, str(source['tag']))
    return source, records, observed


def recovery_command(tag: str, mode: str = 'resume') -> str:
    """Construct argv first, then quote each argument for a POSIX shell."""
    if not VERSION.fullmatch(tag) or mode not in ('resume', 'prepare'):
        raise ValueError('Unsupported recovery command identity')
    return shlex.join(
        [
            'gh',
            'workflow',
            'run',
            Path(COORDINATOR).name,
            '--repo',
            REPOSITORY,
            '--ref',
            tag,
            '-f',
            f'mode={mode}',
        ],
    )


def recovery_copy(value: object) -> RecoveryCopy:
    """Decode retained IDs; Storage independently validates all service metadata."""
    item = document(value)
    return RecoveryCopy(
        Draft(**document(item['product'])),  # type: ignore[arg-type]
        str(item['candidate']),
        {name: Asset(**document(asset)) for name, asset in document(item['assets']).items()},  # type: ignore[arg-type]
    )


def check_producer(manifest: bytes, run: str, attempt: str) -> None:
    """Bind both original transports to the admitted preparation execution."""
    transports = document(document(json.loads(manifest))['transports'])
    for kind in ('sdist', 'wheel'):
        transfer = document(transports[kind])
        if (transfer['run_id'], transfer['run_attempt']) != (run, attempt):
            raise ValueError('Original producer differs from admitted preparation execution')


def reconcile_retention(
    root: Path,
    storage: Storage,
    preparation: Record,
    selection: Record,
) -> Record:
    """Recover a complete copy whose final history append was cancelled."""
    source, records, observed = current(root, storage)
    products = cast('list[object]', observed['github'])
    if len(products) != 1:
        raise ValueError('Unrecognised product storage; stop recovery')
    draft = Draft(**document(selection.event.details['product']))  # type: ignore[arg-type]
    if document(products[0])['id'] != draft.id or selection.event.candidate is None:
        raise ValueError('Original product storage differs from retained builder selection')
    if (selection.event.run, selection.event.attempt) != (
        preparation.event.run,
        preparation.event.attempt,
    ):
        raise ValueError('Retained builder selection differs from admitted producer')
    storage.product(draft, source)
    assets = {asset.name: asset for asset in storage.assets(draft)}
    if 'candidate.json' not in assets:
        raise ValueError('An incomplete recovery copy exists; stop without rebuilding')
    manifest = storage.read(draft, assets['candidate.json'])
    retained = RecoveryCopy(draft, selection.event.candidate, assets)
    with TemporaryDirectory() as directory:
        storage.recover(retained, source, Path(directory) / 'verified')
    check_producer(manifest, preparation.event.run, preparation.event.attempt)
    if current(root, storage) != (source, records, observed):
        raise ValueError('State changed while reconciling original retention')
    last = records[-1]
    return storage.append(
        Event(
            str(source['version']),
            retained.candidate,
            str(source['commit']),
            os.environ['GITHUB_RUN_ID'],
            os.environ['GITHUB_RUN_ATTEMPT'],
            last.event.sequence + 1,
            'recovery-stored',
            last.digest,
            {'recovery': asdict(retained)},
        ),
    )


def admit(root: Path, storage: Storage) -> dict[str, object]:  # noqa: PLR0912 - Explicit fail-closed entry decisions.
    """Deduplicate automatic events using retained identity, including cancelled runs."""
    source, records, observed = current(root, storage)
    mode = entry(source)
    admissions = [record for record in records if record.event.kind == 'admitted']
    same = bool(admissions) and admissions[-1].event.details.get('source') == source
    if same and mode == 'automatic':
        return {
            'action': 'noop',
            'reason': 'Identity already admitted; inspect state before deliberate recovery',
        }
    preparations = [
        record for record in admissions if record.event.details.get('action') == 'prepare'
    ]
    generation = preparations[-1].event.sequence if preparations else 1
    originals = [
        record
        for record in records
        if record.event.kind == 'recovery-stored' and record.event.sequence >= generation
    ]
    retained = originals[-1] if originals and same else None
    selections = [
        record
        for record in records
        if record.event.kind == 'retention-started' and record.event.sequence >= generation
    ]
    selection = selections[-1] if selections and same else None
    product_states = cast('list[object]', observed['github'])
    has_assets = any(document(item)['assets'] for item in product_states)
    candidate = None
    recovery: object = None
    if mode == 'resume':
        if not same:
            raise ValueError('Resume source or workflow differs from retained original tag')
        if retained is None and has_assets:
            if not preparations or selection is None:
                raise ValueError('No retained builder selection authorises these external files')
            retained = reconcile_retention(root, storage, preparations[-1], selection)
            source, records, observed = current(root, storage)
        if retained is None and selection is not None:
            raise ValueError(
                'Original selected files are missing; stop recovery and use a new version',
            )
        if retained is None:
            raise ValueError(
                'Full preparation required if original archives never existed. '
                'Inspect pre-upload state, then use: '
                + recovery_command(str(source['tag']), 'prepare'),
            )
        candidate = retained.event.candidate
        recovery = retained.event.details['recovery']
        action = 'resume'
    else:
        registries = document(observed['registries'])
        irreversible = (
            any(registries.values())
            or any(document(item)['draft'] is not True for item in product_states)
            or any(
                record.event.kind
                not in (
                    'admitted',
                    'preparation-failed',
                    'retention-started',
                    'recovery-stored',
                    'stopped',
                )
                for record in records
            )
        )
        if irreversible:
            raise ValueError(
                'Upload, approval or unrecognised history requires a new version for preparation',
            )
        if records and not admissions:
            raise ValueError('Unrecognised history has no retained admission identity')
        if same and (has_assets or selection is not None) and retained is None:
            raise ValueError(
                'An incomplete recovery copy exists; stop without replacement builds',
            )
        if same and retained is not None:
            raise ValueError('Retained originals exist; use resume, never rebuild replacements')
        action = 'prepare'
    event = Event(
        str(source['version']),
        candidate,
        str(source['commit']),
        os.environ['GITHUB_RUN_ID'],
        os.environ['GITHUB_RUN_ATTEMPT'],
        len(records) + 1,
        'admitted',
        records[-1].digest if records else None,
        {
            'source': source,
            'action': action,
            'observations': observed,
            'recovery': recovery,
            'command': recovery_command(str(source['tag'])),
        },
    )
    # Check originals before adding a resume admission, and again in the fetch stage.
    if action == 'resume':
        with TemporaryDirectory() as directory:
            storage.recover(recovery_copy(recovery), source, Path(directory) / 'verified')
    if current(root, storage) != (source, records, observed):
        raise ValueError('State changed during admission')
    record = storage.append(event)
    return {'action': action, 'event': asdict(event), 'head': record.digest}


def guard(root: Path, storage: Storage, receipt: dict[str, object]) -> Event:
    """Reject stale attempts and any state changed outside the shared queue."""
    source, records, observed = current(root, storage)
    event = Event(**document(receipt.get('event')))  # type: ignore[arg-type]
    if (
        not records
        or records[-1].digest != receipt.get('head')
        or records[-1].event != event
        or event.kind != 'admitted'
        or event.run != os.environ['GITHUB_RUN_ID']
        or event.attempt != os.environ['GITHUB_RUN_ATTEMPT']
        or event.details.get('source') != source
        or event.details.get('observations') != observed
        or receipt.get('action') != event.details.get('action')
    ):
        raise ValueError('Stale attempt or changed source, history or destination state')
    return event


def report(root: Path, storage: Storage, outcome: str) -> dict[str, object]:
    """Append a best-effort outcome without making recovery depend on reporting."""
    source, records, _observed = current(root, storage)
    command = recovery_command(str(source['tag']))
    if (
        records
        and records[-1].event.run == os.environ['GITHUB_RUN_ID']
        and records[-1].event.attempt == os.environ['GITHUB_RUN_ATTEMPT']
    ):
        last = records[-1]
        storage.append(
            Event(
                str(source['version']),
                last.event.candidate,
                str(source['commit']),
                last.event.run,
                last.event.attempt,
                last.event.sequence + 1,
                'stopped',
                last.digest,
                {'outcome': outcome, 'command': command, 'publication': 'disabled'},
            ),
        )
    return {'command': command, 'outcome': outcome, 'publication': 'disabled'}


def prepare_product(root: Path, storage: Storage, receipt: dict[str, object]) -> dict[str, object]:
    """Create a product draft under admission, then freeze its observed identity."""
    event = guard(root, storage, receipt)
    source = document(event.details['source'])
    source_before, records, observed = current(root, storage)
    if event.details['action'] != 'prepare' or observed['github']:
        raise ValueError('Automatic draft creation requires a fresh product selection')
    marker = Draft(
        1,
        'product',
        str(source['tag']),
        str(source['commit']),
        storage.administrative.repository_id,
    )
    created = storage.api.create_product(marker.tag, marker.target, marker.body)
    product = Draft(created.id, 'product', marker.tag, marker.target, marker.repository_id)
    storage.product(product, source)
    source_after, after_records, after = current(root, storage)
    if (
        source_after != source_before
        or after_records != records
        or after['registries'] != observed['registries']
    ):
        raise ValueError('State changed during product draft creation')
    details = {**event.details, 'observations': after}
    admitted = Event(
        event.version,
        None,
        event.source,
        event.run,
        event.attempt,
        event.sequence + 1,
        'admitted',
        str(receipt['head']),
        details,
    )
    record = storage.append(admitted)
    return {'head': record.digest, 'event': asdict(admitted), 'action': 'prepare'}


def selected_stage(args: argparse.Namespace, storage: Storage) -> dict[str, object]:
    """Retrieve the durable admission and check it before any selected operation."""
    if args.head is not None:
        records = storage.history(str(selected_source(args.root)['version']), args.head)
        record = records[-1]
        receipt = {
            'head': record.digest,
            'event': asdict(record.event),
            'action': record.event.details['action'],
        }
    elif args.receipt is not None:
        receipt = document(json.loads(args.receipt.read_bytes()))
    else:
        raise ValueError('Retained admission head or receipt required')
    event = guard(args.root, storage, receipt)
    source = document(event.details['source'])
    if args.stage == 'recover':
        if event.details['action'] != 'resume' or args.output is None:
            raise ValueError('Resume admission and a fresh output path required')
        storage.recover(recovery_copy(event.details['recovery']), source, args.output)
        guard(args.root, storage, receipt)
    elif args.stage == 'retain':
        if (
            event.details['action'] != 'prepare'
            or args.candidate_dir is None
            or args.candidate_digest is None
        ):
            raise ValueError(
                'Preparation admission and builder candidate digest required',
            )
        manifest = (args.candidate_dir / 'candidate.json').read_bytes()
        candidate = args.candidate_digest
        if digest(manifest) != candidate:
            raise ValueError('Original candidate digest differs from builder selection')
        check_producer(manifest, event.run, event.attempt)
        if args.product_id is None:
            receipt = prepare_product(args.root, storage, receipt)
            event = Event(**document(receipt['event']))  # type: ignore[arg-type]
            products = cast('list[object]', document(event.details['observations'])['github'])
            product_id = int(str(document(products[0])['id']))
        else:
            product_id = args.product_id
        product = Draft(
            product_id,
            'product',
            str(source['tag']),
            str(source['commit']),
            args.repository_id,
        )
        verify_candidate(manifest, candidate, source, args.candidate_dir / 'files')
        guard(args.root, storage, receipt)
        selected = storage.append(
            Event(
                event.version,
                candidate,
                event.source,
                event.run,
                event.attempt,
                event.sequence + 1,
                'retention-started',
                str(receipt['head']),
                {'product': asdict(product)},
            ),
        )
        storage.retain(
            product,
            source,
            manifest,
            candidate,
            args.candidate_dir / 'files',
            Event(
                event.version,
                candidate,
                event.source,
                event.run,
                event.attempt,
                selected.event.sequence + 1,
                'recovery-stored',
                selected.digest,
                {},
            ),
        )
    return {'status': 'pass', 'admission-head': receipt['head']}


def testpypi(  # noqa: PLR0917 - Explicit trusted service boundaries for local acceptance.
    root: Path,
    storage: Storage,
    head: str,
    destination: Destination,
    verifier: PublishingVerifier,
    clock: Clock,
    output: Path,
) -> Outcome:
    """Use admitted retained originals for normal and resumed controlled publication."""
    source, records, observed = current(root, storage)
    admissions = [record for record in records if record.digest == head]
    if len(admissions) != 1:
        raise ValueError('Original admission head required')
    admission = admissions[0]
    event = admission.event
    if (
        event.kind != 'admitted'
        or event.details.get('source') != source
        or event.run != os.environ['GITHUB_RUN_ID']
        or event.attempt != os.environ['GITHUB_RUN_ATTEMPT']
        or document(event.details['observations'])['registries'] != observed['registries']
    ):
        raise ValueError('Stale TestPyPI admission or changed source/destinations')
    later = records[event.sequence :]
    if event.details['action'] == 'prepare':
        if [record.event.kind for record in later] != ['retention-started', 'recovery-stored']:
            raise ValueError('Normal TestPyPI requires verified durable retention')
        if any(
            (record.event.run, record.event.attempt) != (event.run, event.attempt)
            for record in later
        ):
            raise ValueError('Retention belongs to a different attempt')
        retained = recovery_copy(later[-1].event.details['recovery'])
    elif event.details['action'] == 'resume' and not later:
        retained = recovery_copy(event.details['recovery'])
    else:
        raise ValueError('Fresh preparation or resume admission required')
    reconciler = Reconciler(
        storage,
        retained,
        source,
        event.run,
        event.attempt,
        records[-1].digest,
        verifier,
        clock,
    )
    publisher = Publisher(REPOSITORY, Path(COORDINATOR).name, str(source['commit']), 'testpypi')
    return publish(reconciler, destination, publisher, output)


def main() -> int:
    """Trusted coordinator CLI; preparation never selects instructions using a tag input."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        'stage',
        choices=[
            'admit',
            'guard',
            'recover',
            'retain',
            'report',
            'testpypi',
            'review',
            'publish-pypi',
            'finalise',
        ],
    )
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--admin-id', required=True, type=int)
    parser.add_argument('--admin-target', required=True)
    parser.add_argument('--repository-id', required=True)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--receipt', type=Path)
    parser.add_argument('--candidate-dir', type=Path)
    parser.add_argument('--candidate-digest')
    parser.add_argument('--product-id', type=int)
    parser.add_argument('--head')
    parser.add_argument('--uploads-disabled', action='store_true')
    parser.add_argument(
        '--outcome',
        choices=['success', 'failure', 'cancelled', 'skipped'],
        default='failure',
    )
    args = parser.parse_args()
    try:
        if args.stage == 'finalise':
            raise ValueError(
                'Hosted GitHub finalisation is disabled. Use the controlled finalisation API '
                'for local acceptance; actual release protection and write adapters need '
                'separately authorised implementation and hosted proof.',
            )
        if args.stage in ('review', 'publish-pypi'):
            raise ValueError(
                'Hosted production approval and uploads are disabled. '
                'Use the controlled approval API for local acceptance; '
                'authenticated check receipts, environment controls and registry adapters '
                'need separate implementation and hosted proof.',
            )
        if args.stage == 'testpypi':
            raise ValueError(
                'Hosted TestPyPI uploads are disabled. Use the controlled publication API '
                'for local '
                'acceptance; live registry and certificate adapters need separate proof.',
            )
        if args.repository_id != os.environ['GITHUB_REPOSITORY_ID']:
            raise ValueError('Repository numeric identity differs from retained setup')
        storage = Storage(
            GitHubAPI(),
            Draft(
                args.admin_id,
                'administrative',
                'release-records',
                args.admin_target,
                args.repository_id,
            ),
        )
        result: dict[str, object]
        if args.stage == 'report':
            result = report(args.root, storage, args.outcome)
        elif args.stage == 'admit':
            result = admit(args.root, storage)
            if args.output is None:
                raise ValueError('Admission output path required')
            args.output.write_bytes(canonical(result))
        else:
            result = selected_stage(args, storage)
        if args.stage == 'admit' and os.environ.get('GITHUB_OUTPUT'):
            source = selected_source(args.root)
            outputs = {
                'action': result['action'],
                'head': result.get('head', ''),
                'tag-ref-target': source['tag_ref_target'],
                'tag-ref-type': source['tag_ref_type'],
            }
            with Path(os.environ['GITHUB_OUTPUT']).open('a', encoding='utf-8') as stream:
                stream.writelines(f'{key}={value}\n' for key, value in outputs.items())
        if args.stage == 'retain' and os.environ.get('GITHUB_OUTPUT'):
            with Path(os.environ['GITHUB_OUTPUT']).open('a', encoding='utf-8') as stream:
                stream.write(f'admission-head={result["admission-head"]}\n')
        public_result = {key: value for key, value in result.items() if key != 'event'}
        print(json.dumps(public_result, sort_keys=True))
    except (ValueError, TypeError, KeyError, OSError, subprocess.SubprocessError) as error:
        print(f'Coordinator stopped: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
