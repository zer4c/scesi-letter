import asyncio
import base64
import hashlib
import hmac
import json
import secrets
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, TypedDict

from fastapi import HTTPException
from groq import APIStatusError
from langgraph.graph import END, StateGraph
from pydantic import ValidationError

from app.core.config import Settings
from app.modules.automation.documents import LetterSuggestionDocument
from app.modules.automation.privacy import (
    LocalPrivacyFilter,
    PrivacyReviewRequired,
    RedactedText,
)
from app.modules.automation.provider import (
    Completion,
    CompletionAdapter,
    GroqCompletionAdapter,
)
from app.modules.automation.quota import (
    QuotaExceeded,
    QuotaService,
    parse_reset_duration,
)
from app.modules.automation.schemas import (
    ListDocumentTypesInput,
    ModelOutput,
    RedactionRange,
    RoleLookupInput,
    SuggestionKind,
)
from app.modules.contact.documents import ContactDocument
from app.modules.document.documents import LetterDocument

PROMPT_VERSION = "v1"
PROMPT_PATH = Path(__file__).parent / "prompts" / "v1.md"
MAX_TOOL_CALLS = 3
MAX_CONTACT_PRIVACY_RECORDS = 10_000
ALLOWED_KINDS = {
    "grammar",
    "style",
    "reference",
    "document_type",
    "topic",
    "recipient_role",
}


class AnalysisState(TypedDict, total=False):
    document: LetterDocument
    requested_kinds: list[SuggestionKind]
    adapter: CompletionAdapter
    quota: QuotaService
    settings: Settings
    privacy: LocalPrivacyFilter
    private_names: list[str]
    role_counts: dict[str, int]
    redacted: RedactedText
    messages: list[dict[str, Any]]
    tool_messages: list[dict[str, Any]]
    tool_call_count: int
    pending_tool_calls: tuple
    analysis_budget: list[int]
    retry_budget: list[int]
    suggestions: list[dict[str, Any]]


def _token_estimate(
    messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None
) -> int:
    serialized = json.dumps({"messages": messages, "tools": tools}, ensure_ascii=False)
    return max(1, (len(serialized) + 2) // 3)


def _tool_definitions(role_keys: list[str]) -> list[dict[str, Any]]:
    role_schema = RoleLookupInput.model_json_schema()
    role_schema["properties"]["role_key"]["enum"] = role_keys
    tools = [
        {
            "type": "function",
            "function": {
                "name": "list_document_types",
                "description": "Return allowed academic letter type codes.",
                "parameters": ListDocumentTypesInput.model_json_schema(),
            },
        }
    ]
    if role_keys:
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": "lookup_role_count",
                    "description": (
                        "Return only the local number of contacts matching "
                        "an approved role key."
                    ),
                    "parameters": role_schema,
                },
            }
        )
    return tools


async def _privacy_material(
    document: LetterDocument,
    privacy: LocalPrivacyFilter,
    manual_redactions: list[RedactionRange] | None = None,
):
    collection = ContactDocument.get_pymongo_collection()
    contacts = (
        await collection.find({"active": True}, {"name": 1, "role_key": 1})
        .limit(MAX_CONTACT_PRIVACY_RECORDS + 1)
        .to_list(length=MAX_CONTACT_PRIVACY_RECORDS + 1)
    )
    if len(contacts) > MAX_CONTACT_PRIVACY_RECORDS:
        raise HTTPException(status_code=503, detail="LOCAL_PRIVACY_DIRECTORY_LIMIT")
    private_names = []
    for party in (document.metadata.sender, document.metadata.recipient):
        if party is not None:
            private_names.append(party.name)
    private_names.extend(contact["name"] for contact in contacts if contact.get("name"))
    try:
        redacted = privacy.redact(
            document.body,
            private_names,
            [(item.start, item.end) for item in manual_redactions or []],
        )
    except PrivacyReviewRequired as error:
        raise HTTPException(status_code=422, detail=error.code) from error
    role_counts: dict[str, int] = {}
    for contact in contacts:
        role_key = contact.get("role_key")
        if role_key and privacy.validate_public_text(
            role_key.replace("_", " "), private_names
        ):
            role_counts[role_key] = role_counts.get(role_key, 0) + 1
    return redacted, role_counts, private_names


