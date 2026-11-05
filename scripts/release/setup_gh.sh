#!/usr/bin/env bash
# Copyright 2026 Axel Voitier
# Fixed Linux amd64 runtime for the reviewed hosted verifier jobs.
set -euo pipefail

test "$(uname -s)" = Linux
test "$(uname -m)" = x86_64
directory=$(mktemp -d "$RUNNER_TEMP/tarn-gh.XXXXXX")
archive="$directory/gh.tar.gz"
curl --fail --location --retry 3 \
  --output "$archive" \
  https://github.com/cli/cli/releases/download/v2.99.0/gh_2.99.0_linux_amd64.tar.gz
printf '%s  %s\n' \
  ed4960225d2833e04a61590d9fa2b5773d147f3aa375459e5466a40c102f3832 \
  "$archive" | sha256sum --check --status
tar --extract --gzip --file "$archive" --directory "$directory" \
  --strip-components=1 gh_2.99.0_linux_amd64/bin/gh
test "$("$directory/bin/gh" --version | head -n 1 | cut -d ' ' -f 3)" = 2.99.0
printf '%s\n' "$directory/bin" >> "$GITHUB_PATH"
