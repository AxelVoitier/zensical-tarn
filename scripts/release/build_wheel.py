#!/usr/bin/env python3
# Copyright 2026 Axel Voitier
# ruff: noqa: EXE001
"""Run the fixed shared wheel stage only in an unprivileged package job."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from prepare_release import build_wheel
from release.sdist import source_identity


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tag', required=True)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--tag-ref-target', required=True)
    parser.add_argument('--tag-ref-type', required=True, choices=['tag', 'commit'])
    parser.add_argument('--sdist', required=True, type=Path)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    identity = source_identity(
        root,
        args.tag,
        args.commit,
        tag_ref_target=args.tag_ref_target,
        tag_ref_type=args.tag_ref_type,
    )
    build_wheel(root, args.sdist, args.sha256, args.output, str(identity['source_date_epoch']))


if __name__ == '__main__':
    main()
