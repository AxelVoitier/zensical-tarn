# Copyright 2026 Axel Voitier
# ruff: noqa: PT009, PT027, INP001, E402
"""Local destination and verifier response fixtures; no registry writes."""

import json
import subprocess
import sys
import unittest
from dataclasses import asdict, replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from release.candidate import canonical, manifest_bytes, wheel_statement
from release.reconciliation import Outcome, Publication, Publisher, Reconciler, RemoteFile
from release.sdist import statement
from release.storage import Event, Storage, digest
from test_storage import ReleaseService


class Clock:
    def __init__(self) -> None:
        self.now = 0.0
        self.observing = False

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


class Verifier:
    """External signature-verifier response fixture, not a certificate verifier."""

    def verify(self, bundle: bytes, deadline: float) -> Publication:
        value = json.loads(bundle)
        if not value['valid']:
            raise ValueError  # External verifier reports an invalid signature.
        return Publication(Publisher(**value['publisher']), value['statement'])


class Destination:
    def __init__(self, publisher: Publisher) -> None:
        self.publisher = publisher
        self.files: dict[str, RemoteFile] = {}
        self.writes: list[str] = []
        self.reads = 0
        self.unavailable_at: set[int] = set()
        self.clock = Clock()
        self.files_visible_at = 0.0
        self.build_visible_at = 0.0
        self.publish_visible_at = 0.0
        self.outcome = 'returned'
        self.changes: dict[int, dict[str, RemoteFile]] = {}

    def observe(self, deadline: float) -> dict[str, RemoteFile]:
        self.clock.observing = True
        self.reads += 1
        if self.reads in self.unavailable_at:
            raise OSError
        self.files.update(self.changes.get(self.reads, {}))
        if self.clock.now < self.files_visible_at:
            return {}
        return {
            name: replace(
                remote,
                build=remote.build if self.clock.now >= self.build_visible_at else None,
                publish=remote.publish if self.clock.now >= self.publish_visible_at else None,
            )
            for name, remote in self.files.items()
        }

    def upload(self, name: str, archive: bytes, build: bytes, deadline: float = 900) -> None:
        self.writes.append(name)
        if self.outcome == 'ignored':
            return
        publish = canonical(
            {
                'valid': True,
                'publisher': asdict(self.publisher),
                'statement': {
                    '_type': 'https://in-toto.io/Statement/v1',
                    'subject': [{'name': name, 'digest': {'sha256': digest(archive)}}],
                    'predicateType': 'https://docs.pypi.org/attestations/publish/v1',
                    'predicate': {},
                },
            },
        )
        self.files[name] = RemoteFile(archive, build, publish)
        if self.outcome == 'lost':
            raise OSError
        if self.outcome == 'cancelled':
            raise KeyboardInterrupt


