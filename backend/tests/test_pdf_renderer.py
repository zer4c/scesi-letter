import pytest

from app.core.config import Settings
from app.modules.document.pdf_renderer import (
    PARAGRAPH_GAP_MM,
    LetterPDF,
    MarkdownPDFRenderer,
)
from app.modules.template.services import TemplateService


def blank_page() -> tuple[MarkdownPDFRenderer, LetterPDF]:
    settings = Settings()
    template = TemplateService.initial_settings(settings)
    pdf = LetterPDF(template, settings.FONT_DIRECTORY)
    pdf.add_page()
    pdf.set_font(pdf.family, size=template.body_font_size)
    return MarkdownPDFRenderer(settings), pdf


def test_letter_body_starts_at_top_margin_below_repeated_header() -> None:
    settings = Settings()
    template = TemplateService.initial_settings(settings)
    pdf = LetterPDF(template, settings.FONT_DIRECTORY)

    for _ in range(2):
        pdf.add_page()
        assert pdf.get_y() == pytest.approx(template.margin_top_mm)


def test_paragraphs_are_separated_by_a_gap() -> None:
    renderer, pdf = blank_page()
    start = pdf.get_y()

    renderer._render_nodes(pdf, renderer._markdown("First.\n\nSecond."))

    assert pdf.get_y() == pytest.approx(start + 2 * (6 + PARAGRAPH_GAP_MM))


def test_list_item_text_starts_after_its_marker() -> None:
    renderer, pdf = blank_page()
    left_margin = pdf.l_margin
    written: list[tuple[float, str]] = []
    write = pdf.write

    def record(height, text="", *args, **kwargs):
        written.append((pdf.get_x(), text))
        return write(height, text, *args, **kwargs)

    pdf.write = record
    renderer._render_nodes(pdf, renderer._markdown("- One\n- Two"))

    assert [text for _, text in written] == ["• ", "One", "• ", "Two"]
    marker_x, text_x = written[0][0], written[1][0]
    assert text_x >= marker_x + pdf.get_string_width("• ")
    assert written[3][0] == pytest.approx(text_x)
    assert pdf.l_margin == pytest.approx(left_margin)


def test_header_logo_is_embedded_when_the_image_exists() -> None:
    settings = Settings()
    template = TemplateService.initial_settings(settings)
    without_logo = LetterPDF(template, settings.FONT_DIRECTORY)
    without_logo.add_page()
    with_logo = LetterPDF(template, settings.FONT_DIRECTORY, settings.IMAGE_DIRECTORY)
    with_logo.add_page()

    image = b"/Subtype /Image"
    assert bytes(with_logo.output()).count(image) > bytes(without_logo.output()).count(image)
