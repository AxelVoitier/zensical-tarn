# Copyright 2026 Axel Voitier
# ruff: noqa: PT009, INP001, E402
"""GitHub finalisation against controlled destinations; external writes disabled."""

import json
import sys
import unittest
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
import test_approval as approval_fixtures
import test_coordinator as coordinator_fixtures
from release.approval import Approval, publish_production
from release.finalisation import PublicRelease, finalise
from release.reconciliation import Outcome
from release.storage import digest


class GitHub:
    """Independent public-release service fixture; no overwrite operation."""

    def __init__(self, fixture: approval_fixtures.ApprovalChecks) -> None:
        self.fixture = fixture
        self.service = fixture.fixture.service
        self.prerelease = False
        self.make_latest = 'true'
        self.writes: list[str] = []

    def observe(self, deadline: float) -> PublicRelease:
        release = self.service.release(20)
        assets = {
            asset.name: data
            for owner, asset, data in self.service.assets.values()
            if owner == self.service.product.id
        }
        return PublicRelease(release, self.prerelease, self.make_latest, assets)

    def attach(self, name: str, data: bytes, deadline: float) -> None:
        self.writes.append(name)
        self.service.upload(20, name, data)

    def publish(self, notes: str, *, prerelease: bool, make_latest: str, deadline: float) -> None:
        self.writes.append('publish')
        self.service.releases[20] = replace(self.service.release(20), body=notes, draft=False)
        self.prerelease = prerelease
        self.make_latest = make_latest


