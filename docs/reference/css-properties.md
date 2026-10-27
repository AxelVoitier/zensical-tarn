# CSS custom properties

Tarn exposes the `--tarn-*` properties below for project stylesheets. A CSS
custom property is a named value read through `var()`. Tarn also sets Zensical's
`--md-*` properties for page colours, code, tables, keyboard keys and the footer.
The tables describe where Tarn's generated stylesheet uses each Tarn property.

## Scheme and palette scope

Tarn defines light values on `:root` and `[data-md-color-scheme="default"]`.
It defines dark values on `[data-md-color-scheme="slate"]`. The root values
provide the light fallback when no scheme is selected.

Project `extra_css` loads after Tarn's stylesheet. A rule with the matching
scheme selector can replace a value for that scheme. A `:root` override alone
does not replace the value declared on a descendant with a scheme attribute,
such as the page's `body`. See [Adjust a colour](../how-to/adjust-colours.md)
for an override and stylesheet configuration.

Tarn maps its brand properties to Zensical's primary colours when
`primary = "custom"`, or when the body has no primary palette attribute.
The accent mapping applies independently when `accent = "custom"`, or when
the body has no accent palette attribute. Explicitly named Zensical palettes
retain their primary or accent colours. The other Tarn properties below still
apply, including inline code, admonitions and Diátaxis decoration.
See [Configuration](configuration.md#palettes) for palette configuration.

## Brand colours

These properties supply the custom primary and accent mappings described above.
Text and background colours form pairs: `--tarn-on-brand` supplies text on the
solid brand colours. The tint supplies a background fill rather than text colour.

| Property | Use |
| --- | --- |
| `--tarn-brand` | Primary colour and prose link colour in the custom primary palette |
| `--tarn-brand-strong` | Dark primary variant and custom accent colour, including link hover |
| `--tarn-brand-tint` | Light primary variant, including the active sidebar fill, and transparent accent variant |
| `--tarn-on-brand` | Text on primary and accent backgrounds, including primary buttons |

## Borders, surfaces and inline code

Inline code outside links uses `--tarn-inline-ink` on `--tarn-inline-bg`.
Inline code inside links inherits the link's text colour.

| Property | Use |
| --- | --- |
| `--tarn-line` | Fine borders and separators in the header, tabs, footer, code blocks, tables and sidebar |
| `--tarn-line-strong` | Button borders |
| `--tarn-hover` | Table row background on hover |
| `--tarn-inline-bg` | Inline code background |
| `--tarn-inline-ink` | Inline code text outside links |
| `--tarn-raised` | Exposed raised-surface value, currently unused by Tarn's CSS rules |
| `--tarn-shadow` | Exposed shadow value, currently unused by Tarn's CSS rules |

Changing `--tarn-raised` or `--tarn-shadow` alone has no visible effect in
Tarn. A project stylesheet can consume either property. Tarn assigns the
keyboard-key background separately through `--md-typeset-kbd-color` and
`--md-typeset-kbd-accent-color`, even though these share the raised-surface
design token.

## Admonition tones

Each tone has a colour and a background tint. The colour supplies the title,
icon and disclosure arrow, and contributes to the border. The tint supplies
the box background. Body text uses `--md-default-fg-color--light`.

| Property | Use |
| --- | --- |
| `--tarn-info` | Default tone colour, including note, abstract and info |
| `--tarn-info-tint` | Default tone background |
| `--tarn-success` | Tone colour for tip, hint, important, success, check and done |
| `--tarn-success-tint` | Success tone background |
| `--tarn-warning` | Tone colour for warning, caution, attention, question, help and faq |
| `--tarn-warning-tint` | Warning tone background |
| `--tarn-danger` | Tone colour for danger, error, failure, fail, missing and bug |
| `--tarn-danger-tint` | Danger tone background |
| `--tarn-neutral` | Tone colour for example, quote and cite |
| `--tarn-neutral-tint` | Neutral tone background |

Neutral admonitions use `--tarn-line` for their border. The component properties
`--tarn-t` and `--tarn-t-tint` select the current tone inside admonitions and
collapsible details. They are internal aliases, rather than additional
scheme-level design tokens.

## Diátaxis colours

Each Diátaxis type has a text colour and a background tint for its page badge.
The text colour also supplies navigation dots and the active tab underline
for sections of that type. The tint applies to the badge background.

| Property | Use |
| --- | --- |
| `--tarn-tutorial` | Tutorial badge text and navigation decoration |
| `--tarn-tutorial-tint` | Tutorial badge background |
| `--tarn-howto` | How-to guide badge text and navigation decoration |
| `--tarn-howto-tint` | How-to guide badge background |
| `--tarn-reference` | Reference badge text and navigation decoration |
| `--tarn-reference-tint` | Reference badge background |
| `--tarn-explanation` | Explanation badge text and navigation decoration |
| `--tarn-explanation-tint` | Explanation badge background |

## Source values and contrast checks

The values come from the repository's
[design tokens](https://github.com/AxelVoitier/zensical-tarn/blob/main/design/tokens.json).
The [CSS generator](https://github.com/AxelVoitier/zensical-tarn/blob/main/scripts/build_css.py)
resolves token aliases and writes the
[generated stylesheet](https://github.com/AxelVoitier/zensical-tarn/blob/main/src/zensical_tarn/assets/stylesheets/tarn.css).
Properties generated from the same source token receive separate literal
values in the CSS. Overriding one does not change the other values generated
from that token. The primary and accent mappings instead use `var()` to read
the Tarn brand properties.

The generator checks selected text/background pairs in both default schemes.
These checks do not cover project overrides. See
[Why these colours](../explanation/colour.md) for the palette's roles and
contrast checks.
