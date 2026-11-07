# Copyright 2026 Axel Voitier
# ruff: noqa: PT009, PT027, INP001, E402, S603, S607
"""Coordinator CLI scenarios with real Git and simulated service responses."""

import hashlib
import io
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import unittest
from collections import Counter
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import asdict, replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from release_context import GITHUB_CONTEXT

sys.path.insert(0, str(ROOT / 'tests'))
from release import coordinator
from release.candidate import manifest_bytes, wheel_statement
from release.sdist import source_identity, statement
from release.storage import Draft, Event, Release, Storage
from test_storage import ReleaseService


def download_output(argv: list[str], data: bytes) -> bytes:
    """Model the CLI's optional response headers at the external boundary."""
    return (b'HTTP/2.0 200 OK\r\n\r\n' if '--include' in argv else b'') + data


class CoordinatorChecks(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.root = self.directory / 'source'
        self.root.mkdir()
        self.git('init', '-b', 'main')
        self.git('config', 'user.email', 'test@example.invalid')
        self.git('config', 'user.name', 'Test')
        self.git('config', 'commit.gpgsign', 'false')
        self.git('config', 'tag.gpgsign', 'false')
        (self.root / 'pyproject.toml').write_bytes((ROOT / 'pyproject.toml').read_bytes())
        for relative in (
            '.github/workflows/release-preparation.yml',
            '.github/workflows/release-build.yml',
            'scripts/release/coordinator.py',
        ):
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((ROOT / relative).read_bytes())
        self.git('add', '.')
        self.git('commit', '-m', 'Fixture source')
        self.git('tag', 'v1.2.3')
        self.commit = self.git('rev-parse', 'HEAD')
        self.service = ReleaseService()
        # Product storage does not exist before preparation.
        del self.service.releases[20]
        self.service.tag_targets['v1.2.3'] = (self.commit, 'commit', self.commit)
        self.environ = {
            'GH_TOKEN': 'fixture-token',
            'GITHUB_REPOSITORY': 'AxelVoitier/zensical-tarn',
            'GITHUB_REPOSITORY_ID': '123',
            'GITHUB_REPOSITORY_OWNER_ID': '456',
            'RUNNER_ENVIRONMENT': 'github-hosted',
            'GITHUB_EVENT_NAME': 'create',
            'GITHUB_REF': 'refs/tags/v1.2.3',
            'GITHUB_SHA': self.commit,
            'GITHUB_WORKFLOW_SHA': self.commit,
            'GITHUB_WORKFLOW_REF': (
                'AxelVoitier/zensical-tarn/.github/workflows/'
                'release-preparation.yml@refs/tags/v1.2.3'
            ),
            'GITHUB_RUN_ID': '101',
            'GITHUB_RUN_ATTEMPT': '1',
        }
        self.event = {'ref_type': 'tag', 'ref': 'v1.2.3'}
        self.registry: dict[str, object] = {'urls': []}
        self.output = ''
        self.cancel_owner: int | None = None
        self.api_page_size = 1
        self.created_product_id: int | None = None
        self.hidden_product_reads = 0
        self.real_process = subprocess.run

    def git(self, *args: str) -> str:
        return subprocess.run(
            ['git', '-C', str(self.root), *args],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    def process(  # noqa: PLR0912 - Fixed external API response scenarios.
        self,
        argv: list[str],
        **kwargs: object,
    ) -> subprocess.CompletedProcess[bytes]:
        if argv[0] != 'gh':
            return self.real_process(argv, **kwargs)  # type: ignore[return-value]
        if argv[1:3] == ['attestation', 'verify']:
            bundle = Path(argv[argv.index('--bundle') + 1])
            return subprocess.CompletedProcess(argv, 0, bundle.read_text(), '')  # type: ignore[return-value]
        endpoint = (
            argv[4]
            .removeprefix('https://uploads.github.com')
            .removeprefix('/')
            .removeprefix('repos/AxelVoitier/zensical-tarn')
        )
        result: object
        if endpoint == '':
            result = {'id': 123}
        elif endpoint.startswith('/git/ref/tags/'):
            target, kind, _commit = self.service.tag_identity(endpoint.rsplit('/', 1)[1])
            result = {'object': {'sha': target, 'type': kind}}
        elif endpoint.startswith('/git/tags/'):
            result = {'object': {'sha': self.commit, 'type': 'commit'}}
        elif endpoint == '/releases':
            data = json.loads(kwargs['input'])  # type: ignore[arg-type]
            self.assertIn('--method', argv)
            self.assertIn('POST', argv)
            self.assertTrue(data['draft'] is True)
            self.assertTrue(data['prerelease'] is True)
            item = self.service.create_product(
                data['tag_name'],
                data['target_commitish'],
                data['body'],
            )
            self.created_product_id = item.id
            result = {
                'id': item.id,
                'tag_name': item.tag,
                'target_commitish': item.target,
                'body': item.body,
                'draft': item.draft,
            }
        elif endpoint.startswith('/releases?'):
            page = int(endpoint.rsplit('=', 1)[1])
            releases = list(self.service.releases.values())
            if page == 1 and self.created_product_id is not None and self.hidden_product_reads:
                self.hidden_product_reads -= 1
                releases = [item for item in releases if item.id != self.created_product_id]
            result = [
                {
                    'id': item.id,
                    'tag_name': item.tag,
                    'target_commitish': item.target,
                    'body': item.body,
                    'draft': item.draft,
                }
                for item in releases[(page - 1) * self.api_page_size : page * self.api_page_size]
            ]
        elif '/assets?per_page=' in endpoint:
            owner = int(endpoint.split('/')[2])
            page = int(endpoint.rsplit('=', 1)[1])
            assets = [
                asset for release, asset, _data in self.service.assets.values() if release == owner
            ]
            result = [
                asdict(item)
                for item in assets[(page - 1) * self.api_page_size : page * self.api_page_size]
            ]
        elif endpoint.startswith('/releases/assets/'):
            identifier = int(endpoint.rsplit('/', 1)[1])
            if 'Accept: application/octet-stream' in argv:
                return subprocess.CompletedProcess(
                    argv,
                    0,
                    download_output(argv, self.service.download(identifier)),
                    b'',
                )
            result = asdict(self.service.asset(identifier))
        elif endpoint.startswith('/releases/') and '/assets?name=' in endpoint:
            owner = int(endpoint.split('/')[2])
            name = endpoint.split('name=', 1)[1]
            self.service.upload(owner, name, kwargs['input'])  # type: ignore[arg-type]
            if self.cancel_owner == owner:
                raise KeyboardInterrupt
            result = {}
        elif endpoint.startswith('/releases/'):
            item = self.service.release(int(endpoint.rsplit('/', 1)[1]))
            result = {
                'id': item.id,
                'tag_name': item.tag,
                'target_commitish': item.target,
                'body': item.body,
                'draft': item.draft,
            }
        else:
            raise AssertionError(endpoint)
        return subprocess.CompletedProcess(argv, 0, json.dumps(result).encode(), b'')

    def registry_response(self, *_args: object, **_kwargs: object) -> io.BytesIO:
        return io.BytesIO(json.dumps(self.registry).encode())

    def run_cli(self, stage: str, *args: str, expected: int = 0) -> dict[str, object]:
        event_path = self.directory / 'event.json'
        event_path.write_text(json.dumps(self.event))
        stdout, stderr = io.StringIO(), io.StringIO()
        with (
            patch.dict(
                os.environ,
                {**self.environ, 'GITHUB_EVENT_PATH': str(event_path)},
                clear=True,
            ),
            patch.object(
                sys,
                'argv',
                [
                    'coordinator.py',
                    stage,
                    '--root',
                    str(self.root),
                    '--admin-id',
                    '10',
                    '--admin-target',
                    'a' * 40,
                    '--repository-id',
                    '123',
                    *args,
                ],
            ),
            patch('subprocess.run', side_effect=self.process),
            patch('urllib.request.urlopen', side_effect=self.registry_response),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            code = coordinator.main()
        self.output = stdout.getvalue() + stderr.getvalue()
        self.assertEqual(code, expected, self.output)
        return json.loads(stdout.getvalue()) if code == 0 else {}

    def test_overlapping_create_and_push_admit_only_one_preparation(self) -> None:
        receipt = self.directory / 'receipt.json'
        first = self.run_cli('admit', '--output', str(receipt))
        self.assertEqual(first['action'], 'prepare')
        self.environ.update(GITHUB_EVENT_NAME='push', GITHUB_RUN_ID='102')
        self.event = {'ref': 'refs/tags/v1.2.3', 'after': self.commit, 'deleted': False}
        second = self.run_cli('admit', '--output', str(self.directory / 'duplicate.json'))
        self.assertEqual(second['action'], 'noop')
        self.environ['GITHUB_RUN_ID'] = '101'
        self.run_cli('guard', '--receipt', str(receipt))

    def move_tag(self) -> None:
        (self.root / 'change.txt').write_text('New source\n')
        self.git('add', '.')
        self.git('commit', '-m', 'Changed fixture source')
        self.git('tag', '-f', 'v1.2.3')
        self.commit = self.git('rev-parse', 'HEAD')
        self.environ.update(
            GITHUB_SHA=self.commit,
            GITHUB_WORKFLOW_SHA=self.commit,
            GITHUB_RUN_ID='103',
        )
        self.service.tag_targets['v1.2.3'] = (self.commit, 'commit', self.commit)

    def test_permitted_move_repeats_preparation_and_supersedes_old_attempt(self) -> None:
        receipt = self.directory / 'receipt.json'
        self.run_cli('admit', '--output', str(receipt))
        self.move_tag()
        moved = self.run_cli('admit', '--output', str(self.directory / 'moved.json'))
        self.assertEqual(moved['action'], 'prepare')
        self.run_cli('guard', '--receipt', str(receipt), expected=1)
        self.assertIn('Stale attempt', self.output)

    def test_api_failure_reports_status_without_exposing_captured_error_text(self) -> None:
        original = self.process
        for stderr, status, reason in (
            (b'gh: API rate limit exceeded (HTTP 403)', 'HTTP 403', 'rate limited'),
            (b'gh: Bad Gateway (HTTP 502)', 'HTTP 502', 'unclassified CLI error'),
            (b'gh: connection failed', 'HTTP status unavailable', 'unclassified CLI error'),
            (
                b'net/http: TLS handshake timeout',
                'HTTP status unavailable',
                'TLS handshake timeout',
            ),
            (b'context deadline exceeded', 'HTTP status unavailable', 'request timeout'),
            (b'read tcp: i/o timeout', 'HTTP status unavailable', 'request timeout'),
            (
                b'dial tcp: lookup example.invalid: no such host',
                'HTTP status unavailable',
                'DNS failure',
            ),
            (
                b'x509: certificate signed by unknown authority',
                'HTTP status unavailable',
                'TLS failure',
            ),
            (b'read tcp: connection reset by peer', 'HTTP status unavailable', 'connection reset'),
            (b'unexpected EOF', 'HTTP status unavailable', 'unexpected EOF'),
            (
                b'http2: stream error: INTERNAL_ERROR',
                'HTTP status unavailable',
                'HTTP/2 stream error',
            ),
        ):

            def process(
                argv: list[str],
                failure: bytes = stderr,
                **kwargs: object,
            ) -> subprocess.CompletedProcess[bytes]:
                if argv[0] == 'gh':
                    raise subprocess.CalledProcessError(
                        1,
                        argv,
                        output=b'private response body',
                        stderr=failure + b'\nfixture-token private details',
                    )
                return original(argv, **kwargs)

            with self.subTest(status=status), patch.object(self, 'process', side_effect=process):
                self.run_cli('admit', '--output', str(self.directory / 'receipt.json'), expected=1)
                self.assertIn(status, self.output)
                self.assertIn(reason, self.output)
                self.assertNotIn('fixture-token', self.output)
                self.assertNotIn('private details', self.output)
                self.assertNotIn('private response body', self.output)

    def test_history_error_keeps_http_status_when_cli_cannot_parse_json_error_body(self) -> None:
        receipt = self.directory / 'receipt.json'
        self.run_cli('admit', '--output', str(receipt))
        original = self.process

        def process(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
            if argv[0] == 'gh' and 'Accept: application/octet-stream' in argv:
                raise subprocess.CalledProcessError(
                    1,
                    argv,
                    output=(
                        b'HTTP/2.0 500 Internal Server Error\n'
                        b'Content-Type: application/json\r\n\r\n'
                    ),
                    stderr=b'unexpected end of JSON input\n',
                )
            return original(argv, **kwargs)

        with patch.object(self, 'process', side_effect=process):
            self.run_cli('guard', '--receipt', str(receipt), expected=1)
        self.assertIn('HTTP 500', self.output)
        self.assertNotIn('Content-Type', self.output)
        self.assertNotIn('unexpected end', self.output)

    def test_history_read_recovers_from_transient_server_errors_without_writes(self) -> None:
        receipt = self.directory / 'receipt.json'
        self.run_cli('admit', '--output', str(receipt))
        originals = dict(self.service.assets)
        original = self.process
        failures = iter([503, 503])

        def process(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
            if (
                argv[0] == 'gh'
                and 'Accept: application/octet-stream' in argv
                and next(failures, None) is not None
            ):
                raise subprocess.CalledProcessError(
                    1,
                    argv,
                    output=(
                        b'HTTP/2.0 503 Service Unavailable\nContent-Type: application/json\r\n\r\n'
                    ),
                    stderr=b'unexpected end of JSON input\n',
                )
            return original(argv, **kwargs)

        with (
            patch.object(self, 'process', side_effect=process),
            patch('time.sleep', return_value=None),
        ):
            self.run_cli('guard', '--receipt', str(receipt))
        self.assertEqual(self.service.assets, originals)
        self.assertIn('HTTP 503', self.output)
        self.assertIn('retry 1/2 in 1s', self.output)
        self.assertIn('recovered on attempt 3/3', self.output)

    def test_history_read_errors_are_bounded_and_denials_are_not_retried(self) -> None:
        receipt = self.directory / 'receipt.json'
        self.run_cli('admit', '--output', str(receipt))
        original = self.process
        for status, expected_reads in ((503, 3), (403, 1), (404, 1)):
            reads: list[list[str]] = []

            def process(
                argv: list[str], observed: list[list[str]] = reads,
                limit: int = expected_reads, code: int = status, **kwargs: object,
            ) -> subprocess.CompletedProcess[bytes]:
                if argv[0] == 'gh' and 'Accept: application/octet-stream' in argv:
                    observed.append(argv)
                    if len(observed) > limit:
                        self.fail('History request exceeded its allowed read attempts')
                    raise subprocess.CalledProcessError(
                        1, argv,
                        output=(f'HTTP/2.0 {code} Error\n'
                                'Content-Type: application/json\r\n\r\n').encode(),
                        stderr=b'unexpected end of JSON input\n',
                    )
                return original(argv, **kwargs)

            with (self.subTest(status=status),
                  patch.object(self, 'process', side_effect=process),
                  patch('time.sleep', return_value=None)):
                self.run_cli('guard', '--receipt', str(receipt), expected=1)
                self.assertIn(f'HTTP {status}', self.output)
                self.assertEqual(len(reads), expected_reads)

    def test_old_queued_identity_and_external_destination_changes_cannot_advance(self) -> None:
        receipt = self.directory / 'receipt.json'
        self.run_cli('admit', '--output', str(receipt))
        self.registry = {'urls': [{'filename': 'external.whl'}]}
        self.run_cli('guard', '--receipt', str(receipt), expected=1)
        self.assertIn('destination state', self.output)
        self.service.tag_targets['v1.2.3'] = ('c' * 40, 'commit', 'c' * 40)
        self.run_cli('admit', '--output', str(self.directory / 'stale.json'), expected=1)
        self.assertIn('Remote tag differs', self.output)

    def test_move_after_any_index_upload_needs_a_new_version(self) -> None:
        receipt = self.directory / 'receipt.json'
        self.run_cli('admit', '--output', str(receipt))
        self.move_tag()
        self.registry = {'urls': [{'filename': 'uploaded.tar.gz'}]}
        self.run_cli('admit', '--output', str(self.directory / 'moved.json'), expected=1)
        self.assertIn('new version', self.output)

    def test_cancelled_before_originals_requires_deliberate_full_preparation(self) -> None:
        receipt = self.directory / 'receipt.json'
        self.run_cli('admit', '--output', str(receipt))
        # No final-report stage runs, and all temporary run artifacts are gone.
        receipt.unlink()
        self.environ.update(GITHUB_EVENT_NAME='workflow_dispatch', GITHUB_RUN_ID='102')
        self.event = {'inputs': {'mode': 'resume'}}
        self.run_cli('admit', '--output', str(receipt), expected=1)
        self.assertIn('Full preparation required', self.output)
        self.assertIn('--ref v1.2.3 -f mode=prepare', self.output)
        self.event = {'inputs': {'mode': 'prepare'}}
        self.assertEqual(self.run_cli('admit', '--output', str(receipt))['action'], 'prepare')

    def make_candidate(self) -> Path:

        source = source_identity(self.root, 'v1.2.3', self.commit)
        candidate = self.directory / 'candidate'
        files = candidate / 'files'
        files.mkdir(parents=True)
        sdist = files / 'zensical_tarn-1.2.3.tar.gz'
        wheel = files / 'zensical_tarn-1.2.3-py3-none-any.whl'
        sdist.write_bytes(b'original source')
        wheel.write_bytes(b'original wheel')
        transfers = {
            kind: {
                **GITHUB_CONTEXT,
                'event_name': self.environ['GITHUB_EVENT_NAME'],
                'run_id': self.environ['GITHUB_RUN_ID'],
                'run_attempt': '1',
                'artifact_id': identifier,
                'artifact_name': f'{kind}-{self.environ["GITHUB_RUN_ID"]}-1',
                'transport_digest': 'sha256:' + 'd' * 64,
            }
            for kind, identifier in (('sdist', '73'), ('wheel', '75'))
        }
        for name, signed in (
            ('sdist', statement(source, sdist, transfers['sdist'])),
            (
                'wheel',
                wheel_statement(source, sdist, wheel, transfers['sdist'], transfers['wheel']),
            ),
        ):
            (files / f'{name}.sigstore.json').write_text(
                json.dumps([{'verificationResult': {'statement': signed}}]),
            )
        (candidate / 'candidate.json').write_bytes(
            manifest_bytes(source, files, transfers, {'sdist': '74', 'wheel': '76'}),
        )
        self.candidate_digest = hashlib.sha256(
            (candidate / 'candidate.json').read_bytes(),
        ).hexdigest()
        return candidate

    def retain_candidate(self) -> Path:
        """Prepare original files through the CLI before exercising an approval wait."""
        product = Draft(20, 'product', 'v1.2.3', self.commit, '123')
        self.service.releases[20] = Release(
            20,
            product.tag,
            product.target,
            product.body,
            draft=True,
        )
        receipt = self.directory / 'receipt.json'
        self.run_cli('admit', '--output', str(receipt))
        self.run_cli('guard', '--receipt', str(receipt))
        candidate = self.make_candidate()
        self.run_cli(
            'retain',
            '--receipt',
            str(receipt),
            '--candidate-dir',
            str(candidate),
            '--product-id',
            '20',
            '--candidate-digest',
            self.candidate_digest,
        )
        return candidate

    def test_approval_wait_rechecks_live_destinations_against_retained_checkpoint(self) -> None:
        self.retain_candidate()
        checkpoint = self.run_cli('checkpoint')
        self.assertEqual(checkpoint['status'], 'pass')
        self.run_cli('recheck', '--head', str(checkpoint['head']))
        self.registry = {'urls': [{'filename': 'outside-writer.whl'}]}
        self.run_cli('recheck', '--head', str(checkpoint['head']), expected=1)
        self.assertIn('changed', self.output)

    def test_preparation_and_approval_fit_repository_job_token_budget(self) -> None:
        # Use the requested API page size for the budget; other scenarios force
        # one item per page to exercise pagination with small fixtures.
        self.api_page_size = 100
        storage = Storage(self.service, self.service.admin)
        for version in ('1.1.9', '1.2.0', '1.2.1', '1.2.2'):
            first = storage.append(
                Event(version, None, self.commit, '99', '1', 1, 'admitted', None, {}),
            )
            storage.append(
                Event(version, None, self.commit, '99', '1', 2, 'stopped', first.digest, {}),
            )
        calls: Counter[str] = Counter()
        original = self.process

        def count(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
            if argv[:2] == ['gh', 'api']:
                calls[argv[4]] += 1
            return original(argv, **kwargs)

        self.process = count
        receipt = self.directory / 'receipt.json'
        self.run_cli('admit', '--output', str(receipt))
        self.run_cli('guard', '--receipt', str(receipt))
        candidate = self.make_candidate()
        self.run_cli(
            'retain',
            '--receipt',
            str(receipt),
            '--candidate-dir',
            str(candidate),
            '--candidate-digest',
            self.candidate_digest,
        )
        checkpoint = self.run_cli('checkpoint')
        self.run_cli('recheck', '--head', str(checkpoint['head']))
        self.run_cli('report', '--outcome', 'success')
        # GitHub documents 1,000 repository GITHUB_TOKEN requests per hour.
        # Include the guard, retention, approval and report, plus another version's history.
        self.assertLess(sum(calls.values()), 1000, dict(calls))

    def test_new_draft_waits_for_listing_visibility_without_repeating_creation(self) -> None:
        self.api_page_size = 100
        self.hidden_product_reads = 1
        receipt = self.directory / 'receipt.json'
        self.run_cli('admit', '--output', str(receipt))
        candidate = self.make_candidate()
        with patch('time.sleep'):
            self.run_cli(
                'retain',
                '--receipt',
                str(receipt),
                '--candidate-dir',
                str(candidate),
                '--candidate-digest',
                self.candidate_digest,
            )
        self.assertEqual(len(self.service.releases), 2)
        self.assertEqual(self.run_cli('checkpoint')['status'], 'pass')

    def test_persistently_missing_created_draft_stops_without_repeating_creation(self) -> None:
        self.api_page_size = 100
        self.hidden_product_reads = 1000
        receipt = self.directory / 'receipt.json'
        self.run_cli('admit', '--output', str(receipt))
        candidate = self.make_candidate()
        waits: list[float] = []
        with patch('time.sleep', side_effect=waits.append):
            self.run_cli(
                'retain',
                '--receipt',
                str(receipt),
                '--candidate-dir',
                str(candidate),
                '--candidate-digest',
                self.candidate_digest,
                expected=1,
            )
        self.assertIn('not visible in listings; inspect before retrying', self.output)
        self.assertEqual(len(self.service.releases), 2)
        self.assertFalse(self.service.assets_page(int(str(self.created_product_id)), 1))
        self.assertLessEqual(sum(waits), 10)

    def test_changed_storage_stops_before_upload_or_success_output(self) -> None:
        original = self.process
        administrative = self.service.releases[10]
        for stage in ('admit', 'guard'):
            with self.subTest(stage=stage):
                receipt = self.directory / 'receipt.json'
                if stage == 'guard':
                    self.run_cli('admit', '--output', str(receipt))
                before = dict(self.service.assets)
                reads = 0

                def changed(
                    argv: list[str],
                    **kwargs: object,
                ) -> subprocess.CompletedProcess[bytes]:
                    nonlocal reads
                    if argv[:2] == ['gh', 'api'] and argv[4].endswith('/releases/10'):
                        reads += 1
                        if reads > 1:
                            self.service.releases[10] = replace(administrative, draft=False)
                    return original(argv, **kwargs)

                self.process = changed
                args = (
                    ('--output', str(receipt)) if stage == 'admit' else ('--receipt', str(receipt))
                )
                self.run_cli(stage, *args, expected=1)
                self.assertIn('changed', self.output)
                self.assertNotIn('"action"', self.output)
                self.assertEqual(self.service.assets, before)
                if stage == 'admit':
                    self.assertFalse(receipt.exists())
                self.service.releases[10] = administrative
                self.process = original

    def test_lost_upload_responses_reconcile_fresh_state_despite_download_counters(self) -> None:
        self.service.upload_outcome = 'lost-response'
        original = self.process
        counter = 0

        def download_activity(
            argv: list[str],
            **kwargs: object,
        ) -> subprocess.CompletedProcess[bytes]:
            nonlocal counter
            response = original(argv, **kwargs)
            if argv[:2] == ['gh', 'api'] and 'Accept: application/octet-stream' not in argv:
                value = json.loads(response.stdout)
                if isinstance(value, dict):
                    counter += 1
                    value['download_count'] = counter
                    value['updated_at'] = str(counter)
                    response.stdout = json.dumps(value).encode()
            return response

        self.process = download_activity
        self.retain_candidate()
        self.assertEqual(self.run_cli('checkpoint')['status'], 'pass')

    def test_new_dispatch_recovers_verified_originals_without_rebuilding(self) -> None:
        receipt = self.directory / 'receipt.json'
        self.run_cli('admit', '--output', str(receipt))
        self.service.product = Draft(20, 'product', 'v1.2.3', self.commit, '123')
        product = self.service.product
        self.service.releases[20] = Release(
            20,
            product.tag,
            product.target,
            product.body,
            draft=True,
        )
        # A product draft must be admitted before its original files may be retained.
        self.environ['GITHUB_RUN_ID'] = '102'
        self.environ['GITHUB_EVENT_NAME'] = 'workflow_dispatch'
        self.event = {'inputs': {'mode': 'prepare'}}
        self.run_cli('admit', '--output', str(receipt))
        candidate = self.make_candidate()
        self.run_cli(
            'retain',
            '--receipt',
            str(receipt),
            '--candidate-dir',
            str(candidate),
            '--product-id',
            '20',
            '--candidate-digest',
            self.candidate_digest,
        )
        original_manifest = (candidate / 'candidate.json').read_bytes()
        # Simulate expired temporary files locally, retaining only service originals.
        shutil.rmtree(candidate)
        receipt.unlink()
        self.environ['GITHUB_RUN_ID'] = '103'
        self.event = {'inputs': {'mode': 'resume'}}
        resumed = self.run_cli('admit', '--output', str(receipt))
        self.assertEqual(resumed['action'], 'resume')
        recovered = self.directory / 'recovered'
        self.run_cli('recover', '--receipt', str(receipt), '--output', str(recovered))
        self.assertEqual(
            (recovered / 'candidate.json').read_bytes(),
            original_manifest,
        )
        self.assertEqual(
            (recovered / 'files/zensical_tarn-1.2.3.tar.gz').read_bytes(),
            b'original source',
        )
        self.assertIn('gh workflow run release-preparation.yml', receipt.read_text())

    def test_hosted_checkpoint_cannot_be_replayed_by_a_new_run(self) -> None:
        self.retain_candidate()
        checkpoint = self.run_cli('checkpoint')
        self.environ['GITHUB_RUN_ID'] = '102'
        self.run_cli('recheck', '--head', str(checkpoint['head']), expected=1)
        self.assertIn('Stale checkpoint attempt', self.output)

    def test_resumed_originals_can_wait_but_changed_history_stops_advancement(self) -> None:
        self.retain_candidate()
        self.run_cli('checkpoint')
        self.run_cli('report', '--outcome', 'success')
        self.environ.update(GITHUB_EVENT_NAME='workflow_dispatch', GITHUB_RUN_ID='102')
        self.event = {'inputs': {'mode': 'resume'}}
        receipt = self.directory / 'resumed.json'
        self.run_cli('admit', '--output', str(receipt))
        self.run_cli(
            'recover',
            '--receipt',
            str(receipt),
            '--output',
            str(self.directory / 'originals'),
        )
        checkpoint = self.run_cli('checkpoint')
        self.run_cli('recheck', '--head', str(checkpoint['head']))
        self.run_cli('report', '--outcome', 'cancelled')
        self.run_cli('recheck', '--head', str(checkpoint['head']), expected=1)
        self.assertIn('history or destination state changed', self.output)

    def test_hosted_checkpoint_verifies_original_bytes_after_approval(self) -> None:
        self.retain_candidate()
        checkpoint = self.run_cli('checkpoint')
        owner, asset, _data = next(
            item for item in self.service.assets.values() if item[1].name.endswith('.whl')
        )
        self.service.assets[asset.id] = (owner, asset, b'substituted file')
        self.run_cli('recheck', '--head', str(checkpoint['head']), expected=1)

    def test_hosted_checkpoint_requires_originals_and_a_bound_head(self) -> None:
        self.run_cli('admit', '--output', str(self.directory / 'receipt.json'))
        self.run_cli('checkpoint', expected=1)
        self.assertIn('Retained candidate', self.output)
        self.run_cli('recheck', expected=1)
        self.assertIn('Checkpoint head required', self.output)

    def test_hosted_queue_probe_holds_the_coordinator_through_recheck(self) -> None:
        workflow = (ROOT / '.github/workflows/release-preparation.yml').read_text()
        self.assertIn('  hosted-checkpoint:', workflow)
        self.assertIn("vars.TARN_RELEASE_HOSTED_PROOF == 'true'", workflow)
        self.assertIn('needs: hosted-checkpoint', workflow)
        self.assertIn('needs: [hosted-checkpoint, hosted-approval]', workflow)
        self.assertIn('coordinator.py recheck', workflow)
        approval = workflow.split('  hosted-approval:\n')[1].split('\n  hosted-recheck:')[0]
        self.assertIn('environment: pypi', approval)
        self.assertIn('permissions: {}', approval)
        self.assertNotIn('checkout', approval)
        report = workflow.split('\n  report:')[1]
        self.assertIn('hosted-recheck', report)

    def test_verifier_jobs_provision_the_pinned_cli_before_checking_its_version(self) -> None:
        for filename in ('release-preparation.yml', 'release-build.yml', 'check.yml'):
            workflow = (ROOT / '.github/workflows' / filename).read_text()
            for job in re.split(r'\n  (?=[a-zA-Z0-9_-]+:)', workflow)[1:]:
                if 'gh --version' in job:
                    with self.subTest(workflow=filename, job=job.splitlines()[0]):
                        self.assertIn('uses: ./.github/actions/setup-gh', job)
                        self.assertLess(job.index('setup-gh'), job.index('gh --version'))

    def test_workflow_runtime_rejects_a_corrupt_download_before_exposing_the_cli(self) -> None:
        commands = self.directory / 'commands'
        commands.mkdir()
        curl = commands / 'curl'
        curl.write_text(
            '#!/bin/sh\nwhile [ "$1" != --output ]; do shift; done\n'
            'shift\nprintf tampered > "$1"\n',
        )
        curl.chmod(0o755)
        path_file = self.directory / 'github-path'
        result = subprocess.run(
            ['bash', str(ROOT / 'scripts/release/setup_gh.sh')],
            env={
                **os.environ,
                'PATH': str(commands) + os.pathsep + os.environ['PATH'],
                'RUNNER_TEMP': str(self.directory),
                'GITHUB_PATH': str(path_file),
            },
            capture_output=True,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(path_file.exists())

    def test_default_branch_dispatch_and_release_publication_are_rejected(self) -> None:
        for changed in (
            {'GITHUB_REF': 'refs/heads/main'},
            {'GITHUB_WORKFLOW_SHA': 'd' * 40},
            {'GITHUB_EVENT_NAME': 'release'},
        ):
            original = self.environ.copy()
            self.environ.update(changed)
            self.run_cli('admit', '--output', str(self.directory / 'wrong.json'), expected=1)
            self.environ = original

    def test_approval_history_blocks_a_move_even_when_indexes_look_empty(self) -> None:
        receipt = self.directory / 'receipt.json'
        first = self.run_cli('admit', '--output', str(receipt))
        storage = Storage(self.service, self.service.admin)
        storage.append(
            Event(
                '1.2.3',
                None,
                self.commit,
                '101',
                '1',
                2,
                'production-approved',
                str(first['head']),
                {},
            ),
        )
        self.move_tag()
        self.run_cli('admit', '--output', str(self.directory / 'moved.json'), expected=1)
        self.assertIn('new version', self.output)

    def test_supported_versions_and_administrative_tags_are_checked_in_full(self) -> None:
        for tag in ('v1.2.3rc4.post5', 'v2.0.0a0', 'v2.0.0b1', 'v2.0.0.post1'):
            with self.subTest(tag=tag):
                self.git('tag', tag)
                self.service.tag_targets[tag] = (self.commit, 'commit', self.commit)
                self.environ.update(
                    GITHUB_REF='refs/tags/' + tag,
                    GITHUB_WORKFLOW_REF=f'AxelVoitier/zensical-tarn/.github/workflows/release-preparation.yml@refs/tags/{tag}',
                )
                self.event = {'ref_type': 'tag', 'ref': tag}
                self.assertEqual(
                    self.run_cli('admit', '--output', str(self.directory / 'version.json'))[
                        'action'
                    ],
                    'prepare',
                )
        for tag in ('release-records', 'v01.2.3', 'v1.2.3junk', 'v1.2.3.dev1'):
            self.environ['GITHUB_REF'] = 'refs/tags/' + tag
            self.run_cli('admit', '--output', str(self.directory / 'invalid.json'), expected=1)

    def test_workflow_uses_original_ref_one_queue_and_separate_resume_path(self) -> None:
        workflow = (ROOT / '.github/workflows/release-preparation.yml').read_text()
        self.assertIn('  create:', workflow)
        self.assertIn("tags: ['v[0-9]*']", workflow)
        self.assertNotIn('  release:', workflow)
        self.assertIn('  group: tarn-release', workflow)
        self.assertIn('  cancel-in-progress: false', workflow)
        self.assertIn('  queue: max', workflow)
        self.assertIn('uses: ./.github/workflows/release-build.yml', workflow)
        self.assertIn("needs.resolve.outputs.action == 'prepare'", workflow)
        self.assertIn("needs.resolve.outputs.action == 'resume'", workflow)
        self.assertNotIn('inputs.tag', workflow)
        self.assertIn("vars.TARN_RELEASE_PREPARATION_ENABLED == 'true'", workflow)

    def test_cancelled_partial_retention_blocks_replacement_builds(self) -> None:
        product = Draft(20, 'product', 'v1.2.3', self.commit, '123')
        self.service.releases[20] = Release(
            20,
            product.tag,
            product.target,
            product.body,
            draft=True,
        )
        receipt = self.directory / 'receipt.json'
        self.run_cli('admit', '--output', str(receipt))
        candidate = self.make_candidate()
        self.cancel_owner = 20
        with self.assertRaises(KeyboardInterrupt):
            self.run_cli(
                'retain',
                '--receipt',
                str(receipt),
                '--candidate-dir',
                str(candidate),
                '--product-id',
                '20',
                '--candidate-digest',
                self.candidate_digest,
            )
        self.cancel_owner = None
        # The manifest alone is not a complete original recovery copy.
        self.environ.update(GITHUB_EVENT_NAME='workflow_dispatch', GITHUB_RUN_ID='102')
        self.event = {'inputs': {'mode': 'prepare'}}
        self.run_cli('admit', '--output', str(self.directory / 'replacement.json'), expected=1)
        self.assertIn('incomplete recovery copy', self.output)

    def test_complete_copy_survives_cancellation_before_its_history_append(self) -> None:
        product = Draft(20, 'product', 'v1.2.3', self.commit, '123')
        self.service.releases[20] = Release(
            20,
            product.tag,
            product.target,
            product.body,
            draft=True,
        )
        receipt = self.directory / 'receipt.json'
        self.run_cli('admit', '--output', str(receipt))
        candidate = self.make_candidate()
        self.run_cli(
            'retain',
            '--receipt',
            str(receipt),
            '--candidate-dir',
            str(candidate),
            '--product-id',
            '20',
            '--candidate-digest',
            self.candidate_digest,
        )
        # Simulate cancellation after every product write but before the new history event exists.
        final_event = max(self.service.assets)
        del self.service.assets[final_event]
        self.environ.update(GITHUB_EVENT_NAME='workflow_dispatch', GITHUB_RUN_ID='102')
        self.event = {'inputs': {'mode': 'resume'}}
        result = self.run_cli('admit', '--output', str(receipt))
        self.assertEqual(result['action'], 'resume')
        self.run_cli(
            'recover',
            '--head',
            str(result['head']),
            '--output',
            str(self.directory / 'recovered'),
        )

    def test_rewritten_annotation_invalidates_old_push_identity(self) -> None:
        self.git('tag', '-a', '-f', 'v1.2.3', '-m', 'Original annotation')
        original = self.git('rev-parse', 'refs/tags/v1.2.3')
        self.service.tag_targets['v1.2.3'] = (original, 'tag', self.commit)
        receipt = self.directory / 'receipt.json'
        self.run_cli('admit', '--output', str(receipt))
        command = json.loads(receipt.read_bytes())['event']['details']['command']
        self.assertEqual(
            shlex.split(command),
            [
                'gh',
                'workflow',
                'run',
                'release-preparation.yml',
                '--repo',
                'AxelVoitier/zensical-tarn',
                '--ref',
                'v1.2.3',
                '-f',
                'mode=resume',
            ],
        )
        self.git('tag', '-a', '-f', 'v1.2.3', '-m', 'Changed annotation')
        changed = self.git('rev-parse', 'refs/tags/v1.2.3')
        self.service.tag_targets['v1.2.3'] = (changed, 'tag', self.commit)
        self.environ.update(GITHUB_EVENT_NAME='push', GITHUB_RUN_ID='102')
        self.event = {'ref': 'refs/tags/v1.2.3', 'after': original, 'deleted': False}
        self.run_cli('admit', '--output', str(self.directory / 'old.json'), expected=1)
        self.assertIn('stale event identity', self.output)
        self.event['after'] = changed
        self.assertEqual(
            self.run_cli('admit', '--output', str(self.directory / 'new.json'))['action'],
            'prepare',
        )

    def test_retention_rejects_a_different_builder_digest_or_execution(self) -> None:
        product = Draft(20, 'product', 'v1.2.3', self.commit, '123')
        self.service.releases[20] = Release(
            20,
            product.tag,
            product.target,
            product.body,
            draft=True,
        )
        receipt = self.directory / 'receipt.json'
        self.run_cli('admit', '--output', str(receipt))
        candidate = self.make_candidate()
        self.run_cli(
            'retain',
            '--receipt',
            str(receipt),
            '--candidate-dir',
            str(candidate),
            '--product-id',
            '20',
            '--candidate-digest',
            '0' * 64,
            expected=1,
        )
        self.assertIn('candidate digest', self.output)
        for run, attempt in (('102', '1'), ('101', '2')):
            self.environ.update(
                GITHUB_EVENT_NAME='workflow_dispatch',
                GITHUB_RUN_ID=run,
                GITHUB_RUN_ATTEMPT=attempt,
            )
            self.event = {'inputs': {'mode': 'prepare'}}
            self.run_cli('admit', '--output', str(receipt))
            self.run_cli(
                'retain',
                '--receipt',
                str(receipt),
                '--candidate-dir',
                str(candidate),
                '--product-id',
                '20',
                '--candidate-digest',
                self.candidate_digest,
                expected=1,
            )
            self.assertIn('producer', self.output)

    def test_unrecorded_external_copy_cannot_claim_builder_acceptance(self) -> None:
        product = Draft(20, 'product', 'v1.2.3', self.commit, '123')
        self.service.releases[20] = Release(
            20,
            product.tag,
            product.target,
            product.body,
            draft=True,
        )
        receipt = self.directory / 'receipt.json'
        self.run_cli('admit', '--output', str(receipt))
        candidate = self.make_candidate()
        for path in [candidate / 'candidate.json', *(candidate / 'files').iterdir()]:
            self.service.upload(20, path.name, path.read_bytes())
        self.environ.update(GITHUB_EVENT_NAME='workflow_dispatch', GITHUB_RUN_ID='102')
        self.event = {'inputs': {'mode': 'resume'}}
        self.run_cli('admit', '--output', str(receipt), expected=1)
        self.assertIn('retained builder selection', self.output)
