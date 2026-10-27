# Why these colours

Tarn's default palette gives colours recurring roles. Blue marks actions such as
links and primary buttons. Green marks tutorials as learning material and
appears in tip and success messages. Keeping default links blue separates these roles.
Neutral slate suits the factual character of reference, while warm ochre marks
explanation and its emphasis on reflection.

The light background is a warm cloud-grey (`#eae5df`), sampled from sunlit clouds
over a tarn. The choice expresses Tarn's aim for a quiet reading surface without
the brightness of a white page or the cooler tone of a blue-grey. Dark mode uses
an ink-blue night. The aim is for both schemes to evoke the tarn, so switching
modes retains that connection.

The roles describe Tarn's defaults. A project's CSS overrides can change both
the palette and its associations. With their standard titles and icons,
admonitions identify their type through words and symbols as well as colour.
The cues in other page content depend on the site's authoring choices.

The stylesheet generator checks selected text/background token pairs against a
4.5:1 contrast threshold in both default schemes. These checks do not establish
full accessibility conformance or cover project colour overrides. They test
specific colour combinations, rather than every rendered element or interaction.

[Design principles](design-principles.md) places the palette within Tarn's wider
approach to reading and navigation. [Adjust a colour](../how-to/adjust-colours.md)
describes project overrides and checking their contrast.
