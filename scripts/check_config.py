#!/usr/bin/env python3
# Copyright 2026 Axel Voitier
# Invoke with Python; report the check result on stdout.
# ruff: noqa: EXE001, T201
# Keep fixture Markdown, configuration and expected strings unchanged.
# ruff: noqa: E501
# Retain the existing local names and positional validation helper.
# ruff: noqa: A001, FBT001

"""Exercise Tarn settings through real strict builds with an installed wheel."""

import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast

NAV = """[
 {"How-to guides" = [{"Nested" = ["how-to/deep/start.md"]}]},
 {"Reference" = "reference.md"},
 {"Tutorials" = ["tutorials/index.md"]},
 {"Explanation" = ["explanation/index.md"]},
 {"About" = ["about/index.md"]},
 {"Other" = ["other/index.md"]},
 {"Home" = "index.md"},
 {"External" = "https://example.org/reference/"},
 {"Learning" = ["learn/index.md"]}
]"""


class Markup(HTMLParser):
    def __init__(self, path: Path) -> None:
        """Initialise the parser and its collected page data."""
        super().__init__()
        self.items: list[dict[str, str | None]] = []
        self.badges: list[str] = []
        self.links: set[str] = set()
        self.feed(path.read_text(encoding='utf-8'))

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]] | dict[str, str | None],
    ) -> None:
        """Collect the relevant attributes from an opening HTML tag."""
        attrs = dict(attrs)
        if tag == 'li' and 'data-tarn-url' in attrs:
            self.items.append(attrs)
        if tag == 'span' and 'tarn-dtx' in (attrs.get('class') or '').split():
            self.badges.append(cast('str', attrs['class']))
        if tag == 'a' and attrs.get('href'):
            self.links.add(cast('str', attrs['href']))


def require(condition: bool, message: str) -> None:
    """Raise a validation error when a required condition fails."""
    if not condition:
        raise ValueError(message)


def make_site(
    root: Path,
    name: str,
    *,
    project: str = '',
    theme: str = '',
    settings: str = '',
    override: bool = False,
    css: str | None = None,
) -> Path:
    """Build a fixture with nested navigation, direct pages, badges and components."""
    destination = root / name
    destination.mkdir()
    pages = {
        'index.md': '# Home\n\nWelcome.',
        # A generic type belongs to the consuming project, and must be ignored.
        'how-to/deep/start.md': '---\ntype: reference\n---\n# Run a task\n\nText with `inline_code` and a [link](../../reference.md).\n\n!!! note\n    An example note.\n\n```python\nprint(\'hello\')\n```\n\n=== "First"\n\n    First tab.\n\n=== "Second"\n\n    Second tab.\n\n| A | B |\n| - | - |\n| One | Two |\n',
        'reference.md': '# Reference\n\nDirect top-level page.',
        'tutorials/index.md': '---\ntarn:\n  type: none\n---\n# Tutorials\n\nNo badge on this overview.',
        'explanation/index.md': '# Explanation',
        'other/index.md': '# Other',
        'about/index.md': '---\ntarn:\n  type: explanation\n---\n# About\n\nExplicit badge; secondary navigation.',
        'learn/index.md': '# Learning',
    }
    for filename, content in pages.items():
        path = destination / 'docs' / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content + '\n', encoding='utf-8')
    if css is not None:
        (destination / 'docs/extra.css').write_text(css, encoding='utf-8')
    if override:
        (destination / 'overrides').mkdir()
        (destination / 'overrides/main.html').write_text(
            '{% extends "tarn.html" %}\n{% block extrahead %}{{ super() }}<meta name="local-override" content="works">{% endblock %}\n',
            encoding='utf-8',
        )
        theme += '\ncustom_dir = "overrides"\n'
    config = (
        '[project]\nsite_name = "Tarn check"\nsite_url = "https://example.org/project/"\n'
        f'nav = {NAV}\n{project}\n[project.theme]\nname = "tarn"\n{theme}\n'
        '[project.plugins.exclude]\nglob = ["__init__.py", "__pycache__/*", "mkdocs_theme.yml"]\n'
        + settings
    )
    (destination / 'zensical.toml').write_text(config, encoding='utf-8')
    subprocess.run(
        [sys.executable, '-m', 'zensical', 'build', '--strict', '--clean'],
        cwd=destination,
        check=True,
    )
    return destination


