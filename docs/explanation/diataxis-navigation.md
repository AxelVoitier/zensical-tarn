# Diátaxis in the navigation

Tarn's optional Diátaxis decoration helps readers recognise the purpose of a
section or page. A coloured dot identifies a section in the navigation, and a
badge above the page title names its documentation type. These cues support the
structure that the author gives the documentation.

## Four reader needs

[Diátaxis](https://diataxis.fr/) organises documentation around four reader needs.
Each need calls for a different kind of writing:

| Reader need | Documentation type | What the reader expects |
| --- | --- | --- |
| Learn through practice | Tutorial | A guided learning experience |
| Complete a task | How-to guide | Directions for a specific goal |
| Look up a detail | Reference | Accurate descriptions to consult |
| Understand a subject | Explanation | Context, reasons and relationships |

The distinction matters when a reader chooses where to go. Someone looking up a
configuration value needs a different page from someone learning to configure a
site for the first time. Section names and visual cues can help them choose,
but the page's writing must still meet that need. Tarn cannot read the prose or
determine whether a page fulfils its stated purpose.

## Section cues and page badges

By default, Tarn decorates recognised Diátaxis sections with coloured dots.
Tabs also use the section colour for the active underline. In sidebar navigation,
the dot appears before the top-level section label. The page badge names the
documentation type in the corresponding colour, so the meaning does not depend
on colour alone.

These decorations are optional. Navigation decoration and page badges have
independent switches, with an overall switch that disables both. A site can keep
the dots while hiding badges, or keep badges without decorating the navigation.
The [configuration reference](../reference/configuration.md#decoration-and-credit-switches)
describes the switches. Disabling them leaves Tarn's other theme styling in place.

Automatic classification comes from the first segment of a page's URL, with
built-in aliases and project mappings. A navigation section takes its
classification from its selected index or first linked page. Changing the visible
section title therefore does not change its decoration. The
[section mapping reference](../reference/section-folders.md) explains the matching
rules, and [Name your sections](../how-to/name-sections.md) covers custom mappings.

A page's purpose can differ from the section that contains it. For example, a
reference section can contain an explanation of a design decision. A page badge
override lets that explanation identify its purpose while the section keeps its
reference dot. The override affects only the badge. It does not move the page or
change the section's classification. A page can also suppress its badge, and a
page outside a Diátaxis section can have an explicit badge. These choices are
covered in [Set or remove a page's badge](../how-to/set-page-type.md).

## Space for other sections

Sites often give project background, contributor information and release history
their own sections. Tarn classifies `about`, `contributing`
and `changelog` as secondary by default. Unrecognised URL segments also default
to secondary. These sections have quieter navigation text, without a dot or an
automatic badge.

Tarn preserves the project's navigation order. When secondary sections are grouped
after the main sections, they sit at the right of the tab bar or below a separator
in sidebar navigation. Classification alone does not move them there. The
[sidebar guide](../how-to/use-sidebar-navigation.md) shows that layout.

A custom section can instead use the `primary` classification. For example, a
collection of examples can remain alongside the main documentation without a
Diátaxis dot or an automatic badge.

## A consistent current-page cue

With Tarn's default colours, the current page in the sidebar stays blue across
Diátaxis sections. Its text also becomes heavier and gains a background highlight.
The current-page cue answers “Where am I?”, while the section dot and page badge
identify the kind of documentation. Keeping these roles distinct lets the section
colour retain its meaning as readers move between pages. Projects that customise
the primary colour also change the colour of the current-page cue.
