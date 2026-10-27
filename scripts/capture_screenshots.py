#!/usr/bin/env python3
# Copyright 2026 Axel Voitier
#
# spell-checker:ignore Hyperlegible diataxis fulfill networkidle scrollwrap
# Invoke with Python; progress belongs on stdout.
# ruff: noqa: EXE001, T201
# Keep the original capture orchestration in its existing functions.
# ruff: noqa: C901, PLR0912, PLR0915
# Keep validation messages in the existing raise expressions.
# ruff: noqa: EM101, EM102, TRY003
# Page callbacks finish within their current browser context and loop iteration.
# ruff: noqa: B023
# Keep literal selectors, JavaScript and configuration snippets intact.
# ruff: noqa: E501
# Font routes request HTTPS Google Fonts URLs; keep the existing downloader.
# ruff: noqa: S310
# Retain the no-op handler body and existing screenshot dimensions.
# ruff: noqa: PIE790, PLR2004

"""Rebuild the documentation screenshots with the installed theme and configured fonts.

Requires Playwright, Chromium, and network access to Google Fonts. The exported
design-preview cards have no HTML sources here and are not regenerated.
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
import tomllib
from functools import lru_cache, partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from textwrap import dedent
from threading import Thread
from urllib.request import Request, urlopen

from playwright.sync_api import Locator, Page, Route, sync_playwright

ROOT = Path(__file__).resolve().parent.parent


class Handler(SimpleHTTPRequestHandler):
    # Keep the original positional-only no-op override; the server calls it positionally.
    def log_message(self, *args: object) -> None:  # pyright: ignore[reportIncompatibleMethodOverride]
        """Suppress request logging during local browser checks."""
        pass


@lru_cache(maxsize=64)
def fetch_font(url: str) -> tuple[bytes, str]:
    """Fetch and cache a font response and its media type."""
    with urlopen(Request(url, headers={'User-Agent': 'Mozilla/5.0'}), timeout=30) as response:
        return response.read(), response.headers.get_content_type()


def font_route(route: Route) -> None:
    """Serve a requested font through the cached downloader."""
    body, content_type = fetch_font(route.request.url)
    route.fulfill(body=body, content_type=content_type)


def build(project: Path) -> None:
    """Build the fixture site with strict checks enabled."""
    subprocess.run(
        [sys.executable, '-m', 'zensical', 'build', '--strict', '--clean'],
        cwd=project,
        check=True,
    )


def crop(page: Page, locator: Locator, path: Path) -> None:
    """Capture the combined bounds of the selected elements."""
    page.evaluate("""async () => {
      scrollTo(0, 0);
      await new Promise(requestAnimationFrame);
      await new Promise(requestAnimationFrame);
    }""")
    bounds = locator.evaluate_all("""elements => {
      const boxes = elements.map(e => e.getBoundingClientRect());
      const x = Math.min(...boxes.map(b => b.left)) + scrollX;
      const y = Math.min(...boxes.map(b => b.top)) + scrollY;
      return {x, y, width: Math.max(...boxes.map(b => b.right)) + scrollX - x,
                    height: Math.max(...boxes.map(b => b.bottom)) + scrollY - y};
    }""")
    if bounds['width'] <= 0 or bounds['height'] <= 0:
        raise RuntimeError(f'Empty screenshot bounds for {path}')
    if 'sidebar-navigation' in path.name and bounds['height'] < 200:
        raise RuntimeError(f'Sidebar has not settled for {path}: {bounds}')
    page.screenshot(path=str(path), clip=bounds, full_page=True, animations='disabled')


def guide_source(filename: str, language: str) -> str:
    """Read the first code example of a language from an authored guide."""
    text = (ROOT / 'docs/how-to' / filename).read_text(encoding='utf-8')
    match = re.search(rf'(?m)^[ \t]*```{language}[^\n]*\n(.*?)^[ \t]*```', text, re.DOTALL)
    if match is None:
        raise ValueError(f'No {language} example in {filename}')
    return dedent(match[1])


def capture_guide_results(executable: str | None = None) -> None:
    """Build the guides' examples and capture their actual navigation and CSS."""
    with TemporaryDirectory(prefix='tarn-guide-results-') as directory:
        root = Path(directory)
        navigation = """nav = [
  {"Home" = "index.md"},
  {"Getting started" = ["getting-started/index.md"]},
  {"Tasks" = ["tasks/deploy.md"]},
  {"Architecture" = ["architecture/index.md"]},
  {"Examples" = ["examples/index.md"]},
  {"Release notes" = ["release-notes/index.md"]},
]"""
        pages = {
            'index.md': '# My project\n',
            'getting-started/index.md': '# Getting started\n',
            'tasks/deploy.md': '# Deploy the site\n',
            'architecture/index.md': '# Architecture\n',
            'examples/index.md': '# Examples\n',
            'release-notes/index.md': '# Release notes\n',
        }
        for name in ('sections', 'colour'):
            project = root / name
            docs = project / 'docs'
            docs.mkdir(parents=True)
            if name == 'sections':
                for filename, content in pages.items():
                    path = docs / filename
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(content, encoding='utf-8')
                project_settings = navigation
                settings = guide_source('name-sections.md', 'toml')
            else:
                (docs / 'index.md').write_text(
                    '# Colour override\n\n' + guide_source('adjust-colours.md', 'markdown'),
                    encoding='utf-8',
                )
                (docs / 'stylesheets').mkdir()
                (docs / 'stylesheets/extra.css').write_text(
                    guide_source('adjust-colours.md', 'css'),
                    encoding='utf-8',
                )
                project_settings = guide_source('adjust-colours.md', 'toml').split('[project]', 1)[
                    1
                ]
                settings = ''
            (project / 'zensical.toml').write_text(
                '[project]\nsite_name = "My project"\n'
                + project_settings
                + '\n[project.theme]\nname = "tarn"\n'
                + '[project.plugins.exclude]\n'
                + 'glob = ["__init__.py", "__pycache__/*", "mkdocs_theme.yml"]\n'
                + settings,
                encoding='utf-8',
            )
            build(project)
        server = ThreadingHTTPServer(('127.0.0.1', 0), partial(Handler, directory=str(root)))
        Thread(target=server.serve_forever, daemon=True).start()
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True, executable_path=executable)
                try:
                    context = browser.new_context(
                        viewport={'width': 1280, 'height': 720},
                        device_scale_factor=2,
                        color_scheme='light',
                    )
                    page = context.new_page()
                    page.route('https://fonts.googleapis.com/**', font_route)
                    page.route('https://fonts.gstatic.com/**', font_route)
                    output = ROOT / 'docs/assets/screenshots'
                    for name, target in (
                        ('sections', 'mapped-sections-tabs.png'),
                        ('colour', 'adjust-colour-result.png'),
                    ):
                        page.goto(
                            f'http://127.0.0.1:{server.server_port}/{name}/site/',
                            wait_until='networkidle',
                        )
                        page.evaluate('document.fonts.ready')
                        if not page.evaluate(
                            'Array.from(document.fonts).some(f => f.status === "loaded" && f.family.includes("Atkinson Hyperlegible Next"))'
                        ):
                            raise RuntimeError('Configured text font did not load')
                        if name == 'sections':
                            for kind in (
                                'tutorial',
                                'howto',
                                'explanation',
                                'primary',
                                'secondary',
                            ):
                                if not page.locator(
                                    f'.md-tabs__item[data-tarn-type="{kind}"]',
                                ).count():
                                    raise RuntimeError(f'Missing mapped navigation type: {kind}')
                            locator = page.locator('.md-header, .md-tabs')
                        else:
                            colour = page.locator('.md-content p > code').evaluate(
                                'el => getComputedStyle(el).color',
                            )
                            if colour != 'rgb(91, 42, 122)':
                                raise RuntimeError(f'Colour override was not applied: {colour}')
                            locator = page.locator('.md-content__inner')
                        crop(page, locator, output / target)
                    context.close()
                finally:
                    browser.close()
        finally:
            server.shutdown()
            server.server_close()
        print('Refreshed mapped-section and colour-result screenshots', flush=True)


