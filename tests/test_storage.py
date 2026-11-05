# Copyright 2026 Axel Voitier
# ruff: noqa: PT009, PT027, INP001, E402
"""Local release-service scenarios at the trusted storage boundary."""

import hashlib
import json
import os
import subprocess
import sys
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from release.candidate import manifest_bytes, wheel_statement
from release.sdist import statement
from release.storage import Asset, Draft, Event, Release, Storage
from release.storage_api import GitHubAPI


class ReleaseService:
    """Mutable external-service fixture; deliberately offers paginated reads."""

    def __init__(self) -> None:
        self.admin = Draft(10, 'administrative', 'release-records', 'a' * 40, '123')
        self.product = Draft(20, 'product', 'v1.2.3', 'b' * 40, '123')
        self.releases = {
            draft.id: Release(draft.id, draft.tag, draft.target, draft.body, draft=True)
            for draft in (self.admin, self.product)
        }
        self.assets: dict[int, tuple[int, Asset, bytes]] = {}
        self.upload_outcome = 'success'
        self.tag_targets = {
            draft.tag: (draft.target, 'commit', draft.target)
            for draft in (self.admin, self.product)
        }

    def create_product(self, tag: str, target: str, body: str) -> Release:
        identifier = max(self.releases) + 1
        result = Release(identifier, tag, target, body, draft=True)
        self.releases[identifier] = result
        return result

    def tag_identity(self, tag: str) -> tuple[str, str, str]:
        return self.tag_targets[tag]

    def repository_id(self) -> str:
        return '123'

    def release(self, identifier: int) -> Release:
        return self.releases[identifier]

    def releases_page(self, page: int) -> list[Release]:
        return list(self.releases.values())[page - 1 : page]

    def assets_page(self, release: int, page: int) -> list[Asset]:
        assets = [asset for owner, asset, _data in self.assets.values() if owner == release]
        return assets[page - 1 : page]

    def asset(self, identifier: int) -> Asset:
        return self.assets[identifier][1]

    def download(self, identifier: int) -> bytes:
        return self.assets[identifier][2]

    def upload(self, release: int, name: str, data: bytes) -> None:
        if self.upload_outcome == 'before-write':
            raise OSError
        identifier = max(self.assets, default=100) + 1
        self.assets[identifier] = (release, Asset(identifier, name, len(data), 'uploaded'), data)
        if self.upload_outcome == 'lost-response':
            raise subprocess.CalledProcessError(1, ['gh', 'api'])
        if self.upload_outcome == 'cancelled':
            raise KeyboardInterrupt


