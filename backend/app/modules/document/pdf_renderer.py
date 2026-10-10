from __future__ import annotations

from io import BytesIO
from datetime import datetime
from pathlib import Path

import mistune
import qrcode
from fpdf import FPDF
from fpdf.enums import MethodReturnValue, XPos, YPos
from fpdf.errors import FPDFException

from app.core.config import Settings
from app.modules.document.markdown_source import ParsedLetter
from app.modules.template.schemas import TemplateSettings


MAX_PDF_PAGES = 50
PAGE_BREAK = "\\pagebreak"
CENTER_OPEN = "::: center"
CENTER_CLOSE = ":::"


def _parse_underline(inline, match, state):
    start = match.end()
    end = state.src.find("++", start)
    if end <= start:
        return None
    child_state = state.copy()
    child_state.src = state.src[start:end]
    state.append_token(
        {"type": "underline", "children": inline.render(child_state)}
    )
    return end + 2


def _underline_plugin(markdown):
    markdown.inline.register(
        "underline", r"\+\+(?=[^\s+])", _parse_underline, before="link"
    )


class InvalidMarkdown(ValueError):
    pass


class RenderLimitExceeded(ValueError):
    pass


def _plain_text(nodes: list[dict[str, object]]) -> str:
    fragments: list[str] = []
    for node in nodes:
        kind = node.get("type")
        if kind in {"text", "inline_code", "codespan"}:
            fragments.append(str(node.get("raw", "")))
        elif kind in {"softbreak", "linebreak"}:
            fragments.append(" ")
        else:
            children = node.get("children")
            if isinstance(children, list):
                fragments.append(_plain_text(children))
    return "".join(fragments)


class LetterPDF(FPDF):
    def __init__(
        self,
        settings: TemplateSettings,
        font_directory: Path,
    ) -> None:
        super().__init__(orientation="P", unit="mm", format="Letter")
        self.template = settings
        self.font_directory = font_directory
        self._qr_png: bytes | None = None
        self.family = "LetterBody"
        self.set_margins(
            settings.margin_left_mm,
            settings.margin_top_mm,
            settings.margin_right_mm,
        )
        self.set_auto_page_break(auto=True, margin=max(settings.margin_bottom_mm, 30))
        self.set_title("Academic letter")
        self.set_author("SCESI")
        self._register_fonts()

    def add_page(self, *args, **kwargs):
        if self.page_no() >= MAX_PDF_PAGES:
            raise RenderLimitExceeded("PDF exceeds the page limit")
        return super().add_page(*args, **kwargs)

    def _register_fonts(self) -> None:
        if self.template.body_font == "charis":
            files = {
                "": "Charis-Regular.ttf",
                "B": "Charis-Bold.ttf",
                "I": "Charis-Italic.ttf",
                "BI": "Charis-BoldItalic.ttf",
            }
        else:
            files = {
                "": "LiberationSerif-Regular.ttf",
                "B": "LiberationSerif-Bold.ttf",
                "I": "LiberationSerif-Regular.ttf",
                "BI": "LiberationSerif-Bold.ttf",
            }
        underline_files = {
            "U": files[""],
            "BU": files["B"],
            "IU": files["I"],
            "BIU": files["BI"],
        }
        for style, filename in {**files, **underline_files}.items():
            path = self.font_directory / filename
            if not path.is_file():
                raise FPDFException(f"Bundled font is missing: {filename}")
            self.add_font(self.family, style=style, fname=str(path))
        self.add_font(
            "LetterCode",
            style="",
            fname=str(self.font_directory / "LiberationSans-Regular.ttf"),
        )

    def header(self) -> None:
        self.set_y(7)
        self.set_text_color(75, 75, 75)
        self.set_font(self.family, size=15)
        self.cell(
            0,
            7,
            self.template.university_name,
            align="C",
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )
        self.set_font(self.family, size=12)
        self.cell(
            0,
            6,
            self.template.faculty_name,
            align="C",
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )
        self.set_font(self.family, size=10)
        self.multi_cell(
            0, 5, self.template.organization_name, align="C",
            new_x=XPos.LMARGIN, new_y=YPos.NEXT,
        )
        self.set_draw_color(155, 155, 155)
        self.set_line_width(0.25)
        self.line(20, 28, self.w - 20, 28)
        self.set_text_color(0, 0, 0)

    def footer(self) -> None:
        height = min(self.template.margin_bottom_mm, 32)
        top = self.h - height
        self.set_fill_color(190, 0, 0)
        self.rect(0, top, self.w, height, style="F")
        qr = self._make_qr()
        qr_x = 4
        qr_size = min(height - 6, 21)
        self.set_fill_color(255, 255, 255)
        self.rect(qr_x - 1, top + 3, qr_size + 2, qr_size + 2, style="F")
        self.image(qr, x=qr_x, y=top + 4, w=qr_size, h=qr_size)

        self.set_text_color(255, 255, 255)
        self.set_font(self.family, style="B", size=8.5)
        self.set_xy(29, top + 5)
        self.multi_cell(48, 4.3, str(self.template.footer_url), align="C")
        self.set_x(29)
        self.multi_cell(48, 4.3, str(self.template.footer_email), align="C")

        self.set_font(self.family, size=8)
        self.set_xy(81, top + 5)
        self.multi_cell(78, 4.2, self.template.footer_address, align="C")
        if self.template.city:
            self.set_x(81)
            self.multi_cell(78, 4.2, self.template.city, align="C")

        if self.template.footer_phones:
            self.set_font(self.family, style="B", size=8)
            self.set_xy(161, top + 4)
            self.multi_cell(
                51,
                3.7,
                "Teléfonos:\n" + "\n".join(self.template.footer_phones),
                align="C",
            )
        self.set_text_color(0, 0, 0)

    def _make_qr(self) -> BytesIO:
        if self._qr_png is not None:
            return BytesIO(self._qr_png)
        qr = qrcode.QRCode(version=None, box_size=5, border=1)
        qr.add_data(str(self.template.qr_destination))
        qr.make(fit=True)
        image = qr.make_image(fill_color="black", back_color="white").convert("RGB")
        buffer = BytesIO()
        image.save(buffer, format="PNG", optimize=True)
        self._qr_png = buffer.getvalue()
        return BytesIO(self._qr_png)


