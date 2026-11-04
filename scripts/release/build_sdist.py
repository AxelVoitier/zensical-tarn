#!/usr/bin/env python3
# Copyright 2026 Axel Voitier
# ruff: noqa: EXE001, T201
# This entry point runs package code exclusively in the unprivileged build role.
"""Build the sdist through the shared release preparation authority."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from prepare_release import build_sdist
from release.sdist import source_identity


def main() -> None:
    """Validate frozen source before invoking the existing package build stage."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('tag')
    parser.add_argument('commit')
    parser.add_argument('output', type=Path)
    parser.add_argument('--tag-ref-target', required=True)
    parser.add_argument('--tag-ref-type', choices=['tag', 'commit'], required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    source_identity(
        root,
        args.tag,
        args.commit,
        tag_ref_target=args.tag_ref_target,
        tag_ref_type=args.tag_ref_type,
    )
    archive = build_sdist(root, args.tag, args.output)
    source_identity(
        root,
        args.tag,
        args.commit,
        tag_ref_target=args.tag_ref_target,
        tag_ref_type=args.tag_ref_type,
    )
    print(archive)


if __name__ == '__main__':
    main()
