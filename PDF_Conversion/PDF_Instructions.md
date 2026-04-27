we are making a compiled set of rules for RC competitions that will be released to the public

the goal is to write a script in python that creates a PDF file from all MD files in the project that are numbered
put the script and other required stuff is the same folder as this instruction

each MD file will become a **section** in the PDF

PDF should have A4 page size
PDF should use Jost font - Jost-VariableFont_wght.ttf and Jost-Italic-VariableFont_wght.ttf inside the project

PDF should start with a title page
title page has FM_Logo.png in the left top corner with half inch padding
title page has FM_Car.png in the lower right corner without padding
in the center of title page it says "Регламент соревнований v1.02"

after the title page there should be a table of contents page, containing all **sections** with clickable links

all links that work in the MD files should also work and be clickable inside the PDF

each **section** should start with a new page in the PDF

each page of the PDF (except the title page) contains:
- header that sais the name of the section
- page number
- FM_Logo.png with 10% opacity in the left lower corner with padding of 0.1 inch