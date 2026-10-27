#!/usr/bin/env python3
# Copyright 2026 Axel Voitier
#
# spell-checker:ignore Diátaxis
# Invoke with Python; report package-check results on stdout.
# ruff: noqa: EXE001, T201
# Keep validation messages in the existing raise expressions.
# ruff: noqa: EM101, EM102, TRY003
# Delay importing Zensical so unit tests can import the independent helpers.
# ruff: noqa: PLC0415
# Keep the existing installed-version status message intact.
# ruff: noqa: E501
# Preserve the existing nested loop and its local variable reuse.
# ruff: noqa: PLW2901

"""Build example sites outside the checkout using an installed Tarn wheel.

Known package-file copying in Zensical 0.0.73 is reported explicitly. The
project-level exclusion workaround must produce clean output; new leaks fail.
"""

import shutil
import subprocess
import sys
from html.parser import HTMLParser
from importlib import metadata
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import unquote, urlsplit

from check_upstream import check

ROOT = Path(__file__).resolve().parent.parent
EXCLUSION_CONFIG = """
[project.plugins.exclude]
glob = ["__init__.py", "__pycache__/*", "mkdocs_theme.yml"]
"""


class Page(HTMLParser):
    def __init__(self) -> None:
        """Initialise the parser and its collected page data."""
        super().__init__()
        self.stylesheets: list[str] = []
        self.tabs: set[str] = set()
        self.badges: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Collect the relevant attributes from an opening HTML tag."""
        values = dict(attrs)
        classes = (values.get('class') or '').split()
        if tag == 'link' and values.get('rel') == 'stylesheet':
            self.stylesheets.append(values.get('href') or '')
        if tag == 'li' and 'md-tabs__item' in classes:
            self.tabs.add(values.get('data-tarn-url') or '')
        if tag == 'span' and 'tarn-dtx' in classes:
            self.badges.update(classes)


def inspect_site(site: Path, page: Path, theme: Path, *, clean: bool) -> None:
    """Check stylesheet bytes, navigation badges and leaked package files."""
    parsed = Page()
    parsed.feed(page.read_text(encoding='utf-8'))
    css_links = [
        href for href in parsed.stylesheets if href.endswith('assets/stylesheets/tarn.css')
    ]
    if len(css_links) != 1:
        raise ValueError(f'{page}: expected one Tarn stylesheet link, got {css_links}')
    css = (page.parent / unquote(urlsplit(css_links[0]).path)).resolve()
    expected_css = theme / 'assets/stylesheets/tarn.css'
    if (
        css != (site / 'assets/stylesheets/tarn.css').resolve()
        or css.read_bytes() != expected_css.read_bytes()
    ):
        raise ValueError(f'{page}: stylesheet is missing or differs from installed theme')
    if not {'tutorials/', 'how-to/', 'reference/', 'explanation/'} <= parsed.tabs:
        raise ValueError(f'{page}: missing Diátaxis tab attributes: {parsed.tabs}')
    if 'tarn-dtx--howto' not in parsed.badges:
        raise ValueError(f'{page}: missing how-to badge')

    internals = {
        path.relative_to(site).as_posix()
        for path in site.rglob('*')
        if path.is_file()
        and (path.suffix in {'.py', '.pyc', '.pyo', '.yml', '.yaml'} or '__pycache__' in path.parts)
    }
    known = {
        '__init__.py',
        'mkdocs_theme.yml',
        f'__pycache__/__init__.{sys.implementation.cache_tag}.pyc',
    }
    unexpected = internals if clean else internals - known
    if unexpected:
        raise ValueError(f'Package internals in generated site: {sorted(unexpected)}')
    if internals:
        print(f'KNOWN Zensical 0.0.73 output limitation: {sorted(internals)}', flush=True)
    print(f'Verified site: {page.relative_to(site)} (clean output required: {clean})', flush=True)


def main() -> None:
    """Verify installed theme resources and generated example sites."""
    import zensical

    (entry,) = metadata.entry_points(group='mkdocs.themes', name='tarn')
    if entry.value != 'zensical_tarn':
        raise ValueError(f'Unexpected theme entry point: {entry.value}')
    theme = Path(entry.load().__file__).resolve().parent
    if theme.is_relative_to(ROOT):
        raise ValueError('Install a built wheel; this check must not use the checkout')
    distribution = metadata.distribution('zensical-tarn')
    if distribution.metadata['Requires-Python'] != '>=3.11':
        raise ValueError('The installed distribution must advertise Python >=3.11')
    check(theme, Path(zensical.__file__).resolve().parent / 'templates')
    print(
        f'Testing installed Tarn {distribution.version} with Zensical {metadata.version("zensical")}',
        flush=True,
    )

    with TemporaryDirectory(prefix='tarn-package-') as directory:
        work = Path(directory)
        for name, source, howto in (
            ('documentation', ROOT, 'how-to/name-sections/index.html'),
            ('minimal', ROOT / 'examples/minimal-site', 'how-to/index.html'),
        ):
            project = work / name
            project.mkdir()
            shutil.copytree(source / 'docs', project / 'docs')
            shutil.copyfile(source / 'zensical.toml', project / 'zensical.toml')
            subprocess.run(
                [sys.executable, '-m', 'zensical', 'build', '--strict', '--clean'],
                cwd=project,
                check=True,
            )
            inspect_site(
                project / 'site',
                project / 'site' / howto,
                theme,
                clean=name == 'documentation',
            )
            for source in (theme / 'assets/licenses/tarn').glob('*.txt'):
                output = project / 'site/assets/licenses/tarn' / source.name
                if not output.is_file() or output.read_bytes() != source.read_bytes():
                    raise ValueError(f'Licence notice missing from generated site: {source.name}')

        # Prove the supported project-level workaround, without imposing it on users.
        project = work / 'minimal'
        with (project / 'zensical.toml').open('a', encoding='utf-8') as config:
            config.write(EXCLUSION_CONFIG)
        shutil.rmtree(project / 'site')
        subprocess.run(
            [sys.executable, '-m', 'zensical', 'build', '--strict', '--clean'],
            cwd=project,
            check=True,
        )
        inspect_site(project / 'site', project / 'site/how-to/index.html', theme, clean=True)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        sys.exit(str(error))
