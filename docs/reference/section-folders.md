# Section folders

Tarn classifies page URLs to choose automatic badges and navigation decoration.
The same default aliases apply to page badges, navigation tabs and the sidebar.
Navigation titles do not affect classification.

## Default aliases

| Classification | First URL segment | Dot | Automatic badge |
| --- | --- | --- | --- |
| `tutorial` | `tutorials`, `tutorial` | green | Tutorial |
| `howto` | `how-to`, `how-tos`, `howto`, `howtos`, `how-to-guides`, `guides` | blue | How-to guide |
| `reference` | `reference`, `references`, `api` | slate | Reference |
| `explanation` | `explanation`, `explanations`, `concepts` | ochre | Explanation |
| `primary` | Empty segment (`""`), `index` | none | none |
| `secondary` | `about`, `contributing`, `changelog`, and any other segment | none | none |

`primary` gives ordinary navigation without a dot. `secondary` gives quieter
navigation separated from primary sections. Classification preserves the
navigation order defined by the project.

## Page URL matching

Matching uses the first segment of a site-relative URL and removes a trailing
`.html` from that segment. For example, `reference/types/` and `reference.html`
both match `reference`. A deployment prefix such as `/project/` in `site_url`
is not part of that segment. Both directory URLs and
`use_directory_urls = false` are supported.

The homepage uses the empty segment for directory URLs or `index` for
`index.html`. Its URL determines its classification regardless of its navigation
position. The `index` alias also applies to URLs such as `index/topic/`.
A page at `reference/index.html` matches `reference`, because `index` is not
its first segment.

## Navigation classification

A directly linked page uses its own URL. A navigation section uses its selected
index when `navigation.indexes` is enabled, or its first child otherwise.
If that child is another section, Tarn follows the first linked descendant.
Tab navigation repeats index selection within nested sections.
The resulting page URL determines the section's classification, even when its
navigation title or other descendants suggest a different type.

External navigation links always use `secondary`. Tarn does not classify them
by their target URL's folders.

## Overrides and switches

[`project.extra.tarn.sections`](configuration.md#section-classifications)
overrides individual aliases. Unspecified aliases retain their defaults.
An unknown segment defaults to `secondary`. An invalid classification in an
explicit mapping falls back to `primary`.
See [Name your sections](../how-to/name-sections.md) for mapping examples.

An explicit [`tarn.type`](configuration.md#page-front-matter) overrides only
that page's badge. A page in a secondary section can therefore display a badge.
See [Set or remove a page's badge](../how-to/set-page-type.md).

Under `project.extra.tarn`, `enabled = false` disables both badges and navigation
decoration. `badges = false` hides only badges, and `navigation = false` hides
only navigation decoration. Page metadata and section mappings cannot override
a disabled switch.
