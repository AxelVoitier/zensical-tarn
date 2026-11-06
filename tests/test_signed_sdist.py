# Copyright 2026 Axel Voitier
"""Local evidence checks; these do not establish a hosted certificate identity."""
# ruff: noqa: PT009, PT027, INP001, E402, S603, S607

import hashlib
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
from check_release import git
from release.sdist import (
    check_statement,
    platform_context,
    select_archive,
    statement,
    verify_bundle,
)
from release_context import GITHUB_CONTEXT


class SignedSdistChecks(unittest.TestCase):
    def test_frozen_source_distinguishes_tag_objects_from_lightweight_refs(self) -> None:
        """Select source without running a package version hook."""
        with TemporaryDirectory() as directory:
            root = Path(directory)
            git(root, 'init', '--quiet')
            git(root, 'config', 'user.name', 'Tarn tests')
            git(root, 'config', 'user.email', 'tests@example.invalid')
            (root / 'pyproject.toml').write_text(
                '[dependency-groups]\nrelease = ["build==1.6.1"]\n',
                encoding='utf-8',
            )
            git(root, 'add', '.')
            git(root, '-c', 'commit.gpgsign=false', 'commit', '--quiet', '-m', 'Source')
            commit = git(root, 'rev-parse', 'HEAD')
            for annotated in (False, True):
                with self.subTest(annotated=annotated):
                    if annotated:
                        git(root, '-c', 'tag.gpgsign=false', 'tag', '-a', 'v1.2.3rc1', '-m', 'Tag')
                    else:
                        git(root, '-c', 'tag.gpgsign=false', 'tag', 'v1.2.3rc1')
                    result = self.command('identity', root, 'v1.2.3rc1', commit)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    identity = json.loads(result.stdout)
                    self.assertEqual(identity['commit'], commit)
                    self.assertEqual(identity['tag_ref_type'], 'tag' if annotated else 'commit')
                    self.assertEqual(
                        identity['tag_ref_target'],
                        git(root, 'rev-parse', 'v1.2.3rc1'),
                    )
                    self.assertEqual(identity['version'], '1.2.3rc1')
                    if annotated:
                        git(
                            root,
                            '-c',
                            'tag.gpgsign=false',
                            'tag',
                            '-f',
                            '-a',
                            'v1.2.3rc1',
                            '-m',
                            'Replaced at the same commit',
                        )
                        rejected = self.command(
                            'identity',
                            root,
                            'v1.2.3rc1',
                            commit,
                            '--tag-ref-target',
                            identity['tag_ref_target'],
                            '--tag-ref-type',
                            'tag',
                        )
                        self.assertNotEqual(rejected.returncode, 0)
                        self.assertIn('Frozen tag target or type changed', rejected.stderr)
                    git(root, 'tag', '-d', 'v1.2.3rc1')

    def test_signing_stage_selects_and_hashes_only_the_identified_archive(self) -> None:
        """Reject transport substitution before constructing protected fields."""
        with TemporaryDirectory() as directory:
            work = Path(directory)
            archive = work / 'selected.zip'
            with zipfile.ZipFile(archive, 'w') as bundle:
                bundle.writestr('zensical_tarn-1.2.3.tar.gz', b'abc')
            metadata = {
                'id': 73,
                'name': 'sdist-101-2',
                'expired': False,
                'digest': 'sha256:' + hashlib.sha256(archive.read_bytes()).hexdigest(),
                'workflow_run': {
                    'id': 101,
                    'head_sha': 'a' * 40,
                    'repository_id': 123,
                    'head_repository_id': 123,
                },
            }

            selected, transport = select_archive(
                archive.read_bytes(),
                metadata,
                work / 'selected',
                '1.2.3',
                commit='a' * 40,
                run='101',
                attempt='2',
                repository_id='123',
                artifact_id='73',
            )
            self.assertEqual(selected.name, 'zensical_tarn-1.2.3.tar.gz')
            self.assertEqual(transport['artifact_id'], '73')
            self.assertEqual(selected.read_bytes(), b'abc')
            with self.assertRaisesRegex(ValueError, 'transport digest'):
                select_archive(
                    archive.read_bytes() + b'changed',
                    metadata,
                    work / 'bad',
                    '1.2.3',
                    commit='a' * 40,
                    run='101',
                    attempt='2',
                    repository_id='123',
                    artifact_id='73',
                )
            for field, value in (('name', 'another artifact'), ('id', 74), ('expired', True)):
                with self.subTest(field=field), self.assertRaises(ValueError):
                    select_archive(
                        archive.read_bytes(),
                        {**metadata, field: value},
                        work / 'bad',
                        '1.2.3',
                        commit='a' * 40,
                        run='101',
                        attempt='2',
                        repository_id='123',
                        artifact_id='73',
                    )

    def test_verified_statement_must_match_frozen_policy_and_selected_bytes(self) -> None:
        """Treat verified statements as data and enforce every protected field."""

        with TemporaryDirectory() as directory:
            archive = Path(directory) / 'zensical_tarn-1.2.3.tar.gz'
            archive.write_bytes(b'abc')
            identity: dict[str, object] = {
                'repository': 'AxelVoitier/zensical-tarn',
                'version': '1.2.3',
                'tag': 'v1.2.3',
                'commit': 'a' * 40,
                'tree': 'b' * 40,
                'source_date_epoch': 123,
                'tag_ref_target': 'c' * 40,
                'tag_ref_type': 'tag',
                'coordinator': {
                    'path': '.github/workflows/release-preparation.yml',
                    'revision': 'a' * 40,
                },
                'builder': {'path': '.github/workflows/release-build.yml', 'revision': 'a' * 40},
                'toolchain': {'build': '1.6.1'},
            }
            transport = {
                **GITHUB_CONTEXT,
                'run_id': '101',
                'run_attempt': '2',
                'artifact_id': '73',
                'artifact_name': 'sdist-101-2',
                'transport_digest': 'sha256:' + 'd' * 64,
            }
            expected = json.loads(
                (ROOT / 'tests/fixtures/sdist/statement.json').read_text(encoding='utf-8'),
            )
            self.assertEqual(statement(identity, archive, transport), expected)
            check_statement(expected, identity, archive, transport)
            text = json.dumps(expected)
            for old, new in (
                ('a' * 40, 'e' * 40),
                ('v1.2.3', 'v1.2.4'),
                ('ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad', '0' * 64),
                ('release-build.yml', 'evil.yml'),
                ('"run_attempt": "2"', '"run_attempt": "3"'),
                ('"event_name": "push"', '"event_name": "workflow_dispatch"'),
                ('"repository_owner_id": "456"', '"repository_owner_id": "789"'),
                ('github-hosted', 'self-hosted'),
            ):
                with self.subTest(change=old), self.assertRaises(ValueError):
                    check_statement(
                        json.loads(text.replace(old, new)),
                        identity,
                        archive,
                        transport,
                    )
            archive.write_bytes(b'substitute')
            with self.assertRaises(ValueError):
                check_statement(expected, identity, archive, transport)

    @unittest.skipUnless(shutil.which('openssl'), 'Local signing fixture needs OpenSSL')
    def test_signature_verifier_rejects_changed_signed_bytes(self) -> None:
        """Use real local signatures at the external verifier boundary, never hosted credentials."""

        with TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / 'zensical_tarn-1.2.3.tar.gz'
            archive.write_bytes(b'abc')
            identity: dict[str, object] = {'version': '1.2.3', 'tag': 'v1.2.3', 'commit': 'a' * 40}
            transport = {**GITHUB_CONTEXT, 'run_id': '101', 'run_attempt': '2'}
            expected = statement(identity, archive, transport)
            evidence = root / 'local-evidence.json'
            evidence.write_text(
                json.dumps([{'verificationResult': {'statement': expected}}]),
                encoding='utf-8',
            )
            private, public, signature = (
                root / name for name in ('private.pem', 'public.pem', 'signature')
            )
            subprocess.run(
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
            subprocess.run(
                ['openssl', 'pkey', '-in', str(private), '-pubout', '-out', str(public)],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                [
                    'openssl',
                    'dgst',
                    '-sha256',
                    '-sign',
                    str(private),
                    '-out',
                    str(signature),
                    str(evidence),
                ],
                check=True,
                capture_output=True,
            )
            real_run = subprocess.run

            def local_verifier(
                argv: list[str],
                **_kwargs: object,
            ) -> subprocess.CompletedProcess[str]:
                # Replace the external verifier with local signature verification.
                # Hosted certificate validation remains untested.
                self.assertIn('--deny-self-hosted-runners', argv)
                self.assertEqual(argv[argv.index('--signer-digest') + 1], 'a' * 40)
                self.assertEqual(argv[argv.index('--source-digest') + 1], 'a' * 40)
                self.assertEqual(
                    argv[argv.index('--signer-workflow') + 1],
                    'AxelVoitier/zensical-tarn/.github/workflows/release-build.yml',
                )
                real_run(
                    [
                        'openssl',
                        'dgst',
                        '-sha256',
                        '-verify',
                        str(public),
                        '-signature',
                        str(signature),
                        str(evidence),
                    ],
                    check=True,
                    capture_output=True,
                )
                return subprocess.CompletedProcess(
                    argv,
                    0,
                    evidence.read_text(encoding='utf-8'),
                    '',
                )

            with patch('release.sdist.subprocess.run', side_effect=local_verifier):
                verify_bundle(archive, evidence, identity, transport)
                evidence.write_text(evidence.read_text(encoding='utf-8') + ' ', encoding='utf-8')
                with self.assertRaises(subprocess.CalledProcessError):
                    verify_bundle(archive, evidence, identity, transport)

    def test_hosted_stage_rejects_context_from_a_different_workflow_revision(self) -> None:
        """A caller cannot select trusted helpers from another source revision."""

        context = {
            'GITHUB_REPOSITORY': 'AxelVoitier/zensical-tarn',
            'GITHUB_SHA': 'a' * 40,
            'GITHUB_REF': 'refs/tags/v1.2.3',
            'GITHUB_WORKFLOW_SHA': 'a' * 40,
            'GITHUB_WORKFLOW_REF': (
                'AxelVoitier/zensical-tarn/'
                '.github/workflows/release-preparation.yml@refs/tags/v1.2.3'
            ),
            'GITHUB_RUN_ID': '101',
            'GITHUB_RUN_ATTEMPT': '2',
            'GITHUB_REPOSITORY_ID': '123',
        }
        self.assertEqual(platform_context(context, 'v1.2.3', 'a' * 40), ('101', '2', '123'))
        for field in context:
            with self.subTest(field=field), self.assertRaises(ValueError):
                platform_context({**context, field: 'unexpected'}, 'v1.2.3', 'a' * 40)

    def test_stage_rejects_noncanonical_versions_before_git_or_package_execution(self) -> None:
        """Support only canonical product tags, including prereleases and post releases."""
        for tag in (
            '1.2.3',
            'v01.2.3',
            'v1.2',
            'v1.2.3.dev1',
            'v1.2.3+local',
            'v1.2.3rc01',
            'v1.2.3;touch injected',
            'release-records',
        ):
            with self.subTest(tag=tag):
                result = self.command('identity', Path('/nonexistent'), tag, 'a' * 40)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('Unsupported release version', result.stderr)

    @staticmethod
    def command(
        stage: str,
        root: Path,
        tag: str,
        commit: str,
        *options: str,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                '-I',
                str(ROOT / 'scripts/release/sdist.py'),
                stage,
                '--root',
                str(root),
                '--tag',
                tag,
                '--commit',
                commit,
                *options,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