async def _prepare(state: AnalysisState) -> dict[str, Any]:
    document = state["document"]
    redacted = state.get("redacted")
    role_counts = state.get("role_counts")
    private_names = state.get("private_names")
    if redacted is None or role_counts is None or private_names is None:
        redacted, role_counts, private_names = await _privacy_material(
            document, state["privacy"]
        )
    requested_kinds = ", ".join(state["requested_kinds"])
    system_prompt = PROMPT_PATH.read_text(encoding="utf-8")
    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": json.dumps(
                {
                    "requested_suggestion_kinds": requested_kinds,
                    "known_role_keys_and_match_counts": role_counts,
                    "redacted_letter_body": redacted.text,
                },
                ensure_ascii=False,
            ),
        },
    ]
    return {
        "redacted": redacted,
        "role_counts": role_counts,
        "private_names": private_names,
        "messages": messages,
        "tool_messages": [],
        "tool_call_count": 0,
    }


async def _call_provider(
    state: AnalysisState, *, tools=None, json_output=False
) -> Completion:
    settings = state["settings"]
    messages = state["messages"]
    estimate = _token_estimate(messages, tools)
    if estimate > settings.LLM_MAX_INPUT_TOKENS:
        raise HTTPException(status_code=413, detail="LLM_INPUT_TOO_LARGE")
    output_budget = settings.LLM_MAX_OUTPUT_TOKENS
    if estimate + output_budget > settings.LLM_MAX_ANALYSIS_TOKENS:
        raise HTTPException(status_code=413, detail="LLM_ANALYSIS_BUDGET_EXCEEDED")
    analysis_budget = state["analysis_budget"]
    if analysis_budget[0] + estimate + output_budget > settings.LLM_MAX_ANALYSIS_TOKENS:
        raise HTTPException(status_code=429, detail="LLM_ANALYSIS_BUDGET_EXCEEDED")
    deadline = time.monotonic() + settings.LLM_REQUEST_TIMEOUT_SECONDS
    while True:
        try:
            reservation = await state["quota"].reserve(estimate, output_budget)
            analysis_budget[0] += estimate + output_budget
        except QuotaExceeded as error:
            raise HTTPException(
                status_code=429,
                detail="LLM_RATE_LIMITED",
                headers={"Retry-After": str(error.retry_after)},
            ) from error
        try:
            request_started_at = datetime.now(UTC)
            completion = await asyncio.wait_for(
                state["adapter"].complete(
                    messages=messages,
                    tools=tools,
                    json_output=json_output,
                ),
                timeout=max(0.1, deadline - time.monotonic()),
            )
        except TimeoutError:
            await state["quota"].settle(
                reservation.id,
                None,
                None,
                {},
                uncertain=True,
                observed_at=request_started_at,
            )
            raise HTTPException(status_code=503, detail="LLM_OUTCOME_UNCERTAIN")
        except APIStatusError as error:
            headers = {
                str(key).casefold(): str(value)
                for key, value in error.response.headers.items()
            }
            await state["quota"].settle(
                reservation.id,
                None,
                None,
                headers,
                uncertain=True,
                observed_at=request_started_at,
            )
            if (
                error.status_code == 429
                and state["retry_budget"][0] < settings.LLM_MAX_RETRIES
            ):
                retry_value = headers.get("retry-after")
                if retry_value:
                    try:
                        wait_seconds = max(1, int(float(retry_value)))
                    except ValueError:
                        try:
                            wait_seconds = parse_reset_duration(retry_value)
                        except ValueError:
                            wait_seconds = 0
                    if wait_seconds and time.monotonic() + wait_seconds < deadline:
                        await asyncio.sleep(wait_seconds)
                        state["retry_budget"][0] += 1
                        continue
            if error.status_code == 429:
                raise HTTPException(
                    status_code=429,
                    detail="LLM_RATE_LIMITED",
                    headers={"Retry-After": headers.get("retry-after", "60")},
                ) from error
            if (
                error.status_code >= 500
                and state["retry_budget"][0] < settings.LLM_MAX_RETRIES
            ):
                state["retry_budget"][0] += 1
                await asyncio.sleep(min(2 ** state["retry_budget"][0], 2))
                continue
            raise HTTPException(status_code=502, detail="LLM_PROVIDER_ERROR") from error
        except Exception as error:
            await state["quota"].settle(
                reservation.id,
                None,
                None,
                {},
                uncertain=True,
                observed_at=request_started_at,
            )
            raise HTTPException(
                status_code=502, detail="LLM_PROVIDER_UNAVAILABLE"
            ) from error
        await state["quota"].settle(
            reservation.id,
            completion.usage_input_tokens,
            completion.usage_output_tokens,
            completion.headers,
            observed_at=request_started_at,
        )
        return completion


