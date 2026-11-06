# Copyright 2026 Axel Voitier
# ruff: noqa: PT009, PT027, INP001, E402
"""Candidate boundaries use original bytes, not producer reports."""

import hashlib
import io
import json
import shutil
import subprocess
import sys
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from release.candidate import (
    check_wheel_statement,
    manifest_bytes,
    validate_manifest,
    verify_candidate,
    wheel_statement,
)
from release.sdist import select_files, statement
from release_context import GITHUB_CONTEXT


class CandidateChecks(unittest.TestCase):
    def test_wheel_statement_requires_exact_source_archive_input(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            sdist = root / 'zensical_tarn-1.2.3.tar.gz'
            wheel = root / 'zensical_tarn-1.2.3-py3-none-any.whl'
            sdist.write_bytes(b'abc')
            wheel.write_bytes(b'wheel')
            identity: dict[str, object] = {'version': '1.2.3', 'tag': 'v1.2.3', 'commit': 'a' * 40}
            source_transfer = {
                **GITHUB_CONTEXT,
                'run_id': '101',
                'run_attempt': '2',
                'artifact_id': '73',
            }
            wheel_transfer = {
                **GITHUB_CONTEXT,
                'run_id': '101',
                'run_attempt': '2',
                'artifact_id': '75',
            }
            signed = wheel_statement(identity, sdist, wheel, source_transfer, wheel_transfer)
            definition = json.loads(json.dumps(signed))['predicate']['buildDefinition']
            self.assertEqual(
                definition['resolvedDependencies'][-1],
                {
                    'uri': 'zensical_tarn-1.2.3.tar.gz',
                    'digest': {
                        'sha256': (
                            'ba7816bf8f01cfea414140de5dae2223'
                            'b00361a396177a9cb410ff61f20015ad'
                        ),
                    },
                },
            )
            check_wheel_statement(signed, identity, sdist, wheel, source_transfer, wheel_transfer)
            for field in ('resolvedDependencies', 'internalParameters', 'externalParameters'):
                changed = json.loads(json.dumps(signed))
                del changed['predicate']['buildDefinition'][field]
                with self.subTest(field=field), self.assertRaises(ValueError):
                    check_wheel_statement(
                        changed,
                        identity,
                        sdist,
                        wheel,
                        source_transfer,
                        wheel_transfer,
                    )
            sdist.write_bytes(b'substituted')
            with self.assertRaises(ValueError):
                check_wheel_statement(
                    signed,
                    identity,
                    sdist,
                    wheel,
                    source_transfer,
                    wheel_transfer,
                )

    def test_wheel_transfer_rejects_reports_and_wrong_producer(self) -> None:
        stream = io.BytesIO()
        name = 'zensical_tarn-1.2.3-py3-none-any.whl'
        with zipfile.ZipFile(stream, 'w') as archive:
            archive.writestr(name, b'wheel')
        data = stream.getvalue()
        metadata: dict[str, object] = {
            'id': 75,
            'name': 'wheel-101-2',
            'expired': False,
            'digest': 'sha256:' + hashlib.sha256(data).hexdigest(),
            'workflow_run': {
                'id': 101,
                'head_sha': 'a' * 40,
                'repository_id': 123,
                'head_repository_id': 123,
            },
        }
        files, transfer = select_files(
            data,
            metadata,
            {name: 1024},
            'wheel',
            commit='a' * 40,
            run='101',
            attempt='2',
            repository_id='123',
            artifact_id='75',
        )
        self.assertEqual(files, {name: b'wheel'})
        self.assertEqual(transfer['artifact_id'], '75')
        for changed in (
            {**metadata, 'name': 'wheel-101-1'},
            {**metadata, 'id': 76},
            {**metadata, 'digest': 'sha256:' + '0' * 64},
        ):
            with self.subTest(metadata=changed), self.assertRaises(ValueError):
                select_files(
                    data,
                    changed,
                    {name: 1024},
                    'wheel',
                    commit='a' * 40,
                    run='101',
                    attempt='2',
                    repository_id='123',
                    artifact_id='75',
                )
        with zipfile.ZipFile(stream, 'a') as archive:
            archive.writestr('build-report.json', '{"input": "arbitrary"}')
        data = stream.getvalue()
        metadata['digest'] = 'sha256:' + hashlib.sha256(data).hexdigest()
        with self.assertRaisesRegex(ValueError, 'selected artifact files'):
            select_files(
                data,
                metadata,
                {name: 1024},
                'wheel',
                commit='a' * 40,
                run='101',
                attempt='2',
                repository_id='123',
                artifact_id='75',
            )

    def test_manifest_freezes_exact_files_evidence_and_identities(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for name, data in (
                ('zensical_tarn-1.2.3.tar.gz', b'abc'),
                ('zensical_tarn-1.2.3-py3-none-any.whl', b'wheel'),
                ('sdist.sigstore.json', b'original source evidence'),
                ('wheel.sigstore.json', b'original wheel evidence'),
            ):
                (root / name).write_bytes(data)
            identity: dict[str, object] = {'version': '1.2.3', 'commit': 'a' * 40}
            transfers = {
                'sdist': {
                    **GITHUB_CONTEXT,
                    'run_id': '101',
                    'run_attempt': '2',
                    'artifact_id': '73',
                    'artifact_name': 'sdist-101-2',
                    'transport_digest': 'sha256:' + 'd' * 64,
                },
                'wheel': {
                    **GITHUB_CONTEXT,
                    'run_id': '101',
                    'run_attempt': '2',
                    'artifact_id': '75',
                    'artifact_name': 'wheel-101-2',
                    'transport_digest': 'sha256:' + 'e' * 64,
                },
            }
            identifiers = {'sdist': '74', 'wheel': '76'}
            frozen = manifest_bytes(identity, root, transfers, identifiers)
            digest = hashlib.sha256(frozen).hexdigest()
            validate_manifest(frozen, digest, identity, root)
            document = json.loads(frozen)
            self.assertEqual(document['schema'], 'tarn-candidate-v1')
            self.assertEqual(
                document['wheel_input_sha256'],
                'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad',
            )
            for key, value in (
                ('schema', 'future'),
                ('observations', ['unexpected']),
                ('wheel_input_sha256', '0' * 64),
                ('source', {'unexpected': 'source'}),
            ):
                changed = {**document, key: value}
                data = (json.dumps(changed, sort_keys=True, separators=(',', ':')) + '\n').encode()
                with self.subTest(key=key), self.assertRaises(ValueError):
                    validate_manifest(data, hashlib.sha256(data).hexdigest(), identity, root)
            with self.assertRaises(ValueError):
                validate_manifest(frozen + b' ', digest, identity, root)
            (root / 'unexpected.whl').write_bytes(b'extra')
            with self.assertRaisesRegex(ValueError, 'exact candidate files'):
                validate_manifest(frozen, digest, identity, root)
            (root / 'unexpected.whl').unlink()
            wheel_path = root / 'zensical_tarn-1.2.3-py3-none-any.whl'
            wheel_path.write_bytes(b'')
            with self.assertRaisesRegex(ValueError, 'size'):
                manifest_bytes(identity, root, transfers, identifiers)
            wheel_path.write_bytes(b'wheel')
            (root / 'wheel.sigstore.json').write_bytes(b'replaced evidence')
            with self.assertRaises(ValueError):
                validate_manifest(frozen, digest, identity, root)

    @unittest.skipUnless(shutil.which('openssl'), 'Local signed evidence needs OpenSSL')
    def test_candidate_checks_original_signatures_and_rejects_two_unrelated_outputs(self) -> None:  # noqa: PLR0915 - One external signature-boundary fixture.
        with TemporaryDirectory() as directory:
            root = Path(directory)
            files = root / 'files'
            files.mkdir()
            sdist = files / 'zensical_tarn-1.2.3.tar.gz'
            wheel = files / 'zensical_tarn-1.2.3-py3-none-any.whl'
            sdist.write_bytes(b'abc')
            wheel.write_bytes(b'wheel')
            identity: dict[str, object] = {'version': '1.2.3', 'tag': 'v1.2.3', 'commit': 'a' * 40}
            transfers = {
                kind: {
                    **GITHUB_CONTEXT,
                    'run_id': '101',
                    'run_attempt': '2',
                    'artifact_id': artifact,
                    'artifact_name': f'{kind}-101-2',
                    'transport_digest': 'sha256:' + 'd' * 64,
                }
                for kind, artifact in (('sdist', '73'), ('wheel', '75'))
            }
            private, public = root / 'private.pem', root / 'public.pem'
            real_run = subprocess.run
            real_run(
                [
                    'openssl',
                    'ecparam',
                    '-name',
                    'prime256v1',
                    '-genkey',
                    '-noout',
                    '-out',
                    str(private),
                ],
                check=True,
                capture_output=True,
            )
            real_run(
                ['openssl', 'pkey', '-in', str(private), '-pubout', '-out', str(public)],
                check=True,
                capture_output=True,
            )

            def sign(kind: str, payload: object) -> None:
                bundle = files / f'{kind}.sigstore.json'
                bundle.write_text(
                    json.dumps([{'verificationResult': {'statement': payload}}]),
                    encoding='utf-8',
                )
                real_run(
                    [
                        'openssl',
                        'dgst',
                        '-sha256',
                        '-sign',
                        str(private),
                        '-out',
                        str(root / f'{kind}.sig'),
                        str(bundle),
                    ],
                    check=True,
                    capture_output=True,
                )

            def verifier(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
                self.assertEqual(argv[:3], ['gh', 'attestation', 'verify'])
                self.assertEqual(argv[argv.index('--source-digest') + 1], 'a' * 40)
                self.assertEqual(argv[argv.index('--signer-digest') + 1], 'a' * 40)
                bundle = Path(argv[argv.index('--bundle') + 1])
                kind = bundle.name.split('.')[0]
                real_run(
                    [
                        'openssl',
                        'dgst',
                        '-sha256',
                        '-verify',
                        str(public),
                        '-signature',
                        str(root / f'{kind}.sig'),
                        str(bundle),
                    ],
                    check=True,
                    capture_output=True,
                )
                return subprocess.CompletedProcess(argv, 0, bundle.read_text(encoding='utf-8'), '')

            source_statement = statement(identity, sdist, transfers['sdist'])
            wheel_payload = wheel_statement(
                identity,
                sdist,
                wheel,
                transfers['sdist'],
                transfers['wheel'],
            )
            sign('sdist', source_statement)
            sign('wheel', wheel_payload)
            identifiers = {'sdist': '74', 'wheel': '76'}

            def verify() -> None:
                data = manifest_bytes(identity, files, transfers, identifiers)
                verify_candidate(data, hashlib.sha256(data).hexdigest(), identity, files)

            with patch('release.sdist.subprocess.run', side_effect=verifier):
                verify()
                for change in ('missing input', 'wrong builder', 'wrong source', 'wrong subject'):
                    payload = json.loads(json.dumps(wheel_payload))
                    if change == 'missing input':
                        payload['predicate']['buildDefinition']['resolvedDependencies'].pop()
                    elif change == 'wrong builder':
                        payload['predicate']['runDetails']['builder']['id'] = 'unexpected'
                    elif change == 'wrong source':
                        payload['predicate']['buildDefinition']['internalParameters']['source'][
                            'commit'
                        ] = 'b' * 40
                    else:
                        payload['subject'][0]['digest']['sha256'] = '0' * 64
                    sign('wheel', payload)
                    with self.subTest(change=change), self.assertRaises(ValueError):
                        verify()
                sign('wheel', wheel_payload)
                # Even a freshly rehashed manifest cannot make damaged signed bytes valid.
                bundle = files / 'wheel.sigstore.json'
                bundle.write_bytes(bundle.read_bytes() + b' ')
                with self.assertRaises(subprocess.CalledProcessError):
                    verify()
