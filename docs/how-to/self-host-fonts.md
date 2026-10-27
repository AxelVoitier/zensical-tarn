# Self-host the fonts

Serve Tarn's default text and code fonts from your own site to avoid Google
Fonts requests. The steps below download both families, including bold weights
and italic styles, and keep their licence notices in the built site.

## Download the fonts and their licences

The Google Fonts repository supplies variable TrueType (`.ttf`) files for
[Atkinson Hyperlegible Next](https://github.com/google/fonts/tree/main/ofl/atkinsonhyperlegiblenext)
and [Atkinson Hyperlegible Mono](https://github.com/google/fonts/tree/main/ofl/atkinsonhyperlegiblemono).
A variable font contains a range of weights in one file. Both families provide
weights from 200 to 800, with separate files for normal and italic styles.
These downloads are TrueType files, so the CSS below uses `format("truetype")`.
Renaming a file to `.woff2` does not convert its format.

Save this script as `download-fonts.py` in your documentation project's root.
It saves the fonts under `docs/assets/fonts/`, with a separate licence file for
each family:

```python title="download-fonts.py"
from pathlib import Path
from urllib.parse import quote
from urllib.request import urlopen

base = "https://raw.githubusercontent.com/google/fonts/main/ofl"
fonts = Path("docs/assets/fonts")
for family, name in (
    ("next", "AtkinsonHyperlegibleNext"),
    ("mono", "AtkinsonHyperlegibleMono"),
):
    destination = fonts / family
    destination.mkdir(parents=True, exist_ok=True)
    for filename in (f"{name}[wght].ttf", f"{name}-Italic[wght].ttf", "OFL.txt"):
        url = f"{base}/{name.lower()}/{quote(filename)}"
        with urlopen(url) as response:
            (destination / filename).write_bytes(response.read())
```

Run it from the same directory with Python 3 and internet access:

```bash
python download-fonts.py
```

Keep both `OFL.txt` files alongside the fonts when you publish the site. Each
contains the family's copyright notice and SIL Open Font License 1.1. The
[Next licence](https://github.com/google/fonts/blob/main/ofl/atkinsonhyperlegiblenext/OFL.txt)
and [Mono licence](https://github.com/google/fonts/blob/main/ofl/atkinsonhyperlegiblemono/OFL.txt)
apply to the font files. They do not require your documentation to use the same
licence. See [About Tarn](../about/index.md) for Tarn's own licence scope.

## Disable the Google Fonts loader

In your existing `[project.theme]` table in `zensical.toml`, set `font = false`:

```toml
[project.theme]
name = "tarn"
font = false
```

Replace any existing `font` table or font selection with this value. Keep your
other theme settings. This disables Zensical's font loader so the local CSS
controls which fonts load.

## Declare the local font faces

Create `docs/stylesheets/fonts.css` with these declarations. Each `@font-face`
connects a font family and style to a local file. The `font-weight: 200 800`
range covers the weights supplied by each downloaded file.

```css
@font-face {
  font-family: "Atkinson Hyperlegible Next";
  src: url("../assets/fonts/next/AtkinsonHyperlegibleNext[wght].ttf") format("truetype");
  font-style: normal;
  font-weight: 200 800;
  font-display: swap;
}

@font-face {
  font-family: "Atkinson Hyperlegible Next";
  src: url("../assets/fonts/next/AtkinsonHyperlegibleNext-Italic[wght].ttf") format("truetype");
  font-style: italic;
  font-weight: 200 800;
  font-display: swap;
}

@font-face {
  font-family: "Atkinson Hyperlegible Mono";
  src: url("../assets/fonts/mono/AtkinsonHyperlegibleMono[wght].ttf") format("truetype");
  font-style: normal;
  font-weight: 200 800;
  font-display: swap;
}

@font-face {
  font-family: "Atkinson Hyperlegible Mono";
  src: url("../assets/fonts/mono/AtkinsonHyperlegibleMono-Italic[wght].ttf") format("truetype");
  font-style: italic;
  font-weight: 200 800;
  font-display: swap;
}

:root {
  --md-text-font: "Atkinson Hyperlegible Next";
  --md-code-font: "Atkinson Hyperlegible Mono";
}
```

The `../assets/fonts/` URLs are relative to `stylesheets/fonts.css`. Keep this
layout when you copy the example. If you use different font files, match their
actual format, styles and weight ranges in these declarations.

## Load the stylesheet

Add `"stylesheets/fonts.css"` to `extra_css` in your existing `[project]` table.
If you already load `stylesheets/extra.css`, the combined list is:

```toml
[project]
extra_css = ["stylesheets/extra.css", "stylesheets/fonts.css"]
```

Retain your existing entries and add the new path once. If you have no other
stylesheets, use `extra_css = ["stylesheets/fonts.css"]`. Do not create a second
`[project]` table. See [Fonts and CSS](../reference/configuration.md#fonts-and-css)
for stylesheet precedence.

## Check the requests and fallback

Build and preview your site as usual. In the browser's developer tools, open the
Network panel, disable the cache and reload the page. Filter for font requests.
The `.ttf` files used on that page must load successfully from your own site.
The browser requests a face only when the page uses that family and style.
Use a page with text, code, bold and italics to exercise the declarations.

Make sure that there are no requests to `fonts.googleapis.com` or
`fonts.gstatic.com`. Also open both `assets/fonts/next/OFL.txt` and
`assets/fonts/mono/OFL.txt` on the preview site to confirm that the licence files
are present in the output.

With `font-display: swap`, the browser displays fallback fonts while local fonts
load. If a font file fails to load, text remains readable with the fallback.
If you omit the local stylesheet entirely, `font = false` leaves Zensical's
system fonts in use.
