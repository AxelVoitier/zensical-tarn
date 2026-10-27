# Configuration

Tarn's configuration controls page badges, navigation decoration, fonts and colours.
It styles the site's existing navigation and does not create a section layout.
The theme selection belongs in `zensical.toml`:

```toml
[project.theme]
name = "tarn"
```

Tarn requires Python 3.11 or newer and pins Zensical to version 0.0.73.
Its navigation template overrides are checked against that release.

## Tarn settings

Tarn's own settings live under `project.extra.tarn`. Each setting is optional.
An omitted setting retains its default. Project values in `sections` and `labels`
replace only the matching entries, so other defaults remain in effect.

| Setting | Type | Default | Effect |
| --- | --- | --- | --- |
| `enabled` | boolean | `true` | Enables Diátaxis badges and navigation decoration. `false` disables both. |
| `badges` | boolean | `true` | Enables page badges when `enabled` is also `true`. |
| `navigation` | boolean | `true` | Enables section dots and secondary-section styling when `enabled` is also `true`. |
| `sections` | table of strings | [Section folders](section-folders.md) | Overrides individual section classifications. Unspecified defaults remain in effect. |
| `labels` | table of strings | English labels below | Overrides individual badge labels. Plain text is escaped as HTML. |
| `credit` | boolean | `true` | Shows the linked Tarn theme credit beside Zensical's footer attribution. Independent of the Diátaxis switches. |
| `credit_url` | string | `https://axelvoitier.github.io/zensical-tarn/` | Destination of the Tarn footer link. |

This example hides page badges, changes three section classifications and defines
two translated badge labels:

```toml
[project.extra.tarn]
badges = false

[project.extra.tarn.sections]
getting-started = "tutorial"
release-notes = "secondary"
examples = "primary"

[project.extra.tarn.labels]
tutorial = "Tutoriel"
howto = "Procédure"
```

For `mkdocs.yml` configuration read by Zensical, use the equivalent structure
under `extra.tarn`. MkDocs itself has not been verified.

### Decoration and credit switches

`enabled = false` hides badges and navigation decoration. `badges = false`
hides only badges, while `navigation = false` hides only navigation decoration.
Neither page metadata nor a section mapping can override a disabled switch.
These switches leave Tarn's stylesheet and other theme styling in place.

The default footer reads “Made with Zensical and the Tarn theme”. Setting
`project.extra.generator = false` hides both credits. `credit = false` under
`project.extra.tarn` hides only Tarn's credit. Project copyright text is retained.
`credit_url` changes Tarn's link destination. An empty value uses the default URL.

### Section classifications

Each key in `sections` is the first segment of a site-relative URL, without
slashes. A direct page such as `reference.html` uses `reference` as its key.
Values are `tutorial`, `howto`, `reference`, `explanation`, `primary`, or
`secondary`. `primary` gives ordinary navigation without a dot. `secondary`
gives quieter navigation separated from primary sections. Neither gives an
automatic badge.

An unknown URL segment defaults to `secondary`. An invalid value in an explicit
`sections` mapping falls back to `primary`, even when the key matches a built-in
alias. The homepage defaults to `primary` regardless of its navigation position.
External links are secondary and are not classified by their target folder. Nested navigation uses the first
linked page, or the section index when Zensical selects one. Explicit page
badges do not change section classification. For the complete default aliases, see
[Section folders](section-folders.md).

Keep secondary entries together at the end of `nav` to place them at the right
of the tab bar, or below a separator in the sidebar. Tarn preserves the order
of the project's navigation. See [Name your sections](../how-to/name-sections.md)
for a mapping task.

### Badge labels

| Key | Default label |
| --- | --- |
| `tutorial` | Tutorial |
| `howto` | How-to guide |
| `reference` | Reference |
| `explanation` | Explanation |

Label overrides affect badges. Navigation titles remain those in the project's
`nav` configuration.

## Page front matter

Page metadata in the opening YAML block can override the badge classification:

```yaml
---
tarn:
  type: howto
---
```

`tarn.type` overrides the automatic badge on that page. Values are `tutorial`,
`howto`, `reference`, and `explanation`. Set `none` to suppress the badge.
Other values produce no badge. If `tarn.type` is absent, the badge uses the page
URL classification, including section overrides. `enabled = false` or
`badges = false` suppresses badges even when the page specifies a valid type.

