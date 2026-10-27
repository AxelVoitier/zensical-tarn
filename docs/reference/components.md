# Components

This page pairs rendered components with source that you can copy into a Tarn
site. Tarn supplies the colours, borders and icons. Zensical supplies the Markdown
syntax. The header toggle shows the light and dark treatments.

For a complete site setup, see [Build your first site](../tutorials/first-site.md).
For theme settings and colour variables, see [Configuration](configuration.md)
and [CSS custom properties](css-properties.md).

## Admonitions

An admonition is a labelled block for supporting information. Tarn groups the
twelve standard types into five colour tones. The icons below are Tarn's defaults.

| Type | Tone | Icon |
| --- | --- | --- |
| `note` | Information | `lucide/info` |
| `abstract` | Information | `lucide/list` |
| `info` | Information | `lucide/info` |
| `tip` | Success | `lucide/lightbulb` |
| `success` | Success | `lucide/check` |
| `question` | Warning | `lucide/circle-help` |
| `warning` | Warning | `lucide/triangle-alert` |
| `failure` | Danger | `lucide/x` |
| `danger` | Danger | `lucide/zap` |
| `bug` | Danger | `lucide/bug` |
| `example` | Neutral | `lucide/flask-conical` |
| `quote` | Neutral | `lucide/quote` |

These five rendered blocks show one example of each tone:

!!! note "Theme configuration"
    Tarn's settings belong under `project.extra.tarn` in `zensical.toml`.

!!! tip "Preview both modes"
    Use the header toggle to inspect the page in light and dark mode.

!!! warning "Replacing a feature list"
    A project `features` list replaces the complete theme default list.
    Include every feature that the site needs.

!!! danger "Removing a source page"
    Deleting a Markdown source file removes that page from the next clean build.
    Update links that point to it.

!!! example "Reference section"
    A page at `reference/components/` receives a Reference badge by default.

The source below produces the first block. The type follows `!!!`, an optional
quoted title follows the type, and the body uses four spaces of indentation.

```markdown
!!! note "Theme configuration"
    Tarn's settings belong under `project.extra.tarn` in `zensical.toml`.
```

A collapsible block uses `???` in place of `!!!`. `???+` starts expanded.
Tarn applies the same tones to these blocks. See Zensical's
[admonition syntax](https://zensical.org/docs/authoring/admonitions/) for nesting
and other forms.

## Code

Inline: `project.extra.tarn` contains Tarn's settings in `zensical.toml`.
Keys: ++ctrl+c++. Highlight: ==the selected text==.

The source for those inline treatments is:

```markdown
Inline: `project.extra.tarn` contains Tarn's settings in `zensical.toml`.
Keys: ++ctrl+c++. Highlight: ==the selected text==.
```

A fenced code block can show a filename, line numbers and selected lines.
This example highlights line 3:

```toml title="zensical.toml" linenums="1" hl_lines="3"
[project.theme]
name = "tarn"
logo = "assets/logo.svg"
```

The complete Markdown source is:

````markdown
```toml title="zensical.toml" linenums="1" hl_lines="3"
[project.theme]
name = "tarn"
logo = "assets/logo.svg"
```
````

`toml` selects syntax highlighting, `title` supplies the displayed filename,
`linenums` sets the first line number, and `hl_lines` selects lines to highlight.
The logo path is illustrative and requires a matching file in the site's `docs`
directory. This documentation site enables code copy buttons with
`content.code.copy` in its feature list. Add that flag to your site's
`project.theme.features` to display copy buttons globally.

See Zensical's [code blocks](https://zensical.org/docs/authoring/code-blocks/)
and [formatting](https://zensical.org/docs/authoring/formatting/) references for
syntax and Markdown extension configuration.

## Content tabs

Content tabs group alternative examples. Each tab below contains a complete
palette list for one colour mode. A project palette list replaces Tarn's default
list, so these examples omit the mode toggle.

=== "Light only"

    ```toml
    [[project.theme.palette]]
    scheme = "default"
    primary = "custom"
    accent = "custom"
    ```

=== "Dark only"

    ```toml
    [[project.theme.palette]]
    scheme = "slate"
    primary = "custom"
    accent = "custom"
    ```

The source uses `===` followed by a quoted tab label. Each tab's content uses
four spaces of indentation:

````markdown
=== "Light only"

    ```toml
    [[project.theme.palette]]
    scheme = "default"
    primary = "custom"
    accent = "custom"
    ```

=== "Dark only"

    ```toml
    [[project.theme.palette]]
    scheme = "slate"
    primary = "custom"
    accent = "custom"
    ```
````

Content tabs work without `content.tabs.link`. This documentation site enables
that flag to keep the tutorial's repeated operating-system tabs in sync.
Selecting a tab also selects tabs with the same label in other groups.
Add the flag to your site's `project.theme.features` for that behaviour.
See Zensical's
[content tabs reference](https://zensical.org/docs/authoring/content-tabs/).

## Table

Tarn gives tables a border, a header background and a row hover treatment.
This table lists three real settings under `project.extra.tarn`:

| Setting | Type | Default | Effect |
| --- | --- | --- | --- |
| `enabled` | boolean | `true` | Enables badges and navigation decoration. |
| `badges` | boolean | `true` | Shows page badges when `enabled` is also `true`. |
| `navigation` | boolean | `true` | Decorates navigation when `enabled` is also `true`. |

```markdown
| Setting | Type | Default | Effect |
| --- | --- | --- | --- |
| `enabled` | boolean | `true` | Enables badges and navigation decoration. |
| `badges` | boolean | `true` | Shows page badges when `enabled` is also `true`. |
| `navigation` | boolean | `true` | Decorates navigation when `enabled` is also `true`. |
```

See [Configuration](configuration.md#tarn-settings) for the full settings table.

## Buttons

Buttons are links with CSS classes. The primary style has a filled background.
The secondary style has an outlined border. These examples link to existing pages:

[Build your first site](../tutorials/first-site.md){ .md-button .md-button--primary } [Configuration](configuration.md){ .md-button }

```markdown
[Build your first site](../tutorials/first-site.md){ .md-button .md-button--primary }
[Configuration](configuration.md){ .md-button }
```

The classes follow the link in braces. See Zensical's
[buttons reference](https://zensical.org/docs/authoring/buttons/) for the syntax.

## Diátaxis badges

Tarn generates page badges from the page's section or its `tarn.type` metadata.
These specimens show the four generated UI treatments:

<span class="tarn-dtx tarn-dtx--tutorial">Tutorial</span> <span class="tarn-dtx tarn-dtx--howto">How-to guide</span> <span class="tarn-dtx tarn-dtx--reference">Reference</span> <span class="tarn-dtx tarn-dtx--explanation">Explanation</span>

Authors control the badge through configuration or page metadata. The HTML spans
above demonstrate the appearance and are not the authoring interface. For example,
this front matter selects a Reference badge:

```yaml
---
tarn:
  type: reference
---
```

See [Set or remove a page's badge](../how-to/set-page-type.md) for the task and
[Configuration](configuration.md#page-front-matter) for accepted values and switches.
