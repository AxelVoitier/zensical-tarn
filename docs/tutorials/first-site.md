# Your first Tarn site

In this tutorial you build a small documentation site with Tarn, organised in the
four Diátaxis sections. Diátaxis groups documentation by what readers need to do:
learn through a tutorial, complete a task, look up details, or understand a topic.

Your finished site will have a home page and four section pages. Each section
will have a coloured dot in the navigation and a badge above its page title.
You will see the result in your browser before you finish.

## Prerequisites

You need Python 3.11 or later, a terminal, and a text editor. You also need an
internet connection to install Tarn and its dependencies.

Tarn's first package release is still in preparation. This lesson installs Tarn
from its source code. Obtain a source checkout or source archive before starting.
If you have an archive, extract it. Name the resulting source folder
`zensical-tarn` and make sure that it contains `pyproject.toml`.

Open your terminal in the directory that contains `zensical-tarn`. Your new
`my-docs` directory will sit alongside that source folder:

```text
working-directory/
├── zensical-tarn/
│   └── pyproject.toml
└── my-docs/               (created in the next step)
```

## 1. Install Zensical and Tarn

First, create a directory for your site and enter it. Then create a virtual
environment, which keeps this site's Python packages separate from other projects.
Activate the environment before installing Tarn.

=== "macOS / Linux"

    ```bash
    python3 --version
    mkdir my-docs
    cd my-docs
    python3 -m venv .venv
    source .venv/bin/activate
    ```

=== "Windows (Command Prompt)"

    ```bat
    py --version
    mkdir my-docs
    cd my-docs
    py -m venv .venv
    .venv\Scripts\activate.bat
    ```

Make sure that the reported Python version is at least 3.11. After activation,
your terminal prompt usually starts with `(.venv)`. Keep this terminal open and
use it for the remaining commands.

Install Tarn from the adjacent source folder in the active environment.
Run this from `my-docs` on either platform:

```bash
python -m pip install ../zensical-tarn
zensical --version
```

Installing Tarn also installs its pinned Zensical dependency. The final command
prints the installed Zensical version.

!!! note "After package publication"
    Once Tarn is published on PyPI, `python -m pip install zensical-tarn` will
    install the published package. For this lesson, use the source installation
    command above.

## 2. Create the project

Inside `my-docs`, create the folders for the four sections:

=== "macOS / Linux"

    ```bash
    mkdir -p docs/tutorials docs/how-to docs/reference docs/explanation
    ```

=== "Windows (Command Prompt)"

    ```bat
    mkdir docs\tutorials docs\how-to docs\reference docs\explanation
    ```

Use your editor to create the following five Markdown files. Markdown is a text
format for headings, paragraphs and links. In these files, `#` starts a page title.
Save each file at the path shown above its contents, relative to `my-docs`.

```markdown title="docs/index.md"
# My project

Welcome to my project's documentation.

Choose a section to find the help you need.
```

```markdown title="docs/tutorials/index.md"
# Tutorials

Learn by following a guided lesson.
```

```markdown title="docs/how-to/index.md"
# How-to guides

Follow instructions to complete a specific task.
```

```markdown title="docs/reference/index.md"
# Reference

Look up configuration settings and technical details.
```

```markdown title="docs/explanation/index.md"
# Explanation

Understand the ideas behind the project.
```

Your project now has this layout. The `.venv` directory contains the environment
from the previous step.

```text
my-docs/
├── .venv/
└── docs/
    ├── index.md
    ├── tutorials/index.md
    ├── how-to/index.md
    ├── reference/index.md
    └── explanation/index.md
```

## 3. Select the theme

Create `zensical.toml` in `my-docs`, beside the `docs` directory. Copy the complete
configuration below into it. TOML is the configuration format that Zensical reads.
The `nav` list sets the navigation order and names each section.

```toml title="zensical.toml"
[project]
site_name = "My project"
nav = [
  {"Home" = "index.md"},
  {"Tutorials" = ["tutorials/index.md"]},
  {"How-to guides" = ["how-to/index.md"]},
  {"Reference" = ["reference/index.md"]},
  {"Explanation" = ["explanation/index.md"]},
]

[project.theme]
name = "tarn"
```

The paths in `nav` are relative to `docs`. Tarn recognises the section folders
used here and supplies their dots and badges. You do not need to configure those
separately for this site.

## 4. Preview it

From `my-docs`, start the local preview:

```bash
zensical serve
```

Keep the command running. Open the local address printed in the terminal,
normally <http://localhost:8000>. You will see the “My project” home page.

On a wide screen, the four sections appear as tabs in the header. On a narrow
screen, open the navigation menu to find them. Visit each section and compare
its page with the following table:

| Section | Page title | Badge above the title |
| --- | --- | --- |
| Tutorials | Tutorials | Tutorial |
| How-to guides | How-to guides | How-to guide |
| Reference | Reference | Reference |
| Explanation | Explanation | Explanation |

Each section has a coloured dot in the navigation. Home has no automatic badge.

In your editor, change the welcome paragraph in `docs/index.md` and save the file.
Return to Home in your browser. The preview rebuilds and shows your changed text.

!!! success "You built a Tarn site"
    Your site now has a home page and four working sections, with Tarn's section
    dots and page badges. Changes to your Markdown files appear in the preview
    when you save them.

Press ++ctrl+c++ in the terminal when you finish previewing.

## Next steps

Give your site its own identity with [Add a project logo](../how-to/add-project-logo.md).
Read [Diátaxis navigation](../explanation/diataxis-navigation.md) to understand how
Tarn classifies the sections.

Before sharing a generated site, see
[Generated site files](../reference/configuration.md#generated-site-files) for the
optional output exclusions. The
[configuration reference](../reference/configuration.md) describes the settings
that you can change as your site grows.

For Zensical features beyond Tarn, continue with the
[Zensical documentation](https://zensical.org/docs/). It covers writing pages,
configuring your site and publishing it.
