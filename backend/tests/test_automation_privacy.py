import asyncio
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import SecretStr

from app.core.config import Settings
from app.modules.automation.graph import (
    LetterAssistanceService,
    _execute_tools,
    _locate_original,
    _parse_suggestions,
    _validate,
    build_graph,
)
from app.modules.automation.privacy import LocalPrivacyFilter
from app.modules.automation.provider import Completion, ToolCall
from app.modules.automation.quota import QuotaService, parse_reset_duration
from app.modules.contact.documents import ContactDocument


class FakeContactsQuery:
    def limit(self, _count):
        return self

    async def to_list(self, length=None):
        return [
            {"name": "María López", "role_key": "director_carrera"},
            {"name": "Carlos Rojas", "role_key": "director_carrera"},
        ]


class FakeContactCollection:
    def find(self, _query, _projection=None):
        return FakeContactsQuery()


class FakeQuota:
    async def reserve(self, estimated_input, output_budget):
        return SimpleNamespace(id=uuid4())

    async def settle(self, *args, **kwargs):
        return None


class PrivacySpyAdapter:
    def __init__(self):
        self.messages = []
        self.call_count = 0

    async def complete(self, *, messages, tools=None, json_output=False):
        self.messages.append(messages)
        self.call_count += 1
        if self.call_count == 1:
            return Completion(
                content=None,
                tool_calls=(
                    ToolCall(
                        "call-exact-7",
                        "lookup_role_count",
                        '{"role_key":"director_carrera"}',
                    ),
                ),
                usage_input_tokens=150,
                usage_output_tokens=20,
                headers={},
            )
        tool_result = next(
            message for message in messages if message.get("role") == "tool"
        )
        assert tool_result["tool_call_id"] == "call-exact-7"
        assert "María López" not in tool_result["content"]
        user_data = json.loads(messages[1]["content"])
        body = user_data["redacted_letter_body"]
        start = body.index("reunion")
        return Completion(
            content=json.dumps(
                {
                    "suggestions": [
                        {
                            "kind": "grammar",
                            "original": "reunion",
                            "replacement": "reunión",
                            "start": start,
                            "end": start + len("reunion"),
                            "reason": "Mejora la acentuación.",
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            tool_calls=(),
            usage_input_tokens=200,
            usage_output_tokens=50,
            headers={},
        )


def test_spanish_private_names_and_identifiers_are_redacted_locally():
    privacy = LocalPrivacyFilter()
    result = privacy.redact(
        "El director Juan Pérez envía su nota al correo juan@example.edu "
        "y pide el aula.",
        ["María López"],
    )
    assert "Juan Pérez" not in result.text
    assert "juan@example.edu" not in result.text
    assert "[PERSON_1]" in result.text
    assert "[EMAIL_1]" in result.text
    assert result.map_range(result.text.index("aula"), result.text.index("aula") + 4)
    assert (
        result.map_range(
            result.text.index("[PERSON_1]"), result.text.index("[PERSON_1]") + 10
        )
        is None
    )


def test_langgraph_provider_only_receives_redacted_body_and_role_counts(monkeypatch):
    monkeypatch.setattr(
        ContactDocument, "get_pymongo_collection", lambda: FakeContactCollection()
    )
    adapter = PrivacySpyAdapter()
    settings = Settings(
        LLM_PROVIDER="groq",
        GROQ_API_KEY=SecretStr("synthetic-test-key"),
        LLM_MAX_OUTPUT_TOKENS=750,
    )
    document = SimpleNamespace(
        id=uuid4(),
        source_hash="a" * 64,
        body="El director Juan Pérez solicita una aula para la reunion academica.",
        document_type="SOL",
        metadata=SimpleNamespace(
            sender=SimpleNamespace(name="Carlos Rojas"),
            recipient=SimpleNamespace(name="Juan Pérez"),
        ),
    )
    result = asyncio.run(
        build_graph().ainvoke(
            {
                "document": document,
                "requested_kinds": ["grammar"],
                "adapter": adapter,
                "quota": FakeQuota(),
                "settings": settings,
                "privacy": LocalPrivacyFilter(),
                "messages": [],
                "analysis_budget": [0],
                "retry_budget": [0],
            }
        )
    )

    provider_transcript = json.dumps(adapter.messages, ensure_ascii=False)
    assert "Juan Pérez" not in provider_transcript
    assert "Carlos Rojas" not in provider_transcript
    assert "María López" not in provider_transcript
    second_pass_tool_result = next(
        item for item in adapter.messages[1] if item.get("role") == "tool"
    )
    assert json.loads(second_pass_tool_result["content"]) == {
        "role_key": "director_carrera",
        "match_count": 2,
    }
    assert result["suggestions"] == [
        {
            "kind": "grammar",
            "original": "reunion",
            "replacement": "reunión",
            "start": document.body.index("reunion"),
            "end": document.body.index("reunion") + len("reunion"),
            "reason": "Mejora la acentuación.",
        }
    ]


def test_provider_reset_headers_are_parsed_as_durations():
    assert parse_reset_duration("1h2m3.2s") == 3724
    assert parse_reset_duration("60s") == 60


def test_private_name_cannot_leak_through_a_custom_role_key():
    privacy = LocalPrivacyFilter()
    assert not privacy.validate_public_text("juan perez", ["Juan Pérez"])


def test_manual_redaction_masks_the_selected_unicode_source_range():
    privacy = LocalPrivacyFilter()
    body = "Para María: préstamo de sala."
    start = len("Para ")
    end = start + len("María")
    redacted = privacy.redact(body, [], [(start, end)])

    assert "María" not in redacted.text
    assert redacted.map_range(0, len("Para ")) == (0, len("Para "))
    assert redacted.map_range(start, start + len("[ENTITY_1]")) is None


def test_privacy_confirmation_token_binds_user_source_tasks_and_redaction():
    service = object.__new__(LetterAssistanceService)
    service._settings = Settings(
        AI_PREVIEW_SIGNING_KEY=SecretStr(
            "synthetic-preview-signing-key-for-tests-only"
        ),
    )
    document = SimpleNamespace(id=uuid4(), source_hash="b" * 64)
    user_id = uuid4()
    kinds = ["grammar"]
    redacted = LocalPrivacyFilter().redact("Juan Pérez pide un aula.", [])
    from datetime import UTC, datetime, timedelta

    from app.modules.automation.schemas import RedactionRange

    expires_at = datetime.now(UTC) + timedelta(minutes=5)
    manual_redactions = [RedactionRange(start=0, end=4)]
    token = service._preview_token(
        document, user_id, kinds, redacted, expires_at, manual_redactions
    )

    service._verify_preview(
        token, document, user_id, kinds, redacted, manual_redactions
    )
    with pytest.raises(HTTPException) as error:
        service._verify_preview(
            token, document, uuid4(), kinds, redacted, manual_redactions
        )
    assert error.value.detail == "PRIVACY_PREVIEW_EXPIRED"
    with pytest.raises(HTTPException):
        service._verify_preview(
            token, document, user_id, ["style"], redacted, manual_redactions
        )


def test_older_provider_headers_cannot_increase_shared_remaining_budget():
    from datetime import UTC, datetime, timedelta

    now = datetime.now(UTC)
    gate = SimpleNamespace(
        header_tpm_remaining=5,
        header_tpm_observed_at=now,
        header_tpm_reset_at=now + timedelta(seconds=60),
        header_rpd_remaining=None,
        header_rpd_observed_at=None,
        header_rpd_reset_at=None,
    )
    QuotaService._tighten_header(
        gate,
        {
            "x-ratelimit-remaining-tokens": "5000",
            "x-ratelimit-reset-tokens": "2m",
        },
        now - timedelta(seconds=5),
        now,
    )
    assert gate.header_tpm_remaining == 5


def test_unknown_tool_calls_are_rejected_without_dynamic_execution():
    class UnsafeToolCall:
        id = "tool-injection-1"
        name = "python_exec"
        arguments = '{"code":"open(\'/etc/passwd\')"}'

    result = asyncio.run(
        _execute_tools(
            {
                "pending_tool_calls": (UnsafeToolCall(),),
                "tool_call_count": 0,
                "messages": [],
                "role_counts": {},
            }
        )
    )
    tool_result = result["tool_messages"][0]
    assert tool_result["tool_call_id"] == "tool-injection-1"
    assert json.loads(tool_result["content"]) == {"error": "tool_not_allowed"}


def test_suggestion_range_is_recovered_only_from_an_unambiguous_original():
    text = "solisitamos una aula y solisitamos permiso para realisar"
    unique = text.index("realisar")
    second = text.index("solisitamos", 1)

    assert _locate_original(text, "realisar", None, None) == (unique, len(text))
    assert _locate_original(text, "realisar", 0, 3) == (unique, len(text))
    assert _locate_original(text, "solisitamos", second, second + 11) == (second, second + 11)
    assert _locate_original(text, "solisitamos", None, None) is None
    assert _locate_original(text, "ausente", None, None) is None
    assert _locate_original(text, "", 0, 0) is None


def test_model_output_keeps_valid_suggestions_and_drops_malformed_ones():
    content = json.dumps(
        {
            "suggestions": [
                {"kind": "grammar", "original": "reunion", "replacement": "reunión",
                 "field": "grammar", "start": 3, "end": 9, "reason": "Falta la tilde."},
                {"kind": "grammar", "original": "aula", "replacement": "sala",
                 "reason": "Es más preciso.", "confidence": 0.9},
                {"kind": "topic", "field": "topic", "replacement": "Solicitud de aula",
                 "reason": "Resume el pedido."},
                "not an object",
            ]
        }
    )

    parsed = _parse_suggestions(content)

    assert [(item["kind"], item["field"]) for item in parsed] == [
        ("grammar", None),
        ("topic", "topic"),
    ]
    for invalid in ("", "[]", '{"suggestions": "none"}'):
        with pytest.raises(HTTPException) as raised:
            _parse_suggestions(invalid)
        assert raised.value.detail == "LLM_INVALID_RESPONSE"


def test_private_reason_is_replaced_without_discarding_the_suggestion():
    privacy = LocalPrivacyFilter()
    redacted = privacy.redact("Solicitamos una aula para la reunion academica.", [])
    state = {
        "redacted": redacted,
        "privacy": privacy,
        "private_names": ["Juan Pérez"],
        "requested_kinds": ["grammar"],
        "role_counts": {},
        "suggestions": [
            {"kind": "grammar", "original": "reunion", "replacement": "reunión",
             "field": None, "start": None, "end": None,
             "reason": "Juan Pérez pidió corregir la tilde."},
        ],
    }

    accepted = _validate(state)["suggestions"]

    assert [(item["original"], item["replacement"]) for item in accepted] == [("reunion", "reunión")]
    assert "Juan" not in accepted[0]["reason"]