def main() -> None:
    """Build and capture the guide examples and documentation pages."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--executable', help='Optional Chromium executable path')
    parser.add_argument(
        '--guide-results',
        action='store_true',
        help='Refresh only the section-mapping and colour-override examples',
    )
    args = parser.parse_args()
    capture_guide_results(args.executable)
    if args.guide_results:
        return
    output = ROOT / 'screenshots'
    for folder in ('site', 'components'):
        (output / folder).mkdir(exist_ok=True)
    with TemporaryDirectory(prefix='tarn-screenshots-') as directory:
        root = Path(directory)
        for layout in ('tabs', 'sidebar'):
            project = root / layout
            project.mkdir()
            shutil.copytree(ROOT / 'docs', project / 'docs')
            config = (ROOT / 'zensical.toml').read_text(encoding='utf-8')
            if layout == 'sidebar':
                features = tomllib.loads(config)['project']['theme']['features']
                features = [
                    'navigation.sections' if feature == 'navigation.tabs' else feature
                    for feature in features
                ]
                config, replacements = re.subn(
                    r'(?ms)^features\s*=\s*\[.*?\]',
                    lambda _: 'features = ' + json.dumps(features),
                    config,
                    count=1,
                )
                if replacements != 1:
                    raise RuntimeError('Expected one site feature list for the sidebar capture')
            (project / 'zensical.toml').write_text(config, encoding='utf-8')
            build(project)
        server = ThreadingHTTPServer(('127.0.0.1', 0), partial(Handler, directory=str(root)))
        Thread(target=server.serve_forever, daemon=True).start()
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True, executable_path=args.executable)
                try:
                    # Capture both preview modes before pages that embed them.
                    for phase in ('previews', 'pages'):
                        for scheme in ('light', 'dark'):
                            context = browser.new_context(
                                viewport={'width': 1280, 'height': 860},
                                device_scale_factor=2,
                                color_scheme=scheme,
                            )
                            page = context.new_page()
                            page.route('https://fonts.googleapis.com/**', font_route)
                            page.route('https://fonts.gstatic.com/**', font_route)

                            def visit(layout: str, path: str) -> None:
                                """Open a page, select its colour mode and wait for fonts."""
                                page.goto(
                                    f'http://127.0.0.1:{server.server_port}/{layout}/site/{path}',
                                    wait_until='networkidle',
                                )
                                # Select explicitly: the documentation may default to a fixed mode.
                                wanted = 'slate' if scheme == 'dark' else 'default'
                                if (
                                    page.locator('body').get_attribute('data-md-color-scheme')
                                    != wanted
                                ):
                                    target = page.locator(
                                        f'[data-md-component="palette"] input[data-md-color-scheme="{wanted}"]',
                                    ).get_attribute('id')
                                    page.locator(
                                        f'[data-md-component="palette"] label[for="{target}"]',
                                    ).click()
                                    page.wait_for_function(
                                        'scheme => document.body.dataset.mdColorScheme === scheme',
                                        arg=wanted,
                                    )
                                page.evaluate('document.fonts.ready')
                                if not page.evaluate(
                                    'Array.from(document.fonts).some(f => f.status === "loaded" && f.family.includes("Atkinson Hyperlegible Next"))'
                                ):
                                    raise RuntimeError(
                                        'Configured text font did not load; screenshots not captured',
                                    )

                            if phase == 'previews':
                                for layout, name in (
                                    ('tabs', 'howto'),
                                    ('sidebar', 'sidebar-navigation'),
                                ):
                                    visit(layout, 'how-to/name-sections/')
                                    path = output / 'site' / f'site-{name}-{scheme}.png'
                                    page.screenshot(
                                        path=str(path),
                                        full_page=True,
                                        animations='disabled',
                                    )
                                    if name == 'howto' or scheme == 'light':
                                        target = Path('assets/screenshots') / path.name
                                        shutil.copyfile(path, ROOT / 'docs' / target)
                                        for variant in ('tabs', 'sidebar'):
                                            shutil.copyfile(path, root / variant / 'docs' / target)
                            else:
                                for name, path in {
                                    'home': '',
                                    'tutorial': 'tutorials/first-site/',
                                    'reference': 'reference/configuration/',
                                    'explanation': 'explanation/diataxis-navigation/',
                                    'about': 'about/',
                                    'components': 'reference/components/',
                                }.items():
                                    visit('tabs', path)
                                    page.screenshot(
                                        path=str(output / 'site' / f'site-{name}-{scheme}.png'),
                                        full_page=True,
                                        animations='disabled',
                                    )
                                visit('tabs', 'reference/components/')
                                crops = {
                                    'admonitions': page.locator('.admonition'),
                                    'code-block': page.locator('.highlight')
                                    .filter(has=page.locator('.filename', has_text='zensical.toml'))
                                    .first,
                                    'content-tabs': page.locator('.tabbed-set').first,
                                    'table': page.locator('.md-typeset__table')
                                    .filter(
                                        has=page.get_by_role('cell', name='enabled', exact=True),
                                    )
                                    .first,
                                    'buttons': page.locator('p')
                                    .filter(has=page.locator('.md-button'))
                                    .first,
                                    'diataxis-badges': page.locator('p')
                                    .filter(has=page.locator('.tarn-dtx'))
                                    .first,
                                    'inline-code-keys-mark': page.locator('p')
                                    .filter(has_text='Inline:')
                                    .first,
                                    'header-and-tabs': page.locator('.md-header, .md-tabs'),
                                }
                                for name, locator in crops.items():
                                    crop(
                                        page,
                                        locator,
                                        output / 'components' / f'{name}-{scheme}.png',
                                    )
                                visit('sidebar', 'how-to/name-sections/')
                                crop(
                                    page,
                                    page.locator('.md-sidebar--primary .md-sidebar__scrollwrap'),
                                    output / 'components' / f'sidebar-navigation-{scheme}.png',
                                )
                            context.close()
                            print(f'Refreshed {scheme} {phase} screenshots', flush=True)
                        if phase == 'previews':
                            for variant in ('tabs', 'sidebar'):
                                build(root / variant)
                finally:
                    browser.close()
        finally:
            server.shutdown()
            server.server_close()


if __name__ == '__main__':
    main()
