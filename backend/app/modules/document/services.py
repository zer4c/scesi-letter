import hashlib

from app.core.config import Settings
from app.modules.document.markdown_source import parse_markdown_source
from app.modules.document.pdf_renderer import MarkdownPDFRenderer
from app.modules.template.schemas import TemplateSettings


class DocumentRenderService:
    def __init__(self, settings: Settings) -> None:
        self._renderer = MarkdownPDFRenderer(settings)

    def preview(
        self,
        markdown: str,
        template: TemplateSettings,
    ) -> tuple[bytes, str]:
        letter = parse_markdown_source(markdown)
        content = self._renderer.render(letter, template)
        return content, hashlib.sha256(content).hexdigest()
