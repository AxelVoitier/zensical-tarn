#!/usr/bin/env bash
# Copyright 2026 Axel Voitier
# Fixed Linux amd64 keyless signer for the isolated hosted signing jobs.
set -euo pipefail

test "$(uname -s)" = Linux
test "$(uname -m)" = x86_64
directory=$(mktemp -d "$RUNNER_TEMP/tarn-cosign.XXXXXX")
binary="$directory/cosign"
curl --fail --location --retry 3 \
  --output "$binary" \
  https://github.com/sigstore/cosign/releases/download/v3.1.4/cosign-linux-amd64
printf '%s  %s\n' \
  424e2c97d0b45fd7a6b608a87f090f35633f4c23ece5f092d48bba11aaf4bbfa \
  "$binary" | sha256sum --check --status
chmod 755 "$binary"
"$binary" version --json | python3 -c \
  'import json, sys; assert json.load(sys.stdin)["gitVersion"] == "v3.1.4"'
printf '%s\n' "$directory" >> "$GITHUB_PATH"
