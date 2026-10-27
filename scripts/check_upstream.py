#!/usr/bin/env python3
# Copyright 2026 Axel Voitier
#
# spell-checker:ignore keepends tofile
# Invoke with Python; report template comparisons on stdout.
# ruff: noqa: EXE001, T201
# Keep validation messages in the existing raise expressions.
# ruff: noqa: EM102, TRY003
# Delay the engine import until the installed-theme check runs.
# ruff: noqa: PLC0415

"""Compare Tarn's installed copied partials with installed Zensical."""

import difflib
import re
import sys
from importlib import metadata
from pathlib import Path


def without_header(source: str) -> str:
    """Ignore only the leading provenance/generated-file comment."""
    return re.sub(r'\A\{#-.*?-#\}\n', '', source, count=1, flags=re.DOTALL)


def upstream_form(name: str, source: str) -> str:
    """Remove exactly the additions maintained by Tarn; fail if they change."""
    changes = {
        'copyright.html': [
            ('{% import "partials/tarn.html" as tarn with context %}\n', 1),
            ('\n    {{ tarn.credit() }}', 1),
        ],
        'tabs-item.html': [
            ('{% import "partials/tarn.html" as tarn with context %}\n', 1),
            (' {{ tarn.navigation_attributes(first) }}', 1),
            (' {{ tarn.navigation_attributes(nav_item) }}', 1),
        ],
        'nav-item.html': [
            ('{% import "partials/tarn.html" as tarn with context %}\n', 1),
            ('    {% set tarn_first = index or nav_item.children | first %}\n', 1),
            ('{% if level == 1 %} {{ tarn.navigation_attributes(tarn_first) }}{% endif %}', 1),
            ('{% if level == 1 %} {{ tarn.navigation_attributes(nav_item) }}{% endif %}', 2),
        ],
    }
    source = without_header(source)
    for old, count in changes[name]:
        if source.count(old) != count:
            raise ValueError(f'{name}: expected {count} Tarn addition(s): {old!r}')
        source = source.replace(old, '', count)
    return source


def check(tarn: Path, zensical: Path) -> None:
    """Compare the copied partials after removing Tarn additions."""
    for name in ('nav-item.html', 'tabs-item.html', 'copyright.html'):
        actual = upstream_form(name, (tarn / 'partials' / name).read_text(encoding='utf-8'))
        expected = without_header((zensical / 'partials' / name).read_text(encoding='utf-8'))
        if actual != expected:
            difference = ''.join(
                difflib.unified_diff(
                    expected.splitlines(keepends=True),
                    actual.splitlines(keepends=True),
                    fromfile=f'zensical/{name}',
                    tofile=f'tarn/{name}',
                ),
            )
            raise ValueError(f'Upstream template drift; review the override:\n{difference}')
        print(f'Upstream template matches: {name}')


def main() -> None:
    """Compare installed Tarn partials with the installed engine."""
    import zensical

    (entry,) = metadata.entry_points(group='mkdocs.themes', name='tarn')
    tarn = Path(entry.load().__file__).resolve().parent
    check(tarn, Path(zensical.__file__).resolve().parent / 'templates')
    print(f'Checked installed Tarn against Zensical {metadata.version("zensical")}')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError) as error:
        sys.exit(str(error))
