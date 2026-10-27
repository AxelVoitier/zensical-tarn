#!/usr/bin/env python3
# Copyright 2026 Axel Voitier
#
# spell-checker:ignore networkidle
# Invoke with Python; report the check result on stdout.
# ruff: noqa: EXE001, T201
# Keep the existing browser-check sequence together.
# ruff: noqa: PLR0912, PLR0915
# Keep literal selectors and JavaScript checks unchanged.
# ruff: noqa: E501
# The page-error callback runs before its current context is closed.
# ruff: noqa: B023
# Retain the no-op handler body and existing viewport expectations.
# ruff: noqa: PIE790, PLR2004
# Preserve the existing overridable artifacts-directory default.
# ruff: noqa: S108

"""Check computed styles and interactions in Chromium; save screenshots and a report."""

import argparse
import json
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from typing import cast

from check_config import make_site, require
from playwright.sync_api import sync_playwright


class Handler(SimpleHTTPRequestHandler):
    # Keep the original positional-only no-op override; the server calls it positionally.
    def log_message(self, *args: object) -> None:  # pyright: ignore[reportIncompatibleMethodOverride]
        """Suppress request logging during local browser checks."""
        pass


def main() -> None:
    """Run Chromium checks across layouts, colour modes and viewport sizes."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--executable', help='Optional Chromium executable path')
    parser.add_argument('--artifacts', type=Path, default=Path('/tmp/tarn-browser-artifacts'))
    args = parser.parse_args()
    args.artifacts.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, object]] = []
    with TemporaryDirectory(prefix='tarn-browser-') as directory:
        root = Path(directory)
        make_site(root, 'tabs', theme='font = false')
        make_site(
            root,
            'sidebar',
            theme='font = false\nfeatures = ["navigation.sections", "navigation.indexes", "content.code.copy"]',
        )
        make_site(root, 'classic', theme='font = false\nvariant = "classic"')
        make_site(root, 'fallback', theme='font = false\npalette = []')
        make_site(
            root,
            'named',
            theme='font = false\npalette = [{scheme = "default", primary = "red", accent = "green"}]',
        )
        make_site(root, 'fonts', theme='font = {text = "Inter", code = "JetBrains Mono"}')
        make_site(
            root,
            'custom-css',
            project='extra_css = ["extra.css"]',
            theme='font = false',
            css='[data-md-color-scheme="default"] { --tarn-inline-ink: rgb(100, 20, 90); }\n',
        )
        server = ThreadingHTTPServer(('127.0.0.1', 0), partial(Handler, directory=str(root)))
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(executable_path=args.executable, headless=True)
                try:
                    for layout in ('tabs', 'sidebar', 'classic'):
                        for scheme in ('light', 'dark'):
                            for width in (390, 820, 1280):
                                context = browser.new_context(
                                    viewport={'width': width, 'height': 900},
                                    color_scheme=scheme,
                                )
                                page = context.new_page()
                                page.set_default_timeout(10000)
                                errors: list[str] = []
                                page.on('pageerror', lambda error: errors.append(str(error)))
                                # Browser checks must not depend on third-party font/network availability.
                                page.route(
                                    '**/*',
                                    lambda route: (
                                        route.continue_()
                                        if route.request.url.startswith('http://127.0.0.1:')
                                        else route.abort()
                                    ),
                                )
                                url = f'http://127.0.0.1:{server.server_port}/{layout}/site/how-to/deep/start/'
                                page.goto(url, wait_until='networkidle')
                                require(
                                    page.locator('.tarn-dtx--howto').is_visible(),
                                    'Missing visible badge',
                                )
                                background = page.locator('.md-main').evaluate(
                                    'el => getComputedStyle(el).backgroundColor',
                                )
                                require(
                                    background
                                    == (
                                        'rgb(20, 26, 54)'
                                        if scheme == 'dark'
                                        else 'rgb(234, 229, 223)'
                                    ),
                                    f'{layout}/{scheme}/{width}: unexpected background {background}',
                                )
                                require(
                                    page.evaluate(
                                        'document.documentElement.scrollWidth <= innerWidth',
                                    ),
                                    f'{layout}/{scheme}/{width}: page overflows horizontally',
                                )
                                page.locator('label[for="__tabbed_1_2"]').click()
                                require(
                                    page.locator('#__tabbed_1_2').is_checked(),
                                    'Content tabs did not switch',
                                )
                                if width < 1220:
                                    page.locator('.md-header__button[for="__drawer"]').click()
                                    require(
                                        page.locator('#__drawer').is_checked(),
                                        'Drawer did not open',
                                    )
                                    require(
                                        page.locator(
                                            '.md-sidebar--primary [data-tarn-type="howto"]',
                                        ).is_visible(),
                                        'Drawer lost section decoration',
                                    )
                                    page.screenshot(
                                        path=str(
                                            args.artifacts
                                            / f'{layout}-{scheme}-{width}-drawer.png',
                                        ),
                                        animations='disabled',
                                    )
                                    overlay = page.locator('.md-overlay')
                                    overlay.click(
                                        position={
                                            'x': cast('dict[str, float]', overlay.bounding_box())[
                                                'width'
                                            ]
                                            - 10,
                                            'y': 300,
                                        },
                                    )
                                    page.wait_for_function(
                                        "!document.querySelector('#__drawer').checked",
                                    )
                                elif layout != 'sidebar':
                                    dot = page.locator(
                                        '.md-tabs__item[data-tarn-type="howto"] .md-tabs__link',
                                    )
                                    require(
                                        dot.evaluate(
                                            "el => getComputedStyle(el, '::before').content",
                                        )
                                        == '""',
                                        'Missing navigation dot',
                                    )
                                # Exercise keyboard focus and its visible outline.
                                page.locator('.md-content h1').click()
                                page.keyboard.press('Tab')
                                focus = page.evaluate(
                                    '({tag: document.activeElement.tagName, outline: getComputedStyle(document.activeElement).outlineStyle})'
                                )
                                require(
                                    focus['outline'] != 'none',
                                    f'Keyboard focus has no visible outline: {focus}',
                                )
                                # Search is supplied by Zensical; confirm Tarn does not break its trigger.
                                trigger = page.locator('.md-search__button')
                                if not trigger.is_visible():
                                    trigger = page.locator('.md-header__button[for="__search"]')
                                trigger.click()
                                query = page.get_by_role('combobox')
                                query.wait_for(state='visible')
                                query.fill('task')
                                query.press('Escape')
                                query.wait_for(state='hidden')
                                require(not errors, f'JavaScript errors: {errors}')
                                page.screenshot(
                                    path=str(args.artifacts / f'{layout}-{scheme}-{width}.png'),
                                )
                                page.goto(
                                    f'http://127.0.0.1:{server.server_port}/{layout}/site/about/',
                                    wait_until='networkidle',
                                )
                                about = page.locator(
                                    '.md-nav--primary > .md-nav__list > [data-tarn-url="about/"]',
                                )
                                separator = about.evaluate("""el => {
                                  const s = getComputedStyle(el);
                                  return {border: s.borderTopWidth, margin: s.marginTop, padding: s.paddingTop,
                                          previousDisplay: getComputedStyle(el.previousElementSibling).display};
                                }""")
                                lifted = width >= 1220 and layout != 'sidebar'
                                require(
                                    separator['border'] == ('0px' if lifted else '1px'),
                                    f'{layout}/{scheme}/{width}: incorrect About separator: {separator}',
                                )
                                if lifted:
                                    require(
                                        separator['margin'] == separator['padding'] == '0px',
                                        f'Hidden separator left spacing above About: {separator}',
                                    )
                                    require(
                                        separator['previousDisplay'] == 'none',
                                        'Regression fixture must hide preceding section',
                                    )
                                if width < 1220:
                                    page.locator('.md-header__button[for="__drawer"]').click()
                                page.screenshot(
                                    path=str(
                                        args.artifacts / f'{layout}-{scheme}-{width}-about.png',
                                    ),
                                    animations='disabled',
                                )
                                results.append(
                                    {
                                        'layout': layout,
                                        'scheme': scheme,
                                        'width': width,
                                        'background': background,
                                        'focus': focus,
                                        'aboutSeparator': separator,
                                    },
                                )
                                context.close()
                    page = browser.new_page()
                    page.route(
                        '**/*',
                        lambda route: (
                            route.continue_()
                            if route.request.url.startswith('http://127.0.0.1:')
                            else route.abort()
                        ),
                    )
                    for name in ('fallback', 'named', 'fonts', 'custom-css'):
                        page.goto(
                            f'http://127.0.0.1:{server.server_port}/{name}/site/how-to/deep/start/',
                            wait_until='networkidle',
                        )
                        styles = page.locator('body').evaluate("""el => {
                          const s = getComputedStyle(el);
                          return {primary:s.getPropertyValue('--md-primary-fg-color').trim(),
                                  accent:s.getPropertyValue('--md-accent-fg-color').trim(),
                                  text:s.getPropertyValue('--md-text-font').trim(),
                                  code:s.getPropertyValue('--md-code-font').trim()};
                        }""")
                        if name == 'fallback':
                            require(
                                page.locator('.md-main').evaluate(
                                    'el => getComputedStyle(el).backgroundColor',
                                )
                                == 'rgb(234, 229, 223)',
                                'No-palette fallback lost light background',
                            )
                            require(
                                'Atkinson' not in styles['text'],
                                'font=false still forces unloaded Atkinson font',
                            )
                        elif name == 'named':
                            require(
                                styles['primary'] == '#ef5552',
                                f'Named primary was lost: {styles}',
                            )
                            require(
                                styles['accent'] == '#00c753',
                                f'Named accent was lost: {styles}',
                            )
                        elif name == 'fonts':
                            require(
                                styles['text'] == '"Inter"'
                                and styles['code'] == '"JetBrains Mono"',
                                f'Custom fonts were lost: {styles}',
                            )
                        else:
                            require(
                                page.locator('p > code').first.evaluate(
                                    'el => getComputedStyle(el).color',
                                )
                                == 'rgb(100, 20, 90)',
                                'extra_css did not override Tarn',
                            )
                        results.append({'case': name, 'styles': styles})
                    page.close()
                finally:
                    browser.close()
        finally:
            server.shutdown()
            server.server_close()
        (args.artifacts / 'report.json').write_text(
            json.dumps(results, indent=2) + '\n',
            encoding='utf-8',
        )
        print(f'Browser checks passed: {len(results)} cases; artifacts in {args.artifacts}')


if __name__ == '__main__':
    main()
