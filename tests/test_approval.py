# Copyright 2026 Axel Voitier
# ruff: noqa: PT009, PT027, INP001, E402
"""Candidate approval through controlled services, without external writes."""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
import test_coordinator as coordinator_fixtures
import test_reconciliation as fixtures
from release.approval import (
    Approval,
    CheckResult,
    ReviewMaterial,
    prepare_review,
    publish_production,
)
from release.testpypi import publish


class ApprovalChecks(unittest.TestCase):
    def setUp(self) -> None:
        fixture = fixtures.ReconciliationChecks()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        self.reconciler = fixtures.Reconciler(
            fixture.storage,
            fixture.retained,
            fixture.source,
            '102',
            '1',
            fixture.storage.history('1.2.3')[-1].digest,
            fixture.verifier,
            fixture.clock,
        )
        self.assertEqual(
            publish(
                self.reconciler,
                fixture.destination,
                fixture.publisher,
                fixture.root / 'testpypi',
            ).status,
            'complete',
        )
        self.production = fixtures.Destination(
            fixtures.replace(fixture.publisher, environment='pypi'),
        )
        self.material: ReviewMaterial = ReviewMaterial(
            dict(fixture.source),
            '# Changelog\n\n## [1.2.3]\n\n- First change.\n- Second change.\n'
            '\n## [1.2.2]\n\n- Older.\n',
            {
                name: CheckResult(
                    fixture.retained.candidate,
                    fixtures.digest(fixtures.canonical(fixture.source)),
                    '101',
                    '1',
                    'pass',
                    'e' * 64,
                )
                for name in (
                    'preparation',
                    'reproducibility',
                    'archive-checks',
                    'testpypi-installation',
                )
            },
        )

    def read(self) -> ReviewMaterial:
        return self.material

    def test_review_contains_complete_notes_originals_and_pending_production(self) -> None:
        summary = prepare_review(
            self.reconciler,
            self.fixture.destination,
            self.production,
            self.read,
        )
        review = json.loads(summary)
        self.assertEqual(review['candidate'], self.fixture.retained.candidate)
        self.assertIn('- First change.\n- Second change.', review['notes'])
        self.assertNotIn('Older', review['notes'])
        self.assertEqual(review['production_verification'], 'pending')
        self.assertEqual(review['execution'], {'run': '102', 'attempt': '1'})
        self.assertEqual(self.production.writes, [])

    def test_approved_production_retrieves_both_evidence_types_before_finalisation(self) -> None:
        summary = prepare_review(
            self.reconciler,
            self.fixture.destination,
            self.production,
            self.read,
        )
        approval = Approval(fixtures.digest(summary), '102', '1')
        output = self.fixture.root / 'pypi'
        result = publish_production(
            self.reconciler,
            self.fixture.destination,
            self.production,
            self.read,
            summary,
            approval,
            output,
        )
        self.assertEqual(result.status, 'complete')
        self.assertEqual(self.production.writes, [self.fixture.sdist, self.fixture.wheel])
        self.assertEqual((output / 'files' / self.fixture.wheel).read_bytes(), b'wheel')
        self.assertTrue((output / 'publishing' / (self.fixture.wheel + '.json')).is_file())
        self.assertEqual(
            self.fixture.storage.history('1.2.3')[-1].event.kind,
            'production-verified',
        )

    def test_duplicate_or_malformed_version_heading_blocks_review(self) -> None:
        self.material = fixtures.replace(
            self.material,
            changelog=self.material.changelog + '\n## [1.2.3] - unknown date\n\n- Extra.\n',
        )
        with self.assertRaises(ValueError):
            prepare_review(self.reconciler, self.fixture.destination, self.production, self.read)

    def review(self) -> bytes:
        return prepare_review(self.reconciler, self.fixture.destination, self.production, self.read)

    def publish(self, summary: bytes, approval: Approval | None = None) -> fixtures.Outcome:
        return publish_production(
            self.reconciler,
            self.fixture.destination,
            self.production,
            self.read,
            summary,
            approval or Approval(fixtures.digest(summary), '102', '1'),
            self.fixture.root / 'pypi',
        )

    def test_missing_failed_or_wrong_candidate_checks_block_review(self) -> None:
        original = self.material
        for name in original.checks:
            for change in (
                None,
                {'status': 'fail'},
                {'candidate': 'f' * 64},
                {'evidence_digest': ''},
            ):
                with self.subTest(name=name, change=change):
                    checks = dict(original.checks)
                    if change is None:
                        del checks[name]
                    else:
                        checks[name] = fixtures.replace(checks[name], **change)
                    self.material = fixtures.replace(original, checks=checks)
                    with self.assertRaises(ValueError):
                        self.review()
        self.assertEqual(self.production.writes, [])

    def test_missing_or_empty_changelog_blocks_review(self) -> None:
        original = self.material
        for changelog in (
            '# Changelog\n## [Unreleased]\n- Later.',
            '## [1.2.3]\n',
            original.changelog + '\n## [1.2.3]\n- Duplicate.',
        ):
            with self.subTest(changelog=changelog):
                self.material = fixtures.replace(original, changelog=changelog)
                with self.assertRaises(ValueError):
                    self.review()

    def test_changed_public_contents_or_summary_are_rejected(self) -> None:
        summary = self.review()
        original = json.loads(summary)
        for field, value in (
            ('notes', 'Different claims'),
            ('assets', ['private-records.json']),
            ('candidate', 'f' * 64),
            ('report_format', {'anything': 'passes'}),
        ):
            with self.subTest(field=field):
                changed = fixtures.canonical({**original, field: value})
                with self.assertRaises(ValueError):
                    self.publish(changed)
        self.assertEqual(self.production.writes, [])

    def test_source_workflow_or_notes_change_during_approval_blocks_upload(self) -> None:
        summary = self.review()
        original = self.material
        for source in (
            {**original.source, 'commit': 'c' * 40},
            {**original.source, 'coordinator': {'revision': 'c' * 40}},
        ):
            self.material = fixtures.replace(original, source=source)
            with self.assertRaises(ValueError):
                self.publish(summary)
        self.material = fixtures.replace(
            original,
            changelog=original.changelog.replace('First', 'New'),
        )
        with self.assertRaises(ValueError):
            self.publish(summary)
        self.assertEqual(self.production.writes, [])

    def test_changed_originals_or_testpypi_evidence_block_after_approval(self) -> None:
        summary = self.review()
        remote = self.fixture.destination.files[self.fixture.sdist]
        self.fixture.destination.files[self.fixture.sdist] = fixtures.replace(remote, publish=None)
        with self.assertRaises(ValueError):
            self.publish(summary)
        self.fixture.destination.files[self.fixture.sdist] = remote
        asset = self.fixture.retained.assets[self.fixture.wheel]
        del self.fixture.service.assets[asset.id]
        with self.assertRaises(ValueError):
            self.publish(summary)
        self.assertEqual(self.production.writes, [])

    def test_new_execution_and_attempt_require_new_summary_and_approval(self) -> None:
        summary = self.review()
        for change in ({'run': '103'}, {'attempt': '2'}):
            original = (self.reconciler.run, self.reconciler.attempt)
            for key, value in change.items():
                setattr(self.reconciler, key, value)
            with self.assertRaises(ValueError):
                self.publish(summary)
            self.reconciler.run, self.reconciler.attempt = original
        self.assertEqual(self.production.writes, [])

    def test_partial_production_resume_requires_fresh_review_then_uploads_only_missing(
        self,
    ) -> None:
        summary = self.review()
        self.production.outcome = 'cancelled'
        with self.assertRaises(KeyboardInterrupt):
            self.publish(summary)
        self.production.outcome = 'returned'
        self.reconciler.run = '103'
        with self.assertRaises(ValueError):
            self.publish(summary)
        resumed = self.review()
        self.assertNotEqual(fixtures.digest(resumed), fixtures.digest(summary))
        self.assertEqual(json.loads(resumed)['remaining_pypi'], [self.fixture.wheel])
        with self.assertRaises(ValueError):
            self.publish(resumed, Approval(fixtures.digest(summary), '102', '1'))
        result = self.publish(resumed, Approval(fixtures.digest(resumed), '103', '1'))
        self.assertEqual(result.status, 'complete')
        self.assertEqual(self.production.writes, [self.fixture.sdist, self.fixture.wheel])

    def test_destination_or_history_change_after_review_blocks_upload(self) -> None:
        summary = self.review()
        self.production.files['unexpected.whl'] = fixtures.RemoteFile(b'bad', None, None)
        with self.assertRaises(ValueError):
            self.publish(summary)
        self.production.files.clear()
        self.reconciler.record('outside-writer', {})
        with self.assertRaises(ValueError):
            self.publish(summary)
        self.assertEqual(self.production.writes, [])

    def test_incomplete_production_evidence_never_allows_finalisation(self) -> None:
        summary = self.review()
        self.production.publish_visible_at = 1000
        self.production.clock = self.fixture.clock
        self.assertEqual(self.publish(summary).status, 'incomplete')
        self.assertFalse((self.fixture.root / 'pypi').exists())
        self.assertNotEqual(
            self.fixture.storage.history('1.2.3')[-1].event.kind,
            'production-verified',
        )

    def test_source_change_while_collecting_review_blocks_preparation(self) -> None:
        reads = 0

        def unstable() -> ReviewMaterial:
            nonlocal reads
            reads += 1
            if reads > 1:
                return fixtures.replace(
                    self.material,
                    source={**self.material.source, 'commit': 'c' * 40},
                )
            return self.material

        with self.assertRaises(ValueError):
            prepare_review(self.reconciler, self.fixture.destination, self.production, unstable)
        self.assertEqual(self.production.writes, [])

    def test_prerelease_review_preserves_latest_stable_and_all_prerequisites(self) -> None:
        fixture = self.fixture
        source = {**fixture.source, 'version': '1.2.3rc1', 'tag': 'v1.2.3rc1'}
        files = fixture.root / 'rc-files'
        files.mkdir()
        for path in fixture.files.iterdir():
            name = path.name.replace('1.2.3', '1.2.3rc1')
            data = (
                path.read_bytes().replace(b'1.2.3', b'1.2.3rc1')
                if path.suffix == '.json'
                else path.read_bytes()
            )
            (files / name).write_bytes(data)
        old_manifest = json.loads(
            fixture.service.download(fixture.retained.assets['candidate.json'].id),
        )
        manifest = fixtures.manifest_bytes(
            source,
            files,
            old_manifest['transports'],
            {'sdist': '74', 'wheel': '76'},
        )
        service = fixtures.ReleaseService()
        service.product = fixtures.replace(service.product, tag='v1.2.3rc1')
        service.releases[20] = fixtures.replace(
            service.releases[20],
            tag='v1.2.3rc1',
            body=service.product.body,
        )
        service.tag_targets['v1.2.3rc1'] = ('b' * 40, 'commit', 'b' * 40)
        storage = fixtures.Storage(service, service.admin)
        retained = storage.retain(
            service.product,
            source,
            manifest,
            fixtures.digest(manifest),
            files,
            fixtures.Event(
                '1.2.3rc1',
                fixtures.digest(manifest),
                'b' * 40,
                '101',
                '1',
                1,
                'recovery-stored',
                None,
                {},
            ),
        )
        reconciler = fixtures.Reconciler(
            storage,
            retained,
            source,
            '102',
            '1',
            storage.history('1.2.3rc1')[-1].digest,
            fixture.verifier,
            fixture.clock,
        )
        testpypi = fixtures.Destination(fixture.publisher)
        production = fixtures.Destination(fixtures.replace(fixture.publisher, environment='pypi'))
        self.assertEqual(
            publish(reconciler, testpypi, fixture.publisher, fixture.root / 'rc-testpypi').status,
            'complete',
        )
        material = ReviewMaterial(
            source,
            self.material.changelog.replace('1.2.3', '1.2.3rc1'),
            {
                name: fixtures.replace(
                    check,
                    candidate=retained.candidate,
                    source_digest=fixtures.digest(fixtures.canonical(source)),
                )
                for name, check in self.material.checks.items()
            },
        )
        review = json.loads(prepare_review(reconciler, testpypi, production, lambda: material))
        self.assertTrue(review['prerelease'])
        self.assertEqual(review['make_latest'], 'false')
        self.assertEqual(len(review['checks']), 4)

    def test_final_production_retrieval_failure_blocks_github_finalisation(self) -> None:
        summary = self.review()
        # Review, post-approval recheck, five reconciliation reads, then retrieval.
        self.production.unavailable_at = {8}
        self.assertEqual(self.publish(summary).status, 'incomplete')
        self.assertFalse((self.fixture.root / 'pypi').exists())
        self.assertEqual(
            self.fixture.storage.history('1.2.3')[-1].event.kind,
            'production-incomplete',
        )


class HostedBoundaryChecks(unittest.TestCase):
    def test_hosted_review_and_production_commands_refuse_without_any_enable_flag(self) -> None:
        fixture = coordinator_fixtures.CoordinatorChecks()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        for stage in ('review', 'publish-pypi'):
            fixture.run_cli(stage, expected=1)
            self.assertIn('Hosted production approval and uploads are disabled', fixture.output)

    def test_production_environment_is_isolated_and_hard_disabled(self) -> None:
        workflow = (ROOT / '.github/workflows/release-preparation.yml').read_text()
        production = workflow.split('  publish-pypi:', 1)[1].split('  report:', 1)[0]
        self.assertIn('environment: pypi', production)
        self.assertIn('false &&', production)
        self.assertIn('needs: [resolve, review]', production)
        self.assertIn('id-token: write', production)
        self.assertNotIn('contents: write', production)
        self.assertNotIn('pip install', production)
        self.assertIn('--uploads-disabled', production)


if __name__ == '__main__':
    unittest.main()