async def _tool_pass(state: AnalysisState) -> dict[str, Any]:
    definitions = _tool_definitions(sorted(state["role_counts"]))
    completion = await _call_provider(state, tools=definitions)
    calls = completion.tool_calls
    assistant_message: dict[str, Any] = {
        "role": "assistant",
        "content": completion.content,
    }
    if calls:
        assistant_message["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {
                    "name": call.name,
                    "arguments": call.arguments,
                },
            }
            for call in calls
        ]
    return {
        "messages": [*state["messages"], assistant_message],
        "pending_tool_calls": calls,
    }


async def _execute_tools(state: AnalysisState) -> dict[str, Any]:
    calls = state.get("pending_tool_calls", ())
    if len(calls) + state.get("tool_call_count", 0) > MAX_TOOL_CALLS:
        raise HTTPException(status_code=502, detail="LLM_TOOL_BUDGET_EXCEEDED")
    tool_messages = []
    for call in calls:
        try:
            arguments = json.loads(call.arguments or "{}")
        except (TypeError, json.JSONDecodeError):
            arguments = None
        result: dict[str, Any]
        if call.name == "list_document_types":
            try:
                ListDocumentTypesInput.model_validate(arguments)
            except ValidationError:
                result = {"error": "invalid_tool_arguments"}
            else:
                result = {
                    "document_types": [
                        "INV",
                        "SOL",
                        "MEM",
                        "ACT",
                        "PRES",
                        "CIRC",
                        "NOT",
                        "GEN",
                    ]
                }
        elif call.name == "lookup_role_count" and isinstance(arguments, dict):
            try:
                valid = RoleLookupInput.model_validate(arguments)
            except ValidationError:
                result = {"error": "invalid_tool_arguments"}
            else:
                role_key = valid.role_key
                if role_key in state["role_counts"]:
                    result = {
                        "role_key": role_key,
                        "match_count": state["role_counts"][role_key],
                    }
                else:
                    result = {"error": "invalid_role_key"}
        else:
            result = {"error": "tool_not_allowed"}
        tool_messages.append(
            {
                "role": "tool",
                "tool_call_id": call.id,
                "content": json.dumps(result, ensure_ascii=False),
            }
        )
    return {
        "messages": [*state["messages"], *tool_messages],
        "tool_messages": tool_messages,
        "tool_call_count": state.get("tool_call_count", 0) + len(calls),
    }


async def _synthesize(state: AnalysisState) -> dict[str, Any]:
    messages = [
        *state["messages"],
        {
            "role": "system",
            "content": (
                'Return only a JSON object matching {"suggestions": [...]}. '
                "Do not request or invoke tools in this pass."
            ),
        },
    ]
    completion = await _call_provider(state | {"messages": messages}, json_output=True)
    try:
        output = ModelOutput.model_validate_json(completion.content or "")
    except (ValidationError, ValueError) as error:
        raise HTTPException(status_code=502, detail="LLM_INVALID_RESPONSE") from error
    return {"suggestions": [item.model_dump() for item in output.suggestions]}