class StorageChecks(unittest.TestCase):
    def test_failure_before_originals_exist_retains_preparation_history(self) -> None:
        service = ReleaseService()
        storage = Storage(service, service.admin)
        event = Event(
            '1.2.3',
            None,
            'b' * 40,
            '101',
            '1',
            1,
            'preparation-failed',
            None,
            {'recovery': 'Full preparation required; original archives never existed.'},
        )
        receipt = storage.append(event)
        self.assertIsNone(storage.history('1.2.3', receipt.digest)[0].event.candidate)
        self.assertIn('Full preparation required', str(receipt.event.details['recovery']))

    def test_moved_administrative_ref_blocks_advancement(self) -> None:
        service = ReleaseService()
        storage = Storage(service, service.admin)
        service.tag_targets['release-records'] = ('c' * 40, 'commit', 'c' * 40)
        with self.assertRaises(ValueError):
            storage.append(Event('1.2.3', 'c' * 64, 'b' * 40, '101', '1', 1, 'preparing', None, {}))
        self.assertFalse(service.assets)

    def test_event_names_fit_the_asset_api_for_long_execution_identities(self) -> None:
        event = Event(
            '123456789.123456789.123456789',
            'c' * 64,
            'b' * 40,
            '12345678901234567890',
            '12345678901234567890',
            123456789,
            'a' * 48,
            None,
            {},
        )
        self.assertLessEqual(len(event.name), 255)

    def test_authenticated_transport_uses_id_endpoints_and_verifies_downloads(self) -> None:
        service = ReleaseService()
        data = b'abc'
        service.upload(20, 'original.tar.gz', data)
        asset = next(iter(service.assets.values()))[1]
        calls: list[list[str]] = []

        def process(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
            calls.append(argv)
            self.assertEqual(argv[:5], ['gh', 'api', '--hostname', 'github.com', argv[4]])
            self.assertNotIn('fixture-token', ' '.join(argv))
            endpoint = argv[4]
            prefix = 'repos/AxelVoitier/zensical-tarn'
            if endpoint == prefix:
                result = b'{"id":123}'
            elif endpoint == prefix + '/git/ref/tags/release-records':
                result = json.dumps({'object': {'type': 'commit', 'sha': 'a' * 40}}).encode()
            elif endpoint == prefix + '/releases/10':
                admin = service.releases[10]
                result = json.dumps(
                    {
                        'id': admin.id,
                        'tag_name': admin.tag,
                        'target_commitish': admin.target,
                        'body': admin.body,
                        'draft': admin.draft,
                    },
                ).encode()
            elif endpoint == prefix + '/releases?per_page=100&page=1':
                admin = service.releases[10]
                result = json.dumps(
                    [
                        {
                            'id': admin.id,
                            'tag_name': admin.tag,
                            'target_commitish': admin.target,
                            'body': admin.body,
                            'draft': admin.draft,
                        },
                    ],
                ).encode()
            elif endpoint == prefix + '/releases?per_page=100&page=2':
                result = b'[]'
            elif endpoint == prefix + '/releases/assets/101':
                if 'Accept: application/octet-stream' in argv:
                    result = data
                else:
                    result = b'{"id":101,"name":"original.tar.gz","size":3,"state":"uploaded"}'
            elif (
                endpoint
                == 'https://uploads.github.com/'
                + prefix
                + '/releases/20/assets?name=original.tar.gz'
            ):
                self.assertEqual(kwargs['input'], b'abc')
                self.assertIn('Content-Type: application/octet-stream', argv)
                self.assertIn('Content-Length: 3', argv)
                result = b'{}'
            else:
                self.fail(f'Unexpected external request: {endpoint}')
            return subprocess.CompletedProcess(argv, 0, result, b'')

        with (
            patch.dict(os.environ, {'GH_TOKEN': 'fixture-token'}, clear=True),
            patch(
                'release.storage_api.subprocess.run',
                side_effect=process,
            ),
        ):
            api = GitHubAPI()
            Storage(api, service.admin)
            self.assertEqual(api.asset(asset.id), asset)
            self.assertEqual(api.download(asset.id), b'abc')
            api.upload(20, 'original.tar.gz', b'abc')
        self.assertTrue(calls)
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(ValueError):
            GitHubAPI().download(101)

    def test_cancelled_and_unaccepted_writes_preserve_recoverable_history(self) -> None:
        for outcome in ('cancelled', 'before-write'):
            with self.subTest(outcome=outcome):
                service = ReleaseService()
                storage = Storage(service, service.admin)
                event = Event('1.2.3', 'c' * 64, 'b' * 40, '101', '1', 1, 'preparing', None, {})
                service.upload_outcome = outcome
                expected = KeyboardInterrupt if outcome == 'cancelled' else OSError
                with self.assertRaises(expected):
                    storage.append(event)
                service.upload_outcome = 'success'
                receipt = storage.append(event)
                self.assertEqual(storage.history('1.2.3', receipt.digest)[0], receipt)
                self.assertEqual(len(service.assets), 1)

    def test_admin_incidents_stop_without_recreating_history(self) -> None:
        for incident in ('deleted', 'public', 'duplicate', 'role', 'repository', 'target'):
            with self.subTest(incident=incident):
                service = ReleaseService()
                storage = Storage(service, service.admin)
                if incident == 'deleted':
                    del service.releases[10]
                elif incident == 'public':
                    service.releases[10] = replace(service.releases[10], draft=False)
                elif incident == 'duplicate':
                    service.releases[11] = replace(service.releases[10], id=11)
                elif incident == 'role':
                    service.releases[10] = replace(service.releases[10], body=service.product.body)
                elif incident == 'target':
                    service.releases[10] = replace(service.releases[10], target='c' * 40)
                else:
                    storage.administrative = replace(service.admin, repository_id='999')
                with self.assertRaises((ValueError, KeyError)):
                    storage.history('1.2.3')
                self.assertFalse(service.assets)

    def test_conflicting_and_deleted_events_cannot_advance(self) -> None:
        service = ReleaseService()
        storage = Storage(service, service.admin)
        first = Event('1.2.3', 'c' * 64, 'b' * 40, '101', '1', 1, 'preparing', None, {})
        receipt = storage.append(first)
        for changed in (
            replace(first, details={'outcome': 'different'}),
            replace(first, run='102'),
            replace(first, sequence=2, predecessor='0' * 64),
            replace(first, sequence=3, predecessor=receipt.digest),
        ):
            with self.subTest(event=changed), self.assertRaises(ValueError):
                storage.append(changed)
        second = replace(first, sequence=2, predecessor=receipt.digest, kind='interrupted')
        final = storage.append(second)
        # Even valid extra documents at the same sequence are competing history.
        competing = replace(second, details={'outcome': 'different'})
        service.upload(10, competing.name, competing.content())
        with self.assertRaises(ValueError):
            storage.history('1.2.3')
        del service.assets[max(service.assets)]
        del service.assets[receipt.asset_id]
        with self.assertRaises(ValueError):
            storage.history('1.2.3', final.digest)
        service.assets.clear()
        with self.assertRaises(ValueError):
            storage.history('1.2.3', final.digest)

    def test_history_keeps_versions_separate_and_validates_all_private_assets(self) -> None:
        service = ReleaseService()
        storage = Storage(service, service.admin)
        first = Event('1.2.3', 'c' * 64, 'b' * 40, '101', '1', 1, 'preparing', None, {})
        receipt = storage.append(first)
        storage.append(replace(first, version='2.0.0', run='102'))
        self.assertEqual(
            [record.event.version for record in storage.history('1.2.3', receipt.digest)],
            ['1.2.3'],
        )
        service.upload(10, 'unexpected.json', b'{}')
        with self.assertRaises(ValueError):
            storage.history('1.2.3')

    def test_uncertain_write_is_reconciled_before_any_retry(self) -> None:
        service = ReleaseService()
        storage = Storage(service, service.admin)
        event = Event('1.2.3', 'c' * 64, 'b' * 40, '101', '1', 1, 'preparing', None, {})
        service.upload_outcome = 'lost-response'
        receipt = storage.append(event)
        self.assertEqual(storage.history('1.2.3', receipt.digest)[0], receipt)
        self.assertEqual(storage.append(event), receipt)
        self.assertEqual(len(service.assets), 1)

    def test_recovery_restores_originals_and_rechecks_signed_identities(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            files = root / 'files'
            files.mkdir()
            source: dict[str, object] = {
                'repository': 'AxelVoitier/zensical-tarn',
                'version': '1.2.3',
                'tag': 'v1.2.3',
                'commit': 'b' * 40,
            }
            sdist, wheel = (
                files / 'zensical_tarn-1.2.3.tar.gz',
                files / 'zensical_tarn-1.2.3-py3-none-any.whl',
            )
            sdist.write_bytes(b'abc')
            wheel.write_bytes(b'wheel')
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
            bundles = {
                'sdist.sigstore.json': json.dumps(
                    [
                        {
                            'verificationResult': {
                                'statement': statement(source, sdist, transfers['sdist']),
                            },
                        },
                    ],
                ).encode(),
                'wheel.sigstore.json': json.dumps(
                    [
                        {
                            'verificationResult': {
                                'statement': wheel_statement(
                                    source,
                                    sdist,
                                    wheel,
                                    transfers['sdist'],
                                    transfers['wheel'],
                                ),
                            },
                        },
                    ],
                ).encode(),
            }
            for name, data in bundles.items():
                (files / name).write_bytes(data)
            manifest = manifest_bytes(source, files, transfers, {'sdist': '74', 'wheel': '76'})
            candidate = hashlib.sha256(manifest).hexdigest()

            def verifier(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
                self.assertEqual(argv[:3], ['gh', 'attestation', 'verify'])
                bundle = Path(argv[argv.index('--bundle') + 1])
                self.assertEqual(bundle.read_bytes(), bundles[bundle.name])
                return subprocess.CompletedProcess(argv, 0, bundle.read_text(), '')

            service = ReleaseService()
            storage = Storage(service, service.admin)
            with patch('release.sdist.subprocess.run', side_effect=verifier):
                event = Event(
                    '1.2.3',
                    candidate,
                    'b' * 40,
                    '101',
                    '1',
                    1,
                    'recovery-stored',
                    None,
                    {},
                )
                service.upload_outcome = 'cancelled'
                with self.assertRaises(KeyboardInterrupt):
                    storage.retain(service.product, source, manifest, candidate, files, event)
                self.assertEqual(storage.history('1.2.3'), [])
                self.assertEqual(len(service.assets), 1)
                service.upload_outcome = 'success'
                copy = storage.retain(service.product, source, manifest, candidate, files, event)
                # Repeating retention reuses the original product and event IDs.
                self.assertEqual(
                    storage.retain(service.product, source, manifest, candidate, files, event),
                    copy,
                )
                shutil_target = root / 'restored'
                storage.recover(copy, source, shutil_target)
                self.assertEqual((shutil_target / 'files' / sdist.name).read_bytes(), b'abc')
                self.assertEqual((shutil_target / 'candidate.json').read_bytes(), manifest)
                for wrong_product in (
                    service.admin,
                    replace(service.product, id=10),
                    replace(service.product, repository_id='999'),
                ):
                    with self.subTest(product=wrong_product), self.assertRaises(ValueError):
                        storage.recover(
                            replace(copy, product=wrong_product),
                            source,
                            root / 'wrong',
                        )
                # An archive substitution cannot be accepted by recomputing API metadata.
                identifier = copy.assets[sdist.name].id
                owner, asset, _data = service.assets[identifier]
                service.assets[identifier] = (owner, replace(asset, size=7), b'changed')
                with self.assertRaises(ValueError):
                    storage.recover(copy, source, root / 'substituted')
            self.assertEqual(storage.history('1.2.3')[-1].event.kind, 'recovery-stored')

    def test_history_survives_product_deletion_and_paginates(self) -> None:
        service = ReleaseService()
        storage = Storage(service, service.admin)
        first = Event('1.2.3', 'c' * 64, 'b' * 40, '101', '1', 1, 'preparing', None, {})
        receipt = storage.append(first)
        second = replace(first, sequence=2, kind='interrupted', predecessor=receipt.digest)
        final = storage.append(second)
        del service.releases[20]
        history = storage.history('1.2.3', final.digest)
        self.assertEqual([entry.event.kind for entry in history], ['preparing', 'interrupted'])
        self.assertEqual(storage.append(second), final)


if __name__ == '__main__':
    unittest.main()
