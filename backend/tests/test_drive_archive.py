import asyncio
import httpx
import pytest
from types import SimpleNamespace

from app.modules.integration.archive import DriveAPI, _category, _safe_segment
from app.modules.integration.archive_schemas import ArchiveRetryRequest
from pydantic import ValidationError


def test_upload_timeout_reconciles_before_creating_another_file() -> None:
    calls: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.method)
        if request.method == "POST":
            raise httpx.ReadTimeout("simulated response loss")
        if len(calls) == 1:
            return httpx.Response(200, json={"files": []})
        return httpx.Response(200, json={"files": [{"id": "drive-file-1"}]})

    api = DriveAPI("synthetic-token", httpx.MockTransport(handler))
    result = asyncio.run(api.upload_immutable(
        "parent", "SOL-SCESI-2026-001-v0001.md", "markdown",
        "document-id", "version-id", b"synthetic markdown", "a" * 64,
    ))

    assert result == "drive-file-1"
    assert calls == ["GET", "POST", "GET"]
    assert "DELETE" not in calls
    assert "PATCH" not in calls


def test_archive_categories_require_classification_for_unknown_type() -> None:
    job = SimpleNamespace(topic_category_override=None)
    assert _category(job, SimpleNamespace(document_type="INV")) == "invitations"
    assert _category(job, SimpleNamespace(document_type="SOL", metadata=SimpleNamespace(topic="Petición de aula"))) == "classrooms"
    general = SimpleNamespace(document_type="GEN")
    assert _category(job, general) is None
    job.topic_category_override = "miscellaneous"
    assert _category(job, general) == "miscellaneous"


def test_miscellaneous_requires_user_confirmation() -> None:
    with pytest.raises(ValidationError):
        ArchiveRetryRequest(topic_category="miscellaneous")
    assert ArchiveRetryRequest(topic_category="miscellaneous", confirm_miscellaneous=True)


def test_folder_display_names_are_sanitized_and_bounded() -> None:
    assert _safe_segment("  jornada/2026?  ") == "jornada-2026"
    assert len(_safe_segment("x" * 500)) == 100
