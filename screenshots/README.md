# Screenshots

Site and component screenshots are taken at 1280 px wide, 2× scale, from a real
Zensical 0.0.73 build of this repository's `docs/` with the installed theme and
the configured Atkinson fonts loaded. Regenerate them with
`python scripts/capture_screenshots.py` after installing the updated theme.
The script also refreshes the light and dark home-page previews and the sidebar image embedded in the documentation.
It builds the section-mapping and colour-override examples to capture their
results in `docs/assets/screenshots/`. To refresh only those two images, run
`python scripts/capture_screenshots.py --guide-results`.

| Folder | What |
| --- | --- |
| `site/` | Full pages, light and dark: home, a tutorial, a how-to, reference, explanation, a secondary section (About), the components page (full length), and the same how-to with sidebar navigation instead of tabs. |
| `components/` | Page elements cropped from the build: header and tabs, sidebar navigation, admonitions, code block, content tabs, table, buttons, Diátaxis badges, inline code / keys / highlight. |
