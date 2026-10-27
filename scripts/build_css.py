#!/usr/bin/env python3
# Copyright 2026 Axel Voitier
#
# spell-checker:ignore Diátaxis allsurf linenodiv srgb zvars
# These scripts are invoked with Python and report results on stdout.
# ruff: noqa: EXE001, T201
# Keep generated CSS and its literal selectors unchanged.
# ruff: noqa: E501
# Keep the original lambdas, loops and contrast constants in place.
# ruff: noqa: E731, PERF401, PLR2004

"""Regenerate the Tarn stylesheet from the design tokens.

    python scripts/build_css.py
    python scripts/build_css.py --check

Reads design/tokens.json, checks selected text/background token pairs for
WCAG contrast (4.5:1 text, 3:1 borders and marks), and writes
src/zensical_tarn/assets/stylesheets/tarn.css. Exits non-zero, without writing,
if a pair fails.
"""

import argparse
import json
import sys
from collections.abc import Callable  # noqa: TC003 - annotations are evaluated at runtime
from pathlib import Path
from typing import NotRequired, TypedDict, cast


class ColourToken(TypedDict):
    """The colour fields read from a design token."""

    name: str
    value: str | dict[str, str]
    usage: NotRequired[str]


class ColourGroup(TypedDict):
    """Named colour themes and their tokens."""

    themes: list[dict[str, str]]
    tokens: list[ColourToken]


class ShadowToken(TypedDict):
    """Shadow values indexed by theme identifier."""

    value: dict[str, str]


class ShadowGroup(TypedDict):
    """The shadow tokens used by the stylesheet."""

    tokens: list[ShadowToken]


class TokenDocument(TypedDict):
    """The sections consumed from the design token export."""

    color: ColourGroup
    shadow: ShadowGroup


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--check', action='store_true', help='Check committed CSS without writing it')
args = parser.parse_args()

ROOT = Path(__file__).resolve().parent.parent
TOKENS = cast('TokenDocument', json.loads((ROOT / 'design' / 'tokens.json').read_text()))
OUT_CSS = ROOT / 'src' / 'zensical_tarn' / 'assets' / 'stylesheets' / 'tarn.css'

THEMES = [(t['id'], t['name']) for t in TOKENS['color']['themes']]
C = [
    (
        t['name'],
        *[t['value'][tid] if isinstance(t['value'], dict) else t['value'] for tid, _ in THEMES],
        t.get('usage', ''),
    )
    for t in TOKENS['color']['tokens']
]
tokens = TOKENS


def resolve(name: str, ti: int) -> str:
    """Resolve a colour token or alias for one theme."""
    for c in C:
        if c[0] == name:
            v = c[1 + ti]
            if v.startswith('{'):
                return resolve(v[1:-1], ti)
            return v
    raise KeyError(name)