def page_path(project: Path, url: str, *, flat: bool = False) -> Path:
    """Locate a generated page for the selected URL layout."""
    return project / 'site' / (url + '.html' if flat else url + '/index.html')


def check_navigation(
    markup: Markup,
    *,
    flat: bool = False,
    custom: bool = False,
    decorated: bool = True,
    tabs: bool = True,
) -> None:
    # Check both tabs and top-level sidebar items. Home is deliberately not first.
    """Check the expected section types in tabs and sidebar items."""
    suffix = '/index.html' if flat else '/'
    expected = {
        'how-to/deep/start.html' if flat else 'how-to/deep/start/': 'howto',
        'reference.html' if flat else 'reference/': 'reference',
        'tutorials' + suffix: 'tutorial',
        'explanation' + suffix: 'explanation',
        'other' + suffix: 'primary' if custom else 'secondary',
        'about' + suffix: 'secondary',
        'index.html' if flat else '': 'primary',
        'https://example.org/reference/': 'secondary',
        'learn' + suffix: 'tutorial' if custom else 'secondary',
    }
    for url, type in expected.items():
        found = [item for item in markup.items if item['data-tarn-url'] == url]
        require(
            len(found) == (2 if tabs else 1),
            f'{url!r}: missing or duplicate tab/sidebar attributes: {found}',
        )
        for item in found:
            require(
                item.get('data-tarn-type') == (type if decorated else None),
                f'{url!r}: expected {type if decorated else None}, got {item}',
            )


