# Keep unittest assertions, discovery and the existing scripts-path bootstrap.
# ruff: noqa: PT009, PT027, INP001, E402
# The subprocess runs the copied generator with fixed arguments from these tests.
# ruff: noqa: S603
# Copyright 2026 Axel Voitier
"""Regression tests for checks that protect the published theme artifacts."""

import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from check_package import inspect_site
from check_release import (
    check_licences,
    check_readme_images,
    check_sdist_contents,
    check_tag,
    release_blockers,
)
from check_upstream import check, upstream_form


class CssChecks(unittest.TestCase):
    def test_stale_and_failed_contrast_checks_do_not_write(self) -> None:
        """Keep existing CSS intact when validation fails."""
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for source in (
                'scripts/build_css.py',
                'design/tokens.json',
                'src/zensical_tarn/assets/stylesheets/tarn.css',
            ):
                target = root / source
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / source, target)
            css = root / 'src/zensical_tarn/assets/stylesheets/tarn.css'

            def run(*args: str) -> subprocess.CompletedProcess[str]:
                """Run the copied CSS generator and collect its output."""
                return subprocess.run(
                    [sys.executable, str(root / 'scripts/build_css.py'), *args],
                    capture_output=True,
                    text=True,
                    check=False,
                )

            self.assertEqual(run('--check').returncode, 0)
            css.write_text('stale CSS', encoding='utf-8')
            result = run('--check')
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('stale or missing', result.stderr)
            self.assertEqual(css.read_text(encoding='utf-8'), 'stale CSS')
            self.assertEqual(run().returncode, 0)
            self.assertEqual(
                css.read_bytes(),
                (ROOT / 'src/zensical_tarn/assets/stylesheets/tarn.css').read_bytes(),
            )

            tokens_path = root / 'design/tokens.json'
            tokens = json.loads(tokens_path.read_text(encoding='utf-8'))
            colours = {token['name']: token for token in tokens['color']['tokens']}
            colours['ink']['value'] = colours['surface']['value']
            tokens_path.write_text(json.dumps(tokens), encoding='utf-8')
            before = css.read_bytes()
            for args in ((), ('--check',)):
                result = run(*args)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('contrast failure', result.stderr)
                self.assertEqual(css.read_bytes(), before)


class UpstreamChecks(unittest.TestCase):
    def test_drift_and_missing_tarn_additions_fail(self) -> None:
        """Reject upstream drift and missing Tarn additions."""
        with TemporaryDirectory() as directory:
            root = Path(directory)
            tarn = root / 'tarn'
            upstream = root / 'upstream'
            shutil.copytree(ROOT / 'src/zensical_tarn/partials', tarn / 'partials')
            (upstream / 'partials').mkdir(parents=True)
            for name in ('nav-item.html', 'tabs-item.html', 'copyright.html'):
                source = (tarn / 'partials' / name).read_text(encoding='utf-8')
                (upstream / 'partials' / name).write_text(
                    upstream_form(name, source),
                    encoding='utf-8',
                )
            check(tarn, upstream)
            path = upstream / 'partials/nav-item.html'
            path.write_text(
                path.read_text(encoding='utf-8') + 'upstream changed\n',
                encoding='utf-8',
            )
            with self.assertRaisesRegex(ValueError, 'Upstream template drift'):
                check(tarn, upstream)
            source = (tarn / 'partials/tabs-item.html').read_text(encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'expected 1 Tarn addition'):
                upstream_form(
                    'tabs-item.html',
                    source.replace(' {{ tarn.navigation_attributes(first) }}', ''),
                )


class OutputChecks(unittest.TestCase):
    def test_unexpected_internals_and_missing_theme_features_fail(self) -> None:
        """Reject leaked internals and missing theme output."""
        with TemporaryDirectory() as directory:
            root = Path(directory)
            site = root / 'site'
            page = site / 'how-to/index.html'
            page.parent.mkdir(parents=True)
            css = site / 'assets/stylesheets/tarn.css'
            css.parent.mkdir(parents=True)
            shutil.copyfile(ROOT / 'src/zensical_tarn/assets/stylesheets/tarn.css', css)
            html = '<link rel="stylesheet" href="../assets/stylesheets/tarn.css">'
            html += '<span class="tarn-dtx tarn-dtx--howto">How-to guide</span>'
            html += ''.join(
                f'<li class="md-tabs__item" data-tarn-url="{folder}/"></li>'
                for folder in ('tutorials', 'how-to', 'reference', 'explanation')
            )
            page.write_text(html, encoding='utf-8')
            theme = ROOT / 'src/zensical_tarn'
            inspect_site(site, page, theme, clean=True)
            internal = site / '__init__.py'
            internal.touch()
            inspect_site(site, page, theme, clean=False)
            with self.assertRaisesRegex(ValueError, 'Package internals'):
                inspect_site(site, page, theme, clean=True)
            internal.unlink()
            unexpected = site / 'surprise.py'
            unexpected.touch()
            with self.assertRaisesRegex(ValueError, 'surprise.py'):
                inspect_site(site, page, theme, clean=False)
            unexpected.unlink()
            page.write_text(html.replace('tarn-dtx--howto', 'other'), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'missing how-to badge'):
                inspect_site(site, page, theme, clean=True)