def lum(h: str) -> float:
    """Calculate relative luminance from a hexadecimal colour."""
    h = h.lstrip('#')
    r, g, b = [int(h[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    f: Callable[[float], float] = lambda c: (
        c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    )
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def cr(a: str, b: str) -> float:
    """Calculate the contrast ratio between two hexadecimal colours."""
    la, lb = lum(a), lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


TEXT = 4.5
UI = 3.0
CHECKS: list[tuple[str, str, float]] = []
allsurf = ['surface', 'surface-sunken', 'surface-raised']
tints = [
    'brand-tint',
    'accent-tint',
    'dtx-reference-tint',
    'dtx-explanation-tint',
    'warning-tint',
    'danger-tint',
    'mark',
    'surface-hover',
    'code-hl',
]
for t in ['ink', 'ink-muted']:
    for s in allsurf + tints:
        CHECKS.append((t, s, TEXT))
for s in ['surface', 'surface-sunken']:
    CHECKS.append(('ink-subtle', s, TEXT))
for s in ['surface', 'surface-sunken', 'brand-tint', 'surface-hover']:
    CHECKS.append(('brand', s, TEXT))
for s in ['surface', 'brand-tint']:
    CHECKS.append(('brand-strong', s, TEXT))
CHECKS += [('on-brand', 'brand', TEXT), ('on-brand', 'brand-strong', TEXT)]  # pyright: ignore[reportConstantRedefinition]
for s in ['surface', 'surface-sunken', 'accent-tint']:
    CHECKS.append(('accent', s, TEXT))
for a, b in [
    ('dtx-reference', 'dtx-reference-tint'),
    ('dtx-reference', 'surface'),
    ('dtx-explanation', 'dtx-explanation-tint'),
    ('dtx-explanation', 'surface'),
    ('warning', 'warning-tint'),
    ('warning', 'surface'),
    ('danger', 'danger-tint'),
    ('danger', 'surface'),
]:
    CHECKS.append((a, b, TEXT))
for k in [
    'code-keyword',
    'code-string',
    'code-number',
    'code-function',
    'code-comment',
    'code-ink',
]:
    for s in ['code-bg', 'code-hl']:
        CHECKS.append((k, s, TEXT))
for s in ['surface', 'surface-sunken']:
    CHECKS.append(('logo-tile', s, UI))
CHECKS.append(('code-inline-ink', 'code-inline-bg', TEXT))
CHECKS.append(('ink', 'code-inline-bg', TEXT))
CHECKS.append(('logo-glyph', 'logo-tile', TEXT))
for s in ['surface', 'surface-sunken', 'surface-raised', 'surface-hover']:
    CHECKS.append(('line-strong', s, UI))
    CHECKS.append(('focus-ring', s, UI))

fails = 0
for ti, (tid, _) in enumerate(THEMES):
    worst: list[tuple[float, str, str, float]] = []
    for a, b, need in CHECKS:
        r = cr(resolve(a, ti), resolve(b, ti))
        if r < need:
            fails += 1
            print(f'FAIL {tid}: {a} on {b} = {r:.2f} (need {need})')
        worst.append((r - need, a, b, r))
    worst.sort()
    print(tid, 'tightest:', ', '.join(f'{a}/{b} {r:.2f}' for _, a, b, r in worst[:4]))
# danger vs success lightness (color-blind) in light
print('success vs danger ratio light:', round(cr(resolve('accent', 0), resolve('danger', 0)), 2))
print('FAILS', fails)


# ---------- Zensical extra.css ----------
def zvars(ti: int) -> str:
    """Render the CSS custom properties for one theme."""
    r: Callable[[str], str] = lambda n: resolve(n, ti)
    m = {
        '--md-default-bg-color': r('surface'),
        '--md-default-bg-color--light': r('surface-sunken'),
        '--md-default-fg-color': r('ink'),
        '--md-default-fg-color--light': r('ink-muted'),
        '--md-default-fg-color--lighter': r('ink-subtle'),
        '--md-default-fg-color--lightest': r('line'),
        '--tarn-brand': r('brand'),
        '--tarn-brand-tint': r('brand-tint'),
        '--tarn-brand-strong': r('brand-strong'),
        '--tarn-on-brand': r('on-brand'),
        '--md-typeset-color': r('ink'),
        '--md-typeset-mark-color': r('mark'),
        '--md-typeset-table-color': r('line'),
        '--md-typeset-table-color--light': r('surface-hover'),
        '--md-typeset-kbd-color': r('surface-raised'),
        '--md-typeset-kbd-accent-color': r('surface-raised'),
        '--md-typeset-kbd-border-color': r('line-strong'),
        '--md-code-bg-color': r('code-bg'),
        '--md-code-fg-color': r('code-ink'),
        '--md-code-hl-color': r('brand'),
        '--md-code-hl-color--light': r('code-hl'),
        '--md-code-hl-keyword-color': r('code-keyword'),
        '--md-code-hl-string-color': r('code-string'),
        '--md-code-hl-number-color': r('code-number'),
        '--md-code-hl-constant-color': r('code-number'),
        '--md-code-hl-function-color': r('code-function'),
        '--md-code-hl-name-color': r('code-ink'),
        '--md-code-hl-variable-color': r('code-ink'),
        '--md-code-hl-special-color': r('code-number'),
        '--md-code-hl-operator-color': r('code-operator'),
        '--md-code-hl-punctuation-color': r('code-operator'),
        '--md-code-hl-comment-color': r('code-comment'),
        '--md-code-hl-generic-color': r('code-comment'),
        '--md-footer-bg-color': r('surface-sunken'),
        '--md-footer-bg-color--dark': r('surface-sunken'),
        '--md-footer-fg-color': r('ink'),
        '--md-footer-fg-color--light': r('ink-muted'),
        '--md-footer-fg-color--lighter': r('ink-subtle'),
        '--md-admonition-bg-color': r('surface'),
        '--md-admonition-fg-color': r('ink'),
        '--tarn-line': r('line'),
        '--tarn-line-strong': r('line-strong'),
        '--tarn-raised': r('surface-raised'),
        '--tarn-hover': r('surface-hover'),
        '--tarn-inline-bg': r('code-inline-bg'),
        '--tarn-inline-ink': r('code-inline-ink'),
        '--tarn-info': r('info'),
        '--tarn-info-tint': r('info-tint'),
        '--tarn-success': r('success'),
        '--tarn-success-tint': r('success-tint'),
        '--tarn-warning': r('warning'),
        '--tarn-warning-tint': r('warning-tint'),
        '--tarn-danger': r('danger'),
        '--tarn-danger-tint': r('danger-tint'),
        '--tarn-neutral': r('neutral'),
        '--tarn-neutral-tint': r('neutral-tint'),
        '--tarn-tutorial': r('dtx-tutorial'),
        '--tarn-tutorial-tint': r('dtx-tutorial-tint'),
        '--tarn-howto': r('dtx-howto'),
        '--tarn-howto-tint': r('dtx-howto-tint'),
        '--tarn-reference': r('dtx-reference'),
        '--tarn-reference-tint': r('dtx-reference-tint'),
        '--tarn-explanation': r('dtx-explanation'),
        '--tarn-explanation-tint': r('dtx-explanation-tint'),
        '--tarn-shadow': tokens['shadow']['tokens'][0]['value'][THEMES[ti][0]],
    }
    return '\n'.join(f'  {k}: {val};' for k, val in m.items())


# Templates classify sections once and expose stable type attributes to CSS.
DTX_TYPES = ('tutorial', 'howto', 'reference', 'explanation')
DTX_ITEM = '.md-tabs__item:is(' + ','.join(f'[data-tarn-type="{t}"]' for t in DTX_TYPES) + ')'
TOP = '.md-nav--primary > .md-nav__list > .md-nav__item'
ATTR_ANY = ':is(' + ','.join(f'[data-tarn-type="{t}"]' for t in DTX_TYPES) + ')'
SECONDARY_SEPARATOR = (
    f'{TOP}:not([data-tarn-type="secondary"]) + .md-nav__item[data-tarn-type="secondary"]'
)
SIDE_CSS = '\n'.join(
    [
        '/* Sidebar section colours use the same classification as tabs and badges. */',
        *[f'{TOP}[data-tarn-type="{t}"] {{ --tarn-tab: var(--tarn-{t}); }}' for t in DTX_TYPES],
        f'{TOP}{ATTR_ANY} > .md-nav__link:not(.md-nav__container) > .md-ellipsis::before,',
        f'{TOP}{ATTR_ANY} > .md-nav__container > .md-nav__link:first-child > .md-ellipsis::before {{',
        '  content: ""; display: inline-block; vertical-align: middle; width: 6px; height: 6px;',
        '  margin: -2px .3rem 0 0; border-radius: 50%; background: var(--tarn-tab); }',
        f'{TOP}[data-tarn-type="secondary"] > .md-nav__link, {TOP}[data-tarn-type="secondary"] > .md-nav__container > .md-nav__link {{',
        '  color: var(--md-default-fg-color--lighter); }',
        f'{SECONDARY_SEPARATOR} {{ margin-top: 1rem; padding-top: .6rem; border-top: 1px solid var(--tarn-line); }}',
        "/* Match Zensical's desktop breakpoint: tabbed sidebars show only the active section. */",
        '@media screen and (min-width: 76.25em) {',
        f'  {SECONDARY_SEPARATOR.replace(".md-nav--primary", ".md-nav--primary.md-nav--lifted")} {{ margin-top: 0; padding-top: 0; border-top: 0; }}',
        '}',
    ],
)
tab_rules = '\n'.join(
    f'.md-tabs__item[data-tarn-type="{t}"] {{ --tarn-tab: var(--tarn-{t}); }}' for t in DTX_TYPES
)

EXTRA = f"""/* Tarn theme for Zensical (zensical-tarn) — GENERATED from design/tokens.json
   by scripts/build_css.py. Do not edit by hand. Loaded by the theme's main.html. */

:root {{
{zvars(0)}
}}

/* Light: scheme "default" */
[data-md-color-scheme="default"] {{
{zvars(0)}
}}

/* Dark: scheme "slate" (starlit indigo) */
[data-md-color-scheme="slate"] {{
  --md-hue: 268;
{zvars(1)}
  color-scheme: dark;
}}

/* Preserve named upstream palettes; Tarn supplies the custom palette and no-palette fallback. */
body:not([data-md-color-primary]), [data-md-color-primary="custom"] {{
  --md-primary-fg-color: var(--tarn-brand);
  --md-primary-fg-color--light: var(--tarn-brand-tint);
  --md-primary-fg-color--dark: var(--tarn-brand-strong);
  --md-primary-bg-color: var(--tarn-on-brand);
  --md-typeset-a-color: var(--tarn-brand);
}}
body:not([data-md-color-accent]), [data-md-color-accent="custom"] {{
  --md-accent-fg-color: var(--tarn-brand-strong);
  --md-accent-fg-color--transparent: var(--tarn-brand-tint);
  --md-accent-bg-color: var(--tarn-on-brand);
}}

/* ---- Structure: one ground, hairline-separated ---- */
.md-header, .md-header--shadow {{ background-color: var(--md-default-bg-color); color: var(--md-default-fg-color);
  box-shadow: inset 0 -1px 0 var(--tarn-line); }}
.md-main, .md-container {{ background-color: var(--md-default-bg-color); }}
.md-footer-meta {{ background-color: var(--md-footer-bg-color); border-top: 1px solid var(--tarn-line); }}
.md-typeset {{ font-size: .8rem; line-height: 1.7; }}
.md-typeset h1 {{ font-size: 1.7rem; line-height: 1.18; font-weight: 700; letter-spacing: -0.01em; color: var(--md-default-fg-color); margin: .3rem 0 1.2rem; }}
.md-typeset h2 {{ font-size: 1.25rem; line-height: 1.28; font-weight: 600; letter-spacing: 0; margin-top: 1.6rem; }}
.md-typeset h3 {{ font-size: 1rem; line-height: 1.4; font-weight: 600; }}
.md-typeset h4 {{ font-size: .85rem; font-weight: 700; }}
.md-content__inner > p, .md-content__inner > ul, .md-content__inner > ol {{ max-width: 42rem; }}
.md-typeset :is(p, li, td, dd, .admonition) > a:not(.md-button) {{ text-decoration: underline; text-decoration-thickness: 1px; text-underline-offset: .18em;
  text-decoration-color: color-mix(in srgb, currentColor 35%, transparent); }}
.md-typeset :is(p, li, td, dd, .admonition) > a:not(.md-button):hover {{ color: var(--md-accent-fg-color); text-decoration-color: currentColor; }}
.md-sidebar--primary .md-nav__link--active {{ color: var(--md-primary-fg-color); font-weight: 600; }}
.md-sidebar--primary .md-nav__item .md-nav__link--active {{ background: var(--md-primary-fg-color--light); border-radius: 6px; }}
:focus-visible {{ outline: 2px solid var(--md-primary-fg-color); outline-offset: 2px; }}

/* ---- Navigation tabs: type attributes come from partials/tarn.html ---- */
.md-tabs {{ background-color: var(--md-default-bg-color); color: var(--md-default-fg-color--light);
  box-shadow: inset 0 -1px 0 var(--tarn-line); }}
.md-tabs__list {{ display: flex; }}
.md-tabs__link {{ opacity: 1; color: var(--md-default-fg-color--light); font-weight: 500; }}
.md-tabs__link:hover {{ color: var(--md-default-fg-color); }}
.md-tabs__item--active {{ border-bottom: 2px solid var(--tarn-tab, var(--md-default-fg-color)); font-weight: 600; }}
.md-tabs__item--active .md-tabs__link {{ color: var(--md-default-fg-color); }}
{tab_rules}
{DTX_ITEM} .md-tabs__link::before {{ content: ""; flex: none; align-self: center; width: 6px; height: 6px;
  margin-right: .4rem; border-radius: 50%; background: var(--tarn-tab); }}
.md-tabs__item[data-tarn-type="secondary"] .md-tabs__link {{ color: var(--md-default-fg-color--lighter); font-weight: 400; }}
.md-tabs__item[data-tarn-type="secondary"].md-tabs__item--active .md-tabs__link {{ color: var(--md-default-fg-color); font-weight: 500; }}
.md-tabs__item:not([data-tarn-type="secondary"]) + .md-tabs__item[data-tarn-type="secondary"] {{ margin-left: auto; }}


{SIDE_CSS}
/* ---- Code ---- */
.md-typeset pre > code, .md-typeset .highlight {{ border-radius: 6px; }}
.md-typeset .highlight {{ box-shadow: inset 0 0 0 1px var(--tarn-line); }}
.md-typeset .highlight .filename {{ background: var(--md-code-bg-color); font-weight: 500; color: var(--md-default-fg-color--light);
  border-bottom: 1px solid var(--tarn-line); font-size: .65rem; }}
.md-typeset .highlight .c, .md-typeset .highlight .c1, .md-typeset .highlight .cm {{ font-style: italic; }}
.md-typeset .linenos, .md-typeset .linenodiv a, .md-typeset .highlight .linenos a {{ color: var(--md-default-fg-color--lighter); text-decoration: none; }}
/* Inline code: plum in light mode, lavender-silver in dark, on a distinct background chip */
.md-typeset :not(pre, .highlight) > code {{ color: var(--tarn-inline-ink); background-color: var(--tarn-inline-bg);
  border-radius: 4px; padding: .12em .38em; font-weight: 500; }}
.md-typeset a > code, .md-typeset a:hover > code {{ color: inherit; }}
.md-typeset h1 code, .md-typeset h2 code, .md-typeset h3 code {{ font-weight: inherit; }}

/* ---- Buttons ---- */
.md-typeset .md-button {{ border-radius: 6px; border: 1px solid var(--tarn-line-strong); color: var(--md-default-fg-color);
  background: transparent; font-weight: 600; padding: .5em 1.1em; }}
.md-typeset .md-button--primary {{ background: var(--md-primary-fg-color); border-color: var(--md-primary-fg-color); color: var(--md-primary-bg-color); }}
.md-typeset .md-button:is(:hover, :focus) {{ background: var(--md-primary-fg-color--dark); border-color: var(--md-primary-fg-color--dark); color: var(--md-primary-bg-color); }}

/* ---- Admonitions: five tones for the twelve types ---- */
.md-typeset :is(.admonition, details) {{ --tarn-t: var(--tarn-info); --tarn-t-tint: var(--tarn-info-tint);
  border: 1px solid color-mix(in srgb, var(--tarn-t) 30%, transparent); border-radius: 6px; box-shadow: none;
  font-size: .75rem; color: var(--md-default-fg-color--light); }}
.md-typeset :is(.admonition, details):is(.tip, .hint, .important, .success, .check, .done) {{ --tarn-t: var(--tarn-success); --tarn-t-tint: var(--tarn-success-tint); }}
.md-typeset :is(.admonition, details):is(.warning, .caution, .attention, .question, .help, .faq) {{ --tarn-t: var(--tarn-warning); --tarn-t-tint: var(--tarn-warning-tint); }}
.md-typeset :is(.admonition, details):is(.danger, .error, .failure, .fail, .missing, .bug) {{ --tarn-t: var(--tarn-danger); --tarn-t-tint: var(--tarn-danger-tint); }}
.md-typeset :is(.admonition, details):is(.example, .quote, .cite) {{ --tarn-t: var(--tarn-neutral); --tarn-t-tint: var(--tarn-neutral-tint); border-color: var(--tarn-line); }}
.md-typeset :is(.admonition, details)[class] {{ background-color: var(--tarn-t-tint); }}
.md-typeset :is(.admonition-title, summary) {{ background: transparent !important; font-weight: 600; color: var(--tarn-t); }}
.md-typeset :is(.admonition-title, summary)::before {{ background-color: var(--tarn-t) !important; }}
.md-typeset details > summary::after {{ color: var(--tarn-t) !important; }}

/* ---- Tables ---- */
.md-typeset table:not([class]) {{ border: 1px solid var(--tarn-line); border-radius: 6px; box-shadow: none; font-size: .75rem; }}
.md-typeset table:not([class]) th {{ background: var(--md-default-bg-color--light); font-weight: 600; }}
.md-typeset table:not([class]) tr:hover {{ background: var(--tarn-hover); box-shadow: none; }}

/* ---- Diátaxis badge (rendered by overrides/main.html) ---- */
.tarn-dtx {{ display: inline-flex; align-items: center; gap: .35em; font-size: .575rem; font-weight: 700; letter-spacing: .06em;
  text-transform: uppercase; padding: .2em .6em; border-radius: 4px; color: var(--c); background: var(--t); }}
.tarn-dtx::before {{ content: ""; width: .5em; height: .5em; border-radius: 50%; background: currentColor; }}
.tarn-dtx--tutorial {{ --c: var(--tarn-tutorial); --t: var(--tarn-tutorial-tint); }}
.tarn-dtx--howto {{ --c: var(--tarn-howto); --t: var(--tarn-howto-tint); }}
.tarn-dtx--reference {{ --c: var(--tarn-reference); --t: var(--tarn-reference-tint); }}
.tarn-dtx--explanation {{ --c: var(--tarn-explanation); --t: var(--tarn-explanation-tint); }}
"""
if fails:
    sys.exit(f'{fails} contrast failure(s); stylesheet not written.')
if args.check:
    if not OUT_CSS.is_file() or OUT_CSS.read_text(encoding='utf-8') != EXTRA:
        sys.exit('Generated CSS is stale or missing; run python scripts/build_css.py')
    print('Generated CSS is up to date')
else:
    OUT_CSS.write_text(EXTRA, encoding='utf-8')
    print(f'wrote {OUT_CSS}')