def main() -> None:
    """Build fixture sites and check the supported theme settings."""
    with TemporaryDirectory(prefix='tarn-config-') as directory:
        root = Path(directory)
        default = make_site(root, 'default')
        markup = Markup(page_path(default, 'how-to/deep/start'))
        check_navigation(markup)
        require(
            markup.badges == ['tarn-dtx tarn-dtx--howto'],
            'Generic type must not replace folder badge',
        )
        require(
            not Markup(page_path(default, 'tutorials')).badges,
            'tarn.type=none must suppress badge',
        )
        require(
            Markup(page_path(default, 'about')).badges == ['tarn-dtx tarn-dtx--explanation'],
            'Explicit badge missing',
        )
        require(
            Markup(page_path(default, 'reference')).badges == ['tarn-dtx tarn-dtx--reference'],
            'Direct page badge missing',
        )
        credit_url = 'https://axelvoitier.github.io/zensical-tarn/'
        require(
            credit_url in markup.links and 'https://zensical.org/' in markup.links,
            'Default footer credits missing',
        )
        for name, settings, zensical_credit in (
            ('tarn-credit-hidden', '[project.extra.tarn]\ncredit = false\n', True),
            ('all-credits-hidden', '[project.extra]\ngenerator = false\n', False),
        ):
            project = make_site(
                root,
                name,
                project='copyright = "Copyright 2026 Example"',
                settings=settings,
            )
            path = page_path(project, 'how-to/deep/start')
            links = Markup(path).links
            require(credit_url not in links, 'Tarn credit switch was ignored')
            require(
                ('https://zensical.org/' in links) == zensical_credit,
                'Generator attribution switch was ignored',
            )
            require(
                'Copyright 2026 Example' in path.read_text(encoding='utf-8'),
                'Project copyright was lost',
            )
        custom_credit_url = 'https://example.org/tarn/?a=1&b=2'
        project = make_site(
            root,
            'credit-url',
            settings=f'[project.extra.tarn]\ncredit_url = "{custom_credit_url}"\n',
        )
        require(
            custom_credit_url in Markup(page_path(project, 'how-to/deep/start')).links,
            'Custom footer URL did not survive HTML escaping',
        )

        custom = make_site(
            root,
            'custom',
            settings="""
[project.extra.tarn.sections]
learn = "tutorial"
other = "primary"
[project.extra.tarn.labels]
howto = "Procédure <test>"
""",
        )
        path = page_path(custom, 'how-to/deep/start')
        check_navigation(Markup(path), custom=True)
        require(
            'Procédure &lt;test&gt;' in path.read_text(encoding='utf-8'),
            'Translated labels must be escaped',
        )

        ordinary = make_site(
            root,
            'primary-override',
            settings='[project.extra.tarn.sections]\nhow-to = "primary"\n',
        )
        markup = Markup(page_path(ordinary, 'how-to/deep/start'))
        require(not markup.badges, 'Primary section override retained an automatic badge')
        require(
            all(
                item.get('data-tarn-type') == 'primary'
                for item in markup.items
                if item['data-tarn-url'] == 'how-to/deep/start/'
            ),
            'Default section alias was not overridden',
        )

        for setting, badges, navigation in (
            ('enabled', False, False),
            ('badges', False, True),
            ('navigation', True, False),
        ):
            project = make_site(
                root,
                setting,
                settings=f'\n[project.extra.tarn]\n{setting} = false\n',
            )
            markup = Markup(page_path(project, 'how-to/deep/start'))
            require(bool(markup.badges) == badges, f'{setting}=false badge switch failed')
            check_navigation(markup, decorated=navigation)

        sidebar = make_site(
            root,
            'sidebar-flat',
            project='use_directory_urls = false',
            theme='features = ["navigation.sections", "navigation.indexes"]',
        )
        markup = Markup(page_path(sidebar, 'how-to/deep/start', flat=True))
        check_navigation(markup, flat=True, tabs=False)
        require(markup.badges == ['tarn-dtx tarn-dtx--howto'], 'Flat URLs lost their badge')
        require(
            Markup(page_path(sidebar, 'reference', flat=True)).badges
            == ['tarn-dtx tarn-dtx--reference'],
            'Flat direct page lost badge',
        )
        empty_features = make_site(root, 'empty-features', theme='features = []')
        check_navigation(Markup(page_path(empty_features, 'how-to/deep/start')), tabs=False)
        # Deliberately no palette, and font loading disabled: light fallbacks must exist.
        no_fonts = make_site(root, 'no-fonts', theme='font = false\npalette = []')
        require(
            'fonts.googleapis.com' not in page_path(no_fonts, 'how-to/deep/start').read_text(),
            'Disabled font loading still contacts Google',
        )
        fonts = make_site(
            root,
            'custom-fonts',
            theme='font = {text = "Inter", code = "JetBrains Mono"}',
        )
        html = page_path(fonts, 'how-to/deep/start').read_text()
        require(
            '--md-text-font:"Inter"' in html and '--md-code-font:"JetBrains Mono"' in html,
            'Custom fonts ignored',
        )
        for name, palette in (
            ('light', '[{scheme = "default", primary = "custom", accent = "custom"}]'),
            ('dark', '[{scheme = "slate", primary = "custom", accent = "custom"}]'),
            ('named', '[{scheme = "default", primary = "red", accent = "green"}]'),
        ):
            make_site(root, name, theme=f'palette = {palette}')
        override = make_site(root, 'override', override=True)
        html = page_path(override, 'how-to/deep/start').read_text()
        require(
            'name="local-override"' in html
            and 'tarn-dtx--howto' in html
            and 'assets/stylesheets/tarn.css' in html,
            'Local template extension lost Tarn styles or badge',
        )
        print('Configuration checks passed', flush=True)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        sys.exit(str(error))
