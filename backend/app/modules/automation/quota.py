import asyncio
import math
import re
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi import HTTPException
from pymongo.errors import PyMongoError

from app.core.config import Settings
from app.core.database import transaction
from app.modules.automation.documents import (
    LLMQuotaGateDocument,
    LLMQuotaReservationDocument,
)


class QuotaExceeded(Exception):
    def __init__(self, retry_after: int) -> None:
        self.retry_after = max(1, retry_after)
        super().__init__("LLM_RATE_LIMITED")


def _effective_tokens(event: dict, dimension: str) -> int:
    actual = event.get(f"actual_{dimension}_tokens")
    estimate = event.get(f"estimated_{dimension}_tokens", 0)
    return int(actual if actual is not None else estimate)


class QuotaService:
    def __init__(self, settings: Settings, client) -> None:
        self._settings = settings
        self._client = client

    async def reserve(
        self, estimated_input: int, output_budget: int
    ) -> LLMQuotaReservationDocument:
        for attempt in range(5):
            try:
                return await self._reserve_once(estimated_input, output_budget)
            except PyMongoError as error:
                transient = error.has_error_label(
                    "TransientTransactionError"
                ) or getattr(error, "code", None) in {112, 251, 11000}
                if not transient or attempt == 4:
                    raise HTTPException(
                        status_code=503, detail="LLM_QUOTA_UNAVAILABLE"
                    ) from error
                await asyncio.sleep(min(0.02 * (2**attempt), 0.25))
        raise HTTPException(status_code=503, detail="LLM_QUOTA_UNAVAILABLE")

    async def _reserve_once(
        self, estimated_input: int, output_budget: int
    ) -> LLMQuotaReservationDocument:
        settings = self._settings
        now = datetime.now(UTC)
        minute_start = now - timedelta(minutes=1)
        day_start = now - timedelta(days=1)
        async with transaction(self._client) as session:
            gates = LLMQuotaGateDocument.get_pymongo_collection()
            await gates.update_one(
                {"model": settings.GROQ_MODEL},
                {
                    "$setOnInsert": {
                        "_id": uuid4(),
                        "model": settings.GROQ_MODEL,
                        "revision": 0,
                    }
                },
                upsert=True,
                session=session,
            )
            gate = await LLMQuotaGateDocument.find_one(
                LLMQuotaGateDocument.model == settings.GROQ_MODEL,
                session=session,
            )
            if gate is None:
                raise HTTPException(status_code=503, detail="LLM_QUOTA_UNAVAILABLE")
            gate.revision += 1
            await gate.save(session=session)
            collection = LLMQuotaReservationDocument.get_pymongo_collection()
            minute_events = await collection.find(
                {"model": settings.GROQ_MODEL, "created_at": {"$gte": minute_start}},
                session=session,
            ).to_list(length=None)
            day_events = minute_events + await collection.find(
                {
                    "model": settings.GROQ_MODEL,
                    "created_at": {"$gte": day_start, "$lt": minute_start},
                },
                session=session,
            ).to_list(length=None)
            minute_requests = len(minute_events)
            day_requests = len(day_events)
            minute_input = sum(
                _effective_tokens(event, "input") for event in minute_events
            )
            minute_output = sum(
                _effective_tokens(event, "output") for event in minute_events
            )
            day_tokens = sum(
                _effective_tokens(event, "input") + _effective_tokens(event, "output")
                for event in day_events
            )
            if minute_requests + 1 > settings.GROQ_LIMIT_RPM:
                raise QuotaExceeded(60)
            if day_requests + 1 > settings.GROQ_LIMIT_RPD:
                raise QuotaExceeded(86400)
            if (
                minute_input + minute_output + estimated_input + output_budget
                > settings.GROQ_LIMIT_TPM
            ):
                raise QuotaExceeded(60)
            if day_tokens + estimated_input + output_budget > settings.GROQ_LIMIT_TPD:
                raise QuotaExceeded(86400)
            if (
                settings.GROQ_LIMIT_ITPM
                and minute_input + estimated_input > settings.GROQ_LIMIT_ITPM
            ):
                raise QuotaExceeded(60)
            if (
                settings.GROQ_LIMIT_OTPM
                and minute_output + output_budget > settings.GROQ_LIMIT_OTPM
            ):
                raise QuotaExceeded(60)
            retry_after = self._check_header_limits(
                gate, minute_events, day_events, estimated_input, output_budget, now
            )
            if retry_after:
                raise QuotaExceeded(retry_after)
            reservation = LLMQuotaReservationDocument(
                model=settings.GROQ_MODEL,
                estimated_input_tokens=estimated_input,
                estimated_output_tokens=output_budget,
                created_at=now,
            )
            await reservation.insert(session=session)
            return reservation

    @staticmethod
    def _check_header_limits(
        gate, minute_events, day_events, input_tokens, output_tokens, now
    ):
        if gate.header_tpm_reset_at and gate.header_tpm_reset_at > now:
            observed = gate.header_tpm_observed_at or now
            consumed = sum(
                _effective_tokens(event, "input") + _effective_tokens(event, "output")
                for event in minute_events
                if event.get("created_at") >= observed
            )
            if (
                gate.header_tpm_remaining is not None
                and consumed + input_tokens + output_tokens > gate.header_tpm_remaining
            ):
                return max(1, int((gate.header_tpm_reset_at - now).total_seconds()))
        if gate.header_rpd_reset_at and gate.header_rpd_reset_at > now:
            observed = gate.header_rpd_observed_at or now
            consumed = sum(
                1 for event in day_events if event.get("created_at") >= observed
            )
            if (
                gate.header_rpd_remaining is not None
                and consumed + 1 > gate.header_rpd_remaining
            ):
                return max(1, int((gate.header_rpd_reset_at - now).total_seconds()))
        return None

    async def settle(
        self,
        reservation_id,
        input_tokens: int | None,
        output_tokens: int | None,
        headers: dict[str, str],
        uncertain: bool = False,
        observed_at: datetime | None = None,
    ) -> None:
        now = datetime.now(UTC)
        observed_at = observed_at or now
        async with transaction(self._client) as session:
            reservation = await LLMQuotaReservationDocument.find_one(
                LLMQuotaReservationDocument.id == reservation_id,
                session=session,
            )
            if reservation is None:
                return
            if input_tokens is not None:
                reservation.actual_input_tokens = max(0, input_tokens)
            if output_tokens is not None:
                reservation.actual_output_tokens = max(0, output_tokens)
            reservation.status = "uncertain" if uncertain else "settled"
            reservation.settled_at = now
            await reservation.save(session=session)
            gate = await LLMQuotaGateDocument.find_one(
                LLMQuotaGateDocument.model == reservation.model,
                session=session,
            )
            if gate is not None:
                self._tighten_header(gate, headers, observed_at, now)
                gate.revision += 1
                await gate.save(session=session)

    @staticmethod
    def _tighten_header(
        gate, headers: dict[str, str], observed_at: datetime, now: datetime
    ) -> None:
        for dimension, remaining_name, reset_name in (
            ("rpd", "x-ratelimit-remaining-requests", "x-ratelimit-reset-requests"),
            ("tpm", "x-ratelimit-remaining-tokens", "x-ratelimit-reset-tokens"),
        ):
            try:
                remaining = int(headers[remaining_name])
                seconds = parse_reset_duration(headers[reset_name])
            except (KeyError, TypeError, ValueError):
                continue
            observed_field = f"header_{dimension}_observed_at"
            reset_field = f"header_{dimension}_reset_at"
            old_reset = getattr(gate, reset_field)
            old_remaining = getattr(gate, f"header_{dimension}_remaining")
            old_observed = getattr(gate, observed_field)
            if old_observed is not None and old_observed > observed_at:
                continue
            reset_at = observed_at + timedelta(seconds=seconds)
            if old_reset is not None and old_reset > now:
                remaining = min(
                    remaining, old_remaining if old_remaining is not None else remaining
                )
                reset_at = max(old_reset, reset_at)
            setattr(gate, f"header_{dimension}_remaining", max(0, remaining))
            setattr(gate, observed_field, now)
            setattr(gate, reset_field, reset_at)


def parse_reset_duration(value: str) -> int:
    match = re.fullmatch(
        r"(?:(\d+)h)?(?:(\d+)m)?(?:(\d+(?:\.\d+)?)s)?", value.strip().casefold()
    )
    if not match or not any(match.groups()):
        raise ValueError("Invalid reset duration")
    hours, minutes, seconds = match.groups()
    total = (
        int(hours or 0) * 3600 + int(minutes or 0) * 60 + math.ceil(float(seconds or 0))
    )
    if total <= 0:
        raise ValueError("Invalid reset duration")
    return total
