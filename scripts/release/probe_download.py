#!/usr/bin/env python3
# Copyright 2026 Axel Voitier
# ruff: noqa: EXE001, T201, S607
"""Read one retained history asset with the real transport, without release work."""

import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from release.sdist import REPOSITORY
from release.storage_api import APIRequestError, GitHubAPI


def encrypted(error: bytes | str | None) -> str:
    """Keep exact stderr private while preserving it for local diagnosis."""
    data = error.encode() if isinstance(error, str) else error or b''
    with TemporaryDirectory() as directory:
        key = Path(directory) / 'recipient.asc'
        key.write_text(os.environ['PROBE_ERROR_PUBLIC_KEY'])
        result = subprocess.run(  # noqa: S603 - Fixed encryption command; recipient is public.
            ['gpg', '--homedir', directory, '--batch', '--trust-model', 'always',
             '--recipient-file', str(key), '--armor', '--encrypt'],
            input=data, capture_output=True, check=True, timeout=10,
        )
        return result.stdout.decode()


def included(identifier: str) -> bytes:
    """Observe the status that gh can otherwise hide on malformed JSON errors."""
    result = subprocess.run(  # noqa: S603 - Fixed GET and host, validated numeric asset ID.
        ['gh', 'api', '--hostname', 'github.com',
         f'repos/{REPOSITORY}/releases/assets/{identifier}',
         '-H', 'Accept: application/octet-stream',
         '-H', 'X-GitHub-Api-Version: 2026-03-10', '--include'],
        check=False, capture_output=True, timeout=120,
    )
    separator = re.search(rb'\r?\n\r?\n', result.stdout)
    headers = result.stdout[:separator.start()] if separator else b''
    body = result.stdout[separator.end():] if separator else b''
    safe: dict[str, str] = {}
    for line in headers.decode(errors='replace').splitlines():
        if status := re.fullmatch(r'HTTP/[0-9.]+ ([0-9]{3})(?: .*)?', line):
            safe['status'] = status[1]
        name, _, value = line.partition(':')
        if name.lower() in {'content-type', 'content-length', 'x-ratelimit-remaining',
                            'x-ratelimit-reset', 'x-ratelimit-used', 'x-github-request-id'}:
            safe[name.lower()] = value.strip()
    print(json.dumps({'http_response': safe}), flush=True)
    if result.returncode:
        error = subprocess.CalledProcessError(
            result.returncode, result.args, output=result.stdout, stderr=result.stderr,
        )
        raise APIRequestError(error, 'Included-header download failed')
    if not separator:
        message = 'Probe response headers are unavailable'
        raise ValueError(message)
    return body


def main() -> int:
    if (
        os.environ.get('GITHUB_REPOSITORY') != 'AxelVoitier/zensical-tarn'
        or os.environ.get('GITHUB_EVENT_NAME') != 'workflow_dispatch'
        or os.environ.get('PREPARATION_ENABLED') != 'false'
        or os.environ.get('HOSTED_PROOF') != 'false'
        or not os.environ.get('PROBE_ERROR_PUBLIC_KEY')
        or os.environ.get('GITHUB_SHA') != os.environ.get('GITHUB_WORKFLOW_SHA')
    ):
        print('Download probe requires explicit dispatch with both release gates disabled.')
        return 1
    identifier = os.environ.get('PROBE_ASSET_ID', '')
    expected = os.environ.get('PROBE_SHA256', '')
    if not re.fullmatch(r'[1-9][0-9]*', identifier) or not re.fullmatch(r'[0-9a-f]{64}', expected):
        print('Download probe requires an asset ID and an independently retained SHA256.')
        return 1
    print(
        json.dumps(
            {
                'probe': 'history-download',
                'source': os.environ['GITHUB_SHA'],
                'workflow': os.environ['GITHUB_WORKFLOW_SHA'],
                'asset': identifier,
                'expected_sha256': expected,
            },
        ),
        flush=True,
    )
    api = GitHubAPI()
    include_headers = os.environ.get('PROBE_INCLUDE_HEADERS') == 'true'
    for attempt in range(1, 101 if include_headers else 21):
        started = time.monotonic()
        try:
            data = (included(identifier) if include_headers
                    else api.download(int(identifier)))
        except APIRequestError as error:
            print(
                json.dumps(
                    {
                        'attempt': attempt,
                        'exit': error.returncode,
                        'seconds': round(time.monotonic() - started, 3),
                        'stderr_encrypted': encrypted(error.stderr),
                    },
                ),
                flush=True,
            )
            return 1
        except subprocess.TimeoutExpired:
            print(json.dumps({'attempt': attempt, 'error': '120-second subprocess timeout'}))
            return 1
        actual = hashlib.sha256(data).hexdigest()
        print(
            json.dumps(
                {
                    'attempt': attempt,
                    'seconds': round(time.monotonic() - started, 3),
                    'bytes': len(data),
                    'sha256': actual,
                },
            ),
            flush=True,
        )
        if actual != expected:
            print('Downloaded bytes differ from the independently retained digest.')
            return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
