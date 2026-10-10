from datetime import date
from io import BytesIO

from PIL import Image
import pytest

from app.core.config import Settings
from app.modules.document.markdown_source import ParsedLetter
from app.modules.document.pdf_renderer import (
    MarkdownPDFRenderer,
    SignatureDoesNotFit,
)
from app.modules.document.schemas import LetterMetadata
from app.modules.signature.services import hash_signing_token
from app.modules.template.services import TemplateService


def tiny_png() -> bytes:
    output = BytesIO()
    Image.new("RGBA", (16, 8), (0, 0, 0, 255)).save(output, format="PNG")
    return output.getvalue()


def sample_letter(body: str = "Solicitud académica.") -> ParsedLetter:
    return ParsedLetter(
        metadata=LetterMetadata(
            document_type="SOL",
            identifier="SOL-SCESI-2026-001",
            date=date(2026, 10, 10),
            signoff="Atentamente",
        ),
        body=body,
    )


def test_signed_pdf_embeds_png_without_persisting_it() -> None:
    settings = Settings()
    template = TemplateService.initial_settings(settings)
    pdf = MarkdownPDFRenderer(settings).render(
        sample_letter(), template, signature_png=tiny_png()
    )

    assert pdf.startswith(b"%PDF-")
    assert b"/Subtype /Image" in pdf


def test_signature_is_rejected_when_fixed_slot_overlaps_letter_body() -> None:
    settings = Settings()
    template = TemplateService.initial_settings(settings)
    body = "\n\n".join(f"Paragraph {index}." for index in range(30))

    with pytest.raises(SignatureDoesNotFit):
        MarkdownPDFRenderer(settings).render(
            sample_letter(body), template, signature_png=tiny_png()
        )


def test_signing_token_hash_never_equals_raw_token() -> None:
    token = "random-authorization-token"

    assert token != hash_signing_token(token)
