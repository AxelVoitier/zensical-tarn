# Copyright 2026 Axel Voitier
# ruff: noqa: PT009, PT027, INP001, E402
"""Controlled publication through the public stage; external writes stay disabled."""

import base64
import json
import os
import shutil
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
import test_coordinator as coordinator_fixtures
import test_reconciliation as fixtures
from check_testpypi import install
from release import coordinator
from release.reconciliation import Reconciler
from release.storage import Release, Storage
from release.testpypi import PreparedDestination, publish, upload_attestations


class TestPyPIChecks(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = fixtures.ReconciliationChecks()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def test_retained_originals_are_retrieved_for_checks_after_publication(self) -> None:
        fixture = self.fixture
        output = fixture.root / 'retrieved'
        result = publish(
            Reconciler(
                fixture.storage,
                fixture.retained,
                fixture.source,
                '102',
                '1',
                fixture.storage.history('1.2.3')[-1].digest,
                fixture.verifier,
                fixture.clock,
            ),
            fixture.destination,
            fixture.publisher,
            output,
        )
        self.assertEqual(result.status, 'complete')
        self.assertEqual((output / 'files' / fixture.wheel).read_bytes(), b'wheel')
        self.assertEqual((output / 'files' / fixture.sdist).read_bytes(), b'abc')
        self.assertTrue((output / 'files' / 'wheel.sigstore.json').is_file())
        self.assertTrue((output / 'publishing' / (fixture.wheel + '.json')).is_file())

    def test_missing_originals_never_reach_the_destination(self) -> None:
        fixture = self.fixture
        asset = fixture.retained.assets[fixture.wheel]
        del fixture.service.assets[asset.id]
        result = self.publish()
        self.assertEqual(result.status, 'incomplete')
        self.assertEqual(fixture.destination.writes, [])
        self.assertFalse((fixture.root / 'retrieved').exists())

    def publish(self) -> fixtures.Outcome:
        fixture = self.fixture
        return publish(
            Reconciler(
                fixture.storage,
                fixture.retained,
                fixture.source,
                '102',
                '1',
                fixture.storage.history('1.2.3')[-1].digest,
                fixture.verifier,
                fixture.clock,
            ),
            fixture.destination,
            fixture.publisher,
            fixture.root / 'retrieved',
        )

    def test_partial_acceptance_resumes_only_the_missing_original(self) -> None:
        fixture = self.fixture
        fixture.destination.outcome = 'cancelled'
        with self.assertRaises(KeyboardInterrupt):
            self.publish()
        fixture.destination.outcome = 'returned'
        self.assertEqual(self.publish().status, 'complete')
        self.assertEqual(fixture.destination.writes, [fixture.sdist, fixture.wheel])

    def test_wrong_coordinator_identity_is_rejected_before_upload(self) -> None:
        fixture = self.fixture
        fixture.publisher = fixtures.replace(fixture.publisher, environment='pypi')
        with self.assertRaises(ValueError):
            self.publish()
        self.assertEqual(fixture.destination.writes, [])

    def test_retrieval_failure_does_not_expose_a_candidate_to_installation(self) -> None:
        fixture = self.fixture
        # First two writes and final reconciliation observation consume five reads.
        fixture.destination.unavailable_at = {6}
        self.assertEqual(self.publish().status, 'incomplete')
        self.assertFalse((fixture.root / 'retrieved').exists())
        last = fixture.storage.history('1.2.3')[-1].event
        self.assertEqual(last.kind, 'testpypi-incomplete')

    def test_upload_conversion_preserves_signed_payload_and_signature(self) -> None:
        # Whitespace and key order are part of the signed bytes, not JSON semantics.
        payload = base64.b64encode(
            b'{ "predicateType": "https://slsa.dev/provenance/v1" }',
        ).decode()
        bundle = {
            'mediaType': 'application/vnd.dev.sigstore.bundle.v0.3+json',
            'verificationMaterial': {
                'certificate': {'rawBytes': 'Y2VydA=='},
                'tlogEntries': [{'logIndex': '1'}],
            },
            'dsseEnvelope': {
                'payloadType': 'application/vnd.in-toto+json',
                'payload': payload,
                'signatures': [{'sig': 'c2ln'}],
            },
        }
        publish_bundle = json.loads(json.dumps(bundle))
        publish_bundle['dsseEnvelope']['payload'] = base64.b64encode(
            b'{"predicateType":"https://docs.pypi.org/attestations/publish/v1"}',
        ).decode()
        original = json.dumps(bundle).encode()
        converted = json.loads(upload_attestations(original, json.dumps(publish_bundle).encode()))
        self.assertEqual(len(converted), 2)
        self.assertEqual(converted[0]['envelope'], {'statement': payload, 'signature': 'c2ln'})
        self.assertEqual(converted[0]['verification_material']['certificate'], 'Y2VydA==')
        self.assertEqual(json.loads(original), bundle)

    def test_both_attestations_are_in_the_initial_upload(self) -> None:
        fixture = self.fixture

        def bundle(statement: object) -> bytes:
            return fixtures.canonical(
                {
                    'mediaType': 'application/vnd.dev.sigstore.bundle.v0.3+json',
                    'verificationMaterial': {
                        'certificate': {'rawBytes': 'Y2VydA=='},
                        'tlogEntries': [{'logIndex': '1'}],
                    },
                    'dsseEnvelope': {
                        'payloadType': 'application/vnd.in-toto+json',
                        'payload': base64.b64encode(fixtures.canonical(statement)).decode(),
                        'signatures': [{'sig': 'c2ln'}],
                    },
                },
            )

        signed: dict[str, object] = {
            '_type': 'https://in-toto.io/Statement/v1',
            'subject': [{'name': fixture.wheel, 'digest': {'sha256': fixtures.digest(b'wheel')}}],
            'predicateType': 'https://docs.pypi.org/attestations/publish/v1',
            'predicate': {},
        }
        publishing = bundle(signed)

        class Signer:
            def sign(self, name: str, archive: bytes, deadline: float) -> bytes:
                return publishing

        class Verifier:
            def verify(self, bundle: bytes, deadline: float) -> fixtures.Publication:
                payload = json.loads(
                    base64.b64decode(json.loads(bundle)['dsseEnvelope']['payload']),
                )
                return fixtures.Publication(fixture.publisher, payload)

        class Transport:
            def __init__(self) -> None:
                self.writes: list[str] = []
                self.evidence: list[object] = []

            def observe(self, deadline: float) -> dict[str, fixtures.RemoteFile]:
                return {}

            def upload(
                self,
                name: str,
                archive: bytes,
                attestations: bytes,
                deadline: float = 900,
            ) -> None:
                self.writes.append(name)
                evidence = json.loads(attestations)
                self.evidence = evidence

        transport = Transport()
        destination = PreparedDestination(transport, Signer(), Verifier(), fixture.publisher)
        destination.upload(
            fixture.wheel,
            b'wheel',
            bundle({'predicateType': 'https://slsa.dev/provenance/v1'}),
            900,
        )
        self.assertEqual(transport.writes, [fixture.wheel])
        self.assertEqual(len(transport.evidence), 2)

    def test_installation_uses_the_retrieved_wheel_in_a_fresh_environment(self) -> None:
        fixture = self.fixture
        self.assertEqual(self.publish().status, 'complete')
        commands: list[list[str]] = []
        # Keep the pre-existing external signature-verifier response fixture.
        # Package execution is observed at its subprocess boundary in this unit scenario.
        verifier = fixtures.subprocess.run

        def observe(argv: list[str], **kwargs: object) -> fixtures.subprocess.CompletedProcess[str]:
            if argv[0] == 'gh':
                return verifier(argv, **kwargs)  # type: ignore[return-value]
            commands.append(argv)
            return fixtures.subprocess.CompletedProcess(argv, 0, '', '')

        with patch('subprocess.run', side_effect=observe):
            install(
                ROOT,
                fixture.root / 'retrieved',
                fixture.source,
                fixture.retained.candidate,
                fixture.root / 'clean',
            )
        self.assertEqual(commands[1][-1], str(fixture.root / 'retrieved/files' / fixture.wheel))
        self.assertEqual(
            [Path(command[1]).name for command in commands[2:]],
            ['check_package.py', 'check_config.py'],
        )
        self.assertIn('venv', commands[0])


class CoordinatorPublicationChecks(unittest.TestCase):
    def test_normal_and_original_tag_resume_share_the_retained_candidate(self) -> None:
        fixture = coordinator_fixtures.CoordinatorChecks()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        receipt = fixture.directory / 'receipt.json'
        admitted = fixture.run_cli('admit', '--output', str(receipt))
        candidate = fixture.make_candidate()

        # New product creation is an external API response fixture.
        def create_product(tag: str, target: str, body: str) -> Release:
            product = Release(20, tag, target, body, draft=True)
            fixture.service.releases[20] = product
            return product

        with patch.object(coordinator.GitHubAPI, 'create_product', side_effect=create_product):
            retained = fixture.run_cli(
                'retain',
                '--head',
                str(admitted['head']),
                '--candidate-dir',
                str(candidate),
                '--candidate-digest',
                fixture.candidate_digest,
            )
        admitted['head'] = retained['admission-head']
        publisher = fixtures.Publisher(
            'AxelVoitier/zensical-tarn',
            'release-preparation.yml',
            fixture.commit,
            'testpypi',
        )
        destination = fixtures.Destination(publisher)
        storage = Storage(fixture.service, fixture.service.admin)
        with (
            patch.dict(os.environ, fixture.environ),
            patch('subprocess.run', side_effect=fixture.process),
            patch('urllib.request.urlopen', side_effect=fixture.registry_response),
        ):
            result = coordinator.testpypi(
                fixture.root,
                storage,
                str(admitted['head']),
                destination,
                fixtures.Verifier(),
                destination.clock,
                fixture.directory / 'retrieved',
            )
        self.assertEqual(result.status, 'complete')
        self.assertEqual(
            (fixture.directory / 'retrieved/files/zensical_tarn-1.2.3.tar.gz').read_bytes(),
            b'original source',
        )
        fixture.environ.update(GITHUB_EVENT_NAME='workflow_dispatch', GITHUB_RUN_ID='102')
        fixture.event = {'inputs': {'mode': 'resume'}}
        resumed = fixture.run_cli('admit', '--output', str(receipt))
        # No builder is available and the original transient candidate is removed.
        shutil.rmtree(candidate)
        destination.writes.clear()
        with (
            patch.dict(os.environ, fixture.environ),
            patch('subprocess.run', side_effect=fixture.process),
            patch('urllib.request.urlopen', side_effect=fixture.registry_response),
        ):
            result = coordinator.testpypi(
                fixture.root,
                storage,
                str(resumed['head']),
                destination,
                fixtures.Verifier(),
                destination.clock,
                fixture.directory / 'resumed',
            )
        self.assertEqual(result.status, 'complete')
        self.assertEqual(destination.writes, [])


class WorkflowBoundaryChecks(unittest.TestCase):
    def test_publisher_is_disabled_and_package_checks_have_no_publishing_authority(self) -> None:
        workflow = (ROOT / '.github/workflows/release-preparation.yml').read_text()
        publisher = workflow.split('  publish-testpypi:', 1)[1].split('  verify-testpypi:', 1)[0]
        self.assertIn('false && always()', publisher)
        self.assertIn('environment: testpypi', publisher)
        self.assertIn('id-token: write', publisher)
        self.assertNotIn('contents: write', publisher)
        self.assertNotIn('pip install', publisher)
        self.assertIn('--uploads-disabled', publisher)
        self.assertIn('needs: [resolve, retain, resume]', publisher)
        consumer = workflow.split('  verify-testpypi:', 1)[1].split('  report:', 1)[0]
        self.assertIn('retrieved-testpypi: true', consumer)
        self.assertNotIn('id-token: write', consumer)
        self.assertNotIn('contents: write', consumer)
        self.assertIn("outputs.retrieved-artifact-id != ''", consumer)
        self.assertIn('needs: [resolve, build]', workflow.split('  retain:', 1)[1])

    def test_hosted_cli_refuses_uploads_even_without_the_disabled_flag(self) -> None:
        fixture = coordinator_fixtures.CoordinatorChecks()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.run_cli('testpypi', expected=1)
        self.assertIn('Hosted TestPyPI uploads are disabled', fixture.output)


if __name__ == '__main__':
    unittest.main()