def _validate(state: AnalysisState) -> dict[str, Any]:
    redacted = state["redacted"]
    privacy = state["privacy"]
    accepted = []
    for item in state.get("suggestions", []):
        kind = item.get("kind")
        if kind not in ALLOWED_KINDS or kind not in state["requested_kinds"]:
            continue
        reason = item.get("reason", "")
        replacement = item.get("replacement")
        if not privacy.validate_public_text(reason, state["private_names"]):
            continue
        if kind in {"grammar", "style", "reference"}:
            start, end = item.get("start"), item.get("end")
            if not isinstance(start, int) or not isinstance(end, int):
                continue
            mapped = redacted.map_range(start, end)
            if mapped is None or item.get("original") != redacted.text[start:end]:
                continue
            if not isinstance(replacement, str) or not privacy.validate_public_text(
                replacement, state["private_names"]
            ):
                continue
            source_start, source_end = mapped
            accepted.append(
                {
                    "kind": kind,
                    "original": redacted.source[source_start:source_end],
                    "replacement": replacement,
                    "start": source_start,
                    "end": source_end,
                    "reason": reason,
                }
            )
        elif kind == "document_type":
            if item.get("field") != "document_type" or replacement not in {
                "INV",
                "SOL",
                "MEM",
                "ACT",
                "PRES",
                "CIRC",
                "NOT",
                "GEN",
            }:
                continue
            accepted.append(
                {
                    "kind": kind,
                    "field": "document_type",
                    "replacement": replacement,
                    "reason": reason,
                }
            )
        elif kind == "topic":
            if (
                item.get("field") != "topic"
                or not isinstance(replacement, str)
                or not replacement.strip()
                or len(replacement) > 200
            ):
                continue
            if not privacy.validate_public_text(replacement, state["private_names"]):
                continue
            accepted.append(
                {
                    "kind": kind,
                    "field": "topic",
                    "replacement": replacement,
                    "reason": reason,
                }
            )
        elif kind == "recipient_role":
            if (
                item.get("field") != "recipient_role"
                or not isinstance(replacement, str)
                or replacement not in state["role_counts"]
            ):
                continue
            accepted.append(
                {
                    "kind": kind,
                    "field": "recipient_role",
                    "replacement": replacement,
                    "reason": reason,
                }
            )
    return {"suggestions": accepted}


def build_graph():
    graph = StateGraph(AnalysisState)
    graph.add_node("prepare", _prepare)
    graph.add_node("tool_pass", _tool_pass)
    graph.add_node("execute_tools", _execute_tools)
    graph.add_node("synthesize", _synthesize)
    graph.add_node("validate", _validate)
    graph.set_entry_point("prepare")
    graph.add_edge("prepare", "tool_pass")
    graph.add_edge("tool_pass", "execute_tools")
    graph.add_edge("execute_tools", "synthesize")
    graph.add_edge("synthesize", "validate")
    graph.add_edge("validate", END)
    return graph.compile()


