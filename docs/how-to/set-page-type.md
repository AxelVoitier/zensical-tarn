# Set or remove a page's badge

Use a page override when its purpose differs from its section, or hide the badge
on a section overview. The override affects the badge above the page title. It
leaves the section's navigation decoration unchanged.

To display a badge, both `enabled` and `badges` under `project.extra.tarn` must be
`true`. Both default to `true`. If either is `false`, a page override cannot
restore the badge. See [Tarn settings](../reference/configuration.md#tarn-settings)
if you need to change these site-wide switches.

Add the following to the page's YAML front matter. If the page already has front
matter, add `tarn` to that block:

```yaml
---
tarn:
  type: howto
---
```

Use `tutorial`, `howto`, `reference`, or `explanation` for the badge you want.
The example selects the How-to guide badge, even if the page is outside a
how-to section.

To hide the badge on this page instead, set `tarn.type` to `none`:

```yaml
---
tarn:
  type: none
---
```

To return to the automatic badge for the page's section, remove `tarn.type`.
The [section mapping](../reference/section-folders.md) determines which badge
appears by default, if any.

Build or preview the site and open the page. With badges enabled, the selected
badge appears above the title. With `none`, the badge is absent. The navigation
decoration stays the same in both cases.

For badge label translations and site-wide controls, see
[Tarn settings](../reference/configuration.md#tarn-settings). For the relationship
between page badges and section decoration, read
[Diátaxis navigation](../explanation/diataxis-navigation.md).
