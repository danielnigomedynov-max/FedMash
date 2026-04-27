we are making a compiled set of rules for RC competitions that will be released to the public

the goal is to maintain a python script that creates a PDF from all numbered MD files in the project root
the script and required files should be in the same folder as this instruction (`PDF_Conversion`)

## source files and sections 
- include only markdown files in project root that match numbered naming like `01. name.md`, `02. name.md`, etc
- sort sections by numeric prefix
- each markdown file becomes one **section**
- each section starts on a new page
- section title source is only the first level-1 heading (`# ...`) from each markdown file
- when rendering section body, remove that first level-1 heading from content to avoid duplicated main heading in the PDF

## rendering engine and dependencies
- use a pure `reportlab` based pipeline (do not rely on `weasyprint` / GTK system libraries)
- required python packages:
  - `markdown`
  - `beautifulsoup4`
  - `reportlab`

## build freshness / cache
- every run must be a fresh build
- clean python cache folders (`__pycache__`) before generation
- avoid generating new bytecode cache during the run

## document layout
- PDF page size: A4
- font family: Jost from local files:
  - `Jost-VariableFont_wght.ttf`
  - `Jost-Italic-VariableFont_wght.ttf`

## title page
- first page is a title page
- `FM_Logo.png` in the top-left corner with 0.5 inch padding
- `FM_Car.png` in the lower-right corner without padding
- centered text: `Регламент соревнований v1.02`

## table of contents
- second page is a table of contents
- TOC contains all sections
- TOC entries are clickable links to the corresponding section
- TOC section names must come from the first level-1 heading (`# ...`) only
- TOC entries should be unnumbered (no added numeric prefix in TOC itself)

## links and markdown features
- keep working links from markdown clickable in the PDF
- preserve external links (`http`, `https`, `mailto`)
- convert links to other project markdown files to internal PDF section links when possible
- markdown tables must be rendered as actual PDF tables (not plain text)

## repeated page elements (all pages except title page)
- header with the current section name (must match the same page, not delayed by one page)
- header section name must come from the first level-1 heading (`# ...`) only
- page number
- `FM_Logo.png` watermark in the lower-left corner:
  - 10% opacity
  - 0.25 inch padding from edges, absolute placement