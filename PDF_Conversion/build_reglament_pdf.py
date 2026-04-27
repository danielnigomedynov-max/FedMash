#!/usr/bin/env python3
"""
Build a single A4 PDF from numbered markdown files in the repository root.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

import markdown
from bs4 import BeautifulSoup, Tag
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, StyleSheet1, getSampleStyleSheet
from reportlab.lib.units import inch, mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Flowable,
    Frame,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from xml.sax.saxutils import escape


ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = Path(__file__).resolve().parent

TITLE_TEXT = "Регламент соревнований v1.02"
NUMBERED_MD_RE = re.compile(r"^(\d+)\.\s+(.+)\.md$", re.IGNORECASE)
sys.dont_write_bytecode = True


@dataclass
class Section:
    file_path: Path
    section_id: str
    title: str
    html_body: str


class SectionMarker(Flowable):
    def __init__(self, section_name: str):
        super().__init__()
        self.section_name = section_name

    def wrap(self, availWidth, availHeight):  # noqa: N802
        return 0, 0

    def draw(self):
        return


def discover_sections(root: Path) -> list[Path]:
    sections: list[tuple[int, Path]] = []
    for file_path in root.glob("*.md"):
        match = NUMBERED_MD_RE.match(file_path.name)
        if not match:
            continue
        sections.append((int(match.group(1)), file_path))
    sections.sort(key=lambda item: item[0])
    return [item[1] for item in sections]


def md_basename_to_slug(path: Path) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", path.stem).strip("-").lower()
    return slug or "section"


def resolve_section_title(md_text: str, fallback_name: str) -> str:
    for line in md_text.splitlines():
        line = line.strip()
        if re.match(r"^#\s+.+", line):
            return re.sub(r"^#\s+", "", line).strip()
    return re.sub(r"^\d+\.\s+", "", fallback_name)


def rewrite_md_links(soup: BeautifulSoup, md_to_anchor: dict[str, str]) -> None:
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"].strip()
        if not href:
            continue
        if href.startswith(("http://", "https://", "mailto:", "#")):
            continue
        target, _, fragment = href.partition("#")
        if target.lower().endswith(".md"):
            if target in md_to_anchor:
                if fragment:
                    anchor["href"] = f"#{md_to_anchor[target]}"
                else:
                    anchor["href"] = f"#{md_to_anchor[target]}"
            else:
                anchor.attrs.pop("href", None)


def sanitize_html_for_reportlab(soup: BeautifulSoup) -> None:
    allowed_a_attrs = {"href", "name", "color"}
    for tag in soup.find_all(True):
        if tag.name.lower() == "a":
            if "id" in tag.attrs and "name" not in tag.attrs:
                tag.attrs["name"] = tag.attrs["id"]
            tag.attrs = {key: value for key, value in tag.attrs.items() if key in allowed_a_attrs}
            continue
        tag.attrs = {}


def markdown_to_html(md_text: str, md_to_anchor: dict[str, str]) -> str:
    raw_html = markdown.markdown(
        md_text,
        extensions=["extra", "tables", "sane_lists", "fenced_code"],
        output_format="html5",
    )
    soup = BeautifulSoup(raw_html, "html.parser")
    rewrite_md_links(soup, md_to_anchor)
    sanitize_html_for_reportlab(soup)
    return str(soup)


def build_sections(files: list[Path]) -> list[Section]:
    md_to_anchor = {file_path.name: f"section-{md_basename_to_slug(file_path)}" for file_path in files}
    sections: list[Section] = []
    for file_path in files:
        md_text = file_path.read_text(encoding="utf-8")
        sections.append(
            Section(
                file_path=file_path,
                section_id=md_to_anchor[file_path.name],
                title=resolve_section_title(md_text, file_path.stem),
                html_body=markdown_to_html(md_text, md_to_anchor),
            )
        )
    return sections


def normalize_inline_markup(text: str) -> str:
    cleaned = text.replace("<strong>", "<b>").replace("</strong>", "</b>")
    cleaned = cleaned.replace("<em>", "<i>").replace("</em>", "</i>")
    return cleaned


def html_block_to_story(node: Tag, styles: StyleSheet1) -> list[Flowable]:
    flows: list[Flowable] = []
    node_name = node.name.lower()

    if node_name in {"h1", "h2", "h3"}:
        style = styles["H1"] if node_name == "h1" else styles["H2"] if node_name == "h2" else styles["H3"]
        flows.append(Paragraph(normalize_inline_markup(node.decode_contents()), style))
        flows.append(Spacer(1, 6))
        return flows

    if node_name == "p":
        flows.append(Paragraph(normalize_inline_markup(node.decode_contents()), styles["Body"]))
        flows.append(Spacer(1, 4))
        return flows

    if node_name in {"ul", "ol"}:
        ordered = node_name == "ol"
        idx = 1
        for li in node.find_all("li", recursive=False):
            bullet = f"{idx}." if ordered else "•"
            body = normalize_inline_markup(li.decode_contents())
            flows.append(Paragraph(f"{bullet} {body}", styles["Body"]))
            idx += 1
        flows.append(Spacer(1, 4))
        return flows

    if node_name == "table":
        rows: list[list[Paragraph]] = []
        for tr in node.find_all("tr"):
            cells: list[Paragraph] = []
            for cell in tr.find_all(["th", "td"], recursive=False):
                cell_html = normalize_inline_markup(cell.decode_contents().strip())
                if not cell_html:
                    cell_html = " "
                cells.append(Paragraph(cell_html, styles["Body"]))
            if cells:
                rows.append(cells)

        if rows:
            max_cols = max(len(r) for r in rows)
            for row in rows:
                while len(row) < max_cols:
                    row.append(Paragraph(" ", styles["Body"]))

            table = Table(rows, repeatRows=1)
            table.setStyle(
                TableStyle(
                    [
                        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#888888")),
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#efefef")),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 4),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                        ("TOPPADDING", (0, 0), (-1, -1), 3),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ]
                )
            )
            flows.append(table)
            flows.append(Spacer(1, 6))
        return flows

    if node_name == "pre":
        code_text = escape(node.get_text("\n"))
        flows.append(Paragraph(f"<font name='Courier'>{code_text}</font>", styles["Body"]))
        flows.append(Spacer(1, 4))
        return flows

    if node_name == "blockquote":
        flows.append(Paragraph(normalize_inline_markup(node.decode_contents()), styles["Quote"]))
        flows.append(Spacer(1, 4))
        return flows

    flows.append(Paragraph(normalize_inline_markup(node.decode_contents()), styles["Body"]))
    flows.append(Spacer(1, 4))
    return flows


def register_fonts() -> None:
    pdfmetrics.registerFont(TTFont("Jost", str(ASSETS_DIR / "Jost-VariableFont_wght.ttf")))
    pdfmetrics.registerFont(TTFont("JostItalic", str(ASSETS_DIR / "Jost-Italic-VariableFont_wght.ttf")))


def make_styles() -> StyleSheet1:
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="Body",
            parent=styles["Normal"],
            fontName="Jost",
            fontSize=11,
            leading=15,
            spaceAfter=3,
            linkColor=colors.HexColor("#0b4ea2"),
        )
    )
    styles.add(
        ParagraphStyle(
            name="H1",
            parent=styles["Heading1"],
            fontName="Jost",
            fontSize=19,
            leading=24,
            spaceAfter=8,
        )
    )
    styles.add(
        ParagraphStyle(
            name="H2",
            parent=styles["Heading2"],
            fontName="Jost",
            fontSize=15,
            leading=19,
            spaceAfter=7,
        )
    )
    styles.add(
        ParagraphStyle(
            name="H3",
            parent=styles["Heading3"],
            fontName="Jost",
            fontSize=13,
            leading=16,
            spaceAfter=6,
        )
    )
    styles.add(
        ParagraphStyle(
            name="Quote",
            parent=styles["Body"],
            fontName="JostItalic",
            textColor=colors.HexColor("#444444"),
            leftIndent=14,
            borderPadding=2,
        )
    )
    styles.add(
        ParagraphStyle(
            name="TOCEntry",
            parent=styles["Body"],
            fontName="Jost",
            fontSize=11,
            leading=14,
            spaceAfter=6,
        )
    )
    return styles


def build_story(sections: list[Section], styles: StyleSheet1) -> list[Flowable]:
    story: list[Flowable] = []
    story.append(Spacer(1, 10))
    story.append(NextPageTemplate("Body"))
    story.append(PageBreak())

    story.append(SectionMarker("Содержание"))
    story.append(Paragraph("Содержание", styles["H1"]))
    for index, section in enumerate(sections, start=1):
        story.append(
            Paragraph(
                f"{index}. <link href='#{section.section_id}' color='#0b4ea2'>{section.title}</link>",
                styles["TOCEntry"],
            )
        )
    story.append(PageBreak())

    for idx, section in enumerate(sections):
        if idx > 0:
            story.append(PageBreak())
        story.append(SectionMarker(section.title))
        story.append(Paragraph(f"<a name='{section.section_id}'/>{section.title}", styles["H1"]))

        soup = BeautifulSoup(section.html_body, "html.parser")
        for node in soup.children:
            if not isinstance(node, Tag):
                continue
            story.extend(html_block_to_story(node, styles))
    return story


def draw_title_page(canvas, _doc) -> None:
    canvas.saveState()
    page_width, page_height = A4
    half_inch = 0.5 * inch

    logo_path = str(ASSETS_DIR / "FM_Logo.png")
    car_path = str(ASSETS_DIR / "FM_Car.png")

    logo_w = 2.2 * inch
    logo_reader = ImageReader(logo_path)
    logo_px_w, logo_px_h = logo_reader.getSize()
    logo_h = logo_w * (logo_px_h / logo_px_w)
    canvas.drawImage(
        logo_path,
        half_inch,
        page_height - half_inch - logo_h,
        width=logo_w,
        height=logo_h,
        preserveAspectRatio=True,
        mask="auto",
    )

    car_w = 3.3 * inch
    car_reader = ImageReader(car_path)
    car_px_w, car_px_h = car_reader.getSize()
    car_h = car_w * (car_px_h / car_px_w)
    canvas.drawImage(
        car_path,
        page_width - car_w,
        0,
        width=car_w,
        height=car_h,
        preserveAspectRatio=True,
        mask="auto",
    )

    canvas.setFont("Jost", 32)
    canvas.drawCentredString(page_width / 2, page_height / 2, TITLE_TEXT)
    canvas.restoreState()


def draw_body_page(canvas, doc) -> None:
    return


def draw_body_page_end(canvas, doc) -> None:
    canvas.saveState()
    page_width, page_height = A4
    page_no = canvas.getPageNumber()
    canvas.resetTransforms()

    watermark_path = str(ASSETS_DIR / "FM_Logo.png")
    canvas.setFillAlpha(0.10)
    canvas.drawImage(
        watermark_path,
        0.25 * inch,
        0.25 * inch,
        width=1.2 * inch,
        height=1.2 * inch,
        preserveAspectRatio=True,
        mask="auto",
    )
    canvas.setFillAlpha(1.0)

    header_text = getattr(doc, "current_section", "")
    canvas.setFont("Jost", 9)
    canvas.drawCentredString(page_width / 2, page_height - 0.35 * inch, header_text)

    content_page_no = max(1, page_no - 1)
    canvas.drawCentredString(page_width / 2, 0.3 * inch, str(content_page_no))
    canvas.restoreState()


def after_flowable(doc, flowable) -> None:
    if isinstance(flowable, SectionMarker):
        doc.current_section = flowable.section_name


def validate_assets() -> None:
    required = [
        ASSETS_DIR / "FM_Logo.png",
        ASSETS_DIR / "FM_Car.png",
        ASSETS_DIR / "Jost-VariableFont_wght.ttf",
        ASSETS_DIR / "Jost-Italic-VariableFont_wght.ttf",
    ]
    missing = [path for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Missing required assets: {', '.join(str(item) for item in missing)}")


def clean_caches(root: Path) -> int:
    removed = 0
    for cache_dir in root.rglob("__pycache__"):
        if cache_dir.is_dir():
            shutil.rmtree(cache_dir, ignore_errors=True)
            removed += 1
    return removed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build PDF from numbered markdown files.")
    parser.add_argument(
        "--output",
        default=str(ASSETS_DIR / "Reglament_v1.02.pdf"),
        help="Path to output PDF file.",
    )
    return parser.parse_args()


def build_pdf(output_path: Path, sections: list[Section]) -> None:
    register_fonts()
    styles = make_styles()

    margin_left = 18 * mm
    margin_right = 18 * mm
    margin_top = 20 * mm
    margin_bottom = 20 * mm

    doc = BaseDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=margin_left,
        rightMargin=margin_right,
        topMargin=margin_top,
        bottomMargin=margin_bottom,
        title=TITLE_TEXT,
    )

    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="content-frame")
    title_template = PageTemplate(id="Title", frames=[frame], onPage=draw_title_page)
    body_template = PageTemplate(id="Body", frames=[frame], onPage=draw_body_page, onPageEnd=draw_body_page_end)
    doc.addPageTemplates([title_template, body_template])
    doc.afterFlowable = lambda flowable: after_flowable(doc, flowable)
    doc.current_section = ""

    story = build_story(sections, styles)
    doc.build(story)


def main() -> None:
    args = parse_args()
    removed_cache_dirs = clean_caches(ROOT)
    validate_assets()
    section_files = discover_sections(ROOT)
    if not section_files:
        raise RuntimeError(f"No numbered markdown files found in {ROOT}")
    sections = build_sections(section_files)
    output_path = Path(args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    build_pdf(output_path, sections)
    print(f"Generated: {output_path}")
    print(f"Sections included: {len(sections)}")
    print(f"Cache folders removed: {removed_cache_dirs}")


if __name__ == "__main__":
    main()
