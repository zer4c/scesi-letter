from uuid import uuid4

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


STATUS_CODES = {
    400: "VALIDATION_ERROR",
    401: "UNAUTHENTICATED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    409: "CONFLICT",
    422: "VALIDATION_ERROR",
    429: "RATE_LIMITED",
}


def request_id(request: Request) -> str:
    value = getattr(request.state, "request_id", None)
    if value is None:
        value = uuid4().hex
        request.state.request_id = value
    return value


async def http_exception_handler(
    request: Request, error: StarletteHTTPException
) -> JSONResponse:
    code = STATUS_CODES.get(error.status_code, "INTERNAL_ERROR")
    message = error.detail if isinstance(error.detail, str) and error.detail in {
        "UNAUTHENTICATED",
        "FORBIDDEN",
        "RATE_LIMITED",
        "CONFLICT",
        "VALIDATION_ERROR",
    } else code
    details = None
    retry_after = (error.headers or {}).get("Retry-After")
    if retry_after and retry_after.isdecimal():
        details = {"retry_after_seconds": int(retry_after)}

    headers = dict(error.headers or {})
    headers["X-Request-ID"] = request_id(request)
    return JSONResponse(
        status_code=error.status_code,
        headers=headers,
        content={
            "error": {"code": code, "message": message, "details": details},
            "request_id": request_id(request),
        },
    )


async def validation_exception_handler(
    request: Request, error: RequestValidationError
) -> JSONResponse:
    details = [
        {
            "location": [str(part) for part in item.get("loc", ())],
            "code": item.get("type", "invalid"),
        }
        for item in error.errors(include_input=False)
    ]
    identifier = request_id(request)
    return JSONResponse(
        status_code=422,
        headers={"X-Request-ID": identifier},
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Request validation failed",
                "details": details,
            },
            "request_id": identifier,
        },
    )
