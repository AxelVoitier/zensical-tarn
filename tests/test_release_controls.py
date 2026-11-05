# Copyright 2026 Axel Voitier
# ruff: noqa: PT009, PT027, INP001
"""Exercise the hosted probe CLI at its external GitHub command boundary."""

import contextlib
import io
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'scripts'))
import check_release_controls

PREFIX = 'repos/AxelVoitier/zensical-tarn'
SOURCE = 'a' * 40
RECORD_BODY = (
    '{"repository":"AxelVoitier/zensical-tarn","repository_id":"123",'
    '"role":"administrative","schema":"tarn-storage-v1","tag":"release-records",'
    '"target":"' + SOURCE + '"}\n'
)
ENV = {
    'GH_TOKEN': 'fixture-token',
    'GITHUB_REPOSITORY': 'AxelVoitier/zensical-tarn',
    'GITHUB_REPOSITORY_ID': '123',
    'RECORD_REPOSITORY_ID': '123',
    'RECORD_ID': '10',
    'RECORD_TARGET': SOURCE,
    'GITHUB_RUN_ID': '101',
    'GITHUB_RUN_ATTEMPT': '1',
    'GITHUB_SHA': 'b' * 40,
    'GITHUB_REF': 'refs/tags/v0-release-controls-' + 'b' * 40,
    'PREPARATION_ENABLED': 'false',
    'FIXTURE_ID': '20',
    # SHA-256 of the canonical empty asset list, b'[]\n'.
    'RECORD_SNAPSHOT': '37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570',
}


class GitHubCommands:
    """External-service responses include private data that must stay out of logs."""

    def __init__(self, denied_status: int | None = 403) -> None:
        self.denied_status = denied_status
        self.denied_message = 'Resource not accessible by integration'
        self.deleted = False

    def denied(self, argv: list[str]) -> None:
        if self.denied_status is not None:
            raise subprocess.CalledProcessError(
                1,
                argv,
                stderr=(
                    f'gh: {self.denied_message} PRIVATE-SENTINEL (HTTP {self.denied_status})'
                ).encode(),
            )

    def call(self, argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[bytes]:
        endpoint = next(item for item in argv if item.startswith(PREFIX))
        if 'DELETE' in argv:
            self.deleted = True
            return subprocess.CompletedProcess(argv, 0, b'', b'')
        if 'POST' in argv:
            self.denied(argv)
            data: object = {'id': 30, 'body': 'PRIVATE-SENTINEL'}
        elif endpoint == PREFIX + '/releases/20':
            if self.deleted:
                self.denied(argv)
            data = {
                'id': 20,
                'tag_name': 'release-controls-probe-101-1',
                'target_commitish': SOURCE,
                'draft': True,
                'body': (
                    '{"schema":"tarn-controls-probe-v1","tag":"release-controls-probe-101-1"}\n'
                ),
            }
        elif endpoint == PREFIX:
            data = {'id': 123}
        elif endpoint == PREFIX + '/releases/10':
            data = {
                'id': 10,
                'tag_name': 'release-records',
                'target_commitish': SOURCE,
                'draft': True,
                'body': RECORD_BODY,
            }
        elif endpoint == PREFIX + '/git/ref/tags/release-records':
            data = {'object': {'sha': SOURCE, 'type': 'commit'}}
        elif endpoint == PREFIX + '/releases?per_page=100&page=1':
            data = [
                {
                    'id': 10,
                    'tag_name': 'release-records',
                    'target_commitish': SOURCE,
                    'draft': True,
                    'body': RECORD_BODY,
                }
            ]
        else:
            data = []
        return subprocess.CompletedProcess(argv, 0, json.dumps(data).encode(), b'')


class HostedProbeTests(unittest.TestCase):
    def invoke(
        self,
        stage: str,
        service: GitHubCommands,
        extra: dict[str, str] | None = None,
    ) -> str:
        stream = io.StringIO()
        with (
            patch.dict(os.environ, {**ENV, **(extra or {})}, clear=True),
            patch.object(sys, 'argv', ['check_release_controls.py', stage]),
            patch('subprocess.run', side_effect=service.call),
            contextlib.redirect_stdout(stream),
        ):
            check_release_controls.main()
        return stream.getvalue()

    def test_cleanup_requires_observed_absence_not_forbidden_access(self) -> None:
        with self.assertRaises(SystemExit):
            self.invoke('cleanup', GitHubCommands(403))

    def test_rate_limit_does_not_prove_a_package_permission_denial(self) -> None:
        service = GitHubCommands(403)
        service.denied_message = 'API rate limit exceeded'
        with self.assertRaises(SystemExit):
            self.invoke('package', service)

    def test_package_write_is_denied_by_a_permission_response(self) -> None:
        self.assertIn('package passed', self.invoke('package', GitHubCommands(403)))

    def test_unexpected_package_write_success_stops_the_probe(self) -> None:
        with self.assertRaises(SystemExit):
            self.invoke('package', GitHubCommands(None))

    def test_unrelated_api_errors_are_not_permission_proof(self) -> None:
        for status in (401, 422, 503):
            with self.subTest(status=status), self.assertRaises(SystemExit) as result:
                self.invoke('package', GitHubCommands(status))
            self.assertNotIn('PRIVATE-SENTINEL', str(result.exception))

    def test_package_job_cannot_have_oidc_identity_access(self) -> None:
        with self.assertRaises(SystemExit):
            self.invoke('package', GitHubCommands(), {'ACTIONS_ID_TOKEN_REQUEST_TOKEN': 'present'})

    def test_cleanup_cannot_delete_the_real_administrative_record(self) -> None:
        service = GitHubCommands(404)
        with self.assertRaises(SystemExit):
            self.invoke('cleanup', service, {'FIXTURE_ID': '10'})
        self.assertFalse(service.deleted)

    def test_cleanup_preserves_independent_administrative_storage(self) -> None:
        self.assertIn('cleanup passed', self.invoke('cleanup', GitHubCommands(404)))


if __name__ == '__main__':
    unittest.main()
