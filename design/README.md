# Design sources

| Path | What |
| --- | --- |
| `tokens.json` | The design tokens: colours for both schemes (with usage notes), type scale, spacing, radii, shadow. **Source of truth for every colour in the theme.** `scripts/build_css.py` turns it into `src/zensical_tarn/assets/stylesheets/tarn.css`. |
| `logo/` | Tarn's own logo (below) and its PNG exports. |

These files were exported from the original AI-assisted design system. The
original Tarn design assets are copyright Axel Voitier and use the Apache 2.0
licence in the repository root. The licence grants no trademark rights.

## Logo

Tarn's mark is a mountain ridge above still water. Its construction uses:

- 24 × 24 tile, corner radius 5, fill `#2563c8` (same in both themes).
- White glyph inside the central 16 × 16, 2-unit round strokes, lines only.

The flow logo in the minimal example uses the same tile and stroke style with
a different glyph. These guidelines describe the supplied artwork. A site's
own logo can use its own shape, colours and lettering. See
[Add a project logo](../docs/how-to/add-project-logo.md) to configure one.

| File | Use |
| --- | --- |
| `tarn-logo.svg` | header logo (`theme.logo`) |
| `tarn-favicon.svg` | favicon (`theme.favicon`), same drawing |
| `tarn-logo-mono.svg` / `tarn-logo-mono-light.svg` | one-colour glyph, for light / dark grounds |
| `tarn-logo-512.png`, `tarn-apple-touch-icon.png`, `tarn-favicon-32.png` | raster exports |
| `tarn-lockup.png` | logo with name, light and dark |
