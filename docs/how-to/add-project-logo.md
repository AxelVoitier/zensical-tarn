# Add a project logo

Show your own logo in the site header. You can also set an icon for browser tabs,
called a favicon.

Use an existing Zensical site with Tarn selected and an SVG or PNG logo.
Choose an image that remains readable at the small size used in the header.

## Set the logo and favicon

1. Copy your logo to `docs/assets/logo.svg`.
   For a PNG, use `docs/assets/logo.png` and change the path below to match.

2. Set the logo path in `zensical.toml`:

    ```toml
    [project.theme]
    name = "tarn"
    logo = "assets/logo.svg"
    ```

    Merge these values into your existing `[project.theme]` section.
    Paths are relative to `docs/`.

3. To set a favicon, copy the icon to `docs/assets/favicon.svg`.
   Add this setting to the same `[project.theme]` section:

    ```toml
    favicon = "assets/favicon.svg"
    ```

    You can use `assets/logo.svg` here to reuse the header logo.

## Check the result

Run `zensical serve` and view the site in both colour modes. The header displays
your logo beside the site name. If you configured a favicon, it appears in the
browser tab. Make sure that the logo remains visible against both backgrounds.

See [Adjust a colour](adjust-colours.md) to customise the palette. The
[design sources](https://github.com/AxelVoitier/zensical-tarn/blob/main/design/README.md#logo)
describe how Tarn's own logo and the example flow logo were drawn.
