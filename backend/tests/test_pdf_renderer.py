import pytest

from app.core.config import Settings
from app.modules.document.pdf_renderer import LetterPDF
from app.modules.template.services import TemplateService


def test_letter_body_starts_at_top_margin_below_repeated_header() -> None:
    settings = Settings()
    template = TemplateService.initial_settings(settings)
    pdf = LetterPDF(template, settings.FONT_DIRECTORY)

    for _ in range(2):
        pdf.add_page()
        assert pdf.get_y() == pytest.approx(template.margin_top_mm)