class FinalisationChecks(unittest.TestCase):
    def setUp(self) -> None:
        self.approval = approval_fixtures.ApprovalChecks()
        self.approval.setUp()
        self.addCleanup(self.approval.doCleanups)
        self.summary = self.approval.review()
        self.assertEqual(self.approval.publish(self.summary).status, 'complete')
        self.github = GitHub(self.approval)

    def finish(self) -> Outcome:
        return finalise(
            self.approval.reconciler,
            self.approval.production,
            self.approval.read,
            self.summary,
            self.github,
        )

    def test_verified_candidate_publishes_exact_assets_and_retains_private_history(self) -> None:
        self.assertEqual(self.finish().status, 'complete')
        observed = self.github.observe(900)
        self.assertFalse(observed.release.draft)
        self.assertEqual(observed.release.body, json.loads(self.summary)['notes'])
        self.assertEqual(set(observed.assets), set(json.loads(self.summary)['assets']))
        self.assertEqual(observed.assets[self.approval.fixture.wheel], b'wheel')
        self.assertEqual(
            self.approval.fixture.storage.history('1.2.3')[-1].event.kind,
            'github-complete',
        )
        self.assertTrue(self.approval.fixture.service.release(10).draft)

    def test_source_change_during_publication_leaves_incomplete_history(self) -> None:
        original_publish = self.github.publish

        def changed(notes: str, *, prerelease: bool, make_latest: str, deadline: float) -> None:
            original_publish(
                notes, prerelease=prerelease, make_latest=make_latest, deadline=deadline
            )
            self.approval.material = replace(
                self.approval.material,
                source={**self.approval.material.source, 'commit': 'c' * 40},
            )

        self.github.publish = changed
        self.assertEqual(self.finish().status, 'incomplete')
        self.assertEqual(
            self.approval.fixture.storage.history('1.2.3')[-1].event.kind,
            'github-incomplete',
        )

    def test_private_payload_in_publishing_bundle_is_rejected_before_public_writes(self) -> None:
        remote = self.approval.production.files[self.approval.fixture.wheel]
        bundle = json.loads(remote.publish or b'{}')
        bundle['raw_logs'] = 'private approval credential fixture'
        self.approval.production.files[self.approval.fixture.wheel] = replace(
            remote,
            publish=json.dumps(bundle).encode(),
        )
        self.assertEqual(self.finish().status, 'incomplete')
        self.assertEqual(self.github.writes, [])

    def test_public_history_projects_technical_outcomes_and_excludes_private_details(self) -> None:
        self.approval.reconciler.record(
            'github-incomplete',
            {'raw_logs': 'PRIVATE-LOG', 'approval': 'PRIVATE-APPROVAL', 'token': 'PRIVATE-TOKEN'},
        )
        self.assertEqual(self.finish().status, 'complete')
        report = self.github.observe(900).assets['verification-report.json']
        self.assertIn(b'github-incomplete', report)
        self.assertNotIn(b'PRIVATE-', report)
        private = self.approval.fixture.storage.history('1.2.3')
        self.assertIn('PRIVATE-TOKEN', str([record.event.details for record in private]))

    def test_github_only_resume_restores_missing_approved_content_without_approval(self) -> None:
        self.assertEqual(self.finish().status, 'complete')
        expected_report = self.github.observe(900).assets['verification-report.json']
        for identifier, (owner, asset, _data) in list(self.github.service.assets.items()):
            if owner == self.github.service.product.id and asset.name == 'verification-report.json':
                del self.github.service.assets[identifier]
        self.approval.reconciler.run = '103'
        self.github.writes.clear()
        production_writes = list(self.approval.production.writes)
        self.assertEqual(self.finish().status, 'complete')
        self.assertEqual(self.github.writes, ['verification-report.json'])
        self.assertEqual(self.approval.production.writes, production_writes)
        self.assertEqual(
            self.github.observe(900).assets['verification-report.json'], expected_report
        )

    def test_conflicting_or_private_asset_stops_without_replacement(self) -> None:
        self.github.service.upload(20, 'raw-approval.log', b'PRIVATE')
        self.assertEqual(self.finish().status, 'incomplete')
        self.assertEqual(self.github.writes, [])

    def test_missing_production_evidence_blocks_all_github_writes(self) -> None:
        name = self.approval.fixture.wheel
        self.approval.production.files[name] = replace(
            self.approval.production.files[name],
            publish=None,
        )
        self.assertEqual(self.finish().status, 'incomplete')
        self.assertEqual(self.github.writes, [])

    def test_platform_restriction_stops_and_explicit_resume_uses_unchanged_plan(self) -> None:
        attach = self.github.attach

        def restricted(name: str, data: bytes, deadline: float) -> None:  # noqa: ARG001 - Service response fixture.
            message = 'PRIVATE platform restriction'
            raise ValueError(message)

        self.github.attach = restricted
        self.assertEqual(self.finish().status, 'incomplete')
        self.assertTrue(self.github.observe(900).release.draft)
        self.github.attach = attach
        self.approval.reconciler.run = '103'
        self.assertEqual(self.finish().status, 'complete')
        self.assertNotIn(b'PRIVATE', self.github.observe(900).assets['verification-report.json'])

    def test_lost_publish_response_requires_explicit_readback_and_does_not_republish(self) -> None:
        publish = self.github.publish

        def lost(notes: str, *, prerelease: bool, make_latest: str, deadline: float) -> None:
            publish(notes, prerelease=prerelease, make_latest=make_latest, deadline=deadline)
            message = 'PRIVATE lost response'
            raise OSError(message)

        self.github.publish = lost
        self.assertEqual(self.finish().status, 'incomplete')
        self.approval.reconciler.run = '103'
        self.github.writes.clear()
        self.assertEqual(self.finish().status, 'complete')
        self.assertEqual(self.github.writes, [])

    def test_changed_notes_summary_or_tag_cannot_reuse_production_approval(self) -> None:
        review = json.loads(self.summary)
        original = self.summary
        for field, changed in (
            ('notes', 'Different claims'),
            ('assets', ['raw-approval.log']),
            ('candidate', 'f' * 64),
            ('prerelease', True),
        ):
            with self.subTest(field=field):
                self.summary = json.dumps({**review, field: changed}).encode()
                self.assertEqual(self.finish().status, 'incomplete')
        self.summary = original
        self.github.service.tag_targets['v1.2.3'] = ('c' * 40, 'commit', 'c' * 40)
        self.assertEqual(self.finish().status, 'incomplete')
        self.assertEqual(self.github.writes, [])

    def test_public_conflict_and_wrong_settings_never_trigger_replacement(self) -> None:
        self.assertEqual(self.finish().status, 'complete')
        self.github.make_latest = 'false'
        self.github.writes.clear()
        self.assertEqual(self.finish().status, 'incomplete')
        self.assertEqual(self.github.writes, [])
        self.github.make_latest = 'true'
        for identifier, (owner, asset, _data) in list(self.github.service.assets.items()):
            if asset.name == 'verification-report.json':
                self.github.service.assets[identifier] = (owner, asset, b'conflict')
        self.assertEqual(self.finish().status, 'incomplete')
        self.assertEqual(self.github.writes, [])

    def test_original_evidence_with_unscreened_private_fields_never_becomes_public(self) -> None:
        # Simulate the original publisher returning valid signed evidence plus raw logs.
        approval = approval_fixtures.ApprovalChecks()
        approval.setUp()
        self.addCleanup(approval.doCleanups)
        upload = approval.production.upload

        def unscreened(name: str, archive: bytes, build: bytes, deadline: float = 900) -> None:
            upload(name, archive, build, deadline)
            remote = approval.production.files[name]
            bundle = json.loads(remote.publish or b'{}')
            bundle['raw_logs'] = 'PRIVATE-TOKEN'
            approval.production.files[name] = replace(remote, publish=json.dumps(bundle).encode())

        approval.production.upload = unscreened
        self.approval = approval
        self.summary = approval.review()
        self.assertEqual(approval.publish(self.summary).status, 'complete')
        self.github = GitHub(approval)
        self.assertEqual(self.finish().status, 'incomplete')
        self.assertEqual(self.github.writes, [])

    def test_prerelease_finalisation_keeps_latest_stable_unchanged(self) -> None:
        self.summary = self.approval.prerelease_review()
        result = publish_production(
            self.approval.reconciler,
            self.approval.fixture.destination,
            self.approval.production,
            self.approval.read,
            self.summary,
            Approval(digest(self.summary), '102', '1'),
            self.approval.fixture.root / 'rc-production',
        )
        self.assertEqual(result.status, 'complete')
        self.github = GitHub(self.approval)
        self.assertEqual(self.finish().status, 'complete')
        observed = self.github.observe(900)
        self.assertTrue(observed.prerelease)
        self.assertEqual(observed.make_latest, 'false')
        self.assertEqual(observed.release.tag, 'v1.2.3rc1')

    def test_public_report_identifies_frozen_workflows_and_verified_builder(self) -> None:
        self.assertEqual(self.finish().status, 'complete')
        report = json.loads(self.github.observe(900).assets['verification-report.json'])
        self.assertEqual(
            report['workflows'],
            {
                'coordinator': {
                    'path': '.github/workflows/release-preparation.yml',
                    'revision': 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',
                },
                'builder': {
                    'path': '.github/workflows/release-build.yml',
                    'revision': 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',
                    'id': 'https://github.com/AxelVoitier/zensical-tarn/'
                    '.github/workflows/release-build.yml@bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',
                },
            },
        )
        review = json.loads(self.summary)
        self.assertIn('workflows', review['report_format']['fields'])
        self.assertEqual(report['source'], review['manifest']['source'])


class HostedBoundaryChecks(unittest.TestCase):
    def test_hosted_finalisation_refuses_unconditionally(self) -> None:
        fixture = coordinator_fixtures.CoordinatorChecks()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.run_cli('finalise', expected=1)
        self.assertIn('Hosted GitHub finalisation is disabled', fixture.output)

    def test_finalisation_job_is_disabled_and_has_no_package_execution(self) -> None:
        workflow = (ROOT / '.github/workflows/release-preparation.yml').read_text()
        job = workflow.split('  finalise:', 1)[1].split('  report:', 1)[0]
        self.assertIn('false &&', job)
        self.assertIn('needs: [resolve, publish-pypi]', job)
        self.assertIn('contents: write', job)
        self.assertNotIn('id-token: write', job)
        self.assertNotIn('pip install', job)
        self.assertIn('persist-credentials: false', job)


if __name__ == '__main__':
    unittest.main()
