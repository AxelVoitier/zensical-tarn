# Choose the default colour mode

Start new visitors in light or dark mode regardless of their system preference,
while keeping the toggle that lets them choose either mode. Tarn follows the system
preference by default. This override applies only to your site.

## Set the palette order

Add one of the following configurations to `zensical.toml`, after your existing
`[project.theme]` settings. If you already define `project.theme.palette`,
replace that definition with the selected configuration.

The first entry sets the initial mode: `default` is light and `slate` is dark.
Omit `media` from both entries so the system preference does not select the
initial mode. The `custom` primary and accent settings retain Tarn's colours.

=== "Light first"

    ```toml
    [[project.theme.palette]]
    scheme = "default"
    primary = "custom"
    accent = "custom"
    toggle = { icon = "lucide/moon", name = "Switch to dark mode" }

    [[project.theme.palette]]
    scheme = "slate"
    primary = "custom"
    accent = "custom"
    toggle = { icon = "lucide/sun", name = "Switch to light mode" }
    ```

=== "Dark first"

    ```toml
    [[project.theme.palette]]
    scheme = "slate"
    primary = "custom"
    accent = "custom"
    toggle = { icon = "lucide/sun", name = "Switch to light mode" }

    [[project.theme.palette]]
    scheme = "default"
    primary = "custom"
    accent = "custom"
    toggle = { icon = "lucide/moon", name = "Switch to dark mode" }
    ```

!!! note "Saved choices take precedence"

    A reader's choice of dark or light mode is remembered in that browser and takes
    precedence on later visits. An existing saved choice still applies after this
    configuration change.

## Check the initial mode

Run `zensical serve` and open the site in a fresh private browsing session.
Use the opposite system preference to confirm that the site starts in your
chosen mode independently of that preference.

## Check the reader's choice

Use the moon toggle to switch from light to dark, or the sun toggle to switch
from dark to light. Reload the page to confirm that the selected mode is kept.

## Restore the automatic default

To restore Tarn's automatic default, remove the palette override from your
project configuration.

See [palette configuration](../reference/configuration.md#palettes) for the
supported schemes and how project palette lists replace the theme defaults.
For the reasons behind Tarn's colour choices, see
[Why these colours](../explanation/colour.md).