class MarkdownPDFRenderer:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._markdown = mistune.create_markdown(
            renderer="ast", plugins=["table", _underline_plugin]
        )

    def render(
        self,
        letter: ParsedLetter,
        template: TemplateSettings,
        created_at: datetime | None = None,
    ) -> bytes:
        pdf = LetterPDF(template, self._settings.FONT_DIRECTORY)
        if created_at is not None:
            pdf.set_creation_date(created_at)
        pdf.add_page()
        self._render_metadata(pdf, letter)
        for centered, block in self._segments(letter.body):
            if block == PAGE_BREAK:
                pdf.add_page()
                continue
            nodes = self._markdown(block)
            self._validate_nodes(nodes)
            self._render_nodes(pdf, nodes, centered=centered)
            if pdf.page_no() > MAX_PDF_PAGES:
                raise RenderLimitExceeded("PDF exceeds the page limit")
        if pdf.page_no() > MAX_PDF_PAGES:
            raise RenderLimitExceeded("PDF exceeds the page limit")
        result = pdf.output()
        if isinstance(result, bytearray):
            return bytes(result)
        return bytes(result)

    @staticmethod
    def _segments(body: str) -> list[tuple[bool, str]]:
        lines = body.splitlines()
        segments: list[tuple[bool, str]] = []
        current: list[str] = []
        centered = False
        code_fence: str | None = None
        for line in lines:
            stripped = line.strip()
            if stripped.startswith(("```", "~~~")):
                marker = stripped[:3]
                if code_fence is None:
                    code_fence = marker
                elif marker == code_fence:
                    code_fence = None
                current.append(line)
                continue
            if code_fence is not None:
                current.append(line)
                continue
            if stripped == CENTER_OPEN:
                if centered:
                    raise InvalidMarkdown("Centered blocks cannot be nested")
                if current:
                    segments.append((False, "\n".join(current)))
                    current = []
                centered = True
                continue
            if stripped == CENTER_CLOSE and centered:
                if current:
                    segments.append((True, "\n".join(current)))
                    current = []
                centered = False
                continue
            if stripped == PAGE_BREAK:
                if centered:
                    raise InvalidMarkdown("Page breaks are not allowed inside centered blocks")
                if current:
                    segments.append((False, "\n".join(current)))
                    current = []
                segments.append((False, PAGE_BREAK))
                continue
            current.append(line)
        if centered:
            raise InvalidMarkdown("Centered block is not closed")
        if current:
            segments.append((False, "\n".join(current)))
        return [(center, text) for center, text in segments if text.strip()]

    @classmethod
    def _validate_nodes(cls, nodes: list[dict[str, object]]) -> None:
        forbidden = {"block_html", "inline_html", "image", "block_error"}
        for node in nodes:
            kind = node.get("type")
            if kind in forbidden:
                raise InvalidMarkdown("Raw HTML and embedded images are unsupported")
            children = node.get("children")
            if isinstance(children, list):
                cls._validate_nodes(children)

    def _render_metadata(self, pdf: LetterPDF, letter: ParsedLetter) -> None:
        metadata = letter.metadata
        if pdf.template.date_format == "long_es":
            months = (
                "enero", "febrero", "marzo", "abril", "mayo", "junio",
                "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
            )
            date_text = (
                f"{pdf.template.city + ', ' if pdf.template.city else ''}"
                f"{metadata.date.day} de {months[metadata.date.month - 1]} de {metadata.date.year}"
            )
        else:
            date_text = metadata.date.strftime("%d/%m/%Y")
        pdf.set_font(pdf.family, style="B", size=12)
        pdf.cell(
            0,
            7,
            f"{metadata.document_type}  {date_text}",
            align="R",
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )
        if metadata.identifier:
            pdf.set_font(pdf.family, style="B", size=13)
            pdf.cell(
                0,
                7,
                metadata.identifier,
                align="R",
                new_x=XPos.LMARGIN,
                new_y=YPos.NEXT,
            )
        for label, value in (
            ("Señor(a):", metadata.recipient),
            ("De:", metadata.sender),
        ):
            if value is None:
                continue
            pdf.ln(2)
            pdf.set_font(pdf.family, style="B", size=10)
            pdf.cell(24, 5, label)
            pdf.set_font(pdf.family, size=10)
            party_text = value.name
            if value.role:
                party_text += f" — {value.role}"
            pdf.multi_cell(
                0,
                5,
                party_text,
                new_x=XPos.LMARGIN,
                new_y=YPos.NEXT,
            )
        if metadata.reference:
            pdf.ln(2)
            pdf.set_font(pdf.family, style="B", size=10)
            pdf.cell(24, 5, "Ref.:")
            pdf.set_font(pdf.family, size=10)
            pdf.multi_cell(0, 5, metadata.reference)
        if metadata.salutation:
            pdf.ln(4)
            pdf.set_font(pdf.family, size=11)
            pdf.multi_cell(0, 6, metadata.salutation)
            pdf.ln(2)
        pdf.set_font(pdf.family, size=pdf.template.body_font_size)

    def _render_nodes(
        self,
        pdf: LetterPDF,
        nodes: list[dict[str, object]],
        centered: bool = False,
    ) -> None:
        for node in nodes:
            kind = str(node.get("type", ""))
            children_value = node.get("children", [])
            children = children_value if isinstance(children_value, list) else []
            if kind in {"blank_line", "thematic_break"}:
                if kind == "thematic_break":
                    pdf.ln(3)
                    pdf.set_draw_color(175, 175, 175)
                    pdf.line(pdf.get_x(), pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
                    pdf.ln(4)
                continue
            if kind == "heading":
                level = int((node.get("attrs") or {}).get("level", 2))
                pdf.ln(2)
                pdf.set_font(pdf.family, style="B", size=max(12, 17 - level * 1.3))
                if centered:
                    pdf.multi_cell(
                        0, 6, _plain_text(children), align="C",
                        new_x=XPos.LMARGIN, new_y=YPos.NEXT,
                    )
                else:
                    self._write_inline(pdf, children, centered=False, style="B")
                    pdf.ln(7)
                pdf.set_font(pdf.family, size=pdf.template.body_font_size)
                continue
            if kind in {"paragraph", "block_text"}:
                pdf.set_font(pdf.family, size=pdf.template.body_font_size)
                pdf.set_x(pdf.l_margin + (5 if node.get("type") == "block_text" else 0))
                if centered:
                    pdf.multi_cell(
                        0, 6, _plain_text(children), align="C",
                        new_x=XPos.LMARGIN, new_y=YPos.NEXT,
                    )
                else:
                    self._write_inline(pdf, children, centered=False)
                pdf.ln(6)
                continue
            if kind == "list":
                attrs = node.get("attrs") or {}
                ordered = bool(attrs.get("ordered", False))
                for index, item in enumerate(children, start=1):
                    item_children = item.get("children", [])
                    if not isinstance(item_children, list):
                        continue
                    pdf.set_x(pdf.l_margin + 5)
                    pdf.set_font(pdf.family, size=pdf.template.body_font_size)
                    marker = f"{index}. " if ordered else "• "
                    pdf.write(6, marker)
                    self._render_nodes(pdf, item_children, centered=centered)
                pdf.ln(2)
                continue
            if kind == "block_code":
                code = str(node.get("raw", ""))
                pdf.set_fill_color(245, 245, 245)
                pdf.set_font("LetterCode", size=9)
                pdf.multi_cell(0, 4.5, code.rstrip(), fill=True)
                pdf.ln(3)
                pdf.set_font(pdf.family, size=pdf.template.body_font_size)
                continue
            if kind == "block_quote":
                quote_text = _plain_text(children)
                pdf.set_x(pdf.l_margin + 5)
                pdf.set_draw_color(160, 160, 160)
                start_y = pdf.get_y()
                pdf.multi_cell(
                    pdf.epw - 10,
                    6,
                    quote_text,
                    border="L",
                    padding=(0, 0, 0, 3),
                )
                pdf.line(pdf.l_margin + 3, start_y, pdf.l_margin + 3, pdf.get_y())
                pdf.ln(3)
                continue
            if kind == "table":
                self._render_table(pdf, children)
                pdf.ln(4)

    def _render_table(self, pdf: LetterPDF, sections: list[dict[str, object]]) -> None:
        rows: list[list[tuple[str, bool]]] = []
        for section in sections:
            section_children = section.get("children", [])
            if not isinstance(section_children, list):
                continue
            if section.get("type") == "table_head":
                rows.append(
                    [
                        (_plain_text(cell.get("children", [])), True)
                        for cell in section_children
                        if isinstance(cell, dict)
                    ]
                )
                continue
            for row in section_children:
                if not isinstance(row, dict):
                    continue
                cells = row.get("children", [])
                if not isinstance(cells, list):
                    continue
                rows.append(
                    [
                        (
                            _plain_text(cell.get("children", [])),
                            bool((cell.get("attrs") or {}).get("head", False)),
                        )
                        for cell in cells
                    ]
                )
        if not rows:
            return
        columns = max(len(row) for row in rows)
        width = pdf.epw / columns
        for row in rows:
            cells = [row[index] if index < len(row) else ("", False) for index in range(columns)]
            heights: list[float] = []
            for text, is_header in cells:
                pdf.set_font(pdf.family, style="B" if is_header else "", size=9)
                height = pdf.multi_cell(
                    width,
                    5,
                    text,
                    dry_run=True,
                    output=MethodReturnValue.HEIGHT,
                    padding=1,
                )
                heights.append(float(height))
            row_height = max(heights, default=5.0)
            if pdf.will_page_break(row_height):
                pdf.add_page()
            row_y = pdf.get_y()
            for index, (text, is_header) in enumerate(cells):
                pdf.set_xy(pdf.l_margin + index * width, row_y)
                pdf.set_font(pdf.family, style="B" if is_header else "", size=9)
                pdf.multi_cell(
                    width,
                    5,
                    text,
                    border=1,
                    new_x=XPos.RIGHT,
                    new_y=YPos.TOP,
                    max_line_height=5,
                    padding=1,
                )
            pdf.set_xy(pdf.l_margin, row_y + row_height)

    def _write_inline(
        self,
        pdf: LetterPDF,
        nodes: list[dict[str, object]],
        centered: bool,
        style: str = "",
    ) -> None:
        original_x = pdf.get_x()
        original_style = style
        for node in nodes:
            kind = node.get("type")
            if kind in {"text", "inline_code", "codespan"}:
                raw = str(node.get("raw", ""))
                if kind in {"inline_code", "codespan"}:
                    pdf.set_font("LetterCode", size=9)
                else:
                    pdf.set_font(pdf.family, style=style, size=pdf.template.body_font_size)
                pdf.write(6, raw)
            elif kind in {"strong", "emphasis", "strikethrough", "link", "underline"}:
                next_style = style
                if kind == "strong":
                    next_style = "".join(letter for letter in "BIU" if letter in style or letter == "B")
                elif kind == "emphasis":
                    next_style = "".join(letter for letter in "BIU" if letter in style or letter == "I")
                elif kind == "underline":
                    next_style = "".join(letter for letter in "BIU" if letter in style or letter == "U")
                children = node.get("children", [])
                if isinstance(children, list):
                    self._write_inline(pdf, children, centered, next_style)
            elif kind in {"softbreak", "linebreak"}:
                pdf.ln(6)
                if centered:
                    pdf.set_x(original_x)
            elif kind == "image":
                raise InvalidMarkdown("Embedded images are unsupported")
        pdf.set_font(pdf.family, style=original_style, size=pdf.template.body_font_size)