class ReleaseChecks(unittest.TestCase):
    def test_readme_images_use_checkout_files_without_network(self) -> None:
        """Check local and repository-hosted README images without bundling them."""
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'README.md').write_text(
                '<img src="https://raw.githubusercontent.com/AxelVoitier/zensical-tarn/main/logo.png">'
                '\n![Preview](screenshots/preview.png)\n',
                encoding='utf-8',
            )
            (root / 'logo.png').write_bytes(b'logo')
            (root / 'screenshots').mkdir()
            image = root / 'screenshots/preview.png'
            image.write_bytes(b'preview')
            self.assertEqual(check_readme_images(root), ['logo.png', 'screenshots/preview.png'])
            image.unlink()
            with self.assertRaisesRegex(ValueError, 'README image missing from checkout'):
                check_readme_images(root)

    def test_source_contract_rejects_missing_inputs_exclusions_and_oversize(self) -> None:
        """Keep standalone sources complete and reject galleries or oversized archives."""
        contents = {
            path.relative_to(ROOT).as_posix(): path.read_bytes()
            for pattern in (
                'src/**/*',
                'scripts/*',
                'tests/*.py',
                'LICENSES/*',
                '*.toml',
                '*.md',
                'LICENSE',
                'NOTICE',
                'pyrightconfig.json',
                'design/tokens.json',
                'design/README.md',
                'docs/about/index.md',
                'docs/contributing/index.md',
            )
            for path in ROOT.glob(pattern)
            if path.is_file() and '__pycache__' not in path.parts
        }
        contents['PKG-INFO'] = b'Metadata-Version: 2.4'
        check_sdist_contents(ROOT, contents, 1_048_576)
        with self.assertRaisesRegex(ValueError, '1,048,576'):
            check_sdist_contents(ROOT, contents, 1_048_577)
        for name in (
            'screenshots/site/gallery.png',
            'examples/minimal-site/zensical.toml',
            'docs/index.md',
            'design/logo/logo.svg',
            'ai-works/private.md',
        ):
            with self.subTest(excluded=name), self.assertRaisesRegex(ValueError, 'Excluded'):
                check_sdist_contents(ROOT, {**contents, name: b'excluded'}, 100)
        for name in ('design/tokens.json', 'docs/about/index.md', 'tests/test_checks.py'):
            incomplete = dict(contents)
            del incomplete[name]
            with (
                self.subTest(missing=name),
                self.assertRaisesRegex(ValueError, 'missing or changed'),
            ):
                check_sdist_contents(ROOT, incomplete, 100)

    def test_wrong_proposed_tag_is_rejected(self) -> None:
        """Accept matching tags and reject unrelated version tags."""
        for tag in (None, '0.1.0', 'v0.1.0'):
            check_tag('0.1.0', tag)
        for tag in ('v0.2.0', 'latest', 'v0.1.0\n'):
            with self.assertRaisesRegex(ValueError, 'does not match'):
                check_tag('0.1.0', tag)

    def test_missing_or_altered_licence_in_either_archive_is_rejected(self) -> None:
        """Reject missing or changed licence files in either archive."""
        expected = {'LICENSE': b'original licence', 'NOTICE': b'attribution'}
        wheel = {f'theme.dist-info/licenses/{name}': data for name, data in expected.items()}
        sdist = dict(expected)
        check_licences(expected, wheel, sdist, 'theme.dist-info')
        for target, path in ((wheel, 'theme.dist-info/licenses/NOTICE'), (sdist, 'NOTICE')):
            original = target.pop(path)
            with self.assertRaisesRegex(ValueError, 'missing or changed: NOTICE'):
                check_licences(expected, wheel, sdist, 'theme.dist-info')
            target[path] = b'different attribution'
            with self.assertRaisesRegex(ValueError, 'missing or changed: NOTICE'):
                check_licences(expected, wheel, sdist, 'theme.dist-info')
            target[path] = original

    def test_unconfirmed_decisions_and_placeholder_urls_are_reported(self) -> None:
        """Report missing review decisions and placeholder URLs."""
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for name in (
                'pyproject.toml',
                'README.md',
                'zensical.toml',
                'CHANGELOG.md',
                'docs/about/index.md',
                'docs/contributing/index.md',
                'design/README.md',
                'src/zensical_tarn/partials/tarn.html',
                'release-review.toml',
            ):
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / name, target)
            self.assertEqual(release_blockers(root), [])
            review = root / 'release-review.toml'
            review.write_text(review.read_text().replace('licence = true', 'licence = false'))
            (root / 'README.md').write_text('https://OWNER.github.io/zensical-tarn/')
            blockers = release_blockers(root)
            self.assertIn('Unconfirmed decision: licence', blockers)
            self.assertTrue(any('README.md:1' in blocker for blocker in blockers))


if __name__ == '__main__':
    unittest.main()