class ReconciliationChecks(unittest.TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.verify_cost = 0.0
        self.clock = Clock()
        self.verification_budgets: list[float | None] = []
        self.files = self.root / 'files'
        self.files.mkdir()
        self.source: dict[str, object] = {
            'repository': 'AxelVoitier/zensical-tarn',
            'version': '1.2.3',
            'tag': 'v1.2.3',
            'commit': 'b' * 40,
        }
        self.sdist = 'zensical_tarn-1.2.3.tar.gz'
        self.wheel = 'zensical_tarn-1.2.3-py3-none-any.whl'
        (self.files / self.sdist).write_bytes(b'abc')
        (self.files / self.wheel).write_bytes(b'wheel')
        transfers = {
            kind: {
                'run_id': '101',
                'run_attempt': '1',
                'artifact_id': number,
                'artifact_name': f'{kind}-101-1',
                'transport_digest': 'sha256:' + 'd' * 64,
            }
            for kind, number in (('sdist', '73'), ('wheel', '75'))
        }
        for kind, payload in (
            ('sdist', statement(self.source, self.files / self.sdist, transfers['sdist'])),
            (
                'wheel',
                wheel_statement(
                    self.source,
                    self.files / self.sdist,
                    self.files / self.wheel,
                    transfers['sdist'],
                    transfers['wheel'],
                ),
            ),
        ):
            (self.files / f'{kind}.sigstore.json').write_bytes(
                canonical(
                    [{'verificationResult': {'statement': payload}}],
                ),
            )
        manifest = manifest_bytes(
            self.source,
            self.files,
            transfers,
            {'sdist': '74', 'wheel': '76'},
        )
        self.service = ReleaseService()
        self.storage = Storage(self.service, self.service.admin)

        def verify(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
            bundle = Path(argv[argv.index('--bundle') + 1])
            if self.clock.observing:
                timeout = _kwargs.get('timeout')
                budget = float(timeout) if isinstance(timeout, (float, int)) else None
                self.verification_budgets.append(budget)
                self.clock.now += (
                    min(self.verify_cost, budget) if budget is not None else self.verify_cost
                )
                if budget is not None and self.verify_cost >= budget:
                    raise subprocess.TimeoutExpired(argv, budget)
            return subprocess.CompletedProcess(argv, 0, bundle.read_text(), '')

        verifier = patch('release.sdist.subprocess.run', side_effect=verify)
        verifier.start()
        self.addCleanup(verifier.stop)
        self.retained = self.storage.retain(
            self.service.product,
            self.source,
            manifest,
            digest(manifest),
            self.files,
            Event('1.2.3', digest(manifest), 'b' * 40, '101', '1', 1, 'recovery-stored', None, {}),
        )
        self.clock = Clock()
        self.publisher = Publisher(
            'AxelVoitier/zensical-tarn',
            'release-preparation.yml',
            'b' * 40,
            'testpypi',
        )
        self.destination = Destination(self.publisher)
        self.destination.clock = self.clock
        self.verifier = Verifier()
        self.verification_budgets.clear()

    def reconcile(self) -> Outcome:
        head = self.storage.history('1.2.3')[-1].digest
        return Reconciler(
            self.storage,
            self.retained,
            self.source,
            '102',
            '1',
            head,
            self.verifier,
            self.clock,
        ).reconcile({'testpypi': self.destination}, {'testpypi': self.publisher})

    def test_one_file_acceptance_uploads_only_the_missing_original(self) -> None:
        self.destination.upload(
            self.sdist,
            b'abc',
            (self.files / 'sdist.sigstore.json').read_bytes(),
        )
        self.destination.writes.clear()
        result = self.reconcile()
        self.assertEqual(result.status, 'complete')
        self.assertEqual(self.destination.writes, [self.wheel])
        self.assertEqual(self.destination.files[self.wheel].archive, b'wheel')
        self.assertEqual(
            self.destination.files[self.wheel].build,
            (self.files / 'wheel.sigstore.json').read_bytes(),
        )
        self.assertEqual(self.storage.history('1.2.3')[-1].event.details['status'], 'complete')

    def test_failed_prewrite_read_does_not_lose_missing_work(self) -> None:
        self.destination.unavailable_at = {2}
        self.assertEqual(self.reconcile().status, 'complete')
        self.assertEqual(self.destination.writes, [self.sdist, self.wheel])

    def test_lost_response_and_delayed_files_and_evidence_are_verified_without_reupload(
        self,
    ) -> None:
        self.destination.outcome = 'lost'
        self.destination.files_visible_at = 60
        self.destination.build_visible_at = 90
        self.destination.publish_visible_at = 120
        self.assertEqual(self.reconcile().status, 'complete')
        self.assertEqual(self.clock.now, 120)
        self.assertEqual(self.destination.writes, [self.sdist, self.wheel])
        outcomes = [
            record.event.details['outcome']
            for record in self.storage.history('1.2.3')
            if record.event.kind == 'upload-outcome'
        ]
        self.assertEqual(outcomes, ['uncertain', 'uncertain'])

    def test_upload_success_without_visibility_stops_at_15_minutes_and_later_checks_again(
        self,
    ) -> None:
        self.destination.outcome = 'ignored'
        self.assertEqual(self.reconcile().status, 'incomplete')
        self.assertEqual(self.clock.now, 900)
        self.assertEqual(self.destination.writes, [self.sdist, self.wheel])
        # A later explicit attempt must not blindly repeat either uncertain write.
        self.assertEqual(self.reconcile().status, 'incomplete')
        self.assertEqual(self.clock.now, 1800)
        self.assertEqual(self.destination.writes, [self.sdist, self.wheel])
        self.destination.outcome = 'returned'
        for name, kind in ((self.sdist, 'sdist'), (self.wheel, 'wheel')):
            self.destination.upload(
                name,
                (self.files / name).read_bytes(),
                (self.files / f'{kind}.sigstore.json').read_bytes(),
            )
        writes = list(self.destination.writes)
        self.assertEqual(self.reconcile().status, 'complete')
        self.assertEqual(self.destination.writes, writes)

    def test_cancellation_retains_intent_and_resume_reuses_accepted_file(self) -> None:
        self.destination.outcome = 'cancelled'
        with self.assertRaises(KeyboardInterrupt):
            self.reconcile()
        self.assertTrue(
            any(record.event.kind == 'upload-started' for record in self.storage.history('1.2.3')),
        )
        self.destination.outcome = 'returned'
        self.assertEqual(self.reconcile().status, 'complete')
        self.assertEqual(self.destination.writes, [self.sdist, self.wheel])

    def test_missing_originals_block_all_uploads(self) -> None:
        del self.service.assets[self.retained.assets[self.sdist].id]
        self.assertEqual(self.reconcile().status, 'incomplete')
        self.assertEqual(self.destination.writes, [])

    def test_conflicting_archive_blocks_before_upload(self) -> None:
        self.destination.files[self.sdist] = RemoteFile(b'wrong', None, None)
        self.assertEqual(self.reconcile().status, 'incomplete')
        self.assertEqual(self.destination.writes, [])

    def test_missing_evidence_never_triggers_duplicate_upload(self) -> None:
        self.destination.files[self.sdist] = RemoteFile(b'abc', None, None)
        self.assertEqual(self.reconcile().status, 'incomplete')
        self.assertEqual(self.clock.now, 900)
        self.assertEqual(self.destination.writes, [self.wheel])

    def test_invalid_signature_or_publishing_identity_blocks_upload(self) -> None:
        self.destination.upload(
            self.sdist,
            b'abc',
            (self.files / 'sdist.sigstore.json').read_bytes(),
        )
        remote = self.destination.files[self.sdist]
        for change in (
            {'valid': False},
            {'publisher': asdict(replace(self.publisher, environment='pypi'))},
        ):
            with self.subTest(change=change):
                assert remote.publish is not None
                bundle = json.loads(remote.publish)
                bundle.update(change)
                self.destination.files[self.sdist] = replace(remote, publish=canonical(bundle))
                self.destination.writes.clear()
                self.assertEqual(self.reconcile().status, 'incomplete')
                self.assertEqual(self.destination.writes, [])

    def test_substituted_build_statement_blocks_upload(self) -> None:
        payload: dict[str, object] = {}
        remote = RemoteFile(
            b'abc',
            canonical([{'verificationResult': {'statement': payload}}]),
            None,
        )
        self.destination.files[self.sdist] = remote
        self.assertEqual(self.reconcile().status, 'incomplete')
        self.assertEqual(self.destination.writes, [])

    def test_outside_writer_change_between_inspection_and_upload_blocks(self) -> None:
        self.destination.changes[2] = {self.wheel: RemoteFile(b'outside', None, None)}
        self.assertEqual(self.reconcile().status, 'incomplete')
        self.assertEqual(self.destination.writes, [])

    def test_outside_writer_cannot_remove_previously_verified_evidence(self) -> None:
        self.assertEqual(self.reconcile().status, 'complete')
        remote = self.destination.files[self.sdist]
        self.destination.files[self.sdist] = replace(remote, publish=None)
        writes = list(self.destination.writes)
        self.assertEqual(self.reconcile().status, 'incomplete')
        self.assertEqual(self.destination.writes, writes)

    def test_destinations_keep_separate_publishing_identities(self) -> None:
        production = replace(self.publisher, environment='pypi')
        pypi = Destination(production)
        head = self.storage.history('1.2.3')[-1].digest
        result = Reconciler(
            self.storage,
            self.retained,
            self.source,
            '102',
            '1',
            head,
            self.verifier,
            self.clock,
        ).reconcile(
            {'testpypi': self.destination, 'pypi': pypi},
            {'testpypi': self.publisher, 'pypi': production},
        )
        self.assertEqual(result.status, 'complete')
        self.assertEqual(self.destination.writes, [self.sdist, self.wheel])
        self.assertEqual(pypi.writes, [self.sdist, self.wheel])
        for name in (self.sdist, self.wheel):
            self.assertEqual(self.destination.files[name].build, pypi.files[name].build)
            self.assertNotEqual(self.destination.files[name].publish, pypi.files[name].publish)

    def test_recovery_rejects_changed_publishing_policy_before_any_write(self) -> None:
        self.destination.outcome = 'ignored'
        self.assertEqual(self.reconcile().status, 'incomplete')
        self.publisher = replace(self.publisher, workflow='unreviewed.yml')
        self.destination.publisher = self.publisher
        self.assertIn('policy', self.reconcile().reason)

    def test_signed_publication_must_name_the_exact_file_digest_and_predicate(self) -> None:
        self.destination.upload(
            self.sdist,
            b'abc',
            (self.files / 'sdist.sigstore.json').read_bytes(),
        )
        remote = self.destination.files[self.sdist]
        assert remote.publish is not None
        for field, value in (
            ('subject', [{'name': self.sdist, 'digest': {'sha256': '0' * 64}}]),
            ('predicateType', 'https://example.invalid/unrelated'),
            ('predicate', {'unreviewed': True}),
        ):
            with self.subTest(field=field):
                bundle = json.loads(remote.publish)
                bundle['statement'][field] = value
                self.destination.files[self.sdist] = replace(remote, publish=canonical(bundle))
                self.destination.writes.clear()
                self.assertEqual(self.reconcile().status, 'incomplete')
                self.assertEqual(self.destination.writes, [])

    def test_stale_history_head_cannot_write(self) -> None:
        head = self.storage.history('1.2.3')[-1].digest
        reconciler = Reconciler(
            self.storage,
            self.retained,
            self.source,
            '102',
            '1',
            head,
            Verifier(),
            self.clock,
        )
        self.storage.append(
            Event(
                '1.2.3',
                self.retained.candidate,
                'b' * 40,
                '103',
                '1',
                2,
                'stopped',
                head,
                {'outcome': 'another attempt'},
            ),
        )
        with self.assertRaises(ValueError):
            reconciler.reconcile({'testpypi': self.destination}, {'testpypi': self.publisher})
        self.assertEqual(self.destination.writes, [])

    def test_unavailable_destination_never_counts_as_absence(self) -> None:
        self.destination.unavailable_at = set(range(1, 100))
        self.assertEqual(self.reconcile().status, 'incomplete')
        self.assertEqual(self.destination.writes, [])
        self.assertEqual(self.clock.now, 900)

    def test_github_archive_verification_does_not_publish_the_product_release(self) -> None:
        head = self.storage.history('1.2.3')[-1].digest
        result = Reconciler(
            self.storage,
            self.retained,
            self.source,
            '102',
            '1',
            head,
            self.verifier,
            self.clock,
        ).reconcile({'github': self.destination}, {'github': self.publisher})
        self.assertEqual(result.status, 'complete')
        self.assertTrue(self.service.release(20).draft)

    def test_build_verification_cannot_exceed_uncertainty_deadline(self) -> None:
        self.destination.upload(
            self.sdist,
            b'abc',
            (self.files / 'sdist.sigstore.json').read_bytes(),
        )
        self.destination.writes.clear()
        self.verify_cost = 600
        result = self.reconcile()
        self.assertEqual(result.status, 'incomplete')
        self.assertLessEqual(self.clock.now, 900)
        self.assertTrue(all(budget is not None for budget in self.verification_budgets))
        self.assertEqual(self.destination.writes, [])

    def test_publishing_verification_receives_and_honours_remaining_deadline(self) -> None:
        self.destination.upload(
            self.sdist,
            b'abc',
            (self.files / 'sdist.sigstore.json').read_bytes(),
        )
        self.destination.writes.clear()
        clock = self.clock
        budgets: list[float] = []

        class SlowVerifier(Verifier):
            def verify(self, bundle: bytes, deadline: float) -> Publication:
                budgets.append(deadline - clock.now)
                clock.now = deadline
                raise TimeoutError

        self.verifier = SlowVerifier()
        self.assertEqual(self.reconcile().status, 'incomplete')
        self.assertEqual(budgets, [900])
        self.assertEqual(self.clock.now, 900)
        self.assertEqual(self.destination.writes, [])
