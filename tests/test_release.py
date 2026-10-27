# Copyright 2026 Axel Voitier
#
# spell-checker:ignore gpgsign nonmatching
# Keep the existing unittest framework and scripts-path bootstrap.
# ruff: noqa: PT009, PT027, INP001, E402
# Tests create local Git fixtures and exercise errors without changing the real checkout.
# ruff: noqa: S603, S607
"""Regression checks for the tag and artifact boundaries of a release."""

import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from check_release import git, verify_tag
from prepare_release import artifact_hashes, check_toolchain, prepare


class ReleaseTagChecks(unittest.TestCase):
    def setUp(self) -> None:
        """Create an independent repository with an annotated release tag."""
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name) / 'source'
        self.root.mkdir()
        git(self.root, 'init', '--quiet')
        git(self.root, 'config', 'user.name', 'Tarn tests')
        git(self.root, 'config', 'user.email', 'tarn-tests@example.invalid')
        git(self.root, 'config', 'commit.gpgsign', 'false')
        git(self.root, 'config', 'tag.gpgsign', 'false')
        (self.root / 'content.txt').write_text('tagged content\n', encoding='utf-8')
        git(self.root, 'add', 'content.txt')
        git(self.root, 'commit', '--quiet', '-m', 'Fixture')
        git(self.root, 'tag', '-a', 'v1.0.0', '-m', 'Fixture release')

    def test_existing_tag_records_exact_commit_and_tree(self) -> None:
        """Resolve annotated tags to their source commit, not the tag object."""
        result = verify_tag(self.root, 'v1.0.0', '1.0.0')
        self.assertEqual(result['commit'], git(self.root, 'rev-parse', 'HEAD'))
        self.assertEqual(result['tag_object'], git(self.root, 'rev-parse', 'refs/tags/v1.0.0'))
        self.assertNotEqual(result['tag_object'], result['commit'])
        self.assertEqual(result['tree'], git(self.root, 'rev-parse', 'HEAD^{tree}'))
        self.assertEqual(
            result['source_date_epoch'],
            int(git(self.root, 'show', '-s', '--format=%ct')),
        )

    def test_missing_tag_and_wrong_commit_are_rejected(self) -> None:
        """Reject text-only tags and tags on another commit."""
        with self.assertRaises(subprocess.CalledProcessError):
            verify_tag(self.root, 'v2.0.0', '2.0.0')
        (self.root / 'content.txt').write_text('later content\n', encoding='utf-8')
        git(self.root, 'commit', '--quiet', '-am', 'Later commit')
        with self.assertRaisesRegex(ValueError, 'checked-out commit'):
            verify_tag(self.root, 'v1.0.0', '1.0.0')

    def test_staged_unstaged_and_untracked_changes_are_rejected(self) -> None:
        """Exclude every kind of uncommitted source from release preparation."""
        (self.root / 'content.txt').write_text('changed\n', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'clean checkout'):
            verify_tag(self.root, 'v1.0.0', '1.0.0')
        git(self.root, 'add', 'content.txt')
        with self.assertRaisesRegex(ValueError, 'clean checkout'):
            verify_tag(self.root, 'v1.0.0', '1.0.0')
        git(self.root, 'restore', '--staged', '--worktree', 'content.txt')
        (self.root / 'untracked.txt').touch()
        with self.assertRaisesRegex(ValueError, 'clean checkout'):
            verify_tag(self.root, 'v1.0.0', '1.0.0')

    def test_multiple_version_tags_on_one_commit_are_rejected(self) -> None:
        """Prevent later tags from changing version inference for an old release."""
        git(self.root, 'tag', 'v1.0.1')
        with self.assertRaisesRegex(ValueError, 'single version tag'):
            verify_tag(self.root, 'v1.0.0', '1.0.0')

    def test_shallow_history_is_rejected(self) -> None:
        """Require full history so version inference cannot silently change."""
        shallow = Path(self.directory.name) / 'shallow'
        subprocess.run(
            ['git', 'clone', '--quiet', '--depth', '1', self.root.as_uri(), str(shallow)],
            check=True,
        )
        with self.assertRaisesRegex(ValueError, 'full Git history'):
            verify_tag(shallow, 'v1.0.0', '1.0.0')


class ReleaseArtifactChecks(unittest.TestCase):
    def test_release_check_requires_an_explicit_tag(self) -> None:
        """Keep the Hatch release check from approving untagged archives."""
        result = subprocess.run(
            [sys.executable, str(ROOT / 'scripts/check_release.py'), '--require-tag'],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('--require-tag requires --tag', result.stderr)

    def test_version_overrides_are_rejected_before_building(self) -> None:
        """Keep pretend versions from bypassing the Git version source."""
        with (
            patch.dict('os.environ', {'SETUPTOOLS_SCM_PRETEND_VERSION_FOR_ZENSICAL_TARN': '1.0.0'}),
            self.assertRaisesRegex(ValueError, 'version overrides'),
        ):
            check_toolchain(ROOT)

    def test_hashes_include_both_archive_bytes(self) -> None:
        """Detect a changed wheel or source archive instead of trusting filenames."""
        with TemporaryDirectory() as directory:
            root = Path(directory)
            wheel = root / 'theme.whl'
            source = root / 'theme.tar.gz'
            wheel.write_bytes(b'wheel')
            source.write_bytes(b'source')
            before = artifact_hashes(root)
            source.write_bytes(b'changed source')
            self.assertNotEqual(before, artifact_hashes(root))
            source.unlink()
            with self.assertRaisesRegex(ValueError, 'exactly one'):
                artifact_hashes(root)

    def test_nonmatching_builds_never_create_release_output(self) -> None:
        """Keep artifacts private until reproducibility and CI comparisons pass."""
        with TemporaryDirectory() as directory:
            root = Path(directory)
            first, second = root / 'first', root / 'second'
            for output in (first, second):
                output.mkdir()
                (output / 'theme.whl').write_bytes(b'wheel')
                (output / 'theme.tar.gz').write_bytes(b'source')
            (second / 'theme.whl').write_bytes(b'changed wheel')
            destination = root / 'release'
            with (
                patch('prepare_release.check_toolchain', return_value={}),
                patch('prepare_release.source_version', return_value='1.0.0'),
                patch('prepare_release.verify_tag', return_value={'source_date_epoch': 1}),
                patch('prepare_release.release_blockers', return_value=[]),
                patch('prepare_release.build_once', side_effect=[first, second]),
                self.assertRaisesRegex(ValueError, 'Independent builds differ'),
            ):
                prepare(root, 'v1.0.0', destination)
            self.assertFalse(destination.exists())
            with (
                patch('prepare_release.check_toolchain', return_value={}),
                patch('prepare_release.source_version', return_value='1.0.0'),
                patch('prepare_release.verify_tag', return_value={'source_date_epoch': 1}),
                patch('prepare_release.release_blockers', return_value=[]),
                patch('prepare_release.build_once', return_value=first),
                self.assertRaisesRegex(ValueError, 'CI-tested artifacts'),
            ):
                prepare(root, 'v1.0.0', destination, tested=second)
            self.assertFalse(destination.exists())


if __name__ == '__main__':
    unittest.main()
