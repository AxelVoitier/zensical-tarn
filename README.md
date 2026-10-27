<p align="center"><img src="https://raw.githubusercontent.com/AxelVoitier/zensical-tarn/main/design/logo/tarn-logo-512.png" width="72" alt="Tarn logo"></p>

<h1 align="center">Tarn</h1>

<p align="center">A quiet, Diátaxis-aware documentation theme for <a href="https://zensical.org">Zensical</a>.</p>

<p align="center"><strong><a href="https://axelvoitier.github.io/zensical-tarn/">Read the docs and try Tarn</a></strong><br>The documentation site uses Tarn itself.</p>

![A how-to guide rendered with Tarn in light mode](https://raw.githubusercontent.com/AxelVoitier/zensical-tarn/main/screenshots/site/site-howto-light.png)

Tarn combines calm colours, legible type and Diátaxis navigation in a restrained layout for documentation.

- **Diátaxis navigation cues.** Recognised sections get coloured dots on navigation tabs or sidebar headings. Recognised page URLs receive a Tutorial, How-to guide, Reference or Explanation badge by default. You can override individual badges or disable badges and navigation decoration separately. Unrecognised sections use quieter, secondary styling by default.
- **Light and dark** palettes draw on the same mountain lake by day and night: warm cloud-grey and starlit indigo. In dark mode, you read cool off-white text against a deep blue-violet sky. The palettes follow the reader's system preference by default, unless the reader saves a choice. Projects can choose their starting mode.
- **Legible type**: Atkinson Hyperlegible Next and Mono.
- **Flat and focused**: a neutral header, thin dividing lines, five admonition tones for Zensical's twelve types, and inline code that stands out from prose and links.
- **Tabs or sidebar**: works with `navigation.tabs` (default) or `navigation.sections`.
- **Contrast checked**: the default text/background token pairs pass the generator’s 4.5:1 checks in both themes.

## Install

Tarn requires Python 3.11 or newer and pins Zensical to version 0.0.73.
See the [configuration reference](https://axelvoitier.github.io/zensical-tarn/reference/configuration/) for dependency details.

With an active virtual environment, install [Tarn from PyPI](https://pypi.org/project/zensical-tarn/):

```bash
python -m pip install zensical-tarn
```

This also installs Zensical.
Select the theme in your project's configuration:

```toml
# zensical.toml
[project.theme]
name = "tarn"
```

Zensical can also read `mkdocs.yml` with the equivalent theme selection.
MkDocs itself has not been verified:

```yaml
theme:
  name: tarn
```

Tarn styles the navigation you configure in Zensical and preserves its order.
Folders such as `tutorials/`, `how-to/`, `reference/` and `explanation/` have
built-in classifications. The homepage defaults to primary styling. Unknown
URL sections default to secondary styling. Use `project.extra.tarn.sections`
to map existing folders or mark a section as primary. The
[first-site tutorial](https://axelvoitier.github.io/zensical-tarn/tutorials/first-site/) covers a working site, and
[Name your sections](https://axelvoitier.github.io/zensical-tarn/how-to/name-sections/) explains custom mappings.

You can [add your own logo](https://axelvoitier.github.io/zensical-tarn/how-to/add-project-logo/),
[adjust colours](https://axelvoitier.github.io/zensical-tarn/how-to/adjust-colours/) and change the fonts through
[Zensical configuration](https://axelvoitier.github.io/zensical-tarn/reference/configuration/#fonts-and-css).

## Screenshots

| Light | Dark |
| --- | --- |
| ![Home, light](https://raw.githubusercontent.com/AxelVoitier/zensical-tarn/main/screenshots/site/site-home-light.png) | ![Home, dark](https://raw.githubusercontent.com/AxelVoitier/zensical-tarn/main/screenshots/site/site-home-dark.png) |
| ![Sidebar navigation, light](https://raw.githubusercontent.com/AxelVoitier/zensical-tarn/main/screenshots/site/site-sidebar-navigation-light.png) | ![Sidebar navigation, dark](https://raw.githubusercontent.com/AxelVoitier/zensical-tarn/main/screenshots/site/site-sidebar-navigation-dark.png) |
| ![Admonitions, light](https://raw.githubusercontent.com/AxelVoitier/zensical-tarn/main/screenshots/components/admonitions-light.png) | ![Admonitions, dark](https://raw.githubusercontent.com/AxelVoitier/zensical-tarn/main/screenshots/components/admonitions-dark.png) |
| ![Code block, light](https://raw.githubusercontent.com/AxelVoitier/zensical-tarn/main/screenshots/components/code-block-light.png) | ![Code block, dark](https://raw.githubusercontent.com/AxelVoitier/zensical-tarn/main/screenshots/components/code-block-dark.png) |

More in [`screenshots/`](https://github.com/AxelVoitier/zensical-tarn/tree/main/screenshots/).

## Documentation

The theme's own documentation, built with Tarn: <https://axelvoitier.github.io/zensical-tarn/>

## Licence

Copyright Axel Voitier. Original Tarn material is licensed under [Apache 2.0](https://github.com/AxelVoitier/zensical-tarn/blob/main/LICENSE).
Includes modified Zensical templates under MIT; see [NOTICE](https://github.com/AxelVoitier/zensical-tarn/blob/main/NOTICE) and the
[upstream licence](https://github.com/AxelVoitier/zensical-tarn/blob/main/LICENSES/zensical-ui.MIT.txt). The combined package metadata
records `Apache-2.0 AND MIT`. Fonts are fetched from Google Fonts, with
[self-hosting instructions](https://axelvoitier.github.io/zensical-tarn/how-to/self-host-fonts/).