See
[Set or remove a page's badge](../how-to/set-page-type.md) for examples.

## Zensical defaults supplied by Tarn

These defaults are in
[`mkdocs_theme.yml`](https://github.com/AxelVoitier/zensical-tarn/blob/main/src/zensical_tarn/mkdocs_theme.yml).
A project setting replaces the
corresponding theme default.

| Option | Default |
| --- | --- |
| `font.text` | `Atkinson Hyperlegible Next` |
| `font.code` | `Atkinson Hyperlegible Mono` |
| `features` | `navigation.tabs`, `navigation.indexes` |
| `palette` | Light (`default`) and dark (`slate`), following the system setting, both with `primary = "custom"` and `accent = "custom"` |
| `icon.admonition` | Lucide icons listed below |

The `icon.admonition` defaults are:

| Admonition | Icon |
| --- | --- |
| `note` | `lucide/info` |
| `abstract` | `lucide/list` |
| `info` | `lucide/info` |
| `tip` | `lucide/lightbulb` |
| `success` | `lucide/check` |
| `question` | `lucide/circle-help` |
| `warning` | `lucide/triangle-alert` |
| `failure` | `lucide/x` |
| `danger` | `lucide/zap` |
| `bug` | `lucide/bug` |
| `example` | `lucide/flask-conical` |
| `quote` | `lucide/quote` |

!!! note "List replacement"

    Project `features` and `palette` values replace the complete default lists.
    Include every entry that the project needs. Tarn does not append defaults
    or add features back after replacement.

See [sidebar navigation](../how-to/use-sidebar-navigation.md) for a complete
feature-list example.

### Palettes

Tarn supplies `default` and `slate` colours. An empty palette list uses a light
fallback. Light-only and dark-only lists are supported. Set `primary = "custom"`
and `accent = "custom"` to retain Tarn's blue link and control colours. Named
Zensical primary and accent colours remain effective when explicitly selected.
Arbitrary custom scheme names are not additional Tarn palettes. See
[Adjust a colour](../how-to/adjust-colours.md) for CSS overrides.

To start new visitors in light or dark mode while keeping the mode toggle, see
[Choose the default colour mode](../how-to/set-default-colour-mode.md). Tarn's default remains
automatic, following the system preference unless a reader has saved a choice.
The default light palette offers `lucide/moon` with the label “Switch to dark mode”. The dark
palette offers `lucide/sun` with the label “Switch to light mode”.

### Fonts and CSS

Configured fonts use Zensical's font loader. `font = false` disables that loader
and uses the upstream system fallback unless a project supplies its own fonts.
Tarn does not force an unloaded Atkinson font. See
[self-host the fonts](../how-to/self-host-fonts.md).

Tarn's stylesheet loads before Zensical's configured font declarations and the
project's `extra_css`. Project CSS can override Tarn's variables. Branding assets
use Zensical's `logo` and `favicon` theme settings, as shown in
[Add a project logo](../how-to/add-project-logo.md).

### Local templates

A local `overrides/main.html` can preserve Tarn's styles and badges by extending
its named base template:

```jinja
{% extends "tarn.html" %}
{% block extrahead %}
  {{ super() }}
  <meta name="example" content="local override">
{% endblock %}
```

Set `custom_dir = "overrides"` in `project.theme`. Extending Zensical's
`base.html` directly bypasses Tarn's template blocks.

## Generated site files

Zensical 0.0.73 copies theme package files into generated sites, including
`__init__.py`, `__pycache__/__init__.cpython-<version>.pyc`, and
`mkdocs_theme.yml`. This is a verified limitation of the pinned release.
Tarn does not remove these files automatically.

The following project-level configuration excludes these paths from the output:

```toml
[project.plugins.exclude]
glob = ["__init__.py", "__pycache__/*", "mkdocs_theme.yml"]
```

If the project already defines this table, add the patterns to its existing
`glob` list. The patterns also exclude documentation assets with matching paths.
This configuration belongs at `project.plugins.exclude`, outside `project.theme`
and `project.extra.tarn`. Theme defaults merge into `project.theme` and cannot
set this project-level plugin configuration.

The package check builds sites with an installed wheel. It reproduces the known
files in the minimal example without exclusions, then requires clean output with
these exclusions. Tarn's own documentation also uses the exclusions. See the
[generated-site checks](https://github.com/AxelVoitier/zensical-tarn/blob/main/scripts/README.md#generated-site-contents)
for the verification details.