class LetterAssistanceService:
    def __init__(
        self,
        settings: Settings,
        client,
        adapter: CompletionAdapter | None = None,
        privacy_filter: LocalPrivacyFilter | None = None,
    ) -> None:
        self._settings = settings
        self._client = client
        self._adapter = adapter
        try:
            self._privacy = privacy_filter or LocalPrivacyFilter()
        except PrivacyReviewRequired as error:
            raise HTTPException(status_code=503, detail=error.code) from error
        self._graph = build_graph()

    def _preview_token(
        self,
        document: LetterDocument,
        user_id,
        kinds,
        redacted: RedactedText,
        expires_at: datetime,
        manual_redactions: list[RedactionRange],
    ) -> str:
        claims = {
            "document_id": str(document.id),
            "user_id": str(user_id),
            "source_hash": document.source_hash,
            "kinds": sorted(kinds),
            "redacted_hash": hashlib.sha256(redacted.text.encode()).hexdigest(),
            "manual_redactions": [item.model_dump() for item in manual_redactions],
            "expires_at": int(expires_at.timestamp()),
            "nonce": secrets.token_urlsafe(12),
        }
        payload = (
            base64.urlsafe_b64encode(json.dumps(claims, separators=(",", ":")).encode())
            .decode()
            .rstrip("=")
        )
        key = self._settings.AI_PREVIEW_SIGNING_KEY.get_secret_value().encode()
        signature = hmac.new(key, payload.encode(), hashlib.sha256).hexdigest()
        return f"{payload}.{signature}"

    def _verify_preview(
        self,
        token: str,
        document: LetterDocument,
        user_id,
        kinds: list[SuggestionKind],
        redacted: RedactedText,
        manual_redactions: list[RedactionRange],
    ) -> None:
        try:
            payload, signature = token.split(".", 1)
            key = self._settings.AI_PREVIEW_SIGNING_KEY.get_secret_value().encode()
            expected_signature = hmac.new(
                key, payload.encode(), hashlib.sha256
            ).hexdigest()
            claims = json.loads(
                base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))
            )
        except (ValueError, json.JSONDecodeError) as error:
            raise HTTPException(
                status_code=409, detail="PRIVACY_PREVIEW_EXPIRED"
            ) from error
        expected_hash = hashlib.sha256(redacted.text.encode()).hexdigest()
        if (
            not hmac.compare_digest(signature, expected_signature)
            or claims
            != {
                "document_id": str(document.id),
                "user_id": str(user_id),
                "source_hash": document.source_hash,
                "kinds": sorted(kinds),
                "redacted_hash": expected_hash,
                "manual_redactions": [item.model_dump() for item in manual_redactions],
                "expires_at": claims.get("expires_at"),
                "nonce": claims.get("nonce"),
            }
            or claims.get("expires_at", 0) < int(datetime.now(UTC).timestamp())
        ):
            raise HTTPException(status_code=409, detail="PRIVACY_PREVIEW_EXPIRED")

    async def create_preview(
        self,
        document: LetterDocument,
        user_id,
        kinds: list[SuggestionKind],
        manual_redactions: list[RedactionRange],
    ) -> dict[str, Any]:
        redacted, _, _ = await _privacy_material(
            document, self._privacy, manual_redactions
        )
        expires_at = datetime.now(UTC) + timedelta(minutes=5)
        return {
            "source_hash": document.source_hash,
            "redacted_body": redacted.text,
            "redaction_count": len(redacted.spans),
            "preview_token": self._preview_token(
                document, user_id, kinds, redacted, expires_at, manual_redactions
            ),
            "expires_at": expires_at,
            "manual_redactions": manual_redactions,
            "analysis_available": self._provider_configured,
        }

    async def analyze(
        self,
        document: LetterDocument,
        user_id,
        kinds: list[SuggestionKind],
        preview_token: str,
        manual_redactions: list[RedactionRange],
        collaboration=None,
        actor=None,
    ) -> list[LetterSuggestionDocument]:
        if self._settings.LLM_PROVIDER == "disabled":
            raise HTTPException(status_code=503, detail="LLM_DISABLED")
        if not self._provider_configured:
            raise HTTPException(status_code=503, detail="LLM_NOT_CONFIGURED")
        redacted, role_counts, private_names = await _privacy_material(
            document, self._privacy, manual_redactions
        )
        self._verify_preview(
            preview_token, document, user_id, kinds, redacted, manual_redactions
        )
        adapter = self._adapter or GroqCompletionAdapter(self._settings)
        state: AnalysisState = {
            "document": document,
            "requested_kinds": kinds,
            "adapter": adapter,
            "quota": QuotaService(self._settings, self._client),
            "settings": self._settings,
            "privacy": self._privacy,
            "messages": [],
            "analysis_budget": [0],
            "retry_budget": [0],
            "redacted": redacted,
            "role_counts": role_counts,
            "private_names": private_names,
        }
        try:
            try:
                result = await asyncio.wait_for(
                    self._graph.ainvoke(state),
                    timeout=self._settings.LLM_REQUEST_TIMEOUT_SECONDS * 2,
                )
            except TimeoutError as error:
                raise HTTPException(
                    status_code=503, detail="LLM_ANALYSIS_TIMEOUT"
                ) from error
            if collaboration is not None and actor is not None:
                await collaboration.checkpoint_now(document.id, actor)
            current = await LetterDocument.find_one(LetterDocument.id == document.id)
            if current is None or current.source_hash != document.source_hash:
                raise HTTPException(status_code=409, detail="STALE_SOURCE")
            suggestions = []
            for item in result.get("suggestions", []):
                suggestion = LetterSuggestionDocument(
                    document_id=document.id,
                    source_hash=document.source_hash,
                    **item,
                )
                await suggestion.insert()
                suggestions.append(suggestion)
            return suggestions
        finally:
            if self._adapter is None and isinstance(adapter, GroqCompletionAdapter):
                await adapter.close()

    @property
    def _provider_configured(self) -> bool:
        key = self._settings.GROQ_API_KEY
        return bool(key and key.get_secret_value().strip())
